"""Shared rendering helpers: Markdown, the page shell, icons, cast labels."""

from __future__ import annotations

import html
import json
from typing import Any

from markdown_it import MarkdownIt

from web.assets import BASE_CSS


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

# Debate Chat Theater — the public cinematic viewer for published debates,
# hosted on the AI-Automation-Library site. Rebuilt from Content/Agent-Debates/
# on every Site deploy; only debates published via scripts/publish_debate.py
# appear there.
THEATER_URL = "https://library.mikesailab.com/tools/debate-chat-theater/"


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
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=JetBrains+Mono:wght@400;500;700;800&display=swap" rel="stylesheet">
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
      <a href="{THEATER_URL}" target="_blank" rel="noopener noreferrer" title="Watch published debates in the Debate Chat Theater">Theater&nbsp;&#8599;</a>
      <a class="cta" href="/">Home</a>
    </nav>
  </div>
</div>
<main>{body_html}</main>
</body></html>"""

def _conv_cast_label(c: dict[str, Any]) -> str:
    """Display label for a conversation's participants on the homepage 'latest'
    list: persona names (' · '-joined) when the conversation recorded a cast in
    ``participant_personas``, else the raw agent ids. Returns a plain (unescaped)
    string for the caller to escape."""
    participants = [str(p) for p in (c.get("participants") or [])]
    raw = c.get("participant_personas")
    personas: Any = raw
    if isinstance(raw, str) and raw:
        try:
            personas = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            personas = None
    if isinstance(personas, dict) and personas:
        order = participants or list(personas.keys())
        names: list[str] = []
        for aid in order:
            entry = personas.get(aid)
            if isinstance(entry, dict) and entry.get("persona_name"):
                names.append(str(entry["persona_name"]))
            else:
                names.append(str(aid))
        if names:
            return " · ".join(names)
    return ", ".join(participants)


def _conv_debaters(c: dict[str, Any]) -> list[str]:
    """The individual debater display names for a conversation: persona names
    when a cast is recorded in ``participant_personas``, else the raw agent ids.
    List form of ``_conv_cast_label`` — the featured panel needs the names split
    out to draw a monogram per debater."""
    participants = [str(p) for p in (c.get("participants") or [])]
    raw = c.get("participant_personas")
    personas: Any = raw
    if isinstance(raw, str) and raw:
        try:
            personas = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            personas = None
    if isinstance(personas, dict) and personas:
        order = participants or list(personas.keys())
        names: list[str] = []
        for aid in order:
            entry = personas.get(aid)
            if isinstance(entry, dict) and entry.get("persona_name"):
                names.append(str(entry["persona_name"]))
            else:
                names.append(str(aid))
        if names:
            return names
    return participants

def _initials(name: str) -> str:
    """Monogram for the persona avatar: first letters of the first two words."""
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


# Small inline stroke icons (Feather, MIT) reused across the persona console.
# Kept inline rather than pulling an icon-library CDN dep into this single-file
# Starlette app (the page must work offline for the local operator).
_PM_ICONS = {
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "edit": '<path d="M17 3a2.83 2.83 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5z"/><line x1="15" y1="5" x2="19" y2="9"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "doc": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
}


def _pm_svg(name: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{_PM_ICONS[name]}</svg>'
    )

def _render_generic_404(path: str) -> str:
    body = (
        '<div class="empty" style="padding:64px 24px;text-align:center;display:flex;'
        'flex-direction:column;align-items:center;gap:4px;">'
        '<div style="font-family:\'JetBrains Mono\',ui-monospace,monospace;font-size:40px;'
        'font-weight:800;color:var(--accent);line-height:1;">404</div>'
        '<h2 style="margin:10px 0 2px;">Page not found</h2>'
        f'<p style="color:var(--muted);margin:0;">Nothing lives at <code>{html.escape(path)}</code>.</p>'
        '<div style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap;justify-content:center;">'
        '<a class="btn btn-primary" href="/conversations">Browse conversations</a>'
        '<a class="btn" href="/">Home</a></div>'
        '</div>'
    )
    return _layout("Not found", "", body)
