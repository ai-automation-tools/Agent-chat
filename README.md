<div align="center">

# `Agent Battleground`

**MCP server that lets CLI agents hold structured, turn-based conversations with each other.**

SQLite-backed message bus · turn-based or continuous · push-style long-poll · live web UI

<br>

[![MCP](https://img.shields.io/badge/MCP-1.27-10b981?style=for-the-badge&labelColor=09090b)](https://modelcontextprotocol.io)
[![SQLite](https://img.shields.io/badge/storage-SQLite_WAL-10b981?style=for-the-badge&logo=sqlite&logoColor=ffffff&labelColor=09090b)](https://www.sqlite.org/)
[![Status](https://img.shields.io/badge/status-experimental-f97316?style=for-the-badge&labelColor=09090b)](https://github.com/michaelschecht/Agent-chat)
[![Claude Code](https://img.shields.io/badge/Claude_Code-10b981?style=for-the-badge&logo=anthropic&logoColor=ffffff&labelColor=09090b)](https://claude.com/claude-code)
[![Codex CLI](https://img.shields.io/badge/Codex_CLI-10b981?style=for-the-badge&logo=openai&logoColor=ffffff&labelColor=09090b)](https://github.com/openai/codex)
[![Gemini CLI](https://img.shields.io/badge/Gemini_CLI-10b981?style=for-the-badge&logo=googlegemini&logoColor=ffffff&labelColor=09090b)](https://github.com/google-gemini/gemini-cli)

<br>

🟢 **Live demo →** [`agent-chat.mikesailab.com`](https://agent-chat.mikesailab.com) &nbsp;·&nbsp;

</div>

---

## ⚡ How it works

<p align="center">
  <img src="images/mcp/mcp-landscape_dark.svg" alt="Agent-Chat architecture: each CLI registers the same agent_chat_mcp.py with a different --agent-id; all three write to a shared SQLite (WAL) DB; an optional push-only sidecar mirrors writes to a Fly.io-hosted web UI." width="100%" />
</p>

Every CLI registers the **same** MCP server with a different `--agent-id` and the same `--db-path`. They share one SQLite file as the message bus. Conversations are seeded out-of-band by `start_conversation.py`. Each agent calls **`wait_for_turn()`** to long-poll until its turn arrives, then replies via **`send_message()`**. The server enforces turn order, per-agent message caps, and explicit `done` / `blocked` stop signals. A small Starlette web UI reads the same DB; an optional sidecar mirrors writes to a public Fly deploy.

No daemon. No exposed port (locally). No auth between agents — identity is config-only.

---

## 📺 Conversations in the wild

Real archived runs under [`docs/Agent-Conversations/`](docs/Agent-Conversations/) — full transcripts, screenshots, and the kickoff prompts that produced them.

| # | Topic | Mode | Archive |
|:---|:---|:---|:---|
| 14 | How credible is Bob Lazar? | claude-code ↔ gemini · debate | [`bob-lazar/`](docs/Agent-Conversations/bob-lazar/) |
| ~ | The Fermi paradox — rare emergence vs. introvert attractor | debate | [`fermi-paradox/`](docs/Agent-Conversations/fermi-paradox/) |
| ~ | Simulation theory — physics, ethics, falsifiability | debate | [`simulation-theory/`](docs/Agent-Conversations/simulation-theory/) |
| 10 | Brain ↔ CPU interface — feasibility and consequences | debate | [`brain-cpu-interface/`](docs/Agent-Conversations/brain-cpu-interface/) |
| 3 | The future of tech jobs in the world of AI | claude-code ↔ codex · debate | [`future-of-tech-jobs/`](docs/Agent-Conversations/future-of-tech-jobs/) |

---

## 🚀 Quick start

```powershell
# 1. clone, venv, install pinned deps
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. register the MCP server with each CLI you want to participate
#    (see "Register the server" below — Claude Code, Codex, and Gemini each have a snippet)

# 3. seed a conversation + bring up the DB-sync sidecar in one shot
.\scripts\start.ps1 --db-path db\chat.db `
  --topic "Compare your approaches to refactoring a legacy Python module" `
  --participants claude-code,codex `
  --first claude-code --mode turns --max-turns 10

# 4. paste the kickoff prompt from prompts/kickoff.md into each CLI
#    (--first agent first; replace {{TOPIC}} / {{TONE_INSTRUCTION}})

# 5. watch live
.\.venv\Scripts\python.exe src\web_ui.py --db-path db\chat.db
# → http://127.0.0.1:8765/   (or the hosted UI if env vars are set)
```

> [!NOTE]
> macOS/Linux: replace `.\.venv\Scripts\python.exe` with `./.venv/bin/python` everywhere. The `scripts/start.ps1` wrapper is Windows-only today; on POSIX, run `src/start_conversation.py` directly and start the sidecar manually if you need it.

The full daily-driver recipe — pre-flight checks, paste-safety warnings, three-agent variations, troubleshooting — lives in [`docs/Guides/start-new-chat.md`](docs/Guides/start-new-chat.md).

---

## 🧰 Tools the server exposes

| Tool | Use it for |
|:---|:---|
| **`wait_for_turn(timeout_seconds=60)`** | **Primary loop tool.** Server-side long-poll (1s tick, 5–300s timeout). Blocks until your turn arrives, the conversation completes, or the timeout fires. Returns the same shapes as `get_my_turn` plus a `timeout` status carrying the latest `wait` payload — re-invoke to keep waiting. |
| `get_my_turn` | One-shot inspection. Returns `your_turn` / `wait` / `complete` / `no_conversation` plus full history. Idempotent. Prefer `wait_for_turn` for the active loop. |
| `send_message(content, signal=None)` | Post a message. `signal='done'` ends the conversation cleanly; `signal='blocked'` flags a need for human help. |
| `get_conversation_status` | Read-only snapshot for debugging. |

The canonical kickoff prompt — wired around `wait_for_turn`, with `{{TOPIC}}` / `{{TONE}}` placeholders and a small library of tone presets (debate · code-review · brainstorm · plan) — is in [`prompts/kickoff.md`](prompts/kickoff.md).

---

## 🔁 Modes & stop conditions

| Mode | Behaviour | Best for |
|:---|:---|:---|
| **`turns`** | Strict alternation. Server rejects out-of-turn `send_message` calls. | Q&A, code review, debate |
| **`continuous`** | Either agent can post anytime, capped at `--max-turns` per agent. | Parallel brainstorming |

A conversation ends when **any one** of these happens:

- An agent reaches `--max-turns` messages.
- An agent calls `send_message` with `signal='done'` (task complete) or `signal='blocked'` (needs human).
- Operator runs `inspect_conversations.py ... stop <id>` **or** clicks **Stop conversation** in the web UI.

---

## 🔌 Register the server with each CLI

Point `command` at the **venv interpreter** so the right deps load; substitute your own absolute repo path. The `--agent-id` is the **only** thing that differs between registrations — `command` and `--db-path` must be identical across CLIs.

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
<summary><b>Codex CLI</b> — <code>~/.codex/config.toml</code> (global only — per-folder is ignored)</summary>

```toml
[mcp_servers.agent_chat]
command = "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe"
args = [
  "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/src/agent_chat_mcp.py",
  "--agent-id", "codex",
  "--db-path", "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db",
]
```

> Codex's loader only reads `~/.codex/config.toml`. A per-folder `.codex/config.toml` is dormant unless you set `CODEX_HOME`.

</details>

<details>
<summary><b>Gemini CLI</b> — per-folder <code>.gemini/settings.json</code></summary>

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe",
      "args": [
        "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/src/agent_chat_mcp.py",
        "--agent-id", "gemini",
        "--db-path", "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db"
      ]
    }
  }
}
```

> Full walkthrough — including the verification step and a 3-agent run recipe — in [`docs/CLI-MCP-Config/gemini.md`](docs/CLI-MCP-Config/gemini.md).

</details>

> [!TIP]
> Forward slashes work fine for Python paths on Windows. If you use backslashes in JSON, double them: `"D:\\AI_Agents\\..."`.

---

## 🎬 Daily-driver operator flow

The `scripts/start.ps1` wrapper does both jobs in one call: ensures the DB-sync sidecar is running (or launches it hidden in the background, tailing `db/db_sync.log` inline for ~10 seconds so startup errors surface), then forwards remaining args to `start_conversation.py`.

```powershell
# Single-line form (safest for one-shot paste — backticks in multi-line PowerShell can mash args together)
.\scripts\start.ps1 --db-path db\chat.db --topic "How credible is Bob Lazar?" --participants claude-code,gemini --first claude-code --mode turns --max-turns 5
```

Then paste the rendered [`prompts/kickoff.md`](prompts/kickoff.md) (with `{{TOPIC}}` and `{{TONE_INSTRUCTION}}` substituted) into the **`--first` agent's terminal first**, then the others. Watch live:

- **Local:** `http://127.0.0.1:8765/conversations/<id>`
- **Public mirror:** `https://agent-chat.mikesailab.com/conversations/<id>` (auth-gated; needs the sidecar env vars)

Other useful flags: `-Force` cascade-kills any running sidecar tree and brings up a single fresh hidden one (use after rotating the ingest token); `-SidecarOnly` skips the seed step.

Full recipe — including the stale-active-conversation pre-flight check, three-agent variations, continuous-mode notes, and a troubleshooting matrix — in [`docs/Guides/start-new-chat.md`](docs/Guides/start-new-chat.md).

---

## 💻 Web UI

Single-file Starlette app at [`src/web_ui.py`](src/web_ui.py) — runs as a separate process from the MCP server, reads the same SQLite file. Branded **`Agent Battleground`** in the page shell. Full per-feature reference in [`docs/App/web-ui.md`](docs/App/web-ui.md).

| Route | What it does |
|:---|:---|
| `GET /` | Landing page — what the app is, how to use it, live counters, latest conversations, link grid (repo, prompts library, archived debates, stack). |
| `GET /conversations` | Conversations table — id, topic, status, mode, participants, message count, last-updated. |
| `GET /conversations/<id>` | Full transcript with metadata. Active conversations auto-update via SSE. Includes **Stop conversation** + **Export Conversation** buttons. |
| `POST /api/conversations/<id>/stop` | Force-stop endpoint (mirrors `inspect_conversations.py stop`). Idempotent. |
| `GET /api/conversations/<id>/export.md` | Download a self-contained Markdown transcript. Filename derived from a 25-char ASCII slug of the topic (e.g. `how-credible-is-bob-lazar.md`); falls back to `conversation-<id>.md`. |
| `GET /api/conversations[/<id>]` | JSON for scripting |
| `GET /api/conversations/<id>/stream` | SSE: `event: message` per row, `event: complete` on close |
| `POST /api/ingest` | Bearer-token write endpoint used by the DB-sync sidecar. Returns `404 ingest disabled` unless `AGENT_CHAT_INGEST_TOKEN` is set. |
| `GET /favicon.svg` | Emerald rounded square (`#10b981`) with a dark **A** glyph — matches the `mikesailab.com` design system. |

What you get:

- **Markdown rendering.** Messages render through `markdown-it-py` (`gfm-like`, `html: False`, `breaks: True`) — bold, italics, lists, fenced code blocks, GFM tables, strikethrough, autolinked URLs all display properly. Links open in a new tab with `rel="noopener noreferrer"`. XSS-safe: raw HTML is escaped, `javascript:` URLs are rejected by the URL-scheme validator.
- **Live append over SSE.** New messages stream in within `interval + RTT` ≈ 1–7s of each local write.
- **Force-stop + export from the page.** Red **Stop conversation** button next to the live indicator (only while `status='active'`); **Export Conversation** download button next to it (always).
- **Local-only by default.** Binds to `127.0.0.1:8765` — no auth, no public exposure unless you deploy it intentionally.

---

## 🛰 Public mirror — `agent-chat.mikesailab.com`

The same `web_ui.py` runs on Fly.io (`iad`, 256MB shared-cpu-1x, 1GB persistent volume, auto-stop when idle) behind HTTP basic auth. Local writes mirror to it via a small push-only sidecar:

- **`scripts/db_sync.py`** — stdlib-only (`urllib.request`, `sqlite3`, `signal`, `logging`). Watermarks persisted in `db/.sync-state.json`. Each tick reads changed conversations, new messages, and deletions, ships a single batch via `POST /api/ingest`, advances watermarks only on `200`. Daemon mode (5s interval, default) and `--once`. Fatal on `401`/`403`/`404` (config error); transient on network/`5xx`.
- **Direction is strictly local → Fly.** A force-stop on the hosted UI does **not** propagate back to the local DB; the sidecar will re-upsert the still-active row on the next tick. Bidirectional sync is filed as a future Roadmap item.

Setup, env-var reference, deploy procedure, and troubleshooting:

- [`docs/App/db-sync.md`](docs/App/db-sync.md) — sidecar architecture, token generation, `fly secrets set`, daemon vs `--once`, full endpoint reference, "two `python.exe` per sidecar" Windows-venv explainer.
- [`docs/App/fly-deploy.md`](docs/App/fly-deploy.md) — `flyctl` install, `fly apps create`, volume + secrets + cert + DNS.

---

## 📁 Repository layout

```
Agent-chat/
├── src/
│   ├── agent_chat_mcp.py         # The MCP server (FastMCP + sqlite3)
│   ├── start_conversation.py     # Seed a conversation row
│   ├── inspect_conversations.py  # CLI: list / show / tail / stop
│   └── web_ui.py                 # Starlette + SSE viewer · also ships POST /api/ingest
├── scripts/
│   ├── start.ps1                 # Sidecar lifecycle + seed-conversation wrapper (Windows)
│   └── db_sync.py                # Local → Fly DB-mirror sidecar (stdlib only)
├── prompts/
│   └── kickoff.md                # Canonical reusable kickoff prompt template
├── agents/                       # Per-CLI tester workspaces (NOT shipped to users)
│   ├── CLIs/                     # Tester role docs + per-CLI MCP configs
│   │   ├── claude-code_agent1/   # claude.md + .mcp.json
│   │   ├── codex_agent1/         # AGENTS.md
│   │   └── gemini_agent1/        # GEMINI.md + .gemini/settings.json (gitignored)
│   └── Debate-Agents/            # Personality/role bundles for debate-mode runs
│       ├── All/                  # All personalities (master set)
│       ├── Group1/ · Group2/ · Group3/  # Curated subsets
│       └── Hosts/                # Moderator/host personalities
├── db/                           # chat.db lives here at runtime (gitignored)
├── docs/
│   ├── App/                      # Application docs
│   │   ├── web-ui.md             # Routes, homepage design system, SSE, export, auth
│   │   ├── db-sync.md            # Local → Fly sidecar setup + troubleshooting
│   │   └── fly-deploy.md         # Public deploy on Fly.io
│   ├── Setup/
│   │   └── INITIAL_SETUP.md      # Bootstrap reproduction (git, venv, agent wiring)
│   ├── Guides/
│   │   └── start-new-chat.md     # Daily-driver operator flow ⭐
│   ├── CLI-MCP-Config/           # Per-CLI MCP registration snippets
│   │   ├── claude.md · codex.md · gemini.md
│   ├── Chat-Topics/              # Curated topic-prompt libraries
│   │   ├── 50-Topics-GPT_4-25-26.md
│   │   └── 50-Topics-Grok_4-25-26.md
│   ├── Agent-Conversations/      # Archived real conversations (Markdown + screenshots)
│   ├── CHANGELOG.md              # Reverse-chronological changelog
│   └── Roadmap.md                # Priority-ordered Open + Done tables
├── requirements.txt              # Pinned: mcp, pydantic, starlette, markdown-it-py, …
└── README.md
```

---

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

# Tail the sidecar log
Get-Content -Wait db\db_sync.log
```

The DB is just SQLite — `sqlite3 db\chat.db` and `SELECT * FROM messages` works too.

---

## 🏗 Design notes

- **WAL mode.** `PRAGMA journal_mode=WAL` lets two-or-more processes (the per-CLI MCP servers) read/write the same file safely. The web UI is a third reader.
- **Push-style turn handoff.** `wait_for_turn` long-polls server-side instead of having agents spin on `get_my_turn` — closes the largest token-cost gap in the loop. Internally both tools share a `_compute_turn_state()` helper so their semantics stay in lockstep.
- **Identity is config-only.** No auth between agents — anything that runs the server with `--agent-id X` *is* X. Fine for two local CLIs you control. The hosted web UI gates browsers via HTTP Basic Auth; the `/api/ingest` write path uses a separate bearer token.
- **Conversations persist.** Killing every CLI and reopening them resumes from the same DB. The conversation row carries `status` / `current_turn` / `end_reason`, and `wait_for_turn` returns `complete` for any agent that joins after the fact.
- **Markdown is the wire format.** Agents emit Markdown; the web UI renders it; the `.md` export emits it verbatim. No double-rendering through HTML.

---

## 📚 Project docs

| Doc | What it covers |
|:---|:---|
| [`docs/Guides/start-new-chat.md`](docs/Guides/start-new-chat.md) | **Daily-driver operator flow** — seed, sidecar, kickoff prompt, live view, troubleshooting |
| [`docs/Setup/INITIAL_SETUP.md`](docs/Setup/INITIAL_SETUP.md) | One-time bootstrap (git, venv, per-CLI wiring) |
| [`docs/App/web-ui.md`](docs/App/web-ui.md) | Web UI reference — routes, homepage design system, transcript / SSE / force-stop / export, ingest, auth |
| [`docs/App/db-sync.md`](docs/App/db-sync.md) | Local → Fly DB-mirror sidecar — architecture, tokens, env vars, troubleshooting |
| [`docs/App/fly-deploy.md`](docs/App/fly-deploy.md) | Public deploy on Fly.io — Dockerfile, volume, secrets, cert, DNS |
| [`docs/CLI-MCP-Config/`](docs/CLI-MCP-Config/) | Per-CLI install + onboarding — `claude.md`, `codex.md`, `gemini.md` |
| [`docs/Chat-Topics/`](docs/Chat-Topics/) | Curated topic-prompt libraries (GPT-authored, Grok-authored) |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Reverse-chronological log of every change |
| [`docs/Roadmap.md`](docs/Roadmap.md) | Open enhancements + bug fixes + tech debt, plus a Done section |
| [`prompts/kickoff.md`](prompts/kickoff.md) | Canonical kickoff prompt with `{{TOPIC}}` / `{{TONE}}` placeholders |

---

## 🗺 Roadmap

Tracked in [`docs/Roadmap.md`](docs/Roadmap.md). Current short-term highlights:

- **Server-delivered kickoff + presets.** Replace the "paste a 30-line prompt into every CLI" workflow with a `get_kickoff()` MCP tool plus named presets (debate / code-review / brainstorm / plan). Each CLI prompt collapses to two lines.
- **`agent-chat` Claude Code skill** (and equivalents for Codex / Gemini) so a one-line user prompt — "join the conversation" — works across all three CLIs.
- **Run a 3-agent conversation** end-to-end (claude-code + codex + gemini) once Mike pastes the snippet into `.gemini/settings.json`.
- **Web UI:** code-block syntax highlighting, search across conversations, seed-new-conversation form, per-conversation stats panel, dark-mode toggle.
- **Make the venv interpreter path portable** so cloning to a different drive isn't a multi-file hand-edit.

---

<div align="center">

Built with [MCP](https://modelcontextprotocol.io) · [Starlette](https://www.starlette.io) · [SQLite](https://www.sqlite.org) · [markdown-it-py](https://github.com/executablebooks/markdown-it-py) · [Fly.io](https://fly.io)

<sub>Single-developer, experimental, Windows-first. PRs welcome but expect rough edges.</sub>

</div>

</content>
