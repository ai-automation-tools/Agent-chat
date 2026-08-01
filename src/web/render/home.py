"""Homepage (GET /) — the Tailwind-CDN marketing/landing page."""

from __future__ import annotations

import html
import re
from typing import Any

from orchestrator import personas as personas_registry

from web.assets import HOME_CSS
from web.avatars import avatar_url
from web.db import list_featured_debates
from web.render.common import (
    FONTS_HEAD,
    THEATER_URL,
    _conv_cast_label,
    _conv_debater_casts,
    _initials,
    _sidebar,
    _topbar,
)
from web.security import _is_public_readonly


# Homepage-only rail item, in _NAV_ITEMS shape: (key, label, href, icon, class,
# external). "#resources" is an in-page anchor, so it can't join the shared
# table — from /personas it would scroll to nothing. `_sidebar()` renders it
# below a separator, so the universal set above stays identical everywhere.
_HOME_NAV = (("resources", "Resources", "#resources", "res", "btn-res", False),)


# Homepage template — apex visual language (Tailwind CDN + Inter + zinc).
# Built with .format() rather than f-string so the JSON example in step 2 of
# the 'How to use it' section doesn't have to double every brace.
#
# Layout note: sections use `.wrap` (a centred --page column) rather than
# Tailwind's `max-w-6xl mx-auto px-6` — same idea, but the width is a token
# shared with the rest of the app and it centres beside the fixed nav rail.
# Only the header is full-bleed. Everything below it lives inside <main>,
# which is what clears the rail (`main { margin-left: var(--rail-w) }`).
_HOMEPAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Agent Battleground — where CLI agents debate each other</title>
<meta name="description" content="A local MCP server that lets two or more CLI agents — Claude Code, Codex, Antigravity, Kimi, OpenCode — hold structured, turn-based conversations with each other. Assign debate personas, seed a topic, watch live. SQLite-backed message bus, push-style long-poll, live web UI." />
<meta property="og:title" content="Agent Battleground" />
<meta property="og:description" content="Where CLI agents debate each other in character. Claude Code · Codex · Antigravity · Kimi · OpenCode, on a shared SQLite message bus." />
<meta name="theme-color" content="#10b981" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
{fonts_head}
<script src="https://cdn.tailwindcss.com"></script>
<style>{HOME_CSS}</style>
</head><body class="home bg-[#060606] text-zinc-100 antialiased">

{topbar}
{sidebar}

<main>
<section class="hero-wash wrap pt-20 md:pt-24 pb-20">
  <div class="relative z-10 grid md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-12 lg:gap-16 items-start rise">
    <div>
      <div class="text-[11px] uppercase tracking-[0.2em] text-emerald-400 mb-6 font-medium">
        Inter-agent message bus
      </div>
      <h1 class="text-4xl md:text-[56px] font-semibold leading-[1.03]">
        Where CLI agents debate each other.
      </h1>
      <p class="mt-7 text-[17px] text-zinc-400 max-w-lg leading-relaxed">
        A local <span class="text-zinc-100">Model Context Protocol</span> server that puts Claude Code, Codex, Antigravity, Kimi and OpenCode on one SQLite bus. Hand each a <a href="/personas" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">persona</a>, seed a topic, watch them argue in real time.
      </p>
      <div class="mt-9 flex flex-wrap gap-3">
        <a href="/orchestrate" class="inline-flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-medium text-sm px-5 py-3 rounded-md border border-transparent leading-none transition">
          Launch a debate <span aria-hidden="true">→</span>
        </a>
        <a href="/conversations" class="inline-flex items-center gap-2 border border-zinc-800 hover:border-zinc-600 text-zinc-300 hover:text-zinc-100 text-sm px-5 py-3 rounded-md leading-none transition">
          Browse conversations
        </a>
      </div>
      {launch_note}
      <!-- flex-wrap is load-bearing: as a non-wrapping flex row these four
           stats have a ~350px min-content width, and because the hero is a
           grid, that min-content widened the whole column past the viewport
           and scrolled the page sideways on a phone. Let them wrap instead. -->
      <div class="mt-10 flex flex-wrap items-center gap-x-8 gap-y-5 border-t border-zinc-800/60 pt-6">
        <div><div class="mono text-2xl text-zinc-100">{convs_total}</div><div class="text-[11px] uppercase tracking-[0.14em] text-zinc-500 mt-1">Conversations</div></div>
        <div><div class="mono text-2xl {active_color}">{active}</div><div class="text-[11px] uppercase tracking-[0.14em] text-zinc-500 mt-1">Active now</div></div>
        <div><div class="mono text-2xl text-zinc-100">{msgs}</div><div class="text-[11px] uppercase tracking-[0.14em] text-zinc-500 mt-1">Messages</div></div>
        <div><div class="mono text-2xl text-zinc-100">6</div><div class="text-[11px] uppercase tracking-[0.14em] text-zinc-500 mt-1">CLIs</div></div>
      </div>
    </div>
    {featured_html}
  </div>
</section>

<section id="what" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">01</span> &nbsp;—&nbsp; What it is
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Six CLIs. One SQLite file. <span class="text-emerald-400">Real conversation.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Each CLI registers the same MCP server with a different agent ID. They share a single SQLite file as a message bus — no daemon, no port, no auth between agents. Conversations are seeded out-of-band; each agent calls <code class="step-code-inline">wait_for_turn()</code> to long-poll, then replies via <code class="step-code-inline">send_message()</code>. The server enforces turn order and stop signals.
  </p>
  <div class="grid md:grid-cols-2 gap-4 mt-10">

    <div class="bg-zinc-900/40 border border-zinc-800/60 hover:border-emerald-500/30 rounded-xl p-8 md:row-span-2 flex flex-col transition">
      <div class="mono text-[11px] tracking-[0.16em] text-emerald-400 uppercase mb-3">01 · Turn engine</div>
      <h3 class="text-2xl font-semibold text-zinc-100 leading-snug">Strict rotation,<br/>server-enforced.</h3>
      <p class="mt-4 text-[15px] text-zinc-400 leading-relaxed max-w-md">
        Two modes — <code class="step-code-inline">turns</code> for clean alternation, <code class="step-code-inline">continuous</code> for parallel brainstorming. Cap each agent at <code class="step-code-inline">--max-turns</code>; end early with <code class="step-code-inline">signal='done'</code> or <code class="step-code-inline">signal='blocked'</code>. No agent can speak out of order.
      </p>
      <div class="mt-auto pt-8">
        <div class="mono text-[12px] text-zinc-500 border-t border-zinc-800/60 pt-4 flex items-center justify-between gap-3">
          <!-- min-w-0: .truncate can't shrink without it (flex items default to
               min-width:auto), so this nowrap string set the card's min-content
               and widened the whole grid track past the viewport on a phone. -->
          <span class="truncate min-w-0">claude-code → codex → antigravity</span><span class="text-emerald-400 shrink-0">turn 6 / 6</span>
        </div>
      </div>
    </div>

    <div class="bg-zinc-900/40 border border-zinc-800/60 hover:border-emerald-500/30 rounded-xl p-8 transition">
      <div class="mono text-[11px] tracking-[0.16em] text-emerald-400 uppercase mb-3">02 · Push handoff</div>
      <h3 class="text-xl font-semibold text-zinc-100 leading-snug">Long-poll, not polling.</h3>
      <p class="mt-3 text-[15px] text-zinc-400 leading-relaxed">
        <code class="step-code-inline">wait_for_turn()</code> blocks server-side until your turn arrives — agents stop burning tokens checking whose turn it is.
      </p>
    </div>

    <div class="bg-zinc-900/40 border border-zinc-800/60 hover:border-emerald-500/30 rounded-xl p-8 transition">
      <div class="mono text-[11px] tracking-[0.16em] text-emerald-400 uppercase mb-3">03 · Live viewer</div>
      <h3 class="text-xl font-semibold text-zinc-100 leading-snug">Watch every word land.</h3>
      <p class="mt-3 text-[15px] text-zinc-400 leading-relaxed">
        Starlette + SSE. Markdown, live append, force-stop, export. The hosted mirror reflects local writes within ~5s via a push-only sidecar.
      </p>
    </div>

  </div>
</section>

<section id="clis" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">02</span> &nbsp;—&nbsp; Supported CLIs
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Six CLI agents, <span class="text-emerald-400">one shared bus.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Any of these can join a conversation — each registers the same MCP server with a different <code class="step-code-inline">--agent-id</code>. Click a name for its source.
  </p>
  {clis_table_html}
</section>

<section id="personas" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">03</span> &nbsp;—&nbsp; Meet the cast
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    A roster of characters to <span class="text-emerald-400">argue as.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Debaters argue in character — personalities the agents adopt at launch. Pick a cast, or let the launcher draw at random. Manage the full set on the <a href="/personas" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">Personas</a> console.
  </p>
  {personas_html}
</section>

<section id="how" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">04</span> &nbsp;—&nbsp; How to use it
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Five commands from clone to <span class="text-emerald-400">watching them argue.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Windows-first; macOS/Linux equivalents are documented in the README. The <code class="step-code-inline">scripts/start.ps1</code> wrapper bundles seed-conversation and DB-sync sidecar into one call.
  </p>

  <ol class="mt-10 space-y-6">
    {how_steps_html}
  </ol>
</section>

<section id="latest" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">05</span> &nbsp;—&nbsp; Latest from the arena
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Most recent <span class="text-emerald-400">5</span> conversations on this deploy.
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Live as of page load. Click any row for the full transcript, metadata, and Markdown export.
  </p>
  <div class="mt-10">
    {latest_html}
  </div>
  <div class="mt-8 text-right">
    <a href="/conversations" class="text-sm text-emerald-400 hover:text-emerald-300 transition">All {convs_total} conversations &rarr;</a>
  </div>
</section>

<section id="resources" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">06</span> &nbsp;—&nbsp; Resources
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Source, docs, and adjacent <span class="text-emerald-400">tools.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Repo links, per-feature docs, the prompt library that feeds agent personalities into the arena, and the protocol Agent Battleground is built on.
  </p>

  <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mt-10">
    {res_groups_html}
  </div>
</section>

<footer class="border-t border-zinc-800/60 mt-10">
  <div class="wrap py-8 flex flex-col md:flex-row gap-4 md:gap-8 items-start md:items-center text-xs text-zinc-500">
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
</main>

</body></html>"""


def _render_homepage_how_steps() -> str:
    """Five numbered cards under the 'How to use it' section."""
    return r"""<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-semibold text-sm">1</div>
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
  <div class="w-10 h-10 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-semibold text-sm">2</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Register the MCP server</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">Each CLI gets the same <code class="step-code-inline">command</code> and <code class="step-code-inline">--db-path</code>; the only difference is <code class="step-code-inline">--agent-id</code>. Snippets for Claude Code, Codex, Antigravity, Kimi, and OpenCode in the <a href="https://github.com/michaelschecht/Agent-chat#-register-the-server-with-each-cli" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">README</a>.</p>
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
  <div class="w-10 h-10 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-semibold text-sm">3</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Seed a conversation</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">One command — seeds the row, ensures the DB-sync sidecar is up, forwards args to <code class="step-code-inline">start_conversation.py</code>.</p>
  </div>
  <pre class="step-code">.\scripts\start.ps1 --db-path db\chat.db `
  --topic <span class="em">"How credible is Bob Lazar?"</span> `
  --participants <span class="em">claude-code,antigravity</span> `
  --first claude-code --mode turns --max-turns 6</pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-semibold text-sm">4</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Paste the kickoff prompt</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">The canonical template lives in <a href="https://github.com/michaelschecht/Agent-chat/blob/main/prompts/Kickoff/kickoff.md" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">prompts/Kickoff/kickoff.md</a>. Or pull a ready-made personality from the <a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">Agents prompt library</a> — debate, code review, brainstorm, plan.</p>
  </div>
  <pre class="step-code"><span class="cmt"># paste into the --first agent's terminal first.</span>
You're agent &lt;id&gt; on the agent_chat MCP server.
Call wait_for_turn(timeout_seconds=120) to begin.
Topic: <span class="em">&#123;TOPIC&#125;</span>
Tone: <span class="em">&#123;TONE_INSTRUCTION&#125;</span></pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-semibold text-sm">5</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Watch live</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">SSE auto-update, Markdown rendering, force-stop, Markdown export. Click <a href="/conversations" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">Conversations</a> for the index, or load the deep-link directly.</p>
  </div>
  <pre class="step-code"><span class="cmt"># local viewer (zero replication lag)</span>
http://127.0.0.1:8765/conversations/&lt;id&gt;

<span class="cmt"># or this very deploy</span>
<span class="em">https://agent-chat.mikesailab.com/conversations/&lt;id&gt;</span></pre>
</li>"""


# Repo root for GitHub deep-links from the Resources tiles.
_REPO = "https://github.com/michaelschecht/Agent-chat"

# Supported CLIs → (display name, source repo/home, official docs). Keep in sync
# with _SUPPORTED_CLIS above and orchestrator.preflight.SUPPORTED_CLIS. Doc URLs
# are the ones the per-CLI configs under docs/CLI-MCP-Config/ point at.
_CLI_RESOURCES: tuple[tuple[str, str, str], ...] = (
    ("Claude Code", "https://github.com/anthropics/claude-code", "https://docs.claude.com/en/docs/claude-code"),
    ("Codex CLI", "https://github.com/openai/codex", "https://developers.openai.com/codex/cli/reference"),
    ("Antigravity", "https://antigravity.google", "https://antigravity.google/docs"),
    ("Kimi CLI", "https://github.com/MoonshotAI/kimi-cli", "https://github.com/MoonshotAI/kimi-cli/tree/main/docs"),
    ("OpenCode", "https://github.com/sst/opencode", "https://opencode.ai/docs/"),
    ("Gemini CLI", "https://github.com/google-gemini/gemini-cli", "https://geminicli.com/docs/"),
)

# This repo's runtime Agent Skills (junctioned into each CLI's config dir) →
# (folder name, one-line role). Rendered as GitHub deep-links.
_SKILL_RESOURCES: tuple[tuple[str, str], ...] = (
    ("agent-chat", "participation loop"),
    ("debate-mode", "argue well"),
    ("start-debate", "launch a debate"),
    ("publish-debate", "publish + cover"),
)


def _res_link(href: str, label: str, sub: str = "", *, external: bool = True, glyph: str = "↗") -> str:
    """One ``<li>`` link row in a Resources tile — matches the hand-written tiles."""
    attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
    sub_html = f' <span class="text-xs text-zinc-500 ml-1">{html.escape(sub)}</span>' if sub else ""
    return (
        f'<li><a href="{href}"{attrs} class="flex items-baseline justify-between gap-3 '
        'text-zinc-300 hover:text-zinc-100 transition group">'
        f'<span>{html.escape(label)}{sub_html}</span>'
        f'<span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">{glyph}</span></a></li>'
    )


def _res_cli_row(name: str, repo: str, docs: str) -> str:
    """CLI row carrying two links (repo + docs) on one line."""
    return (
        '<li class="flex items-baseline justify-between gap-3">'
        f'<span class="text-zinc-300">{html.escape(name)}</span>'
        '<span class="flex items-center gap-3 shrink-0 text-xs">'
        f'<a href="{repo}" target="_blank" rel="noopener noreferrer" '
        'class="text-zinc-400 hover:text-emerald-400 transition">repo&nbsp;↗</a>'
        f'<a href="{docs}" target="_blank" rel="noopener noreferrer" '
        'class="text-zinc-400 hover:text-emerald-400 transition">docs&nbsp;↗</a>'
        '</span></li>'
    )


def _res_tile(title: str, items: list[str]) -> str:
    """Wrap link rows in the standard Resources card."""
    return (
        '<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">'
        f'<h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 font-medium mb-4">{html.escape(title)}</h4>'
        f'<ul class="space-y-2.5 text-sm">{"".join(items)}</ul></div>'
    )


def _render_homepage_res_extra_tiles() -> str:
    """Tiles appended after the hand-written Resources cards: the supported CLIs
    (repo + docs each), MCP references, this repo's runtime skills, and where to
    grab persona files."""
    clis = _res_tile(
        "Supported CLIs",
        [_res_cli_row(name, repo, docs) for name, repo, docs in _CLI_RESOURCES],
    )
    mcp = _res_tile("MCP resources", [
        _res_link("https://modelcontextprotocol.io", "Model Context Protocol", "protocol home"),
        _res_link("https://modelcontextprotocol.io/specification", "Specification", "the wire format"),
        _res_link("https://github.com/modelcontextprotocol/python-sdk", "Python SDK", "FastMCP — this server"),
        _res_link("https://github.com/modelcontextprotocol/servers", "Example servers", "reference implementations"),
        _res_link(f"{_REPO}/blob/main/docs/CLI-MCP-Config/README.md", "Per-CLI MCP setup", "our config reference"),
    ])
    skills = _res_tile(
        "Agent Skills · this repo",
        [_res_link(f"{_REPO}/tree/main/skills", "skills/", "all four, runtime-loaded")]
        + [
            _res_link(f"{_REPO}/tree/main/skills/{name}", name, role)
            for name, role in _SKILL_RESOURCES
        ],
    )
    personas = _res_tile("Personas", [
        _res_link("/personas", "Browse the roster", "manage in this app", external=False, glyph="→"),
        _res_link(f"{_REPO}/tree/main/agents/Debate-Agents", "Persona seed cards", "agents/Debate-Agents"),
        _res_link(f"{_REPO}/blob/main/docs/App/personas.md", "Personas doc", "groups · cards · AI-Models"),
    ])
    return clis + mcp + skills + personas


def _render_homepage_res_groups() -> str:
    """Link tiles under the 'Resources' section.

    The first five are hand-written; the rest (supported CLIs, MCP, this repo's
    skills, persona files) come from ``_render_homepage_res_extra_tiles()``.

    (The former 'The CLIs' tile was removed once the Supported CLIs table —
    ``_render_homepage_clis_table()`` — became the canonical CLI list.)
    """
    return r"""<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 font-medium mb-4">This project</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>GitHub repository <span class="text-xs text-zinc-500 ml-1">michaelschecht/Agent-chat</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/README.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>README <span class="text-xs text-zinc-500 ml-1">overview &amp; quickstart</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Guides/start-new-chat.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Daily-driver flow <span class="text-xs text-zinc-500 ml-1">docs/Guides/start-new-chat.md</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/App/web-ui.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Web UI reference <span class="text-xs text-zinc-500 ml-1">docs/App/web-ui.md</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/Roadmap.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Roadmap <span class="text-xs text-zinc-500 ml-1">open + done</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/docs/CHANGELOG.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Changelog <span class="text-xs text-zinc-500 ml-1">reverse-chron log</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 font-medium mb-4">Prompt library</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Agents <span class="text-xs text-zinc-500 ml-1">personalities for the arena</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://prompts.mikesailab.com/" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>prompts.mikesailab.com <span class="text-xs text-zinc-500 ml-1">full library</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht/Agent-chat/blob/main/prompts/Kickoff/kickoff.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Canonical kickoff template <span class="text-xs text-zinc-500 ml-1">prompts/Kickoff/kickoff.md</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 font-medium mb-4">Sample debates</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="/conversations/14" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>How credible is Bob Lazar? <span class="text-xs text-zinc-500 ml-1">claude-code · gemini</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">→</span></a></li>
    <li><a href="/conversations/5" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>The Fermi paradox <span class="text-xs text-zinc-500 ml-1">debate</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">→</span></a></li>
    <li><a href="/conversations/6" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Simulation theory <span class="text-xs text-zinc-500 ml-1">debate</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">→</span></a></li>
    <li><a href="/conversations/10" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Brain ↔ CPU interface <span class="text-xs text-zinc-500 ml-1">debate</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">→</span></a></li>
    <li><a href="/conversations/3" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Future of tech jobs <span class="text-xs text-zinc-500 ml-1">claude-code · codex</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">→</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 font-medium mb-4">Stack &amp; protocols</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Model Context Protocol <span class="text-xs text-zinc-500 ml-1">modelcontextprotocol.io</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/modelcontextprotocol/python-sdk" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>MCP Python SDK <span class="text-xs text-zinc-500 ml-1">FastMCP</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://www.starlette.io/" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Starlette <span class="text-xs text-zinc-500 ml-1">web UI framework</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://www.sqlite.org/wal.html" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>SQLite WAL mode <span class="text-xs text-zinc-500 ml-1">multi-process bus</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://fly.io/" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Fly.io <span class="text-xs text-zinc-500 ml-1">where this is hosted</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/executablebooks/markdown-it-py" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>markdown-it-py <span class="text-xs text-zinc-500 ml-1">message rendering</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>

<div class="border border-zinc-800/60 hover:border-zinc-700 bg-zinc-900/40 rounded-md p-5 transition">
  <h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 font-medium mb-4">Author</h4>
  <ul class="space-y-2.5 text-sm">
    <li><a href="https://mikesailab.com" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>mikesailab.com <span class="text-xs text-zinc-500 ml-1">main site</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/michaelschecht" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>GitHub: @michaelschecht <span class="text-xs text-zinc-500 ml-1">other repos</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://prompts.mikesailab.com" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>prompts.mikesailab.com <span class="text-xs text-zinc-500 ml-1">prompt library</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
  </ul>
</div>""" + _render_homepage_res_extra_tiles()


# Supported-CLI matrix for the homepage. Each entry:
#   (display name, vendor, agent-id, repo/home URL, status label, is-active)
# Antigravity has no verified public source repo (closed product) → links to its
# official site. Keep this list in sync with orchestrator.preflight.SUPPORTED_CLIS.
_SUPPORTED_CLIS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    ("Claude Code", "Anthropic", "claude-code", "https://github.com/anthropics/claude-code", "Active", True),
    ("Codex CLI", "OpenAI", "codex", "https://github.com/openai/codex", "Active", True),
    ("Antigravity", "Google", "antigravity", "https://antigravity.google", "Active", True),
    ("Kimi CLI", "Moonshot AI", "kimi", "https://github.com/MoonshotAI/kimi-cli", "Active", True),
    ("OpenCode", "SST", "opencode", "https://github.com/sst/opencode", "Active", True),
    ("Gemini CLI", "Google", "gemini", "https://github.com/google-gemini/gemini-cli", "Deprecated · fallback", False),
)


def _render_homepage_clis_table() -> str:
    """Render the supported-CLI matrix — each name hyperlinks to its repo/home."""
    rows: list[str] = []
    for name, vendor, agent_id, url, status, active in _SUPPORTED_CLIS:
        name_cls = "text-zinc-100" if active else "text-zinc-400"
        status_cls = "text-emerald-400" if active else "text-zinc-500"
        rows.append(
            '<tr class="group">'
            '<td class="px-5 py-3.5 border-b border-zinc-800/40">'
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'class="inline-flex items-center gap-2 {name_cls} hover:text-emerald-400 transition font-medium">'
            f'{html.escape(name)} '
            '<span aria-hidden="true" class="text-zinc-600 group-hover:text-emerald-400 transition">↗</span></a></td>'
            f'<td class="px-5 py-3.5 border-b border-zinc-800/40 text-zinc-400">{html.escape(vendor)}</td>'
            f'<td class="px-5 py-3.5 border-b border-zinc-800/40"><code class="step-code-inline">{html.escape(agent_id)}</code></td>'
            f'<td class="px-5 py-3.5 border-b border-zinc-800/40 {status_cls}">{html.escape(status)}</td>'
            '</tr>'
        )
    head = (
        '<tr class="text-left text-[11px] uppercase tracking-[0.14em] text-zinc-500">'
        '<th class="font-medium px-5 py-3 border-b border-zinc-800/60">CLI</th>'
        '<th class="font-medium px-5 py-3 border-b border-zinc-800/60">Vendor</th>'
        '<th class="font-medium px-5 py-3 border-b border-zinc-800/60">agent-id</th>'
        '<th class="font-medium px-5 py-3 border-b border-zinc-800/60">Status</th>'
        '</tr>'
    )
    return (
        '<div class="mt-10 overflow-x-auto">'
        '<table class="w-full text-sm bg-zinc-900/40 border border-zinc-800/60 rounded-md '
        'border-separate border-spacing-0">'
        f'<thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'
    )

def _featured_teaser(text: str, maxlen: int = 104) -> str:
    """One-line description from a debate's opening message: strip Markdown
    punctuation, collapse whitespace, truncate on a word boundary."""
    t = re.sub(r"[*_`#>]+", "", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > maxlen:
        t = t[:maxlen].rsplit(" ", 1)[0].rstrip(" ,.;:—-") + "…"
    return t


def _render_homepage_featured(featured: list[dict[str, Any]]) -> str:
    """Featured-debates panel in the hero: up to four completed debates, each a
    link to its transcript with a one-line teaser and its debater cast. Empty
    state (fresh DB / no completed runs) points at the conversations list."""
    header = (
        '<div class="flex items-center justify-between gap-3 px-4 py-3 border-b border-zinc-800/60">'
        '<span class="text-[11px] uppercase tracking-[0.2em] text-zinc-400">Featured debates</span>'
        '<span class="flex items-center gap-4">'
        f'<a href="{THEATER_URL}" target="_blank" rel="noopener noreferrer" '
        'title="Watch published debates in the Debate Chat Theater" '
        'class="mono text-[11px] text-zinc-400 hover:text-zinc-100 transition">Watch in Theater ↗</a>'
        '<a href="/conversations" class="mono text-[11px] text-emerald-400 hover:text-emerald-300 transition">View all →</a>'
        "</span></div>"
    )
    if not featured:
        body = (
            '<div class="px-4 py-10 text-center text-sm text-zinc-500">'
            'No completed debates yet — '
            '<a href="/conversations" class="text-emerald-400 hover:text-emerald-300 transition">browse conversations</a>'
            ' once one wraps.</div>'
        )
        return (
            '<div class="border border-zinc-800/60 bg-zinc-900/40 rounded-xl overflow-hidden">'
            + header + body + "</div>"
        )
    rows: list[str] = []
    for c in featured:
        cid = c["id"]
        topic = html.escape(str(c.get("topic", "") or "(untitled)"))
        teaser = html.escape(_featured_teaser(c.get("teaser", "")))
        n = c.get("message_count", 0)
        casts = _conv_debater_casts(c)
        names = [nm for nm, _ in casts]
        avatars = "".join(
            '<span class="w-[18px] h-[18px] rounded-full overflow-hidden relative '
            'bg-emerald-500/15 text-emerald-400 mono text-[9px] flex items-center '
            'justify-center font-semibold ring-1 ring-[#060606]">'
            + (
                f'<img src="{html.escape(avatar_url(slug), quote=True)}" alt="" loading="lazy" '
                'class="absolute inset-0 w-full h-full object-cover" '
                "onerror=\"this.style.display='none'\">"
                if slug else ""
            )
            + f"{html.escape(_initials(name))}</span>"
            for name, slug in casts
        )
        if len(names) == 2:
            cast = (
                f'{html.escape(names[0])} <span class="text-zinc-600">vs</span> '
                f"{html.escape(names[1])}"
            )
        else:
            cast = ' <span class="text-zinc-600">·</span> '.join(
                html.escape(nm) for nm in names
            )
        rows.append(
            f'<a href="/conversations/{cid}" class="block group px-4 py-3.5 hover:bg-zinc-800/30 transition">'
            '<div class="flex items-start justify-between gap-3">'
            f'<h3 class="text-[15px] font-semibold text-zinc-100 group-hover:text-emerald-400 transition leading-snug">{topic}</h3>'
            f'<span class="mono text-[10px] text-zinc-600 shrink-0 mt-1">{n} msgs</span>'
            "</div>"
            f'<p class="mt-1 text-[12.5px] text-zinc-400 leading-snug">{teaser}</p>'
            '<div class="mt-2 flex items-center gap-2">'
            f'<span class="flex -space-x-1.5">{avatars}</span>'
            f'<span class="text-[11.5px] text-zinc-500">{cast}</span>'
            "</div></a>"
        )
    return (
        '<div class="border border-zinc-800/60 bg-zinc-900/40 rounded-xl overflow-hidden">'
        + header
        + '<div class="divide-y divide-zinc-800/60">'
        + "".join(rows)
        + "</div></div>"
    )


def _render_homepage_personas() -> str:
    """Persona roster preview for the homepage — a sample of cards plus a link
    to the full /personas console. Empty-state when the registry has no personas
    (e.g. a fresh local DB before the bundled roster is imported)."""
    try:
        all_personas = personas_registry.list_personas()
    except Exception:  # noqa: BLE001 — registry/DB issues degrade to empty-state
        all_personas = []
    total = len(all_personas)
    if total == 0:
        return (
            '<div class="mt-10 text-zinc-500 text-sm py-10 text-center border '
            'border-dashed border-zinc-800/60 rounded-md">'
            'No personas yet — add cards on the '
            '<a href="/personas" class="text-emerald-400 hover:text-emerald-300 transition">Personas</a>'
            ' page or import the bundled roster.</div>'
        )
    # Prefer the debater group for the preview; fall back to the whole roster.
    preview = personas_registry.list_personas(
        personas_registry.DEFAULT_DEBATER_GROUP
    ) or all_personas
    cards: list[str] = []
    for p in preview[:9]:
        words = p.name.split()
        initials = ("".join(w[0] for w in words[:2]) or p.name[:1]).upper()
        tags = "".join(
            '<span class="text-[10px] uppercase tracking-wide text-zinc-500 '
            f'border border-zinc-800 rounded px-1.5 py-0.5">{html.escape(t)}</span>'
            for t in p.tags[:3]
        )
        cards.append(
            '<div class="border border-zinc-800/60 bg-zinc-900/40 rounded-md p-5 '
            'hover:border-zinc-600 transition">'
            '<div class="flex items-center gap-3 mb-2">'
            '<span class="w-8 h-8 rounded-md overflow-hidden relative bg-emerald-500/15 '
            'text-emerald-400 flex items-center justify-center font-semibold text-xs shrink-0">'
            f'<img src="{html.escape(avatar_url(p.slug), quote=True)}" alt="" loading="lazy" '
            'class="absolute inset-0 w-full h-full object-cover" '
            "onerror=\"this.style.display='none'\">"
            f'{html.escape(initials)}</span>'
            '<h4 class="text-base font-semibold text-zinc-100 leading-tight">'
            f'{html.escape(p.name)}</h4></div>'
            '<p class="text-sm text-zinc-400 leading-relaxed line-clamp-2">'
            f'{html.escape(p.summary or "")}</p>'
            + (f'<div class="mt-3 flex flex-wrap gap-1.5">{tags}</div>' if tags else "")
            + "</div>"
        )
    grid = (
        '<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-10">'
        + "".join(cards)
        + "</div>"
    )
    cta = (
        '<div class="mt-8 text-right">'
        '<a href="/personas" class="text-sm text-emerald-400 hover:text-emerald-300 transition">'
        f'Explore all {total} personas &rarr;</a></div>'
    )
    return grid + cta


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
            parts = _conv_cast_label(c)
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

    active_color = "text-emerald-400" if active > 0 else "text-zinc-100"

    how_steps_html = _render_homepage_how_steps()
    res_groups_html = _render_homepage_res_groups()
    clis_table_html = _render_homepage_clis_table()
    personas_html = _render_homepage_personas()
    featured_html = _render_homepage_featured(list_featured_debates())

    # Info-icon note under the CTA. On the hosted mirror we can't spawn CLIs, so
    # say so plainly and send people to the repo; locally it's a light nudge.
    _info_icon = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'class="w-4 h-4 mt-0.5 shrink-0 text-zinc-600" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9"/><path d="M12 11.5v4.5" stroke-linecap="round"/>'
        '<circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none"/></svg>'
    )
    if _is_public_readonly():
        launch_note = (
            '<div class="mt-4 flex items-start gap-2.5 text-[13px] text-zinc-500 max-w-md">'
            + _info_icon
            + '<p>This hosted site is a <span class="text-zinc-300">read-only demo</span> for '
            "viewing debates — you can't launch one here. "
            '<a href="https://github.com/michaelschecht/Agent-chat" target="_blank" '
            'rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 '
            'underline-offset-2 hover:underline">Clone the repo &rarr;</a> to run your own locally.</p>'
            "</div>"
        )
    else:
        launch_note = (
            '<div class="mt-4 flex items-start gap-2.5 text-[13px] text-zinc-500 max-w-md">'
            + _info_icon
            + '<p>Local instance — '
            '<a href="/orchestrate" class="text-emerald-400 hover:text-emerald-300 transition">launch a debate &rarr;</a>'
            " and watch it live.</p></div>"
        )

    return _HOMEPAGE_TEMPLATE.format(
        HOME_CSS=HOME_CSS,
        fonts_head=FONTS_HEAD,
        topbar=_topbar(),
        # Resources is an in-page anchor, so it rides along only here.
        sidebar=_sidebar(active="home", extra_nav=_HOME_NAV),
        convs_total=f"{convs_total:,}",
        active=f"{active:,}",
        msgs=f"{msgs:,}",
        active_color=active_color,
        latest_html=latest_html,
        how_steps_html=how_steps_html,
        res_groups_html=res_groups_html,
        clis_table_html=clis_table_html,
        personas_html=personas_html,
        featured_html=featured_html,
        launch_note=launch_note,
        theater_url=THEATER_URL,
    )
