"""
agent_chat web UI — local read-only viewer for chat.db.

A small Starlette app that reads the same SQLite database the MCP server
writes to. Run as a separate process; does NOT replace or wrap the MCP
server. Bind defaults to 127.0.0.1.

DB path resolution (same precedence as the MCP server):
    --db-path <path>  >  $AGENT_CHAT_DB  >  <repo>/db/chat.db

Usage:
    python src/web_ui.py                                   # default DB
    python src/web_ui.py --host 0.0.0.0 --port 8765        # custom bind
    python src/web_ui.py --db-path /custom/chat.db         # explicit override

Then open http://127.0.0.1:8765/ in a browser.

This module is the app-assembly entrypoint: page routes, the route table,
middleware wiring, and main(). The implementation lives in the ``web``
package (``web.db`` / ``web.security`` / ``web.assets`` / ``web.render`` /
``web.api``) — see each module's docstring.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

# Orchestrator package (sibling to this file). When run as ``python src/web_ui.py``
# the script's directory is on sys.path so ``orchestrator`` imports natively.
from orchestrator import availability as orch_availability  # noqa: E402
from orchestrator import preflight as orch_preflight  # noqa: E402
from orchestrator import personas as orch_personas  # noqa: E402
from orchestrator.model_personas import ensure_model_personas  # noqa: E402

from web.api.conversations import (  # noqa: E402
    api_conversation,
    api_conversation_export,
    api_conversation_export_zip,
    api_conversation_prompt,
    api_conversations,
    api_delete,
    api_stop,
    api_stream,
)
from web.api.battleground import (  # noqa: E402
    api_bg_arena,
    api_bg_arenas,
    api_bg_capture,
    api_bg_create_arena,
    api_bg_delete_arena,
    api_bg_healthz,
    api_bg_roster,
    api_bg_update_arena,
    api_bg_verdict,
)
from web.api.orchestrate import api_orchestrate  # noqa: E402
from web.api.personas import (  # noqa: E402
    api_persona_bulk_delete,
    api_persona_create,
    api_persona_delete,
    api_persona_import,
    api_persona_list,
    api_persona_update,
)
from web.api.setup import (  # noqa: E402
    api_setup,
    api_setup_save,
    api_setup_seats,
)
from web.api.sync import api_ingest, api_since  # noqa: E402
from web.assets import FAVICON_SVG  # noqa: E402
from web.avatars import avatar_response  # noqa: E402
from web.render.common import _render_generic_404, render_markdown  # noqa: E402,F401
from web.render.conversations import (  # noqa: E402
    _render_conversation,
    _render_conversation_not_found,
    _render_index,
)
from web.render.extension import _render_extension_page  # noqa: E402
from web.render.home import _render_homepage  # noqa: E402
from web.render.orchestrate import (  # noqa: E402
    _render_orchestrate,
    _render_orchestrate_readonly,
)
from web.render.personas import _render_personas_page  # noqa: E402
from web.render.setup import _render_setup, _render_setup_readonly  # noqa: E402

# Re-exported for tests (tests/test_web_readonly.py) and back-compat: these
# names historically lived in this module.
from web.db import (  # noqa: E402,F401
    db_init,
    get_conversation,
    list_conversations,
    list_stats,
    set_db_path,
)
from web.security import (  # noqa: E402,F401
    BasicAuthMiddleware,
    ExtensionCorsMiddleware,
    ReadOnlyMiddleware,
    _build_middleware,
    _env_truthy,
    _is_public_readonly,
)


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

async def homepage(request: Request) -> Response:
    """Public landing page. Shows the marketing/intro shell plus live
    counters and the 5 most recent conversations on this deploy.
    """
    convs = list_conversations()
    return HTMLResponse(_render_homepage(list_stats(), convs[:5]))


async def index(request: Request) -> Response:
    return HTMLResponse(_render_index(list_conversations()))


async def conversation_view(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return HTMLResponse(
            _render_conversation_not_found(cid, list_conversations()),
            status_code=404,
        )
    fullscreen = request.query_params.get("fullscreen", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return HTMLResponse(
        _render_conversation(data, list_conversations(), fullscreen=fullscreen)
    )


async def orchestrate(request: Request) -> Response:
    """GET /orchestrate — local: seed-conversation form with page-load preflight;
    hosted (read-only): a local-only explainer (the mirror can't spawn CLIs).

    ``?type=<conv_type>`` pre-selects a conversation format — that's how the
    homepage's separate "Launch a debate" / "Launch a podcast" buttons land on
    the right form. Unknown values fall back to the default type."""
    if _is_public_readonly():
        return HTMLResponse(_render_orchestrate_readonly())
    # Only seats on CLIs this operator actually has (see orchestrator/
    # availability.py) — offering all six to someone who owns one is how the
    # form used to greet a fresh clone. Extra seats created with
    # scripts/setup/add_agent_seat.py still show up on the next page load.
    seat_ids = orch_availability.available_seats()
    initial_preflight = orch_preflight.run_preflight(seat_ids)
    persona_roster = [
        {
            "group": g,
            "personas": [
                {"slug": p.slug, "name": p.name}
                for p in orch_personas.list_personas(g)
            ],
        }
        for g in orch_personas.discover_groups()
    ]
    return HTMLResponse(_render_orchestrate(
        initial_preflight,
        persona_roster,
        availability={
            "declared": orch_availability.is_declared(),
            "clis": orch_availability.available_clis(),
            "seats": seat_ids,
        },
        conv_type=request.query_params.get("type"),
    ))


async def personas_page(request: Request) -> Response:
    """GET /personas — the persona-management page."""
    return HTMLResponse(_render_personas_page())


async def setup_page(request: Request) -> Response:
    """GET /setup — declare which CLI tools this machine has.

    Local only in substance: the hosted mirror has no PATH worth probing and
    nothing to save, so it gets the explainer (its POSTs 403 regardless).
    """
    if _is_public_readonly():
        return HTMLResponse(_render_setup_readonly())
    return HTMLResponse(
        _render_setup(orch_availability.detect_all(), orch_availability.is_declared())
    )


async def extension_page(request: Request) -> Response:
    """GET /extension — what AgentBattleground is and how to install it.

    Renders on both deploys: it's an explainer, not a control surface. The only
    part that differs is the bridge-health block, which is a question only a
    local instance can answer about itself.
    """
    return HTMLResponse(_render_extension_page())


async def favicon(request: Request) -> Response:
    return Response(
        FAVICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def avatars(request: Request) -> Response:
    """GET /avatars/{slug} — persona avatar PNG, or a default silhouette when
    the persona has no image (AI-Models cards, personas without art)."""
    return avatar_response(request.path_params.get("slug", ""))


async def not_found(request: Request, exc: Exception) -> Response:
    """Branded 404 for unmatched routes (typos, ``/conversations/abc``, etc.).

    Handlers that return their own 404 Response (missing conversation/persona)
    bypass this — those aren't raised exceptions. Unknown ``/api/*`` paths get
    JSON; everything else gets the HTML page.
    """
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "not found"}, status_code=404)
    return HTMLResponse(_render_generic_404(request.url.path), status_code=404)


routes = [
    Route("/", homepage),
    Route("/conversations", index),
    Route("/conversations/{cid:int}", conversation_view),
    Route("/api/conversations", api_conversations),
    Route("/api/conversations/{cid:int}", api_conversation),
    Route("/api/conversations/{cid:int}/export.md", api_conversation_export),
    Route("/api/conversations/{cid:int}/export.zip", api_conversation_export_zip),
    Route("/api/conversations/{cid:int}/prompts/{kind}.md", api_conversation_prompt),
    Route("/api/conversations/{cid:int}/stop", api_stop, methods=["POST"]),
    Route("/api/conversations/{cid:int}/delete", api_delete, methods=["POST"]),
    Route("/api/conversations/{cid:int}/stream", api_stream),
    Route("/api/ingest", api_ingest, methods=["POST"]),
    Route("/api/since", api_since),
    Route("/orchestrate", orchestrate),
    Route("/api/orchestrate", api_orchestrate, methods=["POST"]),
    # Which CLI tools this machine has. GET re-probes (safe anywhere); the two
    # POSTs are per-machine setup and 403 on the hosted mirror by method.
    Route("/setup", setup_page),
    Route("/api/setup", api_setup, methods=["GET"]),
    Route("/api/setup", api_setup_save, methods=["POST"]),
    Route("/api/setup/seats", api_setup_seats, methods=["POST"]),
    Route("/extension", extension_page),
    Route("/personas", personas_page),
    # Same path, split by method: GET is the palette's persona index (read-only,
    # so ReadOnlyMiddleware lets it through on the hosted mirror); POST creates.
    Route("/api/personas", api_persona_list, methods=["GET"]),
    Route("/api/personas", api_persona_create, methods=["POST"]),
    Route("/api/personas/import", api_persona_import, methods=["POST"]),
    Route("/api/personas/bulk-delete", api_persona_bulk_delete, methods=["POST"]),
    Route("/api/personas/{slug}", api_persona_update, methods=["POST"]),
    Route("/api/personas/{slug}/delete", api_persona_delete, methods=["POST"]),
    # AgentBattleground — the browser extension's bridge. Local-only data;
    # the hosted mirror 403s these POSTs like any other mutation.
    Route("/api/battleground/healthz", api_bg_healthz),
    Route("/api/battleground/roster", api_bg_roster),
    Route("/api/battleground/arenas", api_bg_arenas, methods=["GET"]),
    Route("/api/battleground/arenas", api_bg_create_arena, methods=["POST"]),
    Route("/api/battleground/arenas/{aid:int}", api_bg_arena, methods=["GET"]),
    Route("/api/battleground/arenas/{aid:int}", api_bg_update_arena, methods=["POST"]),
    Route("/api/battleground/arenas/{aid:int}/capture", api_bg_capture, methods=["POST"]),
    Route("/api/battleground/arenas/{aid:int}/delete", api_bg_delete_arena, methods=["POST"]),
    Route("/api/battleground/drafts/{did:int}/verdict", api_bg_verdict, methods=["POST"]),
    Route("/favicon.svg", favicon),
    Route("/avatars/{slug}", avatars),
]

app = Starlette(
    routes=routes,
    middleware=_build_middleware(),
    exception_handlers={404: not_found},
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _default_db_path() -> str:
    """Resolve DB path with precedence: $AGENT_CHAT_DB > <repo>/db/chat.db.

    The computed default sits one level above this script (src/), so a fresh
    clone Just Works without any flag or env var: `<repo>/db/chat.db`.
    """
    env_db = os.environ.get("AGENT_CHAT_DB")
    if env_db:
        return env_db
    return str((Path(__file__).resolve().parent.parent / "db" / "chat.db"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Web UI for agent_chat conversations.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the shared SQLite database. Defaults to $AGENT_CHAT_DB, "
             "or <repo>/db/chat.db resolved relative to this script.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Bind address. Defaults to $HOST or 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PORT", "8765")),
        type=int,
        help="Port. Defaults to $PORT or 8765.",
    )
    args = parser.parse_args()

    db_path = args.db_path if args.db_path else _default_db_path()
    resolved = str(Path(db_path).resolve())
    set_db_path(resolved)
    db_init()
    # Built-in AI-Models cards back the Cast panel for conversations seeded
    # without personas. Create-if-missing, so operator edits survive a restart
    # and a fresh volume (Fly) or clone self-heals on boot.
    models = ensure_model_personas()
    ingest_on = bool(os.environ.get("AGENT_CHAT_INGEST_TOKEN"))
    print(f"agent_chat web UI — DB: {resolved}")
    print(f"  bind: http://{args.host}:{args.port}/")
    print(f"  basic auth: off (gate disabled)")
    print(f"  /api/ingest: {'on' if ingest_on else 'off'}")
    print(f"  AI-Models cards: {models['created']} created, {models['skipped']} present")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
