"""Shared rendering helpers: Markdown, the page shell, icons, cast labels."""

from __future__ import annotations

import html
import json
from typing import Any

from markdown_it import MarkdownIt

from web.assets import BASE_CSS, MARK_SVG, SHELL_JS
from web.security import _is_public_readonly


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

# `gfm-like` turns linkify ON, and markdown-it-py raises *at render time* — not
# at import — when `linkify-it-py` is missing. That failure mode is the worst
# kind: the homepage renders (no URLs in it), so the app and its health check
# both look fine, while every transcript carrying a link answers 500. It
# happened here for real, on a server started with the system interpreter
# instead of the venv.
#
# So prove the renderer works on the one input that exercises the optional
# dependency, at import, and refuse to serve a half-working app. This costs one
# render per boot and turns a silent 500-per-transcript into a message naming
# the fix.
try:
    _md.render("https://example.com")
except Exception as e:  # noqa: BLE001 — re-raised below with the actionable text
    raise RuntimeError(
        f"Markdown rendering is broken at startup ({type(e).__name__}: {e}). "
        "This usually means the server was started with the wrong Python: "
        "`gfm-like` needs `linkify-it-py`, which is pinned in requirements.txt "
        "but is not in a bare system interpreter. Start it with the venv — "
        r".\.venv\Scripts\python.exe src\web_ui.py"
    ) from e


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

# Persona Registry — the public catalogue of downloadable persona cards, also on
# the AI-Automation-Library site. Cards pulled from there are imported into a
# local instance through /personas ("Import cards").
REGISTRY_URL = "https://library.mikesailab.com/tools/persona-registry/"

# Repo home — the topbar's far-right GitHub button and a palette entry.
GITHUB_URL = "https://github.com/ai-automation-tools/Agent-chat"

# Shared web fonts + preconnects. Identical on the _layout() shell and the
# homepage; kept here so the two <head>s can't drift apart.
FONTS_HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700'
    "&family=IBM+Plex+Mono:wght@400;500&family=JetBrains+Mono:wght@400;500;700;800"
    '&display=swap" rel="stylesheet">'
)

# Feather-style stroke icons for the nav row (MIT). Inline rather than a CDN
# icon font — the local operator's page must render with no network.
_NAV_ICONS = {
    "chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "orch": (
        '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
        '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
        '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
        '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
        '<line x1="17" y1="16" x2="23" y2="16"/>'
    ),
    "pers": (
        '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
        '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    "thea": (
        '<rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/>'
        '<line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/>'
        '<line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/>'
        '<line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/>'
        '<line x1="17" y1="7" x2="22" y2="7"/>'
    ),
    "reg": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'
    ),
    "home": (
        '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/>'
    ),
    "res": '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    # Puzzle piece — the browser extension.
    "extn": (
        '<path d="M10 3.5a2 2 0 1 1 4 0V5h3a1 1 0 0 1 1 1v3h1.5a2 2 0 1 1 0 4H18v3a1 1 0 0 1-1 1h-3v1.5'
        'a2 2 0 1 1-4 0V17H7a1 1 0 0 1-1-1v-3H4.5a2 2 0 1 1 0-4H6V6a1 1 0 0 1 1-1h3z"/>'
    ),
    # Terminal prompt — kept for the standalone CLI-setup renderer.
    "setup": '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    # Gear — /settings, which now holds CLI tools, notifications and delivery.
    "gear": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06'
        'a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09'
        'A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83'
        'l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09'
        'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83'
        'l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09'
        'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83'
        'l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09'
        'a1.65 1.65 0 0 0-1.51 1z"/>'
    ),
    # Bell — "tell me when a run finishes or gets stuck".
    "bell": (
        '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>'
        '<path d="M13.73 21a2 2 0 0 1-3.46 0"/>'
    ),
    # Crosshair — the arena console. Deliberately next to the puzzle piece:
    # /extension explains AgentBattleground, /battleground operates it.
    "arena": (
        '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.4"/>'
        '<line x1="12" y1="1.5" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22.5"/>'
        '<line x1="1.5" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22.5" y2="12"/>'
    ),
}


def _nav_svg(name: str) -> str:
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{_NAV_ICONS[name]}</svg>"
    )


# The nav rail, top to bottom. (key, label, href, icon, css-class, external?)
# `key` is what callers pass as active= to light the current page. Home leads:
# the rail reads as a hierarchy, not a toolbar, so the root belongs at the top.
#
# The rail is deliberately in TWO tables. `_NAV_ITEMS` is this app — pages this
# server renders and the operator acts on. `_RESOURCE_NAV_ITEMS` is everything
# else: reference material and the two sibling properties on the
# AI-Automation-Library site. They used to sit in one undifferentiated column,
# which made "Theater" look like a page of this app. `_sidebar()` renders the
# second group under a labelled separator so the distinction is visible rather
# than implied by the little ↗ marker alone.
_NAV_ITEMS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    ("home", "Home", "/", "home", "btn-home", False),
    ("conversations", "Conversations", "/conversations", "chat", "btn-conv", False),
    ("orchestrate", "Orchestrate", "/orchestrate", "orch", "btn-orch", False),
    ("personas", "Personas", "/personas", "pers", "btn-pers", False),
    ("extension", "Browser extension", "/extension", "extn", "btn-extn", False),
    ("battleground", "Battleground", "/battleground", "arena", "btn-arena", False),
    ("settings", "Settings", "/settings", "gear", "btn-setup", False),
)

# Reference + third-party destinations. "Resources" points at `/#resources`
# rather than a bare `#resources` fragment precisely so it can live here: as an
# in-page anchor it scrolled to nothing from every page but the homepage, which
# is why it used to be passed in through `extra_nav`.
_RESOURCE_NAV_ITEMS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    ("resources", "Resources", "/#resources", "res", "btn-res", False),
    ("registry", "Persona Registry", REGISTRY_URL, "reg", "btn-reg", True),
    ("theater", "Theater", THEATER_URL, "thea", "btn-thea", True),
)

_GH_MARK = (
    '<svg viewBox="0 0 16 16" width="17" height="17" fill="currentColor" aria-hidden="true">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49'
    "-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 "
    "1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36"
    "-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 "
    "1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 "
    '1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>'
)

# Runs before any chrome paints — must stay tiny, synchronous, and first.
# `js` gates the scroll-reveal styles: content that a script hides must only
# ever be hidden when a script is there to show it again, or one failure blanks
# the page (which is exactly what happened — see assets.SHELL_JS).
# `rail-collapsed` is restored here rather than from SHELL_JS so the sidebar
# can't paint open and then snap shut on DOMContentLoaded.
_BOOT_JS = (
    "<script>(function(){var e=document.documentElement;e.classList.add('js');"
    "try{if(localStorage.getItem('ab-rail')==='0')e.classList.add('rail-collapsed');}"
    "catch(_){}})();</script>"
)

# The palette dialog + the JS that drives it (and the live pill, and reveals).
# Emitted once per page by _topbar(), directly after the bar.
_CMDK_HTML = f"""
<div class="cmdk" id="cmdk" hidden>
  <div class="cmdk-scrim" data-cmdk-close></div>
  <div class="cmdk-panel" role="dialog" aria-modal="true" aria-label="Search AgentChat">
    <div class="cmdk-field">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input id="cmdk-input" type="text" role="combobox" aria-expanded="true" aria-controls="cmdk-list"
             aria-autocomplete="list" autocomplete="off" spellcheck="false"
             placeholder="Search conversations, personas, pages&hellip;" />
      <kbd>Esc</kbd>
    </div>
    <ul class="cmdk-list" id="cmdk-list" role="listbox" aria-label="Results"></ul>
    <div class="cmdk-foot">
      <span><kbd>&uarr;</kbd><kbd>&darr;</kbd> navigate</span>
      <span><kbd>&crarr;</kbd> open</span>
      <span class="cmdk-count" id="cmdk-count"></span>
    </div>
  </div>
</div>
<script>window.__AB_LINKS = {{"theater": "{THEATER_URL}", "registry": "{REGISTRY_URL}", "github": "{GITHUB_URL}"}};</script>
{SHELL_JS}
"""


def _sidebar(
    active: str = "",
    extra_nav: tuple[tuple[str, str, str, str, str, bool], ...] = (),
) -> str:
    """The universal navigation rail — a 64px icon column down the left.

    This is the app's navigation. It's the same on every page, which is the
    point: nav that never moves. It's ``position:fixed`` (see TOPBAR_CSS
    ``.siderail``) rather than a grid column, because /conversations and
    /personas already own their own scrolling rails and full-height panes — a
    fixed rail insets them with one ``margin-left`` instead of rewriting their
    layout, and it sits beside their rails rather than fighting them.

    ``active`` is a key from ``_NAV_ITEMS``: it lights that row and marks it
    ``aria-current``.

    The rail opens with the **brand row** — the mark and wordmark (a link home,
    the artwork the browser tab shows) with the collapse toggle beside it. That
    identity used to sit in the topbar's left corner; it belongs at the top of
    the navigation it labels, and the toggle rides with it because collapsing
    the rail is chrome for the rail, not one more destination.

    **Expanded by default**, showing each destination's title; the toggle
    collapses it to icons and persists that in ``localStorage`` under
    ``ab-rail`` (restored by ``_BOOT_JS`` before first paint, so it can't flash
    open and snap shut). Collapsed, the title moves to a hover tooltip — but it
    is *always* on ``aria-label`` too, so the rail never depends on hover or on
    CSS to be identifiable.

    The rail has two fixed sections: this app's pages (``_NAV_ITEMS``), then
    reference and third-party destinations (``_RESOURCE_NAV_ITEMS``) under a
    labelled separator. The label is hidden when the rail is collapsed, where
    the separator alone carries the grouping.

    ``extra_nav`` takes rows in ``_NAV_ITEMS`` shape and appends them at the
    very bottom, for links that exist on exactly one page. Nothing uses it
    today — the homepage's ``#resources`` jump graduated into the shared
    resources table once it was repointed at ``/#resources`` — but the hook
    stays for the next page-specific destination.
    """

    def btn(row: tuple[str, str, str, str, str, bool]) -> str:
        key, label, href, icon, cls, external = row
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        tip = f"{label} &#8599;" if external else label
        aria = ' aria-current="page"' if key == active else ""
        on = " is-active" if key == active else ""
        arrow = ' <span class="rail-ext" aria-hidden="true">&#8599;</span>' if external else ""
        return (
            f'<a class="rail-btn {cls}{on}" href="{href}"{attrs}{aria} '
            f'data-tip="{tip}" aria-label="{label}">{_nav_svg(icon)}'
            f'<span class="rail-lbl">{label}{arrow}</span></a>'
        )

    items = "".join(btn(r) for r in _NAV_ITEMS)
    items += (
        '<span class="rail-sep" aria-hidden="true"></span>'
        '<span class="rail-glabel">Resources</span>'
        + "".join(btn(r) for r in _RESOURCE_NAV_ITEMS)
    )
    if extra_nav:
        items += '<span class="rail-sep" aria-hidden="true"></span>'
        items += "".join(btn(r) for r in extra_nav)
    brand = (
        '<div class="rail-brand">'
        '<a class="rail-mark" href="/" aria-label="AgentChat &mdash; home">'
        f'<span class="glyph" aria-hidden="true">{MARK_SVG}</span>'
        '<span class="rail-lbl">AgentChat</span></a>'
        '<button type="button" class="rail-toggle" id="rail-toggle" '
        'aria-label="Collapse sidebar" title="Collapse sidebar" aria-expanded="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<rect x="3" y="3" width="18" height="18" rx="2.5"/>'
        '<line x1="9.5" y1="3" x2="9.5" y2="21"/></svg>'
        "</button></div>"
    )
    return f'<nav class="siderail" aria-label="Main">{brand}{items}</nav>'


def _topbar(crumbs_html: str = "") -> str:
    """The one topbar, rendered by every page.

    Full-bleed: the breadcrumb sits in the literal left corner and the actions
    in the right one (see TOPBAR_CSS — ``.topbar-inner`` has no max-width, and
    ``.topbar-right`` is pushed out by ``margin-left:auto``).

    Neither navigation nor identity is here: both live in ``_sidebar()`` — the
    mark and wordmark moved to the top of the rail, beside the collapse
    toggle. The bar carries the breadcrumb, status (live pill), and the two
    things that aren't destinations: search and the repo link.

    The live pill renders idle and is corrected within a tick by the polling
    script — server-rendering a count here would only bake in a number that
    goes stale the moment a debate ends.

    The homepage used to hand-maintain its own near-identical <header>; both it
    and ``_layout()`` now call this, so the bar cannot drift between them.
    """
    crumb_block = f'<span class="crumb">{crumbs_html}</span>' if crumbs_html else ""
    return f"""{_BOOT_JS}
<div class="topbar">
  <div class="topbar-inner">
    {crumb_block}
    <div class="topbar-right">
      <a class="live-pill idle" id="ab-live" href="/conversations">
        <span class="dot" aria-hidden="true"></span><span class="live-txt">system online</span>
      </a>
      <button type="button" class="cmdk-trigger" data-cmdk-open aria-label="Search (Control K)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <span class="cmdk-trigger-txt">Search</span>
        <kbd>Ctrl K</kbd>
      </button>
      <span class="topbar-div" aria-hidden="true"></span>
      <a class="gh-link" href="{GITHUB_URL}" target="_blank" rel="noopener noreferrer" aria-label="View source on GitHub">{_GH_MARK}</a>
    </div>
  </div>
</div>
{_CMDK_HTML}"""


def demo_banner() -> str:
    """The hosted mirror's "this is a demo" strip, or ``""`` locally.

    Rendered by ``_layout()`` (so every inner page carries it) and by the
    homepage template. It keys off the **same** env flag
    ``ReadOnlyMiddleware`` enforces on, so what the page promises and what the
    server does cannot drift: if the banner is showing, mutations 403, and if
    mutations 403, the banner is showing.

    Deliberately not dismissible. Someone arriving on a shared
    ``/conversations/<id>`` link has no other cue that Stop, Delete and the
    persona editor in front of them are going to fail, and a notice they can
    hide is a notice that isn't there for the next person on the same link.
    """
    if not _is_public_readonly():
        return ""
    return (
        '<div class="demo-strip" role="note">'
        '<span class="demo-tag">Read-only demo</span>'
        "<span class=\"demo-txt\">This hosted mirror shows real conversations but can't "
        "run them &mdash; nothing here can be changed. "
        f'<a href="{GITHUB_URL}" target="_blank" rel="noopener noreferrer">'
        "Clone the repo</a> to run your own locally.</span>"
        "</div>"
    )


def _layout(
    title: str,
    crumbs_html: str,
    body_html: str,
    head_extras: str = "",
    active: str = "",
) -> str:
    """The shell every page but the homepage renders into.

    ``crumbs_html`` **defaults to the page title**. Nine of the eleven call
    sites passed ``""`` and got a topbar with nothing in it but the wordmark,
    so the bar said the same thing on /settings as on /battleground and the
    only "where am I" signal was the lit rail row. Deriving it costs no call
    site an argument, and the two pages that want something richer (/personas,
    an arena) still pass their own and win.
    """
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)} — AgentChat</title>
<meta name="theme-color" content="#060606" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
{FONTS_HEAD}
<style>{BASE_CSS}</style>
{head_extras}
</head><body>
<a class="skip-link" href="#main">Skip to content</a>
{_topbar(crumbs_html or f'<strong>{html.escape(title)}</strong>')}
{demo_banner()}
{_sidebar(active)}
<main id="main" tabindex="-1">{body_html}</main>
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

def _conv_debater_casts(c: dict[str, Any]) -> list[tuple[str, str]]:
    """``(display name, persona slug)`` per debater — slug ``""`` when no persona
    was recorded. The featured panel needs the slug alongside the name to resolve
    an avatar image (``web.avatars.avatar_url``). Slug-carrying twin of
    :func:`_conv_debaters`."""
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
        out: list[tuple[str, str]] = []
        for aid in order:
            entry = personas.get(aid)
            if isinstance(entry, dict) and entry.get("persona_name"):
                out.append((str(entry["persona_name"]), str(entry.get("persona_slug") or str(aid))))
            else:
                # No persona → the agent id doubles as its CLI brand-avatar slug.
                out.append((str(aid), str(aid)))
        if out:
            return out
    return [(p, p) for p in participants]


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
