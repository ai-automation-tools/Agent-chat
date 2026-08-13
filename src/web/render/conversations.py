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

from orchestrator.conv_types import (
    CONV_TYPE_KEYS,
    CONV_TYPES,
    DEFAULT_CONV_TYPE,
    lead_of,
    parse_roles,
    role_label,
    type_label,
)
from orchestrator.model_personas import model_persona_entries

from web.assets import HIGHLIGHT_JS_HEAD, _CAST_CSS, _CONV_CSS
from web.avatars import avatar_url
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
    "info": '<circle cx="12" cy="12" r="9.5"/><line x1="12" y1="11" x2="12" y2="16"/>'
            '<line x1="12" y1="7.6" x2="12.01" y2="7.6"/>',
    # Media-prompt buttons: a picture frame, and a waveform.
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/>'
             '<circle cx="8.5" cy="9.5" r="1.6"/><polyline points="4 17 9.5 12 13 15 17 11.5 20 14"/>',
    "audio": '<line x1="4" y1="10" x2="4" y2="14"/><line x1="8" y1="7" x2="8" y2="17"/>'
             '<line x1="12" y1="4" x2="12" y2="20"/><line x1="16" y1="8" x2="16" y2="16"/>'
             '<line x1="20" y1="11" x2="20" y2="13"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/>'
            '<path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    # Export actions: a document with a folded corner, and a zipped archive.
    "doc": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
           '<polyline points="14 3 14 8 19 8"/><path d="M9 13h6M9 17h4"/>',
    "zip": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
           '<polyline points="14 3 14 8 19 8"/>'
           '<path d="M9.5 5.5h1M9.5 8h1M9.5 10.5h1M9.5 13h1"/>'
           '<rect x="8.6" y="15" width="2.8" height="3.4" rx="0.7"/>',
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
    style = _visual_style(agent + "|" + label)
    # Persona slug when a cast is recorded, else the bare agent id — which for a
    # CLI participant (claude-code, codex, …) is its AI-Models avatar slug, so
    # conversations with no linked personas still show each tool's brand mark.
    # An unknown id resolves to the default silhouette server-side.
    slug = (personas or {}).get(agent, {}).get("persona_slug") or agent
    if slug:
        # Image overlays the initials chip; onerror reveals the monogram again.
        src = html.escape(avatar_url(str(slug)), quote=True)
        return (
            f'<span class="{class_name} avatar-has-img" style="{style}" '
            f'role="img" aria-label="{html.escape(label, quote=True)}">'
            f'<img class="avatar-img" src="{src}" alt="" loading="lazy" '
            f"onerror=\"this.style.display='none'\">{initials}</span>"
        )
    return (
        f'<span class="{class_name}" style="{style}" '
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


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _fmt_day(ts: Any) -> str:
    """``Aug 12, 2026`` from an ISO timestamp.

    The header used to print the raw column (``2026-08-12 22:31:11``). Nobody
    reads a conversation and needs the second it started; the full timestamp is
    still one click away under *Run details*.
    """
    s = str(ts or "")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return s[:10] or "—"
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"


# ---------------------------------------------------------------------------
# Rail (left pane)
# ---------------------------------------------------------------------------

def _conversations_rail(convs: list[dict[str, Any]], active_cid: int | None) -> str:
    total = len(convs)
    active = sum(1 for c in convs if c.get("status") == "active")
    three_agent = sum(1 for c in convs if len(c.get("participants") or []) >= 3)
    # One chip per conversation type that actually has rows, so adding a type to
    # the registry surfaces here with no edit and an unused one costs no chrome.
    type_counts = Counter(
        str(c.get("conv_type") or DEFAULT_CONV_TYPE) for c in convs
    )
    type_chips = tuple(
        (f"type:{key}", CONV_TYPES[key].plural, type_counts.get(key, 0))
        for key in CONV_TYPE_KEYS
        if type_counts.get(key, 0)
    )
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
            *type_chips,
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
        mark_active = " is-active" if status == "active" else ""
        items.append(
            f'<div class="cv-item{is_active}" '
            f'data-id="{cid}" data-msgs="{msgc}" '
            f'data-updated="{html.escape(str(c.get("updated_at") or ""), quote=True)}" '
            f'data-date="{html.escape(_short_date(c.get("updated_at")), quote=True)}" '
            f'data-cast="{html.escape(cast, quote=True)}" '
            f'data-search="{search_blob}" data-status="{html.escape(status, quote=True)}" '
            f'data-preset="{html.escape(str(c.get("preset") or ""), quote=True)}" '
            f'data-conv-type="{html.escape(str(c.get("conv_type") or DEFAULT_CONV_TYPE), quote=True)}" '
            f'data-participant-count="{len(participants)}" '
            f'data-participants="{html.escape("|".join(participants), quote=True)}">'
            f'<a class="cv-link" href="/conversations/{cid}" '
            f'title="{html.escape(topic, quote=True)}">'
            f'<span class="cv-mark-wrap{mark_active}">'
            f'{_conversation_mark(c, _conv_personas(c), "rail")}</span>'
            f'<span class="cv-topic">{html.escape(topic)}</span>'
            "</a>"
            f'<button type="button" class="cv-info" tabindex="-1" '
            f'aria-label="Details for conversation #{cid}">{_cv_svg("info")}</button>'
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
        '<div class="cv-resizer" id="cv-resizer" role="separator" aria-orientation="vertical" '
        'title="Drag to resize · double-click to reset" aria-label="Resize conversation list"></div>'
        '<div class="cv-tip" id="cv-tip" role="tooltip" aria-hidden="true"></div>'
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
            (activeFilter.startsWith('type:') &&
              (it.dataset.convType || 'debate') === activeFilter.slice(5)) ||
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

      // Drag the rail's right edge to resize; width persisted per-browser.
      const LWID = 'agentchat.cv.railw', RAIL_MIN = 236, RAIL_MAX = 560, RAIL_DEF = 320;
      const resizer = document.getElementById('cv-resizer');
      const setRailW = (w) => root.style.setProperty('--cv-rail-w', Math.round(w) + 'px');
      try { const w = parseInt(localStorage.getItem(LWID) || '', 10); if (w) setRailW(w); } catch (e) {}
      if (resizer) {
        let dragging = false;
        const onMove = (e) => {
          if (!dragging) return;
          const left = root.getBoundingClientRect().left;
          setRailW(Math.max(RAIL_MIN, Math.min(RAIL_MAX, e.clientX - left)));
        };
        const onUp = () => {
          if (!dragging) return;
          dragging = false;
          root.classList.remove('cv-resizing');
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          const cur = parseInt(root.style.getPropertyValue('--cv-rail-w'), 10);
          try { if (cur) localStorage.setItem(LWID, String(cur)); } catch (e) {}
        };
        resizer.addEventListener('mousedown', (e) => {
          e.preventDefault();
          dragging = true;
          root.classList.add('cv-resizing');
          document.addEventListener('mousemove', onMove);
          document.addEventListener('mouseup', onUp);
        });
        resizer.addEventListener('dblclick', () => {
          setRailW(RAIL_DEF);
          try { localStorage.setItem(LWID, String(RAIL_DEF)); } catch (e) {}
        });
      }

      // Hover-(i) details popover — a single fixed element, positioned by JS so
      // the list's overflow can't clip it. Reads the item's data-* attributes.
      const tip = document.getElementById('cv-tip');
      const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => (
        {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
      ));
      function showTip(btn) {
        const it = btn.closest('.cv-item');
        if (!it || !tip) return;
        const status = it.dataset.status || '';
        const parts = (it.dataset.participants || '').split('|').filter(Boolean);
        const cast = it.dataset.cast || parts.join(', ') || '—';
        const row = (k, v) => '<div class="cv-tip-row"><span class="cv-tip-k">' + k +
          '</span><span class="cv-tip-v">' + esc(v) + '</span></div>';
        tip.innerHTML =
          '<div class="cv-tip-h">#' + esc(it.dataset.id) +
          ' <span class="cv-tip-st ' + esc(status) + '">' + esc(status || 'unknown') + '</span></div>' +
          row('Messages', it.dataset.msgs || '0') +
          row('Cast', cast) +
          row('Agents', parts.length || '—') +
          (it.dataset.date ? row('Updated', it.dataset.date) : '');
        tip.classList.add('show');
        const r = btn.getBoundingClientRect();
        const tw = tip.offsetWidth, th = tip.offsetHeight, gap = 8;
        let x = r.right + gap;
        if (x + tw > window.innerWidth - 8) x = r.left - tw - gap;
        let y = r.top + r.height / 2 - th / 2;
        y = Math.max(8, Math.min(y, window.innerHeight - th - 8));
        tip.style.left = x + 'px';
        tip.style.top = y + 'px';
      }
      const hideTip = () => { if (tip) tip.classList.remove('show'); };
      root.querySelectorAll('.cv-info').forEach(btn => {
        btn.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });
        btn.addEventListener('mouseenter', () => showTip(btn));
        btn.addEventListener('mouseleave', hideTip);
      });
      if (list) list.addEventListener('scroll', hideTip, { passive: true });

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
        status = str(c.get("status") or "")
        topic = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
        cast = _conv_cast_label(c)
        msgc = int(c.get("message_count") or 0)
        mark_active = " is-active" if status == "active" else ""
        badge = (
            '<span class="cv-card-live">live</span>' if status == "active" else ""
        )
        recent_rows.append(
            f'<a class="cv-card" href="/conversations/{cid}">'
            '<div class="cv-card-top">'
            f'<span class="cv-mark-wrap{mark_active}">'
            f'{_conversation_mark(c, _conv_personas(c), "recent")}</span>'
            f'<span class="cv-card-topic">{html.escape(topic)}</span>'
            f"{badge}"
            "</div>"
            f'<div class="cv-card-cast">{html.escape(cast)}</div>'
            '<div class="cv-card-meta">'
            f'<span class="mono">#{cid}</span><span class="cv-card-dot"></span>'
            f'<span>{msgc} msg</span><span class="cv-card-dot"></span>'
            f'<span>{html.escape(_short_date(c.get("updated_at")))}</span>'
            "</div>"
            "</a>"
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
        '<div class="cv-recent"><h2>Recent</h2>'
        '<div class="cv-recent-grid">'
        + "".join(recent_rows) +
        "</div></div>"
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
    """The cast column — one expandable row per seat, with message counts.

    Renders for every conversation that has *some* cast to show — a recorded
    persona cast, or the AI-Models fallback for participants without one. Empty
    string only when neither is available (the header then goes single-column).

    The panel spans the reader's full width, under the topic block. A row is a
    single line: avatar, **persona name**, seat, then the CLI / count / chevron
    pushed to the right edge. The old row put the agent id in a green chip
    *before* the name, so the loudest thing in each row was the least
    interesting one. The persona slug is gone entirely — it was the name again,
    lowercased and hyphenated.
    """
    personas, defaulted = _effective_cast(c, personas)
    if not personas:
        return ""
    conv_type = c.get("conv_type")
    roles = parse_roles(c.get("participant_roles"))
    lead = lead_of(conv_type, roles)
    cast_items = []
    for ag in (c.get("participants") or []):
        p = personas.get(ag) or {}
        nm = p.get("persona_name")
        count = int(agent_counts.get(ag, 0))
        count_html = f'<span class="cast-count">{count} msg</span>'
        # Seat label ("Host", "Guest"); empty for rows seeded before roles existed.
        seat = role_label(conv_type, roles.get(ag))
        role_html = (
            f'<span class="cast-role{" is-lead" if ag == lead else ""}">'
            f'{html.escape(seat)}</span>'
        ) if seat else ""
        cli_html = f'<span class="cast-cli">{html.escape(str(ag))}</span>'
        if not nm:
            cast_items.append(
                f'<li class="cast-item"><div class="cast-missing">'
                f'{_agent_avatar(ag, personas, "cast-avatar")}'
                '<span class="cast-name muted">no persona recorded</span>'
                f'{role_html}<span class="cast-tail">{cli_html}{count_html}</span>'
                "</div></li>"
            )
            continue
        # Say so when this is the CLI's default card rather than a cast persona.
        model_html = ('<span class="cast-model">AI model</span>'
                      if str(ag) in defaulted else "")
        card_html = render_markdown(p.get("persona_body") or "_No card body._")
        cast_items.append(
            f'<li class="cast-item"><details>'
            f'<summary>{_agent_avatar(ag, personas, "cast-avatar")}'
            f'<span class="cast-name">{html.escape(nm)}</span>'
            f'{role_html}{model_html}'
            f'<span class="cast-tail">{cli_html}{count_html}'
            f'<span class="cast-chev" aria-hidden="true">{_cv_svg("next")}</span></span>'
            "</summary>"
            f'<div class="cast-card">{card_html}</div></details></li>'
        )
    return (
        '<aside class="cast cv-cast">'
        '<div class="cv-cast-head"><span class="cv-cast-label">Cast</span>'
        '<span class="cv-cast-hint">click to read a card</span></div>'
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
            # Versioned avatar URL so live-streamed messages show the same
            # image as the server-rendered ones. Slug falls back to the agent id
            # (a CLI's own brand-avatar slug) so no-persona conversations still
            # get marks.
            "avatar": avatar_url((personas.get(ag) or {}).get("persona_slug") or str(ag)),
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
    # Media-prompt buttons. Each fetches a prompt built from this conversation's
    # topic + cast (orchestrator/media_prompts.py) and shows it to copy. They
    # produce *text for another tool*, never media — nothing here calls an image
    # or audio API, same posture as the battleground panel's copyable command.
    # GET-only, so they work on the hosted mirror too.
    # Four actions, one hue each, each with a "?" explaining what you get. The
    # prompt labels say "prompt" because the button doesn't make anything — it
    # hands you text to paste elsewhere; "Images" / "Audio" alone read as "this
    # app will generate them", which is the one thing it never does.
    kind_word = type_label(c.get("conv_type")).lower()
    primary_actions = (
        _action_button(
            "images", "image", "Image prompt",
            "This is a <b>prompt, not a generator</b>. Copy it into an image "
            "tool and it produces the cover art, the team shot, and one "
            f"portrait per character for this {kind_word}.",
            "is-violet",
            title="Opens a copyable prompt — nothing is generated here",
        )
        + _action_button(
            "audio", "audio", "Audio prompt",
            "This is a <b>prompt, not a generator</b>. Copy it into a CLI agent "
            "with text-to-speech and it turns this transcript into a voiced MP3.",
            "is-sky",
            title="Opens a copyable prompt — nothing is generated here",
        )
        + _action_button(
            "export-md", "doc", "Export MD",
            "Downloads <b>one Markdown file</b> — the whole transcript, with a "
            "metadata table and a heading per turn. The format the library "
            "archive and the theater app read.",
            "is-amber",
            href=f"/api/conversations/{cid}/export.md",
            download=export_filename,
        )
        + _action_button(
            "export-zip", "zip", "Export ZIP",
            "Downloads a <b>bundle</b>: the transcript, a topic overview, and "
            "one document per character with its full personality card. Use "
            "this one when you're publishing.",
            "is-rose",
            href=f"/api/conversations/{cid}/export.zip",
            download=zip_filename,
        )
    )
    # Window + destructive controls. Kept apart from the four so the row reads
    # as "here are the things you'd do with this conversation" rather than a
    # tray of eight unrelated buttons.
    utility_actions = f"{nav}{screen_btn}{delete_button}{stop_button}"
    actions = (
        '<span class="cv-actions">'
        f"{primary_actions}"
        f'<span class="cv-actions-util">{utility_actions}</span>'
        "</span>"
    )

    # --- facts -------------------------------------------------------------
    # Headline facts only. Everything that used to sit on the two dotted meta
    # lines and is really *run configuration* (id, mode, turn cap, preset, the
    # exact start time, why it ended) moved into the Run-details disclosure
    # below — it's referenced rarely and it was crowding out the numbers people
    # actually scan for.
    facts = [f"{len(msgs)} messages"]
    dur = _fmt_duration(msgs)
    if dur:
        facts.append(dur)
    tok = _fmt_tokens(msgs)
    if tok:
        facts.append(tok)
    facts_line = " · ".join(html.escape(f) for f in facts)

    detail_rows = [("Conversation", f"#{cid}"),
                   ("Mode", f'{c.get("mode", "turns")} · max {c.get("max_turns", "—")}/agent')]
    # The preset only earns a row when it says something the format hasn't. A
    # podcast on the "podcast" preset used to render as `podcast · podcast`,
    # which reads like a bug.
    preset = str(c.get("preset") or "")
    if preset and preset.lower() != str(c.get("conv_type") or "").lower():
        detail_rows.append(("Preset", preset))
    detail_rows.append(("Started", str(_fmt_time(c.get("created_at")))))
    if c.get("end_reason"):
        detail_rows.append(("Ended", str(c["end_reason"])))
    if agent_counts:
        per_agent = " · ".join(
            f"{ag} {agent_counts.get(ag, 0)}" for ag in participants if ag in agent_counts
        )
        if per_agent:
            detail_rows.append(("Per agent", per_agent))
    details_html = "".join(
        f'<div class="cv-drow"><dt>{html.escape(k)}</dt>'
        f'<dd>{html.escape(v)}</dd></div>'
        for k, v in detail_rows
    )

    title = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
    cast_panel = _cast_panel(c, personas, agent_counts)

    # Topic block, then the Cast full-width beneath it, then the transcript —
    # one column all the way down. The facts sit on one line under the title
    # rather than the two dotted meta rows this replaced.
    # The eyebrow keeps only the state of the run (status pill, whose turn).
    # The buttons live in their own row under the Cast — see `action_bar`.
    header = (
        '<header class="cv-read-head">'
        f'<div class="cv-eyebrow">{status_pill}{turn_badge}</div>'
        f'<h1 class="cv-h1">{html.escape(title)}</h1>'
        f'<div class="cv-facts">'
        f'<span class="cv-type">{html.escape(type_label(c.get("conv_type")))}</span>'
        f'<span class="cv-factline">{facts_line}</span>'
        '<span class="cv-factsep">·</span>'
        f'<span class="cv-factline">{html.escape(_fmt_day(c.get("created_at")))}</span>'
        '<details class="cv-details"><summary>Run details</summary>'
        f'<dl class="cv-dlist">{details_html}</dl></details>'
        "</div>"
        "</header>"
    )
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
          // --- media-prompt modal -----------------------------------------
          // The button fetches the prompt rather than carrying it in a data-
          // attribute: they run ~9KB each and would sit in the HTML of every
          // conversation page whether or not anyone opens one.
          const pmModal = document.getElementById('cv-pm');
          const pmTitle = document.getElementById('cv-pm-title');
          const pmSub = document.getElementById('cv-pm-sub');
          const pmText = document.getElementById('cv-pm-text');
          const pmCopy = document.getElementById('cv-pm-copy');
          const pmDl = document.getElementById('cv-pm-dl');
          const PM_META = {{
            images: {{
              title: 'Image prompt',
              sub: 'Copy this and paste it into an image tool (ChatGPT, Gemini, Midjourney, a CLI agent). It asks for a cover, a team shot, and one portrait per character — already filled in with this cast.',
            }},
            audio: {{
              title: 'Audio prompt',
              sub: 'Copy this and paste it into a CLI agent with text-to-speech. It fetches this transcript and renders one voiced MP3 — already filled in with this cast.',
            }},
          }};
          function pmClose() {{
            if (pmModal) pmModal.classList.add('hidden');
          }}
          if (pmModal) {{
            pmModal.addEventListener('click', (e) => {{
              if (e.target === pmModal || e.target.closest('[data-pm-close]')) pmClose();
            }});
            document.addEventListener('keydown', (e) => {{
              if (e.key === 'Escape' && !pmModal.classList.contains('hidden')) pmClose();
            }});
          }}
          document.querySelectorAll('.cv-prompt-btn').forEach(btn => {{
            btn.addEventListener('click', async () => {{
              const kind = btn.dataset.kind;
              const meta = PM_META[kind] || {{ title: 'Prompt', sub: '' }};
              const url = '/api/conversations/' + cid + '/prompts/' + kind + '.md';
              if (!pmModal) return;
              pmTitle.textContent = meta.title;
              pmSub.textContent = meta.sub;
              pmText.value = 'Loading…';
              pmDl.href = url + '?download=1';
              pmModal.classList.remove('hidden');
              try {{
                const res = await fetch(url);
                if (!res.ok) throw new Error('HTTP ' + res.status);
                pmText.value = await res.text();
              }} catch (err) {{
                pmText.value = 'Could not build the prompt: ' + err.message;
              }}
            }});
          }});
          if (pmCopy) {{
            pmCopy.addEventListener('click', async () => {{
              try {{
                await navigator.clipboard.writeText(pmText.value);
                const orig = pmCopy.textContent;
                pmCopy.textContent = 'Copied!';
                setTimeout(() => {{ pmCopy.textContent = orig; }}, 1500);
              }} catch (err) {{
                // Clipboard is blocked outside a secure context (plain http on
                // a LAN address). Selecting the text still lets them copy it.
                pmText.select();
                alert('Copy failed: ' + err.message + '\\nThe text is selected — press Ctrl+C.');
              }}
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
              {{ initials: String(m.sender || 'AI').slice(0, 2).toUpperCase(), style: '--cv-ink:#10b981;--cv-ink-2:#38bdf8;', avatar: '/avatars/' + encodeURIComponent(String(m.sender || '')) }};
            const avatarUrl = visual.avatar || '';
            const avatar = avatarUrl
              ? '<span class="msg-avatar avatar-has-img" style="' + esc(visual.style) + '" role="img">' +
                  '<img class="avatar-img" src="' + esc(avatarUrl) + '" alt="" loading="lazy" ' +
                  'onerror="this.style.display=\\'none\\'">' + esc(visual.initials || 'AI') + '</span>'
              : '<span class="msg-avatar" style="' + esc(visual.style) +
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
        f"{header}{cast_panel}"
        '<section class="cv-box cv-actionbox">'
        '<h3 class="cv-box-label">Actions</h3>'
        f"{actions}"
        "</section>"
        f"{kickoff_panel}"
        '<section class="cv-box cv-convo-box"><h3 class="cv-box-label">Conversation</h3>'
        f'<div id="transcript" class="transcript">{initial_msgs_html}</div>'
        "</section>"
        f"{jump}{_media_prompt_modal()}{script}</div></section>"
    )


def _action_button(key: str, icon: str, label: str, help_html: str, tone: str,
                   *, href: str | None = None, download: str | None = None,
                   title: str = "") -> str:
    """One action button plus the help badge pinned to its top-right corner.

    Renders a ``<button>`` (the prompt actions, wired by JS via ``data-kind``)
    or an ``<a download>`` (the exports, which are plain links) — the chrome is
    identical either way so the row reads as one set of four.

    The badge is a **sibling** of the control, not a child: nesting anything
    interactive inside a button or a link is invalid, and a help affordance that
    also fires the action would be a trap. It's focusable so the explanation is
    reachable without a mouse, and the tip itself is inert (``pointer-events:
    none``) so it can never swallow a click meant for the control under it.

    ``tone`` is the accent class (``is-violet`` …) — see ``.cv-abtn`` in the CSS.
    """
    tip_id = f"cv-help-{key}"
    attrs = f'title="{html.escape(title, quote=True)}"' if title else ""
    if href is not None:
        dl = f' download="{html.escape(download, quote=True)}"' if download else ""
        control = (f'<a class="btn cv-abtn {tone}" href="{href}"{dl} {attrs}>'
                   f'{_cv_svg(icon)} {html.escape(label)}</a>')
    else:
        control = (f'<button type="button" class="btn cv-abtn cv-prompt-btn {tone}" '
                   f'data-kind="{key}" {attrs}>'
                   f'{_cv_svg(icon)} {html.escape(label)}</button>')
    return (
        '<span class="cv-pbtn">'
        + control
        + f'<span class="cv-help" tabindex="0" role="note" aria-describedby="{tip_id}">'
        '<span aria-hidden="true">?</span></span>'
        # Sibling of the badge, not a child: anchored to the wrapper it clears
        # the whole button, instead of opening halfway up it and covering the
        # label it's meant to explain.
        f'<span class="cv-help-tip" id="{tip_id}" role="tooltip">{help_html}</span>'
        "</span>"
    )


def _media_prompt_modal() -> str:
    """The overlay the Images / Audio buttons fill in.

    One modal serves both kinds — the JS swaps the title, blurb, body, and
    download href. Rendered empty on every conversation page; the prompt text
    only arrives when someone opens it.
    """
    return (
        '<div id="cv-pm" class="cv-pm hidden" role="dialog" aria-modal="true" '
        'aria-labelledby="cv-pm-title">'
        '<div class="cv-pm-card">'
        '<header class="cv-pm-head">'
        '<div><h3 id="cv-pm-title">Prompt</h3>'
        '<p id="cv-pm-sub" class="cv-pm-sub"></p></div>'
        '<button type="button" class="icon-btn" data-pm-close '
        f'aria-label="Close">{_cv_svg("close")}</button>'
        "</header>"
        '<textarea id="cv-pm-text" class="cv-pm-text" readonly spellcheck="false" '
        'aria-label="Generated prompt"></textarea>'
        '<footer class="cv-pm-foot">'
        '<span class="cv-pm-note"><strong>This page generates nothing.</strong> '
        'The text above is the instruction &mdash; run it wherever you make '
        'images or audio.</span>'
        '<a id="cv-pm-dl" class="btn" href="#" download>Download .md</a>'
        '<button type="button" id="cv-pm-copy" class="btn btn-primary">Copy prompt</button>'
        "</footer></div></div>"
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
