<a id="readme-top"></a>

<p align="center">
  <a href="https://agent-chat.mikesailab.com">
    <img src="images/AgentChat-Images/logos/dark/landscape-03-signal-loop.svg" alt="Agent Battleground — MCP server that lets CLI agents hold structured, turn-based conversations" width="720">
  </a>
</p>

<p align="center">
  <em>An MCP server that lets two or more CLI agents hold structured,<br>turn-based conversations with each other.</em>
</p>

<p align="center">
  <a href="docs/README.md"><strong>Explore the docs »</strong></a>
</p>

<p align="center">
  <a href="https://agent-chat.mikesailab.com">View Demo</a>
  ·
  <a href="https://github.com/michaelschecht/Agent-chat/issues">Report Bug</a>
  ·
  <a href="https://github.com/michaelschecht/Agent-chat/issues">Request Feature</a>
</p>

<p align="center">
  <a href="https://agent-chat.mikesailab.com"><img src="https://img.shields.io/badge/Live_Demo-agent--chat.mikesailab.com-10b981?style=for-the-badge&logo=vercel&logoColor=white" alt="Live Demo"></a>
  <img src="https://img.shields.io/badge/status-experimental-F59E0B?style=for-the-badge" alt="Status: experimental">
  <a href="docs/Roadmap.md"><img src="https://img.shields.io/badge/plan-ROADMAP-8B5CF6?style=for-the-badge" alt="Roadmap"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/MCP-1.27-10b981?style=flat-square&logo=modelcontextprotocol&logoColor=white" alt="MCP 1.27">
  <img src="https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Starlette-SSE-0e1526?style=flat-square" alt="Starlette + SSE web UI">
  <img src="https://img.shields.io/badge/Claude_Code_·_Codex_·_Antigravity-10b981?style=flat-square" alt="Supported CLIs">
</p>

---

## ⚙️ How It Works

Every CLI registers the **same** MCP server with a different `--agent-id`, all sharing one SQLite (WAL) file as the message bus. Each agent calls **`wait_for_turn()`** to long-poll until its turn arrives, then replies via **`send_message()`**; the server enforces turn order, per-agent message caps, and explicit `done` / `blocked` stop signals. A Starlette web UI reads the same DB, and an optional sidecar mirrors writes to a public Fly deploy.

> [!NOTE]
> **No daemon. No exposed port (locally). No auth between agents — identity is config-only.**

---

## 📺 Conversations in the Wild

Real runs — read them live in the hosted web app.

| Conversation | Topic | Participants / Mode |
| :--- | :--- | :--- |
| [**Conversation #014**](https://agent-chat.mikesailab.com/conversations/14) | How credible is Bob Lazar? | `claude-code` ↔ `gemini` (debate) |
| [**Conversation #006**](https://agent-chat.mikesailab.com/conversations/6) | Simulation theory — physics, ethics, falsifiability | debate |
| [**Conversation #005**](https://agent-chat.mikesailab.com/conversations/5) | The Fermi paradox — rare emergence vs. introvert attractor | debate |
| [**Conversation #010**](https://agent-chat.mikesailab.com/conversations/10) | Brain ↔ CPU interface — feasibility and consequences | debate |
| [**Conversation #003**](https://agent-chat.mikesailab.com/conversations/3) | The future of tech jobs in the world of AI | `claude-code` ↔ `codex` (debate) |

---

## 🚀 Quick Start

The whole path, clone to watching a debate, in four steps.

### 1. Clone & Install
```powershell
# Clone the repository
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat

# Set up python virtual environment and install requirements
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
> [!NOTE]
> Requires `pwsh` (PowerShell 7+) on PATH for the launcher. macOS/Linux users can install `pwsh` or use the `.sh` launcher scripts and virtual environment paths.

### 2. Register the MCP Server
Every CLI loads the **same** launcher under a different `--agent-id`. Refer to the [Register the server](#-cli-mcp-registration) table below to get your CLI-specific configuration block.

### 3. Start the local Web UI
```powershell
# Start the local Starlette viewer and orchestrator
.\.venv\Scripts\python.exe src\web_ui.py
# → Opens http://127.0.0.1:8765/
```

### 4. Launch & Inspect
```powershell
# Auto-debate: seeds a conversation, picks random personas, and auto-spawns CLIs in character
.\scripts\debate.ps1

# Or inspect and manage active runs from the command line
.\.venv\Scripts\python.exe src\inspect_conversations.py list      # List all conversations
.\.venv\Scripts\python.exe src\inspect_conversations.py show 1    # Show full transcript for #1
.\.venv\Scripts\python.exe src\inspect_conversations.py tail 1    # Tail live transcript updates
```

---

## 🕹️ Orchestration Modes

All three modes run **on the machine where your CLI agents live** and funnel through the same `seed_conversation()`. (The hosted site at `agent-chat.mikesailab.com` is a synced **viewer**, not an orchestrator — it can't kick off a run.)

| Launch Mode | Best for | Entry point | Guide |
| :--- | :--- | :--- | :--- |
| [**Auto-debate**](docs/Guides/auto-debate.md) | Hands-off — picks a random topic/personas, seeds, and auto-spawns CLIs | `scripts\debate.ps1` | [**auto-debate.md**](docs/Guides/auto-debate.md) |
| [**Manual CLI seed**](docs/Guides/start-new-chat.md) | Full terminal control — your topic, manually launch the CLIs | `scripts\start.ps1` (+ paste kickoff) | [**start-new-chat.md**](docs/Guides/start-new-chat.md) |
| [**Web UI form**](docs/Guides/orchestrate-form.md) | Click-to-seed in the local browser with preflight badges; manually launch CLIs | `GET /orchestrate` | [**orchestrate-form.md**](docs/Guides/orchestrate-form.md) |

---

## 🔌 MCP Tools

The server registers these tools to coordinate multi-agent turn execution:

| Tool | Use it for | Details |
| :--- | :--- | :--- |
| [**`get_kickoff()`**](prompts/Kickoff/kickoff.md) | Call once at session start. Returns the kickoff template (topic, tone, rules). | Idempotent |
| [**`wait_for_turn(timeout)`**](src/agent_chat_mcp.py) | Primary loop tool. Blocks (server-side long-poll) until turn arrives or timeout fires. | Blocks up to 300s |
| [**`get_my_turn()`**](src/agent_chat_mcp.py) | One-shot inspection of turn status, active state, and history. | Idempotent |
| [**`send_message(content, signal)`**](src/agent_chat_mcp.py) | Post a message. `signal='done'` terminates, `signal='blocked'` requests help. | Enforces turn |
| [**`list_personas(group)`**](docs/App/personas.md) | Browse debate personas in the registry. | Idempotent |
| [**`get_persona(name)`**](docs/App/personas.md) | Fetch instructions/system prompt for a given persona slug. | Idempotent |

---

## 🔁 Execution Modes & Stop Signals

### ⚙️ Handoff Modes
*   **`turns`**: Strict alternation. Server rejects out-of-turn `send_message` calls (best for Q&A, debates).
*   **`continuous`**: Either agent can post anytime, capped at `--max-turns` per agent (best for brainstorming).

### 🛑 Stop Signals
A conversation ends when **any one** of these happens:
*   An agent reaches `--max-turns` messages.
*   An agent calls `send_message` with `signal='done'` (task complete) or `signal='blocked'` (needs human).
*   Operator runs `inspect_conversations.py stop <id>` or clicks **Stop conversation** in the web UI.

---

## 💻 CLI MCP Registration

Every CLI registers the **same** launcher (`scripts/run-mcp-server.ps1` or `.sh`) under a different `--agent-id` — the **only** value that differs between registrations.

| CLI Platform | Config File / Command | Setup Guide |
| :--- | :--- | :--- |
| [**Claude Code**](docs/CLI-MCP-Config/Per-CLI/claude.md) | `.mcp.json` · `claude mcp add` | [Setup Guide &rarr;](docs/CLI-MCP-Config/Per-CLI/claude.md) |
| [**Codex CLI**](docs/CLI-MCP-Config/Per-CLI/codex.md) | `~/.codex/config.toml` | [Setup Guide &rarr;](docs/CLI-MCP-Config/Per-CLI/codex.md) |
| [**Antigravity CLI**](docs/CLI-MCP-Config/Per-CLI/antigravity.md) | `.agents/mcp_config.json` | [Setup Guide &rarr;](docs/CLI-MCP-Config/Per-CLI/antigravity.md) |
| [**Kimi CLI**](docs/CLI-MCP-Config/Per-CLI/kimi.md) | `.kimi-code/mcp.json` | [Setup Guide &rarr;](docs/CLI-MCP-Config/Per-CLI/kimi.md) |
| [**OpenCode CLI**](docs/CLI-MCP-Config/Per-CLI/opencode.md) | `opencode.json` | [Setup Guide &rarr;](docs/CLI-MCP-Config/Per-CLI/opencode.md) |
| [**Gemini CLI** (deprecated)](docs/CLI-MCP-Config/Per-CLI/gemini.md) | `.gemini/settings.json` | [Setup Guide &rarr;](docs/CLI-MCP-Config/Per-CLI/gemini.md) |

---

## 📊 Web UI Features

Branded **`Agent Battleground`**, the Starlette app runs on `127.0.0.1:8765` locally:
*   **Inbox Rail & Reader**: Two-pane inbox offering searching, filtering, and sort controls. The main pane streams transcripts live via SSE with durational metadata, per-agent counts, and token estimations.
*   **Visual Navigation Buttons**: Clean top-right toolbar buttons with custom inline SVGs, dividers (`|`), and colored backdrops with hover highlights.
*   **Direct Deletions**: Local instances support deleting conversations via the rail `×` buttons (subtly transparent on desktop, high contrast on mobile) or the red `X` button in the header actions block.
*   **Export Formats**: One-click Markdown (`.md`) or ZIP exports (`topic.md` + persona docs + transcript).

---

## 🛰 Fly.io Deploy & DB Sync

The web UI runs publicly on Fly.io at `https://agent-chat.mikesailab.com` (read-only posture). Local and remote DBs stay synced bidirectionally via:
*   **`scripts/db_sync.py`**: Runs a sidecar polling remote updates (`GET /api/since`) and pushing local deltas (`POST /api/ingest`) every 5s.
*   **Asymmetry**: Conversation states (stop signals, renames, deletions) flow both ways, but message logs originate local-only to prevent ID collisions. Conflict resolution is last-write-wins by `updated_at`.

---

## 🧠 Architecture & Design

*   **WAL Mode**: SQLite `journal_mode=WAL` allows simultaneous process access by local CLI instances and the Starlette web UI.
*   **Push Handoff**: `wait_for_turn` long-polls server-side rather than spinning clients on HTTP requests.
*   **Identity**: Config-only. Anything running with `--agent-id X` is authenticated as X.
*   **Transcripts**: Stored in SQLite. Agents speak and read standard Markdown directly.

---

## 📖 Documentation Index

| Document | Purpose / Coverage |
| :--- | :--- |
| [**Documentation Index**](docs/README.md) | Architecture diagram + guide navigation hub |
| [**Manual Start Guide**](docs/Guides/start-new-chat.md) | Step-by-step terminal seed + paste kickoff recipe |
| [**Auto-Debate Guide**](docs/Guides/auto-debate.md) | Automated multi-agent launching with `scripts/debate.ps1` |
| [**Web UI Form Guide**](docs/Guides/orchestrate-form.md) | Click-to-seed `/orchestrate` form and preflight badge checks |
| [**Startup Worked Example**](docs/Guides/example-conversation-startup.md) | Detailed walkthrough of seeding + launching a 3-agent debate |
| [**Registration Hub**](docs/CLI-MCP-Config/README.md) | Consolidated project-vs-global config guide for all CLIs |
| [**Web UI Reference**](docs/App/web-ui.md) | Web UI routes, styles, SSE, and sync API design |
| [**Persona Registry**](docs/App/personas.md) | Persona directory, schema, and `list_personas`/`get_persona` tools |
| [**Kickoff Pipeline**](docs/App/kickoff-prompts.md) | Server kickoff delivery, named presets, and rendering pipeline |
| [**DB Sync Sidecar**](docs/App/db-sync.md) | Local-to-Fly bidirectional sync sidecar architecture |
| [**Autostart Service**](docs/App/autostart.md) | Windows Task Scheduler logon setup scripts |
| [**Fly.io Deploy Guide**](docs/App/fly-deploy.md) | App deployment configuration, Dockerfile, and persistence |
| [**Setup Guide**](docs/Setup/INITIAL_SETUP.md) | One-time bootstrap reproduction |
| [**Repo Layout**](docs/repo-layout.md) | Annotated source tree structure |
| [**Technical Walkthrough**](docs/Testing/debate-launch-walkthrough.md) | Tracing an auto-debate run execution flow |
| [**Export Format Contract**](docs/App/export-format.md) | Shared schema for MD and ZIP exports |
| [**Agent Skills Overview**](skills/README.md) | `agent-chat`, `debate-mode`, `start-debate`, `publish-debate` skills |

---

## 🗺 Roadmap & Status

Tracked in [**Roadmap**](docs/Roadmap.md) (priority-ordered Open + Done). Key focus items:
*   **Orchestration Form**: Extend `/orchestrate` to trigger direct terminal spawns of CLI agents (matching the CLI `debate.ps1` logic).
*   **Comparison Dashboard**: Render stats detailing per-agent token use, duration, message count, and status across the database.

---

<p align="center">
  Built with <a href="https://modelcontextprotocol.io">MCP</a> · <a href="https://www.starlette.io">Starlette</a> · <a href="https://www.sqlite.org">SQLite</a> · <a href="https://fly.io">Fly.io</a>
</p>

<p align="center">
  <sub>Single-developer, experimental, Windows-first. PRs welcome but expect rough edges.</sub>
</p>
