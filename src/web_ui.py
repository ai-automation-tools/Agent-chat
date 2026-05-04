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
import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route


DB_PATH: str = ""
POLL_INTERVAL_SECONDS = 1.0


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


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
.msg-body { white-space: pre-wrap; word-wrap: break-word; }
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


def _layout(title: str, crumbs_html: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<title>{html.escape(title)} — agent_chat</title>
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
          <div class="msg-body">{html.escape(m['content'])}</div>
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
            const senderClass = 'sender-' + (m.sender || '');
            const signalClass = m.signal ? 'signal-' + m.signal : '';
            const signalBadge = m.signal
              ? '<span class="signal ' + esc(m.signal) + '">' + esc(m.signal) + '</span>'
              : '';
            return '<div class="msg ' + senderClass + ' ' + signalClass + '" data-id="' + m.id + '">' +
              '<div class="msg-head"><span class="who">' + esc(m.sender) + '</span>' +
              '<span class="time">' + esc(fmtTime(m.created_at)) + '</span>' + signalBadge + '</div>' +
              '<div class="msg-body">' + esc(m.content) + '</div></div>';
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
                yield {"event": "message", "data": json.dumps(m)}
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


routes = [
    Route("/", index),
    Route("/conversations/{cid:int}", conversation_view),
    Route("/api/conversations", api_conversations),
    Route("/api/conversations/{cid:int}", api_conversation),
    Route("/api/conversations/{cid:int}/stop", api_stop, methods=["POST"]),
    Route("/api/conversations/{cid:int}/stream", api_stream),
]

app = Starlette(routes=routes)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global DB_PATH
    parser = argparse.ArgumentParser(
        description="Local web UI for agent_chat conversations."
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the shared SQLite database file (same one the MCP server uses).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", default=8765, type=int, help="Port (default: 8765).")
    args = parser.parse_args()

    db = Path(args.db_path).resolve()
    if not db.exists():
        raise SystemExit(
            f"DB file does not exist: {db}\n"
            f"Seed a conversation first with start_conversation.py, "
            f"or check the --db-path argument."
        )
    DB_PATH = str(db)
    print(f"agent_chat web UI — DB: {DB_PATH}")
    print(f"  open http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
