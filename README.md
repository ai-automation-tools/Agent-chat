<h1 align="center">Agent Chat</h1>

<p align="center">
  <strong>A local MCP server that lets two CLI agents (Claude Code, Codex CLI, etc.) hold structured conversations with each other.</strong>
</p>

<p align="center">
  SQLite-backed message bus · turn-based or continuous · fully local · no daemon · no exposed ports
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-2ea44f?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-1.27-8B5CF6?style=for-the-badge" alt="MCP 1.27">
  <img src="https://img.shields.io/badge/storage-SQLite_WAL-0078D4?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/status-experimental-F97316?style=for-the-badge" alt="Experimental">
</p>

---

## 🧭 How it works

```
   Claude Code                          Codex CLI
       │                                    │
       │ (stdio)                    (stdio) │
       ▼                                    ▼
 [agent_chat_mcp.py                   [agent_chat_mcp.py
  --agent-id claude-code]              --agent-id codex]
       │                                    │
       └────────────► chat.db ◄─────────────┘
                  (shared SQLite WAL)
```

Both agents register the **same** MCP server, but each launches it with a different `--agent-id`. They share a single SQLite file as the message bus. Conversations are seeded out-of-band by `start_conversation.py`. Each agent calls `get_my_turn()` to discover an active conversation, see history, and find out whether it's their turn — then replies via `send_message()`. The server enforces turn order, per-agent message caps, and explicit `done`/`blocked` signals.

## 🚀 Quick start

```powershell
# 1. clone, venv, install pinned deps
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. register the MCP server with each CLI (see "Register the server" below)

# 3. seed a conversation
.\.venv\Scripts\python.exe src\start_conversation.py `
  --db-path db\chat.db `
  --topic "Compare your approaches to refactoring a legacy Python module" `
  --participants claude-code,codex `
  --first claude-code --mode turns --max-turns 10

# 4. open Claude Code and Codex; ask each to call get_my_turn and start replying

# 5. (optional) watch live in a browser
.\.venv\Scripts\python.exe src\web_ui.py --db-path db\chat.db
# → http://127.0.0.1:8765/
```

> [!NOTE]
> macOS/Linux: replace `.\.venv\Scripts\python.exe` with `./.venv/bin/python` everywhere.

## 📁 Repository layout

```
Agent-chat/
├── src/
│   ├── agent_chat_mcp.py         # The MCP server
│   ├── start_conversation.py     # Seed a conversation
│   ├── inspect_conversations.py  # CLI: list / show / tail / stop
│   └── web_ui.py                 # Local web viewer (Starlette + SSE)
├── agents/                       # Per-CLI tester workspaces
│   ├── claude-code_agent1/       # claude.md + .mcp.json
│   └── codex_agent1/             # AGENTS.md
├── db/                           # chat.db lives here at runtime (gitignored)
├── docs/                         # CHANGELOG · BACKLOG · INITIAL_SETUP
└── requirements.txt              # Pinned: mcp, pydantic + transitive
```

## 🛠️ Tools the server exposes

| Tool | Use it for |
|:---|:---|
| `get_my_turn` | Primary tool. Returns `your_turn`, `wait`, `complete`, or `no_conversation` plus full history. Idempotent. |
| `send_message(content, signal=None)` | Post a message. `signal='done'` ends early; `signal='blocked'` flags need for human help. |
| `get_conversation_status` | Read-only snapshot for debugging. |

## 🔁 Modes & stop conditions

| Mode | Behaviour | Best for |
|:---|:---|:---|
| **`turns`** | Strict alternation. Server rejects out-of-turn `send_message` calls. | Q&A, code review, debate |
| **`continuous`** | Either agent can post anytime, capped at `--max-turns` per agent. | Parallel brainstorming |

A conversation ends when **any one** of these happens:

- An agent reaches `--max-turns` messages.
- An agent calls `send_message` with `signal='done'` (task complete) or `signal='blocked'` (needs human).
- You manually run `inspect_conversations.py ... stop <id>`.

## 🔌 Register the server with each CLI

Point `command` at the **venv interpreter** so the right deps load; substitute your own absolute repo path. The `--agent-id` is the **only** thing that differs between the two registrations — `command` and `--db-path` must be identical.

<details>
<summary><b>Claude Code</b> — <code>claude mcp add</code> or per-folder <code>.mcp.json</code></summary>

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe",
      "args": [
        "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/src/agent_chat_mcp.py",
        "--agent-id", "claude-code",
        "--db-path", "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db"
      ]
    }
  }
}
```

</details>

<details>
<summary><b>Codex CLI</b> — <code>~/.codex/config.toml</code></summary>

```toml
[mcp_servers.agent_chat]
command = "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe"
args = [
  "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/src/agent_chat_mcp.py",
  "--agent-id", "codex",
  "--db-path", "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db",
]
```

> Codex's loader only reads `~/.codex/config.toml`. A per-folder `.codex/config.toml` is ignored unless you set `CODEX_HOME`.

</details>

> [!TIP]
> Forward slashes work fine for Python paths on Windows. If you use backslashes in JSON, double them: `"D:\\AI_Agents\\..."`.

## 💬 Running a conversation

**Terminal 1** — seed:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --db-path db\chat.db `
  --topic "Compare your approaches to refactoring a legacy Python module" `
  --participants claude-code,codex `
  --first claude-code --mode turns --max-turns 10
```

**Terminal 2** — launch Claude Code from `agents/claude-code_agent1/` and prompt:

> Call `get_my_turn` to begin participating in the active agent_chat conversation. When it's your turn, reply via `send_message`. Keep going until the server tells you the conversation is complete.

**Terminal 3** — launch Codex CLI (registered globally) and prompt the same way.

**Terminal 4 (optional)** — watch live in a browser:

```powershell
.\.venv\Scripts\python.exe src\web_ui.py --db-path db\chat.db
# → http://127.0.0.1:8765/
```

## 🌐 Web UI

A small read-only viewer at `src/web_ui.py` for browsing conversations without copy-pasting `inspect_conversations.py` invocations. Runs as a separate process — does **not** wrap or replace the MCP server.

| Route | What it does |
|:---|:---|
| `GET /` | Conversations table — id, topic, status, mode, participants, message count |
| `GET /conversations/<id>` | Full transcript with metadata. Active conversations auto-update via SSE. |
| `GET /api/conversations[/<id>]` | JSON for scripting |
| `GET /api/conversations/<id>/stream` | SSE: `event: message` per row, `event: complete` on close |

Binds to `127.0.0.1:8765` by default — local-only, no auth.

## 🔍 Inspection / debugging (CLI)

```powershell
# List all conversations
.\.venv\Scripts\python.exe src\inspect_conversations.py --db-path db\chat.db list

# Full transcript
.\.venv\Scripts\python.exe src\inspect_conversations.py --db-path db\chat.db show 1

# Tail live (Ctrl-C to stop)
.\.venv\Scripts\python.exe src\inspect_conversations.py --db-path db\chat.db tail 1

# Force-end a runaway conversation
.\.venv\Scripts\python.exe src\inspect_conversations.py --db-path db\chat.db stop 1
```

The DB is just SQLite — `sqlite3 db\chat.db` and `SELECT * FROM messages` works too.

## 🏗️ Design notes

- **WAL mode.** `PRAGMA journal_mode=WAL` lets two processes (the two MCP servers) read/write the same file safely.
- **No background polling.** Agents pull state via `get_my_turn` whenever they want to check.
- **Identity is config-only.** No auth — anything that runs the server with `--agent-id X` *is* X. Fine for two local CLIs you control; do not expose this over a network without adding auth.
- **Conversations persist.** Killing both CLIs and reopening them resumes from the same DB.

## 📋 Project docs

| Doc | What it covers |
|:---|:---|
| [`docs/INITIAL_SETUP.md`](docs/INITIAL_SETUP.md) | Step-by-step bootstrap reproduction (git, venv, agent wiring) |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Reverse-chronological log of every change |
| [`docs/BACKLOG.md`](docs/BACKLOG.md) | Open enhancements, bug fixes, tech debt — plus a Done section |

## 🗺️ Roadmap

Tracked in [`docs/BACKLOG.md`](docs/BACKLOG.md). Current short-term highlights:

- Make the venv interpreter path portable (no hardcoded absolute paths in MCP configs)
- Lightweight CI workflow validating venv + JSON/TOML + import on push
- Helper PowerShell wrappers for the common `--db-path` invocations
- `wait_for_turn` MCP tool for push-style turn handoff
- Three+ agents and multi-conversation support (schema already supports both)

---

<p align="center">
  Built with <a href="https://modelcontextprotocol.io">MCP</a> · <a href="https://www.starlette.io">Starlette</a> · <a href="https://www.sqlite.org">SQLite</a>
</p>
