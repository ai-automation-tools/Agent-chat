"""SQLite layer for the web UI — connection, schema, and all SQL helpers.

The DB path is a module global set once at startup via :func:`set_db_path`
(called from ``web_ui.main()``; tests point it at an isolated temp DB).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH: str = ""


def set_db_path(path: str) -> None:
    """Point the whole web process at a SQLite database file.

    Also exports ``AGENT_CHAT_DB``, because ``orchestrator.personas`` resolves
    its own path per call (``$AGENT_CHAT_DB`` > ``<repo>/db/chat.db``) and never
    sees this module's ``DB_PATH``. Without this, ``web_ui.py --db-path <other>``
    reads conversations from one DB and personas from another — and tests
    pointing at a temp DB would quietly touch the real ``db/chat.db``. On Fly the
    two already agree (``fly.toml`` sets ``AGENT_CHAT_DB=/data/chat.db``, which
    is also the ``--db-path`` default), so this only closes the divergent case.
    """
    global DB_PATH
    DB_PATH = path
    os.environ["AGENT_CHAT_DB"] = path


# Mirrors the SCHEMA in src/agent_chat_mcp.py. Both must stay in sync —
# schema changes require updating both files plus a CHANGELOG entry. Kept
# duplicated rather than imported so web_ui.py doesn't drag in the MCP
# server module's heavy imports at startup.
SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    topic             TEXT NOT NULL,
    participants      TEXT NOT NULL,
    mode              TEXT NOT NULL,
    max_turns         INTEGER NOT NULL,
    current_turn      TEXT,
    status            TEXT NOT NULL,
    end_reason        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    preset            TEXT,
    kickoff_template  TEXT,
    participant_personas TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL REFERENCES conversations(id),
    sender           TEXT NOT NULL,
    content          TEXT NOT NULL,
    signal           TEXT,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS personas (
    "group"      TEXT NOT NULL,
    slug         TEXT NOT NULL,
    name         TEXT NOT NULL,
    tags         TEXT,
    category     TEXT,
    subcategory  TEXT,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY ("group", slug)
);

CREATE INDEX IF NOT EXISTS idx_personas_updated ON personas(updated_at);
"""

# Columns added after the initial schema. Mirrors _MIGRATIONS in
# src/agent_chat_mcp.py — keep both lists in sync when adding new columns.
_MIGRATIONS = (
    ("conversations", "preset",           "ALTER TABLE conversations ADD COLUMN preset TEXT"),
    ("conversations", "kickoff_template", "ALTER TABLE conversations ADD COLUMN kickoff_template TEXT"),
    ("conversations", "participant_personas", "ALTER TABLE conversations ADD COLUMN participant_personas TEXT"),
)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    # isolation_level=None (autocommit) matches every other writer on this DB —
    # agent_chat_mcp, seeding, personas, inspect_conversations. Without it,
    # sqlite3 opens an implicit transaction on the first write and holds it until
    # an explicit commit, which is exactly how a second process gets "database is
    # locked" on a shared WAL file.
    conn = sqlite3.connect(DB_PATH, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def db_init() -> None:
    """Create tables/indexes if missing, then apply additive column migrations.

    Used on the public Fly deploy where the persistent volume starts empty:
    the first request would otherwise hit "no such table: conversations".
    Locally this is a no-op when the DB already exists.

    Migrations are idempotent: each is gated on `PRAGMA table_info(table)`
    not already listing the column. Safe across schema versions in either
    direction (e.g. old sidecar pushing to a freshly-migrated server, or
    a freshly-deployed server reading an older volume snapshot).
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(SCHEMA)
        for table, column, ddl in _MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(ddl)


def list_stats() -> dict[str, int]:
    """Headline counters for the landing page.

    Three numbers: total conversations, currently-active conversations,
    total messages. Cheap enough to compute on every render — three
    indexed COUNT(*) queries against the same connection.
    """
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE status='active'"
        ).fetchone()[0]
        messages = conn.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]
    return {
        "conversations": int(total),
        "active": int(active),
        "messages": int(messages),
    }


def list_conversations() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY id DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["participants"] = json.loads(d["participants"])
            except (json.JSONDecodeError, TypeError):
                pass
            d["message_count"] = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (r["id"],),
            ).fetchone()[0]
            out.append(d)
        return out


def list_featured_debates(limit: int = 4) -> list[dict[str, Any]]:
    """Completed conversations to feature in the homepage hero panel.

    Newest-first completed debates with at least a handful of messages (trivial
    /aborted runs are skipped). Each row carries its ``message_count`` and a
    ``teaser`` — the opening non-system message, trimmed by the renderer into a
    one-line description. Debater labels come from ``participant_personas`` when
    a cast was recorded (see ``_conv_debaters``), else the raw agent ids.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE status='complete' ORDER BY id DESC"
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            n = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (r["id"],),
            ).fetchone()[0]
            if n < 4:  # skip trivial / aborted runs
                continue
            d = dict(r)
            try:
                d["participants"] = json.loads(d["participants"])
            except (json.JSONDecodeError, TypeError):
                pass
            d["message_count"] = n
            opener = conn.execute(
                "SELECT content FROM messages "
                "WHERE conversation_id = ? AND sender != 'system' "
                "ORDER BY id ASC LIMIT 1",
                (r["id"],),
            ).fetchone()
            d["teaser"] = (opener["content"] if opener else "") or ""
            out.append(d)
            if len(out) >= limit:
                break
        return out


def get_conversation(cid: int) -> dict[str, Any] | None:
    with _connect() as conn:
        c = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if not c:
            return None
        msgs = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (cid,),
        ).fetchall()
        conv = dict(c)
        try:
            conv["participants"] = json.loads(conv["participants"])
        except (json.JSONDecodeError, TypeError):
            pass
        return {"conversation": conv, "messages": [dict(m) for m in msgs]}


def messages_since(cid: int, last_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages "
            "WHERE conversation_id = ? AND id > ? ORDER BY id ASC",
            (cid, last_id),
        ).fetchall()
        return [dict(r) for r in rows]


def conversation_status(cid: int) -> str | None:
    with _connect() as conn:
        r = conn.execute(
            "SELECT status FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        return r["status"] if r else None


def conversation_turn_state(cid: int) -> tuple[str | None, str | None]:
    """Status + current_turn in one read — polled each tick by the SSE stream
    so the live viewer can show a whose-turn indicator. Returns (None, None)
    when the conversation doesn't exist."""
    with _connect() as conn:
        r = conn.execute(
            "SELECT status, current_turn FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        return (r["status"], r["current_turn"]) if r else (None, None)


def stop_conversation(cid: int) -> dict[str, Any] | None:
    """Force a conversation complete with end_reason='stopped by operator'.

    Mirrors the SQL in inspect_conversations.cmd_stop so the CLI and Web UI
    end up with identical row state. Returns None if the conversation
    doesn't exist; otherwise returns {'already_complete': bool, 'status':
    'complete', 'end_reason': str}.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        # Default deferred isolation; the `with` block commits on clean exit.
        row = conn.execute(
            "SELECT status, end_reason FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] == "complete":
            return {
                "already_complete": True,
                "status": "complete",
                "end_reason": row["end_reason"],
            }
        conn.execute(
            "UPDATE conversations SET status='complete', "
            "end_reason='stopped by operator', current_turn=NULL, "
            "updated_at=? WHERE id=?",
            (now, cid),
        )
        return {
            "already_complete": False,
            "status": "complete",
            "end_reason": "stopped by operator",
        }


# Conversation columns the ingest endpoint accepts. Order matters — both the
# INSERT statement and the per-row tuple build follow this list. If schema
# changes, update SCHEMA above and this tuple in lockstep.
_CONV_COLUMNS = (
    "id", "topic", "participants", "mode", "max_turns",
    "current_turn", "status", "end_reason", "created_at", "updated_at",
    "preset", "kickoff_template", "participant_personas",
)
_MSG_COLUMNS = (
    "id", "conversation_id", "sender", "content", "signal", "created_at",
)
# Personas key on a composite (group, slug). "group" is a SQL reserved word, so
# every identifier is double-quoted in generated SQL via _PERSONA_COLS_SQL — a
# bare ",".join would emit `group` unquoted and fail to parse. Mirrors
# PERSONA_COLUMNS in scripts/db_sync.py; keep both in lockstep.
_PERSONA_COLUMNS = (
    "group", "slug", "name", "tags", "category", "subcategory",
    "body", "created_at", "updated_at",
)
_PERSONA_COLS_SQL = ",".join(f'"{c}"' for c in _PERSONA_COLUMNS)

# Composite-key wire format: group + Unit-Separator (0x1F) + slug. 0x1F is absent
# from group names and [a-z0-9-] slugs, and urlencodes cleanly. Used identically
# on both sides (here and in scripts/db_sync.py) for deletes-by-set-difference.
_PERSONA_KEY_SEP = "\x1f"


def _persona_key(row: dict[str, Any]) -> str:
    return f'{row["group"]}{_PERSONA_KEY_SEP}{row["slug"]}'


def ingest_payload(
    conversations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    deleted_conversation_ids: list[int],
    personas: list[dict[str, Any]] | None = None,
    deleted_persona_keys: list[str] | None = None,
) -> dict[str, int]:
    """Apply a sync batch from the local writer (scripts/db_sync.py).

    Single transaction. Idempotent — re-posting the same payload is a no-op.

    - Conversations are upserted by ``id`` via ``INSERT OR REPLACE`` so
      ``current_turn`` / ``status`` / ``end_reason`` / ``updated_at`` flips
      propagate.
    - Messages use ``INSERT OR IGNORE`` so re-shipping the same id is safe.
    - Deletions run first and remove the conversation rows plus their
      messages (manual cascade — SQLite FK enforcement is off by default in
      this codebase).
    - Personas are upserted by ``(group, slug)`` via ``INSERT OR REPLACE`` and
      deleted by split composite key. Same transaction; backward-compatible —
      a payload from an old sidecar omits both and they no-op.
    """
    personas = personas or []
    deleted_persona_keys = deleted_persona_keys or []
    upserted = inserted = deleted = cascaded = 0
    personas_upserted = personas_deleted = 0
    with _connect() as conn:
        try:
            conn.execute("BEGIN")
            if deleted_conversation_ids:
                placeholders = ",".join("?" for _ in deleted_conversation_ids)
                cur = conn.execute(
                    f"DELETE FROM messages WHERE conversation_id IN ({placeholders})",
                    deleted_conversation_ids,
                )
                cascaded = cur.rowcount or 0
                cur = conn.execute(
                    f"DELETE FROM conversations WHERE id IN ({placeholders})",
                    deleted_conversation_ids,
                )
                deleted = cur.rowcount or 0
            if conversations:
                conv_rows = [
                    tuple(c.get(col) for col in _CONV_COLUMNS)
                    for c in conversations
                ]
                conn.executemany(
                    f"INSERT OR REPLACE INTO conversations "
                    f"({','.join(_CONV_COLUMNS)}) VALUES "
                    f"({','.join('?' * len(_CONV_COLUMNS))})",
                    conv_rows,
                )
                upserted = len(conv_rows)
            if messages:
                msg_rows = [
                    tuple(m.get(col) for col in _MSG_COLUMNS)
                    for m in messages
                ]
                conn.executemany(
                    f"INSERT OR IGNORE INTO messages "
                    f"({','.join(_MSG_COLUMNS)}) VALUES "
                    f"({','.join('?' * len(_MSG_COLUMNS))})",
                    msg_rows,
                )
                # executemany's rowcount is unreliable across SQLite
                # versions; report the attempted-insert count, which the
                # client already knows. Idempotency on the server side is
                # what makes this safe.
                inserted = len(msg_rows)
            if deleted_persona_keys:
                split_keys = [
                    k.split(_PERSONA_KEY_SEP, 1)
                    for k in deleted_persona_keys
                    if _PERSONA_KEY_SEP in k
                ]
                conn.executemany(
                    'DELETE FROM personas WHERE "group" = ? AND slug = ?',
                    split_keys,
                )
                personas_deleted = len(split_keys)
            if personas:
                persona_rows = [
                    tuple(p.get(col) for col in _PERSONA_COLUMNS)
                    for p in personas
                ]
                conn.executemany(
                    f"INSERT OR REPLACE INTO personas "
                    f"({_PERSONA_COLS_SQL}) VALUES "
                    f"({','.join('?' * len(_PERSONA_COLUMNS))})",
                    persona_rows,
                )
                personas_upserted = len(persona_rows)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {
        "conversations_upserted": upserted,
        "messages_inserted": inserted,
        "conversations_deleted": deleted,
        "messages_deleted_cascade": cascaded,
        "personas_upserted": personas_upserted,
        "personas_deleted": personas_deleted,
    }


def delete_conversation(cid: int) -> dict[str, Any] | None:
    """Permanently remove a conversation and cascade-delete its messages.

    Returns ``None`` if the conversation doesn't exist; otherwise
    ``{"deleted": True, "cascaded_messages": <count>}``. Used by
    ``POST /api/conversations/{cid}/delete`` (operator action from the
    hosted UI) and propagated to the local DB by the sidecar's pull
    step on the next tick.

    Manual cascade because SQLite FK enforcement is off in this codebase
    (matches the convention in ``ingest_payload`` for hosted-side deletes
    coming from the local sidecar).
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if row is None:
            return None
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (cid,)
            )
            cascaded = cur.rowcount or 0
            conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"deleted": True, "cascaded_messages": cascaded}


def since_payload(
    updated_after: str,
    known_ids: list[int],
    personas_updated_after: str | None = None,
    known_persona_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Build the response body for ``GET /api/since``.

    Returns conversations whose ``updated_at`` is strictly greater than
    ``updated_after`` plus the subset of ``known_ids`` that no longer
    exist server-side (i.e., what the sidecar should delete locally).
    Also returns ``server_time`` so the sidecar can use it as its next
    watermark and avoid clock-skew bugs.

    Personas sync the same way, keyed on composite ``(group, slug)``:
    rows with ``updated_at`` > ``personas_updated_after`` plus the
    ``known_persona_keys`` no longer present server-side. When
    ``personas_updated_after`` is None (an old sidecar that doesn't send
    the param) the persona work is skipped entirely and empty lists are
    returned — backward-compatible.

    **Messages are intentionally not included.** They flow local-only-
    origin: agents only run locally, so messages always originate
    locally; bidirectional sync covers conversation-row mutations
    (status, topic, end_reason, deletion). See ``docs/App/db-sync.md``.
    """
    cols = ",".join(_CONV_COLUMNS)
    server_time = datetime.now(timezone.utc).isoformat()
    persona_rows: list[dict[str, Any]] = []
    deleted_persona_keys: list[str] = []
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM conversations "
            f"WHERE updated_at > ? ORDER BY updated_at ASC",
            (updated_after,),
        ).fetchall()
        existing = {
            int(r[0])
            for r in conn.execute("SELECT id FROM conversations").fetchall()
        }
        if personas_updated_after is not None:
            prows = conn.execute(
                f"SELECT {_PERSONA_COLS_SQL} FROM personas "
                f"WHERE updated_at > ? ORDER BY updated_at ASC",
                (personas_updated_after,),
            ).fetchall()
            persona_rows = [dict(r) for r in prows]
            existing_keys = {
                _persona_key(dict(r))
                for r in conn.execute(
                    'SELECT "group", slug FROM personas'
                ).fetchall()
            }
            deleted_persona_keys = sorted(
                set(known_persona_keys or []).difference(existing_keys)
            )
    deleted = sorted(set(known_ids).difference(existing))
    return {
        "conversations": [dict(r) for r in rows],
        "deleted_conversation_ids": deleted,
        "personas": persona_rows,
        "deleted_persona_keys": deleted_persona_keys,
        "server_time": server_time,
    }
