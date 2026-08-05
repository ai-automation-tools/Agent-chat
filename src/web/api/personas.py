"""Persona CRUD + bulk-import endpoints under /api/personas/.

All writes go through ``orchestrator.personas`` (create/update/delete/import);
these handlers only validate and translate to/from JSON.
"""

from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import personas as personas_registry
from web.avatars import invalidate_index


def _parse_tags(value: Any) -> list[str]:
    """Accept a list or a comma-separated string of tags; return a clean list."""
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


def _parse_avatar(payload: dict[str, Any]) -> str | None:
    """Pull the uploaded avatar out of a create/update body.

    Accepts either a bare base64 / ``data:`` string or ``{"b64": ...}`` (what
    the browser sends). Returns None when the request carries no image, which
    the registry reads as "leave whatever is there alone". The bytes are
    validated in ``orchestrator.personas.normalize_avatar``, not here.
    """
    avatar = payload.get("avatar")
    if isinstance(avatar, dict):
        avatar = avatar.get("b64") or avatar.get("data")
    if isinstance(avatar, str) and avatar.strip():
        return avatar
    return None

async def api_persona_list(request: Request) -> Response:
    """GET /api/personas — every persona as ``{slug, name, group}``.

    Index for the topbar command palette (see assets.SHELL_JS), which fetches
    it lazily on first open. Deliberately omits card bodies: the palette only
    matches on name and group, and shipping every body would turn a keystroke
    into a megabyte.

    Includes the reserved ``AI-Models`` group — unlike the casting paths, which
    must exclude it (see ``list_debater_personas``), the palette is pure
    navigation and those cards are real pages a user may want to jump to.
    """
    if not personas_registry.root_exists():
        return JSONResponse([], status_code=200)
    return JSONResponse(
        [
            {"slug": p.slug, "name": p.name, "group": p.group}
            for p in personas_registry.list_personas(None)
        ]
    )


async def api_persona_create(request: Request) -> Response:
    """POST /api/personas — create a new persona."""
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    try:
        p = personas_registry.create_persona(
            name=(payload.get("name") or ""),
            body=(payload.get("body") or ""),
            group=(payload.get("group") or personas_registry.DEFAULT_DEBATER_GROUP).strip(),
            tags=_parse_tags(payload.get("tags")),
            avatar=_parse_avatar(payload),
        )
    except personas_registry.PersonaWriteError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    invalidate_index()
    return JSONResponse({
        "ok": True, "slug": p.slug, "group": p.group,
        "has_avatar": p.has_avatar,
    })


async def api_persona_update(request: Request) -> Response:
    """POST /api/personas/{slug} — update an existing persona."""
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    slug = request.path_params["slug"]
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    try:
        p = personas_registry.update_persona(
            slug,
            name=payload.get("name"),
            body=payload.get("body"),
            tags=_parse_tags(payload.get("tags")) if "tags" in payload else None,
            group=(payload.get("group") or None),
            avatar=_parse_avatar(payload),
            clear_avatar=bool(payload.get("clear_avatar")),
        )
    except personas_registry.PersonaWriteError as e:
        code = 404 if "not found" in str(e).lower() else 400
        return JSONResponse({"ok": False, "error": str(e)}, status_code=code)
    invalidate_index()
    return JSONResponse({
        "ok": True, "slug": p.slug, "group": p.group,
        "has_avatar": p.has_avatar,
    })


# Bulk-import safety caps for uploaded zips: refuse pathological archives
# (zip bombs) by bounding entry count and total uncompressed size before any
# bytes are read into memory. We never extract to disk — entries are read into
# memory and parsed — so path traversal is a non-issue here.
_ZIP_MAX_ENTRIES = 1000
_ZIP_MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MiB uncompressed
_MARKDOWN_SUFFIXES = (".md", ".markdown")
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# An image named "<card>-avatar.png" pairs with "<card>.md"; so does a bare
# "avatar.png" sitting in a per-persona folder (rule 2 in _pair_avatars).
_AVATAR_STEM_RE = re.compile(r"[-_ ]?avatar$", re.IGNORECASE)


def _stem_key(filename: str) -> str:
    """Normalize a filename to the key both a card and its image pair on —
    slugified stem, with any trailing ``-avatar`` removed."""
    stem = _AVATAR_STEM_RE.sub("", Path(filename).stem)
    return personas_registry.slugify(stem)


def _pair_avatars(
    cards: list[dict[str, str]], images: list[dict[str, str]],
) -> None:
    """Attach each image in the upload to the card it belongs to, in place.

    Sets ``card["avatar"]`` to the image's base64 when a pairing is found. The
    rules, first match wins, are the shapes people actually zip personas in:

    1. **Same folder, matching name** — ``crypto-chad.md`` + ``crypto-chad.png``
       (or ``crypto-chad-avatar.png``).
    2. **Same folder, one of each** — ``crypto-chad/card.md`` +
       ``crypto-chad/avatar.png``, whatever the two files are called.
    3. **The whole upload is one card and one image** — the obvious intent when
       someone selects a card and its picture together.

    An image that pairs with nothing is left alone (reported by the caller);
    it is never guessed onto an arbitrary card.
    """
    if not cards or not images:
        return
    by_dir_stem: dict[tuple[str, str], dict[str, str]] = {}
    per_dir: dict[str, list[dict[str, str]]] = {}
    for img in images:
        by_dir_stem.setdefault(
            (img.get("dir", ""), _stem_key(img["filename"])), img)
        per_dir.setdefault(img.get("dir", ""), []).append(img)
    cards_per_dir: dict[str, list[dict[str, str]]] = {}
    for card in cards:
        cards_per_dir.setdefault(card.get("dir", ""), []).append(card)

    for card in cards:
        cdir = card.get("dir", "")
        match = by_dir_stem.get((cdir, _stem_key(card["filename"])))
        if match is None:
            siblings = per_dir.get(cdir, [])
            if len(siblings) == 1 and len(cards_per_dir.get(cdir, [])) == 1:
                match = siblings[0]
        if match is None and len(cards) == 1 and len(images) == 1:
            match = images[0]
        if match is not None:
            card["avatar"] = match["b64"]
            match["paired"] = "1"


def _entries_from_zip(
    b64: str, source: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Decode a base64 zip and pull out its Markdown cards and images.

    Returns ``(cards, images, errors)``. Each card is ``{"filename", "text",
    "dir"}`` and each image ``{"filename", "b64", "dir"}`` — the same shapes the
    loose-file path builds, so both feed the same pairing + importer. ``dir`` is
    the entry's folder inside the archive, which is what lets a zip of
    ``<persona>/card.md`` + ``<persona>/avatar.png`` folders pair correctly.

    Directories, ``__MACOSX`` metadata, dotfiles, and any other file type are
    ignored, so a zip of cards mixed with unrelated files still yields the
    cards. Enforces ``_ZIP_MAX_ENTRIES`` / ``_ZIP_MAX_TOTAL_BYTES`` to refuse
    zip bombs; a malformed archive yields a single error and nothing else.
    """
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        return [], [], [f"{source}: not valid base64"]
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return [], [], [f"{source}: not a valid zip archive"]
    cards: list[dict[str, str]] = []
    images: list[dict[str, str]] = []
    errors: list[str] = []
    with zf:
        infos = zf.infolist()
        if len(infos) > _ZIP_MAX_ENTRIES:
            return [], [], [f"{source}: archive has too many entries (> {_ZIP_MAX_ENTRIES})"]
        if sum(i.file_size for i in infos) > _ZIP_MAX_TOTAL_BYTES:
            cap_mib = _ZIP_MAX_TOTAL_BYTES // (1024 * 1024)
            return [], [], [f"{source}: archive too large uncompressed (> {cap_mib} MiB)"]
        for info in infos:
            name = info.filename
            base = Path(name).name
            if info.is_dir() or name.startswith("__MACOSX/") or base.startswith("."):
                continue
            lower = name.lower()
            is_card = lower.endswith(_MARKDOWN_SUFFIXES)
            is_image = lower.endswith(_IMAGE_SUFFIXES)
            if not (is_card or is_image):
                continue
            folder = str(Path(name).parent).replace("\\", "/")
            if folder == ".":
                folder = ""
            try:
                blob = zf.read(info)
            except (zipfile.BadZipFile, OSError) as e:
                errors.append(f"{source} → {name}: could not read ({e})")
                continue
            if is_card:
                try:
                    text = blob.decode("utf-8")
                except UnicodeDecodeError as e:
                    errors.append(f"{source} → {name}: could not read ({e})")
                    continue
                cards.append({"filename": base, "text": text, "dir": folder})
            else:
                images.append({
                    "filename": base,
                    "b64": base64.b64encode(blob).decode("ascii"),
                    "dir": folder,
                })
    return cards, images, errors


async def api_persona_import(request: Request) -> Response:
    """POST /api/personas/import — bulk-create personas from uploaded Markdown.

    Body: ``{"group": str, "overwrite": bool, "files": [{"filename", "text"}],
    "images": [{"filename", "b64"}], "zips": [{"filename", "b64"}]}``. Each loose
    file is parsed as a seed-style card (frontmatter + body); each zip is
    expanded server-side and its ``.md``/``.markdown`` entries are imported the
    same way. At least one of ``files``/``zips`` must be present.

    **Images ride along with the cards.** Any image in the upload — loose, or
    inside a zip next to the card — is paired to a card by :func:`_pair_avatars`
    and stored as that persona's avatar, so one zip of
    ``<persona>.md`` + ``<persona>.png`` lands a persona with both its
    instructions and its picture. An unpaired or unreadable image is reported and
    skipped; it never blocks the card itself from importing.

    Returns per-card counts plus any error messages so partial imports surface
    cleanly.
    """
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    files = payload.get("files")
    images_in = payload.get("images")
    zips = payload.get("zips")
    has_files = isinstance(files, list) and files
    has_images = isinstance(images_in, list) and images_in
    has_zips = isinstance(zips, list) and zips
    if not has_files and not has_zips:
        # Images alone have nothing to attach to — an avatar for an existing
        # persona is an edit (POST /api/personas/{slug}), not an import.
        return JSONResponse(
            {"ok": False, "error": "no Markdown cards provided"}
            if has_images else {"ok": False, "error": "no files provided"},
            status_code=400,
        )
    group = (payload.get("group") or personas_registry.DEFAULT_DEBATER_GROUP).strip() \
        or personas_registry.DEFAULT_DEBATER_GROUP
    overwrite = bool(payload.get("overwrite"))

    # Normalize loose files and zip contents into one list of cards and one of
    # images so both paths share the pairing + importer below. Loose files carry
    # no folder, so they all land in the "" directory bucket.
    cards: list[dict[str, str]] = []
    images: list[dict[str, str]] = []
    errors: list[str] = []
    if has_files:
        for f in files:
            if isinstance(f, dict):
                cards.append({
                    "filename": str(f.get("filename") or ""),
                    "text": f.get("text") or "", "dir": "",
                })
    if has_images:
        for img in images_in:
            if isinstance(img, dict) and img.get("b64"):
                images.append({
                    "filename": str(img.get("filename") or ""),
                    "b64": str(img.get("b64") or ""), "dir": "",
                })
    if has_zips:
        for z in zips:
            if not isinstance(z, dict):
                continue
            zcards, zimages, zerrs = _entries_from_zip(
                str(z.get("b64") or ""), str(z.get("filename") or "archive.zip"),
            )
            cards.extend(zcards)
            images.extend(zimages)
            errors.extend(zerrs)
    if not cards:
        if errors:
            return JSONResponse({"ok": True, "imported": 0, "skipped": 0,
                                 "avatars": 0, "errors": errors})
        return JSONResponse({"ok": False, "error": "no Markdown cards found in the upload"}, status_code=400)

    _pair_avatars(cards, images)
    for img in images:
        if not img.get("paired"):
            errors.append(
                f"{img['filename'] or '(unnamed image)'}: no matching card in "
                "the upload — image skipped"
            )

    imported = avatars = 0
    for c in cards:
        filename = c["filename"]
        avatar = c.get("avatar")
        if avatar:
            # Validate here rather than inside the importer so a bad image costs
            # the persona its picture, not its existence.
            try:
                personas_registry.normalize_avatar(avatar)
            except personas_registry.PersonaWriteError as e:
                errors.append(f"{filename or '(unnamed)'}: avatar skipped ({e})")
                avatar = None
        try:
            p = personas_registry.import_persona_card(
                c["text"], group=group, filename=filename, overwrite=overwrite,
                avatar=avatar,
            )
            imported += 1
            if avatar and p.has_avatar:
                avatars += 1
        except personas_registry.PersonaWriteError as e:
            errors.append(f"{filename or '(unnamed)'}: {e}")
    invalidate_index()
    return JSONResponse({
        "ok": True, "imported": imported,
        "skipped": len(cards) - imported, "avatars": avatars,
        "errors": errors,
    })


async def api_persona_bulk_delete(request: Request) -> Response:
    """POST /api/personas/bulk-delete — delete many personas at once.

    Body: ``{"items": [{"group": str, "slug": str}, ...]}``. Each item is
    matched on its ``(group, slug)`` pair — slugs are only unique within a
    group, so the group disambiguates duplicates across groups. Returns
    ``{ok, deleted, not_found, errors[]}`` so a partial run surfaces cleanly.
    """
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return JSONResponse({"ok": False, "error": "no personas selected"}, status_code=400)
    deleted = not_found = 0
    errors: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        slug = str(it.get("slug") or "").strip()
        group = str(it.get("group") or "").strip() or None
        if not slug:
            continue
        try:
            if personas_registry.delete_persona(slug, group=group):
                deleted += 1
            else:
                not_found += 1
        except personas_registry.PersonaWriteError as e:
            errors.append(f"{slug}: {e}")
    invalidate_index()
    return JSONResponse({
        "ok": True, "deleted": deleted, "not_found": not_found, "errors": errors,
    })


async def api_persona_delete(request: Request) -> Response:
    """POST /api/personas/{slug}/delete — delete a persona."""
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    slug = request.path_params["slug"]
    try:
        ok = personas_registry.delete_persona(slug)
    except personas_registry.PersonaWriteError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if not ok:
        return JSONResponse({"ok": False, "error": f"persona not found: {slug}"}, status_code=404)
    invalidate_index()
    return JSONResponse({"ok": True})
