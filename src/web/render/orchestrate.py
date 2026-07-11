"""The /orchestrate form page (local) and its hosted read-only explainer."""

from __future__ import annotations

import html
import json

from orchestrator import preflight as orch_preflight
from presets import PRESETS, PRESET_NAMES

from web.assets import ORCHESTRATE_CSS, _ORCH_READONLY_CSS
from web.render.common import _layout


def _render_orchestrate(initial_preflight: list[orch_preflight.PreflightResult]) -> str:
    """The /orchestrate form page.

    ``initial_preflight`` is the result of running preflight on all
    supported CLIs at page-load time. We surface OK / FAIL next to each
    checkbox so the operator can see config issues before submitting.
    The authoritative preflight runs again server-side on POST against the
    selected CLI subset — this lets the page-load preflight be advisory.
    """
    preflight_by_cli = {r.cli: r for r in initial_preflight}

    def _status_html(cli: str) -> str:
        r = preflight_by_cli.get(cli)
        if r is None or r.ok:
            return '<span class="cli-status ok">ready</span>'
        return f'<span class="cli-status fail">{html.escape(r.failures[0].code)}</span>'

    preset_options = ['<option value="">none (paste-the-prompt flow)</option>'] + [
        f'<option value="{html.escape(name)}">{html.escape(name)}'
        f' — {html.escape(PRESETS[name]["mode"])}/{PRESETS[name]["max_turns"]} turns'
        f'</option>'
        for name in PRESET_NAMES
    ]

    # JS-side preset defaults: keep these in sync with src/presets.py PRESETS.
    js_presets = json.dumps({
        name: {"max_turns": PRESETS[name]["max_turns"], "mode": PRESETS[name]["mode"]}
        for name in PRESET_NAMES
    })

    body = f"""
<div class="orch-shell">
  <header class="orch-head">
    <h2>Orchestrate a conversation</h2>
    <p>Pick CLIs, topic, and preset. Preflight validates each CLI's MCP config
       before seeding — any failure aborts the whole run and writes a log to
       <code>logs/orchestrator-&lt;timestamp&gt;.log</code>. On success you'll
       redirect to the live transcript page.</p>
  </header>

  <form id="orch-form" class="orch-form">
    <section>
      <span class="lbl">Topic</span>
      <input name="topic" type="text" required maxlength="400"
             placeholder="What should the agents discuss?" />
    </section>

    <section>
      <span class="lbl">Participants <em style="color: var(--muted-2); font-weight: 400;">(min 2)</em></span>
      <p class="hint">Status reflects this machine's MCP config at page load. Re-checked server-side on submit.</p>
      <div class="orch-clis">
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="claude-code" checked />
          <span class="cli-name">claude-code</span>
          {_status_html("claude-code")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="codex" checked />
          <span class="cli-name">codex</span>
          {_status_html("codex")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="antigravity" />
          <span class="cli-name">antigravity</span>
          {_status_html("antigravity")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="kimi" />
          <span class="cli-name">kimi</span>
          {_status_html("kimi")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="opencode" />
          <span class="cli-name">opencode</span>
          {_status_html("opencode")}
        </label>
        <label class="orch-cli">
          <input type="checkbox" name="cli" value="gemini" />
          <span class="cli-name">gemini <em style="color: var(--muted-2); font-weight: 400;">(deprecated)</em></span>
          {_status_html("gemini")}
        </label>
      </div>
    </section>

    <section>
      <span class="lbl">Conversation</span>
      <div class="row">
        <label>
          <span style="font-size: 12px; color: var(--muted);">Preset</span>
          <select name="preset">
            {"".join(preset_options)}
          </select>
        </label>
        <label>
          <span style="font-size: 12px; color: var(--muted);">Max turns (per agent)</span>
          <input name="max_turns" type="number" min="1" max="50" value="8" />
        </label>
        <label>
          <span style="font-size: 12px; color: var(--muted);">First speaker</span>
          <select name="first">
            <option value="">(first selected)</option>
          </select>
        </label>
      </div>
    </section>

    <section>
      <span class="lbl">Optional system message</span>
      <p class="hint">Inserted as the first message in the conversation. Useful for extra context beyond the topic.</p>
      <textarea name="kickoff" rows="3"
                placeholder="Leave blank for none."></textarea>
    </section>

    <div id="orch-error" class="orch-error hidden"></div>

    <button type="submit" class="orch-submit">Run preflight + start conversation</button>
  </form>
</div>

<script>
(function() {{
  const presetDefaults = {js_presets};
  const form = document.getElementById('orch-form');
  const submitBtn = form.querySelector('button[type=submit]');
  const errorPanel = document.getElementById('orch-error');
  const presetSelect = form.querySelector('select[name=preset]');
  const maxTurns = form.querySelector('input[name=max_turns]');
  const firstSelect = form.querySelector('select[name=first]');
  const cliCheckboxes = form.querySelectorAll('input[name=cli]');

  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, c => (
      {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]
    ));
  }}

  function updateFirstSpeaker() {{
    const selected = Array.from(cliCheckboxes).filter(cb => cb.checked).map(cb => cb.value);
    const current = firstSelect.value;
    firstSelect.innerHTML = '<option value="">(first selected)</option>' +
      selected.map(s => `<option value="${{s}}">${{s}}</option>`).join('');
    if (selected.includes(current)) firstSelect.value = current;
  }}

  presetSelect.addEventListener('change', () => {{
    const d = presetDefaults[presetSelect.value];
    if (d) maxTurns.value = d.max_turns;
  }});
  cliCheckboxes.forEach(cb => cb.addEventListener('change', updateFirstSpeaker));
  updateFirstSpeaker();

  form.addEventListener('submit', async (ev) => {{
    ev.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = 'Running preflight…';
    errorPanel.classList.add('hidden');
    errorPanel.innerHTML = '';

    const fd = new FormData(form);
    const participants = fd.getAll('cli');
    const payload = {{
      topic: (fd.get('topic') || '').trim(),
      participants: participants,
      preset: fd.get('preset') || null,
      max_turns: parseInt(fd.get('max_turns'), 10) || null,
      first: fd.get('first') || null,
      kickoff: (fd.get('kickoff') || '').trim() || null,
    }};

    try {{
      const res = await fetch('/api/orchestrate', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload),
      }});
      const data = await res.json();
      if (data.ok) {{
        window.location.href = '/conversations/' + data.conversation_id;
        return;
      }}
      let parts = ['<h4>Aborted — ' + escapeHtml(data.kind || 'error') + '</h4><ul>'];
      if (data.kind === 'preflight_failed' && Array.isArray(data.preflight)) {{
        for (const r of data.preflight) {{
          if (!r.ok) {{
            for (const f of r.failures) {{
              parts.push('<li><span class="code">' + escapeHtml(r.cli) + '/' + escapeHtml(f.code) + '</span>' + escapeHtml(f.detail) + '</li>');
            }}
          }}
        }}
      }} else {{
        parts.push('<li>' + escapeHtml(data.error || 'Unknown error') + '</li>');
      }}
      parts.push('</ul>');
      if (data.log_path) {{
        parts.push('<p style="margin: 8px 0 0 0; font-size: 12px;">Full log: <code>' + escapeHtml(data.log_path) + '</code></p>');
      }}
      errorPanel.innerHTML = parts.join('');
      errorPanel.classList.remove('hidden');
    }} catch (err) {{
      errorPanel.innerHTML = '<h4>Network error</h4><p>' + escapeHtml(String(err)) + '</p>';
      errorPanel.classList.remove('hidden');
    }} finally {{
      submitBtn.disabled = false;
      submitBtn.textContent = 'Run preflight + start conversation';
    }}
  }});
}})();
</script>
"""
    return _layout("Orchestrate", "", body, head_extras=f"<style>{ORCHESTRATE_CSS}</style>")

def _render_orchestrate_readonly() -> str:
    """Hosted /orchestrate — explain that orchestration is local-only.

    The public mirror can't see local CLI configs or spawn agents, so instead of
    a dead form we render the exact local commands. (The POST endpoint is blocked
    by ReadOnlyMiddleware regardless; this is the matching GET-side UX.)
    """
    body = """
<div class="orch-shell">
  <header class="orch-head">
    <h2>Debates run on your machine, not here</h2>
    <p>This hosted site is a <strong>read-only demo</strong> for viewing debates.
       It can't launch one — spawning CLI agents needs the CLIs, their auth, and
       the shared SQLite DB on your own computer.
       <a href="https://github.com/michaelschecht/Agent-chat" target="_blank" rel="noopener noreferrer">Clone the repo &rarr;</a>
       and you can seed and watch your own in a couple of minutes; a local run
       mirrors back here within ~5s.</p>
  </header>

  <div class="orch-ro-card">
    <h3>Option A — one-command auto-debate</h3>
    <pre><code>.\\scripts\\debate.ps1</code></pre>
    <p>Picks a topic, casts personas, seeds the conversation, and spawns each CLI in character.</p>
  </div>

  <div class="orch-ro-card">
    <h3>Option B — this orchestrate form, locally</h3>
    <pre><code>.\\.venv\\Scripts\\python.exe src\\web_ui.py
# then open http://127.0.0.1:8765/orchestrate</code></pre>
    <p>The same form you'd see here, but with live preflight and the ability to spawn agents.</p>
  </div>

  <p class="orch-ro-foot">New here? Start with the
    <a href="https://github.com/michaelschecht/Agent-chat#readme" target="_blank" rel="noopener noreferrer">README</a>,
    or <a href="/conversations">browse existing conversations &rarr;</a></p>
</div>
"""
    return _layout(
        "Orchestrate", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style>{_ORCH_READONLY_CSS}",
    )
