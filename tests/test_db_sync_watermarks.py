r"""Tests for the sidecar's sync watermarks — ``scripts/db_sync.py``.

The sidecar keeps two cursors per synced table, and the whole correctness
argument rests on **each one being measured on exactly one clock**:

- the **push** cursor (``conversations_updated_after`` /
  ``personas_updated_after``) is a *local* ``updated_at`` value — rows newer
  than it get shipped to the mirror;
- the **pull** cursor (``pulled_updated_at`` / ``pulled_personas_updated_at``)
  is the *server's* ``server_time`` — rows on the mirror newer than it get
  fetched.

They used to be mixed: every tick folded the pull's ``server_time`` into the
push cursor as an anti-echo guard, which marched the push cursor forward on the
remote clock whether or not anything was pushed. A local edit whose
``updated_at`` landed behind the last tick's ``server_time`` was then invisible
to ``read_changed_conversations()`` **forever**, because the cursor only grows.
Two seconds of skew between this machine and Fly was enough. It happened for
real — re-titling conversations #54/#57/#58 produced three ``UPDATE``s that
never reached the mirror.

So: ``test_a_local_edit_behind_the_server_clock_still_gets_pushed`` is the
regression that matters. The rest pin the properties that made the old guard
look reasonable — the pull cursor still runs on server time, and the echo the
guard suppressed is self-terminating rather than a ping-pong loop.

The DB is a real SQLite file seeded through ``orchestrator.seeding`` (the WAL
behaviour is the thing under test elsewhere; mocking it here would prove
nothing). Only the two HTTP functions are stubbed.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_db_sync_watermarks.py
"""

from __future__ import annotations

import importlib.util
import logging
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator import seeding  # noqa: E402

_LOG = logging.getLogger("test_db_sync")

# Windows keeps a handle on the WAL sidecar files a moment past close.
_TMP = dict(ignore_cleanup_errors=True)


def _load_db_sync():
    """Import scripts/db_sync.py by path (it's a script, not a package member)."""
    spec = importlib.util.spec_from_file_location(
        "_db_sync_watermarks_under_test", _ROOT / "scripts" / "db_sync.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # db_sync defines @dataclass types, and dataclasses resolves annotations via
    # sys.modules[cls.__module__] — so the module has to be registered first.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


db_sync = _load_db_sync()


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class FakeRemote:
    """Stands in for the mirror: records pushes, replays canned pulls.

    ``server_time`` is the knob the regression turns — set it ahead of the
    local clock to reproduce a Fly instance whose clock runs fast.
    """

    def __init__(self, server_time: str = "2026-01-01T00:00:00+00:00") -> None:
        self.server_time = server_time
        self.conversations: list[dict[str, Any]] = []
        self.deleted_conversation_ids: list[int] = []
        self.personas: list[dict[str, Any]] = []
        self.deleted_persona_keys: list[str] = []
        self.pushes: list[dict[str, Any]] = []

    def get_since(self, url, token, updated_after, known_ids, timeout,
                  personas_updated_after, known_persona_keys):
        return {
            "conversations": self.conversations,
            "deleted_conversation_ids": self.deleted_conversation_ids,
            "personas": self.personas,
            "deleted_persona_keys": self.deleted_persona_keys,
            "server_time": self.server_time,
        }

    def post_batch(self, url, token, batch, timeout):
        self.pushes.append(batch)
        return {"ok": True}

    # -- assertions helpers ------------------------------------------------

    def pushed_conversation_ids(self) -> list[int]:
        return [
            int(c["id"]) for push in self.pushes for c in push["conversations"]
        ]

    def pushed_topics(self) -> list[str]:
        return [
            str(c["topic"]) for push in self.pushes for c in push["conversations"]
        ]


def _tick(db_path: Path, state, remote: FakeRemote):
    """One ``run_tick`` with the two HTTP calls pointed at ``remote``."""
    real_get, real_post = db_sync.get_since, db_sync.post_batch
    db_sync.get_since = remote.get_since
    db_sync.post_batch = remote.post_batch
    try:
        return db_sync.run_tick(
            db_path, state,
            "http://x/api/since", "http://x/api/ingest",
            "token", 5.0, _LOG,
        )
    finally:
        db_sync.get_since, db_sync.post_batch = real_get, real_post


def _seeded_db(tmp: Path) -> tuple[Path, int]:
    db_path = tmp / "chat.db"
    result = seeding.seed_conversation(
        db_path=str(db_path),
        topic="Original topic",
        participants=["claude-code", "codex"],
        mode="turns",
        max_turns=2,
    )
    return db_path, int(result.conversation_id)


def _set_updated_at(db_path: Path, cid: int, topic: str, updated_at: str) -> None:
    """A local edit, exactly as the web UI's rename does it."""
    with sqlite3.connect(str(db_path), timeout=10.0) as conn:
        conn.execute(
            "UPDATE conversations SET topic = ?, updated_at = ? WHERE id = ?",
            (topic, updated_at, cid),
        )


def _read_updated_at(db_path: Path, cid: int) -> str:
    with sqlite3.connect(str(db_path), timeout=10.0) as conn:
        return str(
            conn.execute(
                "SELECT updated_at FROM conversations WHERE id = ?", (cid,)
            ).fetchone()[0]
        )


# ---------------------------------------------------------------------------
# The regression
# ---------------------------------------------------------------------------

def test_a_local_edit_behind_the_server_clock_still_gets_pushed():
    """The bug, reduced: mirror clock ahead, local edit behind it.

    Tick 1 ships the seeded row and learns ``server_time`` (year 2099 — a
    stand-in for "Fly's clock is ahead of this machine's"). Then comes a local
    rename stamped five seconds after the row's own ``updated_at``: newer than
    anything pushed so far, but behind the remote clock. The old code folded
    ``server_time`` into the push cursor, so the edit was already 'in the past'
    and was never selected. It has to ship.
    """
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, cid = _seeded_db(Path(td))
        remote = FakeRemote(server_time="2099-01-01T00:00:00+00:00")
        _set_updated_at(db_path, cid, "Original topic", "2026-08-27T12:00:00+00:00")

        state = _tick(db_path, db_sync.State(), remote)
        assert remote.pushes, "tick 1 should push the freshly seeded row"
        remote.pushes.clear()

        _set_updated_at(db_path, cid, "Renamed locally", "2026-08-27T12:00:05+00:00")
        _tick(db_path, state, remote)

        assert remote.pushed_topics() == ["Renamed locally"], (
            "the local rename never reached the mirror — the push watermark "
            f"ran on the remote clock again (pushes={remote.pushes})"
        )


def test_the_push_cursor_never_takes_the_server_clock():
    """Property behind the regression, asserted directly on the state."""
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, cid = _seeded_db(Path(td))
        remote = FakeRemote(server_time="2099-01-01T00:00:00+00:00")

        state = _tick(db_path, db_sync.State(), remote)

        assert state.conversations_updated_after == _read_updated_at(db_path, cid)
        assert state.personas_updated_after == db_sync.EPOCH, (
            "no persona was pushed, so its push cursor must not have moved"
        )
        assert "2099" not in state.conversations_updated_after
        assert "2099" not in state.personas_updated_after


def test_an_idle_tick_leaves_the_push_cursor_alone():
    """Nothing local changed, so nothing may advance past a future local write."""
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, _ = _seeded_db(Path(td))
        remote = FakeRemote(server_time="2099-01-01T00:00:00+00:00")

        state = _tick(db_path, db_sync.State(), remote)
        after_first = state.conversations_updated_after
        state = _tick(db_path, state, remote)

        assert state.conversations_updated_after == after_first


# ---------------------------------------------------------------------------
# Properties the old guard existed to protect
# ---------------------------------------------------------------------------

def test_the_pull_cursor_still_runs_on_server_time():
    """Unchanged half of the split — clock-skew safety on the pull side."""
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, _ = _seeded_db(Path(td))
        remote = FakeRemote(server_time="2099-01-01T00:00:00+00:00")

        state = _tick(db_path, db_sync.State(), remote)

        assert state.pulled_updated_at == "2099-01-01T00:00:00+00:00"
        assert state.pulled_personas_updated_at == "2099-01-01T00:00:00+00:00"


def test_a_pulled_row_echoes_at_most_once():
    """The echo the old guard suppressed is self-terminating, not a loop.

    ``/api/ingest`` upserts with the row's own ``updated_at`` and never
    rewrites it, so an echoed row is byte-identical to what the mirror holds
    and pushing it moves the cursor past it. One wasted POST, then quiet —
    which is the whole price of the fix.
    """
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, cid = _seeded_db(Path(td))
        remote = FakeRemote()

        state = _tick(db_path, db_sync.State(), remote)
        remote.pushes.clear()

        # The operator renames it on the hosted UI; the mirror hands it back
        # with a server-side updated_at ahead of the local one.
        hosted = dict(remote.conversations)  # keep the type obvious
        assert not hosted
        with sqlite3.connect(str(db_path), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            row = dict(
                conn.execute(
                    f"SELECT {','.join(db_sync.CONV_COLUMNS)} "
                    f"FROM conversations WHERE id = ?", (cid,)
                ).fetchone()
            )
        row["topic"] = "Renamed on the mirror"
        row["updated_at"] = "2030-01-01T00:00:00+00:00"
        remote.conversations = [row]

        state = _tick(db_path, state, remote)
        assert _read_updated_at(db_path, cid) == "2030-01-01T00:00:00+00:00"
        assert remote.pushed_topics() == ["Renamed on the mirror"], (
            "expected exactly one echo of the just-pulled row"
        )

        # Mirror stops reporting it (it is no longer newer than the pull
        # cursor). Nothing further may be pushed.
        remote.conversations = []
        remote.pushes.clear()
        _tick(db_path, state, remote)
        assert remote.pushes == [], "the echo repeated — that is a ping-pong loop"


def test_a_hosted_delete_still_propagates_and_stops():
    """Pull-then-push ordering, unaffected by the watermark split."""
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, cid = _seeded_db(Path(td))
        remote = FakeRemote()

        state = _tick(db_path, db_sync.State(), remote)
        remote.deleted_conversation_ids = [cid]
        remote.pushes.clear()

        state = _tick(db_path, state, remote)
        with sqlite3.connect(str(db_path), timeout=10.0) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE id = ?", (cid,)
            ).fetchone()[0] == 0
        assert state.known_conversation_ids == []

        remote.deleted_conversation_ids = []
        remote.pushes.clear()
        _tick(db_path, state, remote)
        assert remote.pushes == []


# ---------------------------------------------------------------------------
# --force-push
# ---------------------------------------------------------------------------

def test_force_push_rewinds_only_the_push_cursors():
    state = db_sync.State(
        last_message_id=42,
        conversations_updated_after="2026-08-27T12:00:00+00:00",
        pulled_updated_at="2026-08-27T12:00:05+00:00",
        known_conversation_ids=[1, 2],
        personas_updated_after="2026-08-27T12:00:00+00:00",
        pulled_personas_updated_at="2026-08-27T12:00:05+00:00",
        known_persona_keys=["g\x1fs"],
    )
    rewound = db_sync.rewind_push_watermarks(state)

    assert rewound.last_message_id == 0
    assert rewound.conversations_updated_after == db_sync.EPOCH
    assert rewound.personas_updated_after == db_sync.EPOCH
    # Pull cursors and the delete-by-set-difference bookkeeping survive.
    assert rewound.pulled_updated_at == state.pulled_updated_at
    assert rewound.pulled_personas_updated_at == state.pulled_personas_updated_at
    assert rewound.known_conversation_ids == [1, 2]
    assert rewound.known_persona_keys == ["g\x1fs"]


def test_force_push_re_ships_a_row_the_mirror_already_has():
    """The recovery path: no hand-editing of db/.sync-state.json."""
    with tempfile.TemporaryDirectory(**_TMP) as td:
        db_path, cid = _seeded_db(Path(td))
        remote = FakeRemote()

        state = _tick(db_path, db_sync.State(), remote)
        remote.pushes.clear()

        _tick(db_path, state, remote)
        assert remote.pushes == [], "nothing changed; a normal tick pushes nothing"

        _tick(db_path, db_sync.rewind_push_watermarks(state), remote)
        assert remote.pushed_conversation_ids() == [cid]


def test_force_push_is_a_flag_on_the_cli():
    """A recovery flag nobody can find is no recovery flag."""
    src = (_ROOT / "scripts" / "db_sync.py").read_text(encoding="utf-8")
    assert '"--force-push"' in src
    assert "args.force_push" in src


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
