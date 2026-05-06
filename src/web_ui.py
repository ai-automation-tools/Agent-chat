"""
agent_chat web UI — local read-only viewer for chat.db.

A small Starlette app that reads the same SQLite database the MCP server
writes to. Run as a separate process; does NOT replace or wrap the MCP
server. Bind defaults to 127.0.0.1.

Usage:
    python src/web_ui.py --db-path db/chat.db
    python src/web_ui.py --db-path db/chat.db --host 127.0.0.1 --port 8765

Then open http://127.0.0.1:8765/ in a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import html
import json
import os
import re
import secrets
import sqlite3
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


DB_PATH: str = ""
POLL_INTERVAL_SECONDS = 1.0


# Mirrors the SCHEMA in src/agent_chat_mcp.py. Both must stay in sync —
# schema changes require updating both files plus a CHANGELOG entry. Kept
# duplicated rather than imported so web_ui.py doesn't drag in the MCP
# server module's heavy imports at startup.
SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    participants    TEXT NOT NULL,
    mode            TEXT NOT NULL,
    max_turns       INTEGER NOT NULL,
    current_turn    TEXT,
    status          TEXT NOT NULL,
    end_reason      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
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
"""


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
    """Create tables/indexes if missing. Idempotent — safe on every boot.

    Used on the public Fly deploy where the persistent volume starts empty:
    the first request would otherwise hit "no such table: conversations".
    Locally this is a no-op when the DB already exists.
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(SCHEMA)


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
)
_MSG_COLUMNS = (
    "id", "conversation_id", "sender", "content", "signal", "created_at",
)


def ingest_payload(
    conversations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    deleted_conversation_ids: list[int],
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
    """
    upserted = inserted = deleted = cascaded = 0
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
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {
        "conversations_upserted": upserted,
        "messages_inserted": inserted,
        "conversations_deleted": deleted,
        "messages_deleted_cascade": cascaded,
    }


# ---------------------------------------------------------------------------
# HTML rendering (inline — fine for a small local app)
# ---------------------------------------------------------------------------

BASE_CSS = """
:root {
  --bg: #0f1419;
  --panel: #1a2027;
  --panel-2: #232b34;
  --text: #d4d4d4;
  --muted: #8a96a3;
  --accent: #6cb6ff;
  --accent-2: #f6c177;
  --border: #2a3441;
  --good: #7fd194;
  --warn: #f0b072;
  --bad: #e06c75;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.55 -apple-system, "Segoe UI", system-ui, sans-serif;
}
header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  display: flex;
  align-items: baseline;
  gap: 16px;
}
header h1 { margin: 0; font-size: 18px; font-weight: 600; }
header .crumb { color: var(--muted); font-size: 13px; }
header a { color: var(--accent); text-decoration: none; }
header a:hover { text-decoration: underline; }
main { padding: 24px; max-width: 1100px; margin: 0 auto; }
table { width: 100%; border-collapse: collapse; }
th, td {
  padding: 10px 12px; text-align: left;
  border-bottom: 1px solid var(--border);
}
th { font-weight: 600; color: var(--muted); font-size: 12px;
     text-transform: uppercase; letter-spacing: 0.04em; }
tr:hover td { background: var(--panel); }
td a { color: var(--accent); text-decoration: none; }
td a:hover { text-decoration: underline; }
.status-active { color: var(--good); }
.status-complete { color: var(--muted); }
.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  background: var(--panel-2);
  color: var(--muted);
  border: 1px solid var(--border);
}
.muted { color: var(--muted); }
.empty {
  padding: 48px 24px;
  text-align: center;
  color: var(--muted);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
.meta-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 16px;
  margin: 0 0 16px;
  padding: 16px;
  background: var(--panel);
  border-radius: 6px;
  border: 1px solid var(--border);
  font-size: 13px;
}
.meta-grid dt { color: var(--muted); }
.meta-grid dd { margin: 0; }
.transcript { display: flex; flex-direction: column; gap: 12px; }
.msg {
  padding: 12px 16px;
  border-radius: 6px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
}
.msg.sender-system { border-left-color: var(--muted); }
.msg.signal-done { border-left-color: var(--good); }
.msg.signal-blocked { border-left-color: var(--bad); }
.msg-head {
  display: flex; gap: 12px; align-items: baseline;
  font-size: 12px; color: var(--muted); margin-bottom: 6px;
}
.msg-head .who { color: var(--accent-2); font-weight: 600; }
.msg-head .signal {
  text-transform: uppercase; font-size: 10px;
  padding: 1px 6px; border-radius: 3px;
}
.msg-head .signal.done { background: var(--good); color: var(--bg); }
.msg-head .signal.blocked { background: var(--bad); color: var(--bg); }
.msg-body { word-wrap: break-word; overflow-wrap: anywhere; }
.msg-body > :first-child { margin-top: 0; }
.msg-body > :last-child { margin-bottom: 0; }
.msg-body p { margin: 0 0 10px; }
.msg-body p:last-child { margin-bottom: 0; }
.msg-body strong { color: #f0f4f8; font-weight: 600; }
.msg-body em { font-style: italic; }
.msg-body a { color: var(--accent); text-decoration: underline;
              text-decoration-color: rgba(108,182,255,0.4); }
.msg-body a:hover { text-decoration-color: var(--accent); }
.msg-body ul, .msg-body ol { margin: 6px 0 10px; padding-left: 24px; }
.msg-body li { margin: 2px 0; }
.msg-body li > p { margin: 0; }
.msg-body blockquote {
  margin: 8px 0; padding: 4px 12px;
  border-left: 3px solid var(--border);
  color: var(--muted);
}
.msg-body code {
  font: 13px/1.4 ui-monospace, "Cascadia Mono", "Consolas", monospace;
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--border);
}
.msg-body pre {
  margin: 8px 0; padding: 10px 12px;
  background: var(--bg);
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
  margin: 12px 0 6px; font-weight: 600; color: #eef2f6;
}
.msg-body h1 { font-size: 18px; }
.msg-body h2 { font-size: 16px; }
.msg-body h3 { font-size: 15px; }
.msg-body h4, .msg-body h5, .msg-body h6 { font-size: 14px; }
.msg-body table {
  border-collapse: collapse; margin: 8px 0;
  font-size: 13px;
}
.msg-body th, .msg-body td {
  border: 1px solid var(--border);
  padding: 4px 10px;
  text-align: left;
}
.msg-body th { background: var(--panel-2); color: var(--muted); }
.msg-body hr { border: 0; border-top: 1px solid var(--border); margin: 12px 0; }
.msg-body del { color: var(--muted); }
.live-indicator {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--muted);
}
.live-indicator .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--good); animation: pulse 2s ease-in-out infinite;
}
.live-indicator.stopped .dot { background: var(--muted); animation: none; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
.btn {
  font: inherit;
  padding: 5px 12px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  cursor: pointer;
  display: inline-block;
  text-decoration: none;
}
.btn:hover { background: var(--panel); text-decoration: none; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger {
  border-color: var(--bad);
  color: var(--bad);
}
.btn-danger:hover { background: var(--bad); color: var(--bg); }
.header-actions { display: flex; gap: 12px; align-items: center; }
"""


# ---------------------------------------------------------------------------
# Homepage CSS — the landing surface. Console-arena aesthetic: near-black
# canvas, single emerald accent (#10b981, matching the favicon), heavy
# JetBrains Mono display paired with IBM Plex Sans body, hairline rules,
# subtle SVG grain for atmosphere, one staggered reveal on load.
# ---------------------------------------------------------------------------

HOME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --ink: #07090a;
  --ink-2: #0d1013;
  --ink-3: #14191e;
  --line: rgba(255,255,255,0.08);
  --line-strong: rgba(255,255,255,0.14);
  --ash: #6b7480;
  --bone: #c8ccd1;
  --paper: #e7eaee;
  --emerald: #10b981;
  --emerald-soft: rgba(16,185,129,0.12);
  --emerald-line: rgba(16,185,129,0.32);
  --amber: #f59e0b;
  --crimson: #ef4444;
  --display: 'JetBrains Mono', ui-monospace, monospace;
  --body: 'IBM Plex Sans', system-ui, sans-serif;
  --mono: 'IBM Plex Mono', ui-monospace, monospace;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body.home {
  margin: 0;
  background: var(--ink);
  color: var(--bone);
  font: 15px/1.6 var(--body);
  font-weight: 300;
  letter-spacing: 0.005em;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* Atmospheric grain — fine SVG noise overlay, fixed, non-interactive.
   Keeps the near-black canvas from feeling like a flat fill on OLED. */
body.home::before {
  content: '';
  position: fixed; inset: 0;
  pointer-events: none; z-index: 1;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.6 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.4'/></svg>");
  opacity: 0.55;
  mix-blend-mode: overlay;
}

/* Soft emerald spotlight in the upper-left, fading toward black. Built
   from two radial gradients to avoid the cliched single-blob hero. */
body.home::after {
  content: '';
  position: fixed; inset: 0;
  pointer-events: none; z-index: 0;
  background:
    radial-gradient(900px 600px at 8% -10%, rgba(16,185,129,0.18), transparent 60%),
    radial-gradient(700px 500px at 100% 110%, rgba(16,185,129,0.08), transparent 55%);
}

body.home > * { position: relative; z-index: 2; }

/* TOPBAR — thin, monospaced, two-row "console" header */
.topbar {
  border-bottom: 1px solid var(--line);
  background: rgba(7,9,10,0.72);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.topbar-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 14px 28px;
  display: flex;
  align-items: center;
  gap: 24px;
  font-family: var(--mono);
  font-size: 12.5px;
  letter-spacing: 0.04em;
}
.topbar .mark {
  display: inline-flex; align-items: center; gap: 10px;
  text-decoration: none; color: var(--paper);
  font-family: var(--display);
  font-weight: 800;
  letter-spacing: -0.01em;
  font-size: 14.5px;
}
.topbar .mark .glyph {
  width: 22px; height: 22px;
  background: var(--emerald);
  border-radius: 5px;
  display: grid; place-items: center;
  color: var(--ink);
  font-family: var(--display);
  font-weight: 800;
  font-size: 13px;
  line-height: 1;
}
.topbar nav {
  display: flex; gap: 22px; margin-left: auto;
  text-transform: uppercase; font-size: 11.5px;
}
.topbar nav a {
  color: var(--ash); text-decoration: none;
  transition: color 0.15s ease;
  position: relative;
}
.topbar nav a:hover { color: var(--paper); }
.topbar nav a.cta {
  color: var(--emerald);
  border: 1px solid var(--emerald-line);
  padding: 5px 12px;
  border-radius: 2px;
  background: var(--emerald-soft);
}
.topbar nav a.cta:hover {
  background: var(--emerald);
  color: var(--ink);
  border-color: var(--emerald);
}
.topbar .live-pill {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 10.5px; color: var(--emerald);
  text-transform: uppercase; letter-spacing: 0.12em;
}
.topbar .live-pill .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--emerald);
  box-shadow: 0 0 8px var(--emerald);
  animation: pulse-em 1.6s ease-in-out infinite;
}
@keyframes pulse-em { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

/* HERO — asymmetric, monospace coordinate label, oversized display title */
.hero {
  max-width: 1240px;
  margin: 0 auto;
  padding: 88px 28px 72px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 380px);
  gap: 64px;
  align-items: end;
}
.hero .coord {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ash);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  display: flex; align-items: center; gap: 14px;
  margin-bottom: 28px;
  opacity: 0; transform: translateY(8px);
  animation: rise 0.6s ease 0.05s forwards;
}
.hero .coord::before {
  content: ''; display: inline-block;
  width: 28px; height: 1px;
  background: var(--emerald);
}
.hero h1 {
  font-family: var(--display);
  font-weight: 800;
  font-size: clamp(40px, 5.6vw, 80px);
  line-height: 0.96;
  letter-spacing: -0.04em;
  margin: 0 0 28px;
  color: var(--paper);
}
.hero h1 .row { display: block; overflow: hidden; }
.hero h1 .row span {
  display: inline-block;
  opacity: 0; transform: translateY(110%);
  animation: rise-clip 0.7s cubic-bezier(0.2,0.7,0.2,1) forwards;
}
.hero h1 .row:nth-child(1) span { animation-delay: 0.10s; }
.hero h1 .row:nth-child(2) span { animation-delay: 0.20s; color: var(--emerald); }
.hero .lede {
  max-width: 620px;
  font-size: 17.5px;
  line-height: 1.55;
  color: var(--bone);
  opacity: 0; transform: translateY(8px);
  animation: rise 0.7s ease 0.45s forwards;
}
.hero .lede strong { color: var(--paper); font-weight: 500; }
.hero .lede em {
  font-style: normal;
  color: var(--emerald);
  font-family: var(--mono);
  font-size: 15.5px;
  letter-spacing: -0.005em;
}
.hero .actions {
  margin-top: 36px;
  display: flex; gap: 14px; flex-wrap: wrap;
  opacity: 0; transform: translateY(8px);
  animation: rise 0.7s ease 0.6s forwards;
}
.hero .panel {
  border: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent);
  padding: 22px 24px;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ash);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px 22px;
  opacity: 0; transform: translateY(8px);
  animation: rise 0.7s ease 0.55s forwards;
}
.hero .panel .label {
  display: block;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ash);
  margin-bottom: 6px;
}
.hero .panel .value {
  display: block;
  font-family: var(--display);
  font-weight: 700;
  font-size: 28px;
  line-height: 1;
  color: var(--paper);
  letter-spacing: -0.02em;
}
.hero .panel .value.em { color: var(--emerald); }

/* CTAs */
.cta-primary, .cta-ghost {
  font-family: var(--mono);
  font-size: 13px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-decoration: none;
  padding: 14px 22px;
  border-radius: 2px;
  display: inline-flex; align-items: center; gap: 10px;
  transition: all 0.18s ease;
}
.cta-primary {
  background: var(--emerald);
  color: var(--ink);
  font-weight: 700;
  border: 1px solid var(--emerald);
}
.cta-primary:hover {
  background: transparent;
  color: var(--emerald);
  box-shadow: inset 0 0 0 1px var(--emerald);
}
.cta-primary .arrow { transition: transform 0.18s ease; }
.cta-primary:hover .arrow { transform: translateX(4px); }
.cta-ghost {
  background: transparent;
  color: var(--paper);
  border: 1px solid var(--line-strong);
  font-weight: 500;
}
.cta-ghost:hover {
  border-color: var(--paper);
  background: rgba(255,255,255,0.04);
}

/* SECTION shell */
.section {
  max-width: 1240px;
  margin: 0 auto;
  padding: 72px 28px;
  border-top: 1px solid var(--line);
}
.section-eyebrow {
  display: flex; align-items: center; gap: 14px;
  font-family: var(--mono);
  font-size: 11px; letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ash);
  margin-bottom: 22px;
}
.section-eyebrow .num {
  color: var(--emerald);
  font-weight: 700;
}
.section-eyebrow::after {
  content: ''; flex: 1; height: 1px; background: var(--line);
}
.section h2 {
  font-family: var(--display);
  font-weight: 700;
  font-size: clamp(28px, 3.4vw, 42px);
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin: 0 0 18px;
  color: var(--paper);
  max-width: 820px;
}
.section h2 em {
  font-style: normal;
  color: var(--emerald);
}
.section .sub {
  max-width: 720px;
  color: var(--ash);
  font-size: 16px;
  margin: 0 0 44px;
}

/* WHAT — three cards. Hairline borders, a single emerald rule on top of
   the active card, monospace ordinal counter. */
.what-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.what-card {
  background: var(--ink);
  padding: 32px 28px 36px;
  position: relative;
  transition: background 0.2s ease;
}
.what-card:hover { background: var(--ink-2); }
.what-card .ord {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ash);
  letter-spacing: 0.16em;
  margin-bottom: 18px;
}
.what-card .ord .em { color: var(--emerald); }
.what-card h3 {
  font-family: var(--display);
  font-weight: 700;
  font-size: 22px;
  line-height: 1.2;
  letter-spacing: -0.01em;
  margin: 0 0 14px;
  color: var(--paper);
}
.what-card p {
  margin: 0;
  font-size: 14.5px;
  color: var(--bone);
  line-height: 1.65;
}
.what-card p code {
  font-family: var(--mono); font-size: 13px;
  color: var(--emerald);
  background: var(--emerald-soft);
  padding: 1px 6px; border-radius: 2px;
}

/* HOW — numbered steps, two-column rhythm, code blocks emerald-tinted */
.how-list { counter-reset: step; }
.how-step {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 28px;
  padding: 28px 0;
  border-top: 1px solid var(--line);
  align-items: start;
}
.how-step:last-child { border-bottom: 1px solid var(--line); }
.how-step .step-num {
  font-family: var(--display);
  font-weight: 800;
  font-size: 36px;
  line-height: 1;
  color: var(--emerald);
  letter-spacing: -0.02em;
}
.how-step .step-num::before {
  content: counter(step, decimal-leading-zero);
  counter-increment: step;
}
.how-step h4 {
  font-family: var(--display);
  font-weight: 600;
  font-size: 18px;
  margin: 0 0 8px;
  color: var(--paper);
  letter-spacing: -0.005em;
}
.how-step p {
  margin: 0;
  color: var(--bone);
  font-size: 14.5px;
}
.how-step a { color: var(--emerald); text-decoration: underline;
              text-decoration-color: var(--emerald-line); }
.how-step a:hover { text-decoration-color: var(--emerald); }
.how-step pre {
  margin: 0;
  font-family: var(--mono);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--paper);
  background: var(--ink-2);
  border: 1px solid var(--line);
  border-left: 2px solid var(--emerald);
  padding: 14px 16px;
  overflow-x: auto;
  border-radius: 0;
}
.how-step pre .cmt { color: var(--ash); }
.how-step pre .em { color: var(--emerald); }

/* LATEST — table-ish but lighter than the conversations index */
.latest-list { display: flex; flex-direction: column; }
.latest-row {
  display: grid;
  grid-template-columns: 60px minmax(0, 2.4fr) minmax(0, 1fr) 110px;
  gap: 24px;
  align-items: center;
  padding: 18px 4px;
  border-top: 1px solid var(--line);
  text-decoration: none;
  color: var(--paper);
  transition: padding-left 0.18s ease, background 0.18s ease;
}
.latest-row:last-child { border-bottom: 1px solid var(--line); }
.latest-row:hover {
  padding-left: 14px;
  background: linear-gradient(90deg, var(--emerald-soft), transparent 80%);
}
.latest-row .lid {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ash);
  letter-spacing: 0.04em;
}
.latest-row .ltopic {
  font-family: var(--display);
  font-weight: 500;
  font-size: 16px;
  line-height: 1.3;
  color: var(--paper);
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.latest-row .lparts {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ash);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.latest-row .lstatus {
  font-family: var(--mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  text-align: right;
}
.lstatus.active { color: var(--emerald); }
.lstatus.complete { color: var(--ash); }
.latest-empty {
  padding: 36px 0;
  color: var(--ash);
  font-family: var(--mono);
  font-size: 13px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.latest-foot {
  margin-top: 24px;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.04em;
}
.latest-foot a {
  color: var(--emerald);
  text-decoration: none;
  border-bottom: 1px solid var(--emerald-line);
  padding-bottom: 2px;
}
.latest-foot a:hover { border-bottom-color: var(--emerald); }

/* RESOURCES — 2 columns of grouped link tiles */
.res-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.res-group {
  background: var(--ink);
  padding: 28px 26px;
}
.res-group h4 {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ash);
  margin: 0 0 18px;
  display: flex; align-items: center; gap: 10px;
}
.res-group h4::before {
  content: ''; width: 6px; height: 6px;
  background: var(--emerald);
  display: inline-block;
}
.res-group ul { list-style: none; margin: 0; padding: 0; }
.res-group li { margin: 0; }
.res-group a {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  color: var(--paper);
  font-size: 14.5px;
  font-weight: 400;
  letter-spacing: -0.005em;
  transition: color 0.15s ease;
}
.res-group li:last-child a { border-bottom: 0; }
.res-group a .hint {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ash);
  letter-spacing: 0;
  text-transform: none;
  font-weight: 400;
  margin-left: 12px;
  white-space: nowrap;
  text-align: right;
}
.res-group a:hover { color: var(--emerald); }
.res-group a:hover .hint { color: var(--emerald); }
.res-group a .arrow {
  font-family: var(--mono);
  color: var(--ash);
  margin-left: 10px;
  transition: transform 0.15s ease, color 0.15s ease;
}
.res-group a:hover .arrow { color: var(--emerald); transform: translateX(3px); }

/* FOOTER */
.foot {
  border-top: 1px solid var(--line);
  margin-top: 40px;
}
.foot-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 36px 28px 56px;
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 16px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ash);
  letter-spacing: 0.04em;
}
.foot-inner a { color: var(--bone); text-decoration: none; }
.foot-inner a:hover { color: var(--emerald); }
.foot-inner .sig { color: var(--paper); }
.foot-inner .sig em {
  color: var(--emerald); font-style: normal;
}

@keyframes rise {
  to { opacity: 1; transform: translateY(0); }
}
@keyframes rise-clip {
  to { opacity: 1; transform: translateY(0); }
}

/* RESPONSIVE — collapse the hero panel and tables sensibly */
@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 36px;
    padding: 56px 22px 48px;
  }
  .topbar nav { gap: 14px; }
  .topbar nav a:not(.cta) { display: none; }
  .what-grid { grid-template-columns: 1fr; }
  .how-step { grid-template-columns: 60px 1fr; }
  .how-step pre { grid-column: 1 / -1; }
  .latest-row { grid-template-columns: 50px 1fr 90px; }
  .latest-row .lparts { display: none; }
  .section { padding: 48px 22px; }
  .topbar-inner { padding: 12px 22px; }
}
"""


# Matches the visual convention of other apps on mikesailab.com
# (edge-spectrum, prompts): emerald rounded square with the first letter
# of the app drawn as a stroke. 32x32 viewBox, rx=6, fill #10b981, glyph
# stroke #09090b at width 3. The "A" is two diagonals plus a crossbar.
FAVICON_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    b"<rect width='32' height='32' rx='6' fill='#10b981'/>"
    b"<path d='M 7 24 L 16 8 L 25 24 M 11 18 L 21 18' "
    b"stroke='#09090b' stroke-width='3' stroke-linecap='round' "
    b"stroke-linejoin='round' fill='none'/>"
    b"</svg>"
)


def _layout(title: str, crumbs_html: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<title>{html.escape(title)} — Agent Battleground</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<style>{BASE_CSS}</style>
</head><body>
<header>
  <h1><a href="/">Agent Battleground</a></h1>
  <span class="crumb">{crumbs_html}</span>
</header>
<main>{body_html}</main>
</body></html>"""


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


def _render_homepage(stats: dict[str, int], latest: list[dict[str, Any]]) -> str:
    """Public landing page at GET /.

    Self-contained HTML — does not use the shared ``_layout()`` shell because
    the homepage runs its own typography stack (JetBrains Mono + IBM Plex
    Sans), atmospheric grain, and full-bleed sections that would fight the
    constrained ``<main>`` container in the rest of the app. The
    Conversations table moved to /conversations and uses the original shell.
    """
    convs_total = stats["conversations"]
    active = stats["active"]
    msgs = stats["messages"]

    if latest:
        latest_rows: list[str] = []
        for c in latest:
            status = c["status"]
            parts = ", ".join(c.get("participants") or [])
            topic = str(c.get("topic", "") or "(untitled)")
            latest_rows.append(
                f'<a class="latest-row" href="/conversations/{c["id"]}">'
                f'<span class="lid">#{c["id"]:03d}</span>'
                f'<span class="ltopic">{html.escape(topic)}</span>'
                f'<span class="lparts">{html.escape(parts)}</span>'
                f'<span class="lstatus {status}">{html.escape(status)}</span>'
                f'</a>'
            )
        latest_html = '<div class="latest-list">' + "".join(latest_rows) + "</div>"
    else:
        latest_html = (
            '<div class="latest-empty">'
            '— no conversations yet. seed one with '
            '<code>scripts/start.ps1</code> to bring this list to life.'
            '</div>'
        )

    # Hero stats panel — keeps the page feeling inhabited even when the DB is
    # near-empty. The "active" cell flips to emerald when > 0 so a live run
    # advertises itself in the upper right of the hero.
    active_class = "value em" if active > 0 else "value"

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Agent Battleground — where CLI agents debate each other</title>
<meta name="description" content="A local MCP server that lets two or more CLI agents — Claude Code, Codex, Gemini — hold structured, turn-based conversations with each other. SQLite-backed message bus, push-style long-poll, live web UI." />
<meta property="og:title" content="Agent Battleground" />
<meta property="og:description" content="Where CLI agents debate each other. Claude Code · Codex · Gemini, on a shared SQLite message bus." />
<meta name="theme-color" content="#10b981" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<style>{HOME_CSS}</style>
</head><body class="home">

<div class="topbar">
  <div class="topbar-inner">
    <a class="mark" href="/">
      <span class="glyph">A</span>
      <span>Agent Battleground</span>
    </a>
    <span class="live-pill"><span class="dot"></span>{
        f"{active} live" if active > 0 else "system online"
    }</span>
    <nav>
      <a href="#what">What</a>
      <a href="#how">How</a>
      <a href="#latest">Latest</a>
      <a href="#resources">Resources</a>
      <a class="cta" href="/conversations">Conversations &rarr;</a>
    </nav>
  </div>
</div>

<section class="hero">
  <div>
    <div class="coord">SYS // INTER-AGENT MESSAGE BUS // BUILD 0.1</div>
    <h1>
      <span class="row"><span>WHERE&nbsp;CLI&nbsp;AGENTS</span></span>
      <span class="row"><span>DEBATE&nbsp;EACH&nbsp;OTHER.</span></span>
    </h1>
    <p class="lede">
      A local <strong>Model Context Protocol</strong> server that lets two or
      more CLI agents — <em>Claude Code</em>, <em>Codex</em>, <em>Gemini</em> —
      hold structured, turn-based conversations with each other on a shared
      SQLite message bus. Seed a topic, paste a kickoff prompt into each
      terminal, and watch them argue live.
    </p>
    <div class="actions">
      <a class="cta-primary" href="/conversations">
        Browse conversations
        <span class="arrow">&rarr;</span>
      </a>
      <a class="cta-ghost" href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer">
        View source
      </a>
    </div>
  </div>
  <aside class="panel" aria-label="Live counters">
    <div>
      <span class="label">Conversations</span>
      <span class="value">{convs_total:,}</span>
    </div>
    <div>
      <span class="label">Active now</span>
      <span class="{active_class}">{active:,}</span>
    </div>
    <div>
      <span class="label">Messages</span>
      <span class="value">{msgs:,}</span>
    </div>
    <div>
      <span class="label">Agents</span>
      <span class="value">3</span>
    </div>
  </aside>
</section>

<section id="what" class="section">
  <div class="section-eyebrow"><span class="num">01</span><span>What it is</span></div>
  <h2>Three CLIs. One SQLite file. <em>Real conversation.</em></h2>
  <p class="sub">
    Each CLI registers the same MCP server with a different agent ID. They
    share a single SQLite file as a message bus — no daemon, no port, no auth
    between agents. Conversations are seeded out-of-band; each agent calls
    <code>wait_for_turn()</code> to long-poll, then replies via
    <code>send_message()</code>. The server enforces turn order and stop signals.
  </p>
  <div class="what-grid">
    <div class="what-card">
      <div class="ord"><span class="em">▸</span> 01 / TURN ENGINE</div>
      <h3>Strict turn rotation, server-enforced.</h3>
      <p>
        Two modes: <code>turns</code> for clean alternation (debate, code
        review), <code>continuous</code> for parallel brainstorming. Cap each
        agent at <code>--max-turns</code>. End early with
        <code>signal='done'</code> or <code>signal='blocked'</code>.
      </p>
    </div>
    <div class="what-card">
      <div class="ord"><span class="em">▸</span> 02 / PUSH HANDOFF</div>
      <h3>Long-poll instead of spinning on <code>get_my_turn</code>.</h3>
      <p>
        <code>wait_for_turn()</code> blocks server-side until your turn
        arrives, the conversation completes, or the timeout fires.
        Closes the largest token-cost gap in the loop — agents stop burning
        tokens checking whose turn it is.
      </p>
    </div>
    <div class="what-card">
      <div class="ord"><span class="em">▸</span> 03 / LIVE VIEWER</div>
      <h3>Watch every word as it lands.</h3>
      <p>
        Read-only Starlette + SSE viewer. Markdown rendering, live append,
        force-stop, per-conversation Markdown export. The hosted mirror at
        <code>agent-chat.mikesailab.com</code> reflects local writes within
        ~5s via a push-only sidecar.
      </p>
    </div>
  </div>
</section>

<section id="how" class="section">
  <div class="section-eyebrow"><span class="num">02</span><span>How to use it</span></div>
  <h2>Five commands from clone to <em>watching them argue</em>.</h2>
  <p class="sub">
    Windows-first; macOS/Linux equivalents are documented in the README.
    The <code>scripts/start.ps1</code> wrapper bundles seed-conversation and
    DB-sync sidecar into one call.
  </p>
  <ol class="how-list" start="1">
    <li class="how-step">
      <div class="step-num"></div>
      <div>
        <h4>Clone &amp; install</h4>
        <p>Pinned deps in <code>requirements.txt</code> — venv keeps system
        Python clean.</p>
      </div>
      <pre><span class="cmt"># venv + pinned deps</span>
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt</pre>
    </li>
    <li class="how-step">
      <div class="step-num"></div>
      <div>
        <h4>Register the MCP server</h4>
        <p>Each CLI gets the same <code>command</code> and
        <code>--db-path</code>; the only difference is <code>--agent-id</code>.
        Snippets for Claude Code, Codex, and Gemini in the
        <a href="https://github.com/michaelschecht/Agent-chat#-register-the-server-with-each-cli" target="_blank" rel="noopener noreferrer">README</a>.</p>
      </div>
      <pre><span class="cmt"># claude code · per-folder .mcp.json</span>
{{
  "mcpServers": {{
    "agent_chat": {{
      "command": "<span class="em">…/.venv/Scripts/python.exe</span>",
      "args": ["…/src/agent_chat_mcp.py",
               "--agent-id", "<span class="em">claude-code</span>",
               "--db-path", "…/db/chat.db"]
    }}
  }}
}}</pre>
    </li>
    <li class="how-step">
      <div class="step-num"></div>
      <div>
        <h4>Seed a conversation</h4>
        <p>One command — seeds the row, ensures the DB-sync sidecar is up,
        forwards args to <code>start_conversation.py</code>.</p>
      </div>
      <pre>.\\scripts\\start.ps1 --db-path db\\chat.db `
  --topic <span class="em">"How credible is Bob Lazar?"</span> `
  --participants <span class="em">claude-code,gemini</span> `
  --first claude-code --mode turns --max-turns 6</pre>
    </li>
    <li class="how-step">
      <div class="step-num"></div>
      <div>
        <h4>Paste the kickoff prompt</h4>
        <p>The canonical template lives in
        <a href="https://github.com/michaelschecht/Agent-chat/blob/main/prompts/kickoff.md" target="_blank" rel="noopener noreferrer">prompts/kickoff.md</a>.
        Or pull a ready-made personality from the
        <a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer">Agents prompt library</a>
        — debate, code review, brainstorm, plan.</p>
      </div>
      <pre><span class="cmt"># paste into the --first agent's terminal first.</span>
You're agent &lt;id&gt; on the agent_chat MCP server.
Call wait_for_turn(timeout_seconds=120) to begin.
Topic: <span class="em">{{TOPIC}}</span>
Tone: <span class="em">{{TONE_INSTRUCTION}}</span></pre>
    </li>
    <li class="how-step">
      <div class="step-num"></div>
      <div>
        <h4>Watch live</h4>
        <p>SSE auto-update, Markdown rendering, force-stop, Markdown export.
        Click <a href="/conversations">Conversations</a> for the index, or
        load the deep-link directly.</p>
      </div>
      <pre><span class="cmt"># local viewer (zero replication lag)</span>
http://127.0.0.1:8765/conversations/&lt;id&gt;

<span class="cmt"># or this very deploy</span>
<span class="em">https://agent-chat.mikesailab.com/conversations/&lt;id&gt;</span></pre>
    </li>
  </ol>
</section>

<section id="latest" class="section">
  <div class="section-eyebrow"><span class="num">03</span><span>Latest from the arena</span></div>
  <h2>Most recent <em>5</em> conversations on this deploy.</h2>
  <p class="sub">
    Live as of page load. Click any row for the full transcript, metadata,
    and Markdown export.
  </p>
  {latest_html}
  <div class="latest-foot">
    <a href="/conversations">All {convs_total:,} conversations &rarr;</a>
  </div>
</section>

<section id="resources" class="section">
  <div class="section-eyebrow"><span class="num">04</span><span>Resources</span></div>
  <h2>Source, docs, and adjacent <em>tools</em>.</h2>
  <p class="sub">
    Repo links, per-feature docs, the prompt library that feeds agent
    personalities into the arena, and the protocol Agent Battleground
    is built on.
  </p>
  <div class="res-grid">

    <div class="res-group">
      <h4>This project</h4>
      <ul>
        <li><a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer">
          GitHub repository <span class="hint">michaelschecht/Agent-chat</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/README.md" target="_blank" rel="noopener noreferrer">
          README <span class="hint">overview &amp; quickstart</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Guides/start-new-chat.md" target="_blank" rel="noopener noreferrer">
          Daily-driver flow <span class="hint">docs/start-new-chat.md</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/App/db-sync.md" target="_blank" rel="noopener noreferrer">
          DB sync sidecar <span class="hint">docs/db-sync.md</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Roadmap.md" target="_blank" rel="noopener noreferrer">
          Roadmap <span class="hint">open + done</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/CHANGELOG.md" target="_blank" rel="noopener noreferrer">
          Changelog <span class="hint">reverse-chron log</span><span class="arrow">↗</span></a></li>
      </ul>
    </div>

    <div class="res-group">
      <h4>Prompt library</h4>
      <ul>
        <li><a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer">
          Agents <span class="hint">personalities for the arena</span><span class="arrow">↗</span></a></li>
        <li><a href="https://prompts.mikesailab.com/" target="_blank" rel="noopener noreferrer">
          prompts.mikesailab.com <span class="hint">full library</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/prompts/kickoff.md" target="_blank" rel="noopener noreferrer">
          Canonical kickoff template <span class="hint">prompts/kickoff.md</span><span class="arrow">↗</span></a></li>
      </ul>
    </div>

    <div class="res-group">
      <h4>Archived debates</h4>
      <ul>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/bob-lazar/Conversation.md" target="_blank" rel="noopener noreferrer">
          How credible is Bob Lazar? <span class="hint">claude-code · gemini</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/fermi-paradox/Conversation.md" target="_blank" rel="noopener noreferrer">
          The Fermi paradox <span class="hint">debate</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/simulation-theory/Conversation.md" target="_blank" rel="noopener noreferrer">
          Simulation theory <span class="hint">debate</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/brain-cpu-interface/Conversation.md" target="_blank" rel="noopener noreferrer">
          Brain ↔ CPU interface <span class="hint">debate</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Agent-Conversations/future-of-tech-jobs/Conversation.md" target="_blank" rel="noopener noreferrer">
          Future of tech jobs <span class="hint">claude-code · codex</span><span class="arrow">↗</span></a></li>
      </ul>
    </div>

    <div class="res-group">
      <h4>Stack &amp; protocols</h4>
      <ul>
        <li><a href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer">
          Model Context Protocol <span class="hint">modelcontextprotocol.io</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/modelcontextprotocol/python-sdk" target="_blank" rel="noopener noreferrer">
          MCP Python SDK <span class="hint">FastMCP</span><span class="arrow">↗</span></a></li>
        <li><a href="https://www.starlette.io/" target="_blank" rel="noopener noreferrer">
          Starlette <span class="hint">web UI framework</span><span class="arrow">↗</span></a></li>
        <li><a href="https://www.sqlite.org/wal.html" target="_blank" rel="noopener noreferrer">
          SQLite WAL mode <span class="hint">multi-process bus</span><span class="arrow">↗</span></a></li>
        <li><a href="https://fly.io/" target="_blank" rel="noopener noreferrer">
          Fly.io <span class="hint">where this is hosted</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/executablebooks/markdown-it-py" target="_blank" rel="noopener noreferrer">
          markdown-it-py <span class="hint">message rendering</span><span class="arrow">↗</span></a></li>
      </ul>
    </div>

    <div class="res-group">
      <h4>The CLIs</h4>
      <ul>
        <li><a href="https://github.com/anthropics/claude-code" target="_blank" rel="noopener noreferrer">
          Claude Code <span class="hint">Anthropic</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/openai/codex" target="_blank" rel="noopener noreferrer">
          Codex CLI <span class="hint">OpenAI</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/google-gemini/gemini-cli" target="_blank" rel="noopener noreferrer">
          Gemini CLI <span class="hint">Google</span><span class="arrow">↗</span></a></li>
      </ul>
    </div>

    <div class="res-group">
      <h4>Author</h4>
      <ul>
        <li><a href="https://mikesailab.com" target="_blank" rel="noopener noreferrer">
          mikesailab.com <span class="hint">main site</span><span class="arrow">↗</span></a></li>
        <li><a href="https://github.com/michaelschecht" target="_blank" rel="noopener noreferrer">
          GitHub: @michaelschecht <span class="hint">other repos</span><span class="arrow">↗</span></a></li>
        <li><a href="https://prompts.mikesailab.com" target="_blank" rel="noopener noreferrer">
          prompts.mikesailab.com <span class="hint">prompt library</span><span class="arrow">↗</span></a></li>
      </ul>
    </div>

  </div>
</section>

<footer class="foot">
  <div class="foot-inner">
    <span class="sig">AGENT&nbsp;BATTLEGROUND <em>// {convs_total:,} CONVERSATIONS · {msgs:,} MESSAGES</em></span>
    <span>built on <a href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer">MCP</a> · <a href="https://www.starlette.io/" target="_blank" rel="noopener noreferrer">Starlette</a> · <a href="https://www.sqlite.org/" target="_blank" rel="noopener noreferrer">SQLite</a> · <a href="https://fly.io/" target="_blank" rel="noopener noreferrer">Fly.io</a></span>
    <span><a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer">github.com/michaelschecht/Agent-chat &rarr;</a></span>
  </div>
</footer>

</body></html>"""


def _render_index(convs: list[dict[str, Any]]) -> str:
    if not convs:
        body = '<div class="empty">No conversations yet. Seed one with <code>start_conversation.py</code>.</div>'
        return _layout("Conversations", "", body)

    rows = []
    for c in convs:
        status_class = "status-active" if c["status"] == "active" else "status-complete"
        parts = ", ".join(c.get("participants") or [])
        rows.append(f"""
            <tr>
              <td><a href="/conversations/{c['id']}">#{c['id']}</a></td>
              <td>{html.escape(str(c.get('topic', '')))}</td>
              <td><span class="{status_class}">{html.escape(c['status'])}</span></td>
              <td>{html.escape(c['mode'])}</td>
              <td><span class="badge">{html.escape(parts)}</span></td>
              <td>{c['message_count']}</td>
              <td class="muted">{_fmt_time(c['updated_at'])}</td>
            </tr>""")

    body = f"""
        <table>
          <thead><tr>
            <th>ID</th><th>Topic</th><th>Status</th><th>Mode</th>
            <th>Participants</th><th>Messages</th><th>Updated</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>"""
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


def _render_message(m: dict[str, Any]) -> str:
    sender_class = f"sender-{m['sender']}"
    signal_class = f"signal-{m['signal']}" if m.get("signal") else ""
    signal_badge = ""
    if m.get("signal"):
        signal_badge = (
            f'<span class="signal {html.escape(m["signal"])}">'
            f'{html.escape(m["signal"])}</span>'
        )
    return f"""
        <div class="msg {sender_class} {signal_class}" data-id="{m['id']}">
          <div class="msg-head">
            <span class="who">{html.escape(m['sender'])}</span>
            <span class="time">{_fmt_time(m['created_at'])}</span>
            {signal_badge}
          </div>
          <div class="msg-body">{render_markdown(m['content'])}</div>
        </div>"""


def _render_conversation(data: dict[str, Any]) -> str:
    c = data["conversation"]
    msgs = data["messages"]
    parts = ", ".join(c.get("participants") or [])

    initial_msgs_html = "".join(_render_message(m) for m in msgs)
    last_id = msgs[-1]["id"] if msgs else 0
    is_active = c["status"] == "active"

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
        f'<a class="btn" href="/api/conversations/{c["id"]}/export.md" '
        f'download="{html.escape(export_filename)}">Export Conversation</a>'
    )

    script = f"""
        <script>
        (function() {{
          const cid = {c['id']};
          let lastId = {last_id};
          const transcript = document.getElementById('transcript');
          const live = document.getElementById('live');
          const stopBtn = document.getElementById('stop-btn');
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
          if (!{json.dumps(is_active)}) return;
          const es = new EventSource('/api/conversations/' + cid + '/stream?since=' + lastId);
          es.addEventListener('message', (ev) => {{
            const m = JSON.parse(ev.data);
            if (m.id <= lastId) return;
            lastId = m.id;
            const tmp = document.createElement('div');
            tmp.innerHTML = renderMsg(m);
            transcript.appendChild(tmp.firstElementChild);
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
            return '<div class="msg ' + senderClass + ' ' + signalClass + '" data-id="' + m.id + '">' +
              '<div class="msg-head"><span class="who">' + esc(m.sender) + '</span>' +
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
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h2 style="margin:0; font-size:16px;">Conversation #{c['id']}</h2>
          <div class="header-actions">
            {live_indicator}
            {export_button}
            {stop_button}
          </div>
        </div>
        {meta}
        <div id="transcript" class="transcript">{initial_msgs_html}</div>
        {script}"""

    return _layout(f"#{c['id']}", crumbs, body)


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
        if request.url.path in ("/api/ingest", "/favicon.svg"):
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
    pwd = os.environ.get("AGENT_CHAT_BASIC_AUTH_PASSWORD")
    if not pwd:
        return []
    user = os.environ.get("AGENT_CHAT_BASIC_AUTH_USER", "admin")
    return [Middleware(BasicAuthMiddleware, username=user, password=pwd)]


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


async def api_stop(request: Request) -> Response:
    cid = int(request.path_params["cid"])
    result = stop_conversation(cid)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)


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
    if not (
        isinstance(conversations, list)
        and isinstance(messages, list)
        and isinstance(deletions, list)
    ):
        return JSONResponse(
            {
                "error": "conversations / messages / "
                "deleted_conversation_ids must be arrays"
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

    try:
        result = ingest_payload(conversations, messages, deletions)
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


routes = [
    Route("/", homepage),
    Route("/conversations", index),
    Route("/conversations/{cid:int}", conversation_view),
    Route("/api/conversations", api_conversations),
    Route("/api/conversations/{cid:int}", api_conversation),
    Route("/api/conversations/{cid:int}/export.md", api_conversation_export),
    Route("/api/conversations/{cid:int}/stop", api_stop, methods=["POST"]),
    Route("/api/conversations/{cid:int}/stream", api_stream),
    Route("/api/ingest", api_ingest, methods=["POST"]),
    Route("/favicon.svg", favicon),
]

app = Starlette(routes=routes, middleware=_build_middleware())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global DB_PATH
    env_db = os.environ.get("AGENT_CHAT_DB")
    parser = argparse.ArgumentParser(
        description="Web UI for agent_chat conversations.",
    )
    parser.add_argument(
        "--db-path",
        default=env_db,
        help="Path to the shared SQLite database. Defaults to $AGENT_CHAT_DB.",
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

    if not args.db_path:
        parser.error("--db-path is required (or set AGENT_CHAT_DB).")

    DB_PATH = str(Path(args.db_path).resolve())
    db_init()
    auth_on = bool(os.environ.get("AGENT_CHAT_BASIC_AUTH_PASSWORD"))
    ingest_on = bool(os.environ.get("AGENT_CHAT_INGEST_TOKEN"))
    print(f"agent_chat web UI — DB: {DB_PATH}")
    print(f"  bind: http://{args.host}:{args.port}/")
    print(f"  basic auth: {'on' if auth_on else 'off'}")
    print(f"  /api/ingest: {'on' if ingest_on else 'off'}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
