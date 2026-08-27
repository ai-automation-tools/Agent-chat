"""
presets.py - Named kickoff presets for start_conversation.py.

Each preset bundles three operator decisions into one short flag:

    1. The `tone` instruction (a complete sentence pasted into the
       rendered kickoff template's `{{TONE_INSTRUCTION}}` placeholder).
    2. Default `mode` ('turns' or 'continuous').
    3. Default `max_turns` (per-agent message cap).

Explicit `--mode` / `--max-turns` flags on start_conversation.py still
override the preset's defaults — the preset is a starting point, not
a lock.

Tone strings are copied verbatim from prompts/Kickoff/kickoff.md's
"{{TONE_INSTRUCTION}} examples" section. Keep them in sync — if the
canonical kickoff doc changes a tone, this file should change with it.

**Presets are also the sub-type axis.** ``conv_type``
(``orchestrator/conv_types.py``) is the room's *structure* — who is in it and
what each seat is for — and it stays a small set, because a structure is
expensive: seats, role briefs, a skill, a guide. A *flavour* of a structure is
cheap, and that is what a preset is. Brainstorming, planning, and reviewing are
all the same room (a facilitator plus collaborators, converging on an artifact)
pointed at different work, so they are presets of ``collaborate`` rather than
three conversation types that would each duplicate the same seat model.

Three optional keys carry that:

    ``label``       display name of the flavour ("Brainstorm").
    ``deliverable`` for a type whose lead posts a ``signal='result'`` closing
                    turn, the shape that artifact must take. Ignored by types
                    that don't produce one.
    ``for_types``   conv_types this flavour belongs to. **Advisory** — it
                    filters the picker in the web form, exactly like CLI
                    availability does; nothing rejects an odd pairing, and a
                    preset with no ``for_types`` is offered everywhere.
"""

from __future__ import annotations

from typing import TypedDict


class _PresetRequired(TypedDict):
    tone: str
    mode: str
    max_turns: int


class Preset(_PresetRequired, total=False):
    # See the module docstring. `NotRequired` would be tidier but landed in
    # 3.11 and this repo supports 3.10.
    label: str
    deliverable: str
    for_types: tuple[str, ...]


PRESETS: dict[str, Preset] = {
    "debate": {
        "tone": (
            "Have a real debate — take positions, push back, share concrete "
            "predictions. Don't just agree with each other."
        ),
        "mode": "turns",
        "max_turns": 8,
        "label": "Debate",
        "for_types": ("debate",),
    },
    "podcast": {
        "tone": (
            "This is a podcast, not a debate. The host runs the room and asks "
            "the questions; the guests answer at length — concrete stories, "
            "specifics, and opinions they'd actually defend. Disagree where you "
            "genuinely do, but don't manufacture conflict, and let an "
            "interesting tangent run."
        ),
        "mode": "turns",
        "max_turns": 10,
        "label": "Podcast",
        "for_types": ("podcast",),
    },
    "collaborate": {
        "tone": (
            "You are working on this together, not performing for an audience. "
            "Build on what the others put down, say plainly when you think "
            "something is wrong and why, and keep pulling toward one answer "
            "everyone can live with rather than a set of parallel opinions."
        ),
        "mode": "turns",
        "max_turns": 8,
        "label": "Open collaboration",
        "deliverable": (
            "the thing the room was asked to produce, written out in full — "
            "not a summary of the discussion. State what was agreed, name any "
            "disagreement that survived, and say what would settle it."
        ),
        "for_types": ("collaborate",),
    },
    "brainstorm": {
        "tone": (
            "Generate ideas freely. Build on each other rather than "
            "evaluating. Quantity first, then we converge."
        ),
        # Continuous: divergence is the point, so nobody should sit blocked
        # waiting for a turn while an idea is fresh. Convergence is paced by
        # the facilitator off `turns_remaining`, not by a phase machine.
        "mode": "continuous",
        "max_turns": 10,
        "label": "Brainstorm",
        "deliverable": (
            "a ranked shortlist — the strongest ideas in order, each with one "
            "line on why it ranks there and what would have to be true for it "
            "to work. Name the ideas that were dropped and why."
        ),
        "for_types": ("collaborate",),
    },
    "plan": {
        "tone": (
            "Work toward a concrete plan. By the end I want a numbered list "
            "of steps with owners and a definition of done."
        ),
        "mode": "turns",
        "max_turns": 8,
        "label": "Plan",
        "deliverable": (
            "a numbered plan — each step with an owner, what it depends on, "
            "and a definition of done. Call out the risks and what is still "
            "unknown rather than papering over them."
        ),
        "for_types": ("collaborate",),
    },
    # ---- collaboration sub-types added 2026-08-26 -----------------------
    # Each earns its place by producing a DIFFERENT ARTIFACT, not by being
    # about a different subject. "Prioritize" is Decide with the options
    # supplied; "Spec" is Plan with different headings; both were left out on
    # purpose. See docs/Guides/collaborate.md.
    "decide": {
        "tone": (
            "You are choosing between options, not exploring them. Put the "
            "real alternatives on the table early, argue them against stated "
            "criteria, and commit to one. An option nobody argued for was "
            "never a real option."
        ),
        "mode": "turns",
        "max_turns": 8,
        "label": "Decide",
        "deliverable": (
            "the decision, then — just as important — every option that lost "
            "and the specific reason it lost. Name the criteria you judged "
            "against, and say what would have to change for the decision to "
            "flip."
        ),
        "for_types": ("collaborate",),
    },
    "solve": {
        "tone": (
            "Something is broken and you are working out why. Form specific "
            "hypotheses, say what evidence would confirm or kill each one, and "
            "eliminate rather than accumulate. Resist jumping to a fix before "
            "the cause is established."
        ),
        "mode": "turns",
        "max_turns": 8,
        "label": "Solve",
        "deliverable": (
            "the root cause, the evidence that points at it, and the fix — in "
            "that order. List the hypotheses you ruled out and what ruled them "
            "out. If the cause is still uncertain, say so and name the one "
            "test that would settle it."
        ),
        "for_types": ("collaborate",),
    },
    "code-review": {
        "tone": (
            "Review the proposal critically. Reference specific lines or "
            "claims. Distinguish blocking issues from suggestions. End with "
            "an explicit approve / request-changes signal."
        ),
        "mode": "turns",
        "max_turns": 6,
        "label": "Review",
        "deliverable": (
            "a verdict — approve or request-changes — followed by the blocking "
            "issues as a numbered list, then non-blocking suggestions "
            "separately. Every blocking item names what to change and why."
        ),
        "for_types": ("collaborate",),
    },
    "audit": {
        "tone": (
            "You are auditing something that already exists — a repo, a "
            "system, a body of work. Go through it yourself first and form "
            "your own findings before you read anyone else's, then reconcile: "
            "say which findings you both landed on, which you disagree about, "
            "and which one of you missed. Anchor every finding to something "
            "specific you actually looked at, and rank by impact rather than "
            "by how easy it was to spot. Say what you did NOT get to — an "
            "audit that hides its blind spots is worse than a short one."
        ),
        "mode": "turns",
        "max_turns": 8,
        "label": "Audit",
        "deliverable": (
            "a findings register — everything worth acting on, ranked by "
            "impact, each finding naming where it is, the evidence for it, "
            "why it matters, and the recommended change. Keep defects and "
            "enhancements distinguishable. Open with what was examined and "
            "what was not, and close with the findings you disagreed on and "
            "what would settle each."
        ),
        "for_types": ("collaborate",),
    },
    "design": {
        "tone": (
            "You are designing a system, not planning the work to build it. "
            "Argue about structure: components, boundaries, interfaces, and "
            "what happens under failure. Every choice costs something — say "
            "what."
        ),
        "mode": "turns",
        "max_turns": 10,
        "label": "Design",
        "deliverable": (
            "the design itself — components and what each is responsible for, "
            "the interfaces between them, the data that flows across, and the "
            "failure modes. For every significant choice, name the alternative "
            "you rejected and the tradeoff you accepted."
        ),
        "for_types": ("collaborate",),
    },
    "validate": {
        "tone": (
            "You are pressure-testing an idea, not selling it. Go after the "
            "assumptions it depends on. Someone must argue the case against, "
            "and 'it depends' is not an answer — say on what, and what the "
            "answer would have to be."
        ),
        "mode": "turns",
        "max_turns": 10,
        "label": "Validate",
        "deliverable": (
            "a go / no-go / not-yet call with the reasoning, covering who "
            "would buy it and why, who already does this, what it costs to "
            "run, and the assumptions the whole thing rests on. State the "
            "single thing most likely to kill it, and the cheapest test that "
            "would find out."
        ),
        "for_types": ("collaborate",),
    },
}


PRESET_NAMES = tuple(PRESETS.keys())


def get_preset(name: str) -> Preset:
    """Return the preset dict for `name`, or raise KeyError with a helpful message."""
    if name not in PRESETS:
        valid = ", ".join(PRESET_NAMES)
        raise KeyError(f"unknown preset {name!r}; valid presets: {valid}")
    return PRESETS[name]


def preset_label(name: str | None) -> str:
    """Display name for a preset, falling back to the raw key.

    Read path — tolerates a value written by a build that had presets this one
    doesn't, so an old conversation still renders.
    """
    if not name:
        return ""
    p = PRESETS.get(name)
    if p and p.get("label"):
        return p["label"]
    return name.replace("-", " ").replace("_", " ").title()


def presets_for(conv_type: str | None) -> tuple[str, ...]:
    """Preset names offered for a conversation type, in declaration order.

    A preset with no ``for_types`` belongs to every type. Advisory: this shapes
    the picker, it does not validate — see the module docstring.
    """
    if not conv_type:
        return PRESET_NAMES
    return tuple(
        name for name, p in PRESETS.items()
        if conv_type in p.get("for_types", (conv_type,))
    )


def deliverable_for(name: str | None) -> str:
    """The artifact shape this preset asks for, or '' when it names none."""
    if not name:
        return ""
    return PRESETS.get(name, {}).get("deliverable", "")
