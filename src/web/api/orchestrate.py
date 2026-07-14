"""POST /api/orchestrate — validate, preflight, seed a conversation.

Also (Phase 2b) resolves an optional per-CLI persona cast and, on the local
machine, best-effort spawns one CLI window per participant in character via
``scripts/orchestrate-debate.ps1``. Seeding always succeeds independently of
whether the spawn is possible (hosted mirror, non-Windows, no ``pwsh``).
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import personas as orch_personas
from orchestrator import preflight as orch_preflight
from orchestrator import seeding as orch_seeding
from presets import PRESETS, PRESET_NAMES

from web import db
from web.security import _is_public_readonly

# Sentinel values a persona <select> can post per CLI. Anything else is treated
# as a slug / display name to resolve against the registry.
_PERSONA_RANDOM = "__random__"
_PERSONA_NONE = "__none__"


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

    # ---- persona cast (optional) --------------------------------------------
    # ``personas`` maps cli -> slug/name | "__random__" | "__none__"/"". Resolve
    # it into the participant_personas dict seed_conversation stores as JSON (so
    # the Cast panel + .zip export are self-describing) and the spawn wrapper
    # reads back. A bad slug is a validation error; seeding never runs on one.
    personas_pick = payload.get("personas") or {}
    if not isinstance(personas_pick, dict):
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": "personas must be an object mapping cli -> selection"},
                            status_code=400)
    try:
        participant_personas = _resolve_personas(participants, personas_pick)
    except _CastError as e:
        return JSONResponse({"ok": False, "kind": "validation",
                             "error": str(e)}, status_code=400)

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
            participant_personas=participant_personas or None,
        )
    except orch_seeding.SeedError as e:
        return JSONResponse({"ok": False, "kind": "seed_error",
                             "error": str(e)}, status_code=400)

    # ---- best-effort spawn ---------------------------------------------------
    if payload.get("spawn"):
        spawn = _maybe_spawn(
            conversation_id=seed.conversation_id,
            topic=topic,
            participants=participants,
            first=seed.first,
            participant_personas=participant_personas,
            skip_permissions=bool(payload.get("skip_permissions")),
        )
    else:
        spawn = {"status": "skipped", "detail": "auto-spawn not requested"}

    return JSONResponse({
        "ok": True,
        "conversation_id": seed.conversation_id,
        "spawn": spawn,
    })


class _CastError(ValueError):
    """Raised when a persona pick can't be resolved; caller renders .args[0]."""


def _persona_entry(p: orch_personas.Persona) -> dict[str, str]:
    return {"persona_slug": p.slug, "persona_name": p.name, "persona_body": p.body}


def _resolve_personas(
    participants: list[str],
    picks: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Turn a cli -> selection map into {cli: {persona_slug, persona_name,
    persona_body}} for the participants that got a persona.

    Explicit slugs/names resolve across every group; ``__random__`` draws from
    the debater roster (falling back to the whole registry if that group is
    empty), never repeating a persona already picked in the same cast. ``__none__``
    / blank leaves that CLI plain. Raises :class:`_CastError` on an unknown slug
    or when there aren't enough personas to satisfy the random picks.
    """
    result: dict[str, dict[str, str]] = {}
    used_slugs: set[str] = set()
    random_clis: list[str] = []

    for cli in participants:
        raw = picks.get(cli)
        val = (raw if isinstance(raw, str) else "").strip()
        if not val or val == _PERSONA_NONE:
            continue
        if val == _PERSONA_RANDOM:
            random_clis.append(cli)
            continue
        persona = orch_personas.get_persona(val)
        if persona is None:
            raise _CastError(f"persona not found for {cli!r}: {val!r}")
        result[cli] = _persona_entry(persona)
        used_slugs.add(persona.slug)

    if random_clis:
        pool = orch_personas.list_personas(orch_personas.DEFAULT_DEBATER_GROUP)
        if not pool:
            pool = orch_personas.list_personas(None)
        available = [p for p in pool if p.slug not in used_slugs]
        random.shuffle(available)
        if len(available) < len(random_clis):
            raise _CastError(
                f"not enough personas in the registry for {len(random_clis)} "
                f"random pick(s) (found {len(available)} unused)"
            )
        for cli in random_clis:
            persona = available.pop()
            used_slugs.add(persona.slug)
            result[cli] = _persona_entry(persona)

    return result


def _maybe_spawn(
    *,
    conversation_id: int,
    topic: str,
    participants: list[str],
    first: str,
    participant_personas: dict[str, dict[str, str]],
    skip_permissions: bool,
) -> dict[str, Any]:
    """Best-effort: launch one CLI window per participant via the PowerShell
    spawn wrapper. Returns a status dict; never raises (seeding already
    succeeded, so a spawn problem must not fail the request).

    Statuses: ``launched`` (wrapper started), ``unavailable`` (hosted / non-
    Windows / no pwsh — includes the manual command to run), ``error``.
    """
    manual = f".\\scripts\\orchestrate-debate.ps1  (conversation #{conversation_id})"
    if _is_public_readonly():
        return {"status": "unavailable",
                "detail": "the hosted mirror can't spawn local CLIs"}
    if sys.platform != "win32":
        return {"status": "unavailable",
                "detail": "agent spawn is Windows-only", "manual": manual}
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return {"status": "unavailable",
                "detail": "pwsh not found on PATH", "manual": manual}

    # <repo>/src/web/api/orchestrate.py → parents[3] is the repo root.
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "orchestrate-debate.ps1"
    if not script.exists():
        return {"status": "unavailable",
                "detail": f"spawn wrapper missing at {script}", "manual": manual}

    # Launch order: --first speaker first, then the rest in declared order.
    ordered = [first] + [c for c in participants if c != first]
    agents = [{
        "cli": c,
        "persona_name": participant_personas.get(c, {}).get("persona_name", ""),
        "persona_body": participant_personas.get(c, {}).get("persona_body", ""),
    } for c in ordered]

    launch_dir = repo_root / "db" / "launch"
    launch_dir.mkdir(parents=True, exist_ok=True)
    assign_file = launch_dir / f"orch-{conversation_id}-{uuid.uuid4().hex[:8]}.json"
    try:
        assign_file.write_text(json.dumps({
            "conversation_id": conversation_id,
            "topic": topic,
            "skip_permissions": skip_permissions,
            "agents": agents,
        }), encoding="utf-8")
    except OSError as e:
        return {"status": "error", "detail": f"could not write assignments file: {e}",
                "manual": manual}

    cmd = [pwsh, "-NoProfile", "-File", str(script),
           "-AssignmentsFile", str(assign_file)]
    try:
        # Detached + no console: the wrapper opens its own visible pwsh windows
        # (one per agent) and exits; we don't wait on it.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(cmd, creationflags=creationflags, cwd=str(repo_root))
    except OSError as e:
        return {"status": "error", "detail": f"failed to launch spawn wrapper: {e}",
                "manual": manual}

    return {"status": "launched", "detail": f"spawning {len(agents)} CLI window(s)",
            "agents": [a["cli"] for a in agents]}


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
