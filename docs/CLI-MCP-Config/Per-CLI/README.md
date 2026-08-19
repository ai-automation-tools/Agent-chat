<h1 align="center">🔧 Per-CLI MCP Guides</h1>

<p align="center">
  <em>One deep-dive per CLI — the exact config file, the registration block,<br>
  and the quirks that bite. Both project-level and global-level scopes.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/CLIs-6-10b981?style=for-the-badge&labelColor=09090b" alt="6 CLIs">
  <img src="https://img.shields.io/badge/Scopes-project_%7C_global-0284c7?style=for-the-badge&labelColor=09090b" alt="project or global">
  <img src="https://img.shields.io/badge/Launcher-shared-8b5cf6?style=for-the-badge&labelColor=09090b" alt="one shared launcher">
</p>

---

> [!IMPORTANT]
> Start at the [**consolidated reference**](../README.md) — it has the
> CLI × scope jump table and the rules that apply to every CLI. These files are
> the per-tool detail behind it.

Every CLI registers the **same** launcher
([`scripts/run-mcp-server.ps1`](../../../scripts/run-mcp-server.ps1) or
[`.sh`](../../../scripts/run-mcp-server.sh)) under a different `--agent-id` —
that id is the only value that changes between registrations, and it must match
the canonical spelling or turn rotation and message attribution break.

## 📋 The guides

| CLI | Config mechanism | `--agent-id` | Guide |
|:---|:---|:---|:---|
| [**Claude Code**](claude.md) | `.mcp.json` · `claude mcp add` | `claude-code` | [claude.md](claude.md) |
| [**Codex CLI**](codex.md) | `~/.codex/config.toml` · `codex mcp add` | `codex` | [codex.md](codex.md) |
| [**Antigravity CLI**](antigravity.md) | `.agents/mcp_config.json` | `antigravity` | [antigravity.md](antigravity.md) |
| [**OpenCode CLI**](opencode.md) | `opencode.json` — **different shape** | `opencode` | [opencode.md](opencode.md) |
| [**Gemini CLI**](gemini.md) *(deprecated)* | `.gemini/settings.json` · `gemini mcp add` | `gemini` | [gemini.md](gemini.md) |

> [!WARNING]
> **OpenCode is the odd one out.** Its config sits under a top-level `mcp` key
> (not `mcpServers`), with `"type": "local"` and a single `command` **array**
> combining executable and args. The other five share the `mcpServers` +
> `command`/`args` shape.

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../README.md`](../README.md) | The canonical consolidated reference — read this first. |
| [`../../Setup/INITIAL_SETUP.md`](../../Setup/INITIAL_SETUP.md) | Bootstrap the repo before registering anything. |
| [`../../../agents/README.md`](../../../agents/README.md) | The per-CLI tester workspaces that carry working copies of these configs. |
| [`../../Guides/README.md`](../../Guides/README.md) | Once registered — how to actually launch a conversation. |

---

<p align="center">
  <sub>← <a href="../README.md">CLI &amp; MCP config</a> · <a href="../../README.md">Documentation home</a> · <a href="../../../README.md">Agent-Chat</a></sub>
</p>
