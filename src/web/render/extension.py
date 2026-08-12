"""The /extension page — what AgentBattleground is and how to install it.

An explainer, not a control surface, so it renders on the hosted mirror too;
the only local-only piece is the bridge-health block, which asks *this* server
whether the extension would be able to reach it.

The arena **console** — list arenas, review drafts away from the page — is a
different, still-unbuilt page (`/battleground`, tracked on the Roadmap). This
one exists because the extension was invisible to anyone not already reading
the repo.
"""

from __future__ import annotations

import html

from web.api.battleground import KNOWN_SITES
from web.assets import EXTENSION_CSS, ORCHESTRATE_CSS
from web.render.common import _layout
from web.security import _is_public_readonly

_REPO = "https://github.com/michaelschecht/Agent-chat"

# Adapter id → what the operator calls that site. `generic` is the fallback
# adapter, not a site, so it's shown apart from the list.
_SITE_LABELS = {
    "reddit": "Reddit",
    "x": "X / Twitter",
    "hackernews": "Hacker News",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
    "substack": "Substack",
    "discourse": "Discourse forums",
    "disqus": "Disqus threads",
}


def _sites_html() -> str:
    chips = [
        f'<span class="xt-site">{html.escape(_SITE_LABELS[s])}</span>'
        for s in KNOWN_SITES
        if s in _SITE_LABELS
    ]
    return "".join(chips)


def _bridge_html() -> str:
    """Can the extension reach this server? Only a meaningful question locally.

    Rendered as an unknown state and resolved client-side against
    ``/api/battleground/healthz`` — the same endpoint the extension's own
    Settings panel probes, so what the operator reads here is exactly what the
    extension will find.
    """
    if _is_public_readonly():
        return (
            '<div class="xt-bridge">'
            '<span class="xt-dot" aria-hidden="true"></span>'
            "<span>The extension talks to a <strong>local</strong> instance "
            "(<code>http://127.0.0.1:8765</code>), never to this hosted mirror &mdash; "
            "captured page content stays on your machine and is deliberately excluded "
            "from the sync that fills this site.</span>"
            "</div>"
        )
    return (
        '<div class="xt-bridge" id="xt-bridge">'
        '<span class="xt-dot" aria-hidden="true"></span>'
        '<span id="xt-bridge-txt">Checking whether the extension bridge on this '
        "instance is reachable&hellip;</span>"
        "</div>"
        "<script>"
        "(function(){"
        "var box=document.getElementById('xt-bridge');"
        "var txt=document.getElementById('xt-bridge-txt');"
        "fetch('/api/battleground/healthz').then(function(r){return r.json();}).then(function(d){"
        "if(d && d.ok){box.className='xt-bridge up';"
        "txt.innerHTML='Bridge is up on this instance. The extension can create arenas here'"
        "+(d.token_required?', and a bridge token is required \\u2014 paste the same value into the panel\\u2019s Settings.':'; no bridge token is set, so any extension on this machine may use it.');"
        "}else{box.className='xt-bridge down';"
        "txt.textContent='Bridge is not answering: '+((d&&d.error)||'unknown error')"
        "+'. The extension will not be able to open an arena until this server can read its database.';}"
        "}).catch(function(e){box.className='xt-bridge down';"
        "txt.textContent='Bridge check failed: '+e;});"
        "})();"
        "</script>"
    )


def _render_extension_page() -> str:
    bridge = _bridge_html()
    sites = _sites_html()

    body = f"""
<div class="orch-shell xt-shell">
  <header class="orch-head">
    <h2>AgentBattleground &mdash; the browser extension</h2>
    <p>A second front for the same MCP server. Instead of two CLIs arguing inside a local
       SQLite file, <strong>one CLI adopts a persona and argues in a debate that already
       exists on the web</strong>. The extension captures a comment thread, your agent
       reads it and writes a reply, and you decide what happens to that reply.</p>
  </header>

  <div class="xt-invariant">
    <h3>It drafts. It never posts.</h3>
    <p>Every reply an agent produces is stored as a <code>pending</code> draft. Approving
       one <em>types the text into the site&rsquo;s own composer</em> and stops there
       &mdash; a human presses submit. Nothing in this server or in the extension can
       submit to a website, open a composer on its own, or click a site&rsquo;s post
       button.</p>
    <p>That line is what separates this from astroturfing, so it is structural rather
       than a setting: an AI-disclosure line is appended on insert (on by default), and
       the house rules shipped with every arena say plainly that a persona is a
       <em>voice</em>, never a claimed identity. The agent does not pretend to be a
       person.</p>
  </div>

  <div class="xt-sec">
    <h3>How a round goes</h3>
    <ol class="xt-steps">
      <li><div><h4>Capture the thread</h4><p>Open the side panel on a comment page and
        capture. Site access is requested <strong>per domain, at that moment</strong>
        &mdash; the extension ships with no standing permissions and injects nothing
        until you click. A preview shows exactly what the agent will be handed.</p></div></li>
      <li><div><h4>Cast a persona and hand off</h4><p>Pick a persona from your roster;
        the panel gives you a ready-made prompt and the launch command for the CLI you
        want to argue with. You run that command yourself &mdash; this server never
        spawns a process because a web page asked it to.</p></div></li>
      <li><div><h4>The agent drafts</h4><p>Over MCP: <code>get_arena</code> to read the
        thread and the rules, <code>submit_draft</code> to answer,
        <code>wait_for_verdict</code> to find out what you decided. Pick a specific
        comment to answer and the agent is told exactly whom it is replying to.</p></div></li>
      <li><div><h4>You review</h4><p>Approve, edit, or reject with a one-click brief
        (&ldquo;too long&rdquo;, &ldquo;sounds like an LLM&rdquo;, &ldquo;needs a
        source&rdquo;) and the agent tries again. Approving inserts the text into the
        page&rsquo;s reply box and reads it back to confirm it landed. Then it is your
        thread and your click.</p></div></li>
    </ol>
  </div>

  <div class="xt-sec">
    <h3>Sites with a dedicated adapter</h3>
    <p>An adapter&rsquo;s job is to find the posts and give each one a stable id, so
       re-capturing a thread merges new replies instead of duplicating it. Anything
       else falls back to a <code>generic</code> reader, which usually works and is
       flagged in the preview when it doesn&rsquo;t.</p>
    <div class="xt-sites">{sites}</div>
  </div>

  <div class="xt-sec">
    <h3>Install it</h3>
    <ol class="xt-steps">
      <li><div><h4>Chrome (and Chromium browsers)</h4>
        <p>Open <code>chrome://extensions</code>, turn on Developer mode, choose
           <strong>Load unpacked</strong>, and select the <code>extension/</code>
           folder in your clone.</p></div></li>
      <li><div><h4>Firefox</h4>
        <p>Build the Gecko variant first, then load
           <code>extension/dist/firefox/</code> as a temporary add-on from
           <code>about:debugging</code>.</p>
        <div class="xt-code">.\\scripts\\build-extension.ps1</div></div></li>
      <li><div><h4>Point it at your local server</h4>
        <p>The panel&rsquo;s Settings expect <code>http://127.0.0.1:8765</code> &mdash;
           this app, running locally. If you set
           <code>AGENT_CHAT_BATTLEGROUND_TOKEN</code>, paste the same value there.</p></div></li>
    </ol>
    <div style="margin-top:16px">{bridge}</div>
  </div>

  <div class="xt-sec">
    <h3>Where your data goes</h3>
    <p>Nowhere. The two arena tables are deliberately excluded from the local&rarr;hosted
       sync, so captured third-party page content never reaches the public mirror. The
       persona an agent was given is snapshotted onto the arena at capture time, so
       editing a card later can&rsquo;t retroactively change what a running arena was
       told to be.</p>
  </div>

  <div class="xt-sec">
    <h3>Read more</h3>
    <div class="xt-links">
      <a href="{_REPO}/tree/main/extension" target="_blank" rel="noopener noreferrer">Extension source &amp; README &#8599;</a>
      <a href="{_REPO}/blob/main/docs/Guides/battleground.md" target="_blank" rel="noopener noreferrer">Operator guide &#8599;</a>
      <a href="{_REPO}/blob/main/docs/App/battleground.md" target="_blank" rel="noopener noreferrer">Arenas, bridge API, draft gate &#8599;</a>
      <a href="{_REPO}/tree/main/skills/battleground" target="_blank" rel="noopener noreferrer">The agent-side skill &#8599;</a>
    </div>
  </div>
</div>
"""
    return _layout(
        "Browser extension", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style><style>{EXTENSION_CSS}</style>",
        active="extension",
    )
