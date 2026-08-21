"""The ``/battleground`` arena console — the operator surface that isn't a tab.

Until this page, the extension's side panel was the *only* place an arena
existed for a human: no way to see arenas across tabs, no way to review a draft
without the captured page still open, no draft history for a debate that ran
last week. This renders the same rows the panel polls, read from the same
``bg_*`` helpers in :mod:`web.db`.

**It still never posts, and it does not even insert.** Approving here flips a
draft to ``approved`` and stops — typing the text into a page's composer needs
the tab the thread lives in, which is the extension's job (``lib/compose.js``,
the only code in the project that touches a reply box). The page says so
plainly next to the button, because "approved but nothing happened" is the
failure mode this feature can least afford.

Every action posts to a bridge endpoint that already existed
(``/api/battleground/drafts/{id}/verdict``, ``/arenas/{id}``,
``/arenas/{id}/delete``), so no new write route — and no new hole for
``ReadOnlyMiddleware`` to cover. The hosted mirror never has arena rows at all
(both tables are excluded from the sidecar sync), so it gets an explainer
instead of an empty list, the same shape ``/orchestrate`` uses.
"""

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import urlsplit

from web.assets import BATTLEGROUND_CSS, ORCHESTRATE_CSS
from web.db import (
    ARENA_CLOSED,
    ARENA_OPEN,
    DRAFT_APPROVED,
    DRAFT_PENDING,
    DRAFT_POSTED,
    DRAFT_REJECTED,
)
from web.render.common import _layout

_REPO = "https://github.com/michaelschecht/Agent-chat"

# Adapter id → what the operator calls that site. Same map the /extension page
# keeps; duplicated rather than imported so neither page's copy can quietly
# grow a label the other doesn't show.
_SITE_LABELS = {
    "reddit": "Reddit",
    "x": "X / Twitter",
    "hackernews": "Hacker News",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
    "substack": "Substack",
    "discourse": "Discourse",
    "disqus": "Disqus",
    "generic": "generic reader",
}

# The one-click rejection briefs. Same intent as the panel's revision quick
# actions: a rejection with no note reads to the agent as "no", a rejection
# with one reads as a brief it can act on.
_REJECT_REASONS = (
    "Too long — cut it to a few sentences.",
    "Sounds like an LLM — plainer, less balanced-on-both-sides.",
    "Needs a source or a concrete specific.",
    "Wrong target — answer a different post.",
)


def _e(value: Any) -> str:
    """Escape for text content; ``None`` becomes an empty string."""
    return html.escape("" if value is None else str(value))


def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc or url
    except ValueError:
        return url


def _site_label(site: str) -> str:
    return _SITE_LABELS.get(site, site or "generic")


def _short_ts(ts: str | None) -> str:
    """``2026-08-20T14:03:11+00:00`` → ``2026-08-20 14:03``. Stored timestamps
    are ISO-8601 UTC strings written by ``web.db._now()``; anything unexpected
    is shown as-is rather than guessed at."""
    if not ts:
        return "—"
    text = str(ts)
    if len(text) >= 16 and text[10:11] == "T":
        return text[:10] + " " + text[11:16]
    return text


def _cast_label(arena: dict[str, Any]) -> str:
    """Who the arena is cast as. Gated on ``persona_name`` rather than
    ``persona_slug`` — a custom card typed into the panel has a name and a body
    but no registry row, and reading the slug would show it as uncast."""
    name = arena.get("persona_name")
    if name:
        return str(name)
    return "not cast"


def _status_pill(status: str) -> str:
    cls = "open" if status == ARENA_OPEN else "closed"
    return f'<span class="bgc-pill {cls}">{_e(status)}</span>'


def _draft_pill(status: str) -> str:
    known = (DRAFT_PENDING, DRAFT_APPROVED, DRAFT_REJECTED, DRAFT_POSTED)
    cls = status if status in known else "closed"
    return f'<span class="bgc-pill {cls}">{_e(status)}</span>'


# ---------------------------------------------------------------------------
# The invariant, restated on both views
# ---------------------------------------------------------------------------

_DRAFTS_NEVER_POSTS = (
    '<div class="bgc-note" role="note">'
    "<strong>Drafts, never posts.</strong>"
    "<span>Approving marks a draft ready &mdash; it does not touch any web page. "
    "Typing an approved reply into a site&rsquo;s composer happens in the browser "
    "extension&rsquo;s side panel, on the tab the thread is open in, and a human "
    "still presses the site&rsquo;s own post button. "
    '<a href="/extension">About the extension &rarr;</a></span>'
    "</div>"
)


# ---------------------------------------------------------------------------
# Arena list
# ---------------------------------------------------------------------------

def _arena_card(arena: dict[str, Any]) -> str:
    aid = int(arena["id"])
    pending = int(arena.get("pending_count") or 0)
    drafts = int(arena.get("draft_count") or 0)
    posts = len(arena.get("thread") or [])
    pending_pill = (
        f'<span class="bgc-pill pending">{pending} pending</span>' if pending else ""
    )
    return f"""
    <article class="bgc-card">
      <div class="bgc-card-top">
        <span class="bgc-site">{_e(_site_label(str(arena.get("site") or "")))}</span>
        <h3><a href="/battleground/{aid}">{_e(arena.get("title") or arena.get("url"))}</a></h3>
        {pending_pill}
        {_status_pill(str(arena.get("status") or ""))}
      </div>
      <p class="bgc-meta">
        <span>#{aid}</span>
        <span><b>{_e(_host(str(arena.get("url") or "")))}</b></span>
        <span>cast <b>{_e(_cast_label(arena))}</b></span>
        <span>agent <b>{_e(arena.get("agent_id") or "unassigned")}</b></span>
        <span>{posts} posts</span>
        <span>{drafts} draft{"" if drafts == 1 else "s"}</span>
        <span>updated {_e(_short_ts(arena.get("updated_at")))}</span>
      </p>
    </article>"""


def _render_battleground_index(
    arenas: list[dict[str, Any]], status: str | None = None
) -> str:
    """GET /battleground — every arena on this machine, newest first.

    ``status`` is the active filter (``open`` / ``closed`` / ``None`` for all)
    and is applied by the caller's query, not here; this only lights the chip.
    """
    def chip(label: str, value: str | None) -> str:
        href = "/battleground" + (f"?status={value}" if value else "")
        on = " on" if status == value else ""
        return f'<a class="bgc-chip{on}" href="{href}">{label}</a>'

    if arenas:
        pending_total = sum(int(a.get("pending_count") or 0) for a in arenas)
        lead = (
            f"{len(arenas)} arena{'' if len(arenas) == 1 else 's'}"
            + (f" &middot; {pending_total} draft awaiting a verdict"
               if pending_total == 1 else
               f" &middot; {pending_total} drafts awaiting a verdict"
               if pending_total else "")
        )
        listing = (
            f'<p class="bgc-meta" style="margin:0 0 14px">{lead}</p>'
            '<div class="bgc-list">'
            + "".join(_arena_card(a) for a in arenas)
            + "</div>"
        )
    else:
        listing = (
            '<div class="bgc-empty">'
            "<p>No arenas captured yet.</p>"
            "<p>Arenas are opened from the browser extension: open its side panel on a "
            'comment thread and hit <strong>Capture</strong>. '
            '<a href="/extension">Install the extension &rarr;</a></p>'
            "</div>"
        )

    body = f"""
<div class="orch-shell bgc">
  <header class="orch-head">
    <h2>Battleground console</h2>
    <p>Every arena captured on this machine &mdash; across tabs, and after the tab is
       closed. Review a draft, hand down a verdict, and read a debate&rsquo;s whole
       draft history without the original page open.</p>
  </header>
  {_DRAFTS_NEVER_POSTS}
  <div class="bgc-filters">
    {chip("All", None)}
    {chip("Open", ARENA_OPEN)}
    {chip("Closed", ARENA_CLOSED)}
  </div>
  {listing}
</div>
"""
    return _layout(
        "Battleground", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style><style>{BATTLEGROUND_CSS}</style>",
        active="battleground",
    )


# ---------------------------------------------------------------------------
# Arena detail
# ---------------------------------------------------------------------------

def _post_html(post: dict[str, Any], reply_to: str | None) -> str:
    pid = str(post.get("id") or "")
    is_target = bool(reply_to) and pid == reply_to
    depth = post.get("depth")
    indent = ""
    if isinstance(depth, int) and depth > 0:
        # Cap the visual indent well before the schema's depth ceiling (50) —
        # a deep Reddit chain would otherwise squeeze the text to one column.
        indent = f' style="margin-left:{min(depth, 6) * 18}px"'
    bits = [f'<span class="bgc-author">{_e(post.get("author"))}</span>']
    if is_target:
        bits.append('<span class="bgc-target-tag">reply target</span>')
    for key in ("score", "timestamp"):
        if post.get(key):
            bits.append(f"<span>{_e(post[key])}</span>")
    permalink = post.get("permalink")
    if permalink:
        bits.append(
            f'<a href="{html.escape(str(permalink), quote=True)}" target="_blank" '
            'rel="noopener noreferrer">link &#8599;</a>'
        )
    bits.append(f'<span style="color:var(--muted-2)">{_e(pid)}</span>')
    return (
        f'<div class="bgc-post{" target" if is_target else ""}"{indent}>'
        f'<div class="bgc-post-head">{"".join(bits)}</div>'
        f'<p class="bgc-text">{_e(post.get("text"))}</p>'
        "</div>"
    )


def _draft_html(draft: dict[str, Any], arena_open: bool) -> str:
    did = int(draft["id"])
    status = str(draft.get("status") or "")
    sub_blocks = ""
    if draft.get("rationale"):
        sub_blocks += (
            '<div class="bgc-sub"><b>Rationale (never posted)</b>'
            f'{_e(draft["rationale"])}</div>'
        )
    if draft.get("verdict_note"):
        sub_blocks += (
            f'<div class="bgc-sub"><b>Your note</b>{_e(draft["verdict_note"])}</div>'
        )
    if draft.get("posted_text") and draft.get("posted_text") != draft.get("content"):
        sub_blocks += (
            '<div class="bgc-sub"><b>What actually went on the page</b>'
            f'{_e(draft["posted_text"])}</div>'
        )

    # Which verdicts make sense from here. A closed arena is read-only: the
    # agent can't draft into it, so re-litigating its drafts is noise.
    actions: list[str] = []
    if arena_open and status in (DRAFT_PENDING, DRAFT_REJECTED):
        actions.append(
            f'<button type="button" class="btn btn-primary" '
            f'data-verdict="{DRAFT_APPROVED}" data-draft="{did}">Approve</button>'
        )
    if arena_open and status in (DRAFT_PENDING, DRAFT_APPROVED):
        actions.append(
            f'<button type="button" class="btn" data-verdict="{DRAFT_REJECTED}" '
            f'data-draft="{did}">Reject with a note&hellip;</button>'
        )
    if arena_open and status == DRAFT_APPROVED:
        actions.append(
            f'<button type="button" class="btn" data-verdict="{DRAFT_POSTED}" '
            f'data-draft="{did}">I posted this</button>'
        )
    verdict_row = (
        f'<div class="bgc-verdict">{"".join(actions)}</div>' if actions else ""
    )
    target = draft.get("reply_to")
    target_bit = (
        f'<span>&rarr; {_e(target)}</span>' if target else "<span>&rarr; top level</span>"
    )
    pending_cls = " is-pending" if status == DRAFT_PENDING else ""
    return f"""
    <article class="bgc-draft{pending_cls}" id="draft-{did}" data-draft-row="{did}">
      <div class="bgc-draft-head">
        <span class="bgc-author">{_e(draft.get("agent_id"))}</span>
        {_draft_pill(status)}
        {target_bit}
        <span>#{did}</span>
        <span>{_e(_short_ts(draft.get("created_at")))}</span>
      </div>
      <p class="bgc-text">{_e(draft.get("content"))}</p>
      {sub_blocks}
      {verdict_row}
    </article>"""


def _render_battleground_arena(data: dict[str, Any]) -> str:
    """GET /battleground/{aid} — one arena: the captured thread, the cast, and
    every draft with its verdict."""
    arena = data["arena"]
    drafts = data.get("drafts") or []
    aid = int(arena["id"])
    url = str(arena.get("url") or "")
    status = str(arena.get("status") or "")
    is_open = status == ARENA_OPEN
    reply_to = arena.get("reply_to")
    thread = arena.get("thread") or []

    stance = (
        f'<div class="bgc-stance">{_e(arena["stance"])}</div>'
        if arena.get("stance")
        else '<p class="bgc-meta" style="margin:0 0 22px">No stance brief '
             "&mdash; the agent picks its own line.</p>"
    )

    toggle = (
        f'<button type="button" class="btn" data-arena-status="{ARENA_CLOSED}">'
        "Close arena</button>"
        if is_open
        else f'<button type="button" class="btn" data-arena-status="{ARENA_OPEN}">'
             "Reopen arena</button>"
    )

    posts_html = (
        '<div class="bgc-posts">'
        + "".join(_post_html(p, reply_to if isinstance(reply_to, str) else None)
                  for p in thread)
        + "</div>"
        if thread
        else '<div class="bgc-empty">This arena has no readable posts.</div>'
    )
    drafts_html = (
        "".join(_draft_html(d, is_open) for d in drafts)
        if drafts
        else '<div class="bgc-empty">No drafts yet. The assigned agent writes one '
             "with <code>submit_draft</code> after reading the arena over MCP.</div>"
    )

    persona_body = ""
    if arena.get("persona_body"):
        persona_body = (
            '<div class="bgc-sub"><b>Persona snapshot (as captured)</b>'
            f'{_e(arena["persona_body"])}</div>'
        )

    crumbs = (
        '<a href="/battleground">Battleground</a> '
        f'<span style="color:var(--muted-2)">/ #{aid}</span>'
    )

    body = f"""
<div class="orch-shell bgc" data-arena="{aid}">
  <header class="orch-head">
    <h2>{_e(arena.get("title") or url)}</h2>
    <p class="bgc-head-meta">
      <span class="bgc-site">{_e(_site_label(str(arena.get("site") or "")))}</span>
      {_status_pill(status)}
      <span>#{aid}</span>
      <span>agent <b>{_e(arena.get("agent_id") or "unassigned")}</b></span>
      <span>cast <b>{_e(_cast_label(arena))}</b></span>
      <span>captured {_e(_short_ts(arena.get("created_at")))}</span>
      <a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Open the thread &#8599;</a>
    </p>
  </header>
  {_DRAFTS_NEVER_POSTS}
  {stance}
  {persona_body}
  <div class="bgc-actions">
    {toggle}
    <button type="button" class="btn btn-danger" data-arena-delete="{aid}">Delete arena</button>
  </div>
  <p class="bgc-msg" id="bgc-msg"></p>

  <section class="bgc-sec">
    <h3>Drafts ({len(drafts)})</h3>
    {drafts_html}
  </section>

  <section class="bgc-sec">
    <h3>Captured thread ({len(thread)} posts)</h3>
    <p>What the agent reads. Re-capturing a live page merges new replies in by post
       id &mdash; that happens in the extension, on the tab.</p>
    {posts_html}
  </section>
</div>
<script>
(function () {{
  var shell = document.querySelector('[data-arena]');
  if (!shell) return;
  var aid = shell.getAttribute('data-arena');
  var msg = document.getElementById('bgc-msg');
  var reasons = {json.dumps(list(_REJECT_REASONS))};

  function say(text, bad) {{
    msg.textContent = text || '';
    msg.className = 'bgc-msg' + (bad ? ' fail' : '');
  }}

  function post(path, payload) {{
    return fetch(path, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(payload || {{}})
    }}).then(function (r) {{
      return r.json().catch(function () {{ return {{}}; }}).then(function (d) {{
        if (!r.ok) throw new Error((d && d.error) || ('HTTP ' + r.status));
        return d;
      }});
    }});
  }}

  document.addEventListener('click', function (ev) {{
    var t = ev.target;
    if (!t || !t.closest) return;
    var el = t.closest('[data-verdict], [data-arena-status], [data-arena-delete]');
    if (!el) return;

    var verdict = el.getAttribute('data-verdict');
    if (verdict) {{
      var payload = {{verdict: verdict}};
      if (verdict === 'rejected') {{
        var note = window.prompt(
          'Why? The agent reads this as a revision brief.\\n\\n' + reasons.join('\\n'),
          reasons[0]
        );
        if (note === null) return;
        if (note.trim()) payload.note = note.trim();
      }}
      say('Saving\\u2026');
      post('/api/battleground/drafts/' + el.getAttribute('data-draft') + '/verdict', payload)
        .then(function () {{ window.location.reload(); }})
        .catch(function (e) {{ say(String(e.message || e), true); }});
      return;
    }}

    var next = el.getAttribute('data-arena-status');
    if (next) {{
      say('Saving\\u2026');
      post('/api/battleground/arenas/' + aid, {{status: next}})
        .then(function () {{ window.location.reload(); }})
        .catch(function (e) {{ say(String(e.message || e), true); }});
      return;
    }}

    if (el.getAttribute('data-arena-delete')) {{
      if (!window.confirm('Delete arena #' + aid + ' and every draft on it? This cannot be undone.')) return;
      say('Deleting\\u2026');
      post('/api/battleground/arenas/' + aid + '/delete', {{}})
        .then(function () {{ window.location.href = '/battleground'; }})
        .catch(function (e) {{ say(String(e.message || e), true); }});
    }}
  }});
}})();
</script>
"""
    return _layout(
        f"Arena #{aid}", crumbs, body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style><style>{BATTLEGROUND_CSS}</style>",
        active="battleground",
    )


def _render_battleground_not_found(aid: int) -> str:
    body = f"""
<div class="orch-shell bgc">
  <header class="orch-head">
    <h2>No arena #{aid}</h2>
    <p>It was deleted, or it never existed on this machine. Arenas are local &mdash;
       they don&rsquo;t sync, so an id from another install won&rsquo;t resolve here.</p>
  </header>
  <div class="bgc-actions">
    <a class="btn btn-primary" href="/battleground">All arenas</a>
    <a class="btn" href="/extension">About the extension</a>
  </div>
</div>
"""
    return _layout(
        "Arena not found", '<a href="/battleground">Battleground</a>', body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style><style>{BATTLEGROUND_CSS}</style>",
        active="battleground",
    )


# ---------------------------------------------------------------------------
# Hosted mirror
# ---------------------------------------------------------------------------

def _render_battleground_readonly() -> str:
    """Hosted /battleground — an explainer, because the mirror has no arenas.

    Not merely "writes are blocked": ``battleground_arenas`` and
    ``battleground_drafts`` are deliberately absent from the sidecar's column
    lists, so captured third-party page content never leaves the machine that
    captured it. A hosted arena list would be empty forever and would imply the
    opposite.
    """
    body = f"""
<div class="orch-shell bgc">
  <header class="orch-head">
    <h2>Arenas stay on the machine that captured them</h2>
    <p>This hosted site is a <strong>read-only demo</strong>. It has no arenas to show
       you &mdash; and that isn&rsquo;t an empty database. The two AgentBattleground
       tables are deliberately excluded from the sync that fills this mirror, so a
       comment thread you captured in your browser never reaches a server you
       don&rsquo;t run.</p>
  </header>
  {_DRAFTS_NEVER_POSTS}
  <div class="bgc-empty">
    <p>Run the web UI locally and the console lives at
       <code>http://127.0.0.1:8765/battleground</code>.</p>
    <p><a href="/extension">What AgentBattleground is &rarr;</a> &middot;
       <a href="{_REPO}/blob/main/docs/Guides/online-forums.md" target="_blank" rel="noopener noreferrer">How to participate in online forums &#8599;</a></p>
  </div>
</div>
"""
    return _layout(
        "Battleground", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style><style>{BATTLEGROUND_CSS}</style>",
        active="battleground",
    )
