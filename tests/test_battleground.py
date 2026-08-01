r"""Tests for AgentBattleground — the arena bridge and the agent-side loop.

Covers the three things that would break the feature silently:

* **The bridge contract** (``/api/battleground/*``): capture → arena → draft →
  verdict, including the input scrubbing that stands between a hostile web
  page and the DB.
* **The human-in-the-loop gate**: a draft is born ``pending``, and only an
  explicit operator verdict moves it. Nothing in the server can post.
* **Re-capture merging**: known post ids refresh in place, new ones append —
  the property that lets an operator re-capture a live thread mid-argument
  without duplicating the backlog the agent has already read.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_battleground.py

Uses an isolated temp ``chat.db`` — never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from starlette.testclient import TestClient

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import web_ui  # noqa: E402
from web import db as web_db  # noqa: E402


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class _Env:
    """Temp DB + TestClient, restoring the module's DB path on exit."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._saved_db = web_db.DB_PATH
        self._saved_env = os.environ.get("AGENT_CHAT_DB")
        self.db_path = str(Path(self._tmp.name) / "chat.db")

    def __enter__(self) -> _Env:
        web_ui.set_db_path(self.db_path)
        web_ui.db_init()
        self.client = TestClient(web_ui.app)
        return self

    def __exit__(self, *exc) -> None:
        if self._saved_db:
            web_ui.set_db_path(self._saved_db)
        elif self._saved_env is None:
            os.environ.pop("AGENT_CHAT_DB", None)
        self._tmp.cleanup()


_THREAD = [
    {"id": "t1", "author": "op", "text": "Rust is strictly better than Go for services.", "depth": 0},
    {"id": "t2", "author": "gopher", "text": "Compile times say otherwise.", "depth": 1},
]


def _open_arena(client: TestClient, **overrides) -> dict:
    body = {
        "url": "https://reddit.com/r/programming/comments/abc/rust_vs_go",
        "site": "reddit",
        "title": "Rust vs Go",
        "thread": _THREAD,
        "stance": "Defend Go.",
        "agent_id": "claude-code",
    }
    body.update(overrides)
    resp = client.post("/api/battleground/arenas", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["arena"]


# ---------------------------------------------------------------------------
# 1. Arena lifecycle over the bridge
# ---------------------------------------------------------------------------

def test_create_arena_stores_thread_and_cast():
    with _Env() as env:
        arena = _open_arena(env.client)
        assert arena["status"] == "open"
        assert arena["site"] == "reddit"
        assert arena["agent_id"] == "claude-code"
        assert [p["id"] for p in arena["thread"]] == ["t1", "t2"]
        assert arena["stance"] == "Defend Go."


def test_create_arena_requires_url_and_posts():
    with _Env() as env:
        no_url = env.client.post(
            "/api/battleground/arenas", json={"thread": _THREAD}
        )
        assert no_url.status_code == 400
        assert "url is required" in no_url.json()["error"]

        no_posts = env.client.post(
            "/api/battleground/arenas",
            json={"url": "https://example.com", "thread": []},
        )
        assert no_posts.status_code == 400


def test_create_arena_rejects_unknown_agent_and_persona():
    with _Env() as env:
        bad_agent = env.client.post(
            "/api/battleground/arenas",
            json={"url": "https://example.com", "thread": _THREAD, "agent_id": "skynet"},
        )
        assert bad_agent.status_code == 400
        assert "supported" in bad_agent.json()

        bad_persona = env.client.post(
            "/api/battleground/arenas",
            json={
                "url": "https://example.com",
                "thread": _THREAD,
                "persona": "definitely-not-a-real-persona",
            },
        )
        assert bad_persona.status_code == 400


def test_capture_input_is_scrubbed():
    """A captured page is untrusted input: unknown keys are dropped, oversized
    text is clipped, empty nodes are skipped, and an unknown site falls back to
    'generic' rather than being stored verbatim."""
    with _Env() as env:
        arena = _open_arena(
            env.client,
            site="myspace",
            thread=[
                {"id": "a", "author": "x", "text": "y" * 20_000, "evil": "<script>"},
                {"id": "b", "author": "", "text": "   "},  # empty → dropped
                {"id": "c", "author": "z", "text": "real", "depth": 999},
            ],
        )
        assert arena["site"] == "generic"
        posts = arena["thread"]
        assert [p["id"] for p in posts] == ["a", "c"]
        assert len(posts[0]["text"]) == 8_000
        assert "evil" not in posts[0]
        assert posts[1]["author"] == "z"
        assert "depth" not in posts[1]  # 999 is out of range → not stored


def test_every_shipped_adapter_label_survives_a_capture():
    """The extension's adapters and the bridge's KNOWN_SITES have to agree.

    They live in different languages in different directories, so a new adapter
    whose label the bridge doesn't know is silently downgraded to 'generic' —
    the arena still works, but the site is wrong everywhere it's shown.
    """
    with _Env() as env:
        capture_js = (
            Path(__file__).resolve().parent.parent / "extension" / "src" / "capture.js"
        ).read_text(encoding="utf-8")

        for site in ("reddit", "x", "hackernews", "youtube", "linkedin",
                     "substack", "discourse", "disqus", "generic"):
            arena = _open_arena(env.client, site=site)
            assert arena["site"] == site, f"bridge downgraded {site!r}"
            assert f"'{site}'" in capture_js, f"no adapter in capture.js emits {site!r}"


def test_frame_namespaced_ids_merge_like_any_other():
    """Comments captured from a third-party iframe (Disqus and friends) carry
    a `<platform>:<id>` id so they can't collide with the host page's. They
    have to merge on re-capture exactly like a same-frame post."""
    with _Env() as env:
        arena = _open_arena(
            env.client,
            site="disqus",
            thread=[
                {"id": "page", "author": "news.example", "text": "Article lead."},
                {"id": "disqus:501", "author": "reader", "text": "First!"},
            ],
        )
        resp = env.client.post(
            f"/api/battleground/arenas/{arena['id']}/capture",
            json={
                "thread": [
                    {"id": "disqus:501", "author": "reader", "text": "First! (edited)"},
                    {"id": "disqus:502", "author": "other", "text": "A real reply."},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["posts_added"] == 1
        thread = resp.json()["arena"]["thread"]
        assert [p["id"] for p in thread] == ["page", "disqus:501", "disqus:502"]
        assert thread[1]["text"].endswith("(edited)")


def test_recapture_merges_on_post_id():
    with _Env() as env:
        arena = _open_arena(env.client)
        resp = env.client.post(
            f"/api/battleground/arenas/{arena['id']}/capture",
            json={
                "thread": [
                    # t2 edited since first capture, t3 brand new
                    {"id": "t2", "author": "gopher", "text": "Compile times say otherwise. (edited)"},
                    {"id": "t3", "author": "rustacean", "text": "Skill issue."},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["posts_added"] == 1
        thread = resp.json()["arena"]["thread"]
        assert [p["id"] for p in thread] == ["t1", "t2", "t3"]
        assert thread[1]["text"].endswith("(edited)")


def test_reply_target_round_trips_and_is_validated():
    """The operator can point the agent at one captured post.

    It has to name a post the arena actually holds — a stale id would reach the
    agent as a `reply_target` of null with no explanation.
    """
    with _Env() as env:
        arena = _open_arena(env.client, reply_to="t2")
        assert arena["reply_to"] == "t2"

        # Re-target.
        resp = env.client.post(
            f"/api/battleground/arenas/{arena['id']}", json={"reply_to": "t1"}
        )
        assert resp.status_code == 200
        assert resp.json()["arena"]["reply_to"] == "t1"

        # An id that isn't in the thread is refused, on create and on update.
        assert env.client.post(
            f"/api/battleground/arenas/{arena['id']}", json={"reply_to": "nope"}
        ).status_code == 400
        assert env.client.post(
            "/api/battleground/arenas",
            json={
                "url": "https://example.com/x",
                "thread": _THREAD,
                "reply_to": "nope",
            },
        ).status_code == 400

        # An empty string clears it; omitting it leaves it alone.
        env.client.post(
            f"/api/battleground/arenas/{arena['id']}", json={"stance": "unchanged"}
        )
        assert env.client.get(
            f"/api/battleground/arenas/{arena['id']}"
        ).json()["arena"]["reply_to"] == "t1"
        resp = env.client.post(
            f"/api/battleground/arenas/{arena['id']}", json={"reply_to": ""}
        )
        assert resp.json()["arena"]["reply_to"] is None


def test_healthz_answers_without_a_token():
    """/healthz exists to explain why the *other* calls are failing, so a bad
    or missing token must not be able to silence it."""
    with _Env() as env:
        os.environ["AGENT_CHAT_BATTLEGROUND_TOKEN"] = "s3cret"
        try:
            # Every other route is now challenged...
            assert env.client.get("/api/battleground/roster").status_code == 401
            # ...but health still answers, and says a token is in play.
            resp = env.client.get("/api/battleground/healthz")
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["db"] is True and body["schema"] is True
            assert body["token_required"] is True
            assert body["readonly"] is False
        finally:
            os.environ.pop("AGENT_CHAT_BATTLEGROUND_TOKEN", None)

        assert env.client.get(
            "/api/battleground/healthz"
        ).json()["token_required"] is False


def test_roster_launch_commands_match_the_spawn_registry():
    """The panel's handoff card shows how to start the cast CLI. That string
    lives in Python, the real launcher table lives in PowerShell, and a drift
    between them sends the operator to a folder or binary that isn't there."""
    from web.api import battleground as bg

    registry = (
        Path(__file__).resolve().parent.parent / "scripts" / "lib" / "spawn-agents.ps1"
    ).read_text(encoding="utf-8")

    with _Env() as env:
        launch = env.client.get("/api/battleground/roster").json()["launch"]
        # Every supported CLI the map knows about is offered...
        assert set(launch) <= set(bg.CLI_LAUNCH)
        assert "claude-code" in launch and "codex" in launch
        for cli, entry in launch.items():
            if cli == "gemini":
                continue  # deprecated fallback; not in the spawn registry
            assert entry["dir"].replace("/", "\\") in registry, (
                f"{cli}: launch dir {entry['dir']} is not in spawn-agents.ps1"
            )
            assert f"Exe = '{entry['exe']}" in registry, (
                f"{cli}: launch exe {entry['exe']!r} is not in spawn-agents.ps1"
            )


def test_update_and_close_arena():
    with _Env() as env:
        arena = _open_arena(env.client)
        resp = env.client.post(
            f"/api/battleground/arenas/{arena['id']}",
            json={"stance": "Actually, defend Rust.", "status": "closed"},
        )
        assert resp.status_code == 200
        assert resp.json()["arena"]["status"] == "closed"
        assert resp.json()["arena"]["stance"] == "Actually, defend Rust."
        # Untouched fields survive a partial update.
        assert resp.json()["arena"]["agent_id"] == "claude-code"


def test_delete_arena_cascades_drafts():
    with _Env() as env:
        arena = _open_arena(env.client)
        web_db.bg_create_draft(
            arena_id=arena["id"], agent_id="claude-code", content="a reply"
        )
        resp = env.client.post(f"/api/battleground/arenas/{arena['id']}/delete")
        assert resp.status_code == 200
        assert resp.json()["cascaded_drafts"] == 1
        assert env.client.get(f"/api/battleground/arenas/{arena['id']}").status_code == 404


def test_missing_arena_is_404():
    with _Env() as env:
        assert env.client.get("/api/battleground/arenas/999").status_code == 404
        assert env.client.post(
            "/api/battleground/arenas/999/capture", json={"thread": _THREAD}
        ).status_code == 404


# ---------------------------------------------------------------------------
# 2. The human-in-the-loop gate
# ---------------------------------------------------------------------------

def test_draft_starts_pending():
    with _Env() as env:
        arena = _open_arena(env.client)
        draft = web_db.bg_create_draft(
            arena_id=arena["id"],
            agent_id="claude-code",
            content="Go's compile times are the point.",
            rationale="Leading with the concession.",
        )
        assert draft["status"] == "pending"
        assert draft["posted_text"] is None
        # And it surfaces to the panel on the arena read.
        data = env.client.get(f"/api/battleground/arenas/{arena['id']}").json()
        assert len(data["drafts"]) == 1
        assert data["drafts"][0]["rationale"] == "Leading with the concession."


def test_verdict_transitions():
    with _Env() as env:
        arena = _open_arena(env.client)
        draft = web_db.bg_create_draft(
            arena_id=arena["id"], agent_id="claude-code", content="draft one"
        )
        resp = env.client.post(
            f"/api/battleground/drafts/{draft['id']}/verdict",
            json={"verdict": "rejected", "note": "too smug"},
        )
        assert resp.status_code == 200
        assert resp.json()["draft"]["status"] == "rejected"
        assert resp.json()["draft"]["verdict_note"] == "too smug"

        resp = env.client.post(
            f"/api/battleground/drafts/{draft['id']}/verdict",
            json={"verdict": "posted", "posted_text": "draft one, edited by hand"},
        )
        assert resp.json()["draft"]["status"] == "posted"
        assert resp.json()["draft"]["posted_text"] == "draft one, edited by hand"


def test_bad_verdict_rejected():
    with _Env() as env:
        arena = _open_arena(env.client)
        draft = web_db.bg_create_draft(
            arena_id=arena["id"], agent_id="claude-code", content="x"
        )
        resp = env.client.post(
            f"/api/battleground/drafts/{draft['id']}/verdict",
            json={"verdict": "published"},
        )
        assert resp.status_code == 400
        assert env.client.post(
            "/api/battleground/drafts/999/verdict", json={"verdict": "approved"}
        ).status_code == 404


def test_no_drafting_into_a_closed_arena():
    with _Env() as env:
        arena = _open_arena(env.client)
        env.client.post(
            f"/api/battleground/arenas/{arena['id']}", json={"status": "closed"}
        )
        assert (
            web_db.bg_create_draft(
                arena_id=arena["id"], agent_id="claude-code", content="too late"
            )
            is None
        )


# ---------------------------------------------------------------------------
# 3. Listing + roster
# ---------------------------------------------------------------------------

def test_list_arenas_filters():
    with _Env() as env:
        mine = _open_arena(env.client, agent_id="claude-code")
        theirs = _open_arena(env.client, agent_id="codex")
        _open_arena(env.client, agent_id=None)  # unassigned: open to anyone

        all_open = env.client.get("/api/battleground/arenas?status=open").json()
        assert all_open["count"] == 3

        # An agent sees its own arenas plus the unassigned ones — never the
        # one another CLI is already fighting in.
        for_me = env.client.get("/api/battleground/arenas?agent=claude-code").json()
        ids = {a["id"] for a in for_me["arenas"]}
        assert mine["id"] in ids
        assert theirs["id"] not in ids
        assert for_me["count"] == 2

        assert env.client.get("/api/battleground/arenas?status=bogus").status_code == 400


def test_roster_excludes_ai_model_cards():
    with _Env() as env:
        from orchestrator import personas as reg

        reg.create_persona(name="Test Debater", body="Argue.", group="Testers")
        reg.create_persona(name="Claude Code", body="Reference card.", group="AI-Models")
        roster = env.client.get("/api/battleground/roster").json()
        slugs = {p["slug"] for p in roster["personas"]}
        assert "test-debater" in slugs
        assert "claude-code" not in slugs  # reserved group, never castable
        assert "claude-code" in roster["agents"]
        # The panel labels captures from this list, so it has to carry every
        # adapter the extension can pick.
        assert {"reddit", "youtube", "discourse", "disqus", "generic"} <= set(roster["sites"])


def test_persona_body_is_snapshotted_onto_the_arena():
    """Editing a persona later must not retroactively rewrite what the agent
    was told to be in an arena that's already running."""
    with _Env() as env:
        from orchestrator import personas as reg

        reg.create_persona(name="Stoic", body="Be terse.", group="Testers")
        arena = _open_arena(env.client, persona="stoic")
        assert arena["persona_name"] == "Stoic"
        assert arena["persona_body"] == "Be terse."

        reg.update_persona("stoic", body="Be verbose.")
        again = env.client.get(f"/api/battleground/arenas/{arena['id']}").json()
        assert again["arena"]["persona_body"] == "Be terse."


# ---------------------------------------------------------------------------
# 4. Extension CORS gate
# ---------------------------------------------------------------------------

def test_cors_only_for_extension_origins_on_battleground_paths():
    with _Env() as env:
        ext = "chrome-extension://abcdefghijklmnop"
        resp = env.client.get("/api/battleground/roster", headers={"Origin": ext})
        assert resp.headers.get("access-control-allow-origin") == ext

        # A web page's origin is never echoed, so no site can read the bridge.
        page = env.client.get(
            "/api/battleground/roster", headers={"Origin": "https://evil.example"}
        )
        assert "access-control-allow-origin" not in page.headers

        # And the exemption doesn't leak to the rest of the app.
        other = env.client.get("/api/conversations", headers={"Origin": ext})
        assert "access-control-allow-origin" not in other.headers


def test_cors_preflight_answered():
    with _Env() as env:
        ext = "chrome-extension://abcdefghijklmnop"
        resp = env.client.options(
            "/api/battleground/arenas",
            headers={
                "Origin": ext,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 204
        assert resp.headers["access-control-allow-origin"] == ext
        assert "POST" in resp.headers["access-control-allow-methods"]


# ---------------------------------------------------------------------------
# 5. Schema parity — the four-site duplication footgun
# ---------------------------------------------------------------------------

def test_every_schema_declaration_creates_the_battleground_tables():
    """agent_chat_mcp / web.db / orchestrator.seeding each declare SCHEMA
    independently. A DB booted by any one of them must be usable by the other
    two, so all three have to know about these tables."""
    import agent_chat_mcp
    from orchestrator import seeding

    wanted = {"battleground_arenas", "battleground_drafts"}
    for label, schema in (
        ("agent_chat_mcp", agent_chat_mcp.SCHEMA),
        ("web.db", web_db.SCHEMA),
        ("orchestrator.seeding", seeding.SCHEMA),
    ):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            conn = sqlite3.connect(str(Path(d) / "t.db"))
            conn.executescript(schema)
            names = {
                r[0]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            conn.close()
            assert wanted <= names, f"{label} SCHEMA is missing {wanted - names}"


def test_battleground_tables_are_not_synced_to_the_mirror():
    """Captured third-party page content stays local: the sidecar's column
    lists must not carry it, and /api/since must not ship it."""
    payload_keys = set(
        web_db.since_payload("1970-01-01T00:00:00+00:00", []).keys()
    )
    assert not any("arena" in k or "battleground" in k for k in payload_keys)
    for cols in (web_db._CONV_COLUMNS, web_db._MSG_COLUMNS, web_db._PERSONA_COLUMNS):
        assert not any("arena" in c for c in cols)


# ---------------------------------------------------------------------------
# 6. The agent-side loop (MCP tools against the same tables)
# ---------------------------------------------------------------------------

def _mcp_json(coro_result: str) -> dict:
    return json.loads(coro_result)


def test_mcp_agent_loop_end_to_end():
    """get_arena → submit_draft → wait_for_verdict, the loop an agent runs."""
    import asyncio

    import agent_chat_mcp as mcp

    with _Env() as env:
        arena = _open_arena(env.client, agent_id=None)  # unassigned

        saved_agent, saved_db = mcp.AGENT_ID, mcp.DB_PATH
        mcp.AGENT_ID, mcp.DB_PATH = "codex", env.db_path
        try:
            listed = _mcp_json(asyncio.run(mcp.list_arenas(mcp.ListArenasInput())))
            assert listed["count"] == 1
            assert listed["arenas"][0]["posts"] == 2

            opened = _mcp_json(asyncio.run(mcp.get_arena(mcp.GetArenaInput())))
            assert opened["status"] == "ok"
            assert opened["arena"]["id"] == arena["id"]
            assert len(opened["arena"]["thread"]) == 2
            # Reading an unassigned arena claims it, so a second CLI can't
            # draft over the top of this one.
            assert "drafting, not posting" in opened["rules"]

            other = _mcp_json(asyncio.run(mcp.get_arena(mcp.GetArenaInput())))
            assert other["status"] == "ok"  # idempotent for the same agent
            mcp.AGENT_ID = "claude-code"
            blocked = _mcp_json(
                asyncio.run(mcp.get_arena(mcp.GetArenaInput(arena_id=arena["id"])))
            )
            assert blocked["status"] == "assigned_elsewhere"

            mcp.AGENT_ID = "codex"
            submitted = _mcp_json(
                asyncio.run(
                    mcp.submit_draft(
                        mcp.SubmitDraftInput(
                            arena_id=arena["id"],
                            content="Compile times are a feature, not a bug.",
                            reply_to="t2",
                        )
                    )
                )
            )
            assert submitted["status"] == "submitted"
            assert submitted["review_state"] == "pending"

            # Still pending → the long-poll times out rather than inventing a
            # verdict. 5s is the floor the input model allows.
            pending = _mcp_json(
                asyncio.run(
                    mcp.wait_for_verdict(mcp.WaitForVerdictInput(timeout_seconds=5))
                )
            )
            assert pending["status"] == "timeout"

            # Operator approves with an edit; the agent learns the edited text.
            env.client.post(
                f"/api/battleground/drafts/{submitted['draft_id']}/verdict",
                json={"verdict": "posted", "posted_text": "Compile times are a feature."},
            )
            verdict = _mcp_json(
                asyncio.run(
                    mcp.wait_for_verdict(mcp.WaitForVerdictInput(timeout_seconds=5))
                )
            )
            assert verdict["status"] == "verdict"
            assert verdict["verdict"] == "posted"
            assert verdict["operator_edited"] is True
            assert verdict["posted_text"] == "Compile times are a feature."
            assert len(verdict["thread"]) == 2
        finally:
            mcp.AGENT_ID, mcp.DB_PATH = saved_agent, saved_db


def test_mcp_get_arena_hands_over_the_operators_reply_target():
    """A post picked in the panel has to arrive as something the agent can act
    on — the id echoed on the arena, the post itself pulled out of the thread,
    and a `next` line that names it."""
    import asyncio

    import agent_chat_mcp as mcp

    with _Env() as env:
        arena = _open_arena(env.client, agent_id="codex", reply_to="t2")
        saved_agent, saved_db = mcp.AGENT_ID, mcp.DB_PATH
        mcp.AGENT_ID, mcp.DB_PATH = "codex", env.db_path
        try:
            opened = _mcp_json(
                asyncio.run(mcp.get_arena(mcp.GetArenaInput(arena_id=arena["id"])))
            )
            assert opened["arena"]["reply_to"] == "t2"
            assert opened["reply_target"]["author"] == "gopher"
            assert "reply_to='t2'" in opened["next"]

            # Cleared in the panel → the agent picks its own target again.
            env.client.post(
                f"/api/battleground/arenas/{arena['id']}", json={"reply_to": ""}
            )
            reopened = _mcp_json(
                asyncio.run(mcp.get_arena(mcp.GetArenaInput(arena_id=arena["id"])))
            )
            assert reopened["arena"]["reply_to"] is None
            assert reopened["reply_target"] is None
        finally:
            mcp.AGENT_ID, mcp.DB_PATH = saved_agent, saved_db


def test_mcp_reports_no_arena_cleanly():
    import asyncio

    import agent_chat_mcp as mcp

    with _Env() as env:
        saved_agent, saved_db = mcp.AGENT_ID, mcp.DB_PATH
        mcp.AGENT_ID, mcp.DB_PATH = "codex", env.db_path
        try:
            state = _mcp_json(asyncio.run(mcp.get_arena(mcp.GetArenaInput())))
            assert state["status"] == "no_arena"
            verdict = _mcp_json(
                asyncio.run(mcp.wait_for_verdict(mcp.WaitForVerdictInput()))
            )
            assert verdict["status"] == "not_found"
        finally:
            mcp.AGENT_ID, mcp.DB_PATH = saved_agent, saved_db


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
