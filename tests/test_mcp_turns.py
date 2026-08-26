r"""Tests for the MCP server's turn engine — rotation, caps, and stop signals.

The headline case is the **cap race**. `evaluate_stop()` used to end a
conversation as soon as the *first* agent reached `max_turns`, which in a
round-robin is always agent 1 — so every later seat silently lost a turn. Run
#51 ended at 28 messages for "10 per agent" across three agents: 10 + 9 + 9.

That was cosmetic until collaborations started producing deliverables. A lead
seated late is briefed to post the artifact on its final turn, and that is
precisely the turn the old rule took away: `signal='result'` never landed, the
transcript looked complete, and nothing anywhere reported a problem.

Fixing the stop rule alone would have deadlocked the rotation — the pointer
would land on a spent agent, every send would be rejected, and the pointer
would never advance. So `next_turn_agent()` skips spent seats, and the two
halves are tested together here.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_mcp_turns.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import agent_chat_mcp as mcp  # noqa: E402
from orchestrator import seeding  # noqa: E402


# ---------------------------------------------------------------------------
# Harness — a real SQLite file and the real tool functions. No mocks: the
# multi-process WAL behaviour is the thing this repo is, and a mocked cursor
# would test the mock.
# ---------------------------------------------------------------------------

def _seed(tmp: Path, participants: list[str], max_turns: int,
          mode: str = "turns", first: str | None = None) -> tuple[str, int]:
    db = tmp / "chat.db"
    res = seeding.seed_conversation(
        db_path=str(db), topic="Turn engine under test",
        participants=participants, mode=mode, max_turns=max_turns,
        first=first, preset="plan", tone="Be brief.",
        conv_type="collaborate",
    )
    mcp.DB_PATH = str(db)
    return str(db), res.conversation_id


def _send(agent: str, text: str = "hi", signal: str | None = None) -> dict:
    mcp.AGENT_ID = agent
    return json.loads(asyncio.run(
        mcp.send_message(mcp.SendMessageInput(content=text, signal=signal))))


def _turn_state(agent: str) -> dict:
    mcp.AGENT_ID = agent
    return json.loads(asyncio.run(mcp.get_my_turn(mcp.GetMyTurnInput())))


def _row(db: str, cid: int) -> sqlite3.Row:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    finally:
        conn.close()


def _senders(db: str, cid: int) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute(
            "SELECT sender FROM messages WHERE conversation_id=? ORDER BY id", (cid,))]
    finally:
        conn.close()


def _drive(db: str, cid: int, limit: int = 200) -> None:
    """Play the conversation out by always sending as whoever's turn it is."""
    for _ in range(limit):
        row = _row(db, cid)
        if row["status"] != "active" or not row["current_turn"]:
            return
        _send(row["current_turn"])
    raise AssertionError("rotation did not terminate — likely a deadlock")


# ---------------------------------------------------------------------------
# The cap race
# ---------------------------------------------------------------------------

def test_every_agent_gets_its_full_turn_count() -> None:
    """The regression. Two agents, 2 turns each = 4 messages, not 3."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=2)
        _drive(db, cid)
        assert Counter(_senders(db, cid)) == {"a": 2, "b": 2}
        assert _row(db, cid)["status"] == "complete"


def test_three_agents_all_reach_the_cap() -> None:
    """Run #51's shape: 3 agents x 10 turns should be 30 messages, not 28."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b", "c"], max_turns=10)
        _drive(db, cid)
        counts = Counter(_senders(db, cid))
        assert counts == {"a": 10, "b": 10, "c": 10}, counts
        assert sum(counts.values()) == 30


def test_the_last_seat_can_still_post_a_deliverable() -> None:
    """Why the cap race mattered: a lead seated late is briefed to post the
    artifact on its final turn, and that was the turn being taken away."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=2)
        _send("a"); _send("b"); _send("a")
        out = _send("b", "# The plan", signal="result")
        assert out["status"] == "complete", out

        conn = sqlite3.connect(db)
        try:
            signals = [r[0] for r in conn.execute(
                "SELECT signal FROM messages WHERE conversation_id=?", (cid,))]
        finally:
            conn.close()
        assert "result" in signals


def test_conversation_stays_active_until_the_last_agent_is_spent() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=2)
        _send("a"); _send("b"); _send("a")
        assert _row(db, cid)["status"] == "active"     # 'a' is spent, 'b' isn't
        _send("b")
        assert _row(db, cid)["status"] == "complete"


# ---------------------------------------------------------------------------
# Rotation must skip spent seats, or fixing the stop rule deadlocks it
# ---------------------------------------------------------------------------

def test_next_turn_agent_skips_spent_seats() -> None:
    seats = ["a", "b", "c"]
    assert mcp.next_turn_agent(seats, "a") == "b"
    assert mcp.next_turn_agent(seats, "a", {"b"}) == "c"
    assert mcp.next_turn_agent(seats, "a", {"b", "c"}) == "a"
    assert mcp.next_turn_agent(seats, "a", {"a", "b", "c"}) is None


def test_uneven_counts_do_not_deadlock_the_rotation() -> None:
    """The failure mode that made the two halves inseparable: with 'a' already
    spent, the pointer must jump over it instead of parking there forever."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b", "c"], max_turns=2)
        # Burn 'a' early while leaving b and c behind.
        _send("a")                      # turn -> b
        _send("b")                      # turn -> c
        _send("c")                      # turn -> a
        _send("a")                      # 'a' now spent; turn must skip to b
        assert _row(db, cid)["current_turn"] == "b"
        _drive(db, cid)                 # raises if the pointer ever parks
        counts = Counter(_senders(db, cid))
        assert counts == {"a": 2, "b": 2, "c": 2}, counts


def test_spent_agent_is_told_why_it_is_waiting() -> None:
    """A skipped seat would otherwise sit in a plain 'wait' that never becomes
    its turn, with no way to tell that from an ordinary wait."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b", "c"], max_turns=1)
        _send("a")
        state = _turn_state("a")
        assert state["status"] == "wait"
        assert state["turns_remaining"] == 0
        assert "no turns left" in state.get("message", "").lower() or \
               "used all" in state.get("message", "").lower(), state.get("message")


def test_out_of_turn_send_is_rejected() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=3, first="a")
        out = _send("b")
        assert out["status"] == "error"
        assert "not your turn" in out["message"].lower()
        assert _senders(db, cid) == []


def test_over_cap_send_does_not_promise_to_close_the_room() -> None:
    """Reaching YOUR cap no longer ends the conversation, so the rejection must
    not say it does — the other seats carry on without you."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=1, mode="continuous")
        _send("a")
        out = _send("a")
        assert out["status"] == "error"
        assert "being closed" not in out["message"].lower()
        assert "no turns left" in out["message"].lower()
        assert _row(db, cid)["status"] == "active"      # 'b' hasn't spoken


# ---------------------------------------------------------------------------
# Stop signals — unchanged by the cap fix, and worth pinning that they are
# ---------------------------------------------------------------------------

def test_done_ends_immediately_regardless_of_caps() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=10)
        out = _send("a", "we're finished", signal="done")
        assert out["status"] == "complete"
        assert _row(db, cid)["end_reason"] == "agent signaled done"


def test_blocked_ends_immediately() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=10)
        _send("a", "stuck", signal="blocked")
        assert _row(db, cid)["end_reason"] == "agent signaled blocked"


def test_result_is_not_a_stop_signal() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=10)
        out = _send("a", "# draft", signal="result")
        assert out["status"] == "wait", out
        assert _row(db, cid)["status"] == "active"


def test_invalid_signal_is_rejected_before_the_insert() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=10)
        out = _send("a", "hi", signal="finished")
        assert out["status"] == "error"
        assert _senders(db, cid) == []


# ---------------------------------------------------------------------------
# Continuous mode
# ---------------------------------------------------------------------------

def test_continuous_mode_has_no_turn_pointer_and_never_blocks_a_send() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=3, mode="continuous")
        assert _row(db, cid)["current_turn"] is None
        for agent in ("b", "b", "a"):
            assert _send(agent)["status"] == "your_turn"
        assert _senders(db, cid) == ["b", "b", "a"]


def test_continuous_mode_also_waits_for_every_agent() -> None:
    """One fast agent must not close the room on a slower one — the same rule
    as turns mode, and the reason brainstorm sets continuous on purpose."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=2, mode="continuous")
        _send("a"); _send("a")
        assert _row(db, cid)["status"] == "active"
        _send("b"); _send("b")
        assert _row(db, cid)["status"] == "complete"


# ---------------------------------------------------------------------------
# No conversation
# ---------------------------------------------------------------------------

def test_no_conversation_is_reported_not_raised() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td), ["a", "b"], max_turns=2)
        assert _turn_state("stranger")["status"] == "no_conversation"
        assert _send("stranger")["status"] == "error"


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
