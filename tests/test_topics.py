r"""Tests for ``web.topics`` — the topic→logo classifier behind conversation marks.

The classifier is pure keyword scoring, and the interesting behaviour is the
*tie-breaking*: an AI debate about weapons should read as `security`, an AI
debate about jobs as `work`, and so on. Those outcomes depend on the order of
``TOPICS`` and on phrase weighting, both of which are easy to break while
editing keyword lists — hence the table below, drawn from real topics.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_topics.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from web.topics import (  # noqa: E402
    DEFAULT_TOPIC,
    TOPICS,
    TOPICS_BY_SLUG,
    classify_topic,
)

# (topic text, expected slug) — mostly real rows from db/chat.db.
_CASES: tuple[tuple[str, str], ...] = (
    # Unambiguous single-subject topics.
    ("The Fermi Paradox", "space"),
    ("Are we living in a simulation", "philosophy"),
    ("Will lab-grown organs become common within 20 years?", "bio"),
    ("Has social media made people less happy overall?", "society"),
    ("Are AI coding agents overhyped?", "ai"),
    ("Should restaurants be required to disclose when a dish was designed by AI?", "food"),
    ("Is human extinction something we should actually worry about?", "philosophy"),
    # AI shows up in most topics — the *other* subject should win.
    ("AI in Cyber Warfare", "security"),
    ("AI and Quantum Impacts on Global Finance in 2026", "finance"),
    ("The future of tech jobs in the world of AI", "work"),
    ("Should governments require licenses for advanced AI development?", "policy"),
    (
        "Should the world ban fully autonomous AI weapons that can select and "
        "kill human targets without human approval?",
        "security",
    ),
    (
        "Is pop culture stuck in a creativity crisis - drowning in reboots, AI "
        "slop, and algorithm-chasing sameness?",
        "culture",
    ),
    # ...but a topic that is *only* about AI still lands on ai.
    (
        "Open Source AI vs Closed AI - Innovation speed; safety control; "
        "national competitiveness; business models.",
        "ai",
    ),
    # Phrase weight beats a bare word: "stock market" (finance) outscores the
    # lone "extraterrestrials" (space) and "governments" (policy).
    (
        "What would be the impact on the global stock market if governments "
        "admitted that extraterrestrials are real and are among us?",
        "finance",
    ),
    # Space beats policy: "space tourism" (2 words) + "space" > "regulated".
    ("Should space tourism be regulated more heavily?", "space"),
    # Society beats policy: "social media" + "children" > "banned".
    ("Should children under 16 be banned from social media?", "society"),
    # Hyphens are word separators, so "gene-editing" matches "gene editing".
    ("Should gene-editing be allowed for non-medical enhancements?", "bio"),
    ("Should gene editing be allowed for non-medical enhancements?", "bio"),
)


def test_known_topics_classify_as_expected() -> None:
    for text, slug in _CASES:
        got = classify_topic(text).slug
        assert got == slug, f"{text!r} → {got!r}, expected {slug!r}"


def test_unmatched_topic_falls_back_to_default() -> None:
    for text in ("How credible is Bob Lazar?", "Untitled", "?!?", "   "):
        assert classify_topic(text).slug == DEFAULT_TOPIC.slug


def test_missing_topic_falls_back_to_default() -> None:
    assert classify_topic(None).slug == DEFAULT_TOPIC.slug
    assert classify_topic("").slug == DEFAULT_TOPIC.slug


def test_classification_is_case_insensitive() -> None:
    for text in ("the fermi paradox", "THE FERMI PARADOX", "The Fermi Paradox"):
        assert classify_topic(text).slug == "space"


def test_keywords_match_whole_words_only() -> None:
    # policy's "ban" must not fire inside "banana", culture's "art" must not
    # fire inside "artificial", and finance's "tax" must not fire inside "taxi".
    for text in ("Is a banana a berry?", "artificial", "Should taxis exist?"):
        assert classify_topic(text).slug == DEFAULT_TOPIC.slug, text
    # ...but the full phrase does match.
    assert classify_topic("artificial intelligence").slug == "ai"


def test_slugs_are_unique_and_indexed() -> None:
    slugs = [t.slug for t in TOPICS] + [DEFAULT_TOPIC.slug]
    assert len(slugs) == len(set(slugs)), "duplicate topic slug"
    assert set(TOPICS_BY_SLUG) == set(slugs)


def test_every_topic_is_renderable() -> None:
    # Slugs land in a CSS class and glyphs are inlined into SVG unescaped, so
    # keep them boring: no markup, no quotes to break out of an attribute.
    for topic in (*TOPICS, DEFAULT_TOPIC):
        assert re.fullmatch(r"[a-z][a-z0-9-]*", topic.slug), topic.slug
        assert topic.label and '"' not in topic.label, topic.slug
        assert topic.glyph.startswith("<") and topic.glyph.endswith(">"), topic.slug
        for colour in (topic.ink, topic.ink_2):
            assert re.fullmatch(r"#[0-9a-f]{6}", colour), f"{topic.slug}: {colour}"


def test_every_topic_has_keywords() -> None:
    for topic in TOPICS:
        assert topic.keywords, f"{topic.slug} can never be selected"
        assert len(set(topic.keywords)) == len(topic.keywords), \
            f"{topic.slug} has duplicate keywords"


def test_each_topic_wins_on_its_own_keywords() -> None:
    """Every keyword should at least classify as *its* topic in isolation.

    Overlap is expected (a keyword can appear in two lists), but a keyword that
    loses on its own text is dead weight and usually signals a copy-paste slip.
    """
    for topic in TOPICS:
        for keyword in topic.keywords:
            got = classify_topic(keyword)
            assert got.slug == topic.slug, \
                f"{topic.slug}: bare keyword {keyword!r} classified as {got.slug!r}"


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
