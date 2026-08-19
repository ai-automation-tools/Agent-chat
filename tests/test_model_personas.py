r"""Tests for the built-in AI-Models cards and the Cast fallback.

Two things worth pinning:

* The **reserved-group guard.** ``DEFAULT_DEBATER_GROUP`` ("Unique-Personas")
  holds zero rows in a real DB — the roster was reorganised into per-category
  groups — so every random-cast path falls through to "all personas". Without
  ``list_debater_personas()`` excluding reserved groups, a random debate would
  cast "Claude Code" against Gordon Ramsay.
* The **Cast fallback** for conversations seeded without personas.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_model_personas.py

Uses an isolated temp DB — never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _fresh_db():
    """Point the whole stack at an empty temp DB and return its path.

    Sets AGENT_CHAT_DB (personas resolves per call) via web.db.set_db_path, which
    exports it — the same coupling the app relies on.
    """
    tmp = Path(tempfile.mkdtemp(prefix="agentchat-models-")) / "chat.db"
    import web.db as webdb

    webdb.set_db_path(str(tmp))
    webdb.db_init()
    assert os.environ["AGENT_CHAT_DB"] == str(tmp), \
        "set_db_path must export AGENT_CHAT_DB or personas reads the real DB"
    return tmp


def test_ensure_is_idempotent_and_creates_one_card_per_cli() -> None:
    _fresh_db()
    from orchestrator import personas
    from orchestrator.model_personas import MODEL_CARDS, ensure_model_personas

    first = ensure_model_personas()
    assert first["created"] == len(MODEL_CARDS), first
    second = ensure_model_personas()
    assert second == {"created": 0, "skipped": len(MODEL_CARDS)}, second

    cards = personas.list_personas(personas.AI_MODELS_GROUP)
    assert len(cards) == len(MODEL_CARDS)
    # The slug IS the agent id — the whole lookup depends on it.
    assert {c.slug for c in cards} == set(MODEL_CARDS)


def test_cards_cover_every_supported_cli() -> None:
    from orchestrator.model_personas import MODEL_CARDS
    from orchestrator.preflight import SUPPORTED_CLIS

    missing = set(SUPPORTED_CLIS) - set(MODEL_CARDS)
    assert not missing, f"no AI-Models card for: {sorted(missing)}"


def test_ensure_never_overwrites_operator_edits() -> None:
    _fresh_db()
    from orchestrator import personas
    from orchestrator.model_personas import ensure_model_personas

    ensure_model_personas()
    personas.update_persona("codex", name="My Custom Codex",
                            group=personas.AI_MODELS_GROUP)
    ensure_model_personas()
    kept = personas.get_persona("codex", group=personas.AI_MODELS_GROUP)
    assert kept is not None and kept.name == "My Custom Codex"


def test_model_cards_are_excluded_from_random_casting() -> None:
    """The guard that keeps 'Claude Code' out of a random debate cast."""
    _fresh_db()
    from orchestrator import personas
    from orchestrator.model_personas import MODEL_CARDS, ensure_model_personas

    ensure_model_personas()
    personas.create_persona(name="Gordon Ramsay", body="Angry chef.",
                            group="Celebrities")

    # The realistic case: the default debater group is empty, so callers fall
    # back to "everything" — which must not include the reference cards.
    assert personas.list_personas(personas.DEFAULT_DEBATER_GROUP) == []
    castable = personas.list_debater_personas()
    assert [p.name for p in castable] == ["Gordon Ramsay"]
    assert all(p.group != personas.AI_MODELS_GROUP for p in castable)

    # list_personas(None) still means "literally everything".
    assert len(personas.list_personas(None)) == len(castable) + len(MODEL_CARDS)

    # An explicit group request is still honoured.
    explicit = personas.list_debater_personas(personas.AI_MODELS_GROUP)
    assert len(explicit) == len(MODEL_CARDS)


def test_castable_cli_flag_excludes_reserved_groups() -> None:
    """debate.ps1 draws its roster through `list --castable`."""
    _fresh_db()
    import json
    from contextlib import redirect_stdout
    from io import StringIO

    from orchestrator import personas
    from orchestrator.model_personas import MODEL_CARDS, ensure_model_personas

    ensure_model_personas()
    personas.create_persona(name="Gordon Ramsay", body="Angry chef.",
                            group="Celebrities")

    buf = StringIO()
    with redirect_stdout(buf):
        personas._main(["list", "--castable"])
    assert [p["name"] for p in json.loads(buf.getvalue())] == ["Gordon Ramsay"]

    # --all-groups still means all, reference cards included.
    buf = StringIO()
    with redirect_stdout(buf):
        personas._main(["list", "--all-groups"])
    assert len(json.loads(buf.getvalue())) == len(MODEL_CARDS) + 1


def _conv(participants, personas_map=None):
    return {"id": 16, "topic": "AI in Cyber Warfare",
            "participants": participants,
            "participant_personas": personas_map}


def test_cast_falls_back_to_model_cards_when_none_recorded() -> None:
    """Conversation #16 ('gemini', 'codex') should read as Gemini vs Codex."""
    _fresh_db()
    from orchestrator.model_personas import ensure_model_personas
    from web.render.conversations import _cast_panel, _effective_cast

    ensure_model_personas()
    conv = _conv(["gemini", "codex"])

    cast, defaulted = _effective_cast(conv, {})
    assert cast["gemini"]["persona_name"] == "Gemini"
    assert cast["codex"]["persona_name"] == "Codex"
    assert defaulted == {"gemini", "codex"}

    html = _cast_panel(conv, {}, Counter({"gemini": 4, "codex": 4}))
    assert "Gemini" in html and "Codex" in html
    assert "AI model" in html, "fallback rows must be labelled as stand-ins"
    assert "no persona recorded" not in html


def test_recorded_personas_win_over_model_cards() -> None:
    _fresh_db()
    from orchestrator.model_personas import ensure_model_personas
    from web.render.conversations import _effective_cast

    ensure_model_personas()
    recorded = {"codex": {"persona_slug": "elon-musk",
                          "persona_name": "Elon Musk",
                          "persona_body": "Ships fast."}}
    conv = _conv(["gemini", "codex"], recorded)

    cast, defaulted = _effective_cast(conv, recorded)
    assert cast["codex"]["persona_name"] == "Elon Musk"
    assert cast["gemini"]["persona_name"] == "Gemini"
    assert defaulted == {"gemini"}, "only the un-recorded agent is a fallback"


def test_cast_panel_degrades_when_no_cards_exist() -> None:
    """A DB with no AI-Models rows must not crash or invent a cast."""
    _fresh_db()  # deliberately not seeded
    from web.render.conversations import _cast_panel, _effective_cast

    conv = _conv(["gemini", "codex"])
    cast, defaulted = _effective_cast(conv, {})
    assert cast == {} and defaulted == set()
    assert _cast_panel(conv, {}, Counter()) == ""


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {fn.__name__}: {exc!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
