"""The /orchestrate form page (local) and its hosted read-only explainer."""

from __future__ import annotations

import html
import json

from orchestrator import preflight as orch_preflight
from presets import PRESETS, PRESET_NAMES

from web.assets import ORCHESTRATE_CSS, _ORCH_READONLY_CSS
from web.render.common import _layout


# Persona-select rows and participant checkboxes both iterate this order.
_ORCH_CLI_IDS = ("claude-code", "codex", "antigravity", "kimi", "opencode", "gemini")


def _render_orchestrate(
    initial_preflight: list[orch_preflight.PreflightResult],
    persona_roster: list[dict] | None = None,
) -> str:
    """The /orchestrate form page.

    ``initial_preflight`` is the result of running preflight on all
    supported CLIs at page-load time. We surface OK / FAIL next to each
    checkbox so the operator can see config issues before submitting.
    The authoritative preflight runs again server-side on POST against the
    selected CLI subset — this lets the page-load preflight be advisory.

    ``persona_roster`` is ``[{"group": str, "personas": [{"slug", "name"}]}]``
    (from ``orchestrator.personas``) used to build the per-CLI persona picker.
    An empty/None roster still renders the picker (just the random/none choices).
    """
    preflight_by_cli = {r.cli: r for r in initial_preflight}
    persona_roster = persona_roster or []

    def _status_html(cli: str) -> str:
        r = preflight_by_cli.get(cli)
        if r is None or r.ok:
            return '<span class="cli-status ok">ready</span>'
        return f'<span class="cli-status fail">{html.escape(r.failures[0].code)}</span>'

    # Shared <optgroup> block (the roster), reused by every persona <select>.
    optgroups = []
    for grp in persona_roster:
        cards = grp.get("personas") or []
        if not cards:
            continue
        optgroups.append(f'<optgroup label="{html.escape(str(grp.get("group", "")))}">')
        for p in cards:
            optgroups.append(
                f'<option value="{html.escape(str(p["slug"]))}">'
                f'{html.escape(str(p["name"]))}</option>'
            )
        optgroups.append("</optgroup>")
    optgroups_html = "".join(optgroups)

    # Debater select: none / random / roster.
    persona_opts_html = (
        '<option value="__none__" selected>none (no persona)</option>'
        '<option value="__random__">\U0001F3B2 random</option>'
        + optgroups_html
    )
    # Moderator persona select: built-in generic host / random host / roster.
    mod_persona_opts_html = (
        '<option value="__none__" selected>generic host (built-in)</option>'
        '<option value="__random__">\U0001F3B2 random host</option>'
        + optgroups_html
    )
    # Moderator CLI select: all CLIs (JS narrows this to non-debater CLIs).
    mod_cli_opts_html = "".join(
        f'<option value="{c}">{c}</option>' for c in _ORCH_CLI_IDS
    )

    persona_rows = "".join(
        f'<label class="orch-persona-row" data-cli="{c}">'
        f'<span class="cli-name">{c}</span>'
        f'<select name="persona-{c}">{persona_opts_html}</select>'
        f"</label>"
        for c in _ORCH_CLI_IDS
    )

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
      <span class="lbl">Personas <em style="color: var(--muted-2); font-weight: 400;">(optional)</em></span>
      <p class="hint">Assign a personality to each selected CLI. Each agent is spawned in
         character (persona woven into its opening prompt). Rows appear for checked CLIs only.</p>
      <button type="button" id="orch-cast-random" class="orch-cast-random">🎲 Cast all selected randomly</button>
      <div class="orch-persona-rows">
        {persona_rows}
      </div>
    </section>

    <section>
      <span class="lbl">Moderator / host <em style="color: var(--muted-2); font-weight: 400;">(optional)</em></span>
      <p class="hint">Adds a host that opens the debate, keeps turns on track, asks follow-ups,
         and wraps up — it does not argue a side. Runs on its <strong>own</strong> CLI (not one of
         the debaters), speaks first, then interjects each round. Adding a moderator keeps the
         conversation on orderly turn rotation.</p>
      <label class="orch-toggle">
        <input type="checkbox" name="mod_enable" />
        <span>Add a moderator</span>
      </label>
      <div class="orch-persona-rows" id="orch-mod-fields" style="display:none">
        <label class="orch-persona-row">
          <span class="cli-name">Runs on</span>
          <select name="mod_cli">{mod_cli_opts_html}</select>
        </label>
        <label class="orch-persona-row">
          <span class="cli-name">Host persona</span>
          <select name="mod_persona">{mod_persona_opts_html}</select>
        </label>
      </div>
    </section>

    <section>
      <span class="lbl">Launch</span>
      <label class="orch-toggle">
        <input type="checkbox" name="spawn" checked />
        <span>Spawn one CLI window per agent automatically (local Windows only)</span>
      </label>
      <label class="orch-toggle">
        <input type="checkbox" name="skip_permissions" checked />
        <span>Skip each CLI's tool-approval prompts (hands-off run)</span>
      </label>
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

<style>
  .orch-persona-rows {{ display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }}
  .orch-persona-row {{ display: flex; align-items: center; gap: 12px; }}
  .orch-persona-row .cli-name {{ min-width: 120px; }}
  .orch-persona-row select {{ flex: 1; }}
  .orch-cast-random {{ background: none; border: 1px solid var(--border, #ccc);
    border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 13px; }}
  .orch-toggle {{ display: flex; align-items: center; gap: 8px; margin: 4px 0;
    font-size: 13px; cursor: pointer; }}
  .orch-toggle input {{ width: auto; }}
</style>

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
  const personaRows = form.querySelectorAll('.orch-persona-row');
  const castRandomBtn = document.getElementById('orch-cast-random');
  const spawnToggle = form.querySelector('input[name=spawn]');
  const skipToggle = form.querySelector('input[name=skip_permissions]');
  const modEnable = form.querySelector('input[name=mod_enable]');
  const modFields = document.getElementById('orch-mod-fields');
  const modCli = form.querySelector('select[name=mod_cli]');
  const modPersona = form.querySelector('select[name=mod_persona]');
  const ALL_CLIS = Array.from(cliCheckboxes).map(cb => cb.value);

  // The moderator runs on its OWN CLI: show/hide the fields with the checkbox
  // and keep the CLI dropdown limited to CLIs not already checked as debaters.
  function updateModerator() {{
    const on = !!(modEnable && modEnable.checked);
    if (modFields) modFields.style.display = on ? 'flex' : 'none';
    if (!modCli) return;
    const debaters = new Set(
      Array.from(cliCheckboxes).filter(cb => cb.checked).map(cb => cb.value)
    );
    const free = ALL_CLIS.filter(c => !debaters.has(c));
    const prev = modCli.value;
    modCli.innerHTML = free.map(c => `<option value="${{c}}">${{c}}</option>`).join('');
    if (free.includes(prev)) modCli.value = prev;
    modCli.disabled = !on;
    if (modPersona) modPersona.disabled = !on;
  }}

  function personaSelectFor(cli) {{
    return form.querySelector('select[name="persona-' + cli + '"]');
  }}

  // Show a persona row only for a checked CLI; disable hidden ones so their
  // value isn't collected on submit.
  function updatePersonaRows() {{
    const checked = new Set(
      Array.from(cliCheckboxes).filter(cb => cb.checked).map(cb => cb.value)
    );
    personaRows.forEach(row => {{
      const on = checked.has(row.dataset.cli);
      row.style.display = on ? 'flex' : 'none';
      const sel = row.querySelector('select');
      if (sel) sel.disabled = !on;
    }});
  }}

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
  cliCheckboxes.forEach(cb => cb.addEventListener('change', () => {{
    updateFirstSpeaker();
    updatePersonaRows();
    updateModerator();
  }}));
  if (modEnable) modEnable.addEventListener('change', updateModerator);
  updateFirstSpeaker();
  updatePersonaRows();
  updateModerator();

  // "Cast all selected randomly" — set every visible persona select to random.
  if (castRandomBtn) {{
    castRandomBtn.addEventListener('click', () => {{
      Array.from(cliCheckboxes).filter(cb => cb.checked).forEach(cb => {{
        const sel = personaSelectFor(cb.value);
        if (sel) sel.value = '__random__';
      }});
    }});
  }}

  form.addEventListener('submit', async (ev) => {{
    ev.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = 'Running preflight…';
    errorPanel.classList.add('hidden');
    errorPanel.innerHTML = '';

    const fd = new FormData(form);
    const participants = fd.getAll('cli');
    const personas = {{}};
    participants.forEach(cli => {{
      const sel = personaSelectFor(cli);
      if (sel && !sel.disabled) personas[cli] = sel.value;
    }});
    const payload = {{
      topic: (fd.get('topic') || '').trim(),
      participants: participants,
      preset: fd.get('preset') || null,
      max_turns: parseInt(fd.get('max_turns'), 10) || null,
      first: fd.get('first') || null,
      kickoff: (fd.get('kickoff') || '').trim() || null,
      personas: personas,
      spawn: !!(spawnToggle && spawnToggle.checked),
      skip_permissions: !!(skipToggle && skipToggle.checked),
      moderator: (modEnable && modEnable.checked && modCli && modCli.value)
        ? {{ cli: modCli.value, persona: (modPersona ? modPersona.value : '__none__') }}
        : null,
    }};

    try {{
      const res = await fetch('/api/orchestrate', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload),
      }});
      const data = await res.json();
      if (data.ok) {{
        // If spawning couldn't happen (hosted / non-Windows / no pwsh), don't
        // silently redirect — the operator would wonder why no windows opened.
        const sp = data.spawn || {{}};
        if (sp.status === 'unavailable' || sp.status === 'error') {{
          let note = '<h4>Conversation #' + data.conversation_id + ' seeded — but agents were not spawned</h4>';
          note += '<p>' + escapeHtml(sp.detail || 'spawn unavailable') + '</p>';
          if (sp.manual) note += '<p>Launch them yourself: <code>' + escapeHtml(sp.manual) + '</code></p>';
          note += '<p><a href="/conversations/' + data.conversation_id + '">Open the conversation &rarr;</a></p>';
          errorPanel.innerHTML = note;
          errorPanel.classList.remove('hidden');
          submitBtn.disabled = false;
          submitBtn.textContent = 'Run preflight + start conversation';
          return;
        }}
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
