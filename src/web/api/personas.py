"""Persona CRUD + bulk-import endpoints under /api/personas/.

All writes go through ``orchestrator.personas`` (create/update/delete/import);
these handlers only validate and translate to/from JSON.
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import personas as personas_registry


def _parse_tags(value: Any) -> list[str]:
    """Accept a list or a comma-separated string of tags; return a clean list."""
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []

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
        )
    except personas_registry.PersonaWriteError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "slug": p.slug, "group": p.group})


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
        )
    except personas_registry.PersonaWriteError as e:
        code = 404 if "not found" in str(e).lower() else 400
        return JSONResponse({"ok": False, "error": str(e)}, status_code=code)
    return JSONResponse({"ok": True, "slug": p.slug, "group": p.group})


# Bulk-import safety caps for uploaded zips: refuse pathological archives
# (zip bombs) by bounding entry count and total uncompressed size before any
# bytes are read into memory. We never extract to disk — entries are read into
# memory and parsed — so path traversal is a non-issue here.
_ZIP_MAX_ENTRIES = 1000
_ZIP_MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MiB uncompressed
_MARKDOWN_SUFFIXES = (".md", ".markdown")


def _cards_from_zip(b64: str, source: str) -> tuple[list[dict[str, str]], list[str]]:
    """Decode a base64 zip and pull out its Markdown cards.

    Returns ``(cards, errors)`` where each card is ``{"filename", "text"}`` in
    the same shape the loose-file path uses, so both feed the same importer.
    Directories, ``__MACOSX`` metadata, dotfiles, and any non-Markdown entry are
    ignored, so a zip of cards mixed with images/other files just yields the
    cards. Enforces ``_ZIP_MAX_ENTRIES`` / ``_ZIP_MAX_TOTAL_BYTES`` to refuse
    zip bombs; a malformed archive yields a single error and no cards.
    """
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        return [], [f"{source}: not valid base64"]
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return [], [f"{source}: not a valid zip archive"]
    cards: list[dict[str, str]] = []
    errors: list[str] = []
    with zf:
        infos = zf.infolist()
        if len(infos) > _ZIP_MAX_ENTRIES:
            return [], [f"{source}: archive has too many entries (> {_ZIP_MAX_ENTRIES})"]
        if sum(i.file_size for i in infos) > _ZIP_MAX_TOTAL_BYTES:
            cap_mib = _ZIP_MAX_TOTAL_BYTES // (1024 * 1024)
            return [], [f"{source}: archive too large uncompressed (> {cap_mib} MiB)"]
        for info in infos:
            name = info.filename
            base = Path(name).name
            if info.is_dir() or name.startswith("__MACOSX/") or base.startswith("."):
                continue
            if not name.lower().endswith(_MARKDOWN_SUFFIXES):
                continue
            try:
                text = zf.read(info).decode("utf-8")
            except (UnicodeDecodeError, zipfile.BadZipFile, OSError) as e:
                errors.append(f"{source} → {name}: could not read ({e})")
                continue
            cards.append({"filename": base, "text": text})
    return cards, errors


async def api_persona_import(request: Request) -> Response:
    """POST /api/personas/import — bulk-create personas from uploaded Markdown.

    Body: ``{"group": str, "overwrite": bool, "files": [{"filename", "text"}],
    "zips": [{"filename", "b64"}]}``. Each loose file is parsed as a seed-style
    card (frontmatter + body); each zip is expanded server-side and its
    ``.md``/``.markdown`` entries are imported the same way (other files in the
    archive are ignored). At least one of ``files``/``zips`` must be present.
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
    zips = payload.get("zips")
    has_files = isinstance(files, list) and files
    has_zips = isinstance(zips, list) and zips
    if not has_files and not has_zips:
        return JSONResponse({"ok": False, "error": "no files provided"}, status_code=400)
    group = (payload.get("group") or personas_registry.DEFAULT_DEBATER_GROUP).strip() \
        or personas_registry.DEFAULT_DEBATER_GROUP
    overwrite = bool(payload.get("overwrite"))

    # Normalize loose files and zip contents into one list of cards so both
    # paths share the importer below.
    cards: list[dict[str, str]] = []
    errors: list[str] = []
    if has_files:
        for f in files:
            if isinstance(f, dict):
                cards.append({"filename": str(f.get("filename") or ""), "text": f.get("text") or ""})
    if has_zips:
        for z in zips:
            if not isinstance(z, dict):
                continue
            zcards, zerrs = _cards_from_zip(
                str(z.get("b64") or ""), str(z.get("filename") or "archive.zip"),
            )
            cards.extend(zcards)
            errors.extend(zerrs)
    if not cards:
        if errors:
            return JSONResponse({"ok": True, "imported": 0, "skipped": 0, "errors": errors})
        return JSONResponse({"ok": False, "error": "no Markdown cards found in the upload"}, status_code=400)

    imported = 0
    for c in cards:
        filename = c["filename"]
        try:
            personas_registry.import_persona_card(
                c["text"], group=group, filename=filename, overwrite=overwrite,
            )
            imported += 1
        except personas_registry.PersonaWriteError as e:
            errors.append(f"{filename or '(unnamed)'}: {e}")
    return JSONResponse({
        "ok": True, "imported": imported,
        "skipped": len(cards) - imported, "errors": errors,
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
    return JSONResponse({"ok": True})
