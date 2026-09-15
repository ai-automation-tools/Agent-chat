"""/api/settings/delivery — the folder and command sinks, from a form.

The third `config/delivery.json` surface, after `/api/setup` (which CLIs) and
`/api/notifications` (the push sink). These two have always worked and have
never been reachable except by hand-editing the file.

**Ownership is by position, not by a tag.** The notification sink carries
`delivery.NOTIFY_SINK_ID` because the page that owns it created it. Folder and
command sinks predate any UI — the sinks already on this machine have no `id` —
so this module owns **the first sink of each type** and leaves any later one
alone, reporting it back so the page can say so. Tagging them on save would
have silently re-written configs written by hand, which is the one thing a
settings page for a gitignored, history-less file must not do.

Like the other two, this is local-only in substance: `config/` doesn't exist on
the hosted mirror, and `ReadOnlyMiddleware` 403s the POST there without needing
a path list.
"""

from __future__ import annotations

import json
import shlex
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import delivery

#: The two sink types this page manages. The webhook sink is deliberately
#: absent — it belongs to `/api/notifications`, and two pages writing one sink
#: is how a config file loses an operator's work.
MANAGED_TYPES = ("folder", "command")


def _first(cfg: dict[str, Any], kind: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    """Index and body of the first sink of ``kind`` that isn't the notify sink."""
    for i, sink in enumerate(cfg.get("sinks") or []):
        if not isinstance(sink, dict):
            continue
        if str(sink.get("id") or "") == delivery.NOTIFY_SINK_ID:
            continue
        if str(sink.get("type") or "") == kind:
            return i, sink
    return None, None


def _extras(cfg: dict[str, Any]) -> list[str]:
    """Sink types present more than once — the ones this page won't touch."""
    seen: dict[str, int] = {}
    for sink in cfg.get("sinks") or []:
        if not isinstance(sink, dict):
            continue
        if str(sink.get("id") or "") == delivery.NOTIFY_SINK_ID:
            continue
        kind = str(sink.get("type") or "")
        if kind in MANAGED_TYPES:
            seen[kind] = seen.get(kind, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


def _state(cfg: dict[str, Any]) -> dict[str, Any]:
    """Everything the Delivery tab needs to render itself."""
    _, folder = _first(cfg, "folder")
    _, command = _first(cfg, "command")
    default_events = list(cfg.get("events") or ["complete"])
    return {
        "delivery_enabled": bool(cfg.get("enabled")),
        "default_events": default_events,
        "folder": {
            "configured": folder is not None,
            "enabled": bool(folder and folder.get("enabled")),
            "path": str((folder or {}).get("path") or delivery.DEFAULT_FOLDER),
            "include_result": bool((folder or {}).get("include_result")),
            "scope": delivery.sink_scope(folder or {}),
            "events": list((folder or {}).get("events") or default_events),
        },
        "command": {
            "configured": command is not None,
            "enabled": bool(command and command.get("enabled")),
            # argv is a list in the file and a single line in the form. shlex
            # round-trips it, so a path with a space survives the trip rather
            # than splitting into two arguments the way a naive .split() would.
            "argv": shlex.join([str(a) for a in ((command or {}).get("argv") or [])]),
            "timeout": int((command or {}).get("timeout") or 120),
            "events": list((command or {}).get("events") or default_events),
        },
        "events": list(delivery.EVENTS),
        "config_path": str(delivery.config_path()),
        "log_path": str(delivery.log_path()),
        "extra_sinks": _extras(cfg),
    }


async def api_delivery_settings(request: Request) -> Response:
    """GET /api/settings/delivery — the two sinks as the form sees them."""
    return JSONResponse(_state(delivery.load_config()))


def _parse_events(raw: Any, field: str) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{field}: pick at least one event")
    events = [str(e) for e in raw]
    unknown = [e for e in events if e not in delivery.EVENTS]
    if unknown:
        raise ValueError(f"{field}: unknown event(s) {', '.join(unknown)}")
    return events


def _build(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate the form and return the (folder, command) sink bodies."""
    folder_in = payload.get("folder") or {}
    command_in = payload.get("command") or {}
    if not isinstance(folder_in, dict) or not isinstance(command_in, dict):
        raise ValueError("'folder' and 'command' must be objects")

    folder: dict[str, Any] | None = None
    if folder_in.get("present", True):
        path = str(folder_in.get("path") or "").strip()
        if not path:
            raise ValueError("the folder sink needs a path")
        scope = str(folder_in.get("scope") or "all")
        if scope not in ("all", "opt-in"):
            raise ValueError("scope must be 'all' or 'opt-in'")
        folder = {
            "type": "folder",
            "enabled": bool(folder_in.get("enabled")),
            "path": path,
            "include_result": bool(folder_in.get("include_result")),
            "scope": scope,
            "events": _parse_events(folder_in.get("events"), "folder"),
        }

    command: dict[str, Any] | None = None
    if command_in.get("present", True):
        line = str(command_in.get("argv") or "").strip()
        argv: list[str] = []
        if line:
            try:
                argv = shlex.split(line)
            except ValueError as e:
                raise ValueError(f"command: could not parse the command line ({e})") from e
        if command_in.get("enabled") and not argv:
            raise ValueError("the command sink is enabled but has no command")
        # `or 120` would be wrong here: 0 is falsy, so a timeout the operator
        # actually typed as 0 would silently become two minutes. Missing means
        # default; present-and-nonsense means say so.
        raw_timeout = command_in.get("timeout")
        try:
            timeout = 120 if raw_timeout in (None, "") else int(raw_timeout)
        except (TypeError, ValueError) as e:
            raise ValueError("command: timeout must be a whole number of seconds") from e
        if timeout < 1:
            raise ValueError("command: timeout must be at least 1 second")
        command = {
            "type": "command",
            "enabled": bool(command_in.get("enabled")),
            "argv": argv,
            "timeout": timeout,
            "events": _parse_events(command_in.get("events"), "command"),
        }
        # The command sink acts on files the folder sink wrote, so enabling it
        # without one is a config that can only ever log an error. Refuse it
        # here rather than at delivery time, where nobody is watching.
        if command["enabled"] and not (folder and folder["enabled"]):
            raise ValueError(
                "the command sink runs against the delivered folder, so it needs "
                "the folder sink switched on too")
    return folder, command


async def api_delivery_settings_save(request: Request) -> Response:
    """POST /api/settings/delivery — write the two sinks back.

    Replaces the first sink of each managed type **in place**, so its position
    in the file (and therefore its order relative to the notification sink) is
    preserved. Any sink this page doesn't manage is untouched.
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"},
                            status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "JSON body must be an object"},
                            status_code=400)
    try:
        folder, command = _build(payload)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    cfg = delivery.load_config()
    sinks = list(cfg.get("sinks") or [])
    for kind, built in (("folder", folder), ("command", command)):
        if built is None:
            continue
        idx, existing = _first(cfg, kind)
        if idx is None:
            sinks.append(built)
        else:
            # Keep any key the form doesn't know about — a config may carry
            # something a later version added, and a settings page should not
            # be a way to quietly delete it.
            merged = dict(existing or {})
            merged.update(built)
            sinks[idx] = merged
    cfg["sinks"] = sinks

    # Delivery's master switch. Turning a sink on while it stays false saves a
    # config that looks armed and does nothing; turning it off here would
    # silence the notification sink too, so this only ever goes on.
    if (folder and folder["enabled"]) or (command and command["enabled"]):
        cfg["enabled"] = True
    cfg.setdefault("events", ["complete"])

    path = delivery.config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return JSONResponse({"ok": False, "error": f"could not write {path}: {e}"},
                            status_code=500)
    return JSONResponse({"ok": True, **_state(delivery.load_config())})


__all__ = [
    "MANAGED_TYPES",
    "api_delivery_settings",
    "api_delivery_settings_save",
]
