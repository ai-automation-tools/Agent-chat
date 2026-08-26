"""Watchdog — notice a conversation that has gone quiet, and say so once.

The ``quiet for N`` badge on the conversation page only helps while somebody is
looking at that page. Run **#51** stalled for **30 minutes** on an unanswered
Claude Code permission prompt while the operator was away from the machine:
the orchestrator returned "launched" and then nothing watched. That is the gap
this closes.

**It reuses the delivery fan-out rather than growing a second one.** A stall is
a third event alongside ``result`` and ``complete``, so an operator who has
already pointed a webhook at n8n gets stall notices through the same pipe, with
the same config file and the same never-raises guarantee. Nothing new to
configure beyond adding ``"stalled"`` to a sink's ``events``.

Three properties worth stating, because each is a decision:

- **It never touches an agent.** No restart, no stop, no message. A stalled run
  usually needs a human to click something in a CLI window, and a watchdog that
  "fixed" it by ending the conversation would destroy the run it was meant to
  rescue. Same rule the app scripts follow: spawned CLI windows are
  participants, not infrastructure.
- **It notifies once per stall, not once per check.** State is a message id, so
  the next message the conversation produces re-arms it — a run that stalls,
  recovers and stalls again notifies twice, and one that stays stuck notifies
  once. Anything else trains you to ignore it.
- **The bar is the conversation's own rhythm** (``quiet_threshold_seconds``),
  not a fixed number, because a debate turn is seconds and a facilitator
  writing a deliverable legitimately took 16.8 minutes in run #54.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import delivery, export

#: Never call a conversation stalled before this, whatever its own rhythm says.
#: A run whose turns are genuinely fast still deserves the benefit of one slow
#: turn before the operator's phone buzzes.
MIN_STALL_SECONDS = 600.0


def state_path() -> Path:
    """Beside the delivery config — same per-machine, gitignored home."""
    return delivery.config_path().parent / "delivery-stall-state.json"


def _load_state() -> dict[str, int]:
    try:
        raw = state_path().read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    notified = data.get("notified") if isinstance(data, dict) else None
    if not isinstance(notified, dict):
        return {}
    return {str(k): int(v) for k, v in notified.items() if str(v).lstrip("-").isdigit()}


def _save_state(notified: dict[str, int]) -> bool:
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"notified": notified}, indent=2) + "\n",
                        encoding="utf-8")
        return True
    except OSError as exc:
        delivery._log(f"watchdog state: ERROR {exc}")
        return False


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def stalled_conversations(db_path: str | None = None,
                          now: float | None = None) -> list[dict[str, Any]]:
    """Active conversations whose last message is older than their own bar.

    Read-only. Returns one dict per stalled run with everything a notification
    needs: ``conversation_id``, ``topic``, ``current_turn`` (who owes a turn —
    the agent whose window to go look at), ``quiet_seconds``, ``bar_seconds``,
    ``last_message_id`` and ``last_sender``.

    A conversation with **no messages at all** is deliberately excluded: it was
    seeded but never joined, which is a launch problem the orchestrator already
    reports, not a stall.
    """
    path = db_path or delivery.resolve_db_path()
    at = _now() if now is None else now
    try:
        conn = sqlite3.connect(path, isolation_level=None, timeout=10.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        delivery._log(f"watchdog: ERROR opening {path}: {exc}")
        return []

    out: list[dict[str, Any]] = []
    try:
        convs = conn.execute(
            "SELECT * FROM conversations WHERE status = 'active'").fetchall()
        for c in convs:
            msgs = [dict(m) for m in conn.execute(
                "SELECT id, sender, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC", (c["id"],))]
            if not msgs:
                continue
            try:
                last_at = datetime.fromisoformat(
                    str(msgs[-1]["created_at"])).timestamp()
            except (TypeError, ValueError):
                continue
            quiet = at - last_at
            bar = max(MIN_STALL_SECONDS, export.quiet_threshold_seconds(msgs))
            if quiet < bar:
                continue
            out.append({
                "conversation_id": int(c["id"]),
                "topic": c["topic"],
                "conv_type": dict(c).get("conv_type"),
                "current_turn": c["current_turn"],
                "quiet_seconds": int(quiet),
                "bar_seconds": int(bar),
                "last_message_id": int(msgs[-1]["id"]),
                "last_sender": msgs[-1]["sender"],
                "message_count": len(msgs),
            })
    except sqlite3.Error as exc:
        delivery._log(f"watchdog: ERROR reading {path}: {exc}")
    finally:
        conn.close()
    return out


def check(db_path: str | None = None, notify: bool = True,
          now: float | None = None) -> list[dict[str, Any]]:
    """Find stalls and fan out a ``stalled`` delivery event for the new ones.

    Returns every stalled conversation, each with a ``"notified"`` key saying
    whether this call announced it. ``notify=False`` reports without announcing
    or recording — the mode the health check runs in when asked not to repair.

    Never raises: this runs from a scheduled task, and a watchdog that can
    crash is worse than no watchdog.
    """
    try:
        stalls = stalled_conversations(db_path, now=now)
        if not stalls:
            return []

        state = _load_state()
        changed = False
        for s in stalls:
            key = str(s["conversation_id"])
            # Keyed on the LAST MESSAGE ID, not a timestamp: a new message
            # re-arms the alarm on its own, so a run that stalls, recovers and
            # stalls again notifies twice, while one that stays stuck notifies
            # once however long it sits there.
            already = state.get(key) == s["last_message_id"]
            s["notified"] = bool(notify and not already)
            if not s["notified"]:
                continue
            lines = delivery.deliver(s["conversation_id"], "stalled", db_path,
                                     extra=s)
            delivery._log(
                f"#{s['conversation_id']} stalled "
                f"{s['quiet_seconds']}s (bar {s['bar_seconds']}s), "
                f"turn={s['current_turn'] or '-'} -> "
                f"{'; '.join(lines) if lines else 'no sinks configured'}")
            state[key] = s["last_message_id"]
            changed = True

        if changed:
            # Prune rows for conversations that are no longer stalled, so the
            # file tracks live state rather than growing forever.
            live = {str(s["conversation_id"]) for s in stalls}
            _save_state({k: v for k, v in state.items() if k in live})
        return stalls
    except Exception as exc:  # noqa: BLE001 - a watchdog must not crash
        delivery._log(f"watchdog: ERROR {type(exc).__name__}: {exc}")
        return []


def describe(stall: dict[str, Any]) -> str:
    """One operator-readable line for a CLI or a log."""
    mins = stall["quiet_seconds"] / 60
    who = stall.get("current_turn") or stall.get("last_sender") or "?"
    return (f"#{stall['conversation_id']} quiet {mins:.0f} min "
            f"(bar {stall['bar_seconds'] / 60:.0f} min) — waiting on '{who}' — "
            f"{str(stall.get('topic') or '')[:60]}")
