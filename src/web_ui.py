"""
agent_chat web UI — local read-only viewer for chat.db.

A small Starlette app that reads the same SQLite database the MCP server
writes to. Run as a separate process; does NOT replace or wrap the MCP
server. Bind defaults to 127.0.0.1.

DB path resolution (same precedence as the MCP server):
    --db-path <path>  >  $AGENT_CHAT_DB  >  <repo>/db/chat.db

Usage:
    python src/web_ui.py                                   # default DB
    python src/web_ui.py --host 0.0.0.0 --port 8765        # custom bind
    python src/web_ui.py --db-path /custom/chat.db         # explicit override

Then open http://127.0.0.1:8765/ in a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import io
import json
import os
import re
import secrets
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from markdown_it import MarkdownIt
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

# Orchestrator package (sibling to this file). When run as ``python src/web_ui.py``
# the script's directory is on sys.path so ``orchestrator`` imports natively.
from orchestrator import personas as personas_registry  # noqa: E402
from orchestrator import preflight as orch_preflight  # noqa: E402
from orchestrator import seeding as orch_seeding  # noqa: E402
from presets import PRESETS, PRESET_NAMES  # noqa: E402


DB_PATH: str = ""
POLL_INTERVAL_SECONDS = 1.0


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
# Markdown rendering
# ---------------------------------------------------------------------------
# `gfm-like` preset gives us tables, strikethrough, and linkify (auto-linking
# bare URLs) out of the box — all features agents reach for without thinking.
# `html: False` overrides the preset default to reject raw HTML in source,
# which is the strict allowlist the Roadmap called for. `breaks: True`
# converts single newlines to <br> so the rendered output keeps the chat-like
# feel of the pre-Markdown plain-text era.

_md = MarkdownIt("gfm-like", {"html": False, "breaks": True})


def _link_open_renderer(self, tokens, idx, options, env):
    """Add target='_blank' rel='noopener noreferrer' to all rendered links.
    Keeps clicks on agent-emitted URLs from yanking the operator out of the
    conversation, and the rel attrs neutralize tab-napping risks.
    """
    tokens[idx].attrSet("target", "_blank")
    tokens[idx].attrSet("rel", "noopener noreferrer")
    return self.renderToken(tokens, idx, options, env)


_md.add_render_rule("link_open", _link_open_renderer)


def render_markdown(text: str) -> str:
    """Render a single message's content as safe HTML.

    Server-side only. The output is trusted by the browser without further
    escaping (the JS uses `innerHTML` for content_html). Safety relies on
    `html: False` plus markdown-it-py's URL-scheme validator (which rejects
    `javascript:` etc. in link hrefs).
    """
    return _md.render(text or "")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
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


# ---------------------------------------------------------------------------
# HTML rendering (inline — fine for a small local app)
# ---------------------------------------------------------------------------

BASE_CSS = """
/* Apex-aligned design tokens — mirror mikesailab.com.
   Canvas #060606, zinc text, sky-400 links, sky-500 actions, red-500
   destructive, amber-500 warning. Class names match the names the existing
   renderers and SSE-append JS write to the DOM — do not rename without
   updating _render_message + the inline script in _render_conversation. */
:root {
  --bg: #060606;
  --panel: rgba(24, 24, 27, 0.4);          /* zinc-900/40 */
  --panel-solid: #18181b;                   /* zinc-900 */
  --panel-2: #27272a;                       /* zinc-800 */
  --text: #f4f4f5;                          /* zinc-100 */
  --muted: #a1a1aa;                         /* zinc-400 */
  --muted-2: #71717a;                       /* zinc-500 */
  --accent: #38bdf8;                        /* sky-400 — links */
  --accent-strong: #0ea5e9;                 /* sky-500 */
  --accent-2: #38bdf8;                      /* sky-500 — actions/done */
  --border: rgba(39, 39, 42, 0.6);          /* zinc-800/60 */
  --border-strong: #3f3f46;                 /* zinc-700 */
  --good: #38bdf8;                          /* sky-500 */
  --warn: #f59e0b;                          /* amber-500 */
  --bad: #ef4444;                           /* red-500 */
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.6 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* Topbar — thin fixed bar mirroring the apex's `h-12 bg-[#060606]/95
   backdrop-blur border-b border-zinc-900`. */
.topbar {
  position: sticky; top: 0; z-index: 40;
  height: 48px;
  background: rgba(6, 6, 6, 0.95);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-bottom: 1px solid #18181b;
}
.topbar-inner {
  height: 100%;
  display: flex; align-items: center; gap: 16px;
  padding: 0 24px;
  max-width: 1240px; margin: 0 auto;
}
.topbar .mark {
  display: inline-flex; align-items: center; gap: 10px;
  text-decoration: none; color: var(--text);
  font-weight: 600; font-size: 14px;
  letter-spacing: -0.005em;
}
.topbar .mark .glyph {
  width: 28px; height: 28px;
  background: var(--good);
  border-radius: 6px;
  display: grid; place-items: center;
  color: #09090b;
  font-weight: 800; font-size: 14px; line-height: 1;
}
.topbar .crumb {
  color: var(--muted-2);
  font-size: 13px;
}
.topbar .crumb a { color: var(--muted); text-decoration: none; }
.topbar .crumb a:hover { color: var(--text); }
.topbar .crumb strong { color: var(--text); font-weight: 500; }
.topbar nav {
  margin-left: auto;
  display: flex; align-items: center; gap: 6px;
}
.topbar nav a {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  color: var(--muted);
  text-decoration: none;
  border: 1px solid transparent;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.topbar nav a:hover {
  color: var(--text);
  background: rgba(24, 24, 27, 0.6);
  border-color: rgba(63, 63, 70, 0.6);
}
.topbar nav a.cta {
  color: var(--good);
  border-color: rgba(16, 185, 129, 0.32);
  background: rgba(16, 185, 129, 0.08);
}
.topbar nav a.cta:hover {
  background: var(--good);
  color: #09090b;
  border-color: var(--good);
}

main {
  padding: 40px 24px 64px;
  max-width: 1100px;
  margin: 0 auto;
}
main h2.page-title {
  font-size: 28px; font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0 0 6px;
  color: var(--text);
}
main p.page-sub {
  color: var(--muted-2);
  margin: 0 0 32px;
  font-size: 14px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; text-decoration-color: var(--accent-strong); }
/* Conversation list table — apex aesthetic: zinc-900/40 panel surface,
   zinc-800/60 dividers, sky-400 row link, uppercase tracking-wider eyebrow. */
.table-wrap {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel);
  overflow: hidden;
}
table { width: 100%; border-collapse: collapse; }
th, td {
  padding: 12px 16px; text-align: left;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
th {
  font-weight: 500; color: var(--muted-2); font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.08em;
  background: rgba(9, 9, 11, 0.5);
}
tr:last-child td { border-bottom: 0; }
tbody tr { transition: background 0.15s ease; }
tbody tr:hover td { background: rgba(24, 24, 27, 0.6); }
td a { color: var(--text); text-decoration: none; font-weight: 500; }
td a:hover { color: var(--accent); }

/* Status pill — sky for active, muted for complete (apex's 'Live' tile
   convention uses sky-400). */
.status-active, .status-complete {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 500;
}
.status-active { color: var(--accent); }
.status-active::before {
  content: ''; width: 6px; height: 6px;
  border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 6px var(--accent);
  animation: pulse 1.8s ease-in-out infinite;
}
.status-complete { color: var(--muted-2); }
.status-complete::before {
  content: ''; width: 6px; height: 6px;
  border-radius: 50%; background: var(--muted-2);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  background: rgba(9, 9, 11, 0.6);
  color: var(--muted);
  border: 1px solid var(--border);
  font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
}
.muted { color: var(--muted-2); }
.empty {
  padding: 64px 24px;
  text-align: center;
  color: var(--muted-2);
  border: 1px dashed var(--border);
  border-radius: 4px;
  background: var(--panel);
}
.empty code {
  color: var(--good);
  background: rgba(16, 185, 129, 0.08);
  padding: 2px 8px; border-radius: 3px;
  font-size: 12.5px;
}

/* Meta-grid — definition list of conversation metadata, styled as an
   apex panel (zinc-900/40 + zinc-800/60 border). */
.meta-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 20px;
  margin: 0 0 20px;
  padding: 20px 22px;
  background: var(--panel);
  border-radius: 4px;
  border: 1px solid var(--border);
  font-size: 13px;
}
.meta-grid dt {
  color: var(--muted-2);
  text-transform: uppercase;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  align-self: center;
  font-weight: 500;
}
.meta-grid dd { margin: 0; color: var(--text); }
/* Transcript — column of zinc-900/40 message cards. Sender-colored left rule
   uses sky-400 for an agent message, sky for `signal=done`, red for
   `signal=blocked`, muted zinc for system messages. */
.transcript { display: flex; flex-direction: column; gap: 14px; }
.msg {
  padding: 16px 20px;
  border-radius: 4px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 2px solid var(--accent);
  transition: border-color 0.15s ease, background 0.15s ease;
}
.msg:hover {
  background: rgba(24, 24, 27, 0.55);
  border-left-color: var(--accent-strong);
}
.msg.sender-system { border-left-color: var(--muted-2); }
.msg.signal-done { border-left-color: var(--good); }
.msg.signal-blocked { border-left-color: var(--bad); }
.msg-head {
  display: flex; gap: 14px; align-items: baseline;
  font-size: 12px; color: var(--muted-2);
  margin-bottom: 10px;
}
.msg-head .who {
  color: var(--text);
  font-weight: 600;
  font-size: 13px;
  letter-spacing: -0.005em;
}
.msg-head .time {
  font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 11px;
}
.msg-head .signal {
  text-transform: uppercase; font-size: 10px;
  padding: 2px 8px; border-radius: 3px;
  letter-spacing: 0.08em; font-weight: 600;
  background: rgba(9, 9, 11, 0.6);
  border: 1px solid var(--border);
  color: var(--muted);
}
.msg-head .signal.done {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.32);
  color: var(--good);
}
.msg-head .signal.blocked {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.32);
  color: var(--bad);
}
.msg-body { word-wrap: break-word; overflow-wrap: anywhere;
            color: #e4e4e7; font-size: 14.5px; line-height: 1.65; }
.msg-body > :first-child { margin-top: 0; }
.msg-body > :last-child { margin-bottom: 0; }
.msg-body p { margin: 0 0 12px; }
.msg-body p:last-child { margin-bottom: 0; }
.msg-body strong { color: var(--text); font-weight: 600; }
.msg-body em { font-style: italic; color: var(--text); }
.msg-body a { color: var(--accent); text-decoration: underline;
              text-decoration-color: rgba(56, 189, 248, 0.4);
              text-underline-offset: 2px; }
.msg-body a:hover { text-decoration-color: var(--accent); }
.msg-body ul, .msg-body ol { margin: 8px 0 12px; padding-left: 26px; }
.msg-body li { margin: 3px 0; }
.msg-body li > p { margin: 0; }
.msg-body blockquote {
  margin: 10px 0; padding: 6px 16px;
  border-left: 2px solid var(--border-strong);
  color: var(--muted);
  background: rgba(9, 9, 11, 0.4);
}
.msg-body code {
  font: 13px/1.5 ui-monospace, "Cascadia Mono", "Consolas", monospace;
  background: rgba(9, 9, 11, 0.6);
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--border);
  color: #f4f4f5;
}
.msg-body pre {
  margin: 10px 0; padding: 14px 16px;
  background: #09090b;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow-x: auto;
}
.msg-body pre code {
  background: transparent; border: 0; padding: 0;
  font-size: 12.5px;
}
.msg-body h1, .msg-body h2, .msg-body h3,
.msg-body h4, .msg-body h5, .msg-body h6 {
  margin: 16px 0 8px; font-weight: 600; color: var(--text);
  letter-spacing: -0.01em;
}
.msg-body h1 { font-size: 19px; }
.msg-body h2 { font-size: 17px; }
.msg-body h3 { font-size: 15px; }
.msg-body h4, .msg-body h5, .msg-body h6 { font-size: 14px; }
.msg-body table {
  border-collapse: collapse; margin: 10px 0;
  font-size: 13px;
  border: 1px solid var(--border);
}
.msg-body th, .msg-body td {
  border: 1px solid var(--border);
  padding: 6px 12px;
  text-align: left;
}
.msg-body th {
  background: rgba(9, 9, 11, 0.5);
  color: var(--muted);
  font-weight: 500;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.06em;
}
.msg-body hr { border: 0; border-top: 1px solid var(--border); margin: 14px 0; }
.msg-body del { color: var(--muted-2); }

/* Live indicator — sky-400 pulse for active, muted dot for ended.
   The 'stopped' class swap is set by the SSE 'complete' handler. */
.live-indicator {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 11.5px; color: var(--accent);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 500;
}
.live-indicator .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent);
  animation: pulse 1.8s ease-in-out infinite;
}
.live-indicator.stopped { color: var(--muted-2); }
.live-indicator.stopped .dot {
  background: var(--muted-2);
  box-shadow: none;
  animation: none;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

/* "Next: launch each CLI" panel on fresh conversations (status=active
   + 0 messages). Disappears once the first SSE message lands. Subtle
   sky tint so it reads as a guide, not an alert. */
.next-steps {
  margin: 20px 0;
  padding: 20px 22px;
  background: rgba(56, 189, 248, 0.04);
  border: 1px solid rgba(56, 189, 248, 0.25);
  border-radius: 8px;
}
.next-steps h3 {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
}
.next-steps p { margin: 0 0 14px 0; color: var(--muted); }
.next-steps p:last-child { margin-bottom: 0; }
.next-steps .ns-hint { font-size: 12px; color: var(--muted-2); margin-top: 16px; }
.ns-list {
  list-style: none;
  margin: 0 0 4px 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ns-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(24, 24, 27, 0.5);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.ns-agent {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 13px;
  color: var(--text);
}
.ns-first {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--accent);
  background: rgba(56, 189, 248, 0.12);
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.ns-spacer { flex: 1 1 auto; }

/* Page header row — title on the left, primary CTA on the right.
   Used on /conversations and any future list view that gets a "new"
   action. Wraps gracefully on narrow viewports. */
.page-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.page-header-row > div { flex: 1 1 auto; min-width: 0; }
.page-header-row .btn { flex: 0 0 auto; }

/* Buttons — apex CTA family. Default = ghost (zinc border, paper text).
   .btn-primary = sky solid. .btn-danger = red outline that inverts. */
.btn {
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  padding: 7px 14px;
  border-radius: 4px;
  border: 1px solid rgba(63, 63, 70, 0.7);
  background: transparent;
  color: var(--text);
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  text-decoration: none;
  transition: all 0.15s ease;
}
.btn:hover {
  background: rgba(24, 24, 27, 0.7);
  border-color: var(--border-strong);
  text-decoration: none;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary {
  background: var(--good);
  color: #09090b;
  border-color: var(--good);
  font-weight: 600;
}
.btn-primary:hover {
  background: transparent;
  color: var(--good);
  box-shadow: inset 0 0 0 1px var(--good);
}
.btn-danger {
  border-color: rgba(239, 68, 68, 0.5);
  color: var(--bad);
  background: rgba(239, 68, 68, 0.06);
}
.btn-danger:hover {
  background: var(--bad);
  color: #09090b;
  border-color: var(--bad);
}
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.detail-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; gap: 16px; flex-wrap: wrap;
}
.detail-head h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}
"""


# ---------------------------------------------------------------------------
# Homepage CSS — apex-aligned. Mirrors mikesailab.com: #060606 canvas,
# Inter font, zinc-100 text, sky-400 'Live' pills, sky-500 accents on
# hover and CTAs. Tailwind utility classes drive most layout via the CDN
# <script> in <head>; this stylesheet only carries rules Tailwind can't
# express ergonomically (the live-pill pulse animation, code-block tints,
# and the home-only `.live-tile` SVG glyph hover transitions).
# ---------------------------------------------------------------------------

HOME_CSS = """
body.home { font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif; }
summary::-webkit-details-marker { display: none; }
summary { list-style: none; }
@keyframes pulse-sky { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Live pill — sky-400 dot + uppercase label, the apex 'Live' convention. */
.live-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.12em; color: #38bdf8;
  font-weight: 500;
}
.live-pill .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #38bdf8; box-shadow: 0 0 6px #38bdf8;
  animation: pulse-sky 1.6s ease-in-out infinite;
}
.live-pill.idle { color: #71717a; }
.live-pill.idle .dot {
  background: #71717a; box-shadow: none; animation: none;
}

/* Live-tile SVG glyph — fades in from corner, brightens on hover.
   Mirrors apex's per-tile decorative line-art convention. */
.live-tile .glyph { transition: color 0.2s ease, opacity 0.2s ease; }

/* Code blocks inside the how-it-works steps — sky accent rule on
   the left, monospace, zinc-100 text on near-black. */
.step-code {
  background: #09090b;
  border: 1px solid rgba(39, 39, 42, 0.6);
  border-left: 2px solid #38bdf8;
  border-radius: 4px;
  padding: 14px 16px;
  overflow-x: auto;
  font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: #e4e4e7;
  margin: 0;
}
.step-code .cmt { color: #71717a; }
.step-code .em  { color: #38bdf8; }
.step-code-inline {
  font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 13px;
  color: #38bdf8;
  background: rgba(16, 185, 129, 0.08);
  padding: 1px 6px;
  border-radius: 3px;
}

/* Latest list — apex tile-row hover (slide-in + sky-tinted bg). */
.latest-row {
  display: grid;
  grid-template-columns: 70px minmax(0, 2.4fr) minmax(0, 1fr) 110px;
  gap: 20px;
  align-items: center;
  padding: 16px 6px;
  border-top: 1px solid rgba(39, 39, 42, 0.6);
  text-decoration: none;
  color: #f4f4f5;
  transition: padding-left 0.18s ease, background 0.18s ease;
}
.latest-row:last-child { border-bottom: 1px solid rgba(39, 39, 42, 0.6); }
.latest-row:hover {
  padding-left: 16px;
  background: linear-gradient(90deg, rgba(56,189,248,0.08), transparent 75%);
}
.latest-row .lid {
  font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 12px; color: #71717a;
}
.latest-row .ltopic {
  font-weight: 500; font-size: 15px; color: #f4f4f5;
  letter-spacing: -0.005em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.latest-row .lparts {
  font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 11.5px; color: #a1a1aa;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.latest-row .lstatus {
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.1em; text-align: right;
  display: inline-flex; align-items: center; gap: 6px;
  justify-content: flex-end;
}
.latest-row .lstatus::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
}
.latest-row .lstatus.active { color: #38bdf8; }
.latest-row .lstatus.active::before {
  background: #38bdf8; box-shadow: 0 0 6px #38bdf8;
}
.latest-row .lstatus.complete { color: #71717a; }
.latest-row .lstatus.complete::before { background: #71717a; }

@media (max-width: 700px) {
  .latest-row {
    grid-template-columns: 50px 1fr 90px;
    gap: 14px;
  }
  .latest-row .lparts { display: none; }
}

/* (Old console-arena CSS removed — apex match uses Tailwind CDN +
   inline utility classes for layout. See HOME_CSS rules above for the
   small handful of rules still emitted server-side.) */
"""


# Styles for the /orchestrate route. Lives inside the _layout shell, so
# tokens from BASE_CSS (--bg, --text, --accent, --border, --good, --bad)
# are available without redeclaration. Scoped under `.orch-shell` so the
# form rules cannot leak into the conversations index / detail pages.
ORCHESTRATE_CSS = """
.orch-shell { max-width: 760px; margin: 32px auto; padding: 0 24px; }
.orch-head h2 {
  font-size: 28px; font-weight: 700; letter-spacing: -0.02em;
  margin: 0 0 8px 0;
}
.orch-head p { color: var(--muted); margin: 0 0 28px 0; max-width: 60ch; }

.orch-form { display: flex; flex-direction: column; gap: 22px; }
.orch-form section { display: flex; flex-direction: column; gap: 8px; }
.orch-form .lbl {
  font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted-2); font-weight: 600;
}
.orch-form .hint { color: var(--muted-2); font-size: 12px; margin: 0; }

.orch-form input[type=text],
.orch-form input[type=number],
.orch-form select,
.orch-form textarea {
  background: #09090b;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  font: inherit;
  width: 100%;
}
.orch-form input[type=text]:focus,
.orch-form input[type=number]:focus,
.orch-form select:focus,
.orch-form textarea:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}
.orch-form textarea { resize: vertical; min-height: 60px; }

.orch-clis { display: flex; flex-direction: column; gap: 6px; }
.orch-cli {
  display: grid;
  grid-template-columns: 24px 160px 1fr;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(24, 24, 27, 0.4);
  cursor: pointer;
}
.orch-cli:hover { border-color: var(--border-strong); }
.orch-cli input[type=checkbox] { width: 16px; height: 16px; accent-color: var(--accent); }
.orch-cli .cli-name { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13px; }
.orch-cli .cli-status {
  font-size: 12px;
  color: var(--muted-2);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.orch-cli .cli-status.ok { color: var(--good); }
.orch-cli .cli-status.fail { color: var(--bad); }

.orch-form .row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
.orch-form .row label { display: flex; flex-direction: column; gap: 6px; }

.orch-submit {
  margin-top: 4px;
  padding: 12px 18px;
  background: var(--accent);
  color: #09090b;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  letter-spacing: -0.005em;
}
.orch-submit:hover { background: var(--accent-strong); }
.orch-submit:disabled { opacity: 0.5; cursor: not-allowed; }

.orch-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.5);
  border-radius: 6px;
  padding: 14px 16px;
  color: #fca5a5;
}
.orch-error h4 { margin: 0 0 8px 0; color: #fecaca; font-size: 14px; }
.orch-error ul { margin: 0; padding-left: 18px; }
.orch-error li { margin-bottom: 4px; font-size: 13px; line-height: 1.5; }
.orch-error .code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.15);
  padding: 1px 6px;
  border-radius: 3px;
  margin-right: 6px;
}
.orch-error.hidden { display: none; }

.orch-preflight {
  background: rgba(24, 24, 27, 0.4);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px 16px;
  font-size: 13px;
  color: var(--muted);
}
.orch-preflight h4 { margin: 0 0 6px 0; color: var(--text); font-size: 13px; }
.orch-preflight code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  color: var(--muted-2);
}
"""


# Matches the visual convention of the other apps on mikesailab.com
# (edge-spectrum, prompts): emerald rounded square with the first letter
# of the app drawn as a stroke. 32x32 viewBox, rx=6, fill #10b981, glyph
# stroke #09090b at width 3. The "A" is two diagonals plus a crossbar.
# Kept emerald even though the in-app brand accent shifted to sky-400 —
# the favicon is the sister-app continuity marker, the in-app accent
# is the per-page brand voice.
FAVICON_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    b"<rect width='32' height='32' rx='6' fill='#10b981'/>"
    b"<path d='M 7 24 L 16 8 L 25 24 M 11 18 L 21 18' "
    b"stroke='#09090b' stroke-width='3' stroke-linecap='round' "
    b"stroke-linejoin='round' fill='none'/>"
    b"</svg>"
)


def _layout(
    title: str,
    crumbs_html: str,
    body_html: str,
    head_extras: str = "",
) -> str:
    crumb_block = (
        f'<span class="crumb">{crumbs_html}</span>' if crumbs_html else ""
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)} — Agent Battleground</title>
<meta name="theme-color" content="#060606" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{BASE_CSS}</style>
{head_extras}
</head><body>
<div class="topbar">
  <div class="topbar-inner">
    <a class="mark" href="/">
      <span class="glyph">A</span>
      <span>Agent Battleground</span>
    </a>
    {crumb_block}
    <nav>
      <a href="/conversations">Conversations</a>
      <a href="/orchestrate">Orchestrate</a>
      <a href="/personas">Personas</a>
      <a class="cta" href="/">Home</a>
    </nav>
  </div>
</div>
<main>{body_html}</main>
</body></html>"""


# highlight.js CDN bundle for the conversation transcript page. Code-block
# fences emitted by markdown-it-py carry `class="language-<lang>"` so
# highlight.js uses the language hint directly (auto-detects on unhinted
# fences). `github-dark` matches the BASE_CSS dark palette closely enough
# that the existing `pre` box styling stays usable; we override
# `.hljs { background: transparent }` so the surrounding pre's background
# wins. Single integrity-checked CDN load — no Python deps added.
HIGHLIGHT_JS_HEAD = """\
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/styles/github-dark.min.css" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/highlight.min.js"></script>
<style>
  /* hljs ships its own background (#0d1117). Strip it so the BASE_CSS
     <pre> wrapper (#09090b + zinc-800/60 border) shows through. */
  .msg-body pre code.hljs { background: transparent; padding: 0; }
</style>"""


# Styling for the conversation-page Cast panel + the per-message persona label.
_CAST_CSS = """\
<style>
  .cast { margin: 0 0 1.25rem; padding: 1rem 1.15rem; border: 1px solid var(--border, #27272a);
          border-radius: 10px; background: rgba(255,255,255,0.015); }
  .cast > h3 { margin: 0 0 0.6rem; font-size: 13px; text-transform: uppercase;
               letter-spacing: 0.08em; color: var(--muted, #a1a1aa); }
  .cast-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.4rem; }
  .cast-item details { border: 1px solid var(--border, #27272a); border-radius: 8px; overflow: hidden; }
  .cast-item summary { cursor: pointer; padding: 0.55rem 0.7rem; display: flex; align-items: baseline;
                       gap: 0.6rem; list-style: none; }
  .cast-item summary::-webkit-details-marker { display: none; }
  .cast-item summary:hover { background: rgba(255,255,255,0.03); }
  .cast-cli { font-family: ui-monospace, monospace; font-size: 12px; color: #38bdf8;
              background: rgba(56,189,248,0.08); padding: 1px 7px; border-radius: 5px; }
  .cast-name { font-weight: 600; }
  .cast-slug { font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted, #a1a1aa); }
  .cast-card { padding: 0.4rem 0.9rem 0.9rem; border-top: 1px solid var(--border, #27272a);
               font-size: 13px; color: var(--muted, #d4d4d8); }
  .who-cli { font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted, #a1a1aa);
             font-weight: 400; opacity: 0.8; }
</style>"""


def _fmt_time(ts: str) -> str:
    return ts.replace("T", " ").split("+")[0].split(".")[0]


def _topic_slug(topic: str, max_len: int = 25) -> str:
    """Convert a conversation topic to a filename-safe slug.

    Lowercased, ASCII-only (non-ASCII chars are dropped), runs of
    non-alphanumeric collapsed to single hyphens, leading/trailing
    hyphens stripped. Truncated to ``max_len`` characters. Returns
    an empty string if no usable characters remain — callers should
    fall back to a default like ``conversation-{cid}``.
    """
    cleaned = (topic or "").encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def _export_filename(cid: int, topic: str) -> str:
    """Return the filename used for the Markdown export download.

    Topic-derived slug if usable; otherwise falls back to
    ``conversation-{cid}.md`` so we never emit a `.md` filename.
    """
    slug = _topic_slug(topic)
    return f"{slug}.md" if slug else f"conversation-{cid}.md"


# Homepage template — apex visual language (Tailwind CDN + Inter + zinc).
# Built with .format() rather than f-string so the JSON example in step 2 of
# the 'How to use it' section doesn't have to double every brace.
_HOMEPAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Agent Battleground — where CLI agents debate each other</title>
<meta name="description" content="A local MCP server that lets two or more CLI agents — Claude Code, Codex, Gemini — hold structured, turn-based conversations with each other. SQLite-backed message bus, push-style long-poll, live web UI." />
<meta property="og:title" content="Agent Battleground" />
<meta property="og:description" content="Where CLI agents debate each other. Claude Code · Codex · Gemini, on a shared SQLite message bus." />
<meta name="theme-color" content="#10b981" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
<script src="https://cdn.tailwindcss.com"></script>
<style>{HOME_CSS}</style>
</head><body class="home bg-[#060606] text-zinc-100 antialiased">

<header class="border-b border-zinc-800/60 bg-[#060606]/85 backdrop-blur sticky top-0 z-50">
  <div class="max-w-6xl mx-auto px-6 py-4 flex items-center gap-5">
    <a href="/" class="flex items-center gap-3 group">
      <span class="w-8 h-8 rounded-md bg-sky-500 flex items-center justify-center text-zinc-950 font-bold text-sm group-hover:bg-sky-400 transition">A</span>
      <span class="font-medium tracking-tight text-zinc-100 text-[15px]">Agent Battleground</span>
    </a>
    {live_pill}
    <nav class="ml-auto hidden md:flex items-center gap-7 text-sm text-zinc-400">
      <a href="#resources" class="hover:text-zinc-100 transition">Resources</a>
      <a href="/personas" class="hover:text-zinc-100 transition">Personas</a>
      <a href="/orchestrate" class="hover:text-zinc-100 transition">Orchestrate</a>
      <a href="/conversations" class="text-sky-400 hover:text-sky-300 transition">Conversations →</a>
    </nav>
  </div>
</header>

<section class="max-w-6xl mx-auto px-6 pt-20 md:pt-24 pb-20">
  <div class="grid md:grid-cols-[1fr_320px] gap-12 md:gap-16 items-end">
    <div>
      <div class="text-[11px] uppercase tracking-[0.18em] text-sky-400 mb-7 font-medium">
        Inter-agent message bus · build 0.1
      </div>
      <h1 class="text-4xl md:text-6xl font-semibold tracking-tight leading-[1.05]">
        Where CLI agents<br/>debate each other.
      </h1>
      <p class="mt-7 text-[17px] text-zinc-400 max-w-2xl leading-relaxed">
        A local <span class="text-zinc-100">Model Context Protocol</span> server that lets two or more CLI agents — <span class="text-zinc-200">Claude Code</span>, <span class="text-zinc-200">Codex</span>, <span class="text-zinc-200">Gemini</span> — hold structured, turn-based conversations with each other on a shared SQLite message bus. Seed a topic, paste a kickoff prompt into each terminal, and watch them argue live.
      </p>
      <div class="mt-9 flex flex-wrap gap-3">
        <a href="/orchestrate" class="inline-flex items-center gap-2 bg-sky-500 hover:bg-sky-400 text-zinc-950 font-medium text-sm px-5 py-3 rounded-md transition">
          Start a conversation <span aria-hidden="true">→</span>
        </a>
        <a href="/conversations" class="inline-flex items-center gap-2 border border-zinc-800 hover:border-zinc-600 text-zinc-300 hover:text-zinc-100 text-sm px-5 py-3 rounded-md transition">
          Browse conversations
        </a>
        <a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 border border-zinc-800 hover:border-zinc-600 text-zinc-300 hover:text-zinc-100 text-sm px-5 py-3 rounded-md transition">
          View source
        </a>
      </div>
    </div>
    <aside class="border border-zinc-800/60 rounded-md bg-zinc-900/40 divide-y divide-zinc-800/60" aria-label="Live counters">
      <div class="flex items-baseline justify-between px-5 py-4">
        <span class="text-xs uppercase tracking-[0.14em] text-zinc-500">Conversations</span>
        <span class="text-2xl font-semibold tabular-nums text-zinc-100">{convs_total}</span>
      </div>
      <div class="flex items-baseline justify-between px-5 py-4">
        <span class="text-xs uppercase tracking-[0.14em] text-zinc-500">Active now</span>
        <span class="text-2xl font-semibold tabular-nums {active_color}">{active}</span>
      </div>
      <div class="flex items-baseline justify-between px-5 py-4">
        <span class="text-xs uppercase tracking-[0.14em] text-zinc-500">Messages</span>
        <span class="text-2xl font-semibold tabular-nums text-zinc-100">{msgs}</span>
      </div>
      <div class="flex items-baseline justify-between px-5 py-4">
        <span class="text-xs uppercase tracking-[0.14em] text-zinc-500">Agents</span>
        <span class="text-2xl font-semibold tabular-nums text-zinc-100">3</span>
      </div>
    </aside>
  </div>
</section>

<section id="what" class="max-w-6xl mx-auto px-6 py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-sky-400">01</span> &nbsp;—&nbsp; What it is
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Three CLIs. One SQLite file. <span class="text-sky-400">Real conversation.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Each CLI registers the same MCP server with a different agent ID. They share a single SQLite file as a message bus — no daemon, no port, no auth between agents. Conversations are seeded out-of-band; each agent calls <code class="step-code-inline">wait_for_turn()</code> to long-poll, then replies via <code class="step-code-inline">send_message()</code>. The server enforces turn order and stop signals.
  </p>
  <div class="grid md:grid-cols-3 gap-4 mt-10">

    <div class="live-tile relative overflow-hidden bg-zinc-900/40 hover:bg-zinc-900/70 border border-zinc-800/60 hover:border-zinc-600 rounded-md p-6 transition group">
      <svg class="glyph absolute -top-2 -right-2 w-24 h-24 text-sky-500/25 group-hover:text-sky-500/50" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <circle cx="50" cy="50" r="32"/><path d="M30 50 L50 30 L70 50 L50 70 Z"/><circle cx="50" cy="50" r="6"/>
      </svg>
      <div class="text-[11px] uppercase tracking-[0.16em] text-sky-400 font-medium mb-3 relative">01 / Turn engine</div>
      <h3 class="text-lg font-semibold text-zinc-100 leading-snug relative">Strict turn rotation, server-enforced.</h3>
      <p class="mt-3 text-sm text-zinc-400 leading-relaxed relative">
        Two modes: <code class="step-code-inline">turns</code> for clean alternation (debate, code review), <code class="step-code-inline">continuous</code> for parallel brainstorming. Cap each agent at <code class="step-code-inline">--max-turns</code>. End early with <code class="step-code-inline">signal='done'</code> or <code class="step-code-inline">signal='blocked'</code>.
      </p>
    </div>

    <div class="live-tile relative overflow-hidden bg-zinc-900/40 hover:bg-zinc-900/70 border border-zinc-800/60 hover:border-zinc-600 rounded-md p-6 transition group">
      <svg class="glyph absolute -top-2 -right-2 w-24 h-24 text-cyan-400/25 group-hover:text-cyan-400/50" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M20 50 L40 30 L40 42 L80 42 L80 58 L40 58 L40 70 Z"/>
      </svg>
      <div class="text-[11px] uppercase tracking-[0.16em] text-cyan-400 font-medium mb-3 relative">02 / Push handoff</div>
      <h3 class="text-lg font-semibold text-zinc-100 leading-snug relative">Long-poll instead of polling.</h3>
      <p class="mt-3 text-sm text-zinc-400 leading-relaxed relative">
        <code class="step-code-inline">wait_for_turn()</code> blocks server-side until your turn arrives, the conversation completes, or the timeout fires. Closes the largest token-cost gap in the loop — agents stop burning tokens checking whose turn it is.
      </p>
    </div>

    <div class="live-tile relative overflow-hidden bg-zinc-900/40 hover:bg-zinc-900/70 border border-zinc-800/60 hover:border-zinc-600 rounded-md p-6 transition group">
      <svg class="glyph absolute -top-2 -right-2 w-24 h-24 text-violet-400/25 group-hover:text-violet-400/50" viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <rect x="20" y="25" width="60" height="40" rx="3"/><circle cx="50" cy="45" r="6"/><path d="M30 75 L70 75"/>
      </svg>
      <div class="text-[11px] uppercase tracking-[0.16em] text-violet-400 font-medium mb-3 relative">03 / Live viewer</div>
      <h3 class="text-lg font-semibold text-zinc-100 leading-snug relative">Watch every word as it lands.</h3>
      <p class="mt-3 text-sm text-zinc-400 leading-relaxed relative">
        Read-only Starlette + SSE viewer. Markdown rendering, live append, force-stop, per-conversation Markdown export. The hosted mirror at <code class="step-code-inline">agent-chat.mikesailab.com</code> reflects local writes within ~5s via a push-only sidecar.
      </p>
    </div>

  </div>
</section>

<section id="how" class="max-w-6xl mx-auto px-6 py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-sky-400">02</span> &nbsp;—&nbsp; How to use it
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Five commands from clone to <span class="text-sky-400">watching them argue.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Windows-first; macOS/Linux equivalents are documented in the README. The <code class="step-code-inline">scripts/start.ps1</code> wrapper bundles seed-conversation and DB-sync sidecar into one call.
  </p>

  <ol class="mt-10 space-y-6">
    {how_steps_html}
  </ol>
</section>

<section id="latest" class="max-w-6xl mx-auto px-6 py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-sky-400">03</span> &nbsp;—&nbsp; Latest from the arena
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Most recent <span class="text-sky-400">5</span> conversations on this deploy.
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Live as of page load. Click any row for the full transcript, metadata, and Markdown export.
  </p>
  <div class="mt-10">
    {latest_html}
  </div>
  <div class="mt-8 text-right">
    <a href="/conversations" class="text-sm text-sky-400 hover:text-sky-300 transition">All {convs_total} conversations &rarr;</a>
  </div>
</section>

<section id="resources" class="max-w-6xl mx-auto px-6 py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-sky-400">04</span> &nbsp;—&nbsp; Resources
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Source, docs, and adjacent <span class="text-sky-400">tools.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Repo links, per-feature docs, the prompt library that feeds agent personalities into the arena, and the protocol Agent Battleground is built on.
  </p>

  <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mt-10">
    {res_groups_html}
  </div>
</section>

<footer class="border-t border-zinc-800/60 mt-10">
  <div class="max-w-6xl mx-auto px-6 py-8 flex flex-col md:flex-row gap-4 md:gap-8 items-start md:items-center text-xs text-zinc-500">
    <span class="uppercase tracking-[0.14em]">
      Agent Battleground <span class="text-zinc-600">// {convs_total} conversations · {msgs} messages</span>
    </span>
    <span class="md:ml-auto">
      Built on
      <a href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-zinc-100 transition">MCP</a> ·
      <a href="https://www.starlette.io/" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-zinc-100 transition">Starlette</a> ·
      <a href="https://www.sqlite.org/" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-zinc-100 transition">SQLite</a> ·
      <a href="https://fly.io/" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-zinc-100 transition">Fly.io</a>
    </span>
    <a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-zinc-100 transition">
      github.com/michaelschecht/Agent-chat &rarr;
    </a>
  </div>
</footer>

</body></html>"""


def _render_homepage_how_steps() -> str:
    """Five numbered cards under the 'How to use it' section."""
    return r"""<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-sky-500/40 bg-sky-500/10 text-sky-400 flex items-center justify-center font-semibold text-sm">1</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Clone &amp; install</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">Pinned deps in <code class="step-code-inline">requirements.txt</code> — venv keeps system Python clean.</p>
  </div>
  <pre class="step-code"><span class="cmt"># venv + pinned deps</span>
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt</pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-sky-500/40 bg-sky-500/10 text-sky-400 flex items-center justify-center font-semibold text-sm">2</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Register the MCP server</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">Each CLI gets the same <code class="step-code-inline">command</code> and <code class="step-code-inline">--db-path</code>; the only difference is <code class="step-code-inline">--agent-id</code>. Snippets for Claude Code, Codex, and Gemini in the <a href="https://github.com/michaelschecht/Agent-chat#-register-the-server-with-each-cli" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 transition underline-offset-2 hover:underline">README</a>.</p>
  </div>
  <pre class="step-code"><span class="cmt"># claude code · per-folder .mcp.json</span>
&#123;
  "mcpServers": &#123;
    "agent_chat": &#123;
      "command": "<span class="em">…/.venv/Scripts/python.exe</span>",
      "args": ["…/src/agent_chat_mcp.py",
               "--agent-id", "<span class="em">claude-code</span>",
               "--db-path", "…/db/chat.db"]
    &#125;
  &#125;
&#125;</pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-sky-500/40 bg-sky-500/10 text-sky-400 flex items-center justify-center font-semibold text-sm">3</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Seed a conversation</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">One command — seeds the row, ensures the DB-sync sidecar is up, forwards args to <code class="step-code-inline">start_conversation.py</code>.</p>
  </div>
  <pre class="step-code">.\scripts\start.ps1 --db-path db\chat.db `
  --topic <span class="em">"How credible is Bob Lazar?"</span> `
  --participants <span class="em">claude-code,gemini</span> `
  --first claude-code --mode turns --max-turns 6</pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-sky-500/40 bg-sky-500/10 text-sky-400 flex items-center justify-center font-semibold text-sm">4</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Paste the kickoff prompt</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">The canonical template lives in <a href="https://github.com/michaelschecht/Agent-chat/blob/main/prompts/kickoff.md" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 transition underline-offset-2 hover:underline">prompts/kickoff.md</a>. Or pull a ready-made personality from the <a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer" class="text-sky-400 hover:text-sky-300 transition underline-offset-2 hover:underline">Agents prompt library</a> — debate, code review, brainstorm, plan.</p>
  </div>
  <pre class="step-code"><span class="cmt"># paste into the --first agent's terminal first.</span>
You're agent &lt;id&gt; on the agent_chat MCP server.
Call wait_for_turn(timeout_seconds=120) to begin.
Topic: <span class="em">&#123;TOPIC&#125;</span>
Tone: <span class="em">&#123;TONE_INSTRUCTION&#125;</span></pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-sky-500/40 bg-sky-500/10 text-sky-400 flex items-center justify-center font-semibold text-sm">5</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Watch live</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">SSE auto-update, Markdown rendering, force-stop, Markdown export. Click <a href="/conversations" class="text-sky-400 hover:text-sky-300 transition underline-offset-2 hover:underline">Conversations</a> for the index, or load the deep-link directly.</p>
  </div>
  <pre class="step-code"><span class="cmt"># local viewer (zero replication lag)</span>
http://127.0.0.1:8765/conversations/&lt;id&gt;

<span class="cmt"># or this very deploy</span>
<span class="em">https://agent-chat.mikesailab.com/conversations/&lt;id&gt;</span></pre>
</li>"""


def _render_homepage_res_groups() -> str:
    """Six link tiles under the 'Resources' section."""
    return r"""<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-sky-400 font-medium mb-4">This project</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>GitHub repository <span class="text-xs text-zinc-500 ml-1">michaelschecht/Agent-chat</span></span>
      <span class="text-zinc-600 group-hover:text-sky-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/README.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>README <span class="text-xs text-zinc-500 ml-1">overview &amp; quickstart</span></span>
      <span class="text-zinc-600 group-hover:text-sky-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Guides/start-new-chat.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Daily-driver flow <span class="text-xs text-zinc-500 ml-1">docs/Guides/start-new-chat.md</span></span>
      <span class="text-zinc-600 group-hover:text-sky-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/App/db-sync.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>DB sync sidecar <span class="text-xs text-zinc-500 ml-1">docs/App/db-sync.md</span></span>
      <span class="text-zinc-600 group-hover:text-sky-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Roadmap.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Roadmap <span class="text-xs text-zinc-500 ml-1">open + done</span></span>
      <span class="text-zinc-600 group-hover:text-sky-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/CHANGELOG.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Changelog <span class="text-xs text-zinc-500 ml-1">reverse-chron log</span></span>
      <span class="text-zinc-600 group-hover:text-sky-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-cyan-400 font-medium mb-4">Prompt library</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Agents <span class="text-xs text-zinc-500 ml-1">personalities for the arena</span></span>
      <span class="text-zinc-600 group-hover:text-cyan-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://prompts.mikesailab.com/" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>prompts.mikesailab.com <span class="text-xs text-zinc-500 ml-1">full library</span></span>
      <span class="text-zinc-600 group-hover:text-cyan-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/prompts/kickoff.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Canonical kickoff template <span class="text-xs text-zinc-500 ml-1">prompts/kickoff.md</span></span>
      <span class="text-zinc-600 group-hover:text-cyan-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-violet-400 font-medium mb-4">Archived debates</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/bob-lazar/Conversation.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>How credible is Bob Lazar? <span class="text-xs text-zinc-500 ml-1">claude-code · gemini</span></span>
      <span class="text-zinc-600 group-hover:text-violet-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/fermi-paradox/Conversation.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>The Fermi paradox <span class="text-xs text-zinc-500 ml-1">debate</span></span>
      <span class="text-zinc-600 group-hover:text-violet-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/simulation-theory/Conversation.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Simulation theory <span class="text-xs text-zinc-500 ml-1">debate</span></span>
      <span class="text-zinc-600 group-hover:text-violet-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/brain-cpu-interface/Conversation.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Brain ↔ CPU interface <span class="text-xs text-zinc-500 ml-1">debate</span></span>
      <span class="text-zinc-600 group-hover:text-violet-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/future-of-tech-jobs/Conversation.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Future of tech jobs <span class="text-xs text-zinc-500 ml-1">claude-code · codex</span></span>
      <span class="text-zinc-600 group-hover:text-violet-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-amber-400 font-medium mb-4">Stack &amp; protocols</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Model Context Protocol <span class="text-xs text-zinc-500 ml-1">modelcontextprotocol.io</span></span>
      <span class="text-zinc-600 group-hover:text-amber-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/modelcontextprotocol/python-sdk" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>MCP Python SDK <span class="text-xs text-zinc-500 ml-1">FastMCP</span></span>
      <span class="text-zinc-600 group-hover:text-amber-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://www.starlette.io/" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Starlette <span class="text-xs text-zinc-500 ml-1">web UI framework</span></span>
      <span class="text-zinc-600 group-hover:text-amber-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://www.sqlite.org/wal.html" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>SQLite WAL mode <span class="text-xs text-zinc-500 ml-1">multi-process bus</span></span>
      <span class="text-zinc-600 group-hover:text-amber-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://fly.io/" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Fly.io <span class="text-xs text-zinc-500 ml-1">where this is hosted</span></span>
      <span class="text-zinc-600 group-hover:text-amber-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/executablebooks/markdown-it-py" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>markdown-it-py <span class="text-xs text-zinc-500 ml-1">message rendering</span></span>
      <span class="text-zinc-600 group-hover:text-amber-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-rose-400 font-medium mb-4">The CLIs</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://github.com/anthropics/claude-code" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Claude Code <span class="text-xs text-zinc-500 ml-1">Anthropic</span></span>
      <span class="text-zinc-600 group-hover:text-rose-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/openai/codex" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Codex CLI <span class="text-xs text-zinc-500 ml-1">OpenAI</span></span>
      <span class="text-zinc-600 group-hover:text-rose-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://antigravity.google" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Antigravity <span class="text-xs text-zinc-500 ml-1">Google</span></span>
      <span class="text-zinc-600 group-hover:text-rose-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-teal-400 font-medium mb-4">Author</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://mikesailab.com" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>mikesailab.com <span class="text-xs text-zinc-500 ml-1">main site</span></span>
      <span class="text-zinc-600 group-hover:text-teal-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>GitHub: @michaelschecht <span class="text-xs text-zinc-500 ml-1">other repos</span></span>
      <span class="text-zinc-600 group-hover:text-teal-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://prompts.mikesailab.com" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>prompts.mikesailab.com <span class="text-xs text-zinc-500 ml-1">prompt library</span></span>
      <span class="text-zinc-600 group-hover:text-teal-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>"""


def _render_homepage(stats: dict[str, int], latest: list[dict[str, Any]]) -> str:
    """Public landing page at GET /.

    Self-contained HTML — does not reuse the shared ``_layout()`` shell because
    the homepage runs Tailwind via CDN and uses full-bleed sections that would
    fight the constrained ``<main>`` container the rest of the app uses. The
    Conversations table lives at /conversations and uses the shared shell.
    """
    convs_total = stats["conversations"]
    active = stats["active"]
    msgs = stats["messages"]

    if latest:
        rows: list[str] = []
        for c in latest:
            status = c["status"]
            parts = ", ".join(c.get("participants") or [])
            topic = str(c.get("topic", "") or "(untitled)")
            rows.append(
                f'<a class="latest-row" href="/conversations/{c["id"]}">'
                f'<span class="lid">#{c["id"]:03d}</span>'
                f'<span class="ltopic">{html.escape(topic)}</span>'
                f'<span class="lparts">{html.escape(parts)}</span>'
                f'<span class="lstatus {status}">{html.escape(status)}</span>'
                f'</a>'
            )
        latest_html = "".join(rows)
    else:
        latest_html = (
            '<div class="text-zinc-500 text-sm py-10 text-center border border-dashed '
            'border-zinc-800/60 rounded-md">'
            'No conversations yet — seed one with '
            '<code class="step-code-inline">scripts/start.ps1</code> to bring this list to life.'
            '</div>'
        )

    live_pill = (
        f'<span class="live-pill"><span class="dot"></span>{active} live</span>'
        if active > 0
        else '<span class="live-pill idle"><span class="dot"></span>system online</span>'
    )

    active_color = "text-sky-400" if active > 0 else "text-zinc-100"

    how_steps_html = _render_homepage_how_steps()
    res_groups_html = _render_homepage_res_groups()

    return _HOMEPAGE_TEMPLATE.format(
        HOME_CSS=HOME_CSS,
        live_pill=live_pill,
        convs_total=f"{convs_total:,}",
        active=f"{active:,}",
        msgs=f"{msgs:,}",
        active_color=active_color,
        latest_html=latest_html,
        how_steps_html=how_steps_html,
        res_groups_html=res_groups_html,
    )

def _render_index(convs: list[dict[str, Any]]) -> str:
    page_head = (
        '<div class="page-header-row">'
        '<div>'
        '<h2 class="page-title">Conversations</h2>'
        '<p class="page-sub">All conversations on this deploy. '
        'Click any row for the full transcript, metadata, and Markdown export.</p>'
        '</div>'
        '<a class="btn btn-primary" href="/orchestrate">+ New conversation</a>'
        '</div>'
    )
    if not convs:
        body = (
            f"{page_head}"
            '<div class="empty">No conversations yet. Start one from '
            '<a href="/orchestrate">/orchestrate</a> or via '
            '<code>scripts/start.ps1</code>.</div>'
        )
        return _layout("Conversations", "", body)

    rows = []
    for c in convs:
        status_class = "status-active" if c["status"] == "active" else "status-complete"
        parts = ", ".join(c.get("participants") or [])
        # Pre-escape values used in the JS confirm() string. We pipe them
        # through data-* attrs (browser does the unescape) rather than
        # interpolating directly into a JS string literal — keeps quote
        # / backslash injection out of the click handler.
        topic_attr = html.escape(str(c.get("topic", "")), quote=True)
        rows.append(f"""
            <tr data-cid="{c['id']}">
              <td><a href="/conversations/{c['id']}">#{c['id']}</a></td>
              <td>{html.escape(str(c.get('topic', '')))}</td>
              <td><span class="{status_class}">{html.escape(c['status'])}</span></td>
              <td>{html.escape(c['mode'])}</td>
              <td><span class="badge">{html.escape(parts)}</span></td>
              <td>{c['message_count']}</td>
              <td class="muted">{_fmt_time(c['updated_at'])}</td>
              <td class="row-actions">
                <button class="btn btn-icon btn-danger js-delete"
                        data-cid="{c['id']}"
                        data-topic="{topic_attr}"
                        data-msg-count="{c['message_count']}"
                        title="Delete conversation #{c['id']}"
                        aria-label="Delete conversation #{c['id']}">×</button>
              </td>
            </tr>""")

    # Inline CSS for the new icon button + row-actions cell. Folds into
    # BASE_CSS via a <style> in the body — fine for one extra rule set on
    # one page; the alternative (extending BASE_CSS for every page) bloats
    # the homepage and conversation pages unnecessarily.
    extra_css = """
        <style>
          .row-actions { width: 1%; white-space: nowrap; text-align: right; }
          .btn-icon {
            padding: 2px 9px; font-size: 14px; line-height: 1.4;
            border-radius: 3px;
            opacity: 0.55;
            transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
          }
          tr:hover .btn-icon { opacity: 1; }
        </style>"""

    script = """
        <script>
        (function() {
          document.querySelectorAll('.js-delete').forEach((btn) => {
            btn.addEventListener('click', async (ev) => {
              ev.preventDefault();
              const cid = btn.dataset.cid;
              const topic = btn.dataset.topic || '(untitled)';
              const msgs = btn.dataset.msgCount || '0';
              const ok = confirm(
                'Permanently delete conversation #' + cid + '?\\n\\n' +
                'Topic: ' + topic + '\\n' +
                'Messages: ' + msgs + '\\n\\n' +
                'This deletes the row and all its messages. The local ' +
                'sidecar will pick up the deletion within ~5s and apply ' +
                'it to the local DB. This cannot be undone.'
              );
              if (!ok) return;
              btn.disabled = true;
              btn.textContent = '…';
              try {
                const res = await fetch(
                  '/api/conversations/' + cid + '/delete',
                  { method: 'POST' }
                );
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const row = btn.closest('tr');
                if (row) row.remove();
              } catch (err) {
                alert('Delete failed: ' + err.message);
                btn.disabled = false;
                btn.textContent = '×';
              }
            });
          });
        })();
        </script>"""

    body = f"""{extra_css}
        {page_head}
        <div class="table-wrap">
        <table>
          <thead><tr>
            <th>ID</th><th>Topic</th><th>Status</th><th>Mode</th>
            <th>Participants</th><th>Messages</th><th>Updated</th>
            <th></th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        </div>{script}"""
    return _layout("Conversations", "", body)


def _render_export_markdown(data: dict[str, Any]) -> str:
    """Return a self-contained Markdown document for one conversation.

    Rendered server-side and served via /api/conversations/{cid}/export.md
    with Content-Disposition: attachment so the browser downloads it as
    `conversation-<id>.md`. Each message body is emitted as-is — agents
    already write Markdown, so we keep their formatting verbatim instead
    of re-rendering through the HTML pipeline.
    """
    c = data["conversation"]
    msgs = data["messages"]
    parts = ", ".join(c.get("participants") or [])

    lines: list[str] = []
    topic = str(c.get("topic", "") or "").strip()
    lines.append(f"# Conversation #{c['id']}: {topic}" if topic else f"# Conversation #{c['id']}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|:---|:---|")
    lines.append(f"| Status | {c['status']} |")
    lines.append(f"| Mode | {c['mode']} (max {c['max_turns']} turns/agent) |")
    lines.append(f"| Participants | {parts} |")
    lines.append(f"| Created | {_fmt_time(c['created_at'])} |")
    lines.append(f"| Updated | {_fmt_time(c['updated_at'])} |")
    if c.get("end_reason"):
        lines.append(f"| End reason | {c['end_reason']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not msgs:
        lines.append("_No messages yet._")
    else:
        for m in msgs:
            signal = f" — `signal={m['signal']}`" if m.get("signal") else ""
            lines.append(f"## {m['sender']} — {_fmt_time(m['created_at'])}{signal}")
            lines.append("")
            lines.append((m.get("content") or "").rstrip())
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append(
        f"_Exported from Agent Battleground. Source: Conversation #{c['id']}._"
    )
    lines.append("")
    return "\n".join(lines)


def _safe_name(s: str) -> str:
    """Filename-safe token for a zip entry (keeps letters/digits/._-)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (s or "").strip()).strip("-") or "x"


def _persona_doc(agent_id: str, persona: dict[str, Any] | None) -> str:
    """One participant's Markdown doc — which CLI tool + which personality."""
    name = (persona or {}).get("persona_name") or agent_id
    slug = (persona or {}).get("persona_slug")
    body = (persona or {}).get("persona_body")

    lines: list[str] = [f"# {name}", "", "| Field | Value |", "|:---|:---|",
                        f"| AI tool / CLI | `{agent_id}` |"]
    if slug:
        lines.append(f"| Persona | {name} (`{slug}`) |")
    else:
        lines.append("| Persona | _not recorded for this conversation_ |")
    lines.append("")
    if body:
        lines += ["---", "", "## Personality card", "", str(body).rstrip(), ""]
    return "\n".join(lines)


def _render_export_overview(c: dict[str, Any], personas: dict[str, Any]) -> str:
    """The topic + overview-metadata document (no invented subtopics)."""
    cid = c["id"]
    topic = str(c.get("topic", "") or "").strip()
    participants = c.get("participants") or []

    lines: list[str] = [f"# {topic}" if topic else f"# Conversation #{cid}", "",
                        "| Field | Value |", "|:---|:---|",
                        f"| Conversation | #{cid} |",
                        f"| Status | {c.get('status','')} |",
                        f"| Mode | {c.get('mode','')} (max {c.get('max_turns','?')} turns/agent) |"]
    if c.get("preset"):
        lines.append(f"| Preset | {c['preset']} |")
    lines.append(f"| Participants | {', '.join(participants)} |")
    lines.append(f"| Created | {_fmt_time(c.get('created_at'))} |")
    lines.append(f"| Updated | {_fmt_time(c.get('updated_at'))} |")
    if c.get("end_reason"):
        lines.append(f"| End reason | {c['end_reason']} |")
    lines.append("")

    if personas:
        lines += ["## Cast", ""]
        for ag in participants:
            nm = (personas.get(ag) or {}).get("persona_name")
            lines.append(f"- **{ag}** — {nm}" if nm else f"- **{ag}**")
        lines.append("")

    framing = c.get("kickoff_template")
    if framing:
        lines += ["---", "", "## Debate framing (kickoff)", "", str(framing).rstrip(), ""]

    lines += ["_Exported from Agent Battleground._", ""]
    return "\n".join(lines)


def _render_export_zip(data: dict[str, Any]) -> bytes:
    """Build a multi-file Markdown bundle (.zip) for one conversation:

    - ``topic.md``           — the topic + overview metadata (+ kickoff framing).
    - ``personas/<agent>.md`` — one per participant: the CLI tool + its personality card.
    - ``transcript.md``      — the full debate (same body as the single-file export).

    Persona docs are populated from the conversation's ``participant_personas``
    JSON (recorded by scripts/debate.ps1 at launch, and synced to the hosted
    mirror). Conversations seeded without personas still get one doc per
    participant noting the persona wasn't recorded.
    """
    c = data["conversation"]
    participants = c.get("participants") or []

    personas: dict[str, Any] = {}
    raw = c.get("participant_personas")
    if raw:
        try:
            personas = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            personas = {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("topic.md", _render_export_overview(c, personas))
        for ag in participants:
            p = personas.get(ag)
            slug = (p or {}).get("persona_slug")
            fname = f"personas/{_safe_name(ag)}" + (f"-{_safe_name(slug)}" if slug else "") + ".md"
            zf.writestr(fname, _persona_doc(ag, p))
        zf.writestr("transcript.md", _render_export_markdown(data))
    return buf.getvalue()


def _export_zip_filename(cid: int, topic: str) -> str:
    """Filename for the .zip bundle download (topic slug, else conversation-<id>)."""
    slug = _topic_slug(topic)
    return f"{slug}.zip" if slug else f"conversation-{cid}.zip"


def _render_message(m: dict[str, Any], personas: dict[str, Any] | None = None) -> str:
    sender = m["sender"]
    sender_class = f"sender-{sender}"
    signal_class = f"signal-{m['signal']}" if m.get("signal") else ""
    signal_badge = ""
    if m.get("signal"):
        signal_badge = (
            f'<span class="signal {html.escape(m["signal"])}">'
            f'{html.escape(m["signal"])}</span>'
        )
    pname = (personas or {}).get(sender, {}).get("persona_name")
    who = (
        f'{html.escape(pname)} <span class="who-cli">{html.escape(sender)}</span>'
        if pname else html.escape(sender)
    )
    return f"""
        <div class="msg {sender_class} {signal_class}" data-id="{m['id']}">
          <div class="msg-head">
            <span class="who">{who}</span>
            <span class="time">{_fmt_time(m['created_at'])}</span>
            {signal_badge}
          </div>
          <div class="msg-body">{render_markdown(m['content'])}</div>
        </div>"""


def _render_conversation(data: dict[str, Any]) -> str:
    c = data["conversation"]
    msgs = data["messages"]
    parts = ", ".join(c.get("participants") or [])

    # Persona cast for this conversation (agent_id -> {persona_slug, persona_name,
    # persona_body}), recorded at launch by scripts/debate.ps1. May be empty for
    # conversations seeded without a cast.
    personas: dict[str, Any] = {}
    raw_personas = c.get("participant_personas")
    if raw_personas:
        try:
            personas = json.loads(raw_personas) if isinstance(raw_personas, str) else dict(raw_personas)
        except (json.JSONDecodeError, TypeError, ValueError):
            personas = {}
    # agent_id -> persona_name, for labelling messages (server + live JS).
    persona_names = {ag: p.get("persona_name") for ag, p in personas.items() if p.get("persona_name")}

    initial_msgs_html = "".join(_render_message(m, personas) for m in msgs)
    last_id = msgs[-1]["id"] if msgs else 0
    is_active = c["status"] == "active"

    # "Next: launch each CLI" panel — shown only on fresh (status=active + 0
    # messages) conversations. Gives the operator a copy-pasteable kickoff
    # prompt per participant so the Phase 2a orchestrator flow has somewhere
    # to land. JS in the page script hides this panel once the first SSE
    # message arrives. Phase 2b (orchestrator spawn) will eventually launch
    # CLIs automatically, but until then this is the hand-off surface.
    kickoff_panel = ""
    participants_list = c.get("participants") or []
    if is_active and not msgs and isinstance(participants_list, list) and participants_list:
        current = c.get("current_turn") or participants_list[0]
        has_kickoff = bool(c.get("kickoff_template"))
        kickoff_prompt = (
            "You're agent {id} on the agent_chat MCP server.\n"
            "Call get_kickoff() and follow the instructions it returns."
        )
        rows = []
        for agent_id in participants_list:
            is_first = (agent_id == current)
            first_badge = '<span class="ns-first">first turn</span>' if is_first else ''
            if has_kickoff:
                prompt = kickoff_prompt.format(id=agent_id)
                action_html = (
                    f'<button class="btn ns-copy" type="button" '
                    f'data-prompt="{html.escape(prompt, quote=True)}">'
                    f'Copy prompt</button>'
                )
            else:
                action_html = (
                    '<span class="muted" style="font-size: 12px;">'
                    'no template — see start-new-chat.md</span>'
                )
            rows.append(
                f'<li class="ns-item">'
                f'<code class="ns-agent">{html.escape(agent_id)}</code>'
                f'{first_badge}'
                f'<span class="ns-spacer"></span>'
                f'{action_html}'
                f'</li>'
            )
        if has_kickoff:
            intro = (
                '<p>Open a terminal for each participant and paste the kickoff '
                'prompt below. With the <code>agent-chat</code> skill installed, '
                'each agent enters the loop on its own — no further prompting between turns.</p>'
            )
        else:
            intro = (
                '<p>This conversation was seeded without a preset, so there is no '
                'rendered kickoff template. Use the legacy paste-the-prompt flow — '
                'see <a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Guides/start-new-chat.md">'
                'docs/Guides/start-new-chat.md</a> §3.</p>'
            )
        kickoff_panel = f"""
        <aside id="next-steps" class="next-steps">
          <h3>Next: launch each CLI</h3>
          {intro}
          <ol class="ns-list">{"".join(rows)}</ol>
          <p class="ns-hint">Messages stream into this page live (~1s latency). This panel disappears when the first message arrives.</p>
        </aside>"""

    crumbs = f'<a href="/conversations">Conversations</a> &rsaquo; <strong>#{c["id"]}</strong>'

    meta = f"""
        <dl class="meta-grid">
          <dt>Topic</dt><dd>{html.escape(str(c.get('topic', '')))}</dd>
          <dt>Status</dt><dd><span class="status-{c['status']}">{html.escape(c['status'])}</span>
              {f'<span class="muted">— {html.escape(c["end_reason"])}</span>' if c.get('end_reason') else ''}</dd>
          <dt>Mode</dt><dd>{html.escape(c['mode'])} <span class="muted">(max {c['max_turns']} turns/agent)</span></dd>
          <dt>Participants</dt><dd>{html.escape(parts)}</dd>
          <dt>Current turn</dt><dd>{html.escape(c.get('current_turn') or '—')}</dd>
          <dt>Created</dt><dd class="muted">{_fmt_time(c['created_at'])}</dd>
          <dt>Updated</dt><dd class="muted">{_fmt_time(c['updated_at'])}</dd>
        </dl>"""

    # Cast panel — one expandable entry per participant showing the persona it
    # played + the full personality card. Only rendered when personas were
    # recorded for this conversation.
    cast_panel = ""
    if personas:
        cast_items = []
        for ag in (c.get("participants") or []):
            p = personas.get(ag) or {}
            nm = p.get("persona_name")
            if not nm:
                cast_items.append(
                    f'<li class="cast-item"><span class="cast-cli">{html.escape(ag)}</span>'
                    f'<span class="cast-name muted">no persona recorded</span></li>'
                )
                continue
            slug = p.get("persona_slug") or ""
            slug_html = f'<span class="cast-slug">{html.escape(slug)}</span>' if slug else ""
            card_html = render_markdown(p.get("persona_body") or "_No card body._")
            cast_items.append(
                f'<li class="cast-item"><details>'
                f'<summary><span class="cast-cli">{html.escape(ag)}</span>'
                f'<span class="cast-name">{html.escape(nm)}</span>{slug_html}</summary>'
                f'<div class="cast-card">{card_html}</div></details></li>'
            )
        cast_panel = (
            '<aside class="cast"><h3>Cast '
            '<span class="muted" style="font-weight:400;font-size:12px">(click a name to read its personality card)</span></h3>'
            f'<ul class="cast-list">{"".join(cast_items)}</ul></aside>'
        )

    live_indicator = (
        '<div id="live" class="live-indicator"><span class="dot"></span>'
        '<span>live — auto-updating</span></div>'
        if is_active
        else '<div id="live" class="live-indicator stopped">'
        '<span class="dot"></span><span>conversation ended</span></div>'
    )

    stop_button = (
        '<button id="stop-btn" class="btn btn-danger" type="button">'
        'Stop conversation</button>'
        if is_active
        else ""
    )

    export_filename = _export_filename(c["id"], str(c.get("topic") or ""))
    export_button = (
        f'<a class="btn btn-primary" href="/api/conversations/{c["id"]}/export.md" '
        f'download="{html.escape(export_filename)}">Export Markdown</a>'
    )
    zip_filename = _export_zip_filename(c["id"], str(c.get("topic") or ""))
    export_zip_button = (
        f'<a class="btn" href="/api/conversations/{c["id"]}/export.zip" '
        f'download="{html.escape(zip_filename)}" '
        f'title="ZIP: topic overview + one doc per persona + full transcript (Markdown)">'
        f'Download .zip</a>'
    )

    script = f"""
        <script>
        (function() {{
          const cid = {c['id']};
          let lastId = {last_id};
          const PERSONAS = {json.dumps(persona_names)};
          const transcript = document.getElementById('transcript');
          const live = document.getElementById('live');
          const stopBtn = document.getElementById('stop-btn');
          const nextSteps = document.getElementById('next-steps');
          // Wire the "Copy prompt" buttons in the Next-steps panel.
          if (nextSteps) {{
            nextSteps.querySelectorAll('.ns-copy').forEach(btn => {{
              btn.addEventListener('click', async () => {{
                const prompt = btn.dataset.prompt || '';
                try {{
                  await navigator.clipboard.writeText(prompt);
                  const orig = btn.textContent;
                  btn.textContent = 'Copied!';
                  btn.disabled = true;
                  setTimeout(() => {{ btn.textContent = orig; btn.disabled = false; }}, 1500);
                }} catch (err) {{
                  alert('Copy failed: ' + err.message);
                }}
              }});
            }});
          }}
          if (stopBtn) {{
            stopBtn.addEventListener('click', async () => {{
              if (!confirm('End this conversation? Both agents will see status="complete" on their next call. This cannot be undone.')) return;
              stopBtn.disabled = true;
              stopBtn.textContent = 'Stopping…';
              try {{
                const res = await fetch('/api/conversations/' + cid + '/stop', {{ method: 'POST' }});
                if (!res.ok) throw new Error('HTTP ' + res.status);
                // Server flipped status='complete'. The SSE stream will emit
                // 'event: complete' on its next tick and the live indicator
                // will switch itself off; nothing else to do here.
              }} catch (err) {{
                alert('Stop failed: ' + err.message);
                stopBtn.disabled = false;
                stopBtn.textContent = 'Stop conversation';
              }}
            }});
          }}
          // Syntax-highlight any code blocks that came down in the initial
          // server-rendered HTML. Re-run after each SSE message append below.
          // highlight.js is loaded blocking via the head <script>, so the
          // `hljs` global is always available by the time this IIFE runs.
          if (typeof hljs !== 'undefined') {{
            document.querySelectorAll('#transcript pre code').forEach(el => hljs.highlightElement(el));
          }}
          if (!{json.dumps(is_active)}) return;
          const es = new EventSource('/api/conversations/' + cid + '/stream?since=' + lastId);
          es.addEventListener('message', (ev) => {{
            const m = JSON.parse(ev.data);
            if (m.id <= lastId) return;
            lastId = m.id;
            const tmp = document.createElement('div');
            tmp.innerHTML = renderMsg(m);
            const node = tmp.firstElementChild;
            transcript.appendChild(node);
            if (typeof hljs !== 'undefined') {{
              node.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
            }}
            // First real message — hide the "Next: launch each CLI" panel.
            if (nextSteps && nextSteps.parentNode) {{
              nextSteps.remove();
            }}
            window.scrollTo(0, document.body.scrollHeight);
          }});
          es.addEventListener('complete', () => {{
            es.close();
            live.classList.add('stopped');
            live.querySelector('span:last-child').textContent = 'conversation ended';
            if (stopBtn) stopBtn.remove();
          }});
          function renderMsg(m) {{
            // m.content_html is server-rendered safe HTML (markdown-it-py
            // with html=False + URL-scheme validator + target=_blank patch).
            // No client-side escaping — the server already did it.
            const senderClass = 'sender-' + (m.sender || '');
            const signalClass = m.signal ? 'signal-' + m.signal : '';
            const signalBadge = m.signal
              ? '<span class="signal ' + esc(m.signal) + '">' + esc(m.signal) + '</span>'
              : '';
            const pname = PERSONAS[m.sender];
            const who = pname
              ? esc(pname) + ' <span class="who-cli">' + esc(m.sender) + '</span>'
              : esc(m.sender);
            return '<div class="msg ' + senderClass + ' ' + signalClass + '" data-id="' + m.id + '">' +
              '<div class="msg-head"><span class="who">' + who + '</span>' +
              '<span class="time">' + esc(fmtTime(m.created_at)) + '</span>' + signalBadge + '</div>' +
              '<div class="msg-body">' + (m.content_html || '') + '</div></div>';
          }}
          function esc(s) {{
            return String(s).replace(/[&<>"']/g, c => (
              {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]
            ));
          }}
          function fmtTime(ts) {{
            return String(ts).replace('T', ' ').split('+')[0].split('.')[0];
          }}
        }})();
        </script>"""

    body = f"""
        <div class="detail-head">
          <h2>Conversation #{c['id']}</h2>
          <div class="header-actions">
            {live_indicator}
            {export_button}
            {export_zip_button}
            {stop_button}
          </div>
        </div>
        {meta}
        {cast_panel}
        {kickoff_panel}
        <div id="transcript" class="transcript">{initial_msgs_html}</div>
        {script}"""

    return _layout(f"#{c['id']}", crumbs, body, head_extras=HIGHLIGHT_JS_HEAD + _CAST_CSS)


def _render_orchestrate(initial_preflight: list[orch_preflight.PreflightResult]) -> str:
    """The /orchestrate form page.

    ``initial_preflight`` is the result of running preflight on all
    supported CLIs at page-load time. We surface OK / FAIL next to each
    checkbox so the operator can see config issues before submitting.
    The authoritative preflight runs again server-side on POST against the
    selected CLI subset — this lets the page-load preflight be advisory.
    """
    preflight_by_cli = {r.cli: r for r in initial_preflight}

    def _status_html(cli: str) -> str:
        r = preflight_by_cli.get(cli)
        if r is None or r.ok:
            return '<span class="cli-status ok">ready</span>'
        return f'<span class="cli-status fail">{html.escape(r.failures[0].code)}</span>'

    preset_options = ['<option value="">none (paste-the-prompt flow)</option>'] + [
        f'<option value="{html.escape(name)}">{html.escape(name)}'
        f' — {html.escape(PRESETS[name]["mode"])}/{PRESETS[name]["max_turns"]} turns'
        f'</option>'
        for name in PRESET_NAMES
    ]

    # JS-side preset defaults: keep these in sync with src/presets.py PRESETS.
    js_presets = json.dumps({
        name: {"max_turns": PRESETS[name]["max_turns"], "mode": PRESETS[name]["mode"]}
        for name in PRESET_NAMES
    })

    body = f"""
<div class="orch-shell">
  <header class="orch-head">
    <h2>Orchestrate a conversation</h2>
    <p>Pick CLIs, topic, and preset. Preflight validates each CLI's MCP config
       before seeding — any failure aborts the whole run and writes a log to
       <code>logs/orchestrator-&lt;timestamp&gt;.log</code>. On success you'll
       redirect to the live transcript page.</p>
  </header>

  <form id="orch-form" class="orch-form">
    <section>
      <span class="lbl">Topic</span>
      <input name="topic" type="text" required maxlength="400"
             placeholder="What should the agents discuss?" />
    </section>

    <section>
      <span class="lbl">Participants <em style="color: var(--muted-2); font-weight: 400;">(min 2)</em></span>
      <p class="hint">Status reflects this machine's MCP config at page load. Re-checked server-side on submit.</p>
      <div class="orch-clis">
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="claude-code" checked />
          <span class="cli-name">claude-code</span>
          {_status_html("claude-code")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="codex" checked />
          <span class="cli-name">codex</span>
          {_status_html("codex")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="antigravity" />
          <span class="cli-name">antigravity</span>
          {_status_html("antigravity")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="gemini" />
          <span class="cli-name">gemini <em style="color: var(--muted-2); font-weight: 400;">(deprecated)</em></span>
          {_status_html("gemini")}
        </label>
      </div>
    </section>

    <section>
      <span class="lbl">Conversation</span>
      <div class="row">
        <label>
          <span style="font-size: 12px; color: var(--muted);">Preset</span>
          <select name="preset">
            {"".join(preset_options)}
          </select>
        </label>
        <label>
          <span style="font-size: 12px; color: var(--muted);">Max turns (per agent)</span>
          <input name="max_turns" type="number" min="1" max="50" value="8" />
        </label>
        <label>
          <span style="font-size: 12px; color: var(--muted);">First speaker</span>
          <select name="first">
            <option value="">(first selected)</option>
          </select>
        </label>
      </div>
    </section>

    <section>
      <span class="lbl">Optional system message</span>
      <p class="hint">Inserted as the first message in the conversation. Useful for extra context beyond the topic.</p>
      <textarea name="kickoff" rows="3"
                placeholder="Leave blank for none."></textarea>
    </section>

    <div id="orch-error" class="orch-error hidden"></div>

    <button type="submit" class="orch-submit">Run preflight + start conversation</button>
  </form>
</div>

<script>
(function() {{
  const presetDefaults = {js_presets};
  const form = document.getElementById('orch-form');
  const submitBtn = form.querySelector('button[type=submit]');
  const errorPanel = document.getElementById('orch-error');
  const presetSelect = form.querySelector('select[name=preset]');
  const maxTurns = form.querySelector('input[name=max_turns]');
  const firstSelect = form.querySelector('select[name=first]');
  const cliCheckboxes = form.querySelectorAll('input[name=cli]');

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => (
      {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]
    ));
  }}

  function updateFirstSpeaker() {{
    const selected = Array.from(cliCheckboxes).filter(cb => cb.checked).map(cb => cb.value);
    const current = firstSelect.value;
    firstSelect.innerHTML = '<option value="">(first selected)</option>' +
      selected.map(s => `<option value="${{s}}">${{s}}</option>`).join('');
    if (selected.includes(current)) firstSelect.value = current;
  }}

  presetSelect.addEventListener('change', () => {{
    const d = presetDefaults[presetSelect.value];
    if (d) maxTurns.value = d.max_turns;
  }});
  cliCheckboxes.forEach(cb => cb.addEventListener('change', updateFirstSpeaker));
  updateFirstSpeaker();

  form.addEventListener('submit', async (ev) => {{
    ev.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = 'Running preflight…';
    errorPanel.classList.add('hidden');
    errorPanel.innerHTML = '';

    const fd = new FormData(form);
    const participants = fd.getAll('cli');
    const payload = {{
      topic: (fd.get('topic') || '').trim(),
      participants: participants,
      preset: fd.get('preset') || null,
      max_turns: parseInt(fd.get('max_turns'), 10) || null,
      first: fd.get('first') || null,
      kickoff: (fd.get('kickoff') || '').trim() || null,
    }};

    try {{
      const res = await fetch('/api/orchestrate', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload),
      }});
      const data = await res.json();
      if (data.ok) {{
        window.location.href = '/conversations/' + data.conversation_id;
        return;
      }}
      let parts = ['<h4>Aborted — ' + escapeHtml(data.kind || 'error') + '</h4><ul>'];
      if (data.kind === 'preflight_failed' && Array.isArray(data.preflight)) {{
        for (const r of data.preflight) {{
          if (!r.ok) {{
            for (const f of r.failures) {{
              parts.push('<li><span class="code">' + escapeHtml(r.cli) + '/' + escapeHtml(f.code) + '</span>' + escapeHtml(f.detail) + '</li>');
            }}
          }}
        }}
      }} else {{
        parts.push('<li>' + escapeHtml(data.error || 'Unknown error') + '</li>');
      }}
      parts.push('</ul>');
      if (data.log_path) {{
        parts.push('<p style="margin: 8px 0 0 0; font-size: 12px;">Full log: <code>' + escapeHtml(data.log_path) + '</code></p>');
      }}
      errorPanel.innerHTML = parts.join('');
      errorPanel.classList.remove('hidden');
    }} catch (err) {{
      errorPanel.innerHTML = '<h4>Network error</h4><p>' + escapeHtml(String(err)) + '</p>';
      errorPanel.classList.remove('hidden');
    }} finally {{
      submitBtn.disabled = false;
      submitBtn.textContent = 'Run preflight + start conversation';
    }}
  }});
}})();
</script>
"""
    return _layout("Orchestrate", "", body, head_extras=f"<style>{ORCHESTRATE_CSS}</style>")


# ---------------------------------------------------------------------------
# Auth (HTTP Basic) — only active when AGENT_CHAT_BASIC_AUTH_PASSWORD is set
# ---------------------------------------------------------------------------

class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Single shared-credential gate for the public Fly deploy.

    Off by default. Enable by setting AGENT_CHAT_BASIC_AUTH_PASSWORD
    (and optionally AGENT_CHAT_BASIC_AUTH_USER, which defaults to
    "admin"). For real multi-user auth, replace this with whatever
    your platform fronts you with (Cloudflare Access, Tailscale
    Funnel, etc.).
    """

    def __init__(self, app, username: str, password: str) -> None:
        super().__init__(app)
        self._user_b = username.encode("utf-8")
        self._pwd_b = password.encode("utf-8")

    async def dispatch(self, request: Request, call_next):
        # /api/ingest is a separate auth realm (bearer token, validated in
        # the route handler). Skip the basic-auth gate so machine-to-machine
        # clients don't have to also know the human basic-auth password.
        # /favicon.svg is a static, non-sensitive asset — let browsers fetch
        # it for the auth-challenge tab itself so the icon shows.
        if request.url.path in ("/api/ingest", "/api/since", "/favicon.svg"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8", "replace")
                user, _, pwd = decoded.partition(":")
                if (
                    secrets.compare_digest(user.encode("utf-8"), self._user_b)
                    and secrets.compare_digest(pwd.encode("utf-8"), self._pwd_b)
                ):
                    return await call_next(request)
            except Exception:
                pass
        return Response(
            "Authentication required.\n",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="agent_chat"'},
            media_type="text/plain",
        )


def _build_middleware() -> list[Middleware]:
    # Auth gate temporarily disabled — site is fully public for now.
    # To re-enable, restore the AGENT_CHAT_BASIC_AUTH_PASSWORD env-var check
    # and return [Middleware(BasicAuthMiddleware, ...)].
    return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

async def homepage(request: Request) -> Response:
    """Public landing page. Shows the marketing/intro shell plus live
    counters and the 5 most recent conversations on this deploy.
    """
    convs = list_conversations()
    return HTMLResponse(_render_homepage(list_stats(), convs[:5]))


async def index(request: Request) -> Response:
    return HTMLResponse(_render_index(list_conversations()))


async def conversation_view(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return HTMLResponse(
            _layout("Not found", "", '<div class="empty">No such conversation.</div>'),
            status_code=404,
        )
    return HTMLResponse(_render_conversation(data))


async def api_conversations(request: Request) -> Response:
    return JSONResponse(list_conversations())


async def api_conversation(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(data)


async def api_conversation_export(request: Request) -> Response:
    """Serve a conversation as a downloadable Markdown document.

    Content-Disposition forces a download in browsers; the URL ends in
    `.md` so command-line tools (curl, wget) save with the right
    extension by default.
    """
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return Response("Not found", status_code=404, media_type="text/plain")
    md = _render_export_markdown(data)
    topic = str(data["conversation"].get("topic") or "")
    filename = _export_filename(cid, topic)
    return Response(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


async def api_conversation_export_zip(request: Request) -> Response:
    """Serve a conversation as a downloadable .zip of Markdown documents.

    Bundle: ``topic.md`` (topic + overview), ``personas/<agent>.md`` (one per
    participant — CLI tool + personality card), and ``transcript.md`` (the full
    debate). See :func:`_render_export_zip`.
    """
    cid = int(request.path_params["cid"])
    data = get_conversation(cid)
    if not data:
        return Response("Not found", status_code=404, media_type="text/plain")
    blob = _render_export_zip(data)
    topic = str(data["conversation"].get("topic") or "")
    filename = _export_zip_filename(cid, topic)
    return Response(
        blob,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


async def api_stop(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    result = stop_conversation(cid)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)


async def api_delete(request: Request) -> Response:
    """Permanently delete a conversation. Hosted-UI affordance.

    Cascades messages. The local sidecar picks this up on the next pull
    tick (via ``GET /api/since``) and applies the deletion to the local
    DB so the two sides converge. Idempotent — second DELETE returns 404.
    """
    cid = int(request.path_params["cid"])
    result = delete_conversation(cid)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)


async def api_since(request: Request) -> Response:
    """Pull endpoint for the bidirectional-sync sidecar.

    Auth: ``Authorization: Bearer <token>`` matched against
    ``$AGENT_CHAT_INGEST_TOKEN`` (same token as ``/api/ingest`` — one
    less rotation surface for now; can split later if the threat model
    needs read/write separation).

    Query params:
      - ``conversations_updated_after`` (ISO timestamp; required)
      - ``known_ids`` (comma-separated int list of conversation ids the
        sidecar believes still exist; used to compute deletions via
        set-difference. Optional — empty means "no deletions to compute").

    Response::

        {
          "conversations": [<rows where updated_at > the watermark>],
          "deleted_conversation_ids": [<ids in known_ids no longer in DB>],
          "server_time": "<ISO timestamp>"   # sidecar uses this as next watermark
        }

    **Messages are intentionally not in this payload** — they flow
    local-only-origin (agents run locally; messages never originate on
    the hosted side). See ``docs/App/db-sync.md`` for the architectural
    reasoning behind this asymmetry.

    When ``AGENT_CHAT_INGEST_TOKEN`` is unset the endpoint short-circuits
    to ``404 sync disabled`` — same opt-in posture as ``/api/ingest``.
    """
    expected = os.environ.get("AGENT_CHAT_INGEST_TOKEN")
    if not expected:
        return JSONResponse(
            {"error": "sync disabled (AGENT_CHAT_INGEST_TOKEN unset)"},
            status_code=404,
        )

    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse(
            {"error": "missing bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )
    presented = header[7:].encode("utf-8")
    if not secrets.compare_digest(presented, expected.encode("utf-8")):
        return JSONResponse(
            {"error": "invalid bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )

    updated_after = request.query_params.get(
        "conversations_updated_after", ""
    ).strip()
    if not updated_after:
        return JSONResponse(
            {"error": "conversations_updated_after query param is required"},
            status_code=400,
        )

    known_raw = request.query_params.get("known_ids", "").strip()
    try:
        known_ids = (
            [int(x) for x in known_raw.split(",") if x.strip()]
            if known_raw
            else []
        )
    except ValueError:
        return JSONResponse(
            {"error": "known_ids must be a comma-separated list of integers"},
            status_code=400,
        )

    # Persona params are optional: a sidecar that predates persona sync omits
    # `personas_updated_after`, and since_payload then skips persona work.
    personas_updated_after = request.query_params.get(
        "personas_updated_after", ""
    ).strip() or None
    pk_raw = request.query_params.get("known_persona_keys", "").strip()
    known_persona_keys = [k for k in pk_raw.split(",") if k] if pk_raw else []

    try:
        payload = since_payload(
            updated_after, known_ids,
            personas_updated_after, known_persona_keys,
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)
    return JSONResponse(payload)


async def api_ingest(request: Request) -> Response:
    """Apply a sync batch from the local writer (scripts/db_sync.py).

    Auth: ``Authorization: Bearer <token>`` where ``<token>`` matches
    ``$AGENT_CHAT_INGEST_TOKEN``. When the env var is unset the endpoint
    short-circuits to 404 — ingest is opt-in per deployment.

    Body shape::

        {
          "conversations": [<full conversation rows>],
          "messages": [<full message rows>],
          "deleted_conversation_ids": [<int>, ...]
        }

    Idempotent. See :func:`ingest_payload` for the SQL-level semantics.
    """
    expected = os.environ.get("AGENT_CHAT_INGEST_TOKEN")
    if not expected:
        return JSONResponse(
            {"error": "ingest disabled (AGENT_CHAT_INGEST_TOKEN unset)"},
            status_code=404,
        )

    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse(
            {"error": "missing bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )
    presented = header[7:].encode("utf-8")
    if not secrets.compare_digest(presented, expected.encode("utf-8")):
        return JSONResponse(
            {"error": "invalid bearer token"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="agent_chat_ingest"'},
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "body must be a JSON object"}, status_code=400
        )

    conversations = body.get("conversations") or []
    messages = body.get("messages") or []
    deletions = body.get("deleted_conversation_ids") or []
    # Persona keys are new — an old sidecar omits both, which default to [].
    personas = body.get("personas") or []
    deleted_persona_keys = body.get("deleted_persona_keys") or []
    if not (
        isinstance(conversations, list)
        and isinstance(messages, list)
        and isinstance(deletions, list)
        and isinstance(personas, list)
        and isinstance(deleted_persona_keys, list)
    ):
        return JSONResponse(
            {
                "error": "conversations / messages / "
                "deleted_conversation_ids / personas / "
                "deleted_persona_keys must be arrays"
            },
            status_code=400,
        )
    # Coerce deletion ids to int up-front so a stray string can't sneak into
    # the parameterized DELETE.
    try:
        deletions = [int(x) for x in deletions]
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "deleted_conversation_ids must be integers"},
            status_code=400,
        )
    deleted_persona_keys = [str(k) for k in deleted_persona_keys]

    try:
        result = ingest_payload(
            conversations, messages, deletions,
            personas, deleted_persona_keys,
        )
    except sqlite3.Error as e:
        return JSONResponse({"error": f"db error: {e}"}, status_code=500)

    return JSONResponse(result)


async def api_stream(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    last_id = int(request.query_params.get("since", "0"))

    async def event_generator():
        nonlocal last_id
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break
            new = messages_since(cid, last_id)
            for m in new:
                payload = {**m, "content_html": render_markdown(m["content"])}
                yield {"event": "message", "data": json.dumps(payload)}
                last_id = max(last_id, m["id"])
                idle_ticks = 0
            status = conversation_status(cid)
            if status == "complete":
                yield {"event": "complete", "data": ""}
                break
            if status is None:
                break
            idle_ticks += 1
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())


async def favicon(request: Request) -> Response:
    return Response(
        FAVICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def orchestrate(request: Request) -> Response:
    """GET /orchestrate — render the seed-conversation form with page-load preflight."""
    initial_preflight = orch_preflight.run_preflight(list(orch_preflight.SUPPORTED_CLIS))
    return HTMLResponse(_render_orchestrate(initial_preflight))


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
            db_path=DB_PATH,
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
    repo_root = Path(__file__).resolve().parent.parent
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


# ---------------------------------------------------------------------------
# Persona management. Personas live in the shared DB (the personas table), synced
# between local and the hosted mirror by the sidecar — so CRUD works on both. The
# root_exists() guards below now just confirm the DB is reachable (no longer a
# local-only gate). Writes go through orchestrator.personas (create/update/delete).
# ---------------------------------------------------------------------------

_PERSONAS_CSS = """\
<style>
  .pm-intro { color: var(--muted,#a1a1aa); margin: 0 0 1.2rem; max-width:62ch; }
  .pm-unavail { border:1px solid var(--border,#27272a); border-radius:10px; padding:1rem 1.15rem; color:var(--muted,#a1a1aa); }
  .pm-tools { display:flex; flex-direction:column; gap:0.6rem; margin-bottom:1.6rem; }
  .pm-add { border:1px solid var(--border,#27272a); border-radius:10px; padding:0.3rem 0.9rem; background:rgba(255,255,255,0.015); }
  .pm-add > summary { cursor:pointer; font-weight:600; padding:0.6rem 0; list-style:none; user-select:none; }
  .pm-add > summary::-webkit-details-marker { display:none; }
  .pm-add[open] > summary { border-bottom:1px solid var(--border,#27272a); margin-bottom:0.3rem; }
  .pm-group-h { margin:1.6rem 0 0.6rem; font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted,#a1a1aa); display:flex; align-items:center; gap:0.5rem; }
  .pm-list { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:0.4rem; }
  .pm-item details { border:1px solid var(--border,#27272a); border-radius:8px; }
  .pm-item details[open] { background:rgba(255,255,255,0.012); }
  .pm-item summary { cursor:pointer; padding:0.55rem 0.7rem; display:flex; align-items:baseline; gap:0.6rem; list-style:none; }
  .pm-item summary::-webkit-details-marker { display:none; }
  .pm-cli { font-family:ui-monospace,monospace; font-size:11px; color:var(--muted,#a1a1aa); }
  .pm-name { font-weight:600; }
  .pm-tags { font-size:11px; color:var(--muted,#a1a1aa); font-weight:400; }
  .pm-hint { font-size:11px; color:var(--muted,#71717a); font-weight:400; }
  .pm-form { padding:0.4rem 0.9rem 0.9rem; display:flex; flex-direction:column; gap:0.7rem; }
  .pm-form > p.pm-hint { margin:0; }
  .pm-field label { font-size:12px; color:var(--muted,#a1a1aa); display:block; margin-bottom:4px; }
  .pm-form input[type=text], .pm-form select, .pm-form textarea { width:100%; box-sizing:border-box; background:#0a0a0a; color:var(--text,#e4e4e7); border:1px solid var(--border,#27272a); border-radius:6px; padding:0.45rem 0.6rem; font:inherit; }
  .pm-form input[type=file] { font-size:12px; color:var(--muted,#a1a1aa); }
  .pm-form textarea { min-height:220px; font-family:ui-monospace,monospace; font-size:12px; line-height:1.5; resize:vertical; }
  .pm-actions { display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap; }
  .pm-msg { font-size:12px; margin-left:0.3rem; }
  .pm-msg.err { color:#f87171; }
  .pm-msg.ok { color:#34d399; }
  .pm-check { display:flex; align-items:center; gap:0.45rem; font-size:12px; color:var(--muted,#a1a1aa); cursor:pointer; }
  .pm-check input { width:auto; }
  /* Tag chip input */
  .pm-tagbox { display:flex; flex-wrap:wrap; gap:0.35rem; align-items:center; background:#0a0a0a; border:1px solid var(--border,#27272a); border-radius:6px; padding:0.35rem 0.45rem; cursor:text; }
  .pm-tagbox:focus-within { border-color:#52525b; }
  .pm-chip { display:inline-flex; align-items:center; gap:0.3rem; background:rgba(99,102,241,0.16); color:#c7d2fe; border:1px solid rgba(99,102,241,0.35); border-radius:999px; padding:0.1rem 0.5rem; font-size:12px; line-height:1.6; }
  .pm-chip-x { background:none; border:none; color:inherit; cursor:pointer; font-size:14px; line-height:1; padding:0; opacity:0.7; }
  .pm-chip-x:hover { opacity:1; }
  .pm-tagbox input.pm-f-tags-input { flex:1; min-width:8ch; border:none !important; background:none !important; padding:0.1rem 0.2rem !important; outline:none; }
</style>"""


def _group_select(current: str, groups: list[str], cls: str) -> str:
    """Render a <select> of existing group folders + a "new group" escape hatch.

    ``current`` is pre-selected (and added as an option if it isn't already in
    ``groups``, e.g. the default group on a fresh DB). A trailing ``__new__``
    option reveals a sibling text input client-side so a brand-new group can be
    created inline at persona-creation/import time (groups are just distinct
    ``"group"`` values, so a group materializes when its first persona lands)."""
    opts: list[str] = []
    seen = False
    for g in groups:
        sel = " selected" if g == current else ""
        seen = seen or g == current
        opts.append(f'<option value="{html.escape(g, quote=True)}"{sel}>{html.escape(g)}</option>')
    if current and not seen:
        opts.insert(0, f'<option value="{html.escape(current, quote=True)}" selected>{html.escape(current)}</option>')
    opts.append('<option value="__new__">+ Create new group…</option>')
    return f'<select class="{cls}">{"".join(opts)}</select>'


def _persona_form(*, mode: str, slug: str = "", name: str = "", group: str = "",
                  tags: str = "", body: str = "", groups: list[str] | None = None) -> str:
    """Render an add/edit persona form. ``mode`` is 'create' or 'update'."""
    groups = groups or []
    return (
        f'<form class="pm-form" data-mode="{mode}" data-slug="{html.escape(slug, quote=True)}">'
        f'<div class="pm-field"><label>Display name</label>'
        f'<input class="pm-f-name" type="text" value="{html.escape(name, quote=True)}" '
        f'placeholder="e.g. Crypto Chad" required></div>'
        f'<div class="pm-field"><label>Group folder</label>'
        + _group_select(group, groups, "pm-f-group-select")
        + '<input class="pm-f-group-new" type="text" placeholder="New group name" '
        'style="display:none;margin-top:0.4rem"></div>'
        f'<div class="pm-field"><label>Tags <span class="pm-hint">— type a tag and press comma or Enter</span></label>'
        f'<div class="pm-tagbox" data-tags="{html.escape(tags, quote=True)}">'
        f'<input class="pm-f-tags-input" type="text" placeholder="add a tag…"></div></div>'
        f'<div class="pm-field"><label>Personality card (Markdown body)</label>'
        f'<textarea class="pm-f-body" required>{html.escape(body)}</textarea></div>'
        f'<div class="pm-actions">'
        f'<button type="submit" class="btn btn-primary">'
        f'{"Add persona" if mode == "create" else "Save changes"}</button>'
        + ("" if mode == "create" else
           f'<button type="button" class="btn btn-danger pm-delete" data-slug="{html.escape(slug, quote=True)}">Delete</button>')
        + '<span class="pm-msg"></span>'
        f'</div></form>'
    )


def _render_personas_page() -> str:
    crumbs = '<strong>Personas</strong>'
    intro = (
        '<p class="pm-intro">Manage the debate personality roster. Add, edit, or '
        'remove personas — changes are stored in the shared database and synced '
        'between this site and your local machine, so the next debate (and '
        '<code>list_personas</code>) picks them up immediately.</p>'
    )
    if not personas_registry.root_exists():
        body = (
            f'<div class="detail-head"><h2>Personas</h2></div>{intro}'
            '<div class="pm-unavail">Persona storage is <strong>unavailable</strong> — '
            'the database can\'t be reached right now. Try again shortly.</div>'
        )
        return _layout("Personas", crumbs, body, head_extras=_PERSONAS_CSS)

    groups = personas_registry.discover_groups()
    default_group = personas_registry.DEFAULT_DEBATER_GROUP

    add_block = (
        '<details class="pm-add"><summary>＋ Add a new persona</summary>'
        + _persona_form(mode="create", group=default_group, groups=groups)
        + '</details>'
    )

    import_block = (
        '<details class="pm-add"><summary>⬆ Import personas from Markdown files</summary>'
        '<div class="pm-form">'
        '<p class="pm-hint">Select one or more <code>.md</code> cards with YAML '
        'frontmatter (the seed-card format). The filename becomes the slug; the '
        'title, tags, and category come from the frontmatter; everything after the '
        'frontmatter is the personality body.</p>'
        '<div class="pm-field"><label>Target group</label>'
        + _group_select(default_group, groups, "pm-imp-group-select")
        + '<input class="pm-imp-group-new" type="text" placeholder="New group name" '
        'style="display:none;margin-top:0.4rem"></div>'
        '<div class="pm-field"><label>Markdown files</label>'
        '<input class="pm-imp-files" type="file" accept=".md,.markdown,text/markdown" multiple></div>'
        '<label class="pm-check"><input type="checkbox" class="pm-imp-overwrite"> '
        'Overwrite existing personas that have the same slug</label>'
        '<div class="pm-actions"><button type="button" class="btn btn-primary pm-imp-btn">Import</button>'
        '<span class="pm-msg pm-imp-msg"></span></div>'
        '</div></details>'
    )

    tools_block = f'<div class="pm-tools">{add_block}{import_block}</div>'

    sections = []
    for g in groups:
        cards = personas_registry.list_personas(g)
        items = []
        for p in cards:
            tags_str = ", ".join(p.tags)
            tags_html = f'<span class="pm-tags">{html.escape(tags_str)}</span>' if tags_str else ""
            items.append(
                '<li class="pm-item"><details>'
                f'<summary><span class="pm-name">{html.escape(p.name)}</span>'
                f'<span class="pm-cli">{html.escape(p.slug)}</span>{tags_html}</summary>'
                + _persona_form(mode="update", slug=p.slug, name=p.name, group=g,
                                tags=tags_str, body=p.body, groups=groups)
                + '</details></li>'
            )
        sections.append(
            f'<h3 class="pm-group-h">{html.escape(g)} <span class="pm-tags">({len(cards)})</span></h3>'
            f'<ul class="pm-list">{"".join(items)}</ul>'
        )

    script = """
    <script>
    (function() {
      async function postJSON(url, data) {
        const res = await fetch(url, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(data)
        });
        let body = {};
        try { body = await res.json(); } catch (e) {}
        return { ok: res.ok && body.ok !== false, body };
      }

      // --- Tag chip input: type a tag, then comma / Enter resolves it ---------
      function chips(box) { return [...box.querySelectorAll('.pm-chip')]; }
      function tagList(box) { return chips(box).map(c => c.dataset.tag); }
      function addChip(box, text) {
        text = (text || '').trim().replace(/,+$/, '').trim();
        if (!text) return;
        const have = tagList(box).map(t => t.toLowerCase());
        if (have.includes(text.toLowerCase())) return;
        const input = box.querySelector('.pm-f-tags-input');
        const chip = document.createElement('span');
        chip.className = 'pm-chip'; chip.dataset.tag = text;
        chip.append(document.createTextNode(text));
        const x = document.createElement('button');
        x.type = 'button'; x.className = 'pm-chip-x'; x.textContent = '×';
        x.addEventListener('click', () => chip.remove());
        chip.appendChild(x);
        box.insertBefore(chip, input);
      }
      function initTagbox(box) {
        const input = box.querySelector('.pm-f-tags-input');
        (box.dataset.tags || '').split(',').forEach(t => addChip(box, t));
        box.addEventListener('click', () => input.focus());
        input.addEventListener('keydown', e => {
          if (e.key === ',' || e.key === 'Enter') {
            e.preventDefault(); addChip(box, input.value); input.value = '';
          } else if (e.key === 'Backspace' && !input.value) {
            const cs = chips(box); if (cs.length) cs[cs.length - 1].remove();
          }
        });
        // Catch pastes / "comma+space" sequences that slip past keydown.
        input.addEventListener('input', () => {
          if (input.value.includes(',')) {
            const parts = input.value.split(',');
            input.value = parts.pop();
            parts.forEach(p => addChip(box, p));
          }
        });
        input.addEventListener('blur', () => { addChip(box, input.value); input.value = ''; });
      }
      document.querySelectorAll('.pm-tagbox').forEach(initTagbox);

      // --- "Create new group" toggle for any group <select> ------------------
      function wireGroupSelect(sel, newInput) {
        if (!sel || !newInput) return;
        sel.addEventListener('change', () => {
          const isNew = sel.value === '__new__';
          newInput.style.display = isNew ? 'block' : 'none';
          if (isNew) newInput.focus();
        });
      }
      function groupValue(sel, newInput) {
        return sel.value === '__new__' ? (newInput.value || '').trim() : sel.value;
      }

      // --- Create / edit forms -----------------------------------------------
      document.querySelectorAll('.pm-form[data-mode]').forEach(form => {
        const sel = form.querySelector('.pm-f-group-select');
        const newInput = form.querySelector('.pm-f-group-new');
        wireGroupSelect(sel, newInput);
        form.addEventListener('submit', async (ev) => {
          ev.preventDefault();
          const mode = form.dataset.mode;
          const slug = form.dataset.slug;
          const msg = form.querySelector('.pm-msg');
          const btn = form.querySelector('button[type=submit]');
          const box = form.querySelector('.pm-tagbox');
          addChip(box, box.querySelector('.pm-f-tags-input').value);
          box.querySelector('.pm-f-tags-input').value = '';
          const group = groupValue(sel, newInput);
          if (sel.value === '__new__' && !group) {
            msg.className = 'pm-msg err'; msg.textContent = 'Enter a name for the new group'; return;
          }
          const data = {
            name: form.querySelector('.pm-f-name').value,
            group: group,
            tags: tagList(box),
            body: form.querySelector('.pm-f-body').value
          };
          const url = mode === 'create' ? '/api/personas' : '/api/personas/' + encodeURIComponent(slug);
          msg.className = 'pm-msg'; msg.textContent = 'Saving…';
          btn.disabled = true;
          const { ok, body } = await postJSON(url, data);
          btn.disabled = false;
          if (ok) { msg.className = 'pm-msg ok'; msg.textContent = 'Saved'; location.reload(); }
          else { msg.className = 'pm-msg err'; msg.textContent = (body && body.error) || 'Failed'; }
        });
      });

      // --- Delete buttons ----------------------------------------------------
      document.querySelectorAll('.pm-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
          const slug = btn.dataset.slug;
          if (!confirm('Delete persona \\'' + slug + '\\'? This removes it everywhere (synced).')) return;
          btn.disabled = true;
          const { ok, body } = await postJSON('/api/personas/' + encodeURIComponent(slug) + '/delete', {});
          if (ok) location.reload();
          else { alert('Delete failed: ' + ((body && body.error) || 'unknown')); btn.disabled = false; }
        });
      });

      // --- Markdown import ---------------------------------------------------
      const impBtn = document.querySelector('.pm-imp-btn');
      if (impBtn) {
        const impSel = document.querySelector('.pm-imp-group-select');
        const impNew = document.querySelector('.pm-imp-group-new');
        wireGroupSelect(impSel, impNew);
        impBtn.addEventListener('click', async () => {
          const msg = document.querySelector('.pm-imp-msg');
          const files = [...document.querySelector('.pm-imp-files').files];
          if (!files.length) {
            msg.className = 'pm-msg pm-imp-msg err'; msg.textContent = 'Choose at least one .md file'; return;
          }
          const group = groupValue(impSel, impNew);
          if (impSel.value === '__new__' && !group) {
            msg.className = 'pm-msg pm-imp-msg err'; msg.textContent = 'Enter a name for the new group'; return;
          }
          msg.className = 'pm-msg pm-imp-msg'; msg.textContent = 'Reading files…';
          const payload = { group: group, overwrite: document.querySelector('.pm-imp-overwrite').checked, files: [] };
          for (const f of files) payload.files.push({ filename: f.name, text: await f.text() });
          impBtn.disabled = true; msg.textContent = 'Importing…';
          const { ok, body } = await postJSON('/api/personas/import', payload);
          impBtn.disabled = false;
          if (ok) {
            msg.className = 'pm-msg pm-imp-msg ok';
            let txt = 'Imported ' + body.imported + ', skipped ' + body.skipped;
            if (body.errors && body.errors.length) txt += ' — ' + body.errors[0];
            msg.textContent = txt;
            setTimeout(() => location.reload(), body.imported ? 900 : 2500);
          } else {
            msg.className = 'pm-msg pm-imp-msg err'; msg.textContent = (body && body.error) || 'Import failed';
          }
        });
      }
    })();
    </script>"""

    body = (
        f'<div class="detail-head"><h2>Personas</h2></div>{intro}'
        f'{tools_block}{"".join(sections)}{script}'
    )
    return _layout("Personas", crumbs, body, head_extras=_PERSONAS_CSS)


def _parse_tags(value: Any) -> list[str]:
    """Accept a list or a comma-separated string of tags; return a clean list."""
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


async def personas_page(request: Request) -> Response:
    """GET /personas — the persona-management page."""
    return HTMLResponse(_render_personas_page())


async def api_persona_create(request: Request) -> Response:
    """POST /api/personas — create a new persona."""
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    try:
        p = personas_registry.create_persona(
            name=(payload.get("name") or ""),
            body=(payload.get("body") or ""),
            group=(payload.get("group") or personas_registry.DEFAULT_DEBATER_GROUP).strip(),
            tags=_parse_tags(payload.get("tags")),
        )
    except personas_registry.PersonaWriteError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True, "slug": p.slug, "group": p.group})


async def api_persona_update(request: Request) -> Response:
    """POST /api/personas/{slug} — update an existing persona."""
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    slug = request.path_params["slug"]
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    try:
        p = personas_registry.update_persona(
            slug,
            name=payload.get("name"),
            body=payload.get("body"),
            tags=_parse_tags(payload.get("tags")) if "tags" in payload else None,
            group=(payload.get("group") or None),
        )
    except personas_registry.PersonaWriteError as e:
        code = 404 if "not found" in str(e).lower() else 400
        return JSONResponse({"ok": False, "error": str(e)}, status_code=code)
    return JSONResponse({"ok": True, "slug": p.slug, "group": p.group})


async def api_persona_import(request: Request) -> Response:
    """POST /api/personas/import — bulk-create personas from uploaded Markdown.

    Body: ``{"group": str, "overwrite": bool, "files": [{"filename", "text"}]}``.
    Each file is parsed as a seed-style card (frontmatter + body). Returns
    per-file counts plus any error messages so partial imports surface cleanly.
    """
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "request body must be JSON"}, status_code=400)
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        return JSONResponse({"ok": False, "error": "no files provided"}, status_code=400)
    group = (payload.get("group") or personas_registry.DEFAULT_DEBATER_GROUP).strip() \
        or personas_registry.DEFAULT_DEBATER_GROUP
    overwrite = bool(payload.get("overwrite"))
    imported = 0
    errors: list[str] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        filename = str(f.get("filename") or "")
        text = f.get("text") or ""
        try:
            personas_registry.import_persona_card(
                text, group=group, filename=filename, overwrite=overwrite,
            )
            imported += 1
        except personas_registry.PersonaWriteError as e:
            errors.append(f"{filename or '(unnamed)'}: {e}")
    return JSONResponse({
        "ok": True, "imported": imported,
        "skipped": len(files) - imported, "errors": errors,
    })


async def api_persona_delete(request: Request) -> Response:
    """POST /api/personas/{slug}/delete — delete a persona."""
    if not personas_registry.root_exists():
        return JSONResponse({"ok": False, "error": "persona storage unavailable (database unreachable)"}, status_code=404)
    slug = request.path_params["slug"]
    try:
        ok = personas_registry.delete_persona(slug)
    except personas_registry.PersonaWriteError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if not ok:
        return JSONResponse({"ok": False, "error": f"persona not found: {slug}"}, status_code=404)
    return JSONResponse({"ok": True})


routes = [
    Route("/", homepage),
    Route("/conversations", index),
    Route("/conversations/{cid:int}", conversation_view),
    Route("/api/conversations", api_conversations),
    Route("/api/conversations/{cid:int}", api_conversation),
    Route("/api/conversations/{cid:int}/export.md", api_conversation_export),
    Route("/api/conversations/{cid:int}/export.zip", api_conversation_export_zip),
    Route("/api/conversations/{cid:int}/stop", api_stop, methods=["POST"]),
    Route("/api/conversations/{cid:int}/delete", api_delete, methods=["POST"]),
    Route("/api/conversations/{cid:int}/stream", api_stream),
    Route("/api/ingest", api_ingest, methods=["POST"]),
    Route("/api/since", api_since),
    Route("/orchestrate", orchestrate),
    Route("/api/orchestrate", api_orchestrate, methods=["POST"]),
    Route("/personas", personas_page),
    Route("/api/personas", api_persona_create, methods=["POST"]),
    Route("/api/personas/import", api_persona_import, methods=["POST"]),
    Route("/api/personas/{slug}", api_persona_update, methods=["POST"]),
    Route("/api/personas/{slug}/delete", api_persona_delete, methods=["POST"]),
    Route("/favicon.svg", favicon),
]

app = Starlette(routes=routes, middleware=_build_middleware())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _default_db_path() -> str:
    """Resolve DB path with precedence: $AGENT_CHAT_DB > <repo>/db/chat.db.

    The computed default sits one level above this script (src/), so a fresh
    clone Just Works without any flag or env var: `<repo>/db/chat.db`.
    """
    env_db = os.environ.get("AGENT_CHAT_DB")
    if env_db:
        return env_db
    return str((Path(__file__).resolve().parent.parent / "db" / "chat.db"))


def main() -> None:
    global DB_PATH
    parser = argparse.ArgumentParser(
        description="Web UI for agent_chat conversations.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the shared SQLite database. Defaults to $AGENT_CHAT_DB, "
             "or <repo>/db/chat.db resolved relative to this script.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Bind address. Defaults to $HOST or 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PORT", "8765")),
        type=int,
        help="Port. Defaults to $PORT or 8765.",
    )
    args = parser.parse_args()

    db_path = args.db_path if args.db_path else _default_db_path()
    DB_PATH = str(Path(db_path).resolve())
    db_init()
    ingest_on = bool(os.environ.get("AGENT_CHAT_INGEST_TOKEN"))
    print(f"agent_chat web UI — DB: {DB_PATH}")
    print(f"  bind: http://{args.host}:{args.port}/")
    print(f"  basic auth: off (gate disabled)")
    print(f"  /api/ingest: {'on' if ingest_on else 'off'}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
