r"""Tests for CLI availability + the /setup onboarding surface.

Covers :mod:`orchestrator.availability` — the module that answers "which CLI
tools does this machine have", which is what stops a fresh clone being shown
five tools and four failures:

* the declaration file (absent vs empty are different answers, and only one of
  them means "ask me"),
* declaration overriding detection in **both** directions,
* :func:`plan_seats` round-robin, which is what makes one CLI enough,
* the ``/setup`` page + its API, and the ``/extension`` explainer,
* parity between ``CLI_BINARIES`` and the launcher names in
  ``scripts/lib/spawn-agents.ps1`` — detecting a CLI under a name we then fail
  to spawn is a silent, confusing failure.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_availability.py

Uses an isolated temp DB and an isolated temp declaration file — never touches
the real ``db/chat.db`` or ``config/available-clis.json``.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from starlette.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator import availability as avail  # noqa: E402
from orchestrator import seats  # noqa: E402


@contextlib.contextmanager
def _isolated_config(initial: dict | None = None):
    """Point ``$AGENT_CHAT_CLI_CONFIG`` at a throwaway file for one test."""
    saved = os.environ.get("AGENT_CHAT_CLI_CONFIG")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        path = Path(d) / "available-clis.json"
        if initial is not None:
            path.write_text(json.dumps(initial), encoding="utf-8")
        os.environ["AGENT_CHAT_CLI_CONFIG"] = str(path)
        try:
            yield path
        finally:
            os.environ.pop("AGENT_CHAT_CLI_CONFIG", None)
            if saved is not None:
                os.environ["AGENT_CHAT_CLI_CONFIG"] = saved


# ---------------------------------------------------------------------------
# 1. The declaration file
# ---------------------------------------------------------------------------

def test_config_file_honours_env_override():
    with _isolated_config() as path:
        assert avail.config_file() == path
    # Default lands inside the repo's gitignored config/ folder.
    assert avail.config_file().parent.name == "config"


def test_no_file_means_never_answered():
    with _isolated_config():
        assert avail.load_declared() is None
        assert avail.is_declared() is False


def test_empty_list_is_a_real_answer_distinct_from_absent():
    # "I have nothing wired up yet" must not be confused with "ask me" — the
    # first should stop the app guessing, the second shouldn't.
    with _isolated_config():
        avail.save_declared([])
        assert avail.load_declared() == []
        assert avail.is_declared() is True


def test_malformed_file_degrades_to_detection_not_to_empty():
    # Falling back to [] would offer the operator nothing at all on a corrupt
    # file; falling back to None re-runs detection, which is recoverable.
    for junk in ("{not json", '{"available": "claude-code"}', "[]"):
        with _isolated_config() as path:
            path.write_text(junk, encoding="utf-8")
            assert avail.load_declared() is None, junk


def test_save_normalises_order_and_drops_duplicates():
    with _isolated_config():
        avail.save_declared(["opencode", "claude-code", "opencode"])
        saved = avail.load_declared()
        assert saved == [c for c in seats.SUPPORTED_CLIS if c in {"opencode", "claude-code"}]
        assert saved.index("claude-code") < saved.index("opencode")


def test_save_rejects_unknown_cli():
    with _isolated_config():
        try:
            avail.save_declared(["claude-code", "not-a-cli"])
        except avail.AvailabilityError as e:
            assert "not-a-cli" in str(e)
        else:
            raise AssertionError("expected AvailabilityError for an unknown CLI id")


def test_clear_declared_returns_to_detection():
    with _isolated_config():
        avail.save_declared(["claude-code"])
        assert avail.is_declared() is True
        assert avail.clear_declared() is True
        assert avail.load_declared() is None


# ---------------------------------------------------------------------------
# 2. Declaration beats detection, in both directions
# ---------------------------------------------------------------------------

def test_declaration_overrides_detection_both_ways():
    with _isolated_config():
        # Declare exactly one tool, whatever this machine actually has.
        avail.save_declared(["claude-code"])
        assert avail.available_clis() == ["claude-code"]
        by_cli = {s.cli: s for s in avail.detect_all()}
        assert by_cli["claude-code"].available is True
        for cli in seats.SUPPORTED_CLIS:
            if cli != "claude-code":
                # Even a tool sitting right there on PATH is excluded once the
                # operator has said they don't want it.
                assert by_cli[cli].available is False, cli
                assert by_cli[cli].declared is False, cli


def test_declared_is_none_before_any_answer():
    with _isolated_config():
        for status in avail.detect_all():
            assert status.declared is None, status.cli
            # With no declaration, availability is exactly detection.
            assert status.available == status.detected, status.cli


def test_ready_requires_both_available_and_config_ok():
    with _isolated_config():
        avail.save_declared(list(seats.SUPPORTED_CLIS))
        for status in avail.detect_all():
            assert status.available is True, status.cli
            assert status.ready == status.config_ok, status.cli


def test_status_dict_is_json_serialisable():
    with _isolated_config():
        payload = [s.to_dict() for s in avail.detect_all()]
        json.dumps(payload)  # raises on a non-serialisable field
        assert {r["cli"] for r in payload} == set(seats.SUPPORTED_CLIS)


# ---------------------------------------------------------------------------
# 3. plan_seats — why one CLI is enough
# ---------------------------------------------------------------------------

def test_plan_seats_one_tool_multiplexes():
    assert avail.plan_seats(["claude-code"], 2) == ["claude-code", "claude-code-2"]
    assert avail.plan_seats(["claude-code"], 3) == [
        "claude-code", "claude-code-2", "claude-code-3",
    ]


def test_plan_seats_two_tools_is_one_seat_each():
    # The pre-seats default. This is the regression that matters most: adding
    # multiplexing must not change what a normal two-CLI operator gets.
    assert avail.plan_seats(["claude-code", "codex"], 2) == ["claude-code", "codex"]


def test_plan_seats_deals_round_robin_not_in_blocks():
    assert avail.plan_seats(["claude-code", "codex"], 3) == [
        "claude-code", "codex", "claude-code-2",
    ]
    assert avail.plan_seats(["claude-code", "codex"], 4) == [
        "claude-code", "codex", "claude-code-2", "codex-2",
    ]


def test_plan_seats_edges():
    assert avail.plan_seats(["codex"], 0) == []
    for bad, args in (("no tools", ([], 2)), ("over capacity", (["codex"], 6))):
        try:
            avail.plan_seats(*args)
        except avail.AvailabilityError:
            pass
        else:
            raise AssertionError(f"expected AvailabilityError: {bad}")


def test_plan_seats_ids_are_valid_seats():
    plan = avail.plan_seats(["claude-code", "codex"], 5)
    seats.validate_seats(plan)
    assert len(set(plan)) == len(plan)


def test_missing_seat_folders_ignores_seat_one():
    # Seat 1's folder is part of registering the CLI at all — a missing one is a
    # preflight failure with its own advice, not something to clone.
    missing = avail.missing_seat_folders(["claude-code", "claude-code-4", "codex-5"])
    assert "claude-code" not in missing
    assert set(missing) <= {"claude-code-4", "codex-5"}


def test_available_seats_is_filtered_by_declaration():
    with _isolated_config():
        avail.save_declared(["claude-code"])
        offered = avail.available_seats()
        assert offered, "seat 1 of a declared tool must always be offered"
        assert all(seats.seat_cli(s) == "claude-code" for s in offered), offered


# ---------------------------------------------------------------------------
# 4. Registry parity
# ---------------------------------------------------------------------------

def test_cli_binaries_covers_every_supported_cli():
    assert set(avail.CLI_BINARIES) == set(seats.SUPPORTED_CLIS), (
        "CLI_BINARIES and SUPPORTED_CLIS have drifted — a tool with no launcher "
        "name can never be detected"
    )


def test_binary_names_match_the_spawn_registry():
    """``availability.CLI_BINARIES`` ↔ ``$Clis[...].Exe`` in spawn-agents.ps1.

    Detecting a CLI under one name and launching it under another is a silent
    failure: setup says "on PATH", the launcher says "not found".
    """
    text = (_ROOT / "scripts" / "lib" / "spawn-agents.ps1").read_text(encoding="utf-8")
    found = dict(
        re.findall(r"'([a-z-]+)'\s*=\s*@\{[^}]*?Exe\s*=\s*'([^']+)'", text, re.DOTALL)
    )
    assert found, "could not parse the $Clis table out of spawn-agents.ps1"
    for cli, exe in found.items():
        # OpenCode's Exe carries a subcommand ('opencode run'); probe token one.
        binary = exe.split()[0]
        assert cli in avail.CLI_BINARIES, f"{cli} is spawnable but not detectable"
        assert binary in avail.CLI_BINARIES[cli], (
            f"spawn-agents.ps1 launches {cli} as {binary!r}, but availability "
            f"probes for {avail.CLI_BINARIES[cli]}"
        )


# ---------------------------------------------------------------------------
# 5. The web surface
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _client(readonly: bool = False):
    """A TestClient on a freshly-reloaded app, isolated DB + config file."""
    import web_ui

    saved_ro = os.environ.get("AGENT_CHAT_PUBLIC_READONLY")
    with _isolated_config(), tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        if readonly:
            os.environ["AGENT_CHAT_PUBLIC_READONLY"] = "1"
        else:
            os.environ.pop("AGENT_CHAT_PUBLIC_READONLY", None)
        try:
            importlib.reload(web_ui)
            web_ui.set_db_path(str(Path(d) / "chat.db"))
            web_ui.db_init()
            yield TestClient(web_ui.app)
        finally:
            os.environ.pop("AGENT_CHAT_PUBLIC_READONLY", None)
            if saved_ro is not None:
                os.environ["AGENT_CHAT_PUBLIC_READONLY"] = saved_ro
            importlib.reload(web_ui)


def test_setup_page_renders_locally():
    with _client() as client:
        page = client.get("/setup")
        assert page.status_code == 200
        assert "Which CLI tools do you have?" in page.text
        for cli in seats.SUPPORTED_CLIS:
            assert f'value="{cli}"' in page.text, cli


def test_setup_page_is_local_only_when_readonly():
    with _client(readonly=True) as client:
        page = client.get("/setup")
        assert page.status_code == 200
        assert "CLI setup happens on your machine" in page.text
        assert "Which CLI tools do you have?" not in page.text
        assert client.post("/api/setup", json={"available": []}).status_code == 403
        assert client.post("/api/setup/seats", json={"seats": []}).status_code == 403


def test_api_setup_round_trip():
    with _client() as client:
        before = client.get("/api/setup").json()
        assert before["declared"] is False
        assert {c["cli"] for c in before["clis"]} == set(seats.SUPPORTED_CLIS)

        saved = client.post("/api/setup", json={"available": ["claude-code"]})
        assert saved.status_code == 200
        assert saved.json()["available"] == ["claude-code"]

        after = client.get("/api/setup").json()
        assert after["declared"] is True
        assert after["available"] == ["claude-code"]
        assert all(s.startswith("claude-code") for s in after["existing_seats"])


def test_api_setup_rejects_bad_bodies():
    with _client() as client:
        assert client.post("/api/setup", json=["claude-code"]).status_code == 400
        assert client.post("/api/setup", json={"available": "claude-code"}).status_code == 400
        bad = client.post("/api/setup", json={"available": ["nope"]})
        assert bad.status_code == 400
        assert "nope" in bad.json()["error"]


def test_api_setup_seats_refuses_seat_one_and_undeclared_tools():
    with _client() as client:
        client.post("/api/setup", json={"available": ["claude-code"]})
        first = client.post("/api/setup/seats", json={"seats": ["claude-code"]})
        assert first.status_code == 400
        assert "seat 1" in first.json()["error"]

        other = client.post("/api/setup/seats", json={"seats": ["codex-2"]})
        assert other.status_code == 400
        assert "available CLIs" in other.json()["error"]

        assert client.post("/api/setup/seats", json={"seats": "codex-2"}).status_code == 400


def test_orchestrate_only_offers_available_seats():
    with _client() as client:
        client.post("/api/setup", json={"available": ["claude-code"]})
        page = client.get("/orchestrate").text
        offered = re.findall(r'name="cli" value="([^"]+)"', page)
        assert offered, "the form must still list the one available seat"
        assert all(s.startswith("claude-code") for s in offered), offered
        assert "codex" not in offered


def test_orchestrate_warns_when_there_is_nothing_to_run():
    with _client() as client:
        client.post("/api/setup", json={"available": []})
        page = client.get("/orchestrate").text
        assert "No CLI tools available" in page
        assert 'href="/setup"' in page


def test_extension_page_renders_on_both_deploys():
    for readonly in (False, True):
        with _client(readonly=readonly) as client:
            page = client.get("/extension")
            assert page.status_code == 200, readonly
            # The invariant is the reason this page exists; it must be stated
            # on the hosted copy too.
            assert "It drafts. It never posts." in page.text, readonly


def test_demo_banner_tracks_the_readonly_flag():
    # The banner and the 403s key off the same env var, so a page that promises
    # "read-only" and a server that allows writes can't come apart.
    # Match the element, not the string: `.demo-strip` rules ship in the CSS on
    # every page regardless, which is exactly the kind of false pass that would
    # make this test useless.
    marker = '<div class="demo-strip"'
    with _client(readonly=True) as client:
        for path in ("/", "/conversations", "/personas", "/extension"):
            assert marker in client.get(path).text, path
    with _client() as client:
        for path in ("/", "/conversations", "/personas", "/extension"):
            assert marker not in client.get(path).text, path


def test_sidebar_groups_third_party_links_below_a_separator():
    with _client() as client:
        page = client.get("/conversations").text
        rail = page[page.index('<nav class="siderail"'):page.index("</nav>")]
        assert '<span class="rail-glabel">Resources</span>' in rail
        sep = rail.index('class="rail-sep"')
        # This app's pages above the separator; reference links below it.
        for href in ('href="/conversations"', 'href="/personas"', 'href="/setup"'):
            assert rail.index(href) < sep, href
        for marker in ('href="/#resources"', "persona-registry", "debate-chat-theater"):
            assert rail.index(marker) > sep, marker


def test_personas_page_links_out_to_the_registry():
    with _client() as client:
        page = client.get("/personas").text
        assert "Get more cards" in page
        assert "persona-registry" in page


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
