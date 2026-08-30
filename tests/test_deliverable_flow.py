r"""Tests for the five process fixes drawn from live run #54.

#54 was the first collaboration aimed at a *different* repo (Edge-Radar). It
produced a good artifact, and in producing it showed five things the process
got away with rather than got right:

1. A 16.8-minute turn (the facilitator writing a 23k-char deliverable) while
   every other turn took under 1.5 minutes — indistinguishable, from the web
   UI, from a hung agent.
2. Two ``signal='result'`` messages with nothing marking which was current.
3. A collaborator ending the run with ``done``. It happened to fire one message
   *after* the final result; nothing enforced that ordering.
4. Role docs telling every seat it works on "this repo" while the topic named
   another one.
5. An artifact written to a file outside the conversation, with no record of
   where it went.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_deliverable_flow.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import agent_chat_mcp as mcp  # noqa: E402
from orchestrator import export, seeding  # noqa: E402

_NOW = "2026-08-26T22:00:00+00:00"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _seed(tmp: Path, conv_type: str = "collaborate", max_turns: int = 6) -> tuple[str, int]:
    db = tmp / "chat.db"
    kw = {"preset": "plan", "tone": "Be brief."} if conv_type == "collaborate" else {}
    res = seeding.seed_conversation(
        db_path=str(db), topic="Deliverable flow under test",
        participants=["claude-code", "codex"], mode="turns",
        max_turns=max_turns, conv_type=conv_type, **kw)
    mcp.DB_PATH = str(db)
    return str(db), res.conversation_id


def _send(agent: str, text: str = "hi", signal: str | None = None) -> dict:
    mcp.AGENT_ID = agent
    return json.loads(asyncio.run(
        mcp.send_message(mcp.SendMessageInput(content=text, signal=signal))))


def _status(db: str, cid: int) -> str:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT status FROM conversations WHERE id=?", (cid,)).fetchone()[0]
    finally:
        conn.close()


def _count(db: str, cid: int) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (cid,)).fetchone()[0]
    finally:
        conn.close()


def _msgs(n_results: int = 2) -> list[dict]:
    """A synthetic transcript with `n_results` result messages."""
    out: list[dict] = [{"id": 1, "sender": "a", "signal": None, "created_at": _NOW,
                        "content": "opening"}]
    for i in range(n_results):
        out.append({"id": 10 + i, "sender": "a", "signal": "result",
                    "created_at": f"2026-08-26T22:{10 + i:02d}:00+00:00",
                    "content": f"# draft {i}"})
    return out


# ---------------------------------------------------------------------------
# 1. Which result counts
# ---------------------------------------------------------------------------

def test_last_result_wins() -> None:
    ms = _msgs(3)
    assert export.final_result(ms)["id"] == 12
    assert export.superseded_result_ids(ms) == {10, 11}


def test_a_single_result_is_never_superseded() -> None:
    ms = _msgs(1)
    assert export.final_result(ms)["id"] == 10
    assert export.superseded_result_ids(ms) == set()


def test_no_result_at_all() -> None:
    assert export.final_result(_msgs(0)) is None
    assert export.superseded_result_ids(_msgs(0)) == set()


def test_export_overview_names_the_final_result() -> None:
    """The ONLY place the export says which result is current. The transcript
    heading is deliberately untouched — docs/App/export-format.md says it
    *ends* with the `signal=` span, so a consumer may anchor on end-of-line."""
    conv = {"id": 7, "topic": "t", "status": "complete", "mode": "turns",
            "max_turns": 8, "participants": ["a", "b"], "created_at": _NOW,
            "updated_at": _NOW, "conv_type": "collaborate"}
    out = export.render_export_overview(conv, {}, _msgs(2))
    assert "| Result | 2026-08-26 22:11:00 (2 posted; earlier ones superseded) |" in out

    single = export.render_export_overview(conv, {}, _msgs(1))
    assert "| Result | 2026-08-26 22:10:00 |" in single           # no count noise
    assert "superseded" not in single


def test_export_overview_omits_the_row_without_a_result() -> None:
    """A debate produces no artifact; the row must not appear at all."""
    conv = {"id": 7, "topic": "t", "status": "complete", "mode": "turns",
            "max_turns": 8, "participants": ["a", "b"], "created_at": _NOW,
            "updated_at": _NOW, "conv_type": "debate"}
    assert "| Result |" not in export.render_export_overview(conv, {}, _msgs(0))


def test_transcript_headings_are_untouched() -> None:
    """Regression guard on the export contract: three external consumers parse
    these headings, and they must not gain a suffix."""
    data = {"conversation": {"id": 7, "topic": "t", "status": "complete",
                             "mode": "turns", "max_turns": 8,
                             "participants": ["a"], "created_at": _NOW,
                             "updated_at": _NOW},
            "messages": _msgs(2)}
    md = export.render_export_markdown(data)
    heads = [ln for ln in md.split("\n") if ln.startswith("## ")]
    assert sum(1 for h in heads if h.endswith("`signal=result`")) == 2
    assert "superseded" not in md


def test_reader_collapses_superseded_results() -> None:
    from web.render.conversations import _render_message
    ms = _msgs(2)
    sup = export.superseded_result_ids(ms)
    draft = _render_message(ms[1], {}, sup)
    final = _render_message(ms[2], {}, sup)
    assert "msg-superseded" in draft and "superseded draft" in draft
    assert "msg-superseded" not in final
    assert "signal-superseded" in draft and "signal-superseded" not in final
    # The draft is collapsed, not dropped: its body is still in the page.
    assert "draft 0" in draft


def _reader(status: str, msgs: list[dict], conv_type: str = "debate") -> str:
    from web import db as web_db
    from web.render.conversations import _render_conversation_main
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        web_db.set_db_path(str(Path(td) / "chat.db"))
        web_db.db_init()
        conv = {"id": 1, "topic": "t", "mode": "turns", "max_turns": 8,
                "participants": ["a", "b"], "created_at": _NOW, "updated_at": _NOW,
                "current_turn": "a", "conv_type": conv_type, "status": status}
        return _render_conversation_main({"conversation": conv, "messages": msgs}, [], False)


def test_sse_path_demotes_earlier_results_too() -> None:
    """A live run must end up looking like a reload of the same run."""
    html = _reader("active", _msgs(1))
    assert "demoteEarlierResults" in html
    assert "signal-superseded" in html


# ---------------------------------------------------------------------------
# 2. A non-lead may not end a deliverable run before the deliverable exists
# ---------------------------------------------------------------------------

def test_collaborator_done_is_refused_before_any_result() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td))
        _send("claude-code", "Opening.")
        out = _send("codex", "I think we're done.", signal="done")
        assert out["status"] == "error"
        assert "has not posted one" in out["message"]
        assert _status(db, cid) == "active"
        assert _count(db, cid) == 1          # refused before the insert


def test_collaborator_done_is_allowed_once_a_result_exists() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td))
        _send("claude-code", "Opening.")
        _send("codex", "My half.")
        _send("claude-code", "# The plan", signal="result")
        assert _send("codex", "Agreed.", signal="done")["status"] == "complete"
        assert _status(db, cid) == "complete"


def test_the_lead_may_always_end_it() -> None:
    """The seat that owns the artifact is the seat allowed to say there won't
    be one."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td))
        assert _send("claude-code", "Not viable.", signal="done")["status"] == "complete"


def test_blocked_is_never_restricted() -> None:
    """An agent that cannot continue must always be able to say so."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td))
        _send("claude-code", "Opening.")
        assert _send("codex", "I'm stuck.", signal="blocked")["status"] == "complete"


def test_debate_and_podcast_are_untouched() -> None:
    """The guard keys on produces_deliverable, so a transcript type keeps the
    old any-seat-may-stop behaviour."""
    for conv_type in ("debate", "podcast"):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            db, cid = _seed(Path(td), conv_type=conv_type)
            _send("claude-code", "Opening.")
            assert _send("codex", "Enough.", signal="done")["status"] == "complete", conv_type


def test_guard_is_inert_without_recorded_roles() -> None:
    """A row seeded before participant_roles existed has no lead to protect;
    it must not become un-endable."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db, cid = _seed(Path(td))
        conn = sqlite3.connect(db, isolation_level=None)
        conn.execute("UPDATE conversations SET participant_roles=NULL WHERE id=?", (cid,))
        conn.close()
        _send("claude-code", "Opening.")
        assert _send("codex", "Enough.", signal="done")["status"] == "complete"


# ---------------------------------------------------------------------------
# 3. Quiet-for indicator
# ---------------------------------------------------------------------------

def test_quiet_threshold_scales_with_the_conversation() -> None:
    """A fixed alarm cries wolf on a debate and sleeps through a slow
    collaboration, so the bar is 3x this run's own median gap."""
    slow = [{"id": i, "created_at": f"2026-08-26T22:{i * 10:02d}:00+00:00"} for i in range(5)]
    assert export.quiet_threshold_seconds(slow) == 1800.0       # 10-min gaps -> 30 min


def test_quiet_threshold_has_a_floor() -> None:
    """Sub-second gaps must not produce a bar that trips on every pause."""
    fast = [{"id": i, "created_at": f"2026-08-26T22:00:{i:02d}+00:00"} for i in range(6)]
    assert export.quiet_threshold_seconds(fast) == 240.0


def test_quiet_threshold_survives_junk() -> None:
    assert export.quiet_threshold_seconds([]) == 240.0
    assert export.quiet_threshold_seconds([{"created_at": None}]) == 240.0
    assert export.quiet_threshold_seconds([{"created_at": "not a date"}]) == 240.0


def test_quiet_badge_renders_only_for_an_active_run() -> None:
    msgs = [{"id": 1, "sender": "a", "signal": None, "created_at": _NOW, "content": "hi"}]
    live = _reader("active", msgs)
    assert 'id="quiet-badge"' in live
    assert 'data-bar="240"' in live
    assert "tickQuiet" in live
    assert 'id="quiet-badge"' not in _reader("complete", msgs)


# ---------------------------------------------------------------------------
# 4 + 5. Briefs and role docs
# ---------------------------------------------------------------------------

def test_wait_for_turn_default_is_long_enough_for_a_real_turn() -> None:
    """60s cost ~17 wake-ups across #54's 16.8-minute artifact turn."""
    assert mcp.WaitForTurnInput().timeout_seconds == 180


def test_collaborator_brief_matches_the_enforced_rule() -> None:
    """The brief used to say 'do not signal done early' with nothing behind it.
    Now the server refuses — the brief has to say what actually happens."""
    brief = mcp._ROLE_BRIEFS["collaborator"]
    assert "refuses it" in brief
    assert "blocked" in brief


def test_facilitator_brief_asks_where_the_artifact_went() -> None:
    """#54's artifact was written into another repo and nothing recorded it."""
    brief = mcp._ROLE_BRIEFS["facilitator"]
    assert "with the path" in brief
    assert "transcript is not the delivery" in brief.lower()


def test_role_docs_do_not_claim_every_run_is_about_this_repo() -> None:
    clis = Path(__file__).resolve().parent.parent / "agents" / "CLIs"
    # Only the seat's own role doc — glob one level, never rglob: each seat
    # folder also holds a junctioned skills/ tree full of unrelated Markdown.
    docs = [p for p in clis.glob("*/*.md") if p.name != "MCP-NOTE.md"]
    assert len(docs) == 5, [p.name for p in docs]
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert "The topic wins." in text, doc
        assert "full-stack developer" in text, doc


def test_a_skeptic_is_a_non_lead_and_inherits_the_done_guard() -> None:
    """The guard keys on "is this the lead", not on the member role, so the
    seat added by the extra-roles work is covered without touching it. A
    skeptic that decides the plan is doomed argues in prose; it does not get to
    close a run that produced nothing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Path(td) / "chat.db"
        res = seeding.seed_conversation(
            db_path=str(db), topic="Skeptic under test",
            participants=["claude-code", "codex", "antigravity"], mode="turns",
            max_turns=6, conv_type="collaborate", preset="plan",
            tone="Be brief.",
            participant_roles={"claude-code": "facilitator",
                               "antigravity": "skeptic"})
        mcp.DB_PATH = str(db)
        _send("claude-code", "Opening.")
        _send("codex", "My half.")
        out = _send("antigravity", "This can't work.", signal="done")
        assert out["status"] == "error"
        assert "has not posted one" in out["message"]
        assert _status(str(db), res.conversation_id) == "active"


def test_skeptic_brief_says_what_it_is_for_and_what_it_is_not() -> None:
    """The brief is the ONLY guidance a hand-seeded run carries. It has to say
    the two things that make the seat useful rather than obstructive: be
    specific, and don't manufacture an objection."""
    brief = mcp._ROLE_BRIEFS["skeptic"]
    assert "strongest version" in brief
    assert "manufacturing an objection" in brief
    # And it is bound by the same rule the server enforces on collaborators.
    assert "do not signal='done' before the facilitator has posted a result" in brief


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
