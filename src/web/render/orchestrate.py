"""The /orchestrate form page (local) and its hosted read-only explainer."""

from __future__ import annotations

import html
import json

from orchestrator import preflight as orch_preflight
from orchestrator import seats as orch_seats
from orchestrator.conv_types import CONV_TYPES, CONV_TYPE_KEYS, DEFAULT_CONV_TYPE
from presets import PRESETS, PRESET_NAMES

from web.assets import ORCHESTRATE_CSS, _ORCH_READONLY_CSS
from web.render.common import _layout


# Display order for the tools. Extra seats are interleaved after their own tool
# by ``_seat_order()``; anything preflight discovers that isn't listed here still
# renders (appended), so a newly supported CLI can't silently drop off the form.
_ORCH_CLI_IDS = ("claude-code", "codex", "antigravity", "kimi", "opencode", "gemini")

# Seats checked by default — a two-agent debate, the historical default.
_DEFAULT_CHECKED = ("claude-code", "codex")

_DEPRECATED_CLIS = ("gemini",)


def _type_blurb(key: str) -> str:
    """One-line description of a type's seat shape, for the radio label."""
    t = CONV_TYPES[key]
    lead = (f"a {t.lead_label.lower()} plus "
            if t.lead_required else
            f"optional {t.lead_label.lower()}, ")
    return (f"{lead}{t.min_members}–{t.max_members} "
            f"{t.members_label.lower()}")


def _seat_order(available: list[str]) -> list[str]:
    """Discovered seats in display order: registry order, seats within a tool."""
    ranked = {cli: i for i, cli in enumerate(_ORCH_CLI_IDS)}
    return sorted(
        available,
        key=lambda s: (ranked.get(orch_seats.seat_cli(s) or s, len(ranked)),
                       orch_seats.seat_index(s), s),
    )


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
    seat_ids = _seat_order(list(preflight_by_cli)) or list(_ORCH_CLI_IDS)

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
    # Moderator seat select: every seat (JS narrows it to unchecked ones).
    mod_cli_opts_html = "".join(
        f'<option value="{html.escape(s, quote=True)}">{html.escape(s)}</option>'
        for s in seat_ids
    )

    persona_rows = "".join(
        f'<label class="orch-persona-row" data-cli="{html.escape(s, quote=True)}">'
        f'<span class="cli-name">{html.escape(s)}</span>'
        f'<select name="persona-{html.escape(s, quote=True)}">{persona_opts_html}</select>'
        f"</label>"
        for s in seat_ids
    )

    # One checkbox per configured seat. Extra seats ('codex-2') are marked so
    # it's obvious they're a second window of a tool already in the list.
    def _seat_checkbox(s: str) -> str:
        checked = " checked" if s in _DEFAULT_CHECKED else ""
        note = ""
        if orch_seats.seat_index(s) > 1:
            note = (' <em style="color: var(--muted-2); font-weight: 400;">'
                    f'(2nd seat)</em>' if orch_seats.seat_index(s) == 2 else
                    ' <em style="color: var(--muted-2); font-weight: 400;">'
                    f'(seat {orch_seats.seat_index(s)})</em>')
        elif s in _DEPRECATED_CLIS:
            note = (' <em style="color: var(--muted-2); font-weight: 400;">'
                    '(deprecated)</em>')
        return (
            '<label class="orch-cli">'
            f'<input type="checkbox" name="cli" value="{html.escape(s, quote=True)}"{checked} />'
            f'<span class="cli-name">{html.escape(s)}{note}</span>'
            f"{_status_html(s)}"
            "</label>"
        )

    cli_checkboxes = "".join(_seat_checkbox(s) for s in seat_ids)

    # Conversation-type radios, generated from the registry so a new type needs
    # no edit here. Each carries the seat rules the JS enforces client-side.
    type_radios = "".join(
        '<label class="orch-type">'
        f'<input type="radio" name="conv_type" value="{key}"'
        f'{" checked" if key == DEFAULT_CONV_TYPE else ""} />'
        f'<span class="cli-name">{html.escape(CONV_TYPES[key].label)}</span>'
        f'<span class="orch-type-hint">{html.escape(_type_blurb(key))}</span>'
        "</label>"
        for key in CONV_TYPE_KEYS
    )
    js_conv_types = json.dumps({
        key: {
            "label": t.label,
            "leadRole": t.lead_role,
            "leadLabel": t.lead_label,
            "leadRequired": t.lead_required,
            "memberLabel": t.member_label,
            "membersLabel": t.members_label,
            "minMembers": t.min_members,
            "maxMembers": t.max_members,
            "defaultPreset": t.default_preset,
        }
        for key, t in CONV_TYPES.items()
    })

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
      <span class="lbl">Format</span>
      <p class="hint">What kind of room this is — who each seat is for. Separate from
         the preset below, which sets the tone.</p>
      <div class="orch-types">
        {type_radios}
      </div>
    </section>

    <section>
      <span class="lbl" id="orch-participants-label">Participants <em style="color: var(--muted-2); font-weight: 400;">(min 2)</em></span>
      <p class="hint">One CLI process per seat, five seats max. Status reflects this machine's
         MCP config at page load; re-checked server-side on submit. A seat past the first on the
         same tool comes from <code>scripts/setup/add_agent_seat.py</code>.</p>
      <div class="orch-clis">
        {cli_checkboxes}
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
      <p class="hint">Assign a personality to each selected seat. Each agent is spawned in
         character (persona woven into its opening prompt). Rows appear for checked seats only.</p>
      <button type="button" id="orch-cast-random" class="orch-cast-random">🎲 Cast all selected randomly</button>
      <div class="orch-persona-rows">
        {persona_rows}
      </div>
    </section>

    <section>
      <span class="lbl" id="orch-lead-label">Moderator / host <em style="color: var(--muted-2); font-weight: 400;">(optional)</em></span>
      <p class="hint" id="orch-lead-hint">Adds a host that opens the debate, keeps turns on track, asks follow-ups,
         and wraps up — it does not argue a side. Runs on its <strong>own</strong> seat (not one of
         the debaters), speaks first, then interjects each round. Adding a moderator keeps the
         conversation on orderly turn rotation.</p>
      <label class="orch-toggle" id="orch-mod-toggle">
        <input type="checkbox" name="mod_enable" />
        <span id="orch-mod-toggle-text">Add a moderator</span>
      </label>
      <div class="orch-persona-rows" id="orch-mod-fields" style="display:none">
        <label class="orch-persona-row">
          <span class="cli-name">Runs on</span>
          <select name="mod_cli">{mod_cli_opts_html}</select>
        </label>
        <label class="orch-persona-row">
          <span class="cli-name" id="orch-mod-persona-label">Host persona</span>
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
  /* Format picker — one card per conversation type. */
  .orch-types {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }}
  .orch-type {{ display: flex; align-items: baseline; gap: 8px; flex: 1 1 220px;
                padding: 10px 12px; border: 1px solid var(--border, #ccc);
                border-radius: 8px; cursor: pointer; }}
  .orch-type input {{ width: auto; }}
  .orch-type:has(input:checked) {{ border-color: #10b981;
                                   background: rgba(16,185,129,0.07); }}
  .orch-type-hint {{ font-size: 12px; color: var(--muted-2, #71717a); }}
</style>

<script>
(function() {{
  const presetDefaults = {js_presets};
  const convTypes = {js_conv_types};
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
  const typeRadios = form.querySelectorAll('input[name=conv_type]');
  const partsLabel = document.getElementById('orch-participants-label');
  const leadLabel = document.getElementById('orch-lead-label');
  const leadHint = document.getElementById('orch-lead-hint');
  const modToggle = document.getElementById('orch-mod-toggle');
  const modToggleText = document.getElementById('orch-mod-toggle-text');
  const modPersonaLabel = document.getElementById('orch-mod-persona-label');
  const ALL_CLIS = Array.from(cliCheckboxes).map(cb => cb.value);

  function currentType() {{
    const picked = Array.from(typeRadios).find(r => r.checked);
    return convTypes[picked ? picked.value : ''] ? picked.value : 'debate';
  }}

  // Re-label the form for the chosen format and force the lead seat on for a
  // type that requires one (a podcast without a host is not a podcast). The
  // server re-validates all of this — see orchestrator/conv_types.py.
  function updateConvType() {{
    const key = currentType();
    const t = convTypes[key];
    if (!t) return;
    if (partsLabel) {{
      partsLabel.innerHTML = t.membersLabel +
        ' <em style="color: var(--muted-2); font-weight: 400;">(' +
        t.minMembers + '\\u2013' + t.maxMembers + ')</em>';
    }}
    if (leadLabel) {{
      leadLabel.innerHTML = t.leadLabel + (t.leadRequired
        ? ' <em style="color: var(--muted-2); font-weight: 400;">(required)</em>'
        : ' <em style="color: var(--muted-2); font-weight: 400;">(optional)</em>');
    }}
    if (modToggleText) modToggleText.textContent = 'Add a ' + t.leadLabel.toLowerCase();
    if (modPersonaLabel) modPersonaLabel.textContent = t.leadLabel + ' persona';
    if (leadHint) {{
      leadHint.innerHTML = t.leadRequired
        ? 'The ' + t.leadLabel.toLowerCase() + ' runs the room: opens the show, asks the ' +
          'questions, brings in quiet ' + t.membersLabel.toLowerCase() + ', and closes. It does ' +
          'not answer its own questions. Runs on its <strong>own</strong> seat and speaks first.'
        : 'Adds a host that opens the debate, keeps turns on track, asks follow-ups, and ' +
          'wraps up \\u2014 it does not argue a side. Runs on its <strong>own</strong> seat ' +
          '(not one of the debaters), speaks first, then interjects each round.';
    }}
    if (modEnable && t.leadRequired) {{
      modEnable.checked = true;
      modEnable.disabled = true;
      if (modToggle) modToggle.style.opacity = '0.65';
    }} else if (modEnable) {{
      modEnable.disabled = false;
      if (modToggle) modToggle.style.opacity = '';
    }}
    // Nudge the matching preset, but never fight an explicit choice.
    if (presetSelect && t.defaultPreset && !presetSelect.dataset.touched) {{
      const opt = Array.from(presetSelect.options).find(o => o.value === t.defaultPreset);
      if (opt) {{
        presetSelect.value = t.defaultPreset;
        const d = presetDefaults[t.defaultPreset];
        if (d && maxTurns) maxTurns.value = d.max_turns;
      }}
    }}
    updateModerator();
  }}

  // The lead runs on its OWN seat: show/hide the fields with the checkbox and
  // keep the seat dropdown limited to seats not already checked as members.
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
    presetSelect.dataset.touched = '1';
    const d = presetDefaults[presetSelect.value];
    if (d) maxTurns.value = d.max_turns;
  }});
  cliCheckboxes.forEach(cb => cb.addEventListener('change', () => {{
    updateFirstSpeaker();
    updatePersonaRows();
    updateModerator();
  }}));
  typeRadios.forEach(r => r.addEventListener('change', updateConvType));
  if (modEnable) modEnable.addEventListener('change', updateModerator);
  updateFirstSpeaker();
  updatePersonaRows();
  updateConvType();

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
      conv_type: currentType(),
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
    return _layout("Orchestrate", "", body,
                   head_extras=f"<style>{ORCHESTRATE_CSS}</style>",
                   active="orchestrate")

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
        active="orchestrate",
    )
