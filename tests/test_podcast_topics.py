r"""Tests for ``docs/Chat-Topics/Podcast-Topics.md`` — the podcast topic library.

The file is content, but it has a shape something will parse: a future podcast
launcher is meant to reuse ``debate.ps1``'s topic parser with ``Guests`` in
place of ``Debaters``. These cases pin that shape, keep every guest count
inside what a podcast seats, and keep the topics interview-shaped. A yes/no
proposition ("Should X…?", "Is X…?") is the debate library's job, and the whole
reason this file exists is that those make poor interviews.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_podcast_topics.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator.conv_types import CONV_TYPES  # noqa: E402

_LIBRARY = _ROOT / "docs" / "Chat-Topics" / "Podcast-Topics.md"
# Same regexes as debate.ps1's $rxTopic / $rxCount, with the one word swapped.
_RX_TOPIC = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
_RX_COUNT = re.compile(r"^\s*-\s*Guests:\s*(\d+)\s*$")
# Openers that make a topic a yes/no proposition rather than an interview.
_PROPOSITION = re.compile(
    r"^(should|is|are|will|does|do|did|has|have|can|could|would)\b", re.I
)


def _parse() -> list[tuple[int, str, int | None]]:
    lines = _LIBRARY.read_text(encoding="utf-8").splitlines()
    topics: list[tuple[int, str, int | None]] = []
    for i, line in enumerate(lines):
        mt = _RX_TOPIC.match(line)
        if not mt:
            continue
        count = None
        for nxt in lines[i + 1 : i + 4]:
            if not nxt.strip():
                continue
            mc = _RX_COUNT.match(nxt)
            count = int(mc.group(1)) if mc else None
            break
        topics.append((int(mt.group(1)), mt.group(2).replace("✅", "").strip(), count))
    return topics


def test_numbering_is_contiguous() -> None:
    numbers = [n for n, _, _ in _parse()]
    assert numbers, "parsed 0 topics"
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def test_every_topic_has_a_guest_count_a_podcast_can_seat() -> None:
    podcast = CONV_TYPES["podcast"]
    for n, title, count in _parse():
        assert count is not None, f"#{n} {title!r} has no '- Guests: N' line"
        assert podcast.min_members <= count <= podcast.max_members, (
            f"#{n} asks for {count} guests; a podcast seats "
            f"{podcast.min_members}-{podcast.max_members}"
        )


def test_topics_are_open_questions_not_propositions() -> None:
    for n, title, _ in _parse():
        assert title.endswith("?"), f"#{n} {title!r} is not a question"
        assert not _PROPOSITION.match(title), f"#{n} {title!r} reads as a yes/no proposition"


def test_titles_are_unique() -> None:
    titles = [t.lower() for _, t, _ in _parse()]
    assert len(titles) == len(set(titles))


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
