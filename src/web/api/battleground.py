"""AgentBattleground bridge: ``/api/battleground/*``.

The browser extension can't speak MCP — MCP here is stdio, spawned per CLI.
So the extension talks HTTP to this local process, which writes the same
SQLite file the MCP server reads. Same bus as always; the extension is just
another writer.

    extension  --HTTP-->  this module  -->  chat.db  <--MCP--  CLI agent

Two deliberate constraints:

* **Local-only data.** ``battleground_arenas`` / ``battleground_drafts`` are
  absent from the sidecar's column lists, so captured third-party page content
  never reaches the Fly mirror. On the hosted mirror these POSTs 403 via
  ``ReadOnlyMiddleware`` like every other mutation.
* **Draft, never post.** Nothing here submits anything to any website. The
  agent's reply lands as a ``pending`` draft; the operator approves it in the
  side panel; the extension *types it into the composer* and a human clicks
  the site's own post button. ``POST /drafts/{id}/verdict`` is that gate.

Auth follows the ingest pattern in ``web/api/sync.py``, but opt-in from the
other direction: unset ``AGENT_CHAT_BATTLEGROUND_TOKEN`` and the endpoints are
open (the repo's local no-auth posture); set it and every request must carry
``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import personas as orch_personas
from orchestrator import preflight as orch_preflight
from web.db import (
    ARENA_CLOSED,
    ARENA_OPEN,
    DRAFT_VERDICTS,
    bg_create_arena,
    bg_delete_arena,
    bg_get_arena,
    bg_list_arenas,
    bg_merge_thread,
    bg_set_verdict,
    bg_update_arena,
)

# Guardrails on what a page capture may push into the DB. A thread is a
# snapshot for the agent to argue against, not an archive of the site.
MAX_POSTS = 200
MAX_POST_CHARS = 8_000
MAX_FIELD_CHARS = 2_000

# Site labels the extension's adapters can produce. An unrecognised one is
# coerced to "generic" rather than rejected — a capture is worth having even
# when this list is behind the extension.
KNOWN_SITES = (
    "reddit",
    "x",
    "hackernews",
    "youtube",
    "linkedin",
    "substack",
    "discourse",
    "disqus",
    "generic",
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _unauthorized() -> Response:
    return JSONResponse(
        {"error": "invalid or missing bearer token"},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="agent_chat_battleground"'},
    )


def _authorized(request: Request) -> bool:
    """True when the request may proceed.

    No ``AGENT_CHAT_BATTLEGROUND_TOKEN`` set → open, matching the rest of the
    local web UI. Token set → require an exact bearer match.
    """
    expected = os.environ.get("AGENT_CHAT_BATTLEGROUND_TOKEN")
    if not expected:
        return True
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    return secrets.compare_digest(
        header[7:].encode("utf-8"), expected.encode("utf-8")
    )


# ---------------------------------------------------------------------------
# Input scrubbing
# ---------------------------------------------------------------------------

def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> str | None:
    """Coerce a JSON value to a bounded string, or None when it's empty.

    Everything here arrives from a web page the operator happened to be
    looking at, so nothing is trusted for type or length.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _clean_posts(raw: Any) -> list[dict[str, Any]] | str:
    """Normalize a captured thread, or return an error string.

    Each post keeps only the fields the agent needs to argue: a stable ``id``,
    ``author``, ``text``, and the optional ``permalink`` / ``score`` /
    ``timestamp`` / ``depth`` context. Unknown keys are dropped rather than
    stored, so a hostile page can't smuggle a large blob into the DB.
    """
    if not isinstance(raw, list):
        return "thread must be an array of posts"
    if len(raw) > MAX_POSTS:
        raw = raw[:MAX_POSTS]
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f"thread[{i}] must be an object"
        text = _clip(item.get("text"), MAX_POST_CHARS)
        if not text:
            continue  # empty nodes (dividers, deleted comments) carry nothing
        post: dict[str, Any] = {
            "id": _clip(item.get("id"), 200) or f"post-{i}",
            "author": _clip(item.get("author"), 200) or "unknown",
            "text": text,
        }
        for key, limit in (("permalink", 500), ("score", 50), ("timestamp", 100)):
            val = _clip(item.get(key), limit)
            if val:
                post[key] = val
        depth = item.get("depth")
        if isinstance(depth, int) and 0 <= depth <= 50:
            post["depth"] = depth
        out.append(post)
    if not out:
        return "thread contained no readable posts"
    return out


async def _body(request: Request) -> dict[str, Any] | None:
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


# ---------------------------------------------------------------------------
# Arenas
# ---------------------------------------------------------------------------

async def api_bg_arenas(request: Request) -> Response:
    """GET /api/battleground/arenas — list arenas, newest first.

    Query params: ``status`` (``open``/``closed``), ``agent`` (returns that
    agent's arenas plus unassigned ones).
    """
    if not _authorized(request):
        return _unauthorized()
    status = request.query_params.get("status", "").strip() or None
    if status and status not in (ARENA_OPEN, ARENA_CLOSED):
        return JSONResponse(
            {"error": f"status must be '{ARENA_OPEN}' or '{ARENA_CLOSED}'"},
            status_code=400,
        )
    agent = request.query_params.get("agent", "").strip() or None
    try:
        arenas = bg_list_arenas(status=status, agent_id=agent)
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    return JSONResponse({"count": len(arenas), "arenas": arenas})


async def api_bg_create_arena(request: Request) -> Response:
    """POST /api/battleground/arenas — open an arena from a page capture.

    Body::

        {"url": str, "site": str, "title": str,
         "thread": [{"id", "author", "text", "permalink"?, "score"?,
                     "timestamp"?, "depth"?}, ...],
         "stance": str?, "agent_id": str?, "persona": str?}

    ``persona`` is a slug or display name resolved against the registry; the
    card **body is snapshotted onto the arena row** so a later edit to the
    persona can't retroactively change what the agent was told to be.
    """
    if not _authorized(request):
        return _unauthorized()
    body = await _body(request)
    if body is None:
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)

    url = _clip(body.get("url"), 2_000)
    title = _clip(body.get("title"), 500)
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    site = (_clip(body.get("site"), 50) or "generic").lower()
    if site not in KNOWN_SITES:
        site = "generic"

    posts = _clean_posts(body.get("thread"))
    if isinstance(posts, str):
        return JSONResponse({"error": posts}, status_code=400)

    agent_id = _clip(body.get("agent_id"), 100)
    if agent_id and agent_id not in orch_preflight.SUPPORTED_CLIS:
        return JSONResponse(
            {
                "error": f"unknown agent_id {agent_id!r}",
                "supported": list(orch_preflight.SUPPORTED_CLIS),
            },
            status_code=400,
        )

    persona_slug = persona_name = persona_body = None
    persona_query = _clip(body.get("persona"), 200)
    if persona_query:
        persona = orch_personas.get_persona(persona_query)
        if persona is None:
            return JSONResponse(
                {"error": f"no persona matches {persona_query!r}"}, status_code=400
            )
        persona_slug, persona_name, persona_body = (
            persona.slug, persona.name, persona.body
        )

    try:
        arena = bg_create_arena(
            url=url,
            site=site,
            title=title or url,
            thread=posts,
            stance=_clip(body.get("stance"), 4_000),
            agent_id=agent_id,
            persona_slug=persona_slug,
            persona_name=persona_name,
            persona_body=persona_body,
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    return JSONResponse({"arena": arena}, status_code=201)


async def api_bg_arena(request: Request) -> Response:
    """GET /api/battleground/arenas/{aid} — one arena plus every draft on it.

    This is what the side panel polls: it renders the newest ``pending`` draft
    as the Approve/Edit/Discard card.
    """
    if not _authorized(request):
        return _unauthorized()
    aid = int(request.path_params["aid"])
    try:
        data = bg_get_arena(aid)
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    if data is None:
        return JSONResponse({"error": f"no arena {aid}"}, status_code=404)
    return JSONResponse(data)


async def api_bg_update_arena(request: Request) -> Response:
    """POST /api/battleground/arenas/{aid} — patch stance / cast / status.

    Every field is optional; omitted fields are left alone. Passing
    ``persona`` re-snapshots the card body.
    """
    if not _authorized(request):
        return _unauthorized()
    aid = int(request.path_params["aid"])
    body = await _body(request)
    if body is None:
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)

    status = _clip(body.get("status"), 20)
    if status and status not in (ARENA_OPEN, ARENA_CLOSED):
        return JSONResponse(
            {"error": f"status must be '{ARENA_OPEN}' or '{ARENA_CLOSED}'"},
            status_code=400,
        )
    agent_id = _clip(body.get("agent_id"), 100)
    if agent_id and agent_id not in orch_preflight.SUPPORTED_CLIS:
        return JSONResponse(
            {
                "error": f"unknown agent_id {agent_id!r}",
                "supported": list(orch_preflight.SUPPORTED_CLIS),
            },
            status_code=400,
        )

    persona_slug = persona_name = persona_body = None
    persona_query = _clip(body.get("persona"), 200)
    if persona_query:
        persona = orch_personas.get_persona(persona_query)
        if persona is None:
            return JSONResponse(
                {"error": f"no persona matches {persona_query!r}"}, status_code=400
            )
        persona_slug, persona_name, persona_body = (
            persona.slug, persona.name, persona.body
        )

    try:
        arena = bg_update_arena(
            aid,
            stance=_clip(body.get("stance"), 4_000),
            agent_id=agent_id,
            persona_slug=persona_slug,
            persona_name=persona_name,
            persona_body=persona_body,
            status=status,
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    if arena is None:
        return JSONResponse({"error": f"no arena {aid}"}, status_code=404)
    return JSONResponse({"arena": arena})


async def api_bg_capture(request: Request) -> Response:
    """POST /api/battleground/arenas/{aid}/capture — fold in a re-capture.

    Body: ``{"thread": [...]}``. Known post ids are refreshed, new ones
    appended, so the agent sees replies that landed since the last capture
    without the arena being recreated.
    """
    if not _authorized(request):
        return _unauthorized()
    aid = int(request.path_params["aid"])
    body = await _body(request)
    if body is None:
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    posts = _clean_posts(body.get("thread"))
    if isinstance(posts, str):
        return JSONResponse({"error": posts}, status_code=400)
    try:
        arena = bg_merge_thread(aid, posts)
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    if arena is None:
        return JSONResponse({"error": f"no arena {aid}"}, status_code=404)
    return JSONResponse({"arena": arena, "posts_added": arena["posts_added"]})


async def api_bg_delete_arena(request: Request) -> Response:
    """POST /api/battleground/arenas/{aid}/delete — remove arena + drafts."""
    if not _authorized(request):
        return _unauthorized()
    aid = int(request.path_params["aid"])
    try:
        result = bg_delete_arena(aid)
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    if result is None:
        return JSONResponse({"error": f"no arena {aid}"}, status_code=404)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

async def api_bg_verdict(request: Request) -> Response:
    """POST /api/battleground/drafts/{did}/verdict — the human-in-the-loop gate.

    Body: ``{"verdict": "approved"|"rejected"|"posted", "note": str?,
    "posted_text": str?}``.

    ``approved`` means the panel may type it into the page composer;
    ``posted`` is set afterwards, once a human has actually clicked the site's
    own submit button, with ``posted_text`` recording any edit the operator
    made. ``rejected`` + ``note`` reads to the agent as a revision brief.
    """
    if not _authorized(request):
        return _unauthorized()
    did = int(request.path_params["did"])
    body = await _body(request)
    if body is None:
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    verdict = (_clip(body.get("verdict"), 20) or "").lower()
    if verdict not in DRAFT_VERDICTS:
        return JSONResponse(
            {"error": f"verdict must be one of {list(DRAFT_VERDICTS)}"},
            status_code=400,
        )
    try:
        draft = bg_set_verdict(
            did,
            verdict,
            note=_clip(body.get("note"), 4_000),
            posted_text=_clip(body.get("posted_text"), 50_000),
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    if draft is None:
        return JSONResponse({"error": f"no draft {did}"}, status_code=404)
    return JSONResponse({"draft": draft})


# ---------------------------------------------------------------------------
# Roster (one round trip for the panel's pickers)
# ---------------------------------------------------------------------------

async def api_bg_roster(request: Request) -> Response:
    """GET /api/battleground/roster — personas + CLI ids for the side panel.

    Debater roster only (``list_debater_personas`` excludes the reserved
    ``AI-Models`` cards), so the picker never offers "Claude Code" as a
    character to argue as.
    """
    if not _authorized(request):
        return _unauthorized()
    try:
        personas = [
            {"slug": p.slug, "name": p.name, "group": p.group}
            for p in orch_personas.list_debater_personas()
        ]
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    return JSONResponse({
        "personas": personas,
        "agents": list(orch_preflight.SUPPORTED_CLIS),
        "sites": list(KNOWN_SITES),
    })
