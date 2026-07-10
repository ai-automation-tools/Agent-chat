"""Conversation JSON/download/stream endpoints under /api/conversations/."""

from __future__ import annotations

import asyncio
import json

from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator.export import (
    export_filename as _export_filename,
    export_zip_filename as _export_zip_filename,
    render_export_markdown as _render_export_markdown,
    render_export_zip as _render_export_zip,
)

from web.db import (
    conversation_turn_state,
    delete_conversation,
    get_conversation,
    list_conversations,
    messages_since,
    stop_conversation,
)
from web.render.common import render_markdown

POLL_INTERVAL_SECONDS = 1.0


async def api_conversations(request: Request) -> Response:
    return JSONResponse(list_conversations())


async def api_conversation(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(data)


async def api_conversation_export(request: Request) -> Response:
    """Serve a conversation as a downloadable Markdown document.

    Content-Disposition forces a download in browsers; the URL ends in
    `.md` so command-line tools (curl, wget) save with the right
    extension by default.
    """
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return Response("Not found", status_code=404, media_type="text/plain")
    md = _render_export_markdown(data)
    topic = str(data["conversation"].get("topic") or "")
    filename = _export_filename(cid, topic)
    return Response(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


async def api_conversation_export_zip(request: Request) -> Response:
    """Serve a conversation as a downloadable .zip of Markdown documents.

    Bundle: ``topic.md`` (topic + overview), ``personas/<agent>.md`` (one per
    participant — CLI tool + personality card), and ``transcript.md`` (the full
    debate). See :func:`_render_export_zip`.
    """
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return Response("Not found", status_code=404, media_type="text/plain")
    blob = _render_export_zip(data)
    topic = str(data["conversation"].get("topic") or "")
    filename = _export_zip_filename(cid, topic)
    return Response(
        blob,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


async def api_stop(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    result = stop_conversation(cid)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)


async def api_delete(request: Request) -> Response:
    """Permanently delete a conversation. Hosted-UI affordance.

    Cascades messages. The local sidecar picks this up on the next pull
    tick (via ``GET /api/since``) and applies the deletion to the local
    DB so the two sides converge. Idempotent — second DELETE returns 404.
    """
    cid = int(request.path_params["cid"])
    result = delete_conversation(cid)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)

async def api_stream(request: Request) -> Response:
    """SSE stream for a conversation: ``message`` per new row, ``turn`` when
    ``current_turn`` changes (whose-turn indicator), ``complete`` on close."""
    cid = int(request.path_params["cid"])
    last_id = int(request.query_params.get("since", "0"))

    async def event_generator():
        nonlocal last_id
        last_turn: object = "\x00unset"  # sentinel — always emit the first turn
        while True:
            if await request.is_disconnected():
                break
            new = messages_since(cid, last_id)
            for m in new:
                payload = {**m, "content_html": render_markdown(m["content"])}
                yield {"event": "message", "data": json.dumps(payload)}
                last_id = max(last_id, m["id"])
            status, current_turn = conversation_turn_state(cid)
            if status == "complete":
                yield {"event": "complete", "data": ""}
                break
            if status is None:
                break
            if current_turn != last_turn:
                yield {"event": "turn", "data": json.dumps({"current_turn": current_turn})}
                last_turn = current_turn
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
