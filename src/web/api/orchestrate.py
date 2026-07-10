"""POST /api/orchestrate — validate, preflight, seed a conversation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import preflight as orch_preflight
from orchestrator import seeding as orch_seeding
from presets import PRESETS, PRESET_NAMES

from web import db


async def api_orchestrate(request: Request) -> Response:
    """POST /api/orchestrate — validate body, run preflight on selected CLIs, seed conversation.

    Response shape:
      success → {"ok": true, "conversation_id": N}
      preflight failure → {"ok": false, "kind": "preflight_failed",
                           "preflight": [PreflightResult...], "log_path": "..."}
      validation/seed error → {"ok": false, "kind": "validation"|"seed_error", "error": "..."}

    A log file is written to ``<repo>/logs/orchestrator-<timestamp>.log`` on
    preflight failure so the operator can inspect the full report later.
    Successful runs do not write a log (the conversation row is the audit trail).
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "request body must be JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "JSON body must be an object"}, status_code=400)

    topic = (payload.get("topic") or "").strip()
    if not topic:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "topic is required"}, status_code=400)

    participants = payload.get("participants") or []
    if not isinstance(participants, list) or not all(isinstance(p, str) for p in participants):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "participants must be a list of strings"}, status_code=400)
    participants = [p.strip() for p in participants if p.strip()]
    if len(participants) < 2:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "select at least 2 CLIs"}, status_code=400)

    preset = payload.get("preset") or None
    if preset is not None and preset not in PRESET_NAMES:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": f"unknown preset {preset!r}; "
                                      f"choices: {', '.join(PRESET_NAMES)}"}, status_code=400)

    max_turns_raw = payload.get("max_turns")
    if max_turns_raw is None:
        max_turns = PRESETS[preset]["max_turns"] if preset else 10
    else:
        try:
            max_turns = int(max_turns_raw)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": "max_turns must be an integer"}, status_code=400)
        if max_turns < 1 or max_turns > 50:
            return JSONResponse({"ok": False, "kind": "validation",
                                 "error": "max_turns must be between 1 and 50"}, status_code=400)

    first = payload.get("first") or None
    if first and first not in participants:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": f"first speaker {first!r} is not in participants"}, status_code=400)

    mode = PRESETS[preset]["mode"] if preset else "turns"
    tone = PRESETS[preset]["tone"] if preset else None
    initial_msg = (payload.get("kickoff") or "").strip() or None

    # ---- preflight gate ------------------------------------------------------
    results = orch_preflight.run_preflight(participants)
    if not all(r.ok for r in results):
        log_path = _write_preflight_log(results, topic)
        return JSONResponse({
            "ok": False,
            "kind": "preflight_failed",
            "preflight": [_preflight_to_dict(r) for r in results],
            "log_path": str(log_path),
        }, status_code=409)

    # ---- seed ----------------------------------------------------------------
    try:
        seed = orch_seeding.seed_conversation(
            db_path=db.DB_PATH,
            topic=topic,
            participants=participants,
            mode=mode,
            max_turns=max_turns,
            first=first,
            preset=preset,
            tone=tone,
            initial_system_message=initial_msg,
        )
    except orch_seeding.SeedError as e:
        return JSONResponse({"ok": False, "kind": "seed_error",
                             "error": str(e)}, status_code=400)

    return JSONResponse({"ok": True, "conversation_id": seed.conversation_id})


def _preflight_to_dict(r: orch_preflight.PreflightResult) -> dict[str, Any]:
    """Serialize a PreflightResult for the JSON response."""
    return {
        "cli": r.cli,
        "ok": r.ok,
        "config_path": r.config_path,
        "command": r.command,
        "launcher_path": r.launcher_path,
        "failures": [{"code": f.code, "detail": f.detail} for f in r.failures],
    }


def _write_preflight_log(
    results: list[orch_preflight.PreflightResult],
    topic: str,
) -> Path:
    """Write a preflight-failure audit log under ``<repo>/logs/``.

    Filename uses an ISO-ish timestamp (no colons, safe on Windows):
    ``orchestrator-2026-05-15T14-32-09.log``. Best-effort: on filesystem
    failure (read-only, disk full, etc.), returns the intended path
    anyway so the caller's response message stays consistent.
    """
    # This file lives at <repo>/src/web/api/orchestrate.py — parents[3] is the
    # repo root (parents[2] would be src/).
    repo_root = Path(__file__).resolve().parents[3]
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    log_path = log_dir / f"orchestrator-{stamp}.log"
    try:
        with log_path.open("w", encoding="utf-8") as f:
            f.write(f"# Orchestrator preflight failure — {stamp}\n")
            f.write(f"# Topic: {topic}\n")
            f.write(f"# Requested CLIs: {', '.join(r.cli for r in results)}\n\n")
            f.write(orch_preflight.format_preflight_log(results))
    except OSError:
        pass
    return log_path
