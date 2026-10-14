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
| **Model Context Protocol spec** | stdio transport per CLI process; tools declared with JSON Schema; nothing written to stdout except JSON-RPC. Current revision is **2026-07-28** (stateless, no `initialize` handshake, `server/discover`); the server still speaks the 2025 handshake via `mcp` 1.x — see the Roadmap's `mcp` 2.x row | `src/agent_chat_mcp.py` | modelcontextprotocol.io/specification/versioning and the changelog per spec revision | 2026-10-13 |
| **`mcp` Python SDK (FastMCP)** | Pinned `mcp==1.30.0` (1.x, `FastMCP`; maintenance mode since 2.0.0 on 2026-07-28); `@mcp.tool()` decorators; Pydantic v2 models. Latest is 2.x (`MCPServer`) | `src/agent_chat_mcp.py`, `requirements.txt` | github.com/modelcontextprotocol/python-sdk/releases | 2026-10-13 |

## Supported CLIs

Each CLI's launch line lives in `$Clis` in `scripts/lib/spawn-agents.ps1`, its MCP config in
`agents/CLIs/<cli>_agent*/`, and its setup doc in `docs/CLI-MCP-Config/Per-CLI/`. A change to
any of the three must keep the other two, and `tests/test_availability.py` / `tests/test_seats.py`, in step.

| Upstream | What the code assumes | Doc | Check at | Last checked |
|:---|:---|:---|:---|:---|
| **Claude Code** (`claude`) | Project `.mcp.json` or user-scope `~/.claude.json` `mcpServers`; prompt as a positional arg; `--dangerously-skip-permissions` | `claude.md` | code.claude.com/docs and the Claude Code changelog (github.com/anthropics/claude-code, `CHANGELOG.md`) | 2026-10-13 |
| **Codex CLI** (`codex`) | `[mcp_servers.agent_chat]` in `~/.codex/config.toml` or a trusted repo's `.codex/config.toml`; `--yolo` | `codex.md` | github.com/openai/codex/releases; MCP docs now at learn.chatgpt.com/docs/extend/mcp?surface=cli | 2026-10-13 |
| **Gemini CLI** (`gemini`) | `mcpServers` in its `settings.json` | `gemini.md` | github.com/google-gemini/gemini-cli/releases; geminicli.com/docs/tools/mcp-server/ (says Antigravity CLI replaced Gemini CLI for unpaid and Google One users on 2026-06-18) | 2026-10-13 |
| **Antigravity** (`agy`) | Project `mcpServers` in `.agents/mcp_config.json`; `-i <prompt>`; `--dangerously-skip-permissions`; `agy mcp add` manages global scope only (as of v1.1.16) | `antigravity.md` | antigravity.google/docs/getting-started?tab=cli (the `/docs/cli` page redirects there) | 2026-10-13 |
| **OpenCode** (`opencode run`) | Auto-loads `opencode.json` from the launch dir; `--auto` skips permissions | `opencode.md` | opencode.ai/docs/mcp-servers/, opencode.ai/docs/cli/ and github.com/anomalyco/opencode/releases (`sst/opencode` redirects there) | 2026-10-13 |

## Web UI, hosting, extension

| Upstream | What the code assumes | Where | Check at | Last checked |
|:---|:---|:---|:---|:---|
| **Starlette, sse-starlette, uvicorn, Pydantic** | Exact pins in `requirements.txt` (Starlette 1.x) | `src/web_ui.py`, `src/web/` | PyPI release pages. Flag breaking majors and security advisories only | 2026-10-13 |
| **Python** | 3.10+ locally (3.10 hit EOL 2026-10-01 — floor queued to 3.11); `python:3.14-slim` in the Docker image; 3.12 in CI | `Dockerfile`, `CLAUDE.md`, `.github/workflows/ci.yml` | devguide.python.org/versions (EOL dates) | 2026-10-13 |
| **Fly.io** | `fly.toml` keys (`[http_service]`, `auto_stop_machines = "stop"`, `[[vm]] size = "shared-cpu-1x"`, `[mounts]`); manual `fly deploy` | `fly.toml` | docs.fly.io/reference/configuration (fly.io/docs/... 301s there) and community.fly.io "Fresh Produce" | 2026-10-13 |
| **Chrome / Firefox extensions** | Manifest V3 in both `manifest.json` and `manifest.firefox.json` | `extension/` | developer.chrome.com/docs/extensions/whatsnew; extensionworkshop.com | 2026-10-13 |
