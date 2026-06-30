r"""Tests for the public read-only gate + middleware wiring in ``web_ui``.

Covers the security fix that makes the hosted Fly mirror read-only:

* :class:`web_ui.ReadOnlyMiddleware` rejects browser mutations (403) while
  leaving GETs and the bearer-gated ``/api/ingest`` sync realm open.
* :func:`web_ui._build_middleware` assembles the stack from the
  ``AGENT_CHAT_PUBLIC_READONLY`` and ``AGENT_CHAT_BASIC_AUTH_PASSWORD``
  env flags (both off by default).

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_web_readonly.py

Uses an isolated temp ``chat.db`` — never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import web_ui  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Middleware behaviour, in isolation (no DB, no real routes)
# ---------------------------------------------------------------------------

def _isolated_client() -> TestClient:
    """A tiny app wrapping ReadOnlyMiddleware around stand-in routes."""

    async def ok(request):
        return JSONResponse({"ok": True})

    async def mutate(request):
        return JSONResponse({"mutated": True})

    async def ingest(request):
        # Stand-in for the real bearer-gated handler.
        return JSONResponse({"ingested": True})

    app = Starlette(
        routes=[
            Route("/conversations", ok, methods=["GET"]),
            Route("/api/personas", mutate, methods=["POST"]),
            Route("/api/conversations/1/delete", mutate, methods=["POST"]),
            Route("/api/ingest", ingest, methods=["POST"]),
        ],
        middleware=[Middleware(web_ui.ReadOnlyMiddleware)],
    )
    return TestClient(app)


def test_readonly_allows_get():
    client = _isolated_client()
    resp = client.get("/conversations")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_readonly_allows_head():
    # Starlette auto-serves HEAD for GET routes; the gate must not block it.
    client = _isolated_client()
    resp = client.head("/conversations")
    assert resp.status_code == 200


def test_readonly_blocks_post_mutations():
    client = _isolated_client()
    for path in ("/api/personas", "/api/conversations/1/delete"):
        resp = client.post(path)
        assert resp.status_code == 403, path
        assert resp.json()["error"] == "read-only deployment", path


def test_readonly_allows_ingest_bearer_realm():
    # /api/ingest is exempt: it authenticates itself in the route handler,
    # so the local->Fly sidecar keeps pushing even on a read-only mirror.
    client = _isolated_client()
    resp = client.post("/api/ingest")
    assert resp.status_code == 200
    assert resp.json() == {"ingested": True}


# ---------------------------------------------------------------------------
# 2. _env_truthy + _build_middleware wiring (no DB)
# ---------------------------------------------------------------------------

def test_env_truthy_variants(monkeypatch=None):
    truthy = ["1", "true", "TRUE", "Yes", "on", "  on  "]
    falsy = ["", "0", "false", "no", "off", "nope"]
    for val in truthy:
        os.environ["AGENT_CHAT_TEST_FLAG"] = val
        assert web_ui._env_truthy("AGENT_CHAT_TEST_FLAG") is True, repr(val)
    for val in falsy:
        os.environ["AGENT_CHAT_TEST_FLAG"] = val
        assert web_ui._env_truthy("AGENT_CHAT_TEST_FLAG") is False, repr(val)
    os.environ.pop("AGENT_CHAT_TEST_FLAG", None)
    assert web_ui._env_truthy("AGENT_CHAT_TEST_FLAG") is False


def _build_with_env(**env) -> list:
    """Call _build_middleware with a clean copy of the relevant env vars."""
    saved = {}
    keys = (
        "AGENT_CHAT_PUBLIC_READONLY",
        "AGENT_CHAT_BASIC_AUTH_PASSWORD",
        "AGENT_CHAT_BASIC_AUTH_USER",
    )
    for k in keys:
        saved[k] = os.environ.pop(k, None)
    try:
        for k, v in env.items():
            os.environ[k] = v
        return web_ui._build_middleware()
    finally:
        for k in keys:
            os.environ.pop(k, None)
            if saved[k] is not None:
                os.environ[k] = saved[k]


def test_build_middleware_default_empty():
    assert _build_with_env() == []


def test_build_middleware_readonly_only():
    stack = _build_with_env(AGENT_CHAT_PUBLIC_READONLY="1")
    assert [m.cls for m in stack] == [web_ui.ReadOnlyMiddleware]


def test_build_middleware_basic_auth_only():
    stack = _build_with_env(AGENT_CHAT_BASIC_AUTH_PASSWORD="secret")
    assert [m.cls for m in stack] == [web_ui.BasicAuthMiddleware]


def test_build_middleware_both_auth_outermost():
    stack = _build_with_env(
        AGENT_CHAT_PUBLIC_READONLY="true",
        AGENT_CHAT_BASIC_AUTH_PASSWORD="secret",
    )
    # Basic auth first (outermost) so unauthenticated requests are challenged
    # before the read-only check runs.
    assert [m.cls for m in stack] == [
        web_ui.BasicAuthMiddleware,
        web_ui.ReadOnlyMiddleware,
    ]


# ---------------------------------------------------------------------------
# 3. End-to-end against the real route table with the flag on
# ---------------------------------------------------------------------------

def _reload_app_readonly(tmp_db: Path):
    """Reload web_ui so ``app`` is rebuilt with the read-only flag, pointed at
    an isolated temp DB."""
    os.environ["AGENT_CHAT_PUBLIC_READONLY"] = "1"
    importlib.reload(web_ui)
    web_ui.DB_PATH = str(tmp_db)
    web_ui.db_init()
    return web_ui.app


def test_real_routes_readonly_end_to_end():
    saved = os.environ.get("AGENT_CHAT_PUBLIC_READONLY")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp_db = Path(d) / "chat.db"
        try:
            app = _reload_app_readonly(tmp_db)
            client = TestClient(app)

            # Reads still work against the live route table.
            assert client.get("/conversations").status_code == 200
            assert client.get("/api/conversations").status_code == 200

            # Every browser mutation route is blocked before reaching its
            # handler (so no DB row is touched).
            blocked = [
                ("POST", "/api/conversations/1/stop"),
                ("POST", "/api/conversations/1/delete"),
                ("POST", "/api/orchestrate"),
                ("POST", "/api/personas"),
                ("POST", "/api/personas/import"),
                ("POST", "/api/personas/bulk-delete"),
                ("POST", "/api/personas/some-slug"),
                ("POST", "/api/personas/some-slug/delete"),
            ]
            for method, path in blocked:
                resp = client.request(method, path)
                assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
                assert resp.json()["error"] == "read-only deployment", path
        finally:
            os.environ.pop("AGENT_CHAT_PUBLIC_READONLY", None)
            if saved is not None:
                os.environ["AGENT_CHAT_PUBLIC_READONLY"] = saved
            # Restore the module to its default (flag-off) state for any
            # later importers in the same process.
            importlib.reload(web_ui)


def test_orchestrate_is_local_only_when_readonly():
    """Hosted /orchestrate renders the local-only explainer (not the form),
    and the matching POST is blocked — while a local instance keeps the form."""
    saved = os.environ.get("AGENT_CHAT_PUBLIC_READONLY")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp_db = Path(d) / "chat.db"
        try:
            # Hosted / read-only.
            app = _reload_app_readonly(tmp_db)
            client = TestClient(app)
            page = client.get("/orchestrate")
            assert page.status_code == 200
            assert "Orchestration runs locally" in page.text
            assert "Run preflight + start conversation" not in page.text
            assert client.post("/api/orchestrate").status_code == 403

            # Local / writable: form returns, explainer does not.
            os.environ.pop("AGENT_CHAT_PUBLIC_READONLY", None)
            importlib.reload(web_ui)
            web_ui.DB_PATH = str(tmp_db)
            web_ui.db_init()
            local = TestClient(web_ui.app).get("/orchestrate")
            assert local.status_code == 200
            assert "Run preflight + start conversation" in local.text
            assert "Orchestration runs locally" not in local.text
        finally:
            os.environ.pop("AGENT_CHAT_PUBLIC_READONLY", None)
            if saved is not None:
                os.environ["AGENT_CHAT_PUBLIC_READONLY"] = saved
            importlib.reload(web_ui)


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
