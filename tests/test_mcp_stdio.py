r"""The MCP server over its real transport: stdio JSON-RPC to a subprocess.

Every other suite calls the tool coroutines directly, so none of them would
notice the SDK failing to serve or a protocol version a CLI can't negotiate.
(It does not catch a stray ``print()`` to stdout: the SDK's client skips a
non-JSON line, and a real CLI may not. That rule stays a code-review rule.)
This one launches
``agent_chat_mcp.py`` the way a CLI does and talks to it with the SDK's own
client, in both connection modes a CLI may use:

* ``auto`` — the 2026-07-28 stateless protocol (``server/discover``). Claude
  Code tries this first; a server that can't answer costs it a slow first
  connect and a 7-day fallback to the old handshake.
* ``legacy`` — the 2025-era ``initialize`` handshake older clients still send.

Then two server processes, one per seat, play a seeded ``max_turns=1``
conversation to ``status='complete'`` through the shared WAL file.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_mcp_stdio.py

Uses an isolated temp DB — never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

import anyio
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator import seeding  # noqa: E402

_SERVER = _SRC / "agent_chat_mcp.py"


def _params(agent_id: str, db_path: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER), "--agent-id", agent_id, "--db-path", str(db_path)],
    )


async def _call(client: Client, tool: str, **params: Any) -> dict[str, Any]:
    result = await client.call_tool(tool, {"params": params})
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def _connect(mode: str) -> tuple[str, set[str], dict[str, Any]]:
    db = Path(tempfile.mkdtemp()) / "chat.db"

    async def go() -> tuple[str, set[str], dict[str, Any]]:
        async with Client(_params("codex", db), mode=mode) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            return client.protocol_version, tools, await _call(client, "get_my_turn")

    return anyio.run(go)


def test_modern_protocol_negotiated() -> None:
    version, tools, state = _connect("auto")
    assert version in MODERN_PROTOCOL_VERSIONS, f"fell back to {version}"
    assert {"get_my_turn", "send_message", "wait_for_turn", "get_kickoff"} <= tools
    assert state["status"] == "no_conversation"


def test_legacy_handshake_still_served() -> None:
    version, tools, state = _connect("legacy")
    assert version in HANDSHAKE_PROTOCOL_VERSIONS, version
    assert "send_message" in tools
    assert state["status"] == "no_conversation"


def test_two_servers_finish_a_seeded_conversation() -> None:
    db = Path(tempfile.mkdtemp()) / "chat.db"
    seeding.seed_conversation(
        db_path=str(db), topic="stdio smoke", participants=["codex", "claude-code"],
        mode="turns", max_turns=1, first="codex",
    )

    async def turn(agent_id: str, content: str) -> dict[str, Any]:
        async with Client(_params(agent_id, db)) as client:
            assert (await _call(client, "get_my_turn"))["status"] == "your_turn"
            return await _call(client, "send_message", content=content)

    anyio.run(turn, "codex", "opening")
    anyio.run(turn, "claude-code", "reply")

    conn = sqlite3.connect(str(db))
    try:
        status = conn.execute("SELECT status FROM conversations").fetchone()[0]
        senders = [r[0] for r in conn.execute("SELECT sender FROM messages ORDER BY id")]
    finally:
        conn.close()
    assert status == "complete", status
    assert senders[-2:] == ["codex", "claude-code"], senders


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
