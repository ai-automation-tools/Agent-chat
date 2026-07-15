"""Built-in "AI-Models" persona cards — one per supported CLI.

Most conversations record a persona cast (``conversations.participant_personas``,
written by ``debate.ps1`` / ``POST /api/orchestrate``). Plenty of older ones
don't: they were seeded before the persona system existed, so the reader page had
no Cast panel at all and messages were labelled with a bare agent id.

These cards are the fallback. One per entry in ``preflight.SUPPORTED_CLIS``,
slugged with the **agent id** so a lookup is just
``get_persona(agent_id, group=AI_MODELS_GROUP)``. They live in the DB like any
other persona — visible and editable on ``/personas``, and synced to the hosted
mirror by ``scripts/db_sync.py`` — but sit in a **reserved group**
(``personas.RESERVED_GROUPS``) so they're never drawn as random debaters.

``ensure_model_personas()`` is idempotent and **create-if-missing**: it never
overwrites an existing row, so operator edits on /personas survive a restart.
Delete a card and it comes back on the next boot; that's the intended escape
hatch for "reset it to stock".

Bodies are original descriptions of each tool's documented, publicly-observable
behaviour — deliberately *not* copies of any vendor's system prompt. Verbatim
prompt text is copyrighted, and the useful thing here is how the CLI actually
behaves in a debate, which no vendor prompt states anyway. Keep them short: they
render inside a collapsed Cast row.
"""

from __future__ import annotations

from orchestrator.personas import (
    AI_MODELS_GROUP,
    Persona,
    create_persona,
    get_persona,
)

MODEL_CATEGORY = "AI Models"

# agent_id -> (display name, tags, body). The agent id doubles as the slug.
MODEL_CARDS: dict[str, tuple[str, list[str], str]] = {
    "claude-code": (
        "Claude Code",
        ["anthropic", "claude", "cli"],
        """\
**Claude Code** — Anthropic's agentic coding CLI, running a Claude model.

Its default register is careful and qualified: it states the strongest version of
a claim, then names the caveat it knows about rather than leaving it implicit. It
tends to steelman the other side before disagreeing, and it will concede a point
outright instead of defending a losing line — which reads as either intellectual
honesty or as hedging, depending on who's scoring.

In this project it's the most common first speaker, and the reference
implementation for the MCP participation loop.
""",
    ),
    "codex": (
        "Codex",
        ["openai", "gpt", "cli"],
        """\
**Codex** — OpenAI's coding agent CLI, running a GPT-family model.

Terse and structured where others are discursive. It reaches for enumerated
points, concrete mechanisms, and worked specifics, and it prefers to answer the
question asked rather than the interesting question nearby. In a debate that
makes it an effective closer: it restates the disagreement in its own terms and
argues the narrowed version.

Least likely of the roster to pad an answer.
""",
    ),
    "gemini": (
        "Gemini",
        ["google", "gemini", "cli", "deprecated"],
        """\
**Gemini** — Google's Gemini CLI.

Expansive and well-sourced by instinct: it reaches for context, competing
framings, and the history of an argument before committing to a side, and it
often surfaces a consideration the other debaters skipped entirely. The
flip-side is a pull toward even-handedness — it will present a balanced survey
where the format wanted a position.

Deprecated in this project (kept as a fallback and superseded by Antigravity),
but it's the CLI behind several of the earliest conversations in the archive.
""",
    ),
    "antigravity": (
        "Antigravity",
        ["google", "agent-first", "cli"],
        """\
**Antigravity** — Google's agent-first development CLI.

Built around planning and multi-step execution rather than single-shot answers,
and it argues the way it works: it lays out the shape of its case, then fills it
in. It's the most likely to reason about second-order effects and about what
would have to be true for its own position to be wrong.

The Gemini CLI's successor in this project's supported set.
""",
    ),
    "kimi": (
        "Kimi",
        ["moonshot", "kimi", "cli"],
        """\
**Kimi** — Moonshot AI's Kimi CLI.

Long-context by design and comfortable holding a whole thread in view, which
shows in how it argues: it quotes earlier turns back accurately and will call out
when an opponent has quietly shifted position. Direct, and less prone to
diplomatic softening than the US-lab models.

Wired into this project's 4- and 5-agent rotations.
""",
    ),
    "opencode": (
        "OpenCode",
        ["open-source", "model-agnostic", "cli"],
        """\
**OpenCode** — the open-source, model-agnostic coding CLI.

The wildcard of the roster: its character depends on whichever model it's
pointed at, so its voice is the least predictable here. What's consistent is the
open-source sensibility — it's the one most likely to question a premise about
closed platforms, vendor control, or who owns a model's output.

Wired into this project's 5-agent rotation.
""",
    ),
}


def ensure_model_personas() -> dict[str, int]:
    """Create any missing AI-Models cards. Idempotent; never overwrites.

    Returns ``{"created": N, "skipped": M}``. Safe to call on every boot — and on
    a DB that can't be reached, in which case it reports nothing created rather
    than raising, since a missing Cast fallback must never take the app down.
    """
    created = skipped = 0
    for agent_id, (name, tags, body) in MODEL_CARDS.items():
        try:
            if get_persona(agent_id, group=AI_MODELS_GROUP) is not None:
                skipped += 1
                continue
            create_persona(
                name=name,
                body=body.strip(),
                group=AI_MODELS_GROUP,
                tags=list(tags),
                category=MODEL_CATEGORY,
                subcategory="CLI",
                slug=agent_id,
            )
            created += 1
        except Exception:  # noqa: BLE001
            # A DB that's down, or a slug an operator has since repurposed —
            # neither is worth failing a page render or a server start over.
            skipped += 1
    return {"created": created, "skipped": skipped}


def model_persona(agent_id: str) -> Persona | None:
    """The AI-Models card for one agent id, or None."""
    if not agent_id:
        return None
    return get_persona(str(agent_id), group=AI_MODELS_GROUP)


def model_persona_entries(agent_ids: list[str]) -> dict[str, dict[str, str]]:
    """Cast entries for the given agent ids, in ``participant_personas`` shape.

    Returns ``{agent_id: {persona_slug, persona_name, persona_body}}`` — the same
    shape the DB column uses — so callers can merge these with a real recorded
    cast without special-casing. Agent ids with no card are simply absent.
    """
    out: dict[str, dict[str, str]] = {}
    for agent_id in agent_ids:
        persona = model_persona(agent_id)
        if persona is None:
            continue
        out[str(agent_id)] = {
            "persona_slug": persona.slug,
            "persona_name": persona.name,
            "persona_body": persona.body,
        }
    return out


def _main() -> int:
    import json

    print(json.dumps(ensure_model_personas()))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
