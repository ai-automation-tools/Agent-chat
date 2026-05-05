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
}
.btn:hover { background: var(--panel); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger {
  border-color: var(--bad);
  color: var(--bad);
}
.btn-danger:hover { background: var(--bad); color: var(--bg); }
.header-actions { display: flex; gap: 12px; align-items: center; }
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
<title>{html.escape(title)} — agent_chat</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<style>{BASE_CSS}</style>
</head><body>
<header>
  <h1><a href="/">agent_chat</a></h1>
  <span class="crumb">{crumbs_html}</span>
</header>
<main>{body_html}</main>
</body></html>"""


def _fmt_time(ts: str) -> str:
    return ts.replace("T", " ").split("+")[0].split(".")[0]


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

    crumbs = f'<a href="/">Conversations</a> &rsaquo; <strong>#{c["id"]}</strong>'

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
    Route("/", index),
    Route("/conversations/{cid:int}", conversation_view),
    Route("/api/conversations", api_conversations),
    Route("/api/conversations/{cid:int}", api_conversation),
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
