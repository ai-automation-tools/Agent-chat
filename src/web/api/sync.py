"""Sidecar sync realm: /api/ingest (push) and /api/since (pull).

Both authenticate with ``Authorization: Bearer $AGENT_CHAT_INGEST_TOKEN``
inside the handler (not middleware) so they keep working on the read-only
hosted mirror. Client: scripts/db_sync.py.
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from web.db import ingest_payload, since_payload


async def api_since(request: Request) -> Response:
    """Pull endpoint for the bidirectional-sync sidecar.

    Auth: ``Authorization: Bearer <token>`` matched against
    ``$AGENT_CHAT_INGEST_TOKEN`` (same token as ``/api/ingest`` — one
    less rotation surface for now; can split later if the threat model
    needs read/write separation).

    Query params:
      - ``conversations_updated_after`` (ISO timestamp; required)
      - ``known_ids`` (comma-separated int list of conversation ids the
        sidecar believes still exist; used to compute deletions via
        set-difference. Optional — empty means "no deletions to compute").

    Response::

        {
          "conversations": [<rows where updated_at > the watermark>],
          "deleted_conversation_ids": [<ids in known_ids no longer in DB>],
          "server_time": "<ISO timestamp>"   # sidecar uses this as next watermark
        }

    **Messages are intentionally not in this payload** — they flow
    local-only-origin (agents run locally; messages never originate on
    the hosted side). See ``scripts/db_sync.py`` for the architectural
    reasoning behind this asymmetry.

    When ``AGENT_CHAT_INGEST_TOKEN`` is unset the endpoint short-circuits
    to ``404 sync disabled`` — same opt-in posture as ``/api/ingest``.
    """
    expected = os.environ.get("AGENT_CHAT_INGEST_TOKEN")
    if not expected:
        return JSONResponse(
            {"error": "sync disabled (AGENT_CHAT_INGEST_TOKEN unset)"},
            status_code=404,
        )

    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse(
            {"error": "missing bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )
    presented = header[7:].encode("utf-8")
    if not secrets.compare_digest(presented, expected.encode("utf-8")):
        return JSONResponse(
            {"error": "invalid bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )

    updated_after = request.query_params.get(
        "conversations_updated_after", ""
    ).strip()
    if not updated_after:
        return JSONResponse(
            {"error": "conversations_updated_after query param is required"},
            status_code=400,
        )

    known_raw = request.query_params.get("known_ids", "").strip()
    try:
        known_ids = (
            [int(x) for x in known_raw.split(",") if x.strip()]
            if known_raw
            else []
        )
    except ValueError:
        return JSONResponse(
            {"error": "known_ids must be a comma-separated list of integers"},
            status_code=400,
        )

    # Persona params are optional: a sidecar that predates persona sync omits
    # `personas_updated_after`, and since_payload then skips persona work.
    personas_updated_after = request.query_params.get(
        "personas_updated_after", ""
    ).strip() or None
    pk_raw = request.query_params.get("known_persona_keys", "").strip()
    known_persona_keys = [k for k in pk_raw.split(",") if k] if pk_raw else []

    try:
        payload = since_payload(
            updated_after, known_ids,
            personas_updated_after, known_persona_keys,
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    return JSONResponse(payload)


async def api_ingest(request: Request) -> Response:
    """Apply a sync batch from the local writer (scripts/db_sync.py).

    Auth: ``Authorization: Bearer <token>`` where ``<token>`` matches
    ``$AGENT_CHAT_INGEST_TOKEN``. When the env var is unset the endpoint
    short-circuits to 404 — ingest is opt-in per deployment.

    Body shape::

        {
          "conversations": [<full conversation rows>],
          "messages": [<full message rows>],
          "deleted_conversation_ids": [<int>, ...]
        }

    Idempotent. See :func:`ingest_payload` for the SQL-level semantics.
    """
    expected = os.environ.get("AGENT_CHAT_INGEST_TOKEN")
    if not expected:
        return JSONResponse(
            {"error": "ingest disabled (AGENT_CHAT_INGEST_TOKEN unset)"},
            status_code=404,
        )

    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse(
            {"error": "missing bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )
    presented = header[7:].encode("utf-8")
    if not secrets.compare_digest(presented, expected.encode("utf-8")):
        return JSONResponse(
            {"error": "invalid bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "body must be a JSON object"}, status_code=400
        )

    conversations = body.get("conversations") or []
    messages = body.get("messages") or []
    deletions = body.get("deleted_conversation_ids") or []
    # Persona keys are new — an old sidecar omits both, which default to [].
    personas = body.get("personas") or []
    deleted_persona_keys = body.get("deleted_persona_keys") or []
    if not (
        isinstance(conversations, list)
        and isinstance(messages, list)
        and isinstance(deletions, list)
        and isinstance(personas, list)
        and isinstance(deleted_persona_keys, list)
    ):
        return JSONResponse(
            {
                "error": "conversations / messages / "
                "deleted_conversation_ids / personas / "
                "deleted_persona_keys must be arrays"
            },
            status_code=400,
        )
    # Coerce deletion ids to int up-front so a stray string can't sneak into
    # the parameterized DELETE.
    try:
        deletions = [int(x) for x in deletions]
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "deleted_conversation_ids must be integers"},
            status_code=400,
        )
    deleted_persona_keys = [str(k) for k in deleted_persona_keys]

    try:
        result = ingest_payload(
            conversations, messages, deletions,
            personas, deleted_persona_keys,
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)

    return JSONResponse(result)
