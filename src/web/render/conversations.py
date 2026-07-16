"""The /conversations browser — a two-pane inbox: rail list + transcript reader.

Left rail: search, filter chips, sort, and the conversation list. Main pane:
the selected conversation's live transcript (or an overview when nothing is
selected). One click on a conversation reads it — there is no intermediate
preview pane. ``?fullscreen=1`` hides the rail for a distraction-free reader
with previous/next navigation.
"""

from __future__ import annotations

import html
import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any

from orchestrator.export import (
    export_filename as _export_filename,
    export_zip_filename as _export_zip_filename,
    fmt_time as _fmt_time,
)

from orchestrator.model_personas import model_persona_entries

from web.assets import HIGHLIGHT_JS_HEAD, _CAST_CSS, _CONV_CSS
from web.db import list_conversations, list_stats
from web.render.common import _conv_cast_label, _layout, _pm_svg, render_markdown
from web.security import _is_public_readonly
from web.topics import classify_topic



# Small inline stroke icons (Feather, MIT) for the reader/rail chrome — same
# shell as web.render.common._pm_svg but scoped to this page's needs.
_CV_ICONS = {
    "expand": '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>'
              '<line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>',
    "shrink": '<polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/>'
              '<line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/>',
    "prev": '<polyline points="15 18 9 12 15 6"/>',
    "next": '<polyline points="9 18 15 12 9 6"/>',
    "rail": '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
    "close": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
}

_VISUAL_PALETTE = (
    ("#10b981", "#38bdf8"),
    ("#22c55e", "#a78bfa"),
    ("#14b8a6", "#f59e0b"),
    ("#60a5fa", "#f472b6"),
    ("#34d399", "#818cf8"),
    ("#fbbf24", "#2dd4bf"),
)


def _cv_svg(name: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{_CV_ICONS[name]}</svg>'
    )


def _stable_index(value: str, modulo: int) -> int:
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:8], 16) % modulo


def _initials(value: Any, fallback: str = "AI", limit: int = 2) -> str:
    words = [
        "".join(ch for ch in part if ch.isalnum())
        for part in str(value or "").replace("_", " ").replace("-", " ").split()
    ]
    letters = [word[0].upper() for word in words if word]
    if not letters:
        letters = [ch.upper() for ch in str(fallback) if ch.isalnum()]
    return "".join(letters[:limit]) or fallback[:limit].upper()


def _visual_style(seed: str) -> str:
    a, b = _VISUAL_PALETTE[_stable_index(seed, len(_VISUAL_PALETTE))]
    return f"--cv-ink:{a};--cv-ink-2:{b};"


def _agent_display(agent_id: Any, personas: dict[str, Any] | None = None) -> str:
    persona = (personas or {}).get(str(agent_id)) or {}
    return str(persona.get("persona_name") or agent_id or "agent")


def _agent_avatar(agent_id: Any,
                  personas: dict[str, Any] | None = None,
                  class_name: str = "agent-avatar") -> str:
    agent = str(agent_id or "agent")
    label = _agent_display(agent, personas)
    initials = html.escape(_initials(label, agent))
    return (
        f'<span class="{class_name}" style="{_visual_style(agent + "|" + label)}" '
        f'aria-hidden="true">{initials}</span>'
    )


def _conversation_mark(c: dict[str, Any], personas: dict[str, Any] | None = None,
                       size: str = "rail") -> str:
    """Topic logo for a conversation: category glyph on a category-tinted tile.

    The category comes from a keyword scan of the topic (``web.topics``), so
    the same subject always gets the same logo and old rows are covered without
    a schema migration.
    """
    cid = int(c.get("id") or 0)
    topic = classify_topic(c.get("topic"))
    gid = f"cvmark-{cid}-{html.escape(size)}-{topic.slug}"
    return (
        f'<span class="cv-mark cv-mark-{html.escape(size)} cv-mark-{topic.slug}" '
        f'role="img" aria-label="{html.escape(topic.label, quote=True)}">'
        f'<svg viewBox="0 0 64 64" focusable="false">'
        f'<defs><linearGradient id="{gid}" x1="8" y1="8" x2="56" y2="56">'
        f'<stop stop-color="{topic.ink}"/><stop offset="1" stop-color="{topic.ink_2}"/>'
        f'</linearGradient></defs>'
        f'<rect x="4" y="4" width="56" height="56" rx="14" fill="url(#{gid})" opacity="0.95"/>'
        f'<g class="cv-mark-glyph" transform="translate(32 32) scale(1.28) translate(-12 -12)">'
        f'{topic.glyph}</g>'
        f'</svg></span>'
    )


def _conv_personas(c: dict[str, Any]) -> dict[str, Any]:
    raw = c.get("participant_personas")
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _short_date(ts: Any) -> str:
    """Compact ``MM-DD`` from an ISO timestamp, for the rail meta line."""
    s = str(ts or "")
    return s[5:10] if len(s) >= 10 else s


def _fmt_duration(msgs: list[dict[str, Any]]) -> str | None:
    """Human span between the first and last message, or None if < 2 msgs."""
    if len(msgs) < 2:
        return None
    try:
        a = datetime.fromisoformat(str(msgs[0]["created_at"]))
        b = datetime.fromisoformat(str(msgs[-1]["created_at"]))
    except ValueError:
        return None
    secs = max(0, int((b - a).total_seconds()))
    if secs < 90:
        return f"{secs}s"
    mins = secs / 60
    if mins < 90:
        return f"{mins:.0f} min"
    return f"{mins / 60:.1f} h"


def _fmt_tokens(msgs: list[dict[str, Any]]) -> str | None:
    """Rough token estimate (chars / 4) across all message bodies."""
    chars = sum(len(str(m.get("content") or "")) for m in msgs)
    if not chars:
        return None
    tok = chars // 4
    return f"~{tok / 1000:.1f}k tokens" if tok >= 1000 else f"~{tok} tokens"


# ---------------------------------------------------------------------------
# Rail (left pane)
# ---------------------------------------------------------------------------

def _conversations_rail(convs: list[dict[str, Any]], active_cid: int | None) -> str:
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

    chips = "".join(
        '<button type="button" class="cv-fchip'
        + (" active" if key == "all" else "")
        + f'" data-filter="{key}">{label}'
        + f'<span class="cv-fchip-n">{count}</span></button>'
        for key, label, count in (
            ("all", "All", total),
            ("active", "Active", active),
            ("debate", "Debates", debates),
            ("multi", "3-agent", three_agent),
            ("complete", "Done", total - active),
        )
    )
    agent_opts = '<option value="">All agents</option>' + "".join(
        f'<option value="{html.escape(a, quote=True)}">{html.escape(a)}</option>'
        for a in agents
    )
    sort_opts = (
        '<option value="newest">Newest first</option>'
        '<option value="oldest">Oldest first</option>'
        '<option value="updated">Recently updated</option>'
        '<option value="msgs">Most messages</option>'
    )

    items: list[str] = []
    for c in convs:
        cid = int(c["id"])
        status = str(c.get("status") or "")
        topic = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
        participants = [str(p) for p in (c.get("participants") or [])]
        cast = _conv_cast_label(c)
        msgc = int(c.get("message_count") or 0)
        is_active = " active" if cid == active_cid else ""
        search_blob = html.escape(
            " ".join([topic, str(cid), " ".join(participants), cast]).lower(),
            quote=True,
        )
        del_btn = ""
        if not _is_public_readonly():
            del_btn = (
                f'<button class="cv-del" data-cid="{cid}" data-topic="{html.escape(topic, quote=True)}" '
                f'data-msg-count="{msgc}" title="Delete conversation #{cid}" '
                f'aria-label="Delete conversation #{cid}">&times;</button>'
            )
        items.append(
            f'<div class="cv-item{is_active}" '
            f'data-id="{cid}" data-msgs="{msgc}" '
            f'data-updated="{html.escape(str(c.get("updated_at") or ""), quote=True)}" '
            f'data-search="{search_blob}" data-status="{html.escape(status, quote=True)}" '
            f'data-preset="{html.escape(str(c.get("preset") or ""), quote=True)}" '
            f'data-participant-count="{len(participants)}" '
            f'data-participants="{html.escape("|".join(participants), quote=True)}">'
            f'<a class="cv-link" href="/conversations/{cid}" '
            f'title="{html.escape(topic, quote=True)}">'
            f'<span class="cv-status cv-{html.escape(status)}"></span>'
            f'{_conversation_mark(c, _conv_personas(c), "rail")}'
            '<span class="cv-item-main">'
            f'<span class="cv-topic">{html.escape(topic)}</span>'
            f'<span class="cv-cast">{html.escape(cast)}</span>'
            f'<span class="cv-meta">#{cid} · {msgc} msg · {html.escape(_short_date(c.get("updated_at")))}</span>'
            "</span></a>"
            f"{del_btn}"
            "</div>"
        )
    list_inner = "".join(items) if items else (
        '<div class="cv-list-empty">No conversations yet.<br>'
        "Seed one and it shows up here live.</div>"
    )

    return (
        '<aside class="cv-rail">'
        '<div class="cv-railhead"><h2>Conversations</h2>'
        f'<span class="cv-count">{total}</span>'
        '<button type="button" id="cv-rail-toggle" class="icon-btn" '
        f'aria-label="Hide conversation list" title="Hide list">{_cv_svg("rail")}</button>'
        "</div>"
        f'<div class="cv-search">{_pm_svg("search")}'
        '<input type="text" id="cv-search" placeholder="Search conversations" autocomplete="off"></div>'
        f'<div class="cv-fchips">{chips}</div>'
        '<div class="cv-controls">'
        f'<select id="cv-sort" aria-label="Sort conversations">{sort_opts}</select>'
        f'<select id="cv-agent" aria-label="Filter by agent">{agent_opts}</select>'
        "</div>"
        f'<div class="cv-list">{list_inner}'
        '<div class="cv-nomatch" id="cv-nomatch">No matches</div></div>'
        '<div class="cv-railfoot"><a class="btn btn-primary" href="/orchestrate">+ New conversation</a></div>'
        "</aside>"
        '<button type="button" id="cv-rail-open" class="icon-btn" '
        f'aria-label="Show conversation list" title="Show list">{_cv_svg("rail")}</button>'
    )


def _conv_rail_js() -> str:
    """Rail behaviour: search, filter chips, agent filter, sort, collapse, delete."""
    return """
    <script>
    (function() {
      const root = document.querySelector('.cv2');
      if (!root) return;
      const LSORT = 'agentchat.cv.sort', LRAIL = 'agentchat.cv.rail';
      const list = root.querySelector('.cv-list');
      const search = document.getElementById('cv-search');
      const noMatch = document.getElementById('cv-nomatch');
      const sortSel = document.getElementById('cv-sort');
      const agentSel = document.getElementById('cv-agent');
      const items = () => [...root.querySelectorAll('.cv-item')];
      let activeFilter = 'all';

      function applyFilters() {
        const q = (search && search.value.trim().toLowerCase()) || '';
        const ag = (agentSel && agentSel.value) || '';
        let shown = 0;
        items().forEach(it => {
          const qHit = !q || (it.dataset.search || '').includes(q);
          const fHit =
            activeFilter === 'all' ||
            (activeFilter === 'active' && it.dataset.status === 'active') ||
            (activeFilter === 'complete' && it.dataset.status !== 'active') ||
            (activeFilter === 'debate' && it.dataset.preset === 'debate') ||
            (activeFilter === 'multi' && Number(it.dataset.participantCount || '0') >= 3);
          const aHit = !ag || (it.dataset.participants || '').split('|').includes(ag);
          const vis = qHit && fHit && aHit;
          it.style.display = vis ? '' : 'none';
          if (vis) shown++;
        });
        if (noMatch) noMatch.style.display = shown === 0 ? 'block' : 'none';
      }

      function applySort() {
        if (!list || !sortSel) return;
        const mode = sortSel.value;
        const arr = items();
        const num = (it, k) => Number(it.dataset[k] || 0);
        arr.sort((a, b) => {
          if (mode === 'oldest') return num(a, 'id') - num(b, 'id');
          if (mode === 'msgs') return num(b, 'msgs') - num(a, 'msgs');
          if (mode === 'updated') {
            const ua = a.dataset.updated || '', ub = b.dataset.updated || '';
            return ua < ub ? 1 : ua > ub ? -1 : 0;
          }
          return num(b, 'id') - num(a, 'id');   /* newest (default) */
        });
        arr.forEach(it => list.insertBefore(it, noMatch));
        try { localStorage.setItem(LSORT, mode); } catch (e) {}
      }

      if (search) search.addEventListener('input', applyFilters);
      if (agentSel) agentSel.addEventListener('change', applyFilters);
      if (sortSel) sortSel.addEventListener('change', applySort);
      root.querySelectorAll('.cv-fchip[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
          root.querySelectorAll('.cv-fchip[data-filter]').forEach(b => b.classList.toggle('active', b === btn));
          activeFilter = btn.dataset.filter || 'all';
          applyFilters();
        });
      });

      // Collapse / expand the rail; persisted per-browser.
      const railBtn = document.getElementById('cv-rail-toggle');
      const openBtn = document.getElementById('cv-rail-open');
      function setRail(hidden) {
        root.classList.toggle('rail-hidden', hidden);
        try { localStorage.setItem(LRAIL, hidden ? '1' : '0'); } catch (e) {}
      }
      if (railBtn) railBtn.addEventListener('click', () => setRail(true));
      if (openBtn) openBtn.addEventListener('click', () => setRail(false));
      try { if (localStorage.getItem(LRAIL) === '1') setRail(true); } catch (e) {}

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
            const item = btn.closest('.cv-item');
            if (item && item.classList.contains('active')) { location.href = '/conversations'; return; }
            if (item) item.remove();
          } catch (err) { alert('Delete failed: ' + err.message); btn.disabled = false; }
        });
      });

      try {
        const s = localStorage.getItem(LSORT);
        if (s && sortSel) sortSel.value = s;
      } catch (e) {}
      applySort();
      applyFilters();
    })();
    </script>"""


# ---------------------------------------------------------------------------
# Overview (main pane when nothing is selected)
# ---------------------------------------------------------------------------

def _render_conversations_overview(convs: list[dict[str, Any]]) -> str:
    if not convs:
        return (
            '<section class="cv-main" id="cv-main"><div class="cv-empty">'
            + _pm_svg("chat")
            + "<p>No conversations yet.<br>Seed one and it shows up here live.</p>"
            '<a class="btn btn-primary" href="/orchestrate">+ New conversation</a>'
            "</div></section>"
        )
    stats = list_stats()
    recent_rows: list[str] = []
    for c in convs[:6]:
        cid = int(c["id"])
        topic = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
        recent_rows.append(
            f'<li><a class="cv-recent-row" href="/conversations/{cid}">'
            f'<span class="cv-status cv-{html.escape(str(c.get("status") or ""))}"></span>'
            f'{_conversation_mark(c, _conv_personas(c), "recent")}'
            '<span class="cv-recent-main">'
            f'<span class="cv-recent-topic">{html.escape(topic)}</span>'
            f'<span class="cv-recent-sub">#{cid} · {int(c.get("message_count") or 0)} msg · '
            f'{html.escape(_conv_cast_label(c))}</span>'
            "</span>"
            f'<span class="cv-recent-when">{html.escape(_short_date(c.get("updated_at")))}</span>'
            "</a></li>"
        )
    active_cls = " em" if stats["active"] else ""
    return (
        '<section class="cv-main" id="cv-main"><div class="cv-ov">'
        '<header class="cv-ov-head"><h1>Conversations</h1>'
        "<p>Pick a conversation from the list to read it — active ones stream in live.</p></header>"
        '<div class="cv-stats">'
        f'<div class="cv-stat"><span class="cv-stat-n">{stats["conversations"]:,}</span>'
        '<span class="cv-stat-l">Conversations</span></div>'
        f'<div class="cv-stat"><span class="cv-stat-n{active_cls}">{stats["active"]:,}</span>'
        '<span class="cv-stat-l">Active now</span></div>'
        f'<div class="cv-stat"><span class="cv-stat-n">{stats["messages"]:,}</span>'
        '<span class="cv-stat-l">Messages</span></div>'
        "</div>"
        '<div class="cv-recent"><h2>Recent</h2><ul>'
        + "".join(recent_rows) +
        "</ul></div>"
        '<div class="cv-ov-actions">'
        '<a class="btn btn-primary" href="/orchestrate">+ New conversation</a>'
        '<a class="btn" href="/api/conversations" title="Raw JSON of every conversation row">JSON index</a>'
        "</div></div></section>"
    )


# ---------------------------------------------------------------------------
# Reader (main pane with a conversation selected) + full-screen variant
# ---------------------------------------------------------------------------

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
            {_agent_avatar(sender, personas, "msg-avatar")}
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


def _effective_cast(c: dict[str, Any],
                    personas: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """The recorded cast, backfilled with AI-Models cards where none was recorded.

    Conversations seeded before the persona system (and any plain non-debate run)
    have no ``participant_personas``, which used to mean no Cast panel at all.
    Fall back to the built-in card for each participant's CLI, so #16 reads as
    "Gemini vs Codex" instead of showing nothing.

    Returns ``(cast, fallback_agent_ids)`` — the second element marks which rows
    are stand-ins so the panel can label them honestly. Recorded personas always
    win; a DB with no AI-Models cards just yields the original map.
    """
    participants = [str(p) for p in (c.get("participants") or [])]
    missing = [
        ag for ag in participants
        if not (personas.get(ag) or {}).get("persona_name")
    ]
    if not missing:
        return personas, set()
    fallback = model_persona_entries(missing)
    if not fallback:
        return personas, set()
    return {**personas, **fallback}, set(fallback)


def _cast_panel(c: dict[str, Any], personas: dict[str, Any],
                agent_counts: Counter) -> str:
    """Expandable cast list with per-agent message counts.

    Renders for every conversation that has *some* cast to show — a recorded
    persona cast, or the AI-Models fallback for participants without one. Empty
    string only when neither is available.
    """
    personas, defaulted = _effective_cast(c, personas)
    if not personas:
        return ""
    cast_items = []
    for ag in (c.get("participants") or []):
        p = personas.get(ag) or {}
        nm = p.get("persona_name")
        count = int(agent_counts.get(ag, 0))
        count_html = f'<span class="cast-count">{count} msg</span>'
        if not nm:
            cast_items.append(
                f'<li class="cast-item"><div class="cast-missing">'
                f'{_agent_avatar(ag, personas, "cast-avatar")}'
                f'<span class="cast-cli">{html.escape(str(ag))}</span>'
                f'<span class="cast-name muted">no persona recorded</span>{count_html}</div></li>'
            )
            continue
        slug = p.get("persona_slug") or ""
        slug_html = f'<span class="cast-slug">{html.escape(slug)}</span>' if slug else ""
        # Say so when this is the CLI's default card rather than a cast persona.
        model_html = ('<span class="cast-model">AI model</span>'
                      if str(ag) in defaulted else "")
        card_html = render_markdown(p.get("persona_body") or "_No card body._")
        cast_items.append(
            f'<li class="cast-item"><details>'
            f'<summary>{_agent_avatar(ag, personas, "cast-avatar")}'
            f'<span class="cast-cli">{html.escape(str(ag))}</span>'
            f'<span class="cast-name">{html.escape(nm)}</span>'
            f'{model_html}{slug_html}{count_html}</summary>'
            f'<div class="cast-card">{card_html}</div></details></li>'
        )
    return (
        '<aside class="cast"><h3>Cast '
        '<span class="muted" style="font-weight:400;font-size:12px">(click a name to read its personality card)</span></h3>'
        f'<ul class="cast-list">{"".join(cast_items)}</ul></aside>'
    )


def _kickoff_panel(c: dict[str, Any], msgs: list[dict[str, Any]]) -> str:
    """"Next: launch each CLI" panel for fresh conversations (active + 0 msgs).

    Gives the operator a copy-pasteable kickoff prompt per participant. JS in
    the reader script hides this panel once the first SSE message arrives.
    """
    participants_list = c.get("participants") or []
    if not (c["status"] == "active" and not msgs
            and isinstance(participants_list, list) and participants_list):
        return ""
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
            f'<code class="ns-agent">{html.escape(str(agent_id))}</code>'
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
    return f"""
        <aside id="next-steps" class="next-steps">
          <h3>Next: launch each CLI</h3>
          {intro}
          <ol class="ns-list">{"".join(rows)}</ol>
          <p class="ns-hint">Messages stream into this page live (~1s latency). This panel disappears when the first message arrives.</p>
        </aside>"""


def _render_conversation_main(data: dict[str, Any],
                              all_convs: list[dict[str, Any]],
                              fullscreen: bool) -> str:
    """The transcript reader — header strip, cast, kickoff panel, live transcript."""
    c = data["conversation"]
    msgs = data["messages"]
    cid = int(c["id"])
    title = str(c.get("topic") or "").strip() or f"Conversation #{cid}"

    personas: dict[str, Any] = {}
    raw_personas = c.get("participant_personas")
    if raw_personas:
        try:
            personas = json.loads(raw_personas) if isinstance(raw_personas, str) else dict(raw_personas)
        except (json.JSONDecodeError, TypeError, ValueError):
            personas = {}
    initial_msgs_html = "".join(_render_message(m, personas) for m in msgs)
    last_id = msgs[-1]["id"] if msgs else 0
    is_active = c["status"] == "active"
    participants = [str(p) for p in (c.get("participants") or [])]
    persona_names = {ag: p.get("persona_name") for ag, p in personas.items() if p.get("persona_name")}
    visual_agents = set(participants + list(persona_names))
    visual_agents.update(str(m.get("sender") or "agent") for m in msgs)
    agent_visuals = {
        ag: {
            "initials": _initials(_agent_display(ag, personas), ag),
            "style": _visual_style(f"{ag}|{_agent_display(ag, personas)}"),
        }
        for ag in visual_agents
    }
    agent_counts = Counter(
        str(m.get("sender")) for m in msgs if str(m.get("sender")) != "system"
    )

    # --- header strip ------------------------------------------------------
    status = str(c.get("status") or "")
    status_pill = (
        f'<span id="cv-pill" class="cv-pill{" is-active" if is_active else ""}">'
        f'<span class="dot"></span><span class="cv-pill-txt">{html.escape(status or "unknown")}</span></span>'
    )
    # Whose-turn badge — active turn-based conversations only; updated live
    # over the SSE `turn` events emitted by /api/conversations/{cid}/stream.
    turn_badge = ""
    if is_active and str(c.get("mode") or "") == "turns":
        current = c.get("current_turn")
        turn_txt = f"{current} is up" if current else "waiting…"
        turn_badge = (
            '<span id="turn-badge" class="cv-turn"><span class="dot"></span>'
            f'<span class="cv-turn-txt">{html.escape(turn_txt)}</span></span>'
        )

    export_filename = _export_filename(cid, str(c.get("topic") or ""))
    zip_filename = _export_zip_filename(cid, str(c.get("topic") or ""))
    stop_button = (
        '<button id="stop-btn" class="btn btn-danger" type="button">Stop</button>'
        if is_active else ""
    )
    delete_button = ""
    if not _is_public_readonly():
        delete_button = (
            f'<button id="delete-btn" class="icon-btn-danger" type="button" '
            f'data-cid="{cid}" data-topic="{html.escape(title, quote=True)}" '
            f'data-msg-count="{len(msgs)}" title="Delete conversation #{cid}" '
            f'aria-label="Delete conversation #{cid}">{_cv_svg("close")}</button>'
        )
    prev_id, next_id = _conversation_neighbors(all_convs, cid)
    if fullscreen:
        nav = (
            (f'<a class="icon-btn" href="/conversations/{prev_id}?fullscreen=1" '
             f'aria-label="Previous conversation" title="Previous">{_cv_svg("prev")}</a>'
             if prev_id is not None else
             f'<span class="icon-btn btn-disabled">{_cv_svg("prev")}</span>')
            + (f'<a class="icon-btn" href="/conversations/{next_id}?fullscreen=1" '
               f'aria-label="Next conversation" title="Next">{_cv_svg("next")}</a>'
               if next_id is not None else
               f'<span class="icon-btn btn-disabled">{_cv_svg("next")}</span>')
        )
        screen_btn = (
            f'<a class="icon-btn" href="/conversations/{cid}" '
            f'aria-label="Exit full screen" title="Exit full screen">{_cv_svg("shrink")}</a>'
        )
    else:
        nav = ""
        screen_btn = (
            f'<a class="icon-btn" href="/conversations/{cid}?fullscreen=1" '
            f'aria-label="Full screen" title="Full screen">{_cv_svg("expand")}</a>'
        )
    actions = (
        '<span class="cv-actions">'
        f'{nav}{screen_btn}'
        f'<a class="btn" href="/api/conversations/{cid}/export.md" '
        f'download="{html.escape(export_filename)}">Export MD</a>'
        f'<a class="btn" href="/api/conversations/{cid}/export.zip" '
        f'download="{html.escape(zip_filename)}" '
        f'title="ZIP: topic overview + one doc per persona + full transcript (Markdown)">Export ZIP</a>'
        f'{delete_button}'
        f'{stop_button}'
        "</span>"
    )

    # --- meta + stats lines --------------------------------------------------
    meta_bits = [f"#{cid}"]
    if c.get("preset"):
        meta_bits.append(str(c["preset"]))
    meta_bits.append(f'{c.get("mode", "turns")} · max {c.get("max_turns", "—")}/agent')
    meta_bits.append(f'started {_fmt_time(c.get("created_at"))}')
    if c.get("end_reason"):
        meta_bits.append(f'ended: {c["end_reason"]}')
    meta_line = " &nbsp;·&nbsp; ".join(html.escape(str(b)) for b in meta_bits)

    stat_bits: list[str] = [f"{len(msgs)} messages"]
    if agent_counts:
        per_agent = " / ".join(
            f"{ag} {agent_counts.get(ag, 0)}" for ag in participants if ag in agent_counts
        )
        if per_agent:
            stat_bits.append(per_agent)
    dur = _fmt_duration(msgs)
    if dur:
        stat_bits.append(dur)
    tok = _fmt_tokens(msgs)
    if tok:
        stat_bits.append(tok)
    stats_line = " &nbsp;·&nbsp; ".join(html.escape(b) for b in stat_bits)

    title = str(c.get("topic") or "").strip() or f"Conversation #{cid}"

    header = (
        '<header class="cv-read-head">'
        f'<div class="cv-eyebrow">{status_pill}{turn_badge}{actions}</div>'
        '<div class="cv-title-row">'
        f'{_conversation_mark(c, personas, "hero")}'
        '<div class="cv-title-copy">'
        f'<h1>{html.escape(title)}</h1>'
        f'<div class="cv-read-meta">{meta_line}</div>'
        f'<div class="cv-read-meta cv-read-stats">{stats_line}</div>'
        '</div></div>'
        "</header>"
    )

    cast_panel = _cast_panel(c, personas, agent_counts)
    kickoff_panel = _kickoff_panel(c, msgs)

    script = f"""
        <script>
        (function() {{
          const cid = {cid};
          let lastId = {last_id};
          const PERSONAS = {json.dumps(persona_names)};
          const AGENT_VISUALS = {json.dumps(agent_visuals)};
          const transcript = document.getElementById('transcript');
          const pill = document.getElementById('cv-pill');
          const turnBadge = document.getElementById('turn-badge');
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
                // 'event: complete' on its next tick; the pill flips there.
              }} catch (err) {{
                alert('Stop failed: ' + err.message);
                stopBtn.disabled = false;
                stopBtn.textContent = 'Stop';
              }}
            }});
          }}
          const deleteBtn = document.getElementById('delete-btn');
          if (deleteBtn) {{
            deleteBtn.addEventListener('click', async () => {{
              const topic = deleteBtn.dataset.topic || '(untitled)';
              const msgs = deleteBtn.dataset.msgCount || '0';
              if (!confirm('Permanently delete conversation #' + cid + '?\\n\\nTopic: ' + topic +
                           '\\nMessages: ' + msgs + '\\n\\nThis deletes the row and all its messages. ' +
                           'The local sidecar applies the deletion within ~5s. This cannot be undone.')) return;
              deleteBtn.disabled = true;
              try {{
                const res = await fetch('/api/conversations/' + cid + '/delete', {{ method: 'POST' }});
                if (!res.ok) throw new Error('HTTP ' + res.status);
                location.href = '/conversations';
              }} catch (err) {{
                alert('Delete failed: ' + err.message);
                deleteBtn.disabled = false;
              }}
            }});
          }}
          // Syntax-highlight code blocks in the server-rendered HTML.
          // Re-run after each SSE message append below.
          if (typeof hljs !== 'undefined') {{
            document.querySelectorAll('#transcript pre code').forEach(el => hljs.highlightElement(el));
          }}

          // --- scroll progress + jump-to-latest ---------------------------
          // .cv-main is the scroller; the window itself never scrolls on this
          // page, so every measurement below is against the pane. Wired up for
          // complete conversations too (the rail is just as useful reading an
          // archived debate) — hence it sits above the is_active early-return.
          const cvMain = document.getElementById('cv-main');
          const progBar = document.querySelector('#cv-prog i');
          const jumpWrap = document.getElementById('cv-jumpwrap');
          const jumpBtn = document.getElementById('cv-jump');
          const jumpN = document.getElementById('cv-jump-n');
          const NEAR = 120;  // px of slack that still counts as "at the bottom"
          let unread = 0;
          function atBottom() {{
            if (!cvMain) return true;
            return cvMain.scrollHeight - cvMain.scrollTop - cvMain.clientHeight <= NEAR;
          }}
          function paintProgress() {{
            if (!progBar || !cvMain) return;
            const max = cvMain.scrollHeight - cvMain.clientHeight;
            const p = max > 0 ? Math.min(1, Math.max(0, cvMain.scrollTop / max)) : 0;
            progBar.style.transform = 'scaleX(' + p + ')';
          }}
          function paintJump() {{
            if (!jumpWrap) return;
            jumpWrap.classList.toggle('show', unread > 0 && !atBottom());
            if (jumpN) {{ jumpN.hidden = unread < 1; jumpN.textContent = unread; }}
          }}
          function toBottom(smooth) {{
            if (!cvMain) return;
            cvMain.scrollTo({{ top: cvMain.scrollHeight, behavior: smooth ? 'smooth' : 'auto' }});
            unread = 0;
            paintJump();
          }}
          if (cvMain) {{
            cvMain.addEventListener('scroll', () => {{
              paintProgress();
              if (atBottom()) unread = 0;
              paintJump();
            }}, {{ passive: true }});
            window.addEventListener('resize', paintProgress, {{ passive: true }});
            paintProgress();
          }}
          if (jumpBtn) jumpBtn.addEventListener('click', () => toBottom(true));

          if (!{json.dumps(is_active)}) return;
          const es = new EventSource('/api/conversations/' + cid + '/stream?since=' + lastId);
          es.addEventListener('message', (ev) => {{
            const m = JSON.parse(ev.data);
            if (m.id <= lastId) return;
            // Measure BEFORE the DOM grows, or the new message's own height
            // pushes us out of the "at the bottom" window and we never stick.
            const stick = atBottom();
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
            // Follow the tail only if the reader was already at it. This used
            // to scroll unconditionally, which yanked the viewport away from
            // anyone reading earlier in the debate every time an agent replied.
            if (stick) {{
              toBottom(false);
            }} else {{
              unread++;
              paintJump();
            }}
            paintProgress();
          }});
          es.addEventListener('turn', (ev) => {{
            if (!turnBadge) return;
            try {{
              const d = JSON.parse(ev.data);
              const who = d.current_turn;
              const label = who
                ? (PERSONAS[who] ? PERSONAS[who] + ' (' + who + ') is up' : who + ' is up')
                : 'waiting…';
              turnBadge.querySelector('.cv-turn-txt').textContent = label;
            }} catch (e) {{}}
          }});
          es.addEventListener('complete', () => {{
            es.close();
            if (pill) {{
              pill.classList.remove('is-active');
              pill.querySelector('.cv-pill-txt').textContent = 'complete';
            }}
            if (turnBadge) turnBadge.remove();
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
            const visual = AGENT_VISUALS[m.sender] || AGENT_VISUALS.system ||
              {{ initials: String(m.sender || 'AI').slice(0, 2).toUpperCase(), style: '--cv-ink:#10b981;--cv-ink-2:#38bdf8;' }};
            const avatar = '<span class="msg-avatar" style="' + esc(visual.style) +
              '" aria-hidden="true">' + esc(visual.initials || 'AI') + '</span>';
            const who = pname
              ? esc(pname) + ' <span class="who-cli">' + esc(m.sender) + '</span>'
              : esc(m.sender);
            return '<div class="msg ' + senderClass + ' ' + signalClass + '" data-id="' + m.id + '">' +
              '<div class="msg-head">' + avatar + '<span class="who">' + who + '</span>' +
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

    jump = (
        '<div class="cv-jumpwrap" id="cv-jumpwrap">'
        '<button type="button" class="cv-jump" id="cv-jump">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>'
        '<span>Jump to latest</span>'
        '<span class="cv-jump-n" id="cv-jump-n" hidden>0</span>'
        "</button></div>"
    )
    return (
        '<section class="cv-main" id="cv-main">'
        '<div class="cv-prog" id="cv-prog" aria-hidden="true"><i></i></div>'
        '<div class="cv-read">'
        f"{header}{cast_panel}{kickoff_panel}"
        f'<div id="transcript" class="transcript">{initial_msgs_html}</div>'
        f"{jump}{script}</div></section>"
    )


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def _render_conversation(data: dict[str, Any],
                         all_convs: list[dict[str, Any]] | None = None,
                         fullscreen: bool = False) -> str:
    convs = all_convs if all_convs is not None else list_conversations()
    c = data["conversation"]
    title = str(c.get("topic") or "").strip() or f"Conversation #{c['id']}"
    main = _render_conversation_main(data, convs, fullscreen)
    if fullscreen:
        body = f'<div class="cv2 cv-fullscreen">{main}</div>'
    else:
        rail = _conversations_rail(convs, int(c["id"]))
        body = f'<div class="cv2">{rail}{main}</div>{_conv_rail_js()}'
    return _layout(title, "", body,
                   head_extras=HIGHLIGHT_JS_HEAD + _CAST_CSS + _CONV_CSS,
                   active="conversations")


def _render_index(convs: list[dict[str, Any]]) -> str:
    rail = _conversations_rail(convs, None)
    body = f'<div class="cv2">{rail}{_render_conversations_overview(convs)}</div>{_conv_rail_js()}'
    return _layout("Conversations", "", body, head_extras=_CONV_CSS,
                   active="conversations")


def _render_conversation_not_found(cid: int, convs: list[dict[str, Any]]) -> str:
    """Friendly 404 for a missing conversation id — rendered inside the browser
    (with the rail) so the visitor can pick another conversation rather than
    landing on a dead-end error page."""
    rail = _conversations_rail(convs, None)
    center = (
        '<section class="cv-main" id="cv-main"><div class="cv-empty">'
        + _pm_svg("chat") +
        f"<p>Conversation #{cid} doesn't exist.<br>"
        "It may have been deleted, or the link is wrong.</p>"
        '<a class="btn btn-primary" href="/conversations">&larr; Back to conversations</a>'
        "</div></section>"
    )
    body = f'<div class="cv2">{rail}{center}</div>{_conv_rail_js()}'
    return _layout("Not found", "", body, head_extras=_CONV_CSS,
                   active="conversations")
