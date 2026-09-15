"""The /notifications page (local) and its hosted read-only explainer.

"Tell me when a run finishes or gets stuck" — the thing
``orchestrator.delivery`` could already do and nobody could turn on without
knowing the shape of ``config/delivery.json``.

The page is a *view of one sink*, not a new subsystem: see
``web.api.notifications`` for why services are a rendering rather than a type,
and ``orchestrator.delivery.post_webhook`` for why there are no per-service
adapters behind it.

Borrows the orchestrate shell and the setup page's CSS wholesale (``.orch-*``,
``.su-*``) — it is the same kind of page, asking a different question, and a
third stylesheet for two radio groups and a ticklist would be three files to
keep in visual sync instead of one.
"""

from __future__ import annotations

import html
import json

from web.api.notifications import DEFAULT_SERVICE, SERVICES
from web.assets import (NOTIFICATIONS_CSS, ORCHESTRATE_CSS, SETUP_CSS,
                        _ORCH_READONLY_CSS)
from web.render.common import _layout

_DOCS = ("https://github.com/ai-automation-tools/Agent-chat/blob/main/"
         "docs/App/notifications.md")

#: The four delivery events, in the order an operator cares about them, with
#: the wording they'd use. ``complete`` and ``stalled`` are ticked by default:
#: between them they answer "is it done?" and "is it stuck?", which is the
#: whole reason to walk away from the machine.
_EVENT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("complete", "A conversation finishes",
     "Debate, podcast or collaboration — fires once, when the run ends, "
     "whether it ended on a signal, a turn cap, or you stopping it."),
    ("stalled", "A run goes quiet (stuck)",
     "The watchdog's event. Fires while the run is still open, once per stall, "
     "when nothing has been said for longer than that conversation's own "
     "rhythm allows — usually a CLI window sitting on an unanswered prompt."),
    ("started", "A conversation starts",
     "Fires the moment a run is seeded, from the web form or the command line. "
     "Useful if something else launches runs for you."),
    ("result", "A deliverable is posted",
     "Collaborations only: the facilitator tagged a message "
     "<code>signal='result'</code>. A lead that drafts then revises posts "
     "several, so this one can fire more than once per run."),
)


def _service_radio(service_id: str, active: str) -> str:
    meta = SERVICES[service_id]
    checked = " checked" if service_id == active else ""
    return (
        f'<label class="su-row nt-svc" data-service="{html.escape(service_id, quote=True)}">'
        '<span class="su-main">'
        f'<input type="radio" name="nt-service" value="{html.escape(service_id, quote=True)}"{checked}>'
        '<span class="su-names">'
        f'<span class="su-name">{html.escape(str(meta["label"]))}</span>'
        f'<span class="su-sub">{html.escape(str(meta["target_label"]))}</span>'
        '</span></span></label>'
    )


def _event_row(event: str, label: str, detail: str, active: list[str]) -> str:
    checked = " checked" if event in active else ""
    return (
        '<label class="su-row nt-ev">'
        '<span class="su-main">'
        f'<input type="checkbox" name="nt-event" value="{html.escape(event, quote=True)}"{checked}>'
        '<span class="su-names">'
        f'<span class="su-name">{html.escape(label)}</span>'
        f'<span class="su-sub nt-evsub">{detail}</span>'
        '</span></span></label>'
    )


def notifications_body(state: dict) -> str:
    """The notification form, without the page shell — see `setup_body`."""
    service = state.get("service") or DEFAULT_SERVICE
    events = list(state.get("events") or ["complete", "stalled"])
    radios = "".join(_service_radio(s, service) for s in SERVICES)
    rows = "".join(_event_row(e, lbl, det, events) for e, lbl, det in _EVENT_ROWS)

    if state.get("configured") and state.get("enabled") and state.get("delivery_enabled"):
        status = ('<span class="su-pill ok">on</span> Notifications are armed. '
                  'Edit and save to change them, or untick <em>Send me these '
                  'notifications</em> to stop.')
    elif state.get("configured"):
        status = ('<span class="su-pill warn">off</span> Saved but not sending. '
                  'Tick <em>Send me these notifications</em> and save.')
    else:
        status = ('<span class="su-pill off">not set up</span> Nothing is configured '
                  'yet, so nothing is sent.')

    others = state.get("other_sinks") or []
    others_note = ""
    if others:
        kinds = ", ".join(sorted(set(others)))
        others_note = (
            '<p class="su-plan-note">Your config also has '
            f'<strong>{html.escape(kinds)}</strong> '
            f'sink{"" if len(set(others)) == 1 else "s"} in it, set up by hand. '
            'Saving here replaces only the notification sink &mdash; those are '
            'left exactly as they are.</p>'
        )

    meta_json = json.dumps({k: {"target_label": v["target_label"],
                                "target_hint": v["target_hint"],
                                "placeholder": v["placeholder"],
                                "server": v.get("server") or "",
                                "docs": v.get("docs") or ""}
                            for k, v in SERVICES.items()})
    # On a page that has never been configured, `enabled` is False — there is no
    # sink to be enabled. Seeding the toggle from that would hand a first-time
    # operator a form that fills in, saves, and arms nothing. An untouched page
    # means "I am here to turn this on".
    toggle_on = bool(state.get("enabled")) if state.get("configured") else True
    state_json = json.dumps({"target": state.get("target") or "",
                             "server": state.get("server") or "",
                             "enabled": toggle_on,
                             "service": service})

    body = f"""
<div class="orch-shell su-shell nt-shell">
  <header class="orch-head">
    <h2>Tell me when something happens</h2>
    <p>A conversation runs in CLI windows you've probably walked away from. This
       points one notification service at the four moments worth knowing about
       &mdash; most usefully <strong>it finished</strong> and <strong>it's
       stuck</strong>. {status}</p>
  </header>

  <form id="nt-form" class="orch-form">
    <section>
      <span class="lbl">Where should it go?</span>
      <p class="hint">One service at a time. All five are a single HTTP POST &mdash;
         nothing is installed, and no account is needed for
         <a href="https://ntfy.sh" target="_blank" rel="noopener noreferrer">ntfy</a>,
         which is why it's the default.</p>
      <div class="su-rows nt-svcs">{radios}</div>
    </section>

    <section>
      <span class="lbl" id="nt-target-label">Topic</span>
      <p class="hint" id="nt-target-hint"></p>
      <input type="text" id="nt-target" class="nt-input" autocomplete="off" spellcheck="false">
      <div id="nt-server-wrap" class="nt-server">
        <span class="lbl">Server</span>
        <p class="hint">Change this only if you self-host.</p>
        <input type="text" id="nt-server" class="nt-input" autocomplete="off" spellcheck="false">
      </div>
    </section>

    <section>
      <span class="lbl">Tell me when&hellip;</span>
      <p class="hint">Each is a delivery event. Tick what you want to hear about;
         everything else stays silent.</p>
      <div class="su-rows">{rows}</div>
    </section>

    <section>
      <label class="nt-toggle">
        <input type="checkbox" id="nt-enabled" checked>
        <span>Send me these notifications</span>
      </label>
      <p class="hint">Untick to keep the settings but stop sending. Nothing here can
         fail a conversation &mdash; a notification that doesn't go through costs you
         the message, never the run, and the reason lands in
         <code>{html.escape(str(state.get('log_path') or ''))}</code>.</p>
    </section>

    <div id="nt-error" class="orch-error hidden"></div>

    <div class="nt-actions">
      <button type="button" class="btn" id="nt-test">Send test notification</button>
      <button type="submit" class="orch-submit">Save</button>
      <span class="su-seats-msg" id="nt-msg"></span>
    </div>

    <p class="hint su-foot">Stored in
       <code>{html.escape(str(state.get('config_path') or ''))}</code> (gitignored,
       this machine only) as one sink of the existing
       <a href="{_DOCS}" target="_blank" rel="noopener noreferrer">delivery system &#8599;</a>
       &mdash; which can also write the finished bundle to a folder or run a
       command, both hand-configured in the same file.{others_note}</p>
  </form>
</div>

<script>
(function() {{
  const META = {meta_json};
  const SAVED = {state_json};
  const form = document.getElementById('nt-form');
  const targetIn = document.getElementById('nt-target');
  const serverIn = document.getElementById('nt-server');
  const serverWrap = document.getElementById('nt-server-wrap');
  const tLabel = document.getElementById('nt-target-label');
  const tHint = document.getElementById('nt-target-hint');
  const errorPanel = document.getElementById('nt-error');
  const msg = document.getElementById('nt-msg');
  const testBtn = document.getElementById('nt-test');
  const saveBtn = form.querySelector('button[type=submit]');
  const enabledIn = document.getElementById('nt-enabled');

  // Per-service scratch, so switching radios to compare options and switching
  // back doesn't silently drop the URL you already pasted.
  const scratch = {{}};
  let current = SAVED.service;
  scratch[SAVED.service] = {{target: SAVED.target, server: SAVED.server}};
  enabledIn.checked = SAVED.enabled;

  function svc() {{
    const el = form.querySelector('input[name=nt-service]:checked');
    return el ? el.value : '{DEFAULT_SERVICE}';
  }}

  function paint(to) {{
    const meta = META[to] || {{}};
    tLabel.textContent = meta.target_label || 'URL';
    tHint.innerHTML = meta.target_hint || '';
    if (meta.docs) {{
      tHint.innerHTML += ' <a href="' + meta.docs + '" target="_blank" ' +
        'rel="noopener noreferrer">Docs \\u2197</a>';
    }}
    targetIn.placeholder = meta.placeholder || '';
    const saved = scratch[to] || {{}};
    targetIn.value = saved.target || '';
    if (meta.server) {{
      serverWrap.style.display = '';
      serverIn.value = saved.server || meta.server;
    }} else {{
      serverWrap.style.display = 'none';
      serverIn.value = '';
    }}
  }}

  form.addEventListener('change', (ev) => {{
    if (ev.target.name !== 'nt-service') return;
    scratch[current] = {{target: targetIn.value, server: serverIn.value}};
    current = ev.target.value;
    paint(current);
  }});

  function events() {{
    return Array.from(form.querySelectorAll('input[name=nt-event]:checked'))
      .map(b => b.value);
  }}

  function payload() {{
    return {{
      service: svc(),
      target: targetIn.value.trim(),
      server: serverIn.value.trim(),
      events: events(),
      enabled: enabledIn.checked,
    }};
  }}

  function esc(s) {{
    return String(s).replace(/[&<>"']/g, c => (
      {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]
    ));
  }}

  function fail(title, detail) {{
    errorPanel.innerHTML = '<h4>' + esc(title) + '</h4><p>' + esc(detail) + '</p>';
    errorPanel.classList.remove('hidden');
  }}

  async function send(url, btn, busy, done) {{
    errorPanel.classList.add('hidden');
    msg.className = 'su-seats-msg';
    msg.textContent = busy;
    btn.disabled = true;
    try {{
      const res = await fetch(url, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload()),
      }});
      const data = await res.json();
      if (data.ok) {{
        msg.className = 'su-seats-msg ok';
        msg.textContent = done;
        return true;
      }}
      msg.textContent = '';
      fail('Not sent', data.error || 'Unknown error');
    }} catch (err) {{
      msg.textContent = '';
      fail('Network error', String(err));
    }} finally {{
      btn.disabled = false;
    }}
    return false;
  }}

  testBtn.addEventListener('click', () => send(
    '/api/notifications/test', testBtn,
    'Sending\\u2026', 'Sent \\u2713 \\u2014 check your device'));

  form.addEventListener('submit', (ev) => {{
    ev.preventDefault();
    send('/api/notifications', saveBtn, 'Saving\\u2026', 'Saved \\u2713');
  }});

  paint(current);
}})();
</script>
"""
    return body


#: Stylesheets this tab's markup needs, in order.
NOTIFICATIONS_TAB_CSS = (ORCHESTRATE_CSS, SETUP_CSS, NOTIFICATIONS_CSS)


def _render_notifications(state: dict) -> str:
    """Standalone notifications page. Kept for direct callers and tests; the
    route itself now renders through `/settings`."""
    return _layout(
        "Notifications", "", notifications_body(state),
        head_extras=(f"<style>{ORCHESTRATE_CSS}</style><style>{SETUP_CSS}</style>"
                     f"<style>{NOTIFICATIONS_CSS}</style>"),
        active="settings",
    )


def _render_notifications_readonly() -> str:
    """Hosted /notifications — there is nothing here to notify anyone about.

    Same reasoning as the hosted ``/battleground`` console: an empty form would
    read as "notifications are broken" rather than "this is a viewer". The
    config file is per-machine and the events fire in the process that runs
    your CLIs, which is never this one.
    """
    body = f"""
<div class="orch-shell">
  <header class="orch-head">
    <h2>Notifications come from your own machine</h2>
    <p>This hosted site is a <strong>read-only demo</strong>. It mirrors conversations
       for reading; it doesn't run them. The events that would notify you &mdash;
       a run finishing, a run going quiet &mdash; happen in the process driving your
       CLI windows, so this page only does something on a local instance.</p>
  </header>

  <div class="orch-ro-card">
    <h3>What you can be told about</h3>
    <p><strong>A conversation finishes</strong> &middot; <strong>a run goes
       quiet</strong> (the watchdog notices a stall while the run is still open, and
       says so once) &middot; <strong>a conversation starts</strong> &middot;
       <strong>a deliverable is posted</strong> by a collaboration's facilitator.</p>
  </div>

  <div class="orch-ro-card">
    <h3>Where it can go</h3>
    <p>ntfy, Gotify, Discord, Slack, or any URL that accepts a POST &mdash; n8n, Home
       Assistant, a script of your own. Each is one HTTP request, so there's nothing
       to install and no account needed for ntfy.</p>
  </div>

  <div class="orch-ro-card">
    <h3>Turn it on locally</h3>
    <pre><code>.\\.venv\\Scripts\\python.exe src\\web_ui.py
# then open http://127.0.0.1:8765/notifications</code></pre>
    <p>Pick a service, paste a topic or URL, tick the events, send yourself a test.
       It's written to <code>config/delivery.json</code> &mdash; gitignored, and it
       never leaves that machine.</p>
  </div>

  <p class="orch-ro-foot">The full reference, including the folder and command sinks
    this page doesn't manage, is in
    <a href="{_DOCS}" target="_blank" rel="noopener noreferrer">the notifications
    doc &#8599;</a>.</p>
</div>
"""
    return _layout(
        "Notifications", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style>{_ORCH_READONLY_CSS}",
        active="settings",
    )


__all__ = ["_render_notifications", "_render_notifications_readonly"]
