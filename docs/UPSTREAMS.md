# Upstreams

Every external protocol, CLI, library, and platform Agent-Chat depends on, what the code
assumes about each, and where to check whether that assumption still holds. The biweekly
**Agent-Chat Upstream Check** routine (`upstream/auto-*` PRs) works from this file. Keep it
current by hand too: a new supported CLI is a new row.

**Last checked** is filled in by the routine, and only with a date it actually read the
source. `—` means never checked.

## Protocol and SDK

| Upstream | What the code assumes | Code | Check at | Last checked |
|:---|:---|:---|:---|:---|
| **Model Context Protocol spec** | stdio transport per CLI process; tools declared with JSON Schema; nothing written to stdout except JSON-RPC | `src/agent_chat_mcp.py` | modelcontextprotocol.io/specification (changelog per spec revision) | — |
| **`mcp` Python SDK (FastMCP)** | Pinned `mcp==1.28.1`; `@mcp.tool()` decorators; Pydantic v2 models | `src/agent_chat_mcp.py`, `requirements.txt` | github.com/modelcontextprotocol/python-sdk/releases | — |

## Supported CLIs

Each CLI's launch line lives in `$Clis` in `scripts/lib/spawn-agents.ps1`, its MCP config in
`agents/CLIs/<cli>_agent*/`, and its setup doc in `docs/CLI-MCP-Config/Per-CLI/`. A change to
any of the three must keep the other two, and `tests/test_availability.py` / `tests/test_seats.py`, in step.

| Upstream | What the code assumes | Doc | Check at | Last checked |
|:---|:---|:---|:---|:---|
| **Claude Code** (`claude`) | Project `.mcp.json` or user-scope `~/.claude.json` `mcpServers`; prompt as a positional arg; `--dangerously-skip-permissions` | `claude.md` | code.claude.com/docs and the Claude Code changelog | — |
| **Codex CLI** (`codex`) | `[mcp_servers.agent_chat]` in `~/.codex/config.toml` or a trusted repo's `.codex/config.toml`; `--yolo` | `codex.md` | github.com/openai/codex/releases | — |
| **Gemini CLI** (`gemini`) | `mcpServers` in its `settings.json` | `gemini.md` | github.com/google-gemini/gemini-cli/releases | — |
| **Antigravity** (`agy`) | Project `mcpServers` in `.agents/mcp_config.json`; `-i <prompt>`; `--dangerously-skip-permissions`; `agy mcp add` manages global scope only (as of v1.1.16) | `antigravity.md` | Antigravity's official docs and release notes | — |
| **OpenCode** (`opencode run`) | Auto-loads `opencode.json` from the launch dir; `--auto` skips permissions | `opencode.md` | opencode.ai/docs and its GitHub releases | — |

## Web UI, hosting, extension

| Upstream | What the code assumes | Where | Check at | Last checked |
|:---|:---|:---|:---|:---|
| **Starlette, sse-starlette, uvicorn, Pydantic** | Exact pins in `requirements.txt` (Starlette 1.x) | `src/web_ui.py`, `src/web/` | PyPI release pages. Flag breaking majors and security advisories only | — |
| **Python** | 3.10+ locally; `python:3.13-slim` in the Docker image | `Dockerfile`, `CLAUDE.md` | devguide.python.org/versions (EOL dates) | — |
| **Fly.io** | `fly.toml` keys (`[http_service]`, `auto_stop_machines = "stop"`, `[[vm]] size = "shared-cpu-1x"`, `[mounts]`); manual `fly deploy` | `fly.toml` | fly.io/docs/reference/configuration/ and community.fly.io "Fresh Produce" | — |
| **Chrome / Firefox extensions** | Manifest V3 in both `manifest.json` and `manifest.firefox.json` | `extension/` | developer.chrome.com/docs/extensions/whatsnew; extensionworkshop.com | — |
