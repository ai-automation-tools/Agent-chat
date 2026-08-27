"""The /orchestrate form page (local) and its hosted read-only explainer."""

from __future__ import annotations

import html
import json

from orchestrator import delivery as orch_delivery
from orchestrator import preflight as orch_preflight
from orchestrator import seats as orch_seats
from orchestrator.conv_types import CONV_TYPES, CONV_TYPE_KEYS, DEFAULT_CONV_TYPE
from presets import (PRESETS, PRESET_NAMES, deliverable_for, preset_label,
                     presets_for)

from web.assets import ORCHESTRATE_CSS, _ORCH_READONLY_CSS
from web.render.common import GITHUB_URL as _REPO, _layout


# Display order for the tools. Extra seats are interleaved after their own tool
# by ``_seat_order()``; anything preflight discovers that isn't listed here still
# renders (appended), so a newly supported CLI can't silently drop off the form.
_ORCH_CLI_IDS = ("claude-code", "codex", "antigravity", "opencode", "gemini")

# Seats checked by default — a two-agent debate, the historical default.
_DEFAULT_CHECKED = ("claude-code", "codex")

_DEPRECATED_CLIS = ("gemini",)


# What the lead seat is for, in the operator's words. Keyed by conv_type with
# a generic fallback, so a type added to the registry renders something sane
# here before anyone writes it copy. UI wording lives here rather than on
# ConvType — the registry is the domain model, not the phrasebook.
_LEAD_HINTS: dict[str, str] = {
    "debate": (
        "Adds a host that opens the debate, keeps turns on track, asks "
        "follow-ups, and wraps up \u2014 it does not argue a side. Runs on its "
        "<strong>own</strong> seat (not one of the debaters), speaks first, "
        "then interjects each round."
    ),
    "podcast": (
        "The host runs the room: opens the show, asks the questions, brings in "
        "quiet guests, and closes. It does not answer its own questions. Runs "
        "on its <strong>own</strong> seat and speaks first."
    ),
    # No entry for `collaborate` on purpose: its facilitator is one of the
    # collaborators (ConvType.lead_needs_own_seat=False), so this whole section
    # is hidden for it and any copy here would be unreachable and go stale.
    # What the facilitator does is said next to the First speaker field instead
    # — see `firstHint` in the JS payload below.
}


def _lead_hint(key: str) -> str:
    """Operator-facing description of a type's lead seat."""
    t = CONV_TYPES[key]
    return _LEAD_HINTS.get(key) or (
        f"The {t.lead_label.lower()} holds the lead seat: it speaks first and "
        f"runs on its <strong>own</strong> seat, not one of the "
        f"{t.members_label.lower()}."
    )


def _type_blurb(key: str) -> str:
    """One-line description of a type's seat shape, for the radio label."""
    t = CONV_TYPES[key]
    if t.lead_required and not t.lead_needs_own_seat:
        # The lead is one of them, so quoting a member range on top of a lead
        # would read as one seat more than the operator actually picks.
        return (f"{t.min_participants}–{t.max_participants} "
                f"{t.members_label.lower()}; the first speaks as "
                f"{t.lead_label.lower()}")
    lead = (f"a {t.lead_label.lower()} plus "
            if t.lead_required else
            f"optional {t.lead_label.lower()}, ")
    return (f"{lead}{t.min_members}–{t.max_members} "
            f"{t.members_label.lower()}")


# What each sub-type hands back, in the operator's words — the whole point of
# picking one, so it belongs on the card rather than in a doc. Keyed by preset
# name with a generic fallback, so a preset added to `presets.py` renders
# something sane here before anyone writes it copy.
_PRESET_BLURBS: dict[str, str] = {
    "debate": "Positions argued and pushed on.",
    "podcast": "A host interviews; guests answer at length.",
    "collaborate": "Whatever you asked for, written out in full.",
    "brainstorm": "A ranked shortlist — and what got dropped.",
    "plan": "Numbered steps, owners, definition of done.",
    "decide": "The call — plus why every other option lost.",
    "solve": "Root cause, the evidence for it, and the fix.",
    "code-review": "A verdict, with blocking issues kept separate.",
    "audit": "A ranked findings register — issues and enhancements.",
    "design": "Components, interfaces, and the tradeoffs taken.",
    "validate": "Go / no-go, and the thing most likely to kill it.",
}


# The long form of each sub-type, behind the card's "?" button. The card has
# room for one line; this is where "which one of these is mine?" actually gets
# answered, so each entry says what you hand IN, what comes back, and — the
# part a one-liner can never carry — which neighbouring sub-type to pick
# instead. Kept next to `_PRESET_BLURBS` rather than in a doc because an
# operator decides here, mid-form, and a link they have to leave the page for
# is a link they don't click. Trusted HTML authored in this file (never
# escaped at render time) — keep it to <strong>/<em>/<code>.
_PRESET_DETAILS: dict[str, str] = {
    "": (
        "Nothing is rendered for the agents at all — no tone, no "
        "deliverable instruction, no participation loop. You get a bare "
        "conversation row and paste your own opening prompt into each CLI. "
        "Pick this when you have a brief that is already written and don't "
        "want a template wrapped around it."
    ),
    "debate": (
        "<strong>Give it</strong> a proposition or a question with real sides "
        "to it. <strong>Get back</strong> a transcript, not an artifact — "
        "a debate exists to be read. Agents are told to take positions, make "
        "falsifiable predictions, and push back rather than converge, so "
        "don't pick it when you want the room to agree on something."
    ),
    "podcast": (
        "<strong>Give it</strong> a subject and a guest list. "
        "<strong>Get back</strong> an interview transcript: the host asks and "
        "never argues a side, the guests answer at length with specifics and "
        "stories. Longer default run (10 turns each) because answers are "
        "supposed to breathe."
    ),
    "collaborate": (
        "The generic flavour — <strong>the room does exactly what your "
        "topic asks and hands that back written out in full</strong>, not a "
        "summary of the discussion. Pick it when your topic already names the "
        "artifact you want, or when none of the specific sub-types fits. "
        "Everything else on this list is this one with sharper instructions "
        "about the shape of the output."
    ),
    "brainstorm": (
        "<strong>Give it</strong> a space to explore. <strong>Get back</strong> "
        "a ranked shortlist plus the ideas that were dropped and why. Runs in "
        "<code>continuous</code> mode on purpose: nobody waits for a turn "
        "while an idea is fresh, and the facilitator converges the room near "
        "the end. Use <strong>Decide</strong> instead when the options already "
        "exist and you just need to choose."
    ),
    "plan": (
        "<strong>Give it</strong> a goal you have already committed to. "
        "<strong>Get back</strong> numbered steps, each with an owner, what it "
        "depends on, and a definition of done, plus the risks and open "
        "unknowns. It plans the <em>work</em> — for the shape of the "
        "thing being built, pick <strong>Design</strong>."
    ),
    "decide": (
        "<strong>Give it</strong> the options, or a question with obvious "
        "candidates. <strong>Get back</strong> one committed choice, the "
        "criteria it was judged against, <strong>every option that lost and "
        "why</strong>, and what would have to change to flip it. Prioritising "
        "a backlog is this sub-type with the options supplied."
    ),
    "solve": (
        "<strong>Give it</strong> a symptom — something is broken or "
        "behaving wrong. <strong>Get back</strong> the root cause, the "
        "evidence for it, the fix, and the hypotheses that were ruled out. "
        "Agents are told to eliminate rather than accumulate and not to jump "
        "to a fix. One known problem, not a sweep for unknown ones — "
        "that's <strong>Audit</strong>."
    ),
    "code-review": (
        "<strong>Give it</strong> one artifact under review — a diff, a "
        "proposal, a document. <strong>Get back</strong> an explicit approve / "
        "request-changes verdict, then blocking issues as a numbered list, "
        "then non-blocking suggestions kept separate. Shortest default run (6 "
        "turns each). For a whole repo or system with no verdict to give, use "
        "<strong>Audit</strong>."
    ),
    "audit": (
        "<strong>Give it</strong> something that already exists and a lens to "
        "look through — a repo, a pipeline, a set of docs, a body of "
        "data. Agents examine it <strong>independently first</strong>, then "
        "reconcile: agreed findings, contested ones, and what one of them "
        "missed. <strong>Get back</strong> a findings register ranked by "
        "impact — defects and enhancements kept distinguishable, each "
        "with where it is, the evidence, and the recommended change — "
        "opening with what was and wasn't examined. This is the one for "
        "“go through my project and tell me what's wrong and what could "
        "be better”. It <em>finds</em> the work; run <strong>Plan</strong> "
        "afterwards to schedule it."
    ),
    "design": (
        "<strong>Give it</strong> requirements or constraints. "
        "<strong>Get back</strong> the design itself: components and what each "
        "owns, the interfaces between them, the data crossing them, and the "
        "failure modes — with the rejected alternative named for every "
        "significant choice. Structure, not schedule; pair it with "
        "<strong>Plan</strong> for the build order."
    ),
    "validate": (
        "<strong>Give it</strong> an idea, a pitch, or a plan you are about to "
        "commit to. <strong>Get back</strong> a go / no-go / not-yet call "
        "covering demand, competition, cost to run, and the assumptions "
        "underneath — plus the single thing most likely to kill it and "
        "the cheapest test that would find out. Someone is required to argue "
        "the case against."
    ),
}


def _preset_detail(name: str) -> str:
    """Long-form help for a sub-type card; '' when none is written."""
    return _PRESET_DETAILS.get(name, "")


def _preset_blurb(name: str) -> str:
    """One line on what this sub-type produces."""
    return _PRESET_BLURBS.get(name) or deliverable_for(name)[:70] or ""


def _preset_meta(name: str) -> str:
    """The mode/turn defaults, shown so a switch isn't a surprise."""
    p = PRESETS[name]
    return f'{p["mode"]}/{p["max_turns"]} turns'


def _preset_help(name: str, label: str) -> str:
    """The card's "?" and the tooltip it reveals on hover.

    Pure CSS: the panel is a sibling shown by ``:hover``/``:focus-visible`` on
    the button, absolutely positioned so it **floats over** the card rather
    than growing it — an expanding panel reflowed the whole grid, which is a
    lot of movement for a glance. The button stays a real <button> so it is
    keyboard-reachable, and the JS cancels a click on it: it sits inside the
    card's <label>, and reading about a sub-type must not select it.
    """
    detail = _preset_detail(name)
    if not detail:
        return ""
    safe = html.escape(label or "this sub-type", quote=True)
    slug = html.escape(name or "none", quote=True)
    return (
        f'<button type="button" class="orch-preset-help"'
        f' aria-describedby="orch-help-{slug}" aria-label="What is {safe}?">?</button>'
        f'<span class="orch-preset-detail" id="orch-help-{slug}" role="tooltip">'
        f'{detail}</span>'
    )


def _preset_radio(name: str) -> str:
    """One sub-type card. Hidden by the JS when its format isn't selected."""
    label = preset_label(name)
    return (
        f'<label class="orch-preset" data-preset="{html.escape(name, quote=True)}">'
        f'<input type="radio" name="preset" value="{html.escape(name, quote=True)}" />'
        f'<span class="orch-preset-name">{html.escape(label)}</span>'
        f'<span class="orch-preset-hint">{html.escape(_preset_blurb(name))}</span>'
        f'<span class="orch-preset-meta">{html.escape(_preset_meta(name))}</span>'
        f'{_preset_help(name, label)}'
        "</label>"
    )


def _seat_order(available: list[str]) -> list[str]:
    """Discovered seats in display order: registry order, seats within a tool."""
    ranked = {cli: i for i, cli in enumerate(_ORCH_CLI_IDS)}
    return sorted(
        available,
        key=lambda s: (ranked.get(orch_seats.seat_cli(s) or s, len(ranked)),
                       orch_seats.seat_index(s), s),
    )


def _availability_notice(availability: dict | None, seat_ids: list[str]) -> str:
    """The banner above the participant list, or ``""`` when there's nothing to say.

    Three states worth interrupting for, in descending order of urgency: no CLI
    at all (the form can't do anything), exactly one seat (it can seed a
    conversation with nobody to talk to), and never-declared (the list below is
    a guess from detection, not an answer). A settled two-plus-seat setup gets
    silence — the point of the setup page is to stop nagging people who are set up.
    """
    if availability is None:
        return ""
    clis = list(availability.get("clis") or [])
    declared = bool(availability.get("declared"))
    if not clis:
        return (
            '<div class="orch-avail warn">'
            "<strong>No CLI tools available.</strong> Nothing was detected on your "
            "<code>PATH</code> and you haven't declared anything, so there's no one to "
            'seed a conversation with. <a href="/setup">Set up your CLIs &rarr;</a>'
            "</div>"
        )
    if len(seat_ids) < 2:
        return (
            '<div class="orch-avail warn">'
            f"<strong>Only one seat available.</strong> A conversation needs at least two. "
            f"You have <code>{html.escape(clis[0])}</code> — one tool is enough, but it "
            f"needs a second seat to argue with itself. "
            '<a href="/setup">Create one on the setup page &rarr;</a>'
            "</div>"
        )
    if not declared:
        return (
            '<div class="orch-avail">'
            f"Showing the <strong>{len(clis)}</strong> CLI"
            f"{'' if len(clis) == 1 else 's'} detected on this machine. "
            '<a href="/setup">Confirm or correct that &rarr;</a>'
            "</div>"
        )
    return ""


def _delivery_toggle_html() -> str:
    """The *save a copy locally* control for the Launch section.

    Three states, because pretending there are fewer would lie about one of
    them (see orchestrator.delivery.optin_offered):

    - delivery off        → a muted hint, no control. Discoverable without
                            implying a choice that does nothing.
    - a sink scoped "all" → ticked and disabled. Every conversation is
                            delivered whatever the operator clicks, so the box
                            must not suggest otherwise.
    - scoped "opt-in"     → a live checkbox. This is the interesting case, and
                            the one `deliver --init` now ships by default.
    """
    state = orch_delivery.optin_offered()
    if not state["available"]:
        return (
            '<p class="hint" id="orch-deliver-off">Local delivery is off — finished '
            'conversations stay in the database. Turn it on with '
            '<code>inspect_conversations deliver --init</code> '
            '(see <code>docs/App/delivery.md</code>).</p>'
        )
    label = html.escape(state["label"])
    if state["forced"]:
        return (
            '<label class="orch-toggle" id="orch-deliver-toggle">'
            '<input type="checkbox" name="deliver_locally" checked disabled />'
            f'<span>Deliver a copy when this finishes (<code>{label}</code>) — '
            '<strong>every</strong> conversation is delivered on this machine '
            '(<code>scope: all</code>)</span>'
            '</label>'
        )
    return (
        '<label class="orch-toggle" id="orch-deliver-toggle">'
        '<input type="checkbox" name="deliver_locally" />'
        f'<span>Deliver a copy when this finishes (<code>{label}</code>) — '
        'writes the same files as the <em>Export .zip</em> button, unzipped</span>'
        '</label>'
    )


def _render_orchestrate(
    initial_preflight: list[orch_preflight.PreflightResult],
    persona_roster: list[dict] | None = None,
    availability: dict | None = None,
    conv_type: str | None = None,
) -> str:
    """The /orchestrate form page.

    ``initial_preflight`` is the result of running preflight on the seats this
    machine may offer at page-load time. We surface OK / FAIL next to each
    checkbox so the operator can see config issues before submitting.
    The authoritative preflight runs again server-side on POST against the
    selected CLI subset — this lets the page-load preflight be advisory.

    ``persona_roster`` is ``[{"group": str, "personas": [{"slug", "name"}]}]``
    (from ``orchestrator.personas``) used to build the per-CLI persona picker.
    An empty/None roster still renders the picker (just the random/none choices).

    ``availability`` is ``{"declared": bool, "clis": [...], "seats": [...]}``
    from ``orchestrator.availability`` — used only for the notice above the
    participant list. ``None`` renders no notice, which is what a caller that
    doesn't care about onboarding gets.

    ``conv_type`` pre-selects a conversation-type radio (the homepage's
    "Launch a podcast" button arrives as ``/orchestrate?type=podcast``). An
    unknown or missing value falls back to ``DEFAULT_CONV_TYPE``; the JS runs
    ``updateConvType()`` on load, so the whole form re-labels itself from
    whichever radio is checked server-side.
    """
    checked_type = conv_type if conv_type in CONV_TYPES else DEFAULT_CONV_TYPE
    preflight_by_cli = {r.cli: r for r in initial_preflight}
    persona_roster = persona_roster or []
    seat_ids = _seat_order(list(preflight_by_cli))
    avail_notice = _availability_notice(availability, seat_ids)
    # A caller that passed no availability info keeps the historical behaviour
    # of listing the full registry rather than rendering an empty form.
    if not seat_ids and availability is None:
        seat_ids = list(_ORCH_CLI_IDS)

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

    # Which seats start ticked: the historical claude-code/codex pair when both
    # are offered, else simply the first two seats there are. An operator with
    # one CLI should land on a form that already describes a runnable debate
    # (claude-code vs claude-code-2), not one they have to repair.
    default_checked = {s for s in _DEFAULT_CHECKED if s in seat_ids}
    if len(default_checked) < 2:
        default_checked = set(seat_ids[:2])

    # One checkbox per configured seat. Extra seats ('codex-2') are marked so
    # it's obvious they're a second window of a tool already in the list.
    def _seat_checkbox(s: str) -> str:
        checked = " checked" if s in default_checked else ""
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

    delivery_toggle_html = _delivery_toggle_html()

    # Conversation-type radios, generated from the registry so a new type needs
    # no edit here. Each carries the seat rules the JS enforces client-side.
    type_radios = "".join(
        '<label class="orch-type">'
        f'<input type="radio" name="conv_type" value="{key}"'
        f'{" checked" if key == checked_type else ""} />'
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
            "guideUrl": t.guide_url,
            "guideLabel": t.guide_label,
            "leadHint": _lead_hint(key),
            "leadNeedsOwnSeat": t.lead_needs_own_seat,
            "minParticipants": t.min_participants,
            "maxParticipants": t.max_participants,
            "firstLabel": (
                f"First speaker ({t.lead_label.lower()})"
                if t.lead_required and not t.lead_needs_own_seat
                else "First speaker"
            ),
            "firstHint": (
                f"Whoever goes first is the {t.lead_label.lower()}: they frame "
                f"the goal, put decisions to the group, and write the "
                f"{t.deliverable_label.lower()} on their last turn. Leave it "
                f"on \u201c(first selected)\u201d and the top seat takes it."
                if t.lead_required and not t.lead_needs_own_seat
                else ""
            ),
            # Sub-types offered for this format. Presets are the sub-type axis
            # \u2014 see src/presets.py.
            "presets": list(presets_for(key)),
        }
        for key, t in CONV_TYPES.items()
    })
    # Server-rendered for the initially-checked type; the JS re-points it when
    # the operator switches format.
    guide_url = html.escape(CONV_TYPES[checked_type].guide_url, quote=True)
    guide_label = html.escape(CONV_TYPES[checked_type].guide_label)

    # EVERY preset is rendered; `updateConvType()` shows only the ones the
    # chosen format offers. Rendering all of them and toggling visibility beats
    # rebuilding innerHTML — the radios keep their identity, so a selection
    # survives a format switch that still offers it.
    #
    # A radio grid rather than a <select> on purpose: these sub-types ARE the
    # feature, and a dropdown hides them behind a click. The "none" card stays,
    # because it means something different from "Open collaboration" — it skips
    # kickoff rendering entirely (the paste-the-prompt flow).
    preset_radios = (
        '<label class="orch-preset" data-preset="">'
        '<input type="radio" name="preset" value="" />'
        '<span class="orch-preset-name">None</span>'
        '<span class="orch-preset-hint">No kickoff rendered — you paste the prompt yourself.</span>'
        '<span class="orch-preset-meta">paste-the-prompt</span>'
        + _preset_help("", "None")
        + "</label>"
    ) + "".join(_preset_radio(n) for n in PRESET_NAMES)

    # JS-side preset table: keep in sync with src/presets.py PRESETS.
    js_presets = json.dumps({
        name: {
            "max_turns": PRESETS[name]["max_turns"],
            "mode": PRESETS[name]["mode"],
        }
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
      <p class="hint">A question, a proposition, or a brief. Nothing here is
         truncated &mdash; the DB column is plain <code>TEXT</code>, and the
         archive's short slug is derived separately &mdash; so write as much as
         the room needs. For a long standing brief, the
         <em>optional system message</em> at the bottom is a better home: it
         arrives as the conversation's first message instead of as its title.</p>
      <textarea name="topic" required maxlength="4000" rows="2"
                placeholder="What should the agents discuss?"></textarea>
    </section>

    <section>
      <span class="lbl">Format</span>
      <p class="hint">What kind of room this is — who each seat is for. Separate from
         the sub-type below, which decides what the room produces.</p>
      <div class="orch-types">
        {type_radios}
      </div>
      <!-- Guide for whichever format is selected. href/text are rewritten by
           updateConvType() from the convTypes map, so it always points at the
           doc for the checked radio — including the ?type= the homepage CTA
           arrives with. Rendered server-side for the initial type so it's
           correct with JS off. -->
      <p class="orch-guide">
        <a id="orch-guide-link" href="{guide_url}" target="_blank" rel="noopener noreferrer">
          {guide_label} &#8599;</a>
        <span class="hint">&mdash; the operator guide on GitHub: seeding, prompts, and what each seat does.</span>
      </p>
    </section>

    <section id="orch-preset-section">
      <span class="lbl" id="orch-preset-label">Sub-type</span>
      <p class="hint" id="orch-preset-hint">Your topic says <em>what</em> to work on; this says
         <em>what to hand back</em>. It sets the agents' instructions and the shape of the final
         deliverable — nothing else changes. Leave it on the default to just follow your topic.</p>
      <div class="orch-presets" id="orch-preset-grid">
        {preset_radios}
      </div>
    </section>

    <section>
      <span class="lbl" id="orch-participants-label">Participants <em style="color: var(--muted-2); font-weight: 400;">(min 2)</em></span>
      <p class="hint">One CLI process per seat, five seats max. Only seats on the CLIs you
         have are listed &mdash; change that on the <a href="/setup">setup page</a>. Status
         reflects this machine's MCP config at page load; re-checked server-side on submit.
         A seat past the first on the same tool comes from
         <code>scripts/setup/add_agent_seat.py</code>.</p>
      {avail_notice}
      <div class="orch-clis">
        {cli_checkboxes}
      </div>
    </section>

    <section>
      <span class="lbl">Conversation</span>
      <div class="row">
        <label>
          <span style="font-size: 12px; color: var(--muted);">Max turns (per agent)</span>
          <input name="max_turns" type="number" min="1" max="50" value="8" />
        </label>
        <label>
          <span style="font-size: 12px; color: var(--muted);" id="orch-first-label">First speaker</span>
          <select name="first">
            <option value="">(first selected)</option>
          </select>
        </label>
      </div>
      <p class="hint" id="orch-first-hint" style="display:none"></p>
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

    <section id="orch-lead-section">
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
      {delivery_toggle_html}
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
  /* Sub-type picker — one card per preset the chosen format offers. A grid
     rather than a <select> because these ARE the feature; a dropdown hides
     them. Two columns on anything wider than a phone; the cards stack below
     that. Amber-tinted when checked, matching the collaboration accent used
     for a signal=result message, since picking one is choosing the artifact. */
  .orch-presets {{ display: grid; gap: 8px; margin-top: 8px;
                   grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
  .orch-preset {{ position: relative; display: grid; grid-template-columns: auto 1fr;
                  grid-template-areas: "radio name" "radio hint" "radio meta";
                  align-items: baseline; gap: 2px 10px;
                  padding: 10px 12px 10px; border: 1px solid var(--border, #ccc);
                  border-radius: 8px; cursor: pointer; }}
  .orch-preset input {{ grid-area: radio; width: auto; align-self: center; }}
  .orch-preset-name {{ grid-area: name; font-weight: 600; font-size: 13.5px; }}
  .orch-preset-hint {{ grid-area: hint; font-size: 12px; line-height: 1.45;
                       color: var(--muted-2, #71717a); }}
  .orch-preset-meta {{ grid-area: meta; font-size: 11px; margin-top: 2px;
                       font-family: 'IBM Plex Mono', ui-monospace, monospace;
                       color: var(--muted-2, #71717a); opacity: 0.75; }}
  .orch-preset:hover {{ border-color: var(--border-strong, #52525b); }}
  /* "?" in the bottom-right corner. Inside the <label>, so the JS cancels the
     click that would otherwise tick the radio behind it. The meta line keeps
     clear of it with padding-right rather than a column, so the corner stays
     put whatever the meta text says. */
  .orch-preset-meta {{ padding-right: 26px; }}
  .orch-preset-help {{ position: absolute; right: 8px; bottom: 8px;
                       width: 20px; height: 20px; padding: 0; flex: none;
                       display: flex; align-items: center; justify-content: center;
                       font: 600 12px/1 ui-sans-serif, system-ui, sans-serif;
                       border: 1px solid var(--border, #3f3f46); border-radius: 50%;
                       background: transparent; color: var(--muted-2, #71717a);
                       cursor: help; transition: color .12s, border-color .12s; }}
  .orch-preset-help:hover, .orch-preset-help:focus-visible {{
                       color: #f59e0b; border-color: #f59e0b;
                       background: rgba(245,158,11,0.12); }}
  /* The tooltip FLOATS over the card — absolutely positioned, so revealing it
     moves nothing. It hangs above the "?" anchored to the card's right edge,
     which keeps it inside the grid for a right-hand card. Hidden with
     visibility rather than display so it can fade, and pointer-events stay off
     so it never eats a click meant for whatever is underneath. */
  .orch-preset-detail {{ position: absolute; right: -1px; bottom: 30px; z-index: 30;
                         width: max(100%, 300px); max-width: 340px;
                         padding: 10px 12px; border-radius: 8px;
                         border: 1px solid var(--border-strong, #52525b);
                         background: var(--panel-2, #18181b);
                         box-shadow: 0 10px 28px rgba(0,0,0,0.55);
                         font-size: 12px; line-height: 1.6; font-weight: 400;
                         color: var(--muted, #a1a1aa); text-align: left;
                         opacity: 0; visibility: hidden; pointer-events: none;
                         transition: opacity .12s ease, visibility .12s; }}
  .orch-preset-help:hover ~ .orch-preset-detail,
  .orch-preset-help:focus-visible ~ .orch-preset-detail {{ opacity: 1;
                                                           visibility: visible; }}
  .orch-preset-detail strong {{ color: var(--text, #e4e4e7); font-weight: 600; }}
  .orch-preset-detail code {{ font-family: 'IBM Plex Mono', ui-monospace, monospace;
                              font-size: 11px; }}
  /* Lift the hovered card so its tooltip is never painted under a neighbour. */
  .orch-preset:has(.orch-preset-help:hover),
  .orch-preset:has(.orch-preset-help:focus-visible) {{ z-index: 30; }}
  .orch-preset:has(input:checked) {{ border-color: #f59e0b;
                                     background: rgba(245,158,11,0.07); }}
  /* Per-format guide link under the picker (swapped by updateConvType). */
  .orch-guide {{ margin: 10px 0 0; font-size: 13px; }}
  .orch-guide a {{ font-weight: 500; }}
  .orch-guide .hint {{ display: inline; margin: 0; }}
  /* Availability notice above the participant list — see _availability_notice(). */
  .orch-avail {{ border: 1px solid var(--border, #333); border-radius: 8px;
                 padding: 10px 13px; margin: 4px 0 2px;
                 font-size: 12.5px; line-height: 1.6; color: var(--muted, #a1a1aa);
                 background: rgba(255,255,255,0.02); }}
  .orch-avail.warn {{ border-color: rgba(245,158,11,0.35);
                      background: rgba(245,158,11,0.07); color: #fcd9a1; }}
  .orch-avail a {{ color: var(--accent, #10b981); }}
  .orch-avail.warn a {{ color: #fbbf24; }}
  .orch-avail code {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; }}
</style>

<script>
(function() {{
  const presetDefaults = {js_presets};
  const convTypes = {js_conv_types};
  const form = document.getElementById('orch-form');
  const submitBtn = form.querySelector('button[type=submit]');
  const errorPanel = document.getElementById('orch-error');
  const presetRadios = form.querySelectorAll('input[name=preset]');
  const presetCards = form.querySelectorAll('.orch-preset');
  const presetSection = document.getElementById('orch-preset-section');
  const presetLabel = document.getElementById('orch-preset-label');
  const presetGrid = document.getElementById('orch-preset-grid');
  const maxTurns = form.querySelector('input[name=max_turns]');
  const firstSelect = form.querySelector('select[name=first]');
  const cliCheckboxes = form.querySelectorAll('input[name=cli]');
  const personaRows = form.querySelectorAll('.orch-persona-row');
  const castRandomBtn = document.getElementById('orch-cast-random');
  const spawnToggle = form.querySelector('input[name=spawn]');
  const skipToggle = form.querySelector('input[name=skip_permissions]');
  const deliverToggle = form.querySelector('input[name=deliver_locally]');
  const modEnable = form.querySelector('input[name=mod_enable]');
  const modFields = document.getElementById('orch-mod-fields');
  const modCli = form.querySelector('select[name=mod_cli]');
  const modPersona = form.querySelector('select[name=mod_persona]');
  const typeRadios = form.querySelectorAll('input[name=conv_type]');
  const guideLink = document.getElementById('orch-guide-link');
  const partsLabel = document.getElementById('orch-participants-label');
  const leadLabel = document.getElementById('orch-lead-label');
  const leadHint = document.getElementById('orch-lead-hint');
  const modToggle = document.getElementById('orch-mod-toggle');
  const leadSection = document.getElementById('orch-lead-section');
  const firstLabel = document.getElementById('orch-first-label');
  const firstHint = document.getElementById('orch-first-hint');
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
    // A lead that is one of the members is picked from these checkboxes, so
    // the range quoted here is the WHOLE room, not members-besides-the-lead.
    const lo = t.leadNeedsOwnSeat ? t.minMembers : t.minParticipants;
    const hi = t.leadNeedsOwnSeat ? t.maxMembers : t.maxParticipants;
    if (partsLabel) {{
      partsLabel.innerHTML = t.membersLabel +
        ' <em style="color: var(--muted-2); font-weight: 400;">(' +
        lo + '\\u2013' + hi + ')</em>';
    }}
    if (firstLabel) firstLabel.textContent = t.firstLabel || 'First speaker';
    if (firstHint) {{
      firstHint.innerHTML = t.firstHint || '';
      firstHint.style.display = t.firstHint ? '' : 'none';
    }}
    if (leadLabel) {{
      leadLabel.innerHTML = t.leadLabel + (t.leadRequired
        ? ' <em style="color: var(--muted-2); font-weight: 400;">(required)</em>'
        : ' <em style="color: var(--muted-2); font-weight: 400;">(optional)</em>');
    }}
    if (modToggleText) modToggleText.textContent = 'Add a ' + t.leadLabel.toLowerCase();
    if (modPersonaLabel) modPersonaLabel.textContent = t.leadLabel + ' persona';
    if (guideLink && t.guideUrl) {{
      guideLink.href = t.guideUrl;
      guideLink.innerHTML = t.guideLabel + ' \\u2197';
    }}
    if (leadHint && t.leadHint) leadHint.innerHTML = t.leadHint;
    // A lead that is one of the members has no separate seat to configure:
    // hide the section AND clear the toggle so the submit handler sends
    // moderator:null. Left checked-but-hidden it would post an unseen seat.
    if (leadSection) leadSection.style.display = t.leadNeedsOwnSeat ? '' : 'none';
    if (modEnable && !t.leadNeedsOwnSeat) {{
      modEnable.checked = false;
      modEnable.disabled = true;
    }} else if (modEnable && t.leadRequired) {{
      modEnable.checked = true;
      modEnable.disabled = true;
      if (modToggle) modToggle.style.opacity = '0.65';
    }} else if (modEnable) {{
      modEnable.disabled = false;
      if (modToggle) modToggle.style.opacity = '';
    }}
    // Sub-types belong to a format, so show only the ones this format offers.
    // Cards are never rebuilt, just hidden — a selection that is still on
    // offer survives the switch. The server accepts any preset with any type
    // (presets.for_types is advisory), so this only shapes the picker.
    const offered = t.presets || [];
    let stillOffered = false;
    presetCards.forEach(card => {{
      const name = card.dataset.preset;
      const show = name === '' || offered.includes(name);
      card.style.display = show ? '' : 'none';
      const radio = card.querySelector('input');
      if (radio) {{
        radio.disabled = !show;
        if (radio.checked && !show) radio.checked = false;
        if (radio.checked && show) stillOffered = true;
      }}
    }});
    // Only one sub-type on offer means there is nothing to choose — hide the
    // whole section rather than showing a single radio next to "None".
    if (presetSection) presetSection.style.display = offered.length > 1 ? '' : 'none';
    if (presetLabel) presetLabel.textContent = offered.length > 1 ? 'Sub-type' : 'Preset';
    if (!stillOffered) selectPreset(t.defaultPreset && offered.includes(t.defaultPreset)
                                    ? t.defaultPreset : '');
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

  // Check one sub-type and pull its mode/turn defaults across.
  function selectPreset(name) {{
    presetRadios.forEach(r => {{ r.checked = (r.value === name); }});
    const d = presetDefaults[name];
    if (d && maxTurns) maxTurns.value = d.max_turns;
  }}

  function currentPreset() {{
    const picked = Array.from(presetRadios).find(r => r.checked && !r.disabled);
    return picked ? picked.value : '';
  }}

  presetRadios.forEach(r => r.addEventListener('change', () => {{
    const d = presetDefaults[r.value];
    if (d && maxTurns) maxTurns.value = d.max_turns;
  }}));

  // --- sub-type help ------------------------------------------------------
  // The tooltip is pure CSS (:hover / :focus-visible on the "?"), so nothing
  // here shows or hides it. This exists only because the "?" sits inside the
  // card's <label>: without it a stray click on the help button would tick the
  // radio behind it, and reading about a sub-type must not select it.
  // Delegated from the grid so it survives a future re-render of the cards.
  if (presetGrid) {{
    presetGrid.addEventListener('click', (ev) => {{
      if (!ev.target.closest('.orch-preset-help')) return;
      ev.preventDefault();
      ev.stopPropagation();
    }});
  }}
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

  // Topic is a <textarea> so a pasted brief keeps its shape while you edit it,
  // but it used to be an <input>, where Enter submitted. Keep that: Enter
  // submits, Shift+Enter takes a newline — the convention every chat box uses.
  // (Seeding collapses whitespace anyway, so a newline never reaches the DB.)
  const topicBox = form.querySelector('textarea[name=topic]');
  if (topicBox) {{
    topicBox.addEventListener('keydown', (ev) => {{
      if (ev.key === 'Enter' && !ev.shiftKey) {{
        ev.preventDefault();
        form.requestSubmit();
      }}
    }});
  }}

  form.addEventListener('submit', async (ev) => {{
    ev.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = 'Running preflight…';
    // Set on the success path. `window.location.href` does not stop this
    // script or unload the page synchronously, so without this the `finally`
    // below re-enabled the button for the whole teardown-and-navigate window
    // — and a second click in that gap seeded a SECOND conversation and
    // spawned a second set of CLI windows. That is exactly what happened to
    // runs #55/#56 (seeded 219ms apart, four terminals). A launch is not
    // idempotent: the button stays dead once it has worked.
    let navigating = false;
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
      preset: currentPreset() || null,
      max_turns: parseInt(fd.get('max_turns'), 10) || null,
      first: fd.get('first') || null,
      kickoff: (fd.get('kickoff') || '').trim() || null,
      personas: personas,
      spawn: !!(spawnToggle && spawnToggle.checked),
      skip_permissions: !!(skipToggle && skipToggle.checked),
      // Absent (delivery off) or disabled (scope: all) both send false;
      // the server ignores it in the second case anyway.
      deliver_locally: !!(deliverToggle && !deliverToggle.disabled && deliverToggle.checked),
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
        navigating = true;
        submitBtn.textContent = 'Opening conversation…';
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
      // Only when the run did NOT start — see `navigating` above.
      if (!navigating) {{
        submitBtn.disabled = false;
        submitBtn.textContent = 'Run preflight + start conversation';
      }}
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

    The homepage's "Launch a debate" / "Launch a podcast" CTAs both land here on
    the mirror, so this page carries the per-format guide links too — it's the
    only "how do I run one" answer a hosted visitor gets.
    """
    guide_links = "".join(
        f'<a href="{html.escape(t.guide_url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(t.guide_label)} &#8599;</a>'
        for t in CONV_TYPES.values()
    )
    body = f"""
<div class="orch-shell">
  <header class="orch-head">
    <h2>Debates run on your machine, not here</h2>
    <p>This hosted site is a <strong>read-only demo</strong> for viewing debates.
       It can't launch one — spawning CLI agents needs the CLIs, their auth, and
       the shared SQLite DB on your own computer.
       <a href="{_REPO}" target="_blank" rel="noopener noreferrer">Clone the repo &rarr;</a>
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

  <div class="orch-ro-card">
    <h3>The guides</h3>
    <p>One per format &mdash; what to seed, what each seat does, and the prompts to paste.</p>
    <div class="orch-ro-links">
      {guide_links}
      <a href="{_REPO}/blob/main/docs/Guides/online-forums.md" target="_blank" rel="noopener noreferrer">How to participate in online forums &#8599;</a>
    </div>
  </div>

  <p class="orch-ro-foot">New here? Start with the
    <a href="{_REPO}#readme" target="_blank" rel="noopener noreferrer">README</a>,
    or <a href="/conversations">browse existing conversations &rarr;</a></p>
</div>
"""
    return _layout(
        "Orchestrate", "", body,
        head_extras=f"<style>{ORCHESTRATE_CSS}</style>{_ORCH_READONLY_CSS}",
        active="orchestrate",
    )
