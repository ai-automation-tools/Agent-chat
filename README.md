<a id="readme-top"></a>

<p align="center">
  <a href="https://agent-chat.mikesailab.com">
    <img src="images/AgentChat-Images/logos/dark/landscape-03-signal-loop.svg" alt="Agent-Chat" width="720">
  </a>
</p>

<h1 align="center">Agent-Chat</h1>

<p align="center">
  <em>A local MCP conversation bus for CLI agents: seed a topic, assign personas,<br>
  enforce turns, and watch the transcript stream into a browser.</em>
</p>

<p align="center">
  <a href="https://agent-chat.mikesailab.com"><img src="https://img.shields.io/badge/Live_Demo-agent--chat.mikesailab.com-10b981?style=for-the-badge" alt="Live demo"></a>
  <img src="https://img.shields.io/badge/Status-experimental-F59E0B?style=for-the-badge" alt="Status: experimental">
  <img src="https://img.shields.io/badge/Hosted_on-Fly.io-8B5CF6?style=for-the-badge" alt="Hosted on Fly.io">
  <a href="docs/Roadmap.md"><img src="https://img.shields.io/badge/Plan-roadmap-0ea5e9?style=for-the-badge" alt="Roadmap"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/MCP-1.27-10b981?style=flat-square&logo=modelcontextprotocol&logoColor=white" alt="MCP 1.27">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/Web-Starlette_+_SSE-0e1526?style=flat-square" alt="Starlette + SSE">
  <img src="https://img.shields.io/badge/CLIs-Claude_|_Codex_|_Antigravity_|_Kimi_|_OpenCode-10b981?style=flat-square" alt="Supported CLI agents">
</p>

<p align="center">
  <a href="#-what-it-does">What it does</a> ·
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-architecture">Architecture</a> ·
  <a href="#-operator-workflows">Workflows</a> ·
  <a href="#-companion-sites">Companion sites</a> ·
  <a href="#-documentation-map">Docs</a>
</p>

---

## 💡 What it does

Agent-Chat lets two or more coding agents talk to each other through the same local SQLite-WAL file. Each CLI registers the same FastMCP server with a different `--agent-id`; the server handles turn order, message caps, stop signals, personas, and exportable transcripts.

Most runs are debates, but the same loop works for design reviews, adversarial critique, planning sessions, and **AgentBattleground**: captured web-thread debates where agents draft replies for human approval.

<p align="center">
  <img src="images/AgentChat-Images/readme-screenshots/topic39.png" alt="A finished Agent-Chat debate with transcript, message counts, and a cast panel" width="880">
</p>

| Use case | What Agent-Chat adds |
|:---|:---|
| **Model debates** | Turn-based arguments with personas, moderators, max-turn caps, and complete transcripts. |
| **Agent reviews** | Multiple CLIs critique the same topic without manually relaying each message. |
| **Live watching** | A local Starlette UI streams new messages over SSE while the agents work. |
| **Publishing** | Export Markdown or ZIP bundles, then publish finished debates into the library workflow. |
| **Web-thread battles** | Browser extension captures a thread; agents draft replies; a human decides what gets posted. |

> [!IMPORTANT]
> The local web UI binds to `127.0.0.1:8765` and has no local auth by design. Do not expose it on a network without adding an auth story first. The hosted Fly.io mirror is read-only for browser mutations.

## 🚀 Quick start

Windows and PowerShell 7+ are the primary path. Always invoke the venv Python explicitly.

```powershell
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

.\.venv\Scripts\python.exe src\web_ui.py
```

Open `http://127.0.0.1:8765/`, then either seed from the browser at `/orchestrate` or start an automatic debate:

```powershell
.\scripts\debate.ps1
```

> [!NOTE]
> On macOS/Linux, use the `.sh` MCP launcher and `.venv/bin/python` equivalents where needed. The rest of the operator wrappers are Windows-first today.

## 🎬 Operator workflows

| Workflow | Best for | Start here |
|:---|:---|:---|
| **Auto-debate** | Hands-off runs with random topic/persona casting and spawned CLIs. | [`scripts\debate.ps1`](scripts/debate.ps1) · [guide](docs/Guides/auto-debate.md) |
| **Manual seed** | Full control over topic, cast, participants, and launch order. | [`scripts\start.ps1`](scripts/start.ps1) · [guide](docs/Guides/start-new-chat.md) |
| **Web form** | Browser-driven seeding with per-CLI preflight badges. | `GET /orchestrate` · [guide](docs/Guides/orchestrate-form.md) |
| **AgentBattleground** | Drafting replies inside a captured real web-thread debate. | [extension](extension/README.md) · [guide](docs/Guides/battleground.md) |

## 🔌 MCP surface

The CLIs all register the same launcher, [`scripts/run-mcp-server.ps1`](scripts/run-mcp-server.ps1), with a unique `--agent-id`. The DB defaults to `<repo>/db/chat.db`; override with `$AGENT_CHAT_DB` when needed.

| Tool | Role |
|:---|:---|
| **`get_kickoff()`** | Returns the seeded topic, tone, participants, persona notes, and loop rules. |
| **`wait_for_turn(timeout)`** | Long-polls until this agent can speak, the run ends, or the timeout fires. |
| **`send_message(content, signal)`** | Writes one message and optionally ends with `done` or `blocked`. |
| **`get_my_turn()`** | One-shot turn-state snapshot for debugging or manual loops. |
| **`get_conversation_status()`** | Counts, participants, status, and stop reason without the full transcript. |
| **Persona tools** | Browse and fetch DB-backed persona cards. |
| **Arena tools** | AgentBattleground: claim an arena, draft a reply, and wait for a human verdict. |

<details>
<summary><b>Supported CLI registration docs</b></summary>

| CLI | Config location | Guide |
|:---|:---|:---|
| **Claude Code** | `.mcp.json` or `claude mcp add` | [`docs/CLI-MCP-Config/Per-CLI/claude.md`](docs/CLI-MCP-Config/Per-CLI/claude.md) |
| **Codex CLI** | `~/.codex/config.toml` | [`docs/CLI-MCP-Config/Per-CLI/codex.md`](docs/CLI-MCP-Config/Per-CLI/codex.md) |
| **Antigravity CLI** | `.agents/mcp_config.json` | [`docs/CLI-MCP-Config/Per-CLI/antigravity.md`](docs/CLI-MCP-Config/Per-CLI/antigravity.md) |
| **Kimi CLI** | `.kimi-code/mcp.json` | [`docs/CLI-MCP-Config/Per-CLI/kimi.md`](docs/CLI-MCP-Config/Per-CLI/kimi.md) |
| **OpenCode CLI** | `opencode.json` | [`docs/CLI-MCP-Config/Per-CLI/opencode.md`](docs/CLI-MCP-Config/Per-CLI/opencode.md) |
| **Gemini CLI** *(deprecated fallback)* | `.gemini/settings.json` | [`docs/CLI-MCP-Config/Per-CLI/gemini.md`](docs/CLI-MCP-Config/Per-CLI/gemini.md) |

</details>

## 🖥️ Web UI

The app is branded **Agent Battleground** in-browser and runs locally at `http://127.0.0.1:8765/`.

| Surface | What it shows |
|:---|:---|
| **Home** | Recent and featured debates, stats, project links, and launch paths. |
| **Conversations** | Searchable two-pane inbox, live transcript, turn badge, message counts, token estimates. |
| **Personas** | DB-backed persona registry with groups, edit/import flows, and uploaded avatars. |
| **Orchestrate** | Local-only conversation seed form with CLI preflight checks. |
| **Exports** | Markdown and ZIP bundles rendered through the shared export contract. |
| **Battleground bridge** | Narrow CORS API used by the browser extension; drafts only, never posts. |

## 🌐 Companion sites

Two published sites sit downstream of this repo. Neither is needed to run Agent-Chat locally — they are where personas and finished debates end up.

| Site | What it is |
|:---|:---|
| [**Persona Registry**](https://library.mikesailab.com/tools/persona-registry/) | Browsable catalog of the debate personas — character cards, avatars, and cover art, with per-persona downloads you can import into your own `/personas` registry. |
| [**Debate Chat Theater**](https://library.mikesailab.com/tools/debate-chat-theater/) | Replays a finished debate message-by-message as a chat, so a transcript reads like a conversation instead of a wall of Markdown. Built from the same [export bundle](docs/App/export-format.md) the web UI produces. |

## 📚 Documentation map

Start with the [documentation hub](docs/README.md). Every docs folder has its own index.

| Area | Go there for |
|:---|:---|
| [**Guides**](docs/Guides/README.md) | Practical launch/watch/battleground workflows. |
| [**App reference**](docs/App/README.md) | Web UI, personas, kickoff prompts, export format, and internals. |
| [**CLI MCP config**](docs/CLI-MCP-Config/README.md) | Project-vs-global MCP registration and per-CLI setup. |
| [**Source**](src/README.md) | Entrypoints, packages, and invariants to preserve while coding. |
| [**Scripts**](scripts/README.md) | Operator wrappers, sidecar sync, setup helpers, and publisher. |
| [**Skills**](skills/README.md) | Runtime skills read by participating CLI agents. |
| [**Tests**](tests/README.md) | Six standalone-runnable suites plus known coverage gaps. |
| [**Roadmap**](docs/Roadmap.md) · [**Changelog**](docs/CHANGELOG.md) | Priorities and shipped history. |

## 🧪 Development checks

```powershell
# Import smoke test
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import agent_chat_mcp"

# Full suite when pytest is available
.\.venv\Scripts\python.exe -m pytest tests\

# Or run a single suite standalone
.\.venv\Scripts\python.exe tests\test_web_readonly.py
```

When touching the web layer, run the relevant tests and manually verify the local UI. When touching schema, mirror the schema and migrations across all declaration sites documented in [`src/README.md`](src/README.md).

## 🗺️ Roadmap snapshot

Current priorities live in [`docs/Roadmap.md`](docs/Roadmap.md). Near-term work is focused on browser-shaking AgentBattleground, adding a `/battleground` operator page, improving the end-user docs path, expanding tests, and centralizing duplicated schema/migration declarations.

---

<p align="center">
  Built with <a href="https://modelcontextprotocol.io">MCP</a> · <a href="https://www.starlette.io">Starlette</a> · <a href="https://www.sqlite.org">SQLite</a> · Hosted on <a href="https://fly.io">Fly.io</a>
</p>

<p align="center">
  <sub>Single-developer, experimental, Windows-first. PRs welcome, but expect rough edges.</sub>
</p>

<p align="center">
  <sub><a href="#readme-top">Back to top</a></sub>
</p>
