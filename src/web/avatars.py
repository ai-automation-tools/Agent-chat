"""Persona avatar assets — resolve a persona slug to its image.

Three sources, in order:

1. **An uploaded avatar** on the persona's DB row (``avatar_mime`` /
   ``avatar_data``, written from the /personas page — see
   ``orchestrator.personas``). Stored in the DB rather than on disk so the
   sidecar carries it to the hosted mirror with no redeploy.
2. **Shipped file art**, convention-based (mirroring ``web.topics``): the image
   for persona ``<slug>`` is ``images/AgentChat-Avatars/<slug>-avatar.png``, or
   ``.svg`` for the CLI agents' brand-glyph marks.
3. A neutral head-and-shoulders **silhouette**, so every avatar slot always
   renders something — the AI-Models CLI cards, personas with no art yet.

An upload wins over file art on purpose: replacing a shipped avatar from the web
UI is an explicit operator action and should stick.

Served at ``GET /avatars/{slug}`` (route + handler in ``web_ui``). Callers build
the URL with :func:`avatar_url`; render helpers overlay the returned ``<img>``
on the existing initials chip so a load error degrades to the monogram.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from starlette.responses import FileResponse, Response

from orchestrator import personas as personas_registry

# <repo>/images/AgentChat-Avatars. This file is <repo>/src/web/avatars.py, so
# parents[2] is the repo root both locally and inside the Fly image (WORKDIR
# /app, with images/AgentChat-Avatars/ COPYed alongside src/ — see Dockerfile).
AVATARS_DIR = Path(__file__).resolve().parents[2] / "images" / "AgentChat-Avatars"

# Persona slugs are lowercase-hyphen (see orchestrator.personas). Anything else
# is rejected so a path component can never traverse out of AVATARS_DIR.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")

_CACHE = "public, max-age=86400"

# A URL that always resolves to the default silhouette: "_default" can't be a
# persona slug (_SLUG_RE requires a leading [a-z0-9]), so avatar_response falls
# straight through to it. The /personas editor points its preview here after
# "Remove", to show what the persona will look like once saved.
DEFAULT_AVATAR_URL = "/avatars/_default"

# Last-resort "no avatar" silhouette — a standard empty-profile bust. The same
# art is written to disk as default-avatar.svg (the file wins when present, so
# it can be swapped without a code change); this constant covers the case where
# the file didn't ship.
DEFAULT_AVATAR_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="No avatar">
<rect width="128" height="128" fill="#e5e7eb"/>
<circle cx="64" cy="48" r="23" fill="#9ca3af"/>
<path d="M22 119c0-23.2 18.8-41 42-41s42 17.8 42 41z" fill="#9ca3af"/>
</svg>"""


# Uploaded-avatar index ({slug: updated_at}), memoized so building a page of N
# avatar URLs is one query rather than N. Short TTL as a backstop; the write
# paths call invalidate_index() so a fresh upload is visible immediately.
_INDEX_TTL_SECONDS = 30.0
_index_cache: tuple[float, dict[str, str]] | None = None


def uploaded_index() -> dict[str, str]:
    """``{slug: updated_at}`` for personas carrying an uploaded avatar."""
    global _index_cache
    now = time.monotonic()
    if _index_cache is not None and now - _index_cache[0] < _INDEX_TTL_SECONDS:
        return _index_cache[1]
    index = personas_registry.avatar_index()
    _index_cache = (now, index)
    return index


def invalidate_index() -> None:
    """Drop the memoized index. Called by every path that can change a stored
    avatar — the persona write endpoints and the sidecar's ingest — so a new
    upload gets a fresh cache-busting token on the very next render."""
    global _index_cache
    _index_cache = None


def _avatar_version(slug: str) -> str:
    """Cache-busting token for ``slug`` — a digest of the persona row's
    ``updated_at`` when an avatar was uploaded, else the mtime of whichever
    avatar file backs it (empty for the default silhouette). Changes when the
    art is swapped, so a replaced avatar reaches browsers holding a long-cached
    copy of the old one (or the default served before it existed) without a
    manual refresh."""
    if not _SLUG_RE.match(slug or ""):
        return ""
    stamp = uploaded_index().get(slug)
    if stamp:
        return hashlib.sha1(stamp.encode("utf-8")).hexdigest()[:10]
    for ext in ("png", "svg"):
        f = AVATARS_DIR / f"{slug}-avatar.{ext}"
        try:
            if f.is_file():
                return str(int(f.stat().st_mtime))
        except OSError:
            pass
    return ""


def avatar_url(slug: str) -> str:
    """The URL a persona ``slug`` renders its avatar from, content-versioned so
    the long `Cache-Control` can't pin a stale image."""
    v = _avatar_version(slug)
    return f"/avatars/{slug}?v={v}" if v else f"/avatars/{slug}"


def _default_response() -> Response:
    f = AVATARS_DIR / "default-avatar.svg"
    if f.is_file():
        return FileResponse(
            f, media_type="image/svg+xml", headers={"Cache-Control": _CACHE}
        )
    return Response(
        DEFAULT_AVATAR_SVG, media_type="image/svg+xml",
        headers={"Cache-Control": _CACHE},
    )


def avatar_response(slug: str) -> Response:
    """Serve a persona's avatar, else the default silhouette.

    Tries the uploaded image on the persona's DB row first, then
    ``<slug>-avatar.png`` (shipped persona photos), then ``<slug>-avatar.svg``
    (the CLI agents' brand-glyph marks). Falls back to the default silhouette
    when none exists — e.g. a persona with no art, or a bare agent id.

    The DB is read on every request rather than gated on the memoized index, so
    a just-uploaded avatar can never be withheld by a stale cache entry. It's one
    indexed lookup, and the response is cached by the browser for a day."""
    if _SLUG_RE.match(slug or ""):
        stored = personas_registry.get_avatar(slug)
        if stored is not None:
            mime, data = stored
            # Uploaded bytes are operator-supplied, so they're served locked
            # down: nosniff pins the type we verified by magic bytes at upload,
            # and the CSP neuters anything that still manages to be treated as
            # a document.
            return Response(
                data,
                media_type=mime,
                headers={
                    "Cache-Control": _CACHE,
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "default-src 'none'; sandbox",
                },
            )
        for ext, media in (("png", "image/png"), ("svg", "image/svg+xml")):
            f = AVATARS_DIR / f"{slug}-avatar.{ext}"
            if f.is_file():
                return FileResponse(
                    f, media_type=media, headers={"Cache-Control": _CACHE}
                )
    return _default_response()
