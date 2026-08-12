"""/api/setup — read and record which CLI tools this machine has.

``GET`` re-probes and reports; ``POST`` records the operator's answer;
``POST /seats`` creates the extra seat config folders a small CLI set needs to
fill a multi-participant conversation.

All of this is per-machine setup, so all of it is local-only in practice: the
two POSTs are non-safe methods and ``ReadOnlyMiddleware`` 403s them on the
hosted mirror without needing a path list. The GET stays open — it answers
"nothing detected", which is the truth about a Fly machine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import availability as avail
from orchestrator import preflight as orch_preflight
from orchestrator import seats as orch_seats

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _add_seat_module():
    """Import ``scripts/setup/add_agent_seat.py`` on demand.

    It lives under ``scripts/``, not on the package path, and it is only needed
    when the operator actually asks for a seat — so the import is deferred
    rather than paid at web-app boot. Calling it **in process** is deliberate:
    a web request that shells out to a script is a different thing to reason
    about, and this one only writes inside ``agents/CLIs/``.
    """
    scripts_dir = _REPO_ROOT / "scripts" / "setup"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import add_agent_seat  # noqa: PLC0415 — deferred on purpose

    return add_agent_seat


async def api_setup(request: Request) -> Response:
    """GET /api/setup — a fresh probe of every supported CLI.

    ``{"declared": bool, "config_path": str, "available": [cli],
       "existing_seats": [seat], "missing_seats": [seat], "clis": [CliStatus]}``

    ``existing_seats`` is what could be offered right now; ``missing_seats`` is
    every seat folder that *could* be created for an available tool, which is
    what the setup page's "create the seats I need" button works from.
    """
    statuses = avail.detect_all()
    available = [s.cli for s in statuses if s.available]
    existing = avail.available_seats(available)
    missing = [
        orch_seats.seat_id(cli, n)
        for cli in available
        for n in range(2, orch_seats.MAX_SEATS_PER_CLI + 1)
        if orch_seats.seat_id(cli, n) not in existing
    ]
    return JSONResponse({
        "declared": avail.is_declared(),
        "config_path": str(avail.config_file()),
        "available": available,
        "existing_seats": existing,
        "missing_seats": missing,
        "max_seats_per_cli": orch_seats.MAX_SEATS_PER_CLI,
        "clis": [s.to_dict() for s in statuses],
    })


async def api_setup_save(request: Request) -> Response:
    """POST /api/setup — record the operator's CLI list.

    Body: ``{"available": ["claude-code", ...]}``. An empty list is a valid
    answer ("I have none wired up yet") and is stored as such — it is not the
    same as never having answered, which is the file being absent.
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"},
                            status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "JSON body must be an object"},
                            status_code=400)
    raw = payload.get("available")
    if not isinstance(raw, list) or not all(isinstance(c, str) for c in raw):
        return JSONResponse(
            {"ok": False, "error": "'available' must be a list of CLI id strings"},
            status_code=400,
        )
    try:
        path = avail.save_declared(raw)
    except avail.AvailabilityError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except OSError as e:
        return JSONResponse({"ok": False, "error": f"could not write {avail.config_file()}: {e}"},
                            status_code=500)
    saved = avail.load_declared() or []
    return JSONResponse({
        "ok": True,
        "config_path": str(path),
        "available": saved,
        "seats": avail.available_seats(saved),
    })


async def api_setup_seats(request: Request) -> Response:
    """POST /api/setup/seats — create extra seat config folders.

    Body: ``{"seats": ["claude-code-2", ...]}``. Each is a copy of that tool's
    seat-1 MCP config with the agent id rewritten (see
    ``scripts/setup/add_agent_seat.py``). Seats that already exist are reported
    as skipped rather than overwritten — nothing here passes ``force``, because
    an operator asking for a seat is not asking to lose the one they have.
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"},
                            status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "JSON body must be an object"},
                            status_code=400)
    wanted = payload.get("seats")
    if not isinstance(wanted, list) or not all(isinstance(s, str) for s in wanted):
        return JSONResponse({"ok": False, "error": "'seats' must be a list of seat ids"},
                            status_code=400)

    allowed = set(avail.available_clis())
    parsed: list[tuple[str, str, int]] = []
    for seat in wanted:
        cli = orch_seats.seat_cli(seat)
        index = orch_seats.seat_index(seat)
        if cli is None:
            return JSONResponse({"ok": False, "error": f"unrecognised seat id {seat!r}"},
                                status_code=400)
        if index < 2:
            return JSONResponse(
                {"ok": False,
                 "error": f"{seat!r} is seat 1 — that folder is part of registering "
                          f"the CLI itself, not something to clone"},
                status_code=400,
            )
        if cli not in allowed:
            return JSONResponse(
                {"ok": False,
                 "error": f"{cli!r} isn't one of your available CLIs — tick it above "
                          f"and save before adding seats for it"},
                status_code=400,
            )
        parsed.append((seat, cli, index))

    try:
        add_agent_seat = _add_seat_module()
    except ImportError as e:
        return JSONResponse({"ok": False, "error": f"seat helper unavailable: {e}"},
                            status_code=500)

    created: list[str] = []
    skipped: list[str] = []
    notes: list[str] = []
    for seat, cli, index in parsed:
        if avail.seat_folder_path(seat).is_dir():
            skipped.append(seat)
            continue
        try:
            add_agent_seat.add_seat(cli, index)
        except add_agent_seat.SeatSetupError as e:
            return JSONResponse(
                {"ok": False, "error": f"{seat}: {e}", "created": created},
                status_code=400,
            )
        except OSError as e:
            return JSONResponse(
                {"ok": False, "error": f"{seat}: {e}", "created": created},
                status_code=500,
            )
        created.append(seat)
        if cli == "codex":
            # Codex ignores per-folder config, so an extra seat relocates
            # CODEX_HOME — which moves credentials with it.
            notes.append(
                f"{seat} needs its own login: set CODEX_HOME to "
                f"{avail.seat_folder_path(seat) / '.codex'} and run 'codex login' once."
            )

    results = orch_preflight.run_preflight(created) if created else []
    return JSONResponse({
        "ok": True,
        "created": created,
        "skipped": skipped,
        "notes": notes,
        "preflight": [
            {"cli": r.cli, "ok": r.ok,
             "failures": [{"code": f.code, "detail": f.detail} for f in r.failures]}
            for r in results
        ],
    })


__all__: list[str] = ["api_setup", "api_setup_save", "api_setup_seats"]
