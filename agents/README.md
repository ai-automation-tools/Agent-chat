<h1 align="center">🤖 Agents</h1>

<p align="center">
  <em>Per-CLI agent workspaces and the persona seed cards.<br>
  Working configs and source material — <b>not</b> the live persona registry.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/CLI_workspaces-6-10b981?style=for-the-badge&labelColor=09090b" alt="6 CLI workspaces">
  <img src="https://img.shields.io/badge/Personas-live_in_the_DB-f59e0b?style=for-the-badge&labelColor=09090b" alt="personas live in the DB">
</p>

---

> [!IMPORTANT]
> **The card files here are a seed source, not the source of truth.** Personas
> live in the `personas` table in `db/chat.db` (and sync to the Fly mirror).
> These `*.md` folders are a one-time import source for
> `orchestrator/personas.py import`. Editing a card on disk does **not** change
> a persona the app uses — edit it at `/personas` instead. Group names are
> free-form and DB-derived, so this tree's folder names are **not** the live
> group list.

## 📁 What's here

| Folder | What it holds |
|:---|:---|
| [**CLIs/**](CLIs/) | One workspace per supported CLI — a role doc (`claude.md` / `AGENTS.md` / `GEMINI.md`) plus that CLI's own MCP config. Launch a CLI **from inside its folder** and it picks up the `agent_chat` server automatically. |
| [**Debate-Agents/**](Debate-Agents/) | Persona seed cards, organised by where they came from: `Debate-Agents-Random/` (the original hand-written roster + `Debate-Hosts/` moderators) and `AI-Library-Imports/` (cards imported from the AI-Automation-Library, each with a cover image). |
| [**Debate-Agent-Templates/**](Debate-Agent-Templates/README.md) | The authoring templates — the persona card schema and the generator prompt used to write a new one. |

## 🖥️ The CLI workspaces

Each folder carries a working registration for one agent id. This is why a CLI
started at the repo root has no `agent_chat` tools but the same CLI started here
does.

| Workspace | Agent id | Role doc | Config file | Setup guide |
|:---|:---|:---|:---|:---|
| [**claude-code_agent1/**](CLIs/claude-code_agent1/) | `claude-code` | [claude.md](CLIs/claude-code_agent1/claude.md) | `.mcp.json` | [→](../docs/CLI-MCP-Config/Per-CLI/claude.md) |
| [**codex_agent1/**](CLIs/codex_agent1/) | `codex` | [AGENTS.md](CLIs/codex_agent1/AGENTS.md) | global `~/.codex/config.toml` | [→](../docs/CLI-MCP-Config/Per-CLI/codex.md) |
| [**antigravity_agent1/**](CLIs/antigravity_agent1/) | `antigravity` | [AGENTS.md](CLIs/antigravity_agent1/AGENTS.md) | `.agents/mcp_config.json` | [→](../docs/CLI-MCP-Config/Per-CLI/antigravity.md) |
| [**opencode_agent1/**](CLIs/opencode_agent1/) | `opencode` | [AGENTS.md](CLIs/opencode_agent1/AGENTS.md) | `opencode.json` | [→](../docs/CLI-MCP-Config/Per-CLI/opencode.md) |
| [**gemini_agent1/**](CLIs/gemini_agent1/) | `gemini` *(deprecated)* | [GEMINI.md](CLIs/gemini_agent1/GEMINI.md) | `.gemini/settings.json` | [→](../docs/CLI-MCP-Config/Per-CLI/gemini.md) |

Each **role doc** is what that CLI reads on startup from its own folder. All
five say the same thing with per-CLI config details swapped in: the seat is a
**full-stack developer** on this repo that can *also* join an agent-chat
conversation — carrying its agent id, how the three conversation types
(`debate` / `podcast` / `collaborate`) differ, the participation loop, and the
`agent_chat` tool table.

```powershell
# Launch an agent that can actually see the agent_chat tools
cd agents\CLIs\claude-code_agent1
claude
```

## 🎭 Working with personas

| You want to… | Do this |
|:---|:---|
| See / edit / add a persona | The [`/personas`](http://127.0.0.1:8765/personas) page, or `src/orchestrator/personas.py` |
| Know which groups exist | `personas.discover_groups()` — never this folder's names |
| Import these cards into a fresh DB | `personas.py import` (one-time seed) |
| Write a new card | [`Debate-Agent-Templates/`](Debate-Agent-Templates/README.md) |

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../docs/App/personas.md`](../docs/App/personas.md) | The registry: groups, the reserved `AI-Models` group, and the MCP tools. |
| [`../docs/CLI-MCP-Config/README.md`](../docs/CLI-MCP-Config/README.md) | Registering the server per CLI — project vs global. |
| [`../skills/README.md`](../skills/README.md) | What these CLIs read at runtime to participate in a conversation. |

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../docs/App/personas.md">Persona registry</a></sub>
</p>
