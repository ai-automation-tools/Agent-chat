r"""Tests for the conversation-type model — ``conv_type`` + ``participant_roles``.

Three things here are easy to break and expensive to notice:

1. **The backfill.** ``conv_type`` is ``NOT NULL DEFAULT 'debate'``, and the
   ALTER TABLE default is the only thing that marks every pre-existing row as a
   debate. A migration that lost the default would leave the column NULL and
   every old conversation would fall out of the Debates filter.
2. **Column parity.** ``conv_type`` has to reach the Fly mirror, which means it
   must appear in the table, in ``web.db._CONV_COLUMNS``, *and* in
   ``scripts/db_sync.py:CONV_COLUMNS``. Miss the third and the column silently
   never syncs; miss the first and ``/api/ingest`` 500s.
3. **Seat rules.** One host, at most five seats, guests within the type's
   bounds — enforced in ``seed_conversation`` so every caller inherits it.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_conv_types.py
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator import export, seeding  # noqa: E402
from orchestrator.conv_types import (  # noqa: E402
    CONV_TYPES,
    DEFAULT_CONV_TYPE,
    MAX_PARTICIPANTS,
    lead_of,
    parse_roles,
    role_label,
    type_label,
    validate_roles,
)
from web import db as web_db  # noqa: E402


def _load_db_sync():
    """Import scripts/db_sync.py by path (it's a script, not a package member)."""
    spec = importlib.util.spec_from_file_location(
        "_db_sync_under_test", _ROOT / "scripts" / "db_sync.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # db_sync defines @dataclass types, and dataclasses resolves annotations via
    # sys.modules[cls.__module__] — so the module has to be registered first.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _seed(db_path: str, **kw):
    """seed_conversation with the boring arguments filled in."""
    kw.setdefault("topic", "T")
    kw.setdefault("mode", "turns")
    kw.setdefault("max_turns", 2)
    return seeding.seed_conversation(db_path=db_path, **kw)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

def test_default_type_is_debate_and_exists():
    assert DEFAULT_CONV_TYPE == "debate"
    assert DEFAULT_CONV_TYPE in CONV_TYPES


def test_every_type_is_internally_consistent():
    for key, t in CONV_TYPES.items():
        assert t.key == key, f"{key}: key field disagrees with its dict key"
        assert t.lead_role != t.member_role, f"{key}: lead and member share a role"
        assert 1 <= t.min_members <= t.max_members
        # The lead occupies a seat, so members can never fill the whole room
        # for a type that requires one.
        ceiling = MAX_PARTICIPANTS - (1 if t.lead_required else 0)
        assert t.max_members <= ceiling, f"{key}: max_members exceeds the seat cap"


def test_role_and_type_labels_tolerate_unknown_values():
    # Read paths render rows written by any build, including a newer one.
    assert type_label("fireside") == "fireside"
    assert type_label(None) == "Debate"
    assert role_label("fireside", "co-host") == "Co Host"
    assert role_label("podcast", None) == ""


def test_parse_roles_survives_garbage():
    assert parse_roles(None) == {}
    assert parse_roles("") == {}
    assert parse_roles("not json") == {}
    assert parse_roles("[1,2]") == {}
    assert parse_roles('{"a": "host"}') == {"a": "host"}


# ---------------------------------------------------------------------------
# Seat rules
# ---------------------------------------------------------------------------

def test_roles_default_from_seat_order():
    # A podcast needs a host, so the first seat takes it; a debate does not.
    assert validate_roles("podcast", ["a", "b"], None) == {"a": "host", "b": "guest"}
    assert validate_roles("debate", ["a", "b"], None) == {"a": "debater", "b": "debater"}


def test_naming_only_the_lead_is_enough():
    got = validate_roles("debate", ["a", "b", "c"], {"a": "moderator"})
    assert got == {"a": "moderator", "b": "debater", "c": "debater"}


def _expect_seed_error(fragment: str, **kw) -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        try:
            _seed(db, **kw)
        except seeding.SeedError as e:
            assert fragment in str(e), f"expected {fragment!r} in {str(e)!r}"
            return
    raise AssertionError(f"expected a SeedError containing {fragment!r}")


def test_seat_rules_are_enforced_at_seed_time():
    _expect_seed_error("at most 5 participants",
                       participants=list("abcdef"), conv_type="podcast")
    _expect_seed_error("takes one host",
                       participants=list("abc"), conv_type="podcast",
                       participant_roles={"a": "host", "b": "host"})
    _expect_seed_error("invalid role 'debater' for a podcast",
                       participants=list("ab"), conv_type="podcast",
                       participant_roles={"a": "host", "b": "debater"})
    _expect_seed_error("needs at least 2 debaters",
                       participants=list("ab"), conv_type="debate",
                       participant_roles={"a": "moderator"})
    _expect_seed_error("unknown conversation type",
                       participants=list("ab"), conv_type="fireside")
    _expect_seed_error("not a participant",
                       participants=list("ab"), participant_roles={"z": "moderator"})


def test_the_lead_must_speak_first():
    _expect_seed_error("must speak first",
                       participants=list("abc"), conv_type="podcast",
                       participant_roles={"b": "host"})


def test_a_full_podcast_seeds():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        r = _seed(db, participants=list("abcde"), conv_type="podcast",
                  participant_roles={"a": "host"})
        assert r.conv_type == "podcast"
        assert r.participant_roles == {
            "a": "host", "b": "guest", "c": "guest", "d": "guest", "e": "guest",
        }
        assert lead_of("podcast", r.participant_roles) == "a"


def test_seeding_writes_the_columns():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        cid = _seed(db, participants=["x", "y"], conv_type="podcast",
                    participant_roles={"x": "host"}).conversation_id
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT conv_type, participant_roles FROM conversations WHERE id=?",
            (cid,),
        ).fetchone()
        conn.close()
        assert row["conv_type"] == "podcast"
        assert json.loads(row["participant_roles"])["x"] == "host"


# ---------------------------------------------------------------------------
# The backfill
# ---------------------------------------------------------------------------

# The conversations table exactly as it stood before conv_type existed.
_PRE_CONV_TYPE_SCHEMA = """
CREATE TABLE conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    topic             TEXT NOT NULL,
    participants      TEXT NOT NULL,
    mode              TEXT NOT NULL,
    max_turns         INTEGER NOT NULL,
    current_turn      TEXT,
    status            TEXT NOT NULL,
    end_reason        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    preset            TEXT,
    kickoff_template  TEXT,
    participant_personas TEXT
);
"""


def test_migration_backfills_existing_rows_as_debates():
    """An old DB must come back with every row typed 'debate', not NULL."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        conn = sqlite3.connect(db, isolation_level=None)
        conn.executescript(_PRE_CONV_TYPE_SCHEMA)
        conn.execute(
            "INSERT INTO conversations (topic, participants, mode, max_turns, "
            "status, created_at, updated_at) VALUES "
            "('old debate', '[\"claude-code\",\"codex\"]', 'turns', 8, "
            "'complete', '2026-01-01', '2026-01-01')"
        )
        conn.close()

        web_db.set_db_path(db)
        web_db.db_init()

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM conversations").fetchone()
        conn.close()
        assert row["conv_type"] == "debate", "pre-existing row was not backfilled"
        assert row["participant_roles"] is None


def test_every_writer_declares_the_same_conversations_columns():
    """The four SCHEMA mirrors must agree on the conversations table.

    Compared by *creating* each one, so a typo in a column list is caught the
    same way SQLite would catch it, not by diffing strings.
    """
    import agent_chat_mcp

    sources = {
        "agent_chat_mcp.SCHEMA": agent_chat_mcp.SCHEMA,
        "web.db.SCHEMA": web_db.SCHEMA,
        "orchestrator.seeding.SCHEMA": seeding.SCHEMA,
    }
    shapes: dict[str, list[tuple]] = {}
    for name, schema in sources.items():
        conn = sqlite3.connect(":memory:")
        conn.executescript(schema)
        shapes[name] = [
            (r[1], r[2], r[3], r[4])  # name, type, notnull, default
            for r in conn.execute("PRAGMA table_info(conversations)")
        ]
        conn.close()
    first_name, first_shape = next(iter(shapes.items()))
    for name, shape in shapes.items():
        assert shape == first_shape, f"{name} disagrees with {first_name}"

    migrations = {
        "agent_chat_mcp": agent_chat_mcp._MIGRATIONS,
        "web.db": web_db._MIGRATIONS,
        "orchestrator.seeding": seeding._MIGRATIONS,
    }
    first_name, first_mig = next(iter(migrations.items()))
    for name, mig in migrations.items():
        assert mig == first_mig, f"{name}._MIGRATIONS disagrees with {first_name}"


def test_sync_carries_every_conversation_column():
    """web.db, db_sync.py, and the actual table must list the same columns.

    A column missing from ``scripts/db_sync.py`` never reaches the Fly mirror
    and nothing fails loudly — this is the check that notices.
    """
    db_sync = _load_db_sync()
    assert tuple(web_db._CONV_COLUMNS) == tuple(db_sync.CONV_COLUMNS), \
        "web.db._CONV_COLUMNS and scripts/db_sync.py:CONV_COLUMNS have drifted"

    conn = sqlite3.connect(":memory:")
    conn.executescript(web_db.SCHEMA)
    actual = [r[1] for r in conn.execute("PRAGMA table_info(conversations)")]
    conn.close()
    assert sorted(actual) == sorted(web_db._CONV_COLUMNS), \
        f"table has {sorted(actual)}, sync list has {sorted(web_db._CONV_COLUMNS)}"


# ---------------------------------------------------------------------------
# Roles reach the agents
# ---------------------------------------------------------------------------

def test_every_type_has_a_real_default_preset():
    from presets import PRESETS

    for key, t in CONV_TYPES.items():
        assert t.default_preset in PRESETS, \
            f"{key}: default_preset {t.default_preset!r} is not in src/presets.py"


def test_every_role_has_an_in_band_brief():
    """A role with no brief is a seat the agent is never told how to fill.

    ``_ROLE_BRIEFS`` is the only guidance a hand-seeded conversation carries —
    there's no launch prompt, and not every CLI loads the skills.
    """
    import agent_chat_mcp

    from orchestrator.conv_types import ALL_ROLES

    missing = ALL_ROLES - set(agent_chat_mcp._ROLE_BRIEFS)
    assert not missing, f"no _ROLE_BRIEFS entry for: {sorted(missing)}"


def test_the_launch_prompt_stays_role_agnostic():
    """`New-AgentPrompt` must not carry a second copy of the role guidance.

    It used to branch on $Role with one here-string per seat, duplicating
    ``_ROLE_BRIEFS``. That copy was why a new conversation type cost a
    PowerShell edit, and it could drift from what agents actually receive at
    runtime. The prompt now names the seat and points at get_kickoff()'s
    ``role_brief``, so this test guards the collapse rather than the branches:
    a per-role branch reappearing here means the duplication is back.
    """
    ps1 = (_ROOT / "scripts" / "lib" / "spawn-agents.ps1").read_text(encoding="utf-8")
    from orchestrator.conv_types import ALL_ROLES

    assert "role_brief" in ps1, \
        "the launch prompt must point the agent at get_kickoff()'s role_brief"
    assert "ValidateSet" not in ps1.split("function New-AgentPrompt")[1].split("\n}")[0], \
        "-Role is a free-form string; a ValidateSet re-couples PowerShell to the role set"
    for role in sorted(ALL_ROLES):
        assert f"$Role -eq '{role}'" not in ps1, (
            f"New-AgentPrompt branches on role {role!r} again — role guidance "
            "belongs in _ROLE_BRIEFS, which ships in-band"
        )


def test_result_is_a_legal_signal_and_does_not_end_a_conversation():
    """The deliverable rides the existing `signal` column, not a new one.

    ``maybe_complete`` must keep stopping on done/blocked only — a facilitator
    posting the result should still be able to be asked to revise it.
    """
    import agent_chat_mcp

    assert agent_chat_mcp.SIGNAL_RESULT == "result"
    stop = (agent_chat_mcp.SIGNAL_DONE, agent_chat_mcp.SIGNAL_BLOCKED)
    assert agent_chat_mcp.SIGNAL_RESULT not in stop
    src = (_SRC / "agent_chat_mcp.py").read_text(encoding="utf-8")
    assert "SIGNAL_DONE, SIGNAL_BLOCKED, SIGNAL_RESULT" in src, \
        "send_message must accept 'result' as a signal"


def test_only_a_deliverable_type_changes_its_kickoff():
    """A debate's and a podcast's kickoff body must be untouched by this feature.

    ``deliverable_clause`` is appended to the tone at seed time, so a
    regression here silently rewrites every debate's instructions.
    """
    for key, t in CONV_TYPES.items():
        clause = seeding.deliverable_clause(key, t.default_preset)
        if t.produces_deliverable:
            assert clause and "signal='result'" in clause, \
                f"{key} produces a deliverable but its kickoff never asks for one"
            assert t.deliverable_label, f"{key} has no deliverable_label to name it"
        else:
            assert clause == "", f"{key} produces no deliverable but got: {clause!r}"


def test_a_collaboration_seeds_with_a_facilitator_and_asks_for_the_artifact():
    from presets import deliverable_for

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "chat.db")
        res = _seed(
            db_path,
            participants=["claude-code", "codex", "antigravity"],
            conv_type="collaborate",
            preset="plan",
            tone="Work toward a concrete plan.",
        )
        assert res.conv_type == "collaborate"
        assert res.participant_roles == {
            "claude-code": "facilitator",
            "codex": "collaborator",
            "antigravity": "collaborator",
        }
        # The preset's artifact shape has to reach the agents, and the only
        # channel for it is the rendered kickoff body.
        assert deliverable_for("plan")[:30] in res.kickoff_rendered
        assert "signal='result'" in res.kickoff_rendered


def test_a_collaboration_needs_a_facilitator():
    _expect_seed_error(
        "needs a facilitator",
        participants=["claude-code", "codex"],
        conv_type="collaborate",
        participant_roles={"claude-code": "collaborator", "codex": "collaborator"},
    )


def test_every_sub_type_preset_names_its_artifact():
    """A preset offered for a deliverable-producing type must say what to make.

    Without a ``deliverable`` the facilitator falls back to a generic shape,
    which is legal but means the sub-type isn't actually a sub-type.
    """
    from presets import PRESETS, presets_for

    for key, t in CONV_TYPES.items():
        if not t.produces_deliverable:
            continue
        for name in presets_for(key):
            assert PRESETS[name].get("deliverable"), (
                f"preset {name!r} is offered for {key!r} but names no deliverable"
            )


def test_presets_for_filters_by_type_and_stays_advisory():
    from presets import PRESET_NAMES, presets_for

    assert presets_for("debate") == ("debate",)
    assert "brainstorm" in presets_for("collaborate")
    assert "podcast" not in presets_for("collaborate")
    # No conv_type given → everything, so a caller that doesn't care isn't
    # silently filtered.
    assert presets_for(None) == PRESET_NAMES


# sqlite3's context manager commits but does NOT close, and `web/db.py` uses
# `with _connect() as conn:` throughout — so a connection lingers until GC and
# Windows keeps the file locked. The API tests below therefore tolerate a failed
# temp-dir cleanup: they assert on behaviour, not on housekeeping.
_TMP = dict(ignore_cleanup_errors=True)


def _orchestrate(db_path: str, **payload):
    """POST /api/orchestrate in-process; returns (status, body dict)."""
    import asyncio
    import json as _json

    from web import db as web_db
    from web.api import orchestrate as api

    web_db.set_db_path(db_path)
    web_db.db_init()
    payload.setdefault("spawn", False)

    class _Req:
        async def json(self):
            return payload

    resp = asyncio.run(api.api_orchestrate(_Req()))
    return resp.status_code, _json.loads(resp.body.decode())


def _conv_row(db_path: str, cid: int) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return dict(conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone())
    finally:
        conn.close()


def test_a_member_lead_type_does_not_add_a_seat_the_operator_did_not_pick():
    """Two agents selected must mean a two-agent collaboration.

    A facilitator is one of the collaborators, so ``/orchestrate`` must not
    prepend a third seat the way it does for a debate moderator or podcast
    host. The regression this guards: picking claude-code + codex and getting
    antigravity dealt in as facilitator because the lead dropdown defaulted to
    the first *unchecked* seat.
    """
    with tempfile.TemporaryDirectory(**_TMP) as tmp:
        db_path = str(Path(tmp) / "chat.db")
        status, data = _orchestrate(
            db_path, topic="T", conv_type="collaborate", preset="plan",
            participants=["claude-code", "codex"], first="codex",
        )
        assert status == 200, data
        row = _conv_row(db_path, data["conversation_id"])
        assert json.loads(row["participants"]) == ["codex", "claude-code"], \
            "the first speaker must head the participant list"
        assert json.loads(row["participant_roles"]) == {
            "codex": "facilitator", "claude-code": "collaborator"}
        assert row["current_turn"] == "codex"


def test_the_first_speaker_holds_the_lead_role_by_default():
    """With no explicit first, the top seat facilitates — seat order decides.

    Keeps ONE definition of "the lead is participants[0]", in
    ``conv_types.default_roles()``, shared with start_conversation.py.
    """
    with tempfile.TemporaryDirectory(**_TMP) as tmp:
        db_path = str(Path(tmp) / "chat.db")
        status, data = _orchestrate(
            db_path, topic="T", conv_type="collaborate", preset="plan",
            participants=["claude-code", "codex"],
        )
        assert status == 200, data
        row = _conv_row(db_path, data["conversation_id"])
        roles = json.loads(row["participant_roles"])
        assert roles["claude-code"] == "facilitator"
        assert roles["codex"] == "collaborator"


def test_a_separate_lead_seat_is_refused_not_ignored():
    """Silently dropping it would seat a facilitator the caller didn't choose."""
    with tempfile.TemporaryDirectory(**_TMP) as tmp:
        db_path = str(Path(tmp) / "chat.db")
        status, data = _orchestrate(
            db_path, topic="T", conv_type="collaborate", preset="plan",
            participants=["claude-code", "codex"],
            moderator={"cli": "antigravity", "persona": "__none__"},
        )
        assert status == 400, data
        assert "no separate" in data["error"]


def test_seat_bounds_count_the_whole_room_for_a_member_lead_type():
    """The quoted range must match what the operator actually ticks."""
    with tempfile.TemporaryDirectory(**_TMP) as tmp:
        db_path = str(Path(tmp) / "chat.db")
        status, data = _orchestrate(
            db_path, topic="T", conv_type="collaborate", preset="plan",
            participants=["claude-code"],
        )
        assert status == 400, data
        assert "2\u20135" in data["error"] or "2–5" in data["error"], data["error"]

    t = CONV_TYPES["collaborate"]
    assert (t.min_participants, t.max_participants) == (2, 5)
    # And a lead that DOES take its own seat still counts members separately.
    for key in ("debate", "podcast"):
        assert CONV_TYPES[key].lead_needs_own_seat


def test_podcast_still_requires_its_own_host_seat():
    """The change must be per-type: a host is not a guest and never was."""
    with tempfile.TemporaryDirectory(**_TMP) as tmp:
        db_path = str(Path(tmp) / "chat.db")
        status, data = _orchestrate(
            db_path, topic="T", conv_type="podcast", preset="podcast",
            participants=["claude-code", "codex"],
        )
        assert status == 400, data
        assert "host" in data["error"].lower()


def test_a_lead_only_forces_turn_rotation_for_a_room_it_runs():
    """Brainstorm's `continuous` must survive seating a facilitator.

    `/api/orchestrate` forces mode='turns' whenever a lead is seated, because a
    continuous moderator is a free-for-all. A facilitator doesn't police the
    floor, and brainstorm sets continuous on purpose.
    """
    from presets import PRESETS

    assert CONV_TYPES["debate"].lead_forces_turns
    assert CONV_TYPES["podcast"].lead_forces_turns
    assert not CONV_TYPES["collaborate"].lead_forces_turns
    assert PRESETS["brainstorm"]["mode"] == "continuous"
    src = (_SRC / "web" / "api" / "orchestrate.py").read_text(encoding="utf-8")
    assert "type_spec.lead_forces_turns" in src, \
        "orchestrate ignores lead_forces_turns and will flatten brainstorm to turns"


def test_turn_payloads_carry_the_type_and_the_agents_role():
    """An agent must be able to learn it's the host from the tools alone."""
    import asyncio

    import agent_chat_mcp as mcp

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        _seed(db, participants=["claude-code", "codex", "codex-2"],
              conv_type="podcast", participant_roles={"claude-code": "host"},
              preset="podcast", tone="be interesting")
        mcp.DB_PATH = db

        mcp.AGENT_ID = "claude-code"
        kickoff = json.loads(asyncio.run(mcp.get_kickoff(mcp.GetKickoffInput())))
        assert kickoff["conversation_type"] == "podcast"
        assert kickoff["your_role"] == "host"
        assert "HOST" in kickoff["role_brief"]
        assert kickoff["roles"]["codex-2"] == "guest"

        mcp.AGENT_ID = "codex-2"
        turn = json.loads(asyncio.run(mcp.get_my_turn(mcp.GetMyTurnInput())))
        assert turn["conversation_type"] == "podcast"
        assert turn["your_role"] == "guest"
        assert "GUEST" in turn["role_brief"]


def test_turn_payloads_carry_persona_names_but_never_the_cards():
    """A host must be able to introduce guests by name — and only by name.

    Without ``cast`` the host only has agent ids and introduces its guests as
    "codex", which is a tool, not a person. With the whole persona entry it
    could read a guest's brief, which is not its to read.
    """
    import asyncio

    import agent_chat_mcp as mcp

    personas = {
        "claude-code": {"persona_slug": "barkley", "persona_name": "Charles Barkley",
                        "persona_body": "HOST CARD BODY — private to the host"},
        "codex": {"persona_slug": "pinkman", "persona_name": "Jesse Pinkman",
                  "persona_body": "GUEST CARD BODY — private to the guest"},
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        _seed(db, participants=["claude-code", "codex"], conv_type="podcast",
              participant_roles={"claude-code": "host"},
              participant_personas=personas, preset="podcast", tone="t")
        mcp.DB_PATH = db
        mcp.AGENT_ID = "claude-code"

        for payload in (
            json.loads(asyncio.run(mcp.get_kickoff(mcp.GetKickoffInput()))),
            json.loads(asyncio.run(mcp.get_my_turn(mcp.GetMyTurnInput()))),
        ):
            assert payload["cast"] == {
                "claude-code": "Charles Barkley", "codex": "Jesse Pinkman",
            }
            # No card body may appear anywhere in the response.
            blob = json.dumps(payload)
            assert "CARD BODY" not in blob, "a persona body leaked into the payload"
            assert "persona_body" not in blob


def test_cast_is_empty_without_personas():
    """A conversation seeded with no cast returns {}, not a broken payload."""
    import asyncio

    import agent_chat_mcp as mcp

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        _seed(db, participants=["claude-code", "codex"])
        mcp.DB_PATH = db
        mcp.AGENT_ID = "claude-code"
        turn = json.loads(asyncio.run(mcp.get_my_turn(mcp.GetMyTurnInput())))
        assert turn["cast"] == {}


def test_turn_payloads_of_a_pre_roles_conversation_stay_quiet():
    """No roles recorded → no role fields invented, and nothing raises."""
    import asyncio
    import sqlite3 as sq

    import agent_chat_mcp as mcp

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        cid = _seed(db, participants=["claude-code", "codex"]).conversation_id
        conn = sq.connect(db, isolation_level=None)
        conn.execute(
            "UPDATE conversations SET participant_roles = NULL WHERE id = ?", (cid,)
        )
        conn.close()

        mcp.DB_PATH = db
        mcp.AGENT_ID = "claude-code"
        turn = json.loads(asyncio.run(mcp.get_my_turn(mcp.GetMyTurnInput())))
        assert turn["conversation_type"] == "debate"
        assert turn["your_role"] is None
        assert turn["roles"] == {}
        assert "role_brief" not in turn


# ---------------------------------------------------------------------------
# Export bundle
# ---------------------------------------------------------------------------

def _bundle_for(**kw) -> dict[str, str]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = str(Path(td) / "chat.db")
        personas = {
            a: {"persona_slug": f"p-{a}", "persona_name": f"Persona {a}",
                "persona_body": "card"}
            for a in kw["participants"]
        }
        cid = _seed(db, participant_personas=personas, **kw).conversation_id
        data = export.load_conversation(db, cid)
        return dict(export.bundle_files(data))


def test_export_records_the_type_and_the_lead():
    files = _bundle_for(participants=["claude-code", "codex", "antigravity"],
                        conv_type="podcast",
                        participant_roles={"claude-code": "host"})
    topic_md = files["topic.md"]
    assert "| Type | podcast |" in topic_md
    assert "| Host | claude-code |" in topic_md
    # The Cast bullet shape is frozen — downstream consumers parse it.
    assert "- **claude-code** — Persona claude-code" in topic_md

    host_doc = files["personas/claude-code-p-claude-code.md"]
    assert "| Role | Host |" in host_doc
    guest_doc = files["personas/codex-p-codex.md"]
    assert "| Role | Guest |" in guest_doc


def test_export_of_a_pre_roles_conversation_omits_the_lead_row():
    files = _bundle_for(participants=["claude-code", "codex"])
    topic_md = files["topic.md"]
    assert "| Type | debate |" in topic_md
    assert "| Moderator |" not in topic_md


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
