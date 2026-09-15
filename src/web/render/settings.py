"""The /settings page — one nav entry over the three per-machine config files.

Everything Agent-Chat stores about *this machine* rather than about a
conversation lives in `config/`, gitignored, and had grown three separate
answers: a `/setup` page, a `/notifications` page, and, for the delivery sinks,
hand-editing JSON. One tab strip, one nav row.

**The tabs are server-side** (`?tab=`). Each tab's body carries its own script
and its own element ids, and rendering only the selected one means three
independently-written forms can never collide — no id prefixing, no shared
namespace to police. It also keeps the page small: all three at once is ~600
lines of markup.

Tab bodies come from the modules that own them (`setup.setup_body`,
`notifications.notifications_body`, `_delivery_body` here), so each form still
lives next to the API it posts to.
"""

from __future__ import annotations

import html
import json

from web.assets import (DELIVERY_SETTINGS_CSS, NOTIFICATIONS_CSS,
                        ORCHESTRATE_CSS, SETTINGS_CSS, SETUP_CSS,
                        _ORCH_READONLY_CSS)
from web.render.common import _layout

_DOCS = "https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/App"

#: (slug, label, one-line description). Order is the tab order, and the first
#: is the default — CLI tools first because it is the one a fresh clone has to
#: answer before anything else works.
TABS: tuple[tuple[str, str, str], ...] = (
    ("clis", "CLI tools", "Which coding agents this machine has."),
    ("notifications", "Notifications", "Be told when a run finishes or gets stuck."),
    ("delivery", "Delivery", "Write finished conversations out to a folder or a command."),
)

DEFAULT_TAB = TABS[0][0]

#: Old single-purpose URLs → the tab that replaced them. `web_ui` redirects
#: these so links in docs, bookmarks and older CHANGELOG entries keep working.
LEGACY_PATHS: dict[str, str] = {
    "/setup": "clis",
    "/notifications": "notifications",
}


def resolve_tab(raw: str | None) -> str:
    """A `?tab=` value, or the default. Never raises on junk — an unknown tab
    is a mistyped link, not an error page."""
    slug = (raw or "").strip().lower()
    return slug if any(slug == t[0] for t in TABS) else DEFAULT_TAB


def _tab_strip(active: str) -> str:
    """The tab row. Plain links, so a tab is a real URL you can bookmark and
    the back button does what it should."""
    items = []
    for slug, label, _desc in TABS:
        cls = "set-tab on" if slug == active else "set-tab"
        aria = ' aria-current="page"' if slug == active else ""
        items.append(
            f'<a class="{cls}" href="/settings?tab={slug}"{aria}>{html.escape(label)}</a>'
        )
    return f'<nav class="set-tabs" aria-label="Settings sections">{"".join(items)}</nav>'


#: Event order and wording for the delivery ticklists. Deliberately NOT
#: `delivery.EVENTS` order, which is chronological (started → result →
#: complete → stalled) and buries the two anyone actually wants. Same order and
#: the same words as the Notifications tab, so the two read as one setting.
_EVENT_LABELS: tuple[tuple[str, str], ...] = (
    ("complete", "finishes"),
    ("stalled", "goes quiet"),
    ("started", "starts"),
    ("result", "posts a deliverable"),
)


def _event_checks(name: str, active: list[str], all_events: list[str]) -> str:
    """The shared event ticklist, used by both delivery sinks."""
    labels = dict(_EVENT_LABELS)
    # Known events in display order, then anything new that hasn't been given a
    # label yet — so adding a fifth event still renders rather than vanishing.
    ordered = ([e for e, _ in _EVENT_LABELS if e in all_events]
               + [e for e in all_events if e not in labels])
    out = []
    for event in ordered:
        checked = " checked" if event in active else ""
        out.append(
            f'<label class="set-evchk"><input type="checkbox" data-events="{name}" '
            f'value="{html.escape(event, quote=True)}"{checked}> '
            f'{html.escape(labels.get(event, event))}</label>'
        )
    return f'<div class="set-evrow">{"".join(out)}</div>'


def _delivery_body(state: dict) -> str:
    """The Delivery tab: the folder sink and the command sink."""
    folder = state.get("folder") or {}
    command = state.get("command") or {}
    all_events = list(state.get("events") or [])

    extras = state.get("extra_sinks") or []
    extras_note = ""
    if extras:
        extras_note = (
            '<p class="su-plan-note">Your config has more than one '
            f'<strong>{html.escape(", ".join(extras))}</strong> sink. This page '
            'edits the first of each and leaves the rest alone &mdash; use the '
            'file directly for those.</p>'
        )

    body = f"""
<div class="orch-shell su-shell set-shell">
  <header class="orch-head">
    <h2>Write finished conversations out</h2>
    <p>A conversation lives in <code>db/chat.db</code> and you come here to read it.
       Delivery is the other direction: when a run ends, push it somewhere. The
       folder sink writes the <strong>same bundle the <code>.zip</code> download
       contains</strong>, unpacked; the command sink runs something against that
       folder. Both are off until you say otherwise.</p>
  </header>

  <form id="dl-form" class="orch-form">
    <section>
      <label class="nt-toggle">
        <input type="checkbox" id="dl-folder-enabled"{' checked' if folder.get('enabled') else ''}>
        <span>Save a copy of each finished conversation to a folder</span>
      </label>
      <div class="set-sub">
        <span class="lbl">Folder</span>
        <p class="hint">Relative paths resolve against the repo root, so a bare
           <code>deliveries</code> lands beside <code>db/</code>.</p>
        <input type="text" id="dl-folder-path" class="nt-input"
               value="{html.escape(str(folder.get('path') or 'deliveries'), quote=True)}"
               autocomplete="off" spellcheck="false">

        <span class="lbl">Which conversations</span>
        <p class="hint">Every run, or only the ones whose launch form had
           <em>save a copy</em> ticked.</p>
        <div class="set-evrow">
          <label class="set-evchk"><input type="radio" name="dl-scope" value="all"
            {'checked' if folder.get('scope') != 'opt-in' else ''}> every conversation</label>
          <label class="set-evchk"><input type="radio" name="dl-scope" value="opt-in"
            {'checked' if folder.get('scope') == 'opt-in' else ''}> only ones I tick at launch</label>
        </div>

        <span class="lbl">Write it when a conversation&hellip;</span>
        {_event_checks("folder", list(folder.get("events") or []), all_events)}

        <label class="set-evchk set-inline">
          <input type="checkbox" id="dl-folder-result"{' checked' if folder.get('include_result') else ''}>
          also write <code>result.md</code> &mdash; the deliverable on its own
        </label>
        <p class="hint">Not part of the <code>.zip</code> bundle, so it's off by
           default. Worth it for collaborations, where digging the artifact out of
           <code>transcript.md</code> is the whole chore.</p>
      </div>
    </section>

    <section>
      <label class="nt-toggle">
        <input type="checkbox" id="dl-cmd-enabled"{' checked' if command.get('enabled') else ''}>
        <span>Run a command against the delivered folder</span>
      </label>
      <div class="set-sub">
        <span class="lbl">Command</span>
        <p class="hint"><code>{{dir}}</code>, <code>{{cid}}</code>,
           <code>{{topic}}</code> and <code>{{event}}</code> are substituted.
           Quoting works like a shell, so a path with a space stays one argument.
           This runs whatever you put here, with your privileges &mdash; it is
           exactly as trusted as a shell alias, which is the point of it.</p>
        <input type="text" id="dl-cmd-argv" class="nt-input"
               value="{html.escape(str(command.get('argv') or ''), quote=True)}"
               placeholder="pwsh -NoProfile -Command &quot;Write-Host {{dir}}&quot;"
               autocomplete="off" spellcheck="false">

        <span class="lbl">Run it when a conversation&hellip;</span>
        {_event_checks("command", list(command.get("events") or []), all_events)}

        <span class="lbl">Timeout (seconds)</span>
        <input type="number" id="dl-cmd-timeout" class="nt-input set-num" min="1"
               value="{int(command.get('timeout') or 120)}">
        <p class="hint">Needs the folder sink switched on &mdash; it acts on the
           files that sink wrote, so on its own there is nothing to hand it.</p>
      </div>
    </section>

    <div id="dl-error" class="orch-error hidden"></div>

    <div class="nt-actions">
      <button type="submit" class="orch-submit">Save</button>
      <span class="su-seats-msg" id="dl-msg"></span>
    </div>

    <p class="hint su-foot">Stored in
       <code>{html.escape(str(state.get('config_path') or ''))}</code> (gitignored,
       this machine only). Failures are logged to
       <code>{html.escape(str(state.get('log_path') or ''))}</code> and never
       reach a conversation &mdash; a sink costs an artifact, never a turn. Full
       reference: <a href="{_DOCS}/delivery.md" target="_blank"
       rel="noopener noreferrer">delivery &#8599;</a>.{extras_note}</p>
  </form>
</div>

<script>
(function() {{
  const form = document.getElementById('dl-form');
  const errorPanel = document.getElementById('dl-error');
  const msg = document.getElementById('dl-msg');
  const saveBtn = form.querySelector('button[type=submit]');

  function events(name) {{
    return Array.from(form.querySelectorAll('input[data-events=' + name + ']:checked'))
      .map(b => b.value);
  }}

  function esc(s) {{
    return String(s).replace(/[&<>"']/g, c => (
      {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]
    ));
  }}

  form.addEventListener('submit', async (ev) => {{
    ev.preventDefault();
    errorPanel.classList.add('hidden');
    msg.className = 'su-seats-msg';
    msg.textContent = 'Saving\\u2026';
    saveBtn.disabled = true;
    const payload = {{
      folder: {{
        enabled: document.getElementById('dl-folder-enabled').checked,
        path: document.getElementById('dl-folder-path').value.trim(),
        include_result: document.getElementById('dl-folder-result').checked,
        scope: (form.querySelector('input[name=dl-scope]:checked') || {{}}).value || 'all',
        events: events('folder'),
      }},
      command: {{
        enabled: document.getElementById('dl-cmd-enabled').checked,
        argv: document.getElementById('dl-cmd-argv').value.trim(),
        timeout: parseInt(document.getElementById('dl-cmd-timeout').value, 10) || 120,
        events: events('command'),
      }},
    }};
    try {{
      const res = await fetch('/api/settings/delivery', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload),
      }});
      const data = await res.json();
      if (data.ok) {{
        msg.className = 'su-seats-msg ok';
        msg.textContent = 'Saved \\u2713';
      }} else {{
        msg.textContent = '';
        errorPanel.innerHTML = '<h4>Not saved</h4><p>' +
          esc(data.error || 'Unknown error') + '</p>';
        errorPanel.classList.remove('hidden');
      }}
    }} catch (err) {{
      msg.textContent = '';
      errorPanel.innerHTML = '<h4>Network error</h4><p>' + esc(String(err)) + '</p>';
      errorPanel.classList.remove('hidden');
    }} finally {{
      saveBtn.disabled = false;
    }}
  }});
}})();
</script>
"""
    return body


def render_settings(tab: str, body_html: str, css: tuple[str, ...]) -> str:
    """Wrap one tab's body in the tab strip and the page shell."""
    head = "".join(f"<style>{sheet}</style>" for sheet in
                   (SETTINGS_CSS,) + tuple(css))
    return _layout(
        "Settings", "", _tab_strip(tab) + body_html,
        head_extras=head,
        active="settings",
    )


def render_delivery_tab(state: dict) -> str:
    """Convenience wrapper — the Delivery tab as a whole page."""
    return render_settings(
        "delivery", _delivery_body(state),
        (ORCHESTRATE_CSS, SETUP_CSS, NOTIFICATIONS_CSS, DELIVERY_SETTINGS_CSS),
    )


def _render_settings_readonly(tab: str) -> str:
    """Hosted /settings — every tab describes a file that doesn't exist here.

    Same call as the hosted `/orchestrate` and `/battleground`: an empty form
    would read as "settings are broken" rather than "this is a viewer". The tab
    strip still renders, so the shape of the page is honest about what a local
    instance offers.
    """
    blurbs = {
        "clis": (
            "Which CLI tools you have",
            "<p>A ticklist of every supported CLI with two probe results each &mdash; is "
            "the launcher binary on your <code>PATH</code>, and does its "
            "<code>agent_chat</code> MCP entry pass preflight &mdash; plus a button to "
            "create the extra seat folders a small CLI set needs. This hosted site has "
            "no <code>PATH</code> worth probing.</p>",
            "cli-setup.md"),
        "notifications": (
            "Being told when something happens",
            "<p>Point ntfy, Gotify, Discord, Slack or any webhook at four events: a run "
            "<strong>finishes</strong>, <strong>goes quiet</strong>, <strong>starts</strong>, "
            "or <strong>posts a deliverable</strong>. Those fire in whichever process is "
            "driving your CLI windows, which is never this one.</p>",
            "notifications.md"),
        "delivery": (
            "Writing finished conversations out",
            "<p>Unpack the export bundle into a folder as each run ends, and optionally run "
            "a command against it. The mirror has no filesystem you'd want either written "
            "to, and nothing here ends a conversation.</p>",
            "delivery.md"),
    }
    title, detail, doc = blurbs.get(tab, blurbs["clis"])
    body = f"""
<div class="orch-shell">
  <header class="orch-head">
    <h2>Settings live on your own machine</h2>
    <p>This hosted site is a <strong>read-only demo</strong>. Everything on this page
       is stored in <code>config/</code> &mdash; gitignored, per-machine, and about
       the computer that runs your CLI agents. None of it exists here.</p>
  </header>

  <div class="orch-ro-card">
    <h3>{html.escape(title)}</h3>
    {detail}
  </div>

  <div class="orch-ro-card">
    <h3>Open it locally</h3>
    <pre><code>.\\.venv\\Scripts\\python.exe src\\web_ui.py
# then open http://127.0.0.1:8765/settings?tab={html.escape(tab, quote=True)}</code></pre>
    <p>Nothing you set there leaves that machine, and nothing is committed.</p>
  </div>

  <p class="orch-ro-foot">Full reference:
    <a href="{_DOCS}/{doc}" target="_blank" rel="noopener noreferrer">{html.escape(doc)} &#8599;</a>.</p>
</div>
"""
    return _layout(
        "Settings", "", _tab_strip(tab) + body,
        head_extras=(f"<style>{SETTINGS_CSS}</style>"
                     f"<style>{ORCHESTRATE_CSS}</style>{_ORCH_READONLY_CSS}"),
        active="settings",
    )


__all__ = [
    "TABS",
    "DEFAULT_TAB",
    "LEGACY_PATHS",
    "resolve_tab",
    "render_settings",
    "render_delivery_tab",
    "_delivery_body",
    "_render_settings_readonly",
]
