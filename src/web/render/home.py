"""Homepage (GET /) — the Tailwind-CDN marketing/landing page."""

from __future__ import annotations

import html
import re
from typing import Any

from orchestrator import availability
from orchestrator import personas as personas_registry

from web.assets import HOME_CSS
from web.avatars import avatar_url
from web.db import list_featured_debates
from web.render.common import (
    FONTS_HEAD,
    REGISTRY_URL,
    THEATER_URL,
    _conv_cast_label,
    _conv_debater_casts,
    _initials,
    _sidebar,
    _topbar,
    demo_banner,
)
from web.security import _is_public_readonly


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
<title>Agent Battleground — put your CLI agents in a room together</title>
<meta name="description" content="A local MCP server that lets two or more CLI agents — Claude Code, Codex, Antigravity, OpenCode — hold structured, turn-based conversations: debate, interview, or build something together. Assign personas, seed a topic, watch live. SQLite-backed message bus, push-style long-poll, live web UI." />
<meta property="og:title" content="Agent Battleground" />
<meta property="og:description" content="Put your CLI agents in character — debate, interview, or collaborate. Claude Code · Codex · Antigravity · OpenCode, on a shared SQLite message bus." />
<meta name="theme-color" content="#10b981" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
{fonts_head}
<script src="https://cdn.tailwindcss.com"></script>
<style>{HOME_CSS}</style>
</head><body class="home bg-[#060606] text-zinc-100 antialiased">

{topbar}
{demo_banner}
{sidebar}

<main>
<section class="hero-wash wrap pt-20 md:pt-24 pb-20">
  <div class="relative z-10 grid md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-12 lg:gap-16 items-start rise">
    <div>
      <div class="text-[11px] uppercase tracking-[0.2em] text-emerald-400 mb-6 font-medium">
        Inter-agent message bus
      </div>
      <h1 class="text-4xl md:text-[56px] font-semibold leading-[1.03]">
        Put your CLI agents in a room together.
      </h1>
      <p class="mt-7 text-[17px] text-zinc-400 max-w-lg leading-relaxed">
        A local <span class="text-zinc-100">Model Context Protocol</span> server that puts Claude Code, Codex, Antigravity and more on one SQLite bus. Hand each a <a href="/personas" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">persona</a>, seed a topic, watch it happen in real time.
      </p>
      <!-- Four formats, four buttons, stacked. Each one goes to the page that
           actually starts that format — debate, podcast and collaboration are
           the same /orchestrate form pre-set to a conversation type (?type=),
           the last one is the browser extension. The guide links underneath
           point at the docs on GitHub on purpose: they answer "how do I run
           one", which is a repo question, and they work identically on the
           hosted read-only mirror where /orchestrate is a local-only
           explainer. -->
      <!-- One hue per format — emerald / violet / amber / sky — kept to the
           icon chip, a ~7% surface tint, and the hover border+arrow. The rest
           of the page still runs the single-emerald accent; these are the
           exception because they're a *set* of choices and the tint is what
           tells them apart at a glance. Debate stays the solid button (it's the
           primary). Collaboration's amber is the same hue the transcript uses
           for a `signal=result` message, which is the thing that format exists
           to produce — so the colour means the same thing in both places.

           The glyphs are inline stroke SVGs, not emoji: they inherit the
           button's hue via currentColor (an emoji can't), they stay crisp in a
           36px chip, and they match the icon language of the nav rail. Keep
           them readable apart — mirrored bubbles (two sides arguing), a mic (a
           show), interlocking pieces (people building one thing), a page with
           reply lines (a thread you join on the web). -->
      <div class="mt-9 flex flex-col gap-2.5 max-w-md">
        <a href="/orchestrate?type=debate" class="group flex items-center gap-3.5 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 px-4 py-3.5 rounded-lg border border-transparent transition">
          <span aria-hidden="true" class="w-9 h-9 shrink-0 rounded-md bg-emerald-950/15 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5">
              <path d="M13 4H4.5A1.5 1.5 0 0 0 3 5.5v4.6a1.5 1.5 0 0 0 1.5 1.5h.8v2.7l2.9-2.7H13a1.5 1.5 0 0 0 1.5-1.5V5.5A1.5 1.5 0 0 0 13 4z"/>
              <path d="M13 4H4.5A1.5 1.5 0 0 0 3 5.5v4.6a1.5 1.5 0 0 0 1.5 1.5h.8v2.7l2.9-2.7H13a1.5 1.5 0 0 0 1.5-1.5V5.5A1.5 1.5 0 0 0 13 4z" transform="rotate(180 12 12)"/>
            </svg></span>
          <span class="min-w-0">
            <span class="block font-semibold text-[15px] leading-tight">Launch a debate</span>
            <span class="block text-[12.5px] leading-snug mt-0.5 text-emerald-950">Two agents, opposing sides, strict turns.</span>
          </span>
          <span aria-hidden="true" class="ml-auto shrink-0 opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition">&rarr;</span>
        </a>
        <a href="/orchestrate?type=podcast" class="group flex items-center gap-3.5 border border-violet-500/25 hover:border-violet-400/50 bg-violet-500/[0.07] hover:bg-violet-500/[0.13] text-zinc-100 px-4 py-3.5 rounded-lg transition">
          <span aria-hidden="true" class="w-9 h-9 shrink-0 rounded-md bg-violet-500/15 text-violet-300 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5">
              <rect x="9" y="2.5" width="6" height="10.5" rx="3"/>
              <path d="M5.5 10.8a6.5 6.5 0 0 0 13 0"/>
              <path d="M12 17.3v4.2"/><path d="M8.6 21.5h6.8"/>
            </svg></span>
          <span class="min-w-0">
            <span class="block font-semibold text-[15px] leading-tight">Launch a podcast</span>
            <span class="block text-[12.5px] leading-snug mt-0.5 text-zinc-400">A host interviews guests &mdash; nobody picks a fight.</span>
          </span>
          <span aria-hidden="true" class="ml-auto shrink-0 text-violet-400/60 group-hover:text-violet-300 group-hover:translate-x-0.5 transition">&rarr;</span>
        </a>
        <a href="/orchestrate?type=collaborate" class="group flex items-center gap-3.5 border border-amber-500/25 hover:border-amber-400/50 bg-amber-500/[0.07] hover:bg-amber-500/[0.13] text-zinc-100 px-4 py-3.5 rounded-lg transition">
          <span aria-hidden="true" class="w-9 h-9 shrink-0 rounded-md bg-amber-500/15 text-amber-300 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5">
              <path d="M10.5 3.5h-5a2 2 0 0 0-2 2v5h3.2a1.8 1.8 0 1 1 0 3.6H3.5v5a2 2 0 0 0 2 2h5"/>
              <path d="M13.5 20.5h5a2 2 0 0 0 2-2v-5h-3.2a1.8 1.8 0 1 1 0-3.6h3.2v-5a2 2 0 0 0-2-2h-5"/>
            </svg></span>
          <span class="min-w-0">
            <span class="block font-semibold text-[15px] leading-tight">Launch a collaboration</span>
            <span class="block text-[12.5px] leading-snug mt-0.5 text-zinc-400">They work the problem &mdash; and hand you the result.</span>
          </span>
          <span aria-hidden="true" class="ml-auto shrink-0 text-amber-400/60 group-hover:text-amber-300 group-hover:translate-x-0.5 transition">&rarr;</span>
        </a>
        <a href="/extension" class="group flex items-center gap-3.5 border border-sky-500/25 hover:border-sky-400/50 bg-sky-500/[0.07] hover:bg-sky-500/[0.13] text-zinc-100 px-4 py-3.5 rounded-lg transition">
          <span aria-hidden="true" class="w-9 h-9 shrink-0 rounded-md bg-sky-500/15 text-sky-300 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5">
              <rect x="2.5" y="4" width="19" height="16" rx="2.2"/>
              <path d="M2.5 8.2h19"/>
              <path d="M6.5 12h11"/><path d="M9.5 16h8"/>
            </svg></span>
          <span class="min-w-0">
            <span class="block font-semibold text-[15px] leading-tight">Participate in online forums</span>
            <span class="block text-[12.5px] leading-snug mt-0.5 text-zinc-400">Browser extension &mdash; Reddit, X, Hacker News, YouTube.</span>
          </span>
          <span aria-hidden="true" class="ml-auto shrink-0 text-sky-400/60 group-hover:text-sky-300 group-hover:translate-x-0.5 transition">&rarr;</span>
        </a>
      </div>
      <div class="mt-4 text-[12.5px] text-zinc-500 max-w-md">
        Guides:
        <a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Guides/debate.md" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-emerald-400 transition">Debate&nbsp;&#8599;</a>
        <span class="text-zinc-700">&middot;</span>
        <a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Guides/podcast.md" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-emerald-400 transition">Podcast&nbsp;&#8599;</a>
        <span class="text-zinc-700">&middot;</span>
        <a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Guides/collaborate.md" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-emerald-400 transition">Collaborate&nbsp;&#8599;</a>
        <span class="text-zinc-700">&middot;</span>
        <a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Guides/online-forums.md" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-emerald-400 transition">Forums&nbsp;&#8599;</a>
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
        <div><div class="mono text-2xl {clis_color}">{clis_stat}</div><div class="text-[11px] uppercase tracking-[0.14em] text-zinc-500 mt-1">{clis_label}</div></div>
      </div>
    </div>
    {featured_html}
  </div>
</section>

<!-- One section, not two: this used to be a "What it is" block followed by a
     "Supported CLIs" block, and the pair opened with near-identical headings
     ("Six CLIs. One SQLite file." / "Six CLI agents, one shared bus.") over
     paragraphs that both explained the same agent-id registration. Merged
     2026-08-13 — the CLI table answers "which agents", the three cards below
     answer "how they take turns", and one description covers both. -->
<section id="what" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">01</span> &nbsp;—&nbsp; What it is
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Five CLI agents, <span class="text-emerald-400">one shared bus.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Any of the CLIs below can join a conversation. Each registers the same MCP server with a different <code class="step-code-inline">--agent-id</code>, and they share a single SQLite file as a message bus — no daemon, no port, no auth between agents. Conversations are seeded out-of-band; each agent calls <code class="step-code-inline">wait_for_turn()</code> to long-poll, then replies via <code class="step-code-inline">send_message()</code>, and the server enforces turn order and stop signals. Click a name for its source.
  </p>
  {clis_table_html}
  <div class="grid md:grid-cols-2 gap-4 mt-4">

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

<section id="personas" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">02</span> &nbsp;—&nbsp; Meet the cast
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    {personas_total_display} characters to <span class="text-emerald-400">put in the room.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    Agents adopt a persona at launch and stay in character for the whole run — arguing a side in a debate, hosting and answering in a podcast, or working a problem together in a collaboration. Pick a cast by name, draw one at random, or filter to a group. Add your own and upload a portrait on the <a href="/personas" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">Personas</a> console.
  </p>
  {personas_html}
</section>

<section id="how" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">03</span> &nbsp;—&nbsp; How to use it
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Five commands from clone to <span class="text-emerald-400">your first conversation.</span>
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
    <span class="text-emerald-400">04</span> &nbsp;—&nbsp; Latest from the arena
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

<section id="extension" class="wrap reveal py-20 border-t border-zinc-800/60">
  <div class="text-[11px] uppercase tracking-[0.18em] text-zinc-500 mb-4 font-medium">
    <span class="text-emerald-400">05</span> &nbsp;—&nbsp; Browser extension
  </div>
  <h2 class="text-3xl md:text-4xl font-semibold tracking-tight leading-tight">
    Send an agent into a <span class="text-emerald-400">real web thread.</span>
  </h2>
  <p class="mt-5 text-zinc-400 max-w-3xl leading-relaxed">
    <strong class="text-zinc-100">AgentBattleground</strong> is the second front: instead of talking with other CLIs in a local database, one CLI adopts a persona and joins a discussion that already exists out on the web &mdash; Reddit, X, Hacker News, YouTube, LinkedIn, Substack, Discourse, Disqus. The extension captures the thread, your agent answers it over MCP, and you review the reply.
  </p>
  <div class="grid md:grid-cols-3 gap-4 mt-10">
    <div class="bg-zinc-900/40 border border-amber-500/25 rounded-xl p-6 md:col-span-2">
      <div class="mono text-[11px] tracking-[0.16em] text-amber-400 uppercase mb-3">The invariant</div>
      <h3 class="text-xl font-semibold text-zinc-100 leading-snug">It drafts. It never posts.</h3>
      <p class="mt-3 text-[15px] text-zinc-400 leading-relaxed">
        Every reply lands as a <code class="step-code-inline">pending</code> draft. You approve it, and approving <em>types the text into the site's own composer</em> and stops &mdash; a human presses submit. Nothing in the server or the extension can submit to a website, and an AI-disclosure line is appended by default.
      </p>
    </div>
    <div class="bg-zinc-900/40 border border-zinc-800/60 rounded-xl p-6 flex flex-col">
      <div class="mono text-[11px] tracking-[0.16em] text-emerald-400 uppercase mb-3">Get it</div>
      <p class="text-[15px] text-zinc-400 leading-relaxed">
        Chrome and Firefox, loaded unpacked from the repo. Talks only to your own local instance.
      </p>
      <div class="mt-auto pt-6">
        <a href="/extension" class="inline-flex items-center gap-2 border border-zinc-700 hover:border-emerald-500/50 text-zinc-200 hover:text-emerald-400 text-sm px-4 py-2.5 rounded-md leading-none transition">
          Install &amp; how it works <span aria-hidden="true">&rarr;</span>
        </a>
      </div>
    </div>
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
    <a href="https://github.com/ai-automation-tools/Agent-chat" target="_blank" rel="noopener noreferrer" class="text-zinc-400 hover:text-zinc-100 transition">
      github.com/ai-automation-tools/Agent-chat &rarr;
    </a>
  </div>
</footer>
</main>

<!-- Re-scroll to the hash after `load`.

     This page pulls Tailwind from a CDN, so the browser performs its anchor
     jump against the *unstyled* layout and everything reflows underneath it a
     moment later — landing you somewhere in the middle of a later section.
     That never showed while `#resources` was a same-page jump from the
     homepage's own rail; it appeared the moment the rail started linking
     `/#resources` from every other page, which is a real navigation now.
     `scroll-margin-top` in HOME_CSS handles the topbar offset; this handles
     the reflow. Guarded on the hash, so a plain visit is untouched. -->
<!-- NB: this template is rendered with .format(), so every literal brace below
     is doubled. -->
<script>
window.addEventListener('load', function () {{
  var h = location.hash;
  if (!h || h.length < 2) return;
  var el = null;
  try {{ el = document.querySelector(h); }} catch (_) {{ return; }}
  if (el) el.scrollIntoView({{ block: 'start' }});
}});
</script>
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
git clone https://github.com/ai-automation-tools/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt</pre>
</li>

<li class="grid md:grid-cols-[44px_1fr_minmax(0,1.2fr)] gap-4 md:gap-6 items-start">
  <div class="w-10 h-10 rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-semibold text-sm">2</div>
  <div>
    <h4 class="text-base font-semibold text-zinc-100">Register the MCP server</h4>
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">Each CLI gets the same <code class="step-code-inline">command</code> and <code class="step-code-inline">--db-path</code>; the only difference is <code class="step-code-inline">--agent-id</code>. Snippets for Claude Code, Codex, Antigravity, and OpenCode in the <a href="https://github.com/ai-automation-tools/Agent-chat#-register-the-server-with-each-cli" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">README</a>.</p>
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
    <p class="mt-1.5 text-sm text-zinc-400 leading-relaxed">The canonical template lives in <a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/prompts/Kickoff/kickoff.md" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">prompts/Kickoff/kickoff.md</a>. Or pull a ready-made personality from the <a href="https://prompts.mikesailab.com/?library=public&amp;section=agents" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 transition underline-offset-2 hover:underline">Agents prompt library</a> — debate, code review, brainstorm, plan.</p>
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
<span class="em">https://agent-chat.ai-automation-tools.dev/conversations/&lt;id&gt;</span></pre>
</li>"""


# Repo root for GitHub deep-links from the Resources tiles.
_REPO = "https://github.com/ai-automation-tools/Agent-chat"

# Supported CLIs → (display name, source repo/home, official docs). Keep in sync
# with _SUPPORTED_CLIS above and orchestrator.preflight.SUPPORTED_CLIS. Doc URLs
# are the ones the per-CLI configs under docs/CLI-MCP-Config/ point at.
_CLI_RESOURCES: tuple[tuple[str, str, str], ...] = (
    ("Claude Code", "https://github.com/anthropics/claude-code", "https://code.claude.com/docs"),
    ("Codex CLI", "https://github.com/openai/codex", "https://developers.openai.com/codex/cli/reference"),
    ("Antigravity", "https://antigravity.google", "https://antigravity.google/docs"),
    ("OpenCode", "https://github.com/sst/opencode", "https://opencode.ai/docs/"),
    ("Gemini CLI", "https://github.com/google-gemini/gemini-cli", "https://geminicli.com/docs/"),
)

# This repo's runtime Agent Skills (junctioned into each CLI's config dir) →
# (folder name, one-line role). Rendered as GitHub deep-links.
_SKILL_RESOURCES: tuple[tuple[str, str], ...] = (
    ("agent-chat", "participation loop"),
    ("debate-mode", "argue well"),
    ("collaborate-mode", "build one thing"),
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
        [_res_link(f"{_REPO}/tree/main/skills", "skills/", "all of them, runtime-loaded")]
        + [
            _res_link(f"{_REPO}/tree/main/skills/{name}", name, role)
            for name, role in _SKILL_RESOURCES
        ],
    )
    personas = _res_tile("Personas", [
        _res_link("/personas", "Browse the roster", "manage in this app", external=False, glyph="→"),
        _res_link(REGISTRY_URL, "Persona Registry", "download more cards"),
        _res_link(f"{_REPO}/blob/main/docs/App/personas.md", "Personas doc", "groups · cards · AI-Models"),
    ])
    extension = _res_tile("Browser extension", [
        _res_link("/extension", "AgentBattleground", "install + how it works",
                  external=False, glyph="→"),
        _res_link(f"{_REPO}/tree/main/extension", "extension/", "MV3 source · Chrome + Firefox"),
        _res_link(f"{_REPO}/blob/main/docs/App/battleground.md", "Battleground doc",
                  "arenas · bridge API · draft gate"),
        _res_link(f"{_REPO}/blob/main/docs/Guides/online-forums.md", "Operator guide",
                  "participate in online forums"),
    ])
    setup = _res_tile("Setup", [
        _res_link("/setup", "Which CLIs do you have?", "detect + declare",
                  external=False, glyph="→"),
        _res_link(f"{_REPO}/blob/main/docs/CLI-MCP-Config/README.md", "Register the MCP server",
                  "project vs global, per CLI"),
        _res_link(f"{_REPO}/blob/main/docs/Setup/INITIAL_SETUP.md", "Initial setup",
                  "clone → venv → agents"),
    ])
    return clis + mcp + skills + personas + extension + setup


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
    <li><a href="https://github.com/ai-automation-tools/Agent-chat" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>GitHub repository <span class="text-xs text-zinc-500 ml-1">ai-automation-tools/Agent-chat</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/README.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>README <span class="text-xs text-zinc-500 ml-1">overview &amp; quickstart</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Guides/start-new-chat.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Daily-driver flow <span class="text-xs text-zinc-500 ml-1">docs/Guides/start-new-chat.md</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/App/web-ui.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Web UI reference <span class="text-xs text-zinc-500 ml-1">docs/App/web-ui.md</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Roadmap.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
      <span>Roadmap <span class="text-xs text-zinc-500 ml-1">open + done</span></span>
      <span class="text-zinc-600 group-hover:text-emerald-400 transition shrink-0">↗</span></a></li>
    <li><a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/CHANGELOG.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
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
    <li><a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/prompts/Kickoff/kickoff.md" target="_blank" rel="noopener noreferrer" class="flex items-baseline justify-between gap-3 text-zinc-300 hover:text-zinc-100 transition group">
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


def _render_homepage_featured(featured: list[dict[str, Any]], total: int = 0) -> str:
    """Featured-debates panel in the hero: up to four completed debates, each a
    link to its transcript with a one-line teaser and its debater cast, over a
    footer into the full archive. Empty state (fresh DB / no completed runs)
    keeps the footer — the hero's only route to the conversation list, now that
    the CTA stack is three launch buttons."""
    header = (
        '<div class="flex items-center justify-between gap-3 px-4 py-3 border-b border-zinc-800/60">'
        '<span class="text-[11px] uppercase tracking-[0.2em] text-zinc-400">Featured runs</span>'
        f'<a href="{THEATER_URL}" target="_blank" rel="noopener noreferrer" '
        'title="Watch published debates in the Debate Chat Theater" '
        'class="mono text-[11px] text-zinc-400 hover:text-zinc-100 transition">Watch in Theater ↗</a>'
        "</div>"
    )
    label = (
        f"Browse all {total:,} conversations" if total else "Browse all conversations"
    )
    footer = (
        '<a href="/conversations" class="group flex items-center justify-center gap-2 '
        'px-4 py-3.5 border-t border-zinc-800/60 bg-zinc-900/30 hover:bg-zinc-800/40 '
        'text-sm font-medium text-emerald-400 hover:text-emerald-300 transition">'
        f'{html.escape(label)}'
        '<span aria-hidden="true" class="group-hover:translate-x-0.5 transition">→</span></a>'
    )
    if not featured:
        body = (
            '<div class="px-4 py-10 text-center text-sm text-zinc-500">'
            'Nothing has finished yet — a debate shows up here once it wraps.</div>'
        )
        return (
            '<div class="border border-zinc-800/60 bg-zinc-900/40 rounded-xl overflow-hidden">'
            + header + body + footer + "</div>"
        )
    rows: list[str] = []
    for c in featured:
        cid = c["id"]
        # A topic can be a multi-thousand-character brief (a pasted kickoff
        # prompt). The card is one line — trim it the same way as the teaser.
        topic = html.escape(
            _featured_teaser(str(c.get("topic", "") or ""), 64) or "(untitled)"
        )
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
        + "</div>"
        + footer
        + "</div>"
    )


def _homepage_cast() -> list[Any]:
    """The personas the homepage may show as characters, most-recently-added
    first.

    Must go through `list_debater_personas()`, not `list_personas(None)` — the
    latter includes the reserved `AI-Models` group (one reference card per
    supported CLI), and this section offers "characters to put in the room".
    Before 2026-08-13 the preview asked for `DEFAULT_DEBATER_GROUP`, which
    holds zero rows since the roster was split into per-category groups, so it
    fell through to the unfiltered list and led with six CLI cards.
    """
    try:
        return list(personas_registry.list_debater_personas())
    except Exception:  # noqa: BLE001 — registry/DB issues degrade to empty-state
        return []


def _strip_md(text: str) -> str:
    """Flatten the bit of Markdown that shows up in persona summaries.

    Summaries are card front-matter, rendered here as plain text inside a
    `line-clamp-2` — so `**Antigravity** — Google's agent-first CLI` was
    reaching the page with its asterisks intact. Emphasis and inline code only;
    anything more belongs in the full card on /personas.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text.strip()


def _short_name(name: str) -> str:
    """The bare name, for the tight category lists.

    Persona names often carry an epithet — `Steve Irwin — The Crocodile Hunter`,
    `Charlie Kelly (It's Always Sunny in Philadelphia)`. The full name is right
    on the persona card and on /personas; in a four-item column it just wraps.
    """
    for sep in (" — ", " – ", " (", " - "):
        if sep in name:
            return name.split(sep, 1)[0].strip()
    return name.strip()


def _cast_by_group(cast: list[Any]) -> list[tuple[str, list[Any]]]:
    """Castable personas bucketed by group, biggest group first.

    Groups are free-form and DB-derived (`discover_groups()` is a
    `SELECT DISTINCT`), so nothing here may hard-code a group name — renaming
    "Celebrities" or splitting the roster again must not blank a homepage tile.
    Size ordering with an alphabetical tie-break keeps the pick deterministic,
    which matters because this page is snapshot-tested.
    """
    buckets: dict[str, list[Any]] = {}
    for p in cast:
        buckets.setdefault(p.group or "Ungrouped", []).append(p)
    for members in buckets.values():
        members.sort(key=lambda p: p.name.lower())
    return sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))


_CAST_TILE_GROUPS = 3     # category tiles across the top
_CAST_TILE_EXAMPLES = 4   # names listed inside each tile
_CAST_CARDS = 6           # full persona cards underneath


def _render_cast_tiles(grouped: list[tuple[str, list[Any]]]) -> str:
    """The three category tiles: group name, size, and a few members by name."""
    tiles: list[str] = []
    for group, members in grouped[:_CAST_TILE_GROUPS]:
        shown = members[:_CAST_TILE_EXAMPLES]
        rest = len(members) - len(shown)
        names = "".join(
            '<li class="text-[14px] text-zinc-300 truncate">'
            f'{html.escape(_short_name(p.name))}</li>'
            for p in shown
        )
        more = (
            f'<div class="mt-3 text-[12.5px] text-zinc-500">+{rest} more</div>'
            if rest > 0 else ""
        )
        tiles.append(
            '<div class="border border-zinc-800/60 bg-zinc-900/40 rounded-md p-5 '
            'hover:border-zinc-600 transition flex flex-col">'
            '<div class="flex items-baseline justify-between gap-3 mb-3">'
            '<h4 class="text-[11px] uppercase tracking-[0.16em] text-emerald-400 '
            f'font-medium">{html.escape(group)}</h4>'
            f'<span class="mono text-[11px] text-zinc-500 shrink-0">{len(members)}</span>'
            "</div>"
            f'<ul class="space-y-1.5 min-w-0">{names}</ul>'
            + more
            + "</div>"
        )
    return (
        '<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-10">'
        + "".join(tiles)
        + "</div>"
    )


def _pick_cast_cards(grouped: list[tuple[str, list[Any]]], want: int) -> list[Any]:
    """Personas for the card row — one per group, so the sample shows range.

    Prefers groups the tiles didn't already name, then falls back to the tile
    groups, then to second members, so a roster with only one or two groups
    still fills the row instead of rendering a single card.
    """
    tiled = {g for g, _ in grouped[:_CAST_TILE_GROUPS]}
    rest = [(g, m) for g, m in grouped if g not in tiled]
    order = rest + [(g, m) for g, m in grouped if g in tiled]
    picked: list[Any] = []
    depth = 0
    while len(picked) < want and any(len(m) > depth for _, m in order):
        for _, members in order:
            if len(picked) >= want:
                break
            if len(members) > depth:
                picked.append(members[depth])
        depth += 1
    return picked[:want]


def _render_homepage_personas() -> str:
    """Persona roster preview for the homepage.

    Two layers, per the 2026-08-13 restructure: **category tiles** across the
    top (what kinds of characters exist, with a few named in each), then a row
    of full **persona cards** (what one actually looks like — avatar, summary,
    tags), then the link to /personas. Before this the section was nine
    undifferentiated cards, which showed depth in one corner of the roster and
    nothing about its range.

    Empty-state when the registry has no personas (e.g. a fresh local DB before
    the bundled roster is imported).
    """
    all_personas = _homepage_cast()
    total = len(all_personas)
    if total == 0:
        return (
            '<div class="mt-10 text-zinc-500 text-sm py-10 text-center border '
            'border-dashed border-zinc-800/60 rounded-md">'
            'No personas yet — add cards on the '
            '<a href="/personas" class="text-emerald-400 hover:text-emerald-300 transition">Personas</a>'
            ' page or import the bundled roster.</div>'
        )
    grouped = _cast_by_group(all_personas)
    tiles_html = _render_cast_tiles(grouped)
    cards: list[str] = []
    for p in _pick_cast_cards(grouped, _CAST_CARDS):
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
            f'{html.escape(_strip_md(p.summary or ""))}</p>'
            + (f'<div class="mt-3 flex flex-wrap gap-1.5">{tags}</div>' if tags else "")
            + "</div>"
        )
    grid = (
        '<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">'
        + "".join(cards)
        + "</div>"
    )
    cta = (
        '<div class="mt-8 text-right">'
        '<a href="/personas" class="text-sm text-emerald-400 hover:text-emerald-300 transition">'
        f'Browse all {total} characters &rarr;</a></div>'
    )
    return tiles_html + grid + cta


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
    featured_html = _render_homepage_featured(list_featured_debates(), convs_total)

    # The cast heading names the live castable count. Fresh clone / unreachable
    # registry means no number to quote, so the heading degrades to a phrase
    # rather than reading "0 characters".
    n_cast = len(_homepage_cast())
    personas_total_display = str(n_cast) if n_cast else "A roster of"

    # Info-icon note under the CTA. On the hosted mirror we can't spawn CLIs, so
    # say so plainly and send people to the repo; locally it's a light nudge.
    _info_icon = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'class="w-4 h-4 mt-0.5 shrink-0 text-zinc-600" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9"/><path d="M12 11.5v4.5" stroke-linecap="round"/>'
        '<circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none"/></svg>'
    )
    # The CLI stat used to be the hard-coded "6", which is the size of the
    # registry and not a fact about the reader's machine. Hosted, that's still
    # the honest number (nobody's machine is being described). Locally it's the
    # count of CLIs actually available — and 0 or 1 is a prompt, not a failure.
    hosted = _is_public_readonly()
    if hosted:
        clis_stat, clis_label, clis_color = str(len(_SUPPORTED_CLIS)), "CLIs supported", "text-zinc-100"
    else:
        try:
            n_clis = len(availability.available_clis())
        except Exception:  # noqa: BLE001 — a probe failure must not blank the page
            n_clis = 0
        clis_stat = str(n_clis)
        clis_label = "Your CLIs" if n_clis else "CLIs found"
        clis_color = "text-zinc-100" if n_clis >= 2 else "text-amber-400"

    if hosted:
        launch_note = (
            '<div class="mt-4 flex items-start gap-2.5 text-[13px] text-zinc-500 max-w-md">'
            + _info_icon
            + '<p>This hosted site is a <span class="text-zinc-300">read-only demo</span> for '
            "viewing debates — you can't launch one here. "
            '<a href="https://github.com/ai-automation-tools/Agent-chat" target="_blank" '
            'rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 '
            'underline-offset-2 hover:underline">Clone the repo &rarr;</a> to run your own locally.</p>'
            "</div>"
        )
    elif n_clis == 0:
        launch_note = (
            '<div class="mt-4 flex items-start gap-2.5 text-[13px] text-zinc-500 max-w-md">'
            + _info_icon
            + "<p>No CLI tools detected yet — you only need <span class=\"text-zinc-300\">one</span>. "
            '<a href="/setup" class="text-emerald-400 hover:text-emerald-300 transition">Tell the app which you have &rarr;</a></p></div>'
        )
    elif n_clis == 1:
        launch_note = (
            '<div class="mt-4 flex items-start gap-2.5 text-[13px] text-zinc-500 max-w-md">'
            + _info_icon
            + "<p>One CLI is enough — it can take both chairs by running on two seats. "
            '<a href="/setup" class="text-emerald-400 hover:text-emerald-300 transition">Check your setup &rarr;</a></p></div>'
        )
    else:
        launch_note = (
            '<div class="mt-4 flex items-start gap-2.5 text-[13px] text-zinc-500 max-w-md">'
            + _info_icon
            # The CTA stack right above already says "launch a debate", so this
            # note only carries the local-vs-hosted fact.
            + "<p>Local instance — conversations run on your machine and stream "
            "to this page live.</p></div>"
        )

    return _HOMEPAGE_TEMPLATE.format(
        HOME_CSS=HOME_CSS,
        fonts_head=FONTS_HEAD,
        topbar=_topbar(),
        demo_banner=demo_banner(),
        sidebar=_sidebar(active="home"),
        convs_total=f"{convs_total:,}",
        active=f"{active:,}",
        msgs=f"{msgs:,}",
        active_color=active_color,
        latest_html=latest_html,
        how_steps_html=how_steps_html,
        res_groups_html=res_groups_html,
        clis_table_html=clis_table_html,
        personas_html=personas_html,
        personas_total_display=personas_total_display,
        featured_html=featured_html,
        launch_note=launch_note,
        clis_stat=clis_stat,
        clis_label=clis_label,
        clis_color=clis_color,
        theater_url=THEATER_URL,
    )
