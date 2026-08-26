r"""Tests for ``orchestrator.delivery`` — pushing a finished conversation out.

The load-bearing guarantee is the first one below: **what the folder sink
writes is byte-for-byte what the ``/export.zip`` download contains**, just
unpacked. That is the whole promise of the feature, and it is easy to break
without noticing on Windows, where opening a file in text mode silently
rewrites every ``\n`` to ``\r\n``. The comparison here is against the real
``render_export_zip()`` output, not a hand-written expectation, so it stays
true through any future change to the export format.

The rest pins the safety properties: delivery is off unless configured, and a
sink that fails takes the artifact down with it and nothing else — never a
conversation, never the sinks configured after it.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_delivery.py
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator import delivery, export  # noqa: E402
from orchestrator.seeding import SCHEMA  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — a real SQLite file, never a mock. The WAL/multi-process behaviour
# is the thing under test everywhere else in this repo; keep the habit.
# ---------------------------------------------------------------------------

_NOW = "2026-08-26T12:00:00+00:00"


def _seed_db(path: Path, *, with_result: bool = True) -> int:
    """Create a two-agent conversation with a few messages. Returns its id."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO conversations (topic, participants, mode, max_turns, "
        "status, end_reason, created_at, updated_at, preset, conv_type, "
        "participant_roles) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "Should delivery sinks be configurable?",
            json.dumps(["claude-code", "codex"]),
            "turns", 3, "complete", "agent signaled done", _NOW, _NOW,
            "plan", "collaborate",
            json.dumps({"claude-code": "facilitator", "codex": "collaborator"}),
        ),
    )
    cid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    rows = [
        ("claude-code", "Opening the collaboration.", None),
        ("codex", "Here is my half.", None),
    ]
    if with_result:
        rows += [
            ("claude-code", "# Draft one\n\nRough.", "result"),
            ("claude-code", "# Final plan\n\nThe actual deliverable.", "result"),
        ]
    for sender, content, signal in rows:
        conn.execute(
            "INSERT INTO messages (conversation_id, sender, content, signal, "
            "created_at) VALUES (?,?,?,?,?)",
            (cid, sender, content, signal, _NOW),
        )
    conn.close()
    return cid


@contextmanager
def _env(config: dict | str | None):
    """Point delivery at a throwaway config + DB for the duration of a test.

    ``config`` may be a dict (written as JSON), a raw string (to test a
    malformed file), or None (no file at all — the default posture).
    """
    # ignore_cleanup_errors: the /orchestrate test leaves web.db holding a
    # connection to the temp DB, and Windows refuses to unlink an open file.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        root = Path(td)
        cfg = root / "delivery.json"
        if isinstance(config, dict):
            cfg.write_text(json.dumps(config), encoding="utf-8")
        elif isinstance(config, str):
            cfg.write_text(config, encoding="utf-8")
        prev = os.environ.get("AGENT_CHAT_DELIVERY_CONFIG")
        os.environ["AGENT_CHAT_DELIVERY_CONFIG"] = str(cfg)
        # The log path is resolved from the repo root, not the config — without
        # this a test run would write fake deliveries into the operator's real
        # logs/delivery.log.
        prev_log = delivery.log_path
        delivery.log_path = lambda: root / "delivery.log"  # type: ignore[assignment]
        db = root / "chat.db"
        cid = _seed_db(db)
        try:
            yield root, str(db), cid
        finally:
            delivery.log_path = prev_log  # type: ignore[assignment]
            if prev is None:
                os.environ.pop("AGENT_CHAT_DELIVERY_CONFIG", None)
            else:
                os.environ["AGENT_CHAT_DELIVERY_CONFIG"] = prev


def _folder_config(out: Path, **sink_extra) -> dict:
    sink = {"type": "folder", "enabled": True, "path": str(out)}
    sink.update(sink_extra)
    return {"enabled": True, "events": ["complete"], "sinks": [sink]}


# ---------------------------------------------------------------------------
# The contract: unzipped == the zip
# ---------------------------------------------------------------------------

def test_folder_sink_is_byte_identical_to_export_zip() -> None:
    """The delivered folder must be the .zip bundle, unpacked. Same entry
    names, same bytes — including line endings, which is why the sink writes
    bytes rather than text."""
    with _env(None) as (root, db, cid):
        out = root / "out"
        os.environ["AGENT_CHAT_DELIVERY_CONFIG"] = str(root / "cfg.json")
        (root / "cfg.json").write_text(
            json.dumps(_folder_config(out)), encoding="utf-8")

        lines = delivery.deliver(cid, "complete", db)
        assert lines and lines[0].startswith("folder: "), lines

        data = export.load_conversation(db, cid)
        zf = zipfile.ZipFile(io.BytesIO(export.render_export_zip(data)))
        target = out / delivery.bundle_dir_name(cid, data["conversation"]["topic"])

        on_disk = sorted(
            str(p.relative_to(target)).replace("\\", "/")
            for p in target.rglob("*") if p.is_file()
        )
        assert on_disk == sorted(zf.namelist()), (on_disk, zf.namelist())
        for name in zf.namelist():
            assert zf.read(name) == (target / name).read_bytes(), name

        # The personas/ subdirectory is a real directory, not a flattened name.
        assert (target / "personas").is_dir()


def test_folder_sink_writes_lf_not_crlf() -> None:
    """Explicit regression guard for the Windows text-mode trap. The check
    above would catch it too, but only as an opaque byte mismatch."""
    with _env(None) as (root, db, cid):
        out = root / "out"
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(out)), encoding="utf-8")
        delivery.deliver(cid, "complete", db)
        target = out / delivery.bundle_dir_name(cid, "Should delivery sinks be configurable?")
        raw = (target / "transcript.md").read_bytes()
        assert b"\r\n" not in raw


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------

def test_no_config_means_no_delivery() -> None:
    """A clone with no config/delivery.json delivers nothing and touches
    nothing. This is the default state of the repo."""
    with _env(None) as (root, db, cid):
        assert delivery.deliver(cid, "complete", db) == []
        assert delivery.load_config() == {}


def test_config_present_but_disabled_delivers_nothing() -> None:
    with _env(None) as (root, db, cid):
        cfg = _folder_config(root / "out")
        cfg["enabled"] = False
        (root / "delivery.json").write_text(json.dumps(cfg), encoding="utf-8")
        assert delivery.deliver(cid, "complete", db) == []
        assert not (root / "out").exists()


def test_starter_config_is_disabled() -> None:
    """`--init` must never write a config that starts delivering."""
    assert delivery.STARTER_CONFIG["enabled"] is False
    assert delivery.enabled_sinks(delivery.STARTER_CONFIG, "complete") == []


def test_malformed_config_is_treated_as_absent() -> None:
    """A JSON typo must not take down the MCP server mid-conversation."""
    with _env("{not json at all") as (root, db, cid):
        assert delivery.load_config() == {}
        assert delivery.deliver(cid, "complete", db) == []


# ---------------------------------------------------------------------------
# Event gating
# ---------------------------------------------------------------------------

def test_default_events_are_complete_only() -> None:
    """A lead that drafts-then-revises posts a `result` per revision; nobody
    should get four deliveries by default."""
    cfg = {"enabled": True, "sinks": [{"type": "folder", "enabled": True}]}
    assert delivery.enabled_sinks(cfg, "complete")
    assert delivery.enabled_sinks(cfg, "result") == []


def test_per_sink_events_override_the_global_list() -> None:
    cfg = {
        "enabled": True,
        "events": ["complete"],
        "sinks": [
            {"type": "folder", "enabled": True, "events": ["result", "complete"]},
            {"type": "webhook", "enabled": True, "url": "http://x"},
        ],
    }
    assert [s["type"] for s in delivery.enabled_sinks(cfg, "result")] == ["folder"]
    assert [s["type"] for s in delivery.enabled_sinks(cfg, "complete")] == \
        ["folder", "webhook"]


def test_disabled_sink_is_skipped_even_when_delivery_is_on() -> None:
    cfg = {
        "enabled": True,
        "sinks": [
            {"type": "folder", "enabled": False},
            {"type": "webhook", "enabled": True, "url": "http://x"},
        ],
    }
    assert [s["type"] for s in delivery.enabled_sinks(cfg, "complete")] == ["webhook"]


# ---------------------------------------------------------------------------
# result.md
# ---------------------------------------------------------------------------

def test_result_md_is_off_by_default() -> None:
    """The bundle is the zip's contents, exactly — an extra file is opt-in."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out")), encoding="utf-8")
        delivery.deliver(cid, "complete", db)
        target = root / "out" / delivery.bundle_dir_name(cid, "Should delivery sinks be configurable?")
        assert not (target / "result.md").exists()


def test_include_result_writes_the_latest_result_body() -> None:
    """Several `signal='result'` messages means several drafts; the newest is
    the artifact."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out", include_result=True)),
            encoding="utf-8")
        delivery.deliver(cid, "complete", db)
        target = root / "out" / delivery.bundle_dir_name(cid, "Should delivery sinks be configurable?")
        body = (target / "result.md").read_text(encoding="utf-8")
        assert "The actual deliverable." in body
        assert "Rough." not in body


def test_latest_result_is_none_without_one() -> None:
    assert delivery.latest_result([{"content": "hi", "signal": None}]) is None


# ---------------------------------------------------------------------------
# Per-conversation opt-in (the /orchestrate checkbox)
# ---------------------------------------------------------------------------

def test_scope_all_ignores_the_optin_list() -> None:
    """The original behaviour, and still the default for a sink that says
    nothing: every conversation is delivered."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out")), encoding="utf-8")
        assert not delivery.is_opted_in(cid)
        lines = delivery.deliver(cid, "complete", db)
        assert lines and lines[0].startswith("folder: "), lines


def test_scope_optin_delivers_nothing_until_marked() -> None:
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out", scope="opt-in")), encoding="utf-8")

        assert delivery.deliver(cid, "complete", db) == []
        assert not (root / "out").exists()

        assert delivery.mark_opt_in(cid) is True
        lines = delivery.deliver(cid, "complete", db)
        assert lines and lines[0].startswith("folder: "), lines


def test_optin_is_per_conversation() -> None:
    """Ticking the box for one launch must not deliver the next one."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out", scope="opt-in")), encoding="utf-8")
        delivery.mark_opt_in(cid)
        other = _seed_db(Path(db))  # a second conversation in the same DB
        assert delivery.is_opted_in(cid)
        assert not delivery.is_opted_in(other)
        assert delivery.deliver(other, "complete", db) == []


def test_optin_round_trip_is_idempotent() -> None:
    with _env(None) as (root, db, cid):
        assert delivery.mark_opt_in(cid) is True
        assert delivery.mark_opt_in(cid) is True          # no duplicate row
        assert json.loads(delivery.optin_path().read_text())["conversations"] == [cid]
        assert delivery.clear_opt_in(cid) is True
        assert not delivery.is_opted_in(cid)


def test_optin_file_lives_beside_the_config_and_is_local_only() -> None:
    """It is bookkeeping about this machine's filesystem, so it must never
    become a `conversations` column — a column would have to be mirrored across
    four SCHEMA copies, carried by db_sync + /api/ingest, and would then travel
    to a hosted mirror where `deliveries/` does not exist."""
    with _env(None) as (root, db, cid):
        assert delivery.optin_path().parent == delivery.config_path().parent

    conv_ddl = SCHEMA.split("CREATE TABLE IF NOT EXISTS conversations")[1].split(");")[0]
    assert "deliver" not in conv_ddl.lower(), conv_ddl

    from web.db import _CONV_COLUMNS
    assert not [c for c in _CONV_COLUMNS if "deliver" in c]


def test_malformed_optin_file_is_treated_as_empty() -> None:
    with _env(None) as (root, db, cid):
        delivery.optin_path().write_text("[[[not json", encoding="utf-8")
        assert delivery.is_opted_in(cid) is False


def test_manual_delivery_ignores_scope() -> None:
    """`inspect_conversations deliver 42` is itself the opt-in — refusing it
    because a checkbox went unticked at launch would be absurd."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out", scope="opt-in")), encoding="utf-8")
        assert delivery.deliver(cid, "complete", db) == []            # the hook
        lines = delivery.deliver(cid, "complete", db, ignore_scope=True)
        assert lines and lines[0].startswith("folder: "), lines


def test_cli_passes_ignore_scope() -> None:
    src = Path(__file__).resolve().parent.parent / "src"
    text = (src / "inspect_conversations.py").read_text(encoding="utf-8")
    assert "ignore_scope=True" in text


def test_enabled_sinks_ignores_scope_when_no_cid_is_given() -> None:
    """The /orchestrate renderer asks what a config *can* do, not what it will
    do for one conversation — otherwise the checkbox could never appear."""
    cfg = _folder_config(Path("out"), scope="opt-in")
    assert delivery.enabled_sinks(cfg, "complete", cid=None)
    assert delivery.enabled_sinks(cfg, "complete", cid=999) == []


# ---------------------------------------------------------------------------
# The /orchestrate control
# ---------------------------------------------------------------------------

def _toggle_html() -> str:
    from web.render.orchestrate import _delivery_toggle_html
    return _delivery_toggle_html()


def test_toggle_hidden_when_delivery_is_off() -> None:
    """No control at all — but a hint, so the feature stays discoverable
    without implying a choice that would do nothing."""
    with _env(None) as (root, db, cid):
        html = _toggle_html()
        assert 'name="deliver_locally"' not in html
        assert "orch-deliver-off" in html


def test_toggle_is_live_when_a_sink_is_opt_in() -> None:
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out", scope="opt-in")), encoding="utf-8")
        html = _toggle_html()
        assert 'name="deliver_locally"' in html
        assert "disabled" not in html
        assert "checked" not in html          # opt-in means opt-in


def test_toggle_is_ticked_and_disabled_when_a_sink_is_scoped_all() -> None:
    """A sink scoped `all` delivers whatever the operator clicks. The box must
    say so rather than offering a choice it does not have."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out")), encoding="utf-8")
        html = _toggle_html()
        assert "checked" in html and "disabled" in html
        assert "scope: all" in html


def test_orchestrate_records_the_optin_only_when_asked() -> None:
    """End-to-end through POST /api/orchestrate, preflight stubbed."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out", scope="opt-in")), encoding="utf-8")

        status, data = _orchestrate(db, topic="Plain launch",
                                    participants=["claude-code", "codex"],
                                    conv_type="collaborate")
        assert status == 200, data
        assert data["deliver_locally"] is False
        assert not delivery.is_opted_in(data["conversation_id"])

        status, data = _orchestrate(db, topic="Launch with the box ticked",
                                    participants=["claude-code", "codex"],
                                    conv_type="collaborate", deliver_locally=True)
        assert status == 200, data
        assert data["deliver_locally"] is True
        assert delivery.is_opted_in(data["conversation_id"])


def _orchestrate(db_path: str, **payload):
    """POST /api/orchestrate in-process, preflight stubbed — same helper shape
    as tests/test_conv_types.py (CI has no MCP configs, so a real preflight
    would 409 there and pass here)."""
    import asyncio
    import json as _json

    from orchestrator import preflight as orch_preflight
    from web import db as web_db
    from web.api import orchestrate as api

    web_db.set_db_path(db_path)
    web_db.db_init()
    payload.setdefault("spawn", False)

    class _Req:
        async def json(self):
            return payload

    def _all_ok(seats):
        return [orch_preflight.PreflightResult(cli=s, ok=True, config_path="<stub>")
                for s in seats]

    real = orch_preflight.run_preflight
    orch_preflight.run_preflight = _all_ok
    try:
        resp = asyncio.run(api.api_orchestrate(_Req()))
    finally:
        orch_preflight.run_preflight = real
    return resp.status_code, _json.loads(resp.body.decode())


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def test_bundle_dir_name_disambiguates_by_id() -> None:
    """Two conversations on the same subject share a slug (it truncates at 25
    chars) — without the id they would overwrite each other in an accumulating
    folder, which is the difference between this and the one-shot .zip name."""
    topic = "Are AI coding agents overhyped or underhyped, really?"
    assert delivery.bundle_dir_name(7, topic) != delivery.bundle_dir_name(8, topic)
    assert delivery.bundle_dir_name(7, topic).endswith("-7")


def test_bundle_dir_name_falls_back_for_unsluggable_topics() -> None:
    assert delivery.bundle_dir_name(9, "日本語") == "conversation-9"
    assert delivery.bundle_dir_name(9, "") == "conversation-9"


# ---------------------------------------------------------------------------
# Failure isolation — the point of the whole module
# ---------------------------------------------------------------------------

def test_a_failing_sink_neither_raises_nor_stops_the_next_one() -> None:
    """A dead webhook costs an artifact, not a turn — and not the folder copy
    configured after it."""
    with _env(None) as (root, db, cid):
        cfg = {
            "enabled": True,
            "events": ["complete"],
            "sinks": [
                # Port 1 on loopback: nothing listens, connection refused fast.
                {"type": "webhook", "enabled": True,
                 "url": "http://127.0.0.1:1/nope", "timeout": 2},
                {"type": "folder", "enabled": True, "path": str(root / "out")},
            ],
        }
        (root / "delivery.json").write_text(json.dumps(cfg), encoding="utf-8")

        lines = delivery.deliver(cid, "complete", db)
        assert len(lines) == 2
        assert lines[0].startswith("webhook: ERROR"), lines[0]
        assert lines[1].startswith("folder: "), lines[1]
        target = root / "out" / delivery.bundle_dir_name(cid, "Should delivery sinks be configurable?")
        assert (target / "transcript.md").exists()


def test_unknown_sink_type_is_reported_not_raised() -> None:
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(json.dumps({
            "enabled": True,
            "sinks": [{"type": "carrier-pigeon", "enabled": True}],
        }), encoding="utf-8")
        lines = delivery.deliver(cid, "complete", db)
        assert lines == ["carrier-pigeon: ERROR unknown sink type"]


def test_missing_conversation_is_reported_not_raised() -> None:
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(
            json.dumps(_folder_config(root / "out")), encoding="utf-8")
        lines = delivery.deliver(99999, "complete", db)
        assert lines == ["ERROR: no conversation #99999"]


def test_command_sink_requires_the_folder_sink() -> None:
    """It acts on files; with nothing on disk there is nothing to hand it."""
    with _env(None) as (root, db, cid):
        (root / "delivery.json").write_text(json.dumps({
            "enabled": True,
            "sinks": [{"type": "command", "enabled": True, "argv": ["echo", "{dir}"]}],
        }), encoding="utf-8")
        lines = delivery.deliver(cid, "complete", db)
        assert lines[0].startswith("command: ERROR"), lines
        assert "folder sink" in lines[0]


# ---------------------------------------------------------------------------
# Webhook payload
# ---------------------------------------------------------------------------

def test_webhook_payload_shape() -> None:
    """Pin the JSON an automation receives. The transcript is excluded by
    default — it is tens of thousands of characters and most endpoints refuse
    a payload that size."""
    sent: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["headers"] = dict(req.headers)
        sent["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    import urllib.request as _ur
    real = _ur.urlopen
    _ur.urlopen = _fake_urlopen
    try:
        with _env(None) as (root, db, cid):
            (root / "delivery.json").write_text(json.dumps({
                "enabled": True,
                "sinks": [{"type": "webhook", "enabled": True,
                           "url": "http://127.0.0.1:5678/webhook/agent-chat",
                           "headers": {"X-Token": "abc"},
                           "text_key": "text"}],
            }), encoding="utf-8")
            lines = delivery.deliver(cid, "complete", db)
            assert lines[0].startswith("webhook: POST"), lines

        body = sent["body"]
        assert body["conversation_id"] == cid
        assert body["event"] == "complete"
        assert body["status"] == "complete"
        assert body["conv_type"] == "collaborate"
        assert body["preset"] == "plan"
        assert body["participants"] == ["claude-code", "codex"]
        assert body["message_count"] == 4
        assert "The actual deliverable." in body["result"]
        assert "transcript" not in body
        # text_key is the whole Slack/Discord adapter: one key name.
        assert str(cid) in body["text"]
        assert sent["headers"].get("X-token") == "abc"  # urllib title-cases
    finally:
        _ur.urlopen = real


# ---------------------------------------------------------------------------
# Wiring — the call sites must exist, or delivery silently never fires
# ---------------------------------------------------------------------------

def test_completion_paths_all_call_deliver() -> None:
    """Three places end a conversation. All three must fan out, or stopping one
    from the Web UI would deliver while stopping it from the CLI would not."""
    src = Path(__file__).resolve().parent.parent / "src"
    for rel in ("agent_chat_mcp.py", "web/db.py", "inspect_conversations.py"):
        text = (src / rel).read_text(encoding="utf-8")
        assert "delivery.deliver(" in text, f"{rel} never calls delivery.deliver()"


def test_mcp_result_signal_matches_delivery_constant() -> None:
    """delivery.SIGNAL_RESULT is a deliberate duplicate (the MCP server imports
    this module, so importing back would be a cycle). Keep them equal."""
    text = (Path(__file__).resolve().parent.parent / "src" / "agent_chat_mcp.py"
            ).read_text(encoding="utf-8")
    assert f'SIGNAL_RESULT = "{delivery.SIGNAL_RESULT}"' in text


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
