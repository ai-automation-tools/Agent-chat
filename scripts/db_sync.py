"""
db_sync.py — bidirectional mirror between the local DB and Fly.

Each tick:
  1. **Pull** conversation deltas from the remote ``GET /api/since`` —
     status flips, topic edits, force-stops, deletions originated on the
     hosted UI flow back to the local DB.
  2. **Push** local deltas (new messages, changed/created conversations,
     deleted conversations) to the remote ``POST /api/ingest``.

Authenticates with a shared bearer token (``AGENT_CHAT_INGEST_TOKEN``;
same token for both pull and push — opt-in via env var on the server).

**Asymmetry**: messages flow local-only-origin (agents only run locally).
The pull payload covers conversation rows and deletions only; messages
never come back from the mirror. See the module docstring below for the why.

Conflict resolution is last-write-wins by ``updated_at``. Hosted-side
deletes are authoritative — applied locally on the next pull.

Stdlib only — no extra deps. Designed to run as a long-lived daemon in a
PowerShell window or as a Windows Scheduled Task; ``--once`` makes it a
one-shot for cron-style use.

Usage::

    python scripts/db_sync.py \\
        --db-path db/chat.db \\
        --remote-url https://agent-chat.ai-automation-tools.dev \\
        --token "$env:AGENT_CHAT_INGEST_TOKEN"

``--force-push`` rewinds the push watermarks for one run and re-ships
every local conversation, message and persona. ``/api/ingest`` is
idempotent, so it is a safe way to repair a mirror that has drifted
without hand-editing ``db/.sync-state.json``.
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
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Mirrors the column lists in src/web_ui.py:ingest_payload. If the schema
# grows a column, update both this file and web_ui.py in the same PR.
CONV_COLUMNS = (
    "id", "topic", "participants", "mode", "max_turns",
    "current_turn", "status", "end_reason", "created_at", "updated_at",
    "preset", "kickoff_template", "participant_personas",
    "conv_type", "participant_roles",
)
MSG_COLUMNS = (
    "id", "conversation_id", "sender", "content", "signal", "created_at",
)
# Personas key on a composite (group, slug). "group" is a SQL reserved word, so
# generated SQL double-quotes every identifier via PERSONA_COLS_SQL. Mirrors
# _PERSONA_COLUMNS in src/web_ui.py; keep both in lockstep.
PERSONA_COLUMNS = (
    "group", "slug", "name", "tags", "category", "subcategory",
    "body", "avatar_mime", "avatar_data", "created_at", "updated_at",
)
PERSONA_COLS_SQL = ",".join(f'"{c}"' for c in PERSONA_COLUMNS)

# Composite-key wire format: group + Unit-Separator (0x1F) + slug. 0x1F is absent
# from group names and [a-z0-9-] slugs, and urlencodes cleanly. Same format the
# server uses (src/web_ui.py:_persona_key) for deletes-by-set-difference.
PERSONA_KEY_SEP = "\x1f"


def _persona_key(row: dict[str, Any]) -> str:
    return f'{row["group"]}{PERSONA_KEY_SEP}{row["slug"]}'


# ---------------------------------------------------------------------------
# State file
# ---------------------------------------------------------------------------

EPOCH = "1970-01-01T00:00:00+00:00"


@dataclass
class State:
    """Persisted sync watermarks. Lives next to the DB by default.

    Two independent watermarks track the two directions, and **each is
    measured on exactly one clock** — mixing them is what let a local
    edit fall behind the cursor and never sync (see ``run_tick``):

    - ``conversations_updated_after`` (push side, **local clock**): rows
      with ``updated_at`` > this get pushed. Advanced only to the highest
      ``updated_at`` actually pushed. Never touched by the pull.
    - ``pulled_updated_at`` (pull side, **server clock**): rows on the
      server with ``updated_at`` > this get pulled. Advanced to the
      server's ``server_time`` after each successful pull (avoids
      local-vs-Fly clock-skew bugs).
    """

    last_message_id: int = 0
    conversations_updated_after: str = EPOCH
    pulled_updated_at: str = EPOCH
    known_conversation_ids: list[int] = field(default_factory=list)
    # Persona watermarks mirror the conversation ones: a push watermark
    # (rows with updated_at > this get pushed) and a pull watermark
    # (advanced to server_time each pull). known_persona_keys drives
    # delete-by-set-difference. All default to EPOCH/[] so the first tick
    # after upgrade does one full persona sync.
    personas_updated_after: str = EPOCH
    pulled_personas_updated_at: str = EPOCH
    known_persona_keys: list[str] = field(default_factory=list)


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
    # `pulled_updated_at` is new in the bidirectional version. State files
    # written by the push-only version don't have it — default to EPOCH so
    # the first tick after upgrade does one big pull. Legitimate cost is
    # paid once.
    return State(
        last_message_id=int(raw.get("last_message_id", 0)),
        conversations_updated_after=str(
            raw.get("conversations_updated_after", EPOCH)
        ),
        pulled_updated_at=str(raw.get("pulled_updated_at", EPOCH)),
        known_conversation_ids=list(raw.get("known_conversation_ids", [])),
        # Persona keys are new — state files from before persona sync lack
        # them and default to EPOCH/[], triggering one full persona sync.
        personas_updated_after=str(raw.get("personas_updated_after", EPOCH)),
        pulled_personas_updated_at=str(
            raw.get("pulled_personas_updated_at", EPOCH)
        ),
        known_persona_keys=list(raw.get("known_persona_keys", [])),
    )


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            {
                "last_message_id": state.last_message_id,
                "conversations_updated_after": state.conversations_updated_after,
                "pulled_updated_at": state.pulled_updated_at,
                "known_conversation_ids": sorted(state.known_conversation_ids),
                "personas_updated_after": state.personas_updated_after,
                "pulled_personas_updated_at": state.pulled_personas_updated_at,
                "known_persona_keys": sorted(state.known_persona_keys),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def rewind_push_watermarks(state: State) -> State:
    """Return ``state`` with the three push cursors rewound to the start.

    Recovery path for a mirror that has drifted — the next tick re-reads
    every conversation, message and persona and ships the lot.
    ``/api/ingest`` upserts by id and composite key, so a full re-push is
    idempotent. The **pull** cursors are left alone: they are measured on
    the server's clock and rewinding them would only re-pull rows the
    local DB already has.
    """
    return State(
        last_message_id=0,
        conversations_updated_after=EPOCH,
        pulled_updated_at=state.pulled_updated_at,
        known_conversation_ids=list(state.known_conversation_ids),
        personas_updated_after=EPOCH,
        pulled_personas_updated_at=state.pulled_personas_updated_at,
        known_persona_keys=list(state.known_persona_keys),
    )


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


def read_changed_personas(
    db_path: Path, updated_after: str
) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        try:
            rows = conn.execute(
                f"SELECT {PERSONA_COLS_SQL} FROM personas "
                f"WHERE updated_at > ? ORDER BY updated_at ASC",
                (updated_after,),
            ).fetchall()
        except sqlite3.OperationalError:
            # personas table not created yet (pre-upgrade local DB) — nothing
            # to push. The next server/web_ui/seeding boot creates it.
            return []
    return [dict(r) for r in rows]


def read_all_persona_keys(db_path: Path) -> list[str]:
    with _connect(db_path) as conn:
        try:
            rows = conn.execute(
                'SELECT "group", slug FROM personas'
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return sorted(_persona_key(dict(r)) for r in rows)


# ---------------------------------------------------------------------------
# Remote POST
# ---------------------------------------------------------------------------

class SyncError(Exception):
    """Anything that should make us pause and retry next tick."""


class FatalSyncError(Exception):
    """Configuration errors (bad token, ingest disabled). No retry."""


class PullNotSupported(Exception):
    """Raised when the remote returns 404 from /api/since.

    Treated as soft on the sidecar side: the remote may be running an
    older build that predates bidirectional sync. We log a warning and
    skip the pull step; the push step still runs. This means a new
    sidecar can talk to an old server without erroring out — the user
    just doesn't get hosted-→-local propagation until they redeploy.
    """


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


def get_since(
    url: str,
    token: str,
    updated_after: str,
    known_ids: list[int],
    timeout: float,
    personas_updated_after: str,
    known_persona_keys: list[str],
) -> dict[str, Any]:
    """GET /api/since with the conversation + persona watermarks and known-key
    lists.

    Returns ``{conversations, deleted_conversation_ids, personas,
    deleted_persona_keys, server_time}`` (an older server omits the persona
    keys, which the caller treats as empty).

    HTTP error mapping (same families as ``post_batch``, with one
    difference): a 404 here is interpreted as **PullNotSupported**, not
    fatal — the remote may not yet have the pull endpoint deployed.
    Caller decides whether to skip pull or bail.
    """
    qs = urllib.parse.urlencode({
        "conversations_updated_after": updated_after,
        "known_ids": ",".join(str(i) for i in known_ids),
        "personas_updated_after": personas_updated_after,
        "known_persona_keys": ",".join(known_persona_keys),
    })
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "agent_chat-db-sync/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace") if e.fp else ""
        if e.code == 404:
            raise PullNotSupported(detail.strip() or "404 from /api/since")
        if e.code in (401, 403):
            raise FatalSyncError(
                f"server rejected the pull ({e.code}): {detail.strip()}"
            )
        raise SyncError(f"HTTP {e.code}: {detail.strip()}")
    except urllib.error.URLError as e:
        raise SyncError(f"network error: {e.reason}")
    except (TimeoutError, ConnectionError) as e:
        raise SyncError(f"transport error: {e}")


# ---------------------------------------------------------------------------
# Local DB writes (pull-apply)
# ---------------------------------------------------------------------------

def apply_pull(
    db_path: Path,
    conversations: list[dict[str, Any]],
    deleted_ids: list[int],
    personas: list[dict[str, Any]] | None = None,
    deleted_persona_keys: list[str] | None = None,
) -> dict[str, int]:
    """Apply a pull payload to the local DB.

    Conversations: ``INSERT OR REPLACE`` so hosted-side mutations
    overwrite local state for those rows. Deletions: cascade-delete
    messages first, then the conversation row. Personas: upsert by
    composite ``(group, slug)`` and delete by split key, same as the
    server's ``ingest_payload``. Single transaction.

    Returns a counters dict for logging.
    """
    personas = personas or []
    deleted_persona_keys = deleted_persona_keys or []
    upserted = deleted = cascaded = 0
    personas_upserted = personas_deleted = 0
    if not (conversations or deleted_ids or personas or deleted_persona_keys):
        return {
            "conversations_upserted": 0,
            "conversations_deleted": 0,
            "messages_deleted_cascade": 0,
            "personas_upserted": 0,
            "personas_deleted": 0,
        }
    with sqlite3.connect(str(db_path), timeout=10.0) as conn:
        try:
            conn.execute("BEGIN")
            if deleted_ids:
                placeholders = ",".join("?" for _ in deleted_ids)
                cur = conn.execute(
                    f"DELETE FROM messages WHERE conversation_id IN ({placeholders})",
                    deleted_ids,
                )
                cascaded = cur.rowcount or 0
                cur = conn.execute(
                    f"DELETE FROM conversations WHERE id IN ({placeholders})",
                    deleted_ids,
                )
                deleted = cur.rowcount or 0
            if conversations:
                conv_rows = [
                    tuple(c.get(col) for col in CONV_COLUMNS)
                    for c in conversations
                ]
                conn.executemany(
                    f"INSERT OR REPLACE INTO conversations "
                    f"({','.join(CONV_COLUMNS)}) VALUES "
                    f"({','.join('?' * len(CONV_COLUMNS))})",
                    conv_rows,
                )
                upserted = len(conv_rows)
            if deleted_persona_keys:
                split_keys = [
                    k.split(PERSONA_KEY_SEP, 1)
                    for k in deleted_persona_keys
                    if PERSONA_KEY_SEP in k
                ]
                conn.executemany(
                    'DELETE FROM personas WHERE "group" = ? AND slug = ?',
                    split_keys,
                )
                personas_deleted = len(split_keys)
            if personas:
                persona_rows = [
                    tuple(p.get(col) for col in PERSONA_COLUMNS)
                    for p in personas
                ]
                conn.executemany(
                    f"INSERT OR REPLACE INTO personas "
                    f"({PERSONA_COLS_SQL}) VALUES "
                    f"({','.join('?' * len(PERSONA_COLUMNS))})",
                    persona_rows,
                )
                personas_upserted = len(persona_rows)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {
        "conversations_upserted": upserted,
        "conversations_deleted": deleted,
        "messages_deleted_cascade": cascaded,
        "personas_upserted": personas_upserted,
        "personas_deleted": personas_deleted,
    }


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

def run_tick(
    db_path: Path,
    state: State,
    since_url: str,
    ingest_url: str,
    token: str,
    timeout: float,
    log: logging.Logger,
) -> State:
    """One sync pass. Pull-then-push. Returns the updated state.

    Order matters: pull first so hosted-side stops/deletes propagate
    locally before the push step computes its delta. Without that
    ordering, a hosted-side delete would race with a local re-upsert of
    the conversation row.

    On no-op (nothing to pull, nothing to push), state is returned
    unchanged.
    """
    if not db_path.exists():
        log.debug("local DB not present yet (%s); skipping tick.", db_path)
        return state

    # ---------- Pull ----------
    pulled_server_time: str | None = None
    try:
        since = get_since(
            since_url,
            token,
            state.pulled_updated_at,
            state.known_conversation_ids,
            timeout,
            state.pulled_personas_updated_at,
            state.known_persona_keys,
        )
    except PullNotSupported as e:
        # Mixed-version path: new sidecar, old server. Push still works.
        # Logged once per tick — could throttle further if it gets noisy.
        log.warning(
            "remote does not yet expose /api/since (%s); skipping pull. "
            "Hosted-side stops/deletes will be clobbered by the next push.",
            e,
        )
        since = None

    if since is not None:
        pull_result = apply_pull(
            db_path,
            since.get("conversations") or [],
            [int(i) for i in (since.get("deleted_conversation_ids") or [])],
            since.get("personas") or [],
            [str(k) for k in (since.get("deleted_persona_keys") or [])],
        )
        pulled_server_time = since.get("server_time")
        if any(pull_result[k] for k in (
            "conversations_upserted", "conversations_deleted",
            "personas_upserted", "personas_deleted",
        )):
            log.info(
                "pull: convs=%d deletes=%d cascaded=%d personas=%d "
                "persona_deletes=%d (server_time=%s)",
                pull_result["conversations_upserted"],
                pull_result["conversations_deleted"],
                pull_result["messages_deleted_cascade"],
                pull_result["personas_upserted"],
                pull_result["personas_deleted"],
                pulled_server_time,
            )
        else:
            log.debug("pull: no changes (server_time=%s).", pulled_server_time)

    # ---------- Push ----------
    changed_convs = read_changed_conversations(
        db_path, state.conversations_updated_after
    )
    new_msgs = read_new_messages(db_path, state.last_message_id)
    current_ids = read_all_conversation_ids(db_path)
    known_ids = set(state.known_conversation_ids)
    deleted_ids = sorted(known_ids.difference(current_ids))

    changed_personas = read_changed_personas(
        db_path, state.personas_updated_after
    )
    current_persona_keys = read_all_persona_keys(db_path)
    known_persona_keys = set(state.known_persona_keys)
    deleted_persona_keys = sorted(
        known_persona_keys.difference(current_persona_keys)
    )

    pushed = bool(
        changed_convs or new_msgs or deleted_ids
        or changed_personas or deleted_persona_keys
    )
    if pushed:
        batch = {
            "conversations": changed_convs,
            "messages": new_msgs,
            "deleted_conversation_ids": deleted_ids,
            "personas": changed_personas,
            "deleted_persona_keys": deleted_persona_keys,
        }
        log.info(
            "push: convs=%d msgs=%d deletes=%d personas=%d "
            "persona_deletes=%d → %s",
            len(changed_convs), len(new_msgs), len(deleted_ids),
            len(changed_personas), len(deleted_persona_keys), ingest_url,
        )
        result = post_batch(ingest_url, token, batch, timeout)
        log.info("server reply: %s", json.dumps(result, sort_keys=True))
    else:
        log.debug("push: no changes.")

    # ---------- New state ----------
    # **One clock per watermark.** The push cursor advances only to
    #   max( old, max updated_at among the rows we actually pushed )
    # — all values read out of the *local* DB. It used to also fold in
    # the pull's `server_time`, which marched it forward on the *remote*
    # clock every tick whether anything was pushed or not; any local
    # write whose `updated_at` landed behind that never got pushed, and
    # never would, because the cursor only grows. A couple of seconds of
    # skew between this machine and Fly was enough to lose a row.
    #
    # What that bump bought was suppressing the echo of a row we had just
    # pulled. It is still only an echo: `/api/ingest` upserts with the
    # row's own `updated_at` and never rewrites it, so the echoed payload
    # is byte-identical to what the server already holds, and pushing it
    # advances the cursor past it — one redundant push per hosted-side
    # edit, then quiet. A wasted POST is cheap; a silently dropped local
    # edit is not.
    new_pushed_at = max(
        (c["updated_at"] for c in changed_convs),
        default=state.conversations_updated_after,
    )
    new_pulled_at = pulled_server_time or state.pulled_updated_at

    # Persona watermarks split the same way: push on local `updated_at`,
    # pull on the server's clock.
    new_persona_pushed_at = max(
        (p["updated_at"] for p in changed_personas),
        default=state.personas_updated_after,
    )
    new_persona_pulled_at = (
        pulled_server_time or state.pulled_personas_updated_at
    )

    new_state = State(
        last_message_id=max(
            state.last_message_id,
            max((m["id"] for m in new_msgs), default=state.last_message_id),
        ),
        conversations_updated_after=new_pushed_at,
        pulled_updated_at=new_pulled_at,
        known_conversation_ids=current_ids,
        personas_updated_after=new_persona_pushed_at,
        pulled_personas_updated_at=new_persona_pulled_at,
        known_persona_keys=current_persona_keys,
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
        help="Base URL of the deployed Web UI (e.g. https://agent-chat.ai-automation-tools.dev). "
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
        "--force-push",
        action="store_true",
        help="Rewind the push watermarks before the first tick and re-ship "
             "every local conversation, message and persona. Ingest is "
             "idempotent; use this to repair a mirror that has drifted "
             "instead of hand-editing the state file.",
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
    base = args.remote_url.rstrip("/")
    ingest_url = base + "/api/ingest"
    since_url = base + "/api/since"

    log.info("local DB: %s", db_path)
    log.info("state file: %s", state_path)
    log.info("ingest URL: %s", ingest_url)
    log.info("since URL: %s", since_url)
    log.info("mode: %s, interval: %ss", "once" if args.once else "daemon", args.interval)

    state = load_state(state_path)
    if args.force_push:
        log.info(
            "--force-push: rewinding push watermarks; this run re-ships "
            "every local conversation, message and persona."
        )
        state = rewind_push_watermarks(state)
    _install_signal_handlers(log)

    consecutive_failures = 0
    while True:
        try:
            new_state = run_tick(
                db_path, state, since_url, ingest_url,
                args.token, args.timeout, log,
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
