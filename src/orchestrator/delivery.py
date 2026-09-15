"""Delivery — write a finished conversation somewhere other than the web UI.

The web UI is a *viewer*: a conversation lives in ``db/chat.db`` and you go
look at it. Delivery is the push half — when a conversation finishes (or posts
its deliverable), fan the export bundle out to a folder on disk, an HTTP
endpoint, or a local command.

**Everything here is off unless ``config/delivery.json`` exists and says
otherwise.** ``config/`` is gitignored per-machine setup, the same place
``available-clis.json`` lives, so turning delivery on never touches the repo.

The bundle is NOT rendered here. ``export.bundle_files()`` is the single source
of truth for what one conversation looks like as Markdown — the folder sink
writes exactly the entries the ``.zip`` download contains, byte for byte, just
unpacked. A format change belongs in ``export.py`` (and its contract doc), not
in a sink.

Three sinks, and they are deliberately the only three:

``folder``   the bundle, unzipped, into ``deliveries/<slug>-<cid>/``.
``webhook``  a JSON POST — n8n, Home Assistant, Slack, Discord, anything.
``command``  run an argv against the written folder — git, gh gist, a copy
             into a notes vault, mail. The escape hatch that means a fourth
             sink never needs writing.

**A sink must never break a conversation.** ``deliver()`` swallows every
exception and reports through ``logs/delivery.log``; a webhook that 500s or a
disk that is full loses an artifact, not a turn. Callers ignore the return value.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import export

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Delivery triggers. ``started`` fires from ``seeding.seed_conversation()``
#: the moment a run is seeded — the only event where the bundle is empty (no
#: messages yet), which is why the default ``events`` list does not include it:
#: it is for notifying, not for writing an artifact nobody has produced.
#: ``result`` fires when a message lands with ``signal='result'`` (a
#: collaboration's deliverable — see conv_types); it can fire several times in
#: one conversation, because a lead that drafts-then-revises posts a result per
#: revision. ``complete`` fires once, when the conversation's status flips.
#: ``stalled`` fires from the watchdog when a run goes quiet for longer than its
#: own rhythm allows — the only event that is NOT triggered by something
#: happening, and the only one that can fire while a conversation is active.
EVENTS = ("started", "result", "complete", "stalled")

#: The ``id`` carried by the one sink the ``/notifications`` page owns. The page
#: replaces a sink with this id and leaves every other sink in the file alone,
#: so a hand-written folder or command sink survives a save from the browser.
NOTIFY_SINK_ID = "notifications"

#: The message signal that marks a deliverable. Duplicated from
#: ``agent_chat_mcp.SIGNAL_RESULT`` on purpose — the MCP server imports this
#: module, so importing it back would be a cycle.
SIGNAL_RESULT = "result"

DEFAULT_FOLDER = "deliveries"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def config_path() -> Path:
    """``$AGENT_CHAT_DELIVERY_CONFIG`` wins, else ``<repo>/config/delivery.json``."""
    override = os.environ.get("AGENT_CHAT_DELIVERY_CONFIG")
    if override:
        return Path(override).expanduser()
    return _REPO_ROOT / "config" / "delivery.json"


def log_path() -> Path:
    return _REPO_ROOT / "logs" / "delivery.log"


def _log(message: str) -> None:
    """Append one line to the delivery log. Never raises — this is the thing
    that reports failures, so it cannot itself become one."""
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {message}\n")
    except OSError:
        pass


def load_config() -> dict[str, Any]:
    """Read ``config/delivery.json``. Missing file → ``{}`` → delivery is off.

    A malformed file is logged and treated as absent rather than raised: a typo
    in an optional config must not take the MCP server down mid-conversation.
    """
    path = config_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log(f"config ERROR {path}: {exc}")
        return {}
    return cfg if isinstance(cfg, dict) else {}


def enabled_sinks(cfg: dict[str, Any], event: str,
                  cid: int | None = None) -> list[dict[str, Any]]:
    """The sinks that should fire for ``event``, in config order.

    A sink runs when the top-level ``enabled`` is true, its own ``enabled`` is
    true, ``event`` is in its ``events`` (falling back to the top-level
    ``events``, which defaults to ``complete`` only — a per-revision folder
    rewrite is opt-in), and its ``scope`` admits this conversation.

    ``scope`` is ``"all"`` unless stated (every conversation, the original
    behaviour) or ``"opt-in"`` (only conversations the operator ticked the box
    for — see ``is_opted_in``). Pass ``cid=None`` to ask what a config *can*
    do, ignoring scope; that is what the ``/orchestrate`` renderer wants.
    """
    if not cfg.get("enabled"):
        return []
    default_events = cfg.get("events") or ["complete"]
    out: list[dict[str, Any]] = []
    for sink in cfg.get("sinks") or []:
        if not isinstance(sink, dict) or not sink.get("enabled"):
            continue
        if event not in (sink.get("events") or default_events):
            continue
        if cid is not None and sink_scope(sink) == "opt-in" and not is_opted_in(cid):
            continue
        out.append(sink)
    return out


def sink_scope(sink: dict[str, Any]) -> str:
    """``"opt-in"`` or ``"all"`` (the default for a sink that doesn't say)."""
    return "opt-in" if str(sink.get("scope") or "all") == "opt-in" else "all"


# ---------------------------------------------------------------------------
# Per-conversation opt-in
# ---------------------------------------------------------------------------
#
# Which conversations to deliver is an operator preference about **this
# machine's filesystem**, not a property of the conversation — so it lives in a
# local JSON file next to the delivery config, not in a `conversations` column.
#
# That is a deliberate call, and the reasons are the same ones that keep the
# battleground tables out of the sync: a column would have to be mirrored
# across four SCHEMA copies, carried by `scripts/db_sync.py` and `/api/ingest`,
# and would then travel to the hosted mirror — where `deliveries/` does not
# exist and never will. Nothing about "save a copy on my D: drive" belongs in a
# row that syncs to Fly.

def optin_path() -> Path:
    return config_path().parent / "delivery-optin.json"


def _load_optin() -> list[int]:
    try:
        raw = optin_path().read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    ids = data.get("conversations") if isinstance(data, dict) else data
    if not isinstance(ids, list):
        return []
    return [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()]


def is_opted_in(cid: int) -> bool:
    """Did the operator ask for this conversation to be delivered?"""
    return int(cid) in _load_optin()


def mark_opt_in(cid: int) -> bool:
    """Record a conversation as opted in. Idempotent; never raises.

    Called by ``POST /api/orchestrate`` when the launch form's *save a copy*
    box is ticked. Returns False if the file could not be written — the
    conversation was still seeded, so this must not be able to fail a launch.
    """
    ids = _load_optin()
    if int(cid) in ids:
        return True
    ids.append(int(cid))
    try:
        path = optin_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"conversations": sorted(ids)}, indent=2) + "\n",
                        encoding="utf-8")
        return True
    except OSError as exc:
        _log(f"#{cid} opt-in: ERROR {exc}")
        return False


def clear_opt_in(cid: int) -> bool:
    """Remove a conversation from the opt-in list. Idempotent; never raises."""
    ids = [i for i in _load_optin() if i != int(cid)]
    try:
        path = optin_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"conversations": sorted(ids)}, indent=2) + "\n",
                        encoding="utf-8")
        return True
    except OSError as exc:
        _log(f"#{cid} opt-in clear: ERROR {exc}")
        return False


def optin_offered() -> dict[str, Any]:
    """What the ``/orchestrate`` launch form should render.

    Returns ``{"available": bool, "forced": bool, "label": str}``:

    - ``available`` False — delivery is off, or no sink is scoped ``opt-in``
      with nothing else running either. The form shows a muted hint.
    - ``forced`` True — a sink is scoped ``all``, so every conversation is
      delivered whatever the box says. The form shows it ticked and disabled
      rather than pretending the operator has a choice.
    """
    cfg = load_config()
    # The /orchestrate checkbox is about DELIVERING A COPY of the bundle. The
    # sink the /notifications page owns is scoped "all" by design (you want to
    # be told about every run), and counting it here would render that checkbox
    # as forced-and-ticked — telling the operator every conversation gets saved
    # to disk because they asked to be pinged. Different question, different
    # sink.
    sinks = [s for s in enabled_sinks(cfg, "complete", cid=None)
             if str(s.get("id") or "") != NOTIFY_SINK_ID]
    if not sinks:
        return {"available": False, "forced": False, "label": ""}
    scopes = {sink_scope(s) for s in sinks}
    kinds = sorted({str(s.get("type") or "?") for s in sinks})
    return {
        "available": True,
        "forced": "all" in scopes,
        "label": " + ".join(kinds),
    }


def _resolve(path_str: str) -> Path:
    """Config paths may be relative — resolve those against the repo root, so a
    config written by hand does not depend on which directory an agent's CLI
    happened to start in. (The same trap that once had spawned agents creating
    stray ``db/chat.db`` files in their seat folders.)"""
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else _REPO_ROOT / p


# ---------------------------------------------------------------------------
# Bundle helpers
# ---------------------------------------------------------------------------

def bundle_dir_name(cid: int, topic: str) -> str:
    """Folder name for one conversation's delivery.

    The ``.zip`` download is named for the topic slug alone, which is fine for a
    file landing in Downloads. A delivery folder accumulates, and two
    conversations on the same subject share a slug (it truncates at 25 chars),
    so the id is appended to keep them from overwriting each other.
    """
    slug = export.topic_slug(topic)
    return f"{slug}-{cid}" if slug else f"conversation-{cid}"


def latest_result(messages: list[dict[str, Any]]) -> str | None:
    """Body of the most recent ``signal='result'`` message, or None.

    A lead that revises posts one per draft; the last is the current artifact.
    """
    for m in reversed(messages):
        if m.get("signal") == SIGNAL_RESULT:
            return m.get("content")
    return None


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------

def _sink_folder(data: dict[str, Any], sink: dict[str, Any],
                 ctx: dict[str, Any]) -> str:
    r"""Write the export bundle, unzipped, into ``<path>/<slug>-<cid>/``.

    Contents are exactly ``export.bundle_files()`` — the same entries, with the
    same bytes, as the ``.zip`` download. Written via ``write_bytes`` rather
    than ``write_text`` on purpose: text mode on Windows would rewrite every
    ``\n`` to ``\r\n`` and the unpacked copy would no longer match the zip.

    Re-delivering overwrites in place, so a conversation that posts several
    results leaves the newest one on disk.
    """
    conv = data["conversation"]
    cid = conv["id"]
    root = _resolve(str(sink.get("path") or DEFAULT_FOLDER))
    target = root / bundle_dir_name(cid, conv.get("topic") or "")
    target.mkdir(parents=True, exist_ok=True)

    files = list(export.bundle_files(data))
    if sink.get("include_result"):
        # Not part of the zip bundle, so off by default: the deliverable on its
        # own, for a collaboration where digging it out of transcript.md is the
        # whole chore.
        body = latest_result(data["messages"])
        if body:
            files.append(("result.md", body.rstrip() + "\n"))

    for name, content in files:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode("utf-8"))

    ctx["dir"] = str(target)
    return f"{len(files)} files -> {target}"


class _SafeDict(dict):
    """``format_map`` helper: an unknown ``{placeholder}`` renders empty.

    A template is written by hand in a config file, against a payload whose
    keys vary by event (``quiet_seconds`` exists on ``stalled`` and nowhere
    else). Raising on the first typo would mean a notification config that
    works until the day it matters — the stall it was configured to catch.
    """

    def __missing__(self, key: str) -> str:  # noqa: D105
        return ""


def fill_template(template: str, fields: dict[str, Any]) -> str:
    """Substitute ``{placeholder}`` tokens from ``fields``; never raises.

    Unknown names render empty (see :class:`_SafeDict`); an unbalanced or
    malformed brace falls back to the literal string rather than losing the
    message entirely.
    """
    try:
        return str(template).format_map(_SafeDict(fields))
    except (IndexError, KeyError, ValueError):
        return str(template)


def summary_line(payload: dict[str, Any], event: str) -> str:
    """The one-line human summary — the default body of a text notification.

    Shared by the ``text_key`` JSON path and the plain-text body path so a
    Slack message and an ntfy push read the same.
    """
    quiet = payload.get("quiet_seconds")
    if quiet is not None:
        tail = (f"quiet {round(float(quiet) / 60)} min, waiting on "
                f"'{payload.get('current_turn') or '?'}'")
    else:
        tail = str(payload.get("status"))
    return (f"[{event}] Conversation #{payload.get('conversation_id')}: "
            f"{payload.get('topic') or '(no topic)'} — {tail}")


def webhook_payload(data: dict[str, Any], sink: dict[str, Any],
                    ctx: dict[str, Any]) -> dict[str, Any]:
    """The JSON facts one webhook carries. Also the template's field set."""
    conv = data["conversation"]
    payload: dict[str, Any] = {
        "event": ctx["event"],
        "conversation_id": conv["id"],
        "topic": conv.get("topic"),
        "status": conv.get("status"),
        "end_reason": conv.get("end_reason"),
        "conv_type": conv.get("conv_type"),
        "preset": conv.get("preset"),
        "participants": conv.get("participants") or [],
        "message_count": len(data["messages"]),
        "result": latest_result(data["messages"]),
        "current_turn": conv.get("current_turn"),
        "url": f"http://127.0.0.1:8765/conversations/{conv['id']}",
        "delivered_dir": ctx.get("dir"),
    }
    # Watchdog facts (quiet_seconds, bar_seconds, last_sender, ...) — present
    # only on a 'stalled' event, and never allowed to clobber the fields above.
    for k, v in (ctx.get("extra") or {}).items():
        payload.setdefault(str(k), v)
    if sink.get("include_transcript"):
        payload["transcript"] = export.render_export_markdown(data)
    return payload


def post_webhook(sink: dict[str, Any], payload: dict[str, Any],
                 event: str) -> str:
    """Send one webhook. The whole transport, and the only copy of it.

    Two body modes, because notification services split cleanly in half:

    ``json`` (default)
        The payload verbatim. ``text_key`` adds a human summary under a key
        the receiver reads — ``"text"`` for Slack, ``"content"`` for Discord,
        ``"message"`` for ntfy's and Gotify's JSON APIs.
    ``text``
        ``template`` rendered as a plain-text body, which is what ntfy's
        topic-URL mode and most "POST me a string" hooks want. Title,
        priority and tags ride in headers there, so header VALUES are
        templated too (``"X-Title": "Agent-Chat: {event}"``).

    Naming the key or the template in config is deliberately all there is: a
    per-service adapter for each of ntfy, Gotify, Slack and Discord would be
    four modules that differ by one string.
    """
    url = sink.get("url")
    if not url:
        raise ValueError("webhook sink has no 'url'")

    fields = dict(payload)
    fields.setdefault("summary", summary_line(payload, event))
    # A list renders as its Python repr inside a template, which is exactly
    # wrong on a lock screen. Offer the joined form under its own name rather
    # than reshaping `participants` — that key is the JSON payload's contract
    # with whatever automation is already parsing it.
    parts = payload.get("participants")
    fields.setdefault("participants_text",
                      ", ".join(str(x) for x in parts) if isinstance(parts, list)
                      else str(parts or ""))

    if str(sink.get("body") or "json").lower() == "text":
        template = sink.get("template") or "{summary}"
        body = fill_template(str(template), fields).encode("utf-8")
        content_type = str(sink.get("content_type") or "text/plain; charset=utf-8")
    else:
        text_key = sink.get("text_key")
        if text_key:
            template = sink.get("template")
            payload[str(text_key)] = (fill_template(str(template), fields)
                                      if template else fields["summary"])
        body = json.dumps(payload).encode("utf-8")
        content_type = "application/json"

    headers = {"Content-Type": content_type}
    for k, v in (sink.get("headers") or {}).items():
        headers[str(k)] = fill_template(str(v), fields)

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    timeout = float(sink.get("timeout") or 5)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return f"POST {url} -> {resp.status} ({len(body)} bytes)"


def _sink_webhook(data: dict[str, Any], sink: dict[str, Any],
                  ctx: dict[str, Any]) -> str:
    """POST a summary of the conversation. stdlib ``urllib`` — no new
    dependency for one call.

    The transcript is omitted by default: it runs to tens of thousands of
    characters and most endpoints (Slack among them) reject a payload that
    size. Set ``include_transcript`` when the receiver is your own automation.
    """
    return post_webhook(sink, webhook_payload(data, sink, ctx), ctx["event"])


def _sink_command(data: dict[str, Any], sink: dict[str, Any],
                  ctx: dict[str, Any]) -> str:
    """Run a local command against the delivered folder.

    ``{dir}``, ``{cid}``, ``{topic}`` and ``{event}`` are substituted into each
    argv token. Requires the folder sink to have run first — this sink acts on
    files, so with nothing on disk there is nothing to hand it.

    This runs whatever the config says, which is the point: the config file is
    per-machine, gitignored, and written by the operator, so it is exactly as
    trusted as a shell alias.
    """
    argv = sink.get("argv")
    if not isinstance(argv, list) or not argv:
        raise ValueError("command sink has no 'argv' list")
    if not ctx.get("dir"):
        raise ValueError("command sink needs the folder sink enabled for the same event")

    conv = data["conversation"]
    subs = {
        "dir": ctx["dir"],
        "cid": str(conv["id"]),
        "topic": conv.get("topic") or "",
        "event": ctx["event"],
    }
    resolved = [str(tok).format(**subs) for tok in argv]
    timeout = float(sink.get("timeout") or 120)
    proc = subprocess.run(resolved, capture_output=True, text=True,
                          timeout=timeout, cwd=str(_REPO_ROOT))
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(f"exit {proc.returncode}: {' / '.join(tail)}")
    return f"{resolved[0]} -> exit 0"


_SINKS = {
    "folder": _sink_folder,
    "webhook": _sink_webhook,
    "command": _sink_command,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def resolve_db_path(db_path: str | None = None) -> str:
    """``db_path`` > ``$AGENT_CHAT_DB`` > ``<repo>/db/chat.db`` — the same
    precedence the MCP server and publish_debate.py use."""
    if db_path:
        return db_path
    env = os.environ.get("AGENT_CHAT_DB")
    if env:
        return env
    return str(_REPO_ROOT / "db" / "chat.db")


def deliver(cid: int, event: str, db_path: str | None = None,
            ignore_scope: bool = False,
            extra: dict[str, Any] | None = None) -> list[str]:
    """Fan one conversation out to every sink configured for ``event``.

    Returns a human-readable line per sink attempt (``"folder: 3 files -> …"``,
    ``"webhook: ERROR …"``) — for the CLI and the tests. Callers in the message
    path ignore it.

    ``extra`` merges into the webhook payload — the watchdog uses it to say
    how long a run has been quiet and whose turn it is, facts that exist
    nowhere in the conversation row.

    ``ignore_scope`` delivers even to sinks scoped ``opt-in`` for a
    conversation that was never ticked. The automatic hooks leave it False —
    that is what the checkbox is for — but an operator typing
    ``inspect_conversations deliver 42`` **is** the opt-in, and refusing an
    explicit request because a box went unticked at launch would be absurd.

    Never raises. Every failure mode here — no config, unreadable DB, dead
    webhook, command that exits 1 — costs an artifact, and a conversation must
    not be worth less than the copy of it.
    """
    try:
        cfg = load_config()
        sinks = enabled_sinks(cfg, event, cid=None if ignore_scope else cid)
        if not sinks:
            return []

        data = export.load_conversation(resolve_db_path(db_path), cid)
        if data is None:
            _log(f"#{cid} {event}: no such conversation")
            return [f"ERROR: no conversation #{cid}"]

        ctx: dict[str, Any] = {"event": event, "extra": dict(extra or {})}
        results: list[str] = []
        for sink in sinks:
            kind = str(sink.get("type") or "")
            fn = _SINKS.get(kind)
            if fn is None:
                line = f"{kind or '?'}: ERROR unknown sink type"
            else:
                try:
                    line = f"{kind}: {fn(data, sink, ctx)}"
                except Exception as exc:  # noqa: BLE001 - see docstring
                    line = f"{kind}: ERROR {type(exc).__name__}: {exc}"
            _log(f"#{cid} {event} {line}")
            results.append(line)
        return results
    except Exception as exc:  # noqa: BLE001 - a sink must never break a turn
        _log(f"#{cid} {event}: ERROR {type(exc).__name__}: {exc}")
        return [f"ERROR: {exc}"]


def send_test(sink: dict[str, Any], event: str = "complete") -> str:
    """Fire one notification at ``sink`` with stand-in facts. Raises on failure.

    Used by ``POST /api/notifications/test`` so the page's *Send test* button
    proves the real thing: same :func:`post_webhook`, same body mode, same
    template, same headers. A "test" that posted through its own code path
    would confirm nothing about the config being saved.

    Unlike :func:`deliver` this **does** raise — the caller is a human waiting
    for an answer, and "it failed" is the useful one.
    """
    payload = {
        "event": event,
        "conversation_id": 0,
        "topic": "Test notification from Agent-Chat",
        "status": "complete",
        "end_reason": "test",
        "conv_type": "debate",
        "preset": None,
        "participants": ["claude-code", "codex"],
        "message_count": 0,
        "result": None,
        "current_turn": None,
        "url": "http://127.0.0.1:8765/conversations",
        "delivered_dir": None,
        "quiet_seconds": 900 if event == "stalled" else None,
    }
    if payload["quiet_seconds"] is None:
        payload.pop("quiet_seconds")
    return post_webhook(sink, payload, event)


#: Written by ``inspect_conversations deliver --init``. Disabled, with one
#: example of each sink to edit rather than a blank file to invent. The CLI
#: lives there and not here: this is a package member, so
#: ``python -m orchestrator.delivery`` cannot find itself from the repo root.
STARTER_CONFIG: dict[str, Any] = {
    "enabled": False,
    "events": ["complete"],
    "sinks": [
        {
            "type": "folder",
            "enabled": True,
            "path": "deliveries",
            "include_result": False,
            # "opt-in" = only conversations whose launch form had "save a copy"
            # ticked. Change to "all" to deliver every conversation.
            "scope": "opt-in",
        },
        {
            "type": "webhook",
            "enabled": False,
            "url": "http://127.0.0.1:5678/webhook/agent-chat",
            "headers": {},
            "timeout": 5,
            "include_transcript": False,
            # Add "stalled" here to be told when a run goes quiet — the one
            # event that fires while a conversation is still going, and the
            # only thing that watches a run you have walked away from.
            # "started" fires at seed time, when the bundle is still empty.
            "events": ["complete", "stalled"],
        },
        # A push notification to your phone. The /notifications page writes
        # exactly this sink (with "id": "notifications") and owns it from then
        # on, so edit it there rather than here unless you want a second one.
        {
            "type": "webhook",
            "enabled": False,
            "url": "https://ntfy.sh/CHANGE-ME-to-your-topic",
            # ntfy's topic-URL mode: the message is the body, the rest is
            # headers. `body: "text"` is what makes that possible, and header
            # values are templated from the same payload the JSON mode sends.
            "body": "text",
            "template": "{topic}\n{status} — {participants_text}\n{url}",
            "headers": {"X-Title": "Agent-Chat: {event}", "X-Tags": "robot"},
            "events": ["complete", "stalled"],
            "timeout": 8,
        },
        {
            "type": "command",
            "enabled": False,
            "argv": ["pwsh", "-NoProfile", "-Command", "Write-Host {dir}"],
            "timeout": 120,
        },
    ],
}
