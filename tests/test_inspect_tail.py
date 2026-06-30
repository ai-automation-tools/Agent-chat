r"""Regression tests for ``inspect_conversations.py tail`` completion behaviour.

Pins the fix for the "tail prints '(conversation complete)' prematurely" bug:
the loop must keep polling while the conversation is ``active`` and only declare
completion when the row's ``status`` is literally ``'complete'`` — never because
a poll happened to return no new messages. Also covers the ``end_reason`` now
surfaced in the completion banner.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_inspect_tail.py

Uses isolated temp DBs — never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import io
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import inspect_conversations as ic  # noqa: E402

_SCHEMA = """
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY, topic TEXT, participants TEXT, mode TEXT,
    max_turns INTEGER, current_turn TEXT, status TEXT, end_reason TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER,
    sender TEXT, content TEXT, signal TEXT, created_at TEXT
);
"""


def _row(status: str, end_reason: str | None) -> sqlite3.Row:
    """A faithful sqlite3.Row with status/end_reason for unit-testing the guard."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (status TEXT, end_reason TEXT)")
    conn.execute("INSERT INTO t VALUES (?, ?)", (status, end_reason))
    return conn.execute("SELECT status, end_reason FROM t").fetchone()


def _seed_db(path: Path, *, status: str = "active",
             end_reason: str | None = None,
             msgs: tuple[tuple[str, str], ...] = ()) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO conversations (id, topic, participants, mode, max_turns, "
            "status, end_reason, created_at, updated_at) "
            "VALUES (1, 't', '[]', 'turns', 8, ?, ?, 'now', 'now')",
            (status, end_reason),
        )
        for sender, content in msgs:
            conn.execute(
                "INSERT INTO messages (conversation_id, sender, content, created_at) "
                "VALUES (1, ?, ?, 'now')",
                (sender, content),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. The completion guard, in isolation (the heart of the bug)
# ---------------------------------------------------------------------------

def test_completion_line_active_returns_none():
    # An active conversation must NEVER yield a completion banner — this is the
    # exact invariant the premature-'(conversation complete)' bug violated.
    assert ic._completion_line(_row("active", None)) is None
    assert ic._completion_line(_row("active", "ignored while active")) is None


def test_completion_line_complete_without_reason():
    assert ic._completion_line(_row("complete", None)) == "(conversation complete)"


def test_completion_line_complete_with_reason():
    line = ic._completion_line(_row("complete", "max_turns reached (8 per agent)"))
    assert line == "(conversation complete — max_turns reached (8 per agent))"


# ---------------------------------------------------------------------------
# 2. cmd_tail end-to-end (temp DB)
# ---------------------------------------------------------------------------

def test_cmd_tail_missing_conversation_returns_1():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = Path(d) / "chat.db"
        _seed_db(db)  # only conversation #1 exists
        conn = ic.connect(str(db))
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ic.cmd_tail(conn, 999, 0.01)
            assert rc == 1
            assert "(no conversation #999)" in buf.getvalue()
        finally:
            conn.close()


def test_cmd_tail_prints_messages_and_reason_on_complete():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = Path(d) / "chat.db"
        _seed_db(db, status="complete", end_reason="signal=done from codex",
                 msgs=(("claude-code", "opening"), ("codex", "rebuttal")))
        conn = ic.connect(str(db))
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ic.cmd_tail(conn, 1, 0.01)
            out = buf.getvalue()
            assert rc == 0
            assert "opening" in out and "rebuttal" in out
            assert "(conversation complete — signal=done from codex)" in out
        finally:
            conn.close()


def test_cmd_tail_does_not_complete_while_active():
    """The regression test for the reported bug: tail must keep polling an active
    conversation (even when no new messages arrive) and only stop once the row
    flips to ``complete``. This fails against any 'exit on a quiet poll'
    implementation."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = Path(d) / "chat.db"
        _seed_db(db, status="active", msgs=(("claude-code", "first"),))
        result: dict[str, object] = {}

        def run() -> None:
            conn = ic.connect(str(db))
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result["rc"] = ic.cmd_tail(conn, 1, 0.02)
                result["out"] = buf.getvalue()
            finally:
                conn.close()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        # Several poll intervals elapse with the conversation still active and no
        # new messages — tail must NOT have declared completion.
        time.sleep(0.4)
        assert t.is_alive(), "cmd_tail exited while the conversation was still active"

        # Flip to complete from a separate connection (mimics the MCP server / a
        # web force-stop in another process).
        w = sqlite3.connect(str(db))
        try:
            w.execute(
                "UPDATE conversations SET status='complete', "
                "end_reason='max_turns reached (8 per agent)' WHERE id=1"
            )
            w.commit()
        finally:
            w.close()

        t.join(timeout=3.0)
        assert not t.is_alive(), "cmd_tail did not stop after status became complete"
        assert result.get("rc") == 0
        assert "(conversation complete — max_turns reached (8 per agent))" in \
            str(result.get("out", ""))


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
