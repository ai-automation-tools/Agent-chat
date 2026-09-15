"""/api/notifications — enable push notifications without hand-editing JSON.

Notifications are not a new subsystem. They are **one delivery sink** —
``orchestrator.delivery`` already fans a finished conversation out to a webhook,
already carries the ``started`` / ``result`` / ``complete`` / ``stalled``
events, and already guarantees that a dead endpoint costs an artifact rather
than a turn. What was missing was a way to turn it on that did not involve
knowing the shape of ``config/delivery.json``.

So this module owns exactly one sink in that file, tagged with
``delivery.NOTIFY_SINK_ID``, and **merges** rather than overwrites: a folder or
command sink somebody wrote by hand survives a save from the browser. That
matters more than it looks — the config is gitignored per-machine state with no
history, so clobbering it loses work with no way back.

Services are a *rendering* of the sink, not a type of it. Each entry in
:data:`SERVICES` is the handful of fields that differ — body mode, one key
name, a header or two — which is why adding Gotify cost a dict entry and no
code. See ``delivery.post_webhook`` for why there are no per-service adapters.

All three routes are local-only in substance: ``config/`` does not exist on the
hosted mirror, and the two POSTs are non-safe methods that ``ReadOnlyMiddleware``
403s there without needing a path list.
"""

from __future__ import annotations

import json
import re
import urllib.error
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from orchestrator import delivery

#: Per-service shape. ``build`` turns the operator's one input (a topic, a
#: webhook URL) into the sink fields ``delivery.post_webhook`` reads.
#:
#: ``target_label`` / ``target_hint`` are what the form asks for. ``server``
#: is only offered by services that can be self-hosted.
SERVICES: dict[str, dict[str, Any]] = {
    "ntfy": {
        "label": "ntfy",
        "target_label": "Topic",
        "target_hint": "Anything you like — it's the channel name you subscribe to "
                       "in the ntfy app. Treat it as a secret: whoever knows it can "
                       "read your notifications.",
        "placeholder": "my-agent-chat",
        "server": "https://ntfy.sh",
        "docs": "https://docs.ntfy.sh/",
    },
    "gotify": {
        "label": "Gotify",
        "target_label": "App token",
        "target_hint": "From your Gotify server: Apps → your app → token.",
        "placeholder": "AbCdEf123456",
        "server": "http://localhost:8080",
        "docs": "https://gotify.net/docs/",
    },
    "discord": {
        "label": "Discord",
        "target_label": "Webhook URL",
        "target_hint": "Channel → Edit Channel → Integrations → Webhooks → New Webhook.",
        "placeholder": "https://discord.com/api/webhooks/...",
        "docs": "https://support.discord.com/hc/en-us/articles/228383668",
    },
    "slack": {
        "label": "Slack",
        "target_label": "Incoming webhook URL",
        "target_hint": "From a Slack app with Incoming Webhooks enabled.",
        "placeholder": "https://hooks.slack.com/services/...",
        "docs": "https://api.slack.com/messaging/webhooks",
    },
    "webhook": {
        "label": "Raw webhook",
        "target_label": "URL",
        "target_hint": "Gets the full JSON payload — conversation id, topic, status, "
                       "participants, the deliverable. For n8n, Home Assistant, or "
                       "your own script.",
        "placeholder": "http://127.0.0.1:5678/webhook/agent-chat",
        "docs": "",
    },
}

DEFAULT_SERVICE = "ntfy"

#: ntfy topics and Gotify tokens end up in a URL path, so they are constrained
#: rather than escaped — a topic with a slash in it would silently post to a
#: different topic, which is the failure mode where you think you are covered
#: and are not.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


def _build_sink(service: str, target: str, server: str, events: list[str],
                enabled: bool) -> dict[str, Any]:
    """The sink JSON for one service. Raises ValueError on bad input."""
    sink: dict[str, Any] = {
        "type": "webhook",
        "id": delivery.NOTIFY_SINK_ID,
        "enabled": bool(enabled),
        "service": service,          # rendering hint; delivery ignores it
        "events": list(events),
        # Notifications are about every run, not the ones ticked for a filesystem
        # copy — so never "opt-in". optin_offered() excludes this sink by id so
        # the /orchestrate checkbox doesn't read as forced because of it.
        "scope": "all",
        "timeout": 8,
    }

    if service == "ntfy":
        if not _TOKEN_RE.match(target):
            raise ValueError("an ntfy topic can use letters, numbers, dash, dot "
                             "and underscore only")
        base = (server or SERVICES["ntfy"]["server"]).rstrip("/")
        sink["url"] = f"{base}/{target}"
        # Topic-URL mode: the message is the raw body, everything else is a
        # header. Title carries the event so a glance at the lock screen says
        # which of the four fired.
        sink["body"] = "text"
        sink["template"] = "{topic}\n{status} — {participants_text}\n{url}"
        sink["headers"] = {
            "X-Title": "Agent-Chat: {event}",
            "X-Tags": "robot",
        }
    elif service == "gotify":
        if not _TOKEN_RE.match(target):
            raise ValueError("a Gotify app token can use letters, numbers, dash, "
                             "dot and underscore only")
        base = (server or SERVICES["gotify"]["server"]).rstrip("/")
        sink["url"] = f"{base}/message?token={target}"
        sink["text_key"] = "message"   # Gotify reads {"title", "message"}
        sink["template"] = "{summary}\n{url}"
    elif service in ("discord", "slack"):
        if not target.lower().startswith("https://"):
            raise ValueError(f"a {SERVICES[service]['label']} webhook URL must "
                             "start with https://")
        sink["url"] = target
        # One key name is the entire difference between the two.
        sink["text_key"] = "content" if service == "discord" else "text"
        sink["template"] = "**{summary}**\n{url}"
    elif service == "webhook":
        if not re.match(r"^https?://", target, re.IGNORECASE):
            raise ValueError("a webhook URL must start with http:// or https://")
        sink["url"] = target
    else:
        raise ValueError(f"unknown service {service!r}")
    return sink


def _read_config() -> dict[str, Any]:
    return delivery.load_config()


def _find_sink(cfg: dict[str, Any]) -> dict[str, Any] | None:
    for sink in cfg.get("sinks") or []:
        if isinstance(sink, dict) and str(sink.get("id") or "") == delivery.NOTIFY_SINK_ID:
            return sink
    return None


def _service_of(sink: dict[str, Any] | None) -> str:
    """Which service a stored sink represents.

    ``service`` is written by this module, but a sink hand-edited into the file
    (or written by an older build) won't have it — so fall back to reading the
    URL, and land on the honest generic answer rather than guessing wrong.
    """
    if not sink:
        return DEFAULT_SERVICE
    named = str(sink.get("service") or "")
    if named in SERVICES:
        return named
    url = str(sink.get("url") or "")
    if "ntfy" in url:
        return "ntfy"
    if "discord.com" in url:
        return "discord"
    if "hooks.slack.com" in url:
        return "slack"
    if "/message?token=" in url:
        return "gotify"
    return "webhook"


def _target_of(sink: dict[str, Any] | None, service: str) -> tuple[str, str]:
    """Split a stored URL back into (target, server) for the form."""
    if not sink:
        return "", str(SERVICES.get(service, {}).get("server") or "")
    url = str(sink.get("url") or "")
    if service == "ntfy":
        base, _, topic = url.rpartition("/")
        return topic, base
    if service == "gotify":
        base, _, query = url.partition("/message?token=")
        return query, base
    return url, ""


def _state(cfg: dict[str, Any]) -> dict[str, Any]:
    """Everything the page needs to render itself."""
    sink = _find_sink(cfg)
    service = _service_of(sink)
    target, server = _target_of(sink, service)
    others = [
        str(s.get("type") or "?")
        for s in (cfg.get("sinks") or [])
        if isinstance(s, dict) and str(s.get("id") or "") != delivery.NOTIFY_SINK_ID
    ]
    return {
        "configured": sink is not None,
        # Both flags must be on for anything to fire: delivery has a master
        # switch, and the page's own toggle is the per-sink one. Reporting them
        # separately is what lets the form say WHICH is off.
        "enabled": bool(sink and sink.get("enabled")),
        "delivery_enabled": bool(cfg.get("enabled")),
        "service": service,
        "target": target,
        "server": server,
        "events": list(sink.get("events") or ["complete", "stalled"]) if sink
                  else ["complete", "stalled"],
        "config_path": str(delivery.config_path()),
        "log_path": str(delivery.log_path()),
        "other_sinks": others,
    }


async def api_notifications(request: Request) -> Response:
    """GET /api/notifications — the current notification sink, if any."""
    return JSONResponse(_state(_read_config()))


def _parse(payload: Any) -> tuple[str, str, str, list[str], bool]:
    """Validate a save/test body. Raises ValueError with an operator-facing
    message — the same validation for both routes, so *Send test* cannot pass
    against something *Save* would reject."""
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    service = str(payload.get("service") or "").strip()
    if service not in SERVICES:
        raise ValueError(f"'service' must be one of: {', '.join(sorted(SERVICES))}")
    target = str(payload.get("target") or "").strip()
    if not target:
        raise ValueError(f"{SERVICES[service]['target_label']} is required")
    server = str(payload.get("server") or "").strip()
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("pick at least one thing to be notified about")
    events = [str(e) for e in raw_events]
    unknown = [e for e in events if e not in delivery.EVENTS]
    if unknown:
        raise ValueError(f"unknown event(s): {', '.join(unknown)}")
    return service, target, server, events, bool(payload.get("enabled", True))


async def api_notifications_save(request: Request) -> Response:
    """POST /api/notifications — write the notification sink into the config.

    Merges: the sink carrying ``NOTIFY_SINK_ID`` is replaced, everything else
    in the file is preserved byte-for-byte in meaning. Turning notifications on
    also flips delivery's master ``enabled`` — leaving it false would save a
    config that looks armed and fires nothing, which is the worst of the three
    possible outcomes.
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"},
                            status_code=400)
    try:
        service, target, server, events, enabled = _parse(payload)
        sink = _build_sink(service, target, server, events, enabled)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    cfg = _read_config()
    sinks = [s for s in (cfg.get("sinks") or [])
             if isinstance(s, dict) and str(s.get("id") or "") != delivery.NOTIFY_SINK_ID]
    sinks.append(sink)
    cfg["sinks"] = sinks
    if enabled:
        cfg["enabled"] = True
    cfg.setdefault("events", ["complete"])

    path = delivery.config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return JSONResponse({"ok": False, "error": f"could not write {path}: {e}"},
                            status_code=500)
    return JSONResponse({"ok": True, **_state(_read_config())})


async def api_notifications_test(request: Request) -> Response:
    """POST /api/notifications/test — send one notification with stand-in facts.

    Tests what is in the **form**, not what is on disk, so the button answers
    "will this work" before a save rather than after. It goes through
    ``delivery.send_test`` → ``delivery.post_webhook``, the same transport a
    real event uses; a test with its own code path would prove nothing.
    """
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"},
                            status_code=400)
    try:
        service, target, server, events, _enabled = _parse(payload)
        sink = _build_sink(service, target, server, events, True)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    event = events[0] if events else "complete"
    try:
        detail = delivery.send_test(sink, event)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200].strip()
        except Exception:  # noqa: BLE001 — the status is the useful part
            pass
        return JSONResponse(
            {"ok": False,
             "error": f"{SERVICES[service]['label']} answered HTTP {e.code}"
                      + (f": {body}" if body else "")},
            status_code=400)
    except urllib.error.URLError as e:
        return JSONResponse(
            {"ok": False, "error": f"could not reach it: {e.reason}"},
            status_code=400)
    except Exception as e:  # noqa: BLE001 — surface anything else as text
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"},
                            status_code=400)
    return JSONResponse({"ok": True, "detail": detail, "event": event})


__all__ = [
    "SERVICES",
    "DEFAULT_SERVICE",
    "api_notifications",
    "api_notifications_save",
    "api_notifications_test",
]
