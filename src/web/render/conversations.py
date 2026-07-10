"""The /conversations browser + conversation transcript rendering."""

from __future__ import annotations

import html
import json
from typing import Any

from orchestrator.export import (
    export_filename as _export_filename,
    export_zip_filename as _export_zip_filename,
    fmt_time as _fmt_time,
)

from web.assets import HIGHLIGHT_JS_HEAD, _CAST_CSS, _CONV_CSS
from web.db import list_conversations
from web.render.common import _layout, _pm_svg, render_markdown


def _conversations_rail(convs: list[dict[str, Any]], active_cid: int | None) -> str:
    """Left filter rail for the conversations browser."""
    total = len(convs)
    active = sum(1 for c in convs if c.get("status") == "active")
    debates = sum(1 for c in convs if c.get("preset") == "debate")
    three_agent = sum(1 for c in convs if len(c.get("participants") or []) >= 3)
    agents = sorted({
        str(p)
        for c in convs
        for p in (c.get("participants") or [])
        if str(p).strip()
    })
    filters = [
        ("all", "All conversations", total),
        ("active", "Active", active),
        ("debate", "Debates", debates),
        ("multi", "Three-agent", three_agent),
        ("complete", "Archived", total - active),
    ]
    filter_buttons = "".join(
        '<button type="button" class="cv-filter'
        + (" active" if key == "all" else "")
        + f'" data-filter="{html.escape(key, quote=True)}">'
        + f'{html.escape(label)}<span class="cv-filter-count">{count}</span></button>'
        for key, label, count in filters
    )
    agent_buttons = "".join(
        f'<button type="button" class="cv-filter" data-agent="{html.escape(agent, quote=True)}">'
        f'{html.escape(agent)}</button>'
        for agent in agents[:8]
    )
    count_badge = f'<span class="cv-count">{len(convs)}</span>' if convs else ""
    return (
        '<aside class="cv-rail">'
        f'<div class="cv-railhead"><h2>Conversations</h2>{count_badge}</div>'
        f'<div class="cv-search">{_pm_svg("search")}'
        '<input type="text" id="cv-search" placeholder="Search conversations" autocomplete="off"></div>'
        f'<div class="cv-rail-section"><div class="cv-rail-label">Views</div>{filter_buttons}</div>'
        f'<div class="cv-rail-section"><div class="cv-rail-label">Participants</div>{agent_buttons}</div>'
        '<div class="cv-railfoot"><a class="btn btn-primary" href="/orchestrate">+ New conversation</a></div>'
        '</aside>'
    )


def _conv_rail_js() -> str:
    """Conversation browser behaviour: search, saved filters, and row delete."""
    return """
    <script>
    (function() {
      const root = document.querySelector('.cv2');
      if (!root) return;
      const search = document.getElementById('cv-search');
      const noMatch = document.getElementById('cv-nomatch');
      const rows = [...root.querySelectorAll('.cv-row')];
      let activeFilter = 'all';
      let activeAgent = '';
      function applyFilters() {
        const q = search.value.trim().toLowerCase();
        let shown = 0;
        rows.forEach(it => {
          const qHit = !q || (it.dataset.search || '').includes(q);
          const fHit =
            activeFilter === 'all' ||
            (activeFilter === 'active' && it.dataset.status === 'active') ||
            (activeFilter === 'complete' && it.dataset.status !== 'active') ||
            (activeFilter === 'debate' && it.dataset.preset === 'debate') ||
            (activeFilter === 'multi' && Number(it.dataset.participantCount || '0') >= 3);
          const aHit = !activeAgent || (it.dataset.participants || '').split('|').includes(activeAgent);
          const vis = qHit && fHit && aHit;
          it.hidden = !vis;
          it.style.display = vis ? '' : 'none';
          if (vis) shown++;
        });
        if (noMatch) noMatch.style.display = shown === 0 ? 'block' : 'none';
      }
      if (search) search.addEventListener('input', applyFilters);
      root.querySelectorAll('.cv-filter[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
          root.querySelectorAll('.cv-filter[data-filter]').forEach(b => b.classList.toggle('active', b === btn));
          activeFilter = btn.dataset.filter || 'all';
          applyFilters();
        });
      });
      root.querySelectorAll('.cv-filter[data-agent]').forEach(btn => {
        btn.addEventListener('click', () => {
          const same = activeAgent === btn.dataset.agent;
          activeAgent = same ? '' : (btn.dataset.agent || '');
          root.querySelectorAll('.cv-filter[data-agent]').forEach(b => b.classList.toggle('active', !same && b === btn));
          applyFilters();
        });
      });
      root.querySelectorAll('.cv-del').forEach(btn => {
        btn.addEventListener('click', async (ev) => {
          ev.preventDefault(); ev.stopPropagation();
          const cid = btn.dataset.cid;
          const topic = btn.dataset.topic || '(untitled)';
          const msgs = btn.dataset.msgCount || '0';
          if (!confirm('Permanently delete conversation #' + cid + '?\\n\\nTopic: ' + topic +
                       '\\nMessages: ' + msgs + '\\n\\nThis deletes the row and all its messages. ' +
                       'The local sidecar applies the deletion within ~5s. This cannot be undone.')) return;
          btn.disabled = true;
          try {
            const res = await fetch('/api/conversations/' + cid + '/delete', { method: 'POST' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const item = btn.closest('.cv-row');
            if (item && item.classList.contains('active')) { location.href = '/conversations'; return; }
            if (item) item.remove();
          } catch (err) { alert('Delete failed: ' + err.message); btn.disabled = false; }
        });
      });
      root.querySelectorAll('.cv-stop').forEach(btn => {
        btn.addEventListener('click', async () => {
          const cid = btn.dataset.cid;
          if (!confirm('End conversation #' + cid + '? Both agents will see status="complete" on their next call.')) return;
          btn.disabled = true;
          btn.textContent = 'Stopping...';
          try {
            const res = await fetch('/api/conversations/' + cid + '/stop', { method: 'POST' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            location.reload();
          } catch (err) {
            alert('Stop failed: ' + err.message);
            btn.disabled = false;
            btn.textContent = 'Stop';
          }
        });
      });
      applyFilters();
    })();
    </script>"""


def _conv_personas(c: dict[str, Any]) -> dict[str, Any]:
    raw = c.get("participant_personas")
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _render_conversations_table(
    convs: list[dict[str, Any]],
    active_cid: int | None,
) -> str:
    if not convs:
        return (
            '<section class="cv-center"><div class="cv-empty">'
            + _pm_svg("chat")
            + '<p>No conversations yet.<br>Seed one and it shows up here live.</p>'
            '<a class="btn btn-primary" href="/orchestrate">+ New conversation</a>'
            '</div></section>'
        )

    rows: list[str] = []
    for c in convs:
        cid = int(c["id"])
        status = str(c.get("status") or "")
        topic = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
        participants = [str(p) for p in (c.get("participants") or [])]
        personas = _conv_personas(c)
        cast_names: list[str] = []
        for p in participants:
            entry = personas.get(p)
            cast_names.append(str(entry.get("persona_name")) if isinstance(entry, dict) and entry.get("persona_name") else p)
        chips = "".join(f'<span class="cv-chip">{html.escape(name)}</span>' for name in cast_names[:2])
        if len(cast_names) > 2:
            chips += f'<span class="cv-chip">+{len(cast_names) - 2}</span>'
        updated = _fmt_time(c.get("updated_at"))
        msgc = int(c.get("message_count") or 0)
        active = " active" if cid == active_cid else ""
        search_blob = html.escape(" ".join([topic, str(cid), " ".join(participants), " ".join(cast_names)]).lower(), quote=True)
        participant_blob = html.escape("|".join(participants), quote=True)
        rows.append(
            f'<div class="cv-row{active}" '
            f'data-search="{search_blob}" data-status="{html.escape(status, quote=True)}" '
            f'data-preset="{html.escape(str(c.get("preset") or ""), quote=True)}" '
            f'data-participant-count="{len(participants)}" data-participants="{participant_blob}" '
            f'title="{html.escape(topic, quote=True)}">'
            f'<a class="cv-row-content" href="/conversations/{cid}">'
            f'<span class="cv-id">{cid}</span>'
            '<span>'
            f'<span class="cv-row-topic">{html.escape(topic)}</span>'
            f'<span class="cv-row-sub">#{cid} · {msgc} msg · {html.escape(updated)}</span>'
            '</span>'
            f'<span class="cv-cast-chips">{chips}</span>'
            f'<span class="cv-status-pill {html.escape(status)}"><span class="cv-status cv-{html.escape(status)}"></span>{html.escape(status or "unknown")}</span>'
            f'<span class="cv-msgcount">{msgc}</span>'
            '</a>'
            f'<button class="cv-del" data-cid="{cid}" data-topic="{html.escape(topic, quote=True)}" '
            f'data-msg-count="{msgc}" title="Delete conversation #{cid}" aria-label="Delete conversation #{cid}">&times;</button>'
            '</div>'
        )

    return (
        '<section class="cv-center">'
        '<header class="cv-chead">'
        '<h1>All conversations</h1>'
        '<select class="cv-sort" aria-label="Sort conversations"><option>Newest first</option></select>'
        '<a class="btn" href="/api/conversations">JSON index</a>'
        '</header>'
        '<div class="cv-table-head"><span></span><span>Topic</span><span>Cast</span><span>Status</span><span>Messages</span></div>'
        f'<div class="cv-table">{"".join(rows)}'
        '<div class="cv-nomatch" id="cv-nomatch">No matches</div></div>'
        '</section>'
    )


def _render_conversation_side_detail(data: dict[str, Any] | None) -> str:
    if data is None:
        return (
            '<aside class="cv-detail"><div class="cv-detail-empty">'
            + _pm_svg("doc")
            + '<p>Select a conversation to preview it,<br>or create a new one.</p>'
            '<a class="btn btn-primary" href="/orchestrate">+ New conversation</a>'
            '</div></aside>'
        )

    c = data["conversation"]
    msgs = data["messages"]
    cid = int(c["id"])
    topic = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
    participants = [str(p) for p in (c.get("participants") or [])]
    personas = _conv_personas(c)
    cast_lines: list[str] = []
    for p in participants:
        entry = personas.get(p)
        name = str(entry.get("persona_name")) if isinstance(entry, dict) and entry.get("persona_name") else p
        cast_lines.append(f'{html.escape(name)} <span class="muted">as {html.escape(p)}</span>')
    cast_html = "<br>".join(cast_lines) if cast_lines else "—"
    msgc = len(msgs)
    last_msg = msgs[-1] if msgs else None
    preview = ""
    if last_msg:
        content = " ".join(str(last_msg.get("content") or "").split())
        if len(content) > 360:
            content = content[:357].rstrip() + "..."
        preview = (
            '<div class="cv-preview">'
            f'<span class="muted">{html.escape(str(last_msg.get("sender") or ""))} · {_fmt_time(last_msg.get("created_at"))}</span>'
            f'<p>{html.escape(content)}</p></div>'
        )
    else:
        preview = '<div class="cv-preview"><span class="muted">No messages yet.</span></div>'
    status = str(c.get("status") or "")
    status_class = " active" if status == "active" else ""
    stop_button = (
        f'<button class="btn btn-danger cv-stop" type="button" data-cid="{cid}">Stop</button>'
        if status == "active" else ""
    )
    return (
        '<aside class="cv-detail"><div class="cv-side">'
        f'<span class="cv-status-pill{status_class}"><span class="cv-status cv-{html.escape(status)}"></span>{html.escape(status or "unknown")}</span>'
        f'<h2>{html.escape(topic)}</h2>'
        '<div class="cv-side-stats">'
        f'<div class="cv-side-stat"><b>{msgc}</b><span>Messages</span></div>'
        f'<div class="cv-side-stat"><b>{len(participants)}</b><span>Agents</span></div>'
        f'<div class="cv-side-stat"><b>{html.escape(str(c.get("max_turns") or "—"))}</b><span>Turns</span></div>'
        '</div>'
        f'<div><div class="cv-side-label">Cast</div><p class="cv-side-text">{cast_html}</p></div>'
        f'<div><div class="cv-side-label">Last message preview</div>{preview}</div>'
        '<div class="cv-side-actions">'
        f'<a class="btn btn-primary" href="/conversations/{cid}?fullscreen=1">Full screen</a>'
        f'<a class="btn" href="/api/conversations/{cid}/export.md">Export MD</a>'
        f'<a class="btn" href="/api/conversations/{cid}/export.zip">Export ZIP</a>'
        f'{stop_button}'
        '</div>'
        '</div></aside>'
    )


def _render_conversations_browser(
    convs: list[dict[str, Any]],
    selected: dict[str, Any] | None,
) -> str:
    active_cid = int(selected["conversation"]["id"]) if selected else None
    rail = _conversations_rail(convs, active_cid)
    center = _render_conversations_table(convs, active_cid)
    detail = _render_conversation_side_detail(selected)
    body = f'<div class="cv2">{rail}{center}{detail}</div>{_conv_rail_js()}'
    return _layout("Conversations", "", body, head_extras=_CONV_CSS)


def _render_index(convs: list[dict[str, Any]]) -> str:
    return _render_conversations_browser(convs, None)


def _render_conversation_not_found(cid: int, convs: list[dict[str, Any]]) -> str:
    """Friendly 404 for a missing conversation id — rendered inside the console
    (with the rail) so the visitor can pick another conversation rather than
    landing on a dead-end error page."""
    rail = _conversations_rail(convs, None)
    center = (
        '<div class="cv-main"><div class="cv-empty">'
        + _pm_svg("chat") +
        f"<p>Conversation #{cid} doesn't exist.<br>"
        "It may have been deleted, or the link is wrong.</p>"
        '<a class="btn btn-primary" href="/conversations">&larr; Back to conversations</a>'
        '</div></div>'
    )
    body = f'<div class="cv2">{rail}{center}</div>{_conv_rail_js()}'
    return _layout("Not found", "", body, head_extras=_CONV_CSS)


# The export renderers (_render_export_markdown / _render_export_zip and
# their helpers) moved to orchestrator.export (imported above) so the
# browser download and scripts/publish_debate.py share one implementation.


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


def _conversation_neighbors(
    convs: list[dict[str, Any]],
    cid: int,
) -> tuple[int | None, int | None]:
    """Return newer/older neighboring conversation ids from the rail order."""
    ids = [int(c["id"]) for c in convs]
    try:
        idx = ids.index(int(cid))
    except ValueError:
        return None, None
    prev_id = ids[idx - 1] if idx > 0 else None
    next_id = ids[idx + 1] if idx < len(ids) - 1 else None
    return prev_id, next_id


def _render_conversation(data: dict[str, Any],
                         all_convs: list[dict[str, Any]] | None = None,
                         fullscreen: bool = False) -> str:
    c = data["conversation"]
    if not fullscreen:
        return _render_conversations_browser(
            all_convs if all_convs is not None else list_conversations(),
            data,
        )
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

    meta = f"""
        <dl class="meta-grid">
          <dt>Topic</dt><dd>{html.escape(str(c.get('topic', '')))}</dd>
          <dt>Conversation</dt><dd>#{c['id']}</dd>
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
    convs_for_nav = all_convs if all_convs is not None else list_conversations()
    prev_id, next_id = _conversation_neighbors(convs_for_nav, int(c["id"]))
    full_screen_button = (
        f'<a class="btn" href="/conversations/{c["id"]}?fullscreen=1">'
        'Full screen</a>'
    )
    if fullscreen:
        prev_button = (
            f'<a class="btn" href="/conversations/{prev_id}?fullscreen=1">Previous</a>'
            if prev_id is not None
            else '<span class="btn btn-disabled">Previous</span>'
        )
        next_button = (
            f'<a class="btn" href="/conversations/{next_id}?fullscreen=1">Next</a>'
            if next_id is not None
            else '<span class="btn btn-disabled">Next</span>'
        )
        full_screen_button = (
            '<span class="cv-fullnav">'
            f'{prev_button}'
            f'{next_button}'
            f'<a class="btn btn-primary" href="/conversations/{c["id"]}">'
            'Exit full screen</a>'
            '</span>'
        )
    title = str(c.get("topic") or "").strip() or f"Conversation #{c['id']}"
    title_html = html.escape(title)

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
            // Auto-scroll the content pane (the transcript lives in a scroll
            // container now, not the document body).
            const cvMain = document.getElementById('cv-main');
            if (cvMain) cvMain.scrollTop = cvMain.scrollHeight;
            else window.scrollTo(0, document.body.scrollHeight);
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

    rail = _conversations_rail(all_convs if all_convs is not None else list_conversations(), c["id"])
    center = f"""
        <div class="cv-main" id="cv-main">
        <div class="detail-head">
          <h2>{title_html}</h2>
          <div class="header-actions">
            {live_indicator}
            {full_screen_button}
            {export_button}
            {export_zip_button}
            {stop_button}
          </div>
        </div>
        {meta}
        {cast_panel}
        {kickoff_panel}
        <div id="transcript" class="transcript">{initial_msgs_html}</div>
        {script}
        </div>"""

    if fullscreen:
        rail = ""
    shell_class = "cv2 cv-fullscreen" if fullscreen else "cv2"
    body = f'<div class="{shell_class}">{rail}{center}</div>{_conv_rail_js()}'

    return _layout(title, "", body,
                   head_extras=HIGHLIGHT_JS_HEAD + _CAST_CSS + _CONV_CSS)
