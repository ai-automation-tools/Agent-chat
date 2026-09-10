"""The /setup page (local) and its hosted read-only explainer.

"Which CLI tools do you have?" — the question the app used to never ask, and
then answered wrongly on the operator's behalf by offering all of them. See
:mod:`orchestrator.availability` for the model: detect, let them override,
persist.
"""

from __future__ import annotations

import html

from orchestrator import availability as avail
from orchestrator import seats as orch_seats

from web.assets import ORCHESTRATE_CSS, SETUP_CSS, _ORCH_READONLY_CSS
from web.render.common import _layout

_DOCS = "https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/CLI-MCP-Config"

# Display name + where to get it, per tool. The per-CLI registration doc is the
# answer to "it's installed but the config check fails".
_CLI_META: dict[str, tuple[str, str, str]] = {
    # cli -> (display name, vendor, install/home URL)
    "claude-code": ("Claude Code", "Anthropic", "https://github.com/anthropics/claude-code"),
    "codex": ("Codex CLI", "OpenAI", "https://github.com/openai/codex"),
    "antigravity": ("Antigravity", "Google", "https://antigravity.google"),
    "opencode": ("OpenCode", "SST", "https://github.com/sst/opencode"),
    "gemini": ("Gemini CLI", "Google", "https://github.com/google-gemini/gemini-cli"),
}

_DOC_SLUG = {
    "claude-code": "claude.md",
    "codex": "codex.md",
    "antigravity": "antigravity.md",
    "opencode": "opencode.md",
    "gemini": "gemini.md",
}


def _status_row(s: avail.CliStatus) -> str:
    """One tool: a tick the operator owns, plus the two probe results."""
    name, vendor, home = _CLI_META.get(s.cli, (s.cli, "", ""))
    checked = " checked" if s.available else ""
    bin_names = " / ".join(s.binaries)
    if s.detected:
        bin_html = (
            '<span class="su-pill ok" title="'
            + html.escape(str(s.binary_path), quote=True)
            + '">on PATH</span>'
        )
    else:
        bin_html = f'<span class="su-pill off">no <code>{html.escape(bin_names)}</code></span>'
    if s.config_ok:
        cfg_html = '<span class="su-pill ok">MCP config OK</span>'
    else:
        cfg_html = (
            '<span class="su-pill warn">MCP config '
            f'{html.escape(s.failure_code or "failed")}</span>'
        )
    detail = ""
    if not s.config_ok and s.failure_detail:
        doc = f"{_DOCS}/Per-CLI/{_DOC_SLUG.get(s.cli, 'README.md')}"
        detail = (
            '<p class="su-detail">'
            f"{html.escape(s.failure_detail)} "
            f'<a href="{doc}" target="_blank" rel="noopener noreferrer">'
            "How to register it &#8599;</a></p>"
        )
    dep = ' <em class="su-dep">deprecated</em>' if s.deprecated else ""
    return (
        f'<div class="su-row" data-cli="{html.escape(s.cli, quote=True)}">'
        '<label class="su-main">'
        f'<input type="checkbox" name="cli" value="{html.escape(s.cli, quote=True)}"{checked}>'
        '<span class="su-names">'
        f'<span class="su-name">{html.escape(name)}{dep}</span>'
        f'<span class="su-sub">{html.escape(vendor)} &middot; '
        f'<code>{html.escape(s.cli)}</code></span>'
        "</span>"
        f'<span class="su-pills">{bin_html}{cfg_html}</span>'
        "</label>"
        f"{detail}"
        f'<p class="su-links">'
        f'<a href="{home}" target="_blank" rel="noopener noreferrer">Get {html.escape(name)} &#8599;</a>'
        "</p>"
        "</div>"
    )


def _render_setup(statuses: list[avail.CliStatus], declared: bool) -> str:
    """GET /setup on a local instance."""
    rows = "".join(_status_row(s) for s in statuses)
    n_avail = sum(1 for s in statuses if s.available)
    max_seats = orch_seats.MAX_SEATS_PER_CLI

    intro_state = (
        "Saved &mdash; this is what the rest of the app offers you."
        if declared else
        "Nothing saved yet, so the ticks below are just what was <em>detected</em>. "
        "Correct them and save."
    )

    body = f"""
<div class="orch-shell su-shell">
  <header class="orch-head">
    <h2>Which CLI tools do you have?</h2>
    <p>Agent-Chat doesn't need all five. It needs <strong>one</strong> &mdash; a seat is
       configuration, not a program, so a single install can argue with itself. Tick what
       you actually have and everything else in the app (the orchestrate form, the
       launcher, the seat planner) will offer only those. {intro_state}</p>
  </header>

  <form id="su-form" class="orch-form">
    <section>
      <span class="lbl">Your CLIs</span>
      <p class="hint">Two probes per tool: is the launcher binary on your <code>PATH</code>,
         and does its <code>agent_chat</code> MCP entry pass preflight. Your tick wins over
         both &mdash; check a tool you're about to install, uncheck one you'll never use.</p>
      <div class="su-rows">{rows}</div>
    </section>

    <section>
      <span class="lbl">What that gives you</span>
      <div class="su-plan" id="su-plan"></div>
    </section>

    <div id="su-error" class="orch-error hidden"></div>

    <button type="submit" class="orch-submit">Save my CLI setup</button>
    <p class="hint su-foot">Stored in <code>config/available-clis.json</code> (gitignored,
       this machine only). Nothing here installs anything or edits your CLI configs &mdash;
       when a tool needs registering, follow its
       <a href="{_DOCS}/README.md" target="_blank" rel="noopener noreferrer">MCP setup doc &#8599;</a>.</p>
  </form>
</div>

<script>
(function() {{
  const MAX_SEATS = {max_seats};
  const form = document.getElementById('su-form');
  const submitBtn = form.querySelector('button[type=submit]');
  const errorPanel = document.getElementById('su-error');
  const planBox = document.getElementById('su-plan');
  const boxes = Array.from(form.querySelectorAll('input[name=cli]'));

  function esc(s) {{
    return String(s).replace(/[&<>"']/g, c => (
      {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]
    ));
  }}

  // Same round-robin as orchestrator.availability.plan_seats — one seat per
  // tool, then a second on each. Mirrored here only to preview the plan; the
  // server plans for real when a conversation is seeded.
  function planSeats(clis, count) {{
    const out = [];
    let idx = 1;
    while (out.length < count && idx <= MAX_SEATS) {{
      for (const c of clis) {{
        if (out.length >= count) break;
        out.push(idx === 1 ? c : c + '-' + idx);
      }}
      idx++;
    }}
    return out;
  }}

  function chosen() {{ return boxes.filter(b => b.checked).map(b => b.value); }}

  function renderPlan() {{
    const clis = chosen();
    if (!clis.length) {{
      planBox.innerHTML = '<p class="su-plan-none">No CLIs ticked. With none, there\\'s ' +
        'nothing to seed a conversation with &mdash; install one and come back, or tick ' +
        'the one you already have.</p>';
      return;
    }}
    const two = planSeats(clis, 2);
    const three = planSeats(clis, 3);
    const extra = two.concat(three).filter((s, i, a) =>
      a.indexOf(s) === i && /-[2-9]$/.test(s));
    let html = '<p class="su-plan-lead"><strong>' + clis.length + '</strong> CLI' +
      (clis.length === 1 ? '' : 's') + ' available.</p>' +
      '<ul class="su-plan-list">' +
      '<li><span class="su-plan-k">2-agent debate</span>' +
        '<span class="su-seatline">' + two.map(s => '<code>' + esc(s) + '</code>').join(
          ' <span class="su-vs">vs</span> ') + '</span></li>' +
      '<li><span class="su-plan-k">3-agent debate</span>' +
        '<span class="su-seatline">' + three.map(s => '<code>' + esc(s) + '</code>').join(
          ' <span class="su-vs">&middot;</span> ') + '</span></li>' +
      '</ul>';
    if (clis.length === 1) {{
      html += '<p class="su-plan-note">One tool is fine: seat 1 keeps the bare id and ' +
        'each extra seat gets its own config folder passing its own <code>--agent-id</code>. ' +
        'Two instances of the same CLI, two personas, one debate.</p>';
    }}
    if (extra.length) {{
      html += '<div class="su-seats" id="su-seats" data-seats="' +
        esc(extra.join(',')) + '">' +
        '<p>Those runs need seat folders that don\\'t exist yet: ' +
        extra.map(s => '<code>' + esc(s) + '</code>').join(', ') + '. ' +
        'Each is a copy of seat 1\\'s MCP config with the agent id rewritten.</p>' +
        '<button type="button" class="btn su-mkseats">Create the missing seat folders</button>' +
        '<span class="su-seats-msg"></span></div>';
    }}
    planBox.innerHTML = html;
    // Only offer creation for seats that are genuinely absent.
    const box = document.getElementById('su-seats');
    if (box) refreshSeats(box);
  }}

  async function refreshSeats(box) {{
    const want = box.dataset.seats.split(',').filter(Boolean);
    try {{
      const res = await fetch('/api/setup');
      const data = await res.json();
      const missing = want.filter(s => (data.missing_seats || []).includes(s) ||
                                        !(data.existing_seats || []).includes(s));
      if (!missing.length) {{ box.remove(); return; }}
      box.dataset.seats = missing.join(',');
    }} catch (_) {{ /* leave the button; the POST reports the real outcome */ }}
  }}

  planBox.addEventListener('click', async (ev) => {{
    const btn = ev.target.closest('.su-mkseats');
    if (!btn) return;
    const box = btn.closest('.su-seats');
    const msg = box.querySelector('.su-seats-msg');
    btn.disabled = true;
    msg.textContent = 'Creating\\u2026';
    try {{
      const res = await fetch('/api/setup/seats', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{seats: box.dataset.seats.split(',').filter(Boolean)}}),
      }});
      const data = await res.json();
      if (data.ok) {{
        msg.className = 'su-seats-msg ok';
        msg.textContent = 'Created: ' + (data.created || []).join(', ');
        if (data.notes && data.notes.length) {{
          const p = document.createElement('p');
          p.className = 'su-plan-note';
          p.textContent = data.notes.join(' ');
          box.appendChild(p);
        }}
        btn.remove();
      }} else {{
        msg.className = 'su-seats-msg fail';
        msg.textContent = data.error || 'Could not create the seats.';
        btn.disabled = false;
      }}
    }} catch (err) {{
      msg.className = 'su-seats-msg fail';
      msg.textContent = String(err);
      btn.disabled = false;
    }}
  }});

  boxes.forEach(b => b.addEventListener('change', renderPlan));
  renderPlan();

  form.addEventListener('submit', async (ev) => {{
    ev.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving\\u2026';
    errorPanel.classList.add('hidden');
    try {{
      const res = await fetch('/api/setup', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{available: chosen()}}),
      }});
      const data = await res.json();
      if (data.ok) {{
        submitBtn.textContent = 'Saved \\u2713';
        setTimeout(() => {{
          submitBtn.disabled = false;
          submitBtn.textContent = 'Save my CLI setup';
        }}, 1600);
        return;
      }}
      errorPanel.innerHTML = '<h4>Not saved</h4><p>' + esc(data.error || 'Unknown error') + '</p>';
      errorPanel.classList.remove('hidden');
    }} catch (err) {{
      errorPanel.innerHTML = '<h4>Network error</h4><p>' + esc(String(err)) + '</p>';
      errorPanel.classList.remove('hidden');
    }} finally {{
      if (submitBtn.textContent === 'Saving\\u2026') {{
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save my CLI setup';
      }}
    }}
  }});
}})();
</script>
"""
    return _layout(
        "CLI setup", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style><style>{SETUP_CSS}</style>",
        active="setup",
    )


def _render_setup_readonly() -> str:
    """Hosted /setup — the question only has an answer on your own machine."""
    body = """
<div class="orch-shell">
  <header class="orch-head">
    <h2>CLI setup happens on your machine</h2>
    <p>This hosted site is a <strong>read-only demo</strong>. It has no CLI tools, no
       <code>PATH</code> to probe, and nothing to save &mdash; which CLIs you have is a
       fact about your own computer, so this page only does something on a local
       instance.</p>
  </header>

  <div class="orch-ro-card">
    <h3>You need exactly one CLI to start</h3>
    <p>Claude Code, Codex, Antigravity or OpenCode &mdash; any one of them. A
       participant seat is configuration rather than a separate program, so a single
       install can hold both chairs in a debate: <code>claude-code</code> against
       <code>claude-code-2</code>, two personas, one tool.</p>
  </div>

  <div class="orch-ro-card">
    <h3>Then run this page locally</h3>
    <pre><code>.\\.venv\\Scripts\\python.exe src\\web_ui.py
# then open http://127.0.0.1:8765/setup</code></pre>
    <p>It probes each tool (binary on <code>PATH</code>, MCP config valid), lets you
       correct the result, and remembers the answer.</p>
  </div>

  <p class="orch-ro-foot">Registration snippets per CLI are in the
    <a href="https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/CLI-MCP-Config/README.md"
       target="_blank" rel="noopener noreferrer">MCP config reference</a>,
    or start from the
    <a href="https://github.com/ai-automation-tools/Agent-chat#readme" target="_blank" rel="noopener noreferrer">README</a>.</p>
</div>
"""
    return _layout(
        "CLI setup", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style>{_ORCH_READONLY_CSS}",
        active="setup",
    )
