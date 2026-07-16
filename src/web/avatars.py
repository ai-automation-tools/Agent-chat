"""Persona avatar assets — resolve a persona slug to its image.

Avatars are convention-based (no schema, mirroring ``web.topics``): the image
for persona ``<slug>`` is ``images/AgentChat-Avatars/<slug>-avatar.png``. Any
slug without a file — the AI-Models CLI cards, personas with no art yet — falls
back to a neutral head-and-shoulders silhouette, so every avatar slot always
renders something.

Served at ``GET /avatars/{slug}`` (route + handler in ``web_ui``). Callers build
the URL with :func:`avatar_url`; render helpers overlay the returned ``<img>``
on the existing initials chip so a load error degrades to the monogram.
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.responses import FileResponse, Response

# <repo>/images/AgentChat-Avatars. This file is <repo>/src/web/avatars.py, so
# parents[2] is the repo root both locally and inside the Fly image (WORKDIR
# /app, with images/AgentChat-Avatars/ COPYed alongside src/ — see Dockerfile).
AVATARS_DIR = Path(__file__).resolve().parents[2] / "images" / "AgentChat-Avatars"

# Persona slugs are lowercase-hyphen (see orchestrator.personas). Anything else
# is rejected so a path component can never traverse out of AVATARS_DIR.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")

_CACHE = "public, max-age=86400"

# Last-resort "no avatar" silhouette — a standard empty-profile bust. The same
# art is written to disk as default-avatar.svg (the file wins when present, so
# it can be swapped without a code change); this constant covers the case where
# the file didn't ship.
DEFAULT_AVATAR_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="No avatar">
<rect width="128" height="128" fill="#e5e7eb"/>
<circle cx="64" cy="48" r="23" fill="#9ca3af"/>
<path d="M22 119c0-23.2 18.8-41 42-41s42 17.8 42 41z" fill="#9ca3af"/>
</svg>"""


def avatar_url(slug: str) -> str:
    """The URL a persona ``slug`` renders its avatar from."""
    return f"/avatars/{slug}"


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

    Tries ``<slug>-avatar.png`` first (persona photos), then ``<slug>-avatar.svg``
    (the CLI agents' brand-glyph marks). Falls back to the default silhouette when
    neither exists — e.g. a persona with no art, or a bare agent id."""
    if _SLUG_RE.match(slug or ""):
        for ext, media in (("png", "image/png"), ("svg", "image/svg+xml")):
            f = AVATARS_DIR / f"{slug}-avatar.{ext}"
            if f.is_file():
                return FileResponse(
                    f, media_type=media, headers={"Cache-Control": _CACHE}
                )
    return _default_response()
