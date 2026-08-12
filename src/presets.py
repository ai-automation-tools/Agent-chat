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
"""

from __future__ import annotations

from typing import TypedDict


class Preset(TypedDict):
    tone: str
    mode: str
    max_turns: int


PRESETS: dict[str, Preset] = {
    "debate": {
        "tone": (
            "Have a real debate — take positions, push back, share concrete "
            "predictions. Don't just agree with each other."
        ),
        "mode": "turns",
        "max_turns": 8,
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
    },
    "code-review": {
        "tone": (
            "Review the proposal critically. Reference specific lines or "
            "claims. Distinguish blocking issues from suggestions. End with "
            "an explicit approve / request-changes signal."
        ),
        "mode": "turns",
        "max_turns": 6,
    },
    "brainstorm": {
        "tone": (
            "Generate ideas freely. Build on each other rather than "
            "evaluating. Quantity first, then we converge."
        ),
        "mode": "continuous",
        "max_turns": 10,
    },
    "plan": {
        "tone": (
            "Work toward a concrete plan. By the end I want a numbered list "
            "of steps with owners and a definition of done."
        ),
        "mode": "turns",
        "max_turns": 8,
    },
}


PRESET_NAMES = tuple(PRESETS.keys())


def get_preset(name: str) -> Preset:
    """Return the preset dict for `name`, or raise KeyError with a helpful message."""
    if name not in PRESETS:
        valid = ", ".join(PRESET_NAMES)
        raise KeyError(f"unknown preset {name!r}; valid presets: {valid}")
    return PRESETS[name]
