"""Auth middleware + env-flag middleware-stack assembly.

Two independent gates, both off by default (local dev stays fully writable):
``AGENT_CHAT_BASIC_AUTH_PASSWORD`` (HTTP basic) and
``AGENT_CHAT_PUBLIC_READONLY`` (reject browser mutations — the hosted
Fly-mirror posture).
"""

from __future__ import annotations

import base64
import os
import secrets

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# ---------------------------------------------------------------------------
# Auth (HTTP Basic) — only active when AGENT_CHAT_BASIC_AUTH_PASSWORD is set
# ---------------------------------------------------------------------------

class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Single shared-credential gate for the public Fly deploy.

    Off by default. Enable by setting AGENT_CHAT_BASIC_AUTH_PASSWORD
    (and optionally AGENT_CHAT_BASIC_AUTH_USER, which defaults to
    "admin"). For real multi-user auth, replace this with whatever
    your platform fronts you with (Cloudflare Access, Tailscale
    Funnel, etc.).
    """

    def __init__(self, app, username: str, password: str) -> None:
        super().__init__(app)
        self._user_b = username.encode("utf-8")
        self._pwd_b = password.encode("utf-8")

    async def dispatch(self, request: Request, call_next):
        # /api/ingest is a separate auth realm (bearer token, validated in
        # the route handler). Skip the basic-auth gate so machine-to-machine
        # clients don't have to also know the human basic-auth password.
        # /favicon.svg and /avatars/* are static, non-sensitive assets — let
        # browsers fetch them for the auth-challenge tab itself so images show.
        path = request.url.path
        if (path in ("/api/ingest", "/api/since", "/favicon.svg")
                or path.startswith("/avatars/")):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8", "replace")
                user, _, pwd = decoded.partition(":")
                if (
                    secrets.compare_digest(user.encode("utf-8"), self._user_b)
                    and secrets.compare_digest(pwd.encode("utf-8"), self._pwd_b)
                ):
                    return await call_next(request)
            except Exception:
                pass
        return Response(
            "Authentication required.\n",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="agent_chat"'},
            media_type="text/plain",
        )


# ---------------------------------------------------------------------------
# Read-only public mode — reject browser mutations when
# AGENT_CHAT_PUBLIC_READONLY is set (the posture for the hosted Fly mirror)
# ---------------------------------------------------------------------------

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# POST routes that carry their own bearer-token auth (the sidecar sync realm)
# and must keep working even when the public site is read-only.
_BEARER_REALM_PATHS = frozenset({"/api/ingest"})


def _env_truthy(name: str) -> bool:
    """True when env var *name* is set to a truthy string (1/true/yes/on)."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _is_public_readonly() -> bool:
    """True on the hosted public mirror (AGENT_CHAT_PUBLIC_READONLY set).

    Route handlers use this to render hosted-appropriate UI — e.g. /orchestrate
    becomes a local-only explainer instead of a form that can't spawn local
    CLIs. The actual mutation block is enforced by ReadOnlyMiddleware; this is
    just for presentation."""
    return _env_truthy("AGENT_CHAT_PUBLIC_READONLY")


class ReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject browser mutations when the deploy is in public read-only mode.

    Enabled by setting AGENT_CHAT_PUBLIC_READONLY (1/true/yes/on) — the
    intended posture for the hosted Fly mirror, which is a viewer, not a
    control surface. Any non-safe HTTP method (everything but GET/HEAD/
    OPTIONS) is answered with 403, *except* the bearer-token sync realm
    (/api/ingest), which authenticates itself in the route handler so the
    local->Fly sidecar keeps pushing. New mutation routes are covered
    automatically — the gate keys off the HTTP method, not a path list.
    """

    async def dispatch(self, request: Request, call_next):
        if (
            request.method not in _SAFE_METHODS
            and request.url.path not in _BEARER_REALM_PATHS
        ):
            return JSONResponse(
                {
                    "error": "read-only deployment",
                    "detail": (
                        "This hosted mirror is read-only. Run conversations and "
                        "manage personas on your local instance."
                    ),
                },
                status_code=403,
            )
        return await call_next(request)


def _build_middleware() -> list[Middleware]:
    """Assemble the middleware stack from env-var feature flags.

    Both gates are off by default, so local dev stays fully writable and
    unauthenticated:

    * AGENT_CHAT_BASIC_AUTH_PASSWORD → require HTTP basic auth on every route
      except the bearer/sync/static exceptions baked into BasicAuthMiddleware.
    * AGENT_CHAT_PUBLIC_READONLY → block browser mutations (403) while leaving
      GETs and the bearer-gated /api/ingest sync realm open.

    The hosted Fly deploy is expected to set at least the read-only flag.
    Basic auth is listed first so it forms the outermost layer (an
    unauthenticated request is challenged before the read-only check runs).
    """
    stack: list[Middleware] = []
    password = os.environ.get("AGENT_CHAT_BASIC_AUTH_PASSWORD")
    if password:
        user = os.environ.get("AGENT_CHAT_BASIC_AUTH_USER", "admin")
        stack.append(Middleware(BasicAuthMiddleware, username=user, password=password))
    if _env_truthy("AGENT_CHAT_PUBLIC_READONLY"):
        stack.append(Middleware(ReadOnlyMiddleware))
    return stack
