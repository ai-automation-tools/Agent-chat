<div align="center">

# 🔌 Register the `agent_chat` MCP server

**Pick your CLI, then jump straight to the project-level or global-level steps.**

</div>

Every CLI registers the **same** launcher — [`scripts/run-mcp-server.ps1`](../../scripts/run-mcp-server.ps1) (Windows) or [`run-mcp-server.sh`](../../scripts/run-mcp-server.sh) (POSIX) — under a different `--agent-id`. The launcher resolves the venv interpreter and server script relative to itself, so the launcher path is the **only** hardcoded string per config, and the agent-id is the **only** value that changes between CLIs.

---

## 🎯 Jump to your CLI × scope

| CLI | Config mechanism | Add at project level | Add at global level | Full guide |
|:--|:--|:--|:--|:--|
| **Claude Code** | `.mcp.json` · `claude mcp add` | [Project →](Per-CLI/claude.md#project-level-registration) | [Global →](Per-CLI/claude.md#global-level-registration) | [claude.md](Per-CLI/claude.md) |
| **Codex CLI** | `~/.codex/config.toml` · `codex mcp add` | [Project →](Per-CLI/codex.md#project-level-registration) | [Global →](Per-CLI/codex.md#global-level-registration) | [codex.md](Per-CLI/codex.md) |
| **Antigravity CLI** | `.agents/mcp_config.json` | [Project →](Per-CLI/antigravity.md#project-level-registration) | [Global →](Per-CLI/antigravity.md#global-level-registration) | [antigravity.md](Per-CLI/antigravity.md) |
| **OpenCode CLI** | `opencode.json` · `~/.config/opencode/opencode.json` | [Project →](Per-CLI/opencode.md#project-level-registration) | [Global →](Per-CLI/opencode.md#global-level-registration) | [opencode.md](Per-CLI/opencode.md) |
| **Gemini CLI** *(deprecated)* | `.gemini/settings.json` · `gemini mcp add` | [Project →](Per-CLI/gemini.md#project-level-registration) | [Global →](Per-CLI/gemini.md#global-level-registration) | [gemini.md](Per-CLI/gemini.md) |

> [!TIP]
> **Project vs global?** **Project** scopes the server to one launch folder (what this repo's per-CLI agent workspaces use) — other folders stay clean and don't pay the startup cost. **Global** registers it once for *every* session on the machine. Pick one; each guide has both sections.

📁 Browsing rather than jumping? [**`Per-CLI/`**](Per-CLI/README.md) indexes all five deep-dive guides.

---

## 📌 Rules that apply to every CLI

- **`--agent-id` must match** the canonical value (`claude-code`, `codex`, `antigravity`, `opencode`, `gemini`) — turn rotation, message attribution, and the web-UI labels key off it. Never rename it.
- **A second seat on the same tool gets a numbered id.** To put two personalities on one CLI, give it another config folder: `agents/CLIs/<cli>_agent2/` with `--agent-id <cli>-2`. Don't hand-roll it — `scripts/setup/add_agent_seat.py --cli <cli> --seat 2` clones the seat-1 config and rewrites the id for you, in whichever shape that CLI uses, and `/orchestrate` runs the same code when you seat two chairs on one tool. **Two tools keep no seat-1 file to clone**, and both are handled: Codex's seat 1 *is* `~/.codex/config.toml`, and Claude Code registered with `--scope user` has only an entry in `~/.claude.json` — seat 2's `.mcp.json` is synthesized from that entry (and nothing else in that file travels with it). Seat ids run to `-5` (the participant cap). **Codex can't do project-scoped config**, so its extra seats relocate `CODEX_HOME` and need their own `codex login` — see [codex.md](Per-CLI/codex.md).
- **OpenCode uses a different config shape** — under a top-level `mcp` key (not `mcpServers`), with `"type": "local"` and a single `command` **array** (executable + args combined). See [opencode.md](Per-CLI/opencode.md). The others share the `mcpServers` + `command`/`args` shape.
- **`pwsh` (PowerShell 7+) on PATH** is required for the `.ps1` launcher (`winget install Microsoft.PowerShell`). On macOS/Linux, install `pwsh` or use the `.sh` launcher form — `"command": "/abs/path/to/run-mcp-server.sh"`, `"args": ["<agent-id>"]` (each guide has a collapsible variant).
- **`--db-path` is optional** — the server defaults to `<repo>/db/chat.db`; set `$env:AGENT_CHAT_DB` to override, or append `--db-path <path>` after the agent-id in `args`.
- **Restart after changes** — none of these CLIs reliably hot-reload a newly added server.
- **Forward slashes** work in Windows paths; if you use backslashes in JSON, double them (`"D:\\AI_Agents\\..."`).

---

## 📚 Vendor documentation

These mechanisms are external-vendor behavior and can change. When something stops matching a guide, check the source:

| CLI | Official MCP docs |
|:--|:--|
| **Claude Code** | <https://code.claude.com/docs/en/mcp> |
| **Codex CLI** | <https://developers.openai.com/codex/mcp> |
| **Antigravity CLI** | <https://codelabs.developers.google.com/developer-knowledge-mcp-antigravity> |
| **OpenCode CLI** | <https://opencode.ai/docs/mcp-servers/> |
| **Gemini CLI** | <https://geminicli.com/docs/tools/mcp-server/> |
| **MCP spec** | <https://modelcontextprotocol.io> |

---

<p align="center">
  <sub>← <a href="../README.md">Documentation home</a> · <a href="../../README.md">Agent-Chat</a> · <a href="Per-CLI/README.md">Per-CLI guides</a> · Next: <a href="../Guides/README.md">Guides →</a></sub>
</p>
