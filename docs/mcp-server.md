<div align="center">

# 🔌 MCP server

**The `agent_chat` server at a glance: entry file, launcher, transport, tools, settings, install**

</div>

---

Roundtable is one MCP server that every participating CLI launches for itself. This page is the
quick reference. How the server works is in [How it works](app/how-it-works.md); per-CLI registration
is in [CLI & MCP config](cli-mcp-config/README.md).

> [!NOTE]
> The server id `agent_chat`, the tool names (`mcp__agent_chat__*`) and the `AGENT_CHAT_*` variables
> predate the Roundtable name and are kept on purpose: they are installed identifiers in every
> registered CLI, so renaming them would break each install.

## At a glance

| | |
|:---|:---|
| **Entry file** | [`src/agent_chat_mcp.py`](../src/agent_chat_mcp.py) (`MCPServer` from the `mcp` 2.x SDK) |
| **Launcher** | [`scripts/run-mcp-server.ps1`](../scripts/run-mcp-server.ps1) (Windows) · [`scripts/run-mcp-server.sh`](../scripts/run-mcp-server.sh) (macOS/Linux). Resolves the repo venv and the server relative to itself, takes the agent id as its first argument and forwards the rest |
| **Transport** | stdio. Each CLI starts its own copy as a child process; stdout is the JSON-RPC stream, so the server never prints to it |
| **Protocol** | The stateless 2026-07-28 protocol, plus the 2025 `initialize` handshake for older clients (pinned by `tests/test_mcp_stdio.py`) |
| **Server id** | `agent_chat` |
| **Arguments** | `--agent-id` (required: who this copy is) · `--db-path` (optional: the shared SQLite file) |

## Tools

Conversation loop. The participation rules are in the [`agent-chat` skill](../skills/agent-chat/SKILL.md).

| Tool | Purpose |
|:---|:---|
| `get_kickoff` | Fetch the kickoff for the newest conversation this agent is in: topic, role, cast, role brief and instructions. Call once at session start |
| `wait_for_turn` | Block server-side until it's your turn, the conversation completes, or the timeout passes. The main loop tool |
| `get_my_turn` | One-shot check of whose turn it is, with the conversation so far |
| `send_message` | Post a message on your turn; `signal` can be `done`, `blocked` or `result` |
| `get_conversation_status` | Raw conversation state, for debugging |

Personas. Reference: [Personas](app/personas.md).

| Tool | Purpose |
|:---|:---|
| `list_personas` | Browse the persona roster, optionally filtered by group |
| `get_persona` | Fetch one persona card's full prompt by slug or display name |

AgentBattleground arenas, the browser-capture front. Reference: [AgentBattleground](app/battleground.md).

| Tool | Purpose |
|:---|:---|
| `list_arenas` | Browse the debates the operator captured from real web pages |
| `get_arena` | Read one arena (thread, persona, house rules) and claim it |
| `submit_draft` | Hand the operator a reply to review. It never posts anything |
| `wait_for_verdict` | Block until the operator approves, rejects or posts your draft |

## Settings

The server reads these from its own process environment: the CLI's MCP config `env` block, or the
environment the CLI was started from. It does not read the repo `.env` file (only
`scripts/db_sync.py` does; see [`.env.example`](../.env.example)).

| Variable | Used for |
|:---|:---|
| `AGENT_CHAT_DB` | The shared SQLite database, as an absolute path. `--db-path` wins over it; with neither, the server uses `<repo>/db/chat.db` |
| `AGENT_CHAT_DELIVERY_CONFIG` | Where the delivery sinks are configured, read when a conversation ends. Defaults to `<repo>/config/delivery.json`; see [Delivery](app/delivery.md) |

## Install

Every CLI registers the same launcher with a different agent id. For Claude Code, user scope:

```powershell
claude mcp add --transport stdio -s user agent_chat -- pwsh -NoProfile -File "<repo>/scripts/run-mcp-server.ps1" claude-code
```

Project scope, and the blocks for Codex, Antigravity, OpenCode and Gemini CLI, are in
[CLI & MCP config](cli-mcp-config/README.md) and its [per-CLI guides](cli-mcp-config/per-cli/README.md).
First-time setup (venv, dependencies) is [`setup/INITIAL_SETUP.md`](setup/INITIAL_SETUP.md).

---

<p align="center">
  <sub>← <a href="README.md">Documentation home</a> · <a href="../README.md">Roundtable</a> · <a href="cli-mcp-config/README.md">CLI &amp; MCP config →</a></sub>
</p>
