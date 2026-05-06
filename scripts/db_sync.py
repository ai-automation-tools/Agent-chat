"""
db_sync.py — local → Fly mirror for agent_chat.

Polls the local SQLite database the MCP server writes to and POSTs deltas
(new messages, changed/created conversations, deleted conversations) to a
remote ``/api/ingest`` endpoint. Authenticates with a shared bearer token.

The remote endpoint is in src/web_ui.py and is opt-in via the
``AGENT_CHAT_INGEST_TOKEN`` env var on the server side. See docs/db-sync.md
for the end-to-end setup procedure.

Stdlib only — no extra deps. Designed to run as a long-lived daemon in a
PowerShell window or as a Windows Scheduled Task; ``--once`` makes it a
one-shot for cron-style use.

Usage::

    python scripts/db_sync.py \\
        --db-path db/chat.db \\
        --remote-url https://agent-chat.mikesailab.com \\
        --token "$env:AGENT_CHAT_INGEST_TOKEN"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Mirrors the column lists in src/web_ui.py:ingest_payload. If the schema
# grows a column, update both this file and web_ui.py in the same PR.
CONV_COLUMNS = (
    "id", "topic", "participants", "mode", "max_turns",
    "current_turn", "status", "end_reason", "created_at", "updated_at",
)
MSG_COLUMNS = (
    "id", "conversation_id", "sender", "content", "signal", "created_at",
)


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

@dataclass
class State:
    """Persisted sync watermarks. Lives next to the DB by default."""

    last_message_id: int = 0
    conversations_updated_after: str = "1970-01-01T00:00:00+00:00"
    known_conversation_ids: list[int] = field(default_factory=list)


def state_path_for(db_path: Path, override: Path | None) -> Path:
    if override:
        return override
    return db_path.parent / ".sync-state.json"


def load_state(path: Path) -> State:
    if not path.exists():
        return State()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(
            f"sync-state file at {path} is unreadable ({e}); "
            f"delete it to reset the watermarks and re-sync from scratch."
        )
    return State(
        last_message_id=int(raw.get("last_message_id", 0)),
        conversations_updated_after=str(
            raw.get("conversations_updated_after", "1970-01-01T00:00:00+00:00")
        ),
        known_conversation_ids=list(raw.get("known_conversation_ids", [])),
    )


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            {
                "last_message_id": state.last_message_id,
                "conversations_updated_after": state.conversations_updated_after,
                "known_conversation_ids": sorted(state.known_conversation_ids),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Local DB reads
# ---------------------------------------------------------------------------

def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Read-only enough for our purposes; WAL is set by the writer process.
    return conn


def read_changed_conversations(
    db_path: Path, updated_after: str
) -> list[dict[str, Any]]:
    cols = ",".join(CONV_COLUMNS)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM conversations "
            f"WHERE updated_at > ? ORDER BY updated_at ASC",
            (updated_after,),
        ).fetchall()
    return [dict(r) for r in rows]


def read_new_messages(db_path: Path, last_id: int) -> list[dict[str, Any]]:
    cols = ",".join(MSG_COLUMNS)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM messages "
            f"WHERE id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def read_all_conversation_ids(db_path: Path) -> list[int]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT id FROM conversations").fetchall()
    return sorted(int(r["id"]) for r in rows)


# ---------------------------------------------------------------------------
# Remote POST
# ---------------------------------------------------------------------------

class SyncError(Exception):
    """Anything that should make us pause and retry next tick."""


class FatalSyncError(Exception):
    """Configuration errors (bad token, ingest disabled). No retry."""


def post_batch(
    url: str, token: str, batch: dict[str, Any], timeout: float
) -> dict[str, Any]:
    body = json.dumps(batch).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "agent_chat-db-sync/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace") if e.fp else ""
        if e.code in (401, 403, 404):
            # 401/403 = bad token, 404 = ingest disabled on server. Either
            # way, retrying on the next tick will keep failing — bail.
            raise FatalSyncError(
                f"server rejected the request ({e.code}): {detail.strip()}"
            )
        raise SyncError(f"HTTP {e.code}: {detail.strip()}")
    except urllib.error.URLError as e:
        raise SyncError(f"network error: {e.reason}")
    except (TimeoutError, ConnectionError) as e:
        raise SyncError(f"transport error: {e}")


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def run_tick(
    db_path: Path,
    state: State,
    remote_url: str,
    token: str,
    timeout: float,
    log: logging.Logger,
) -> State:
    """One sync pass. Returns the updated state on success.

    On no-op (nothing to send), state is returned unchanged.
    """
    if not db_path.exists():
        log.debug("local DB not present yet (%s); skipping tick.", db_path)
        return state

    changed_convs = read_changed_conversations(db_path, state.conversations_updated_after)
    new_msgs = read_new_messages(db_path, state.last_message_id)
    current_ids = read_all_conversation_ids(db_path)
    known_ids = set(state.known_conversation_ids)
    deleted_ids = sorted(known_ids.difference(current_ids))

    if not changed_convs and not new_msgs and not deleted_ids:
        log.debug("no changes — nothing to ship.")
        return state

    batch = {
        "conversations": changed_convs,
        "messages": new_msgs,
        "deleted_conversation_ids": deleted_ids,
    }
    log.info(
        "shipping batch: convs=%d msgs=%d deletes=%d → %s",
        len(changed_convs), len(new_msgs), len(deleted_ids), remote_url,
    )

    result = post_batch(remote_url, token, batch, timeout)
    log.info("server reply: %s", json.dumps(result, sort_keys=True))

    new_state = State(
        last_message_id=max(
            state.last_message_id,
            max((m["id"] for m in new_msgs), default=state.last_message_id),
        ),
        conversations_updated_after=max(
            (c["updated_at"] for c in changed_convs),
            default=state.conversations_updated_after,
        ),
        known_conversation_ids=current_ids,
    )
    return new_state


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------

_should_stop = False


def _install_signal_handlers(log: logging.Logger) -> None:
    def handler(signum, _frame):
        global _should_stop
        log.info("received signal %s — stopping after current tick.", signum)
        _should_stop = True

    signal.signal(signal.SIGINT, handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mirror local agent_chat DB writes to a remote ingest endpoint.",
    )
    parser.add_argument(
        "--db-path",
        default=os.environ.get("AGENT_CHAT_DB", "db/chat.db"),
        help="Path to the shared SQLite DB. Defaults to $AGENT_CHAT_DB or db/chat.db.",
    )
    parser.add_argument(
        "--remote-url",
        default=os.environ.get("AGENT_CHAT_REMOTE_URL"),
        help="Base URL of the deployed Web UI (e.g. https://agent-chat.mikesailab.com). "
             "Defaults to $AGENT_CHAT_REMOTE_URL.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENT_CHAT_INGEST_TOKEN"),
        help="Bearer token for /api/ingest. Defaults to $AGENT_CHAT_INGEST_TOKEN.",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Where to persist sync watermarks. Defaults to <db dir>/.sync-state.json.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between ticks in daemon mode. Default 5.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout for each POST in seconds. Default 30.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single sync tick and exit. Useful for cron / Task Scheduler.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Log debug-level details (every tick, including no-ops).",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Append logs to this file instead of stderr. Useful when running "
             "the sidecar in a hidden background window where stderr would be "
             "discarded. Parent dir is created if it doesn't exist.",
    )
    args = parser.parse_args()

    if not args.remote_url:
        parser.error("--remote-url is required (or set AGENT_CHAT_REMOTE_URL).")
    if not args.token:
        parser.error("--token is required (or set AGENT_CHAT_INGEST_TOKEN).")

    log_kwargs: dict[str, Any] = {
        "level": logging.DEBUG if args.verbose else logging.INFO,
        "format": "%(asctime)s db_sync %(levelname)s %(message)s",
    }
    if args.log_file:
        log_path = Path(args.log_file).resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_kwargs["filename"] = str(log_path)
        log_kwargs["filemode"] = "a"
    else:
        log_kwargs["stream"] = sys.stderr
    logging.basicConfig(**log_kwargs)
    log = logging.getLogger("db_sync")

    db_path = Path(args.db_path).resolve()
    state_path = state_path_for(
        db_path, Path(args.state_file).resolve() if args.state_file else None
    )
    ingest_url = args.remote_url.rstrip("/") + "/api/ingest"

    log.info("local DB: %s", db_path)
    log.info("state file: %s", state_path)
    log.info("ingest URL: %s", ingest_url)
    log.info("mode: %s, interval: %ss", "once" if args.once else "daemon", args.interval)

    state = load_state(state_path)
    _install_signal_handlers(log)

    consecutive_failures = 0
    while True:
        try:
            new_state = run_tick(
                db_path, state, ingest_url, args.token, args.timeout, log
            )
            if new_state is not state:
                save_state(state_path, new_state)
                state = new_state
            consecutive_failures = 0
        except FatalSyncError as e:
            log.error("fatal: %s", e)
            sys.exit(2)
        except SyncError as e:
            consecutive_failures += 1
            log.warning("transient error (%d in a row): %s", consecutive_failures, e)
        except sqlite3.Error as e:
            log.error("local DB error: %s", e)
            sys.exit(3)

        if args.once or _should_stop:
            break
        time.sleep(args.interval)

    log.info("exit (clean).")


if __name__ == "__main__":
    main()
