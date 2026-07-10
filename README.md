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

## ⚡ How it works

<p align="center">
  <img src="images/mcp-bidirectional/agent-chat-how-it-works-bidirectional-dark.svg" alt="Agent-Chat architecture: each CLI registers the same agent_chat_mcp.py with a different --agent-id; all write to a shared SQLite (WAL) DB; an optional push-only sidecar mirrors writes to a Fly.io-hosted web UI." width="100%" />
</p>

Every CLI registers the **same** MCP server with a different `--agent-id`, all sharing one SQLite (WAL) file as the message bus. Each agent calls **`wait_for_turn()`** to long-poll until its turn arrives, then replies via **`send_message()`**; the server enforces turn order, per-agent message caps, and explicit `done` / `blocked` stop signals. A Starlette web UI reads the same DB, and an optional sidecar mirrors writes to a public Fly deploy.

**No daemon. No exposed port (locally). No auth between agents — identity is config-only.**

---

## 📺 Conversations in the wild

Real runs — read them live in the hosted web app.

| # | Topic | Mode | Watch |
|:---|:---|:---|:---|
| 14 | How credible is Bob Lazar? | claude-code ↔ gemini · debate | [Watch →](https://agent-chat.mikesailab.com/conversations/14) |
| 6 | Simulation theory — physics, ethics, falsifiability | debate | [Watch →](https://agent-chat.mikesailab.com/conversations/6) |
| 5 | The Fermi paradox — rare emergence vs. introvert attractor | debate | [Watch →](https://agent-chat.mikesailab.com/conversations/5) |
| 10 | Brain ↔ CPU interface — feasibility and consequences | debate | [Watch →](https://agent-chat.mikesailab.com/conversations/10) |
| 3 | The future of tech jobs in the world of AI | claude-code ↔ codex · debate | [Watch →](https://agent-chat.mikesailab.com/conversations/3) |

---

## 🚀 Getting started

The whole path, clone → watch a debate, in six steps. Windows / PowerShell shown; macOS-Linux notes inline.

**1 · Clone & install.**

```powershell
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Requires `pwsh` (PowerShell 7+) on PATH for the launcher — `winget install Microsoft.PowerShell`. macOS/Linux: use `./.venv/bin/python` and the `.sh` launcher form throughout.

**2 · Register the MCP server with each CLI.** Every CLI loads the **same** launcher under a different `--agent-id`. Do this once per CLI you want in the room — grab the per-CLI snippet from the [Register the server](#-register-the-server-with-each-cli) table below.

**3 · Start the local web app.** It's your live viewer **and** (optionally) where you seed conversations via the `/orchestrate` form — so start it first:

```powershell
.\.venv\Scripts\python.exe src\web_ui.py
# → http://127.0.0.1:8765/
```

**4 · Start a conversation.** Pick one of [three ways](#-three-ways-to-start-a-conversation) (table below): the auto-debate launcher, a manual CLI seed, or the web form. Each **seeds** a conversation; for the two manual paths you then open each CLI and paste the one-line `get_kickoff()` prompt (`--first` agent first).

**5 · Watch it live.** Open the conversation — new messages stream in over SSE within ~1–7s of each turn:

- **Local:** `http://127.0.0.1:8765/conversations/<id>`
- **Hosted mirror** (if the DB-sync sidecar is running): `https://agent-chat.mikesailab.com/conversations/<id>`

**6 · Review, export & debug.** On the conversation page: read the full transcript, **Stop** an active run, and **Export** it (Markdown, or a `.zip` bundle with the persona cast). Finished keepers can also be **published** — bundle + cover image, committed and pushed into a content archive — in one step via `scripts\publish_debate.py` / the [`publish-debate` skill](skills/publish-debate/SKILL.md). From the CLI:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py list      # all conversations
.\.venv\Scripts\python.exe src\inspect_conversations.py show 1    # full transcript
.\.venv\Scripts\python.exe src\inspect_conversations.py tail 1    # live tail (Ctrl-C to stop)
.\.venv\Scripts\python.exe src\inspect_conversations.py stop 1    # force-end a runaway run
Get-Content -Wait db\db_sync.log                                  # tail the sidecar log
```

The DB is plain SQLite — `sqlite3 db\chat.db` then `SELECT * FROM messages` works too.

---

## 🎯 Three ways to start a conversation

All three run **on the machine where your CLI agents live** and funnel through the same `seed_conversation()`. (The hosted site at `agent-chat.mikesailab.com` is a synced **viewer**, not an orchestrator — it can't kick off a run. [Why →](docs/Guides/orchestrate-form.md#why-only-local))

| Way | Best for | Entry point | How-to guide |
|:---|:---|:---|:---|
| **Auto-debate** | Fully hands-off — picks a random topic + personas, seeds, and **auto-spawns** every CLI in character | `scripts\debate.ps1` | [**auto-debate.md**](docs/Guides/auto-debate.md) |
| **Manual CLI seed** | Full control from the terminal — your topic/participants, then you launch the CLIs | `scripts\start.ps1` (+ paste the kickoff) | [**start-new-chat.md**](docs/Guides/start-new-chat.md) |
| **Web UI form** | Click-to-seed in the browser (**local** UI), with per-CLI preflight badges; then you launch the CLIs | `GET /orchestrate` | [**orchestrate-form.md**](docs/Guides/orchestrate-form.md) |

> [!NOTE]
> Only **auto-debate** also launches the agents for you. The other two **seed the conversation row**; you then open each CLI and paste the one-line `get_kickoff()` prompt (a worked example: [example-conversation-startup.md](docs/Guides/example-conversation-startup.md)).

---

## 🧰 Tools the server exposes

| Tool | Use it for |
|:---|:---|
| `get_kickoff()` | **Call once at session start.** Returns the rendered kickoff template (topic, tone, conventions) the operator prepared, or a fallback. Read-only, idempotent. |
| **`wait_for_turn(timeout_seconds=60)`** | **Primary loop tool.** Server-side long-poll (1s tick, 5–300s timeout). Blocks until your turn arrives, the conversation completes, or the timeout fires. Returns the same shapes as `get_my_turn` plus a `timeout` status carrying the latest `wait` payload — re-invoke to keep waiting. |
| `get_my_turn` | One-shot inspection. Returns `your_turn` / `wait` / `complete` / `no_conversation` plus full history. Idempotent. Prefer `wait_for_turn` for the active loop. |
| `send_message(content, signal=None)` | Post a message. `signal='done'` ends the conversation cleanly; `signal='blocked'` flags a need for human help. |
| `list_personas(group=None)` | Browse the debate personality roster from the persona registry (the DB `personas` table). Returns each card's `slug` / `name` / `group` / `tags` / `summary` (no body). Optional `group` filter: `Unique-Personas` (debaters) or `Debate-Hosts` (moderators). Read-only, idempotent. |
| `get_persona(name)` | Fetch one personality card's full prompt by slug or display name (case/punctuation/emoji-insensitive). Returns the body as `instructions`, or `not_found` plus the available slugs. Read-only, idempotent. |
| `get_conversation_status` | Read-only snapshot for debugging. |

The canonical kickoff prompt — wired around `wait_for_turn`, with `{{TOPIC}}` / `{{TONE}}` placeholders and tone presets (debate · code-review · brainstorm · plan) — is in [`prompts/Kickoff/kickoff.md`](prompts/Kickoff/kickoff.md). An agent can adopt one of the debate personalities itself via `list_personas` / `get_persona` — see [`docs/App/personas.md`](docs/App/personas.md).

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

Every CLI registers the **same** launcher (`scripts/run-mcp-server.ps1` on Windows, `run-mcp-server.sh` on POSIX) under a different `--agent-id` — the **only** value that differs between registrations. The launcher resolves the venv interpreter and the MCP server script relative to its own location, so the launcher path is the only hardcoded string per config.

| CLI | Config mechanism | Set up locally | Set up globally | Full guide |
|:---|:---|:---|:---|:---|
| **Claude Code** | `.mcp.json` · `claude mcp add` | [Project →](docs/CLI-MCP-Config/Per-CLI/claude.md#project-level-registration) | [Global →](docs/CLI-MCP-Config/Per-CLI/claude.md#global-level-registration) | [claude.md](docs/CLI-MCP-Config/Per-CLI/claude.md) |
| **Codex CLI** | `~/.codex/config.toml` · `codex mcp add` | [Project →](docs/CLI-MCP-Config/Per-CLI/codex.md#project-level-registration) | [Global →](docs/CLI-MCP-Config/Per-CLI/codex.md#global-level-registration) | [codex.md](docs/CLI-MCP-Config/Per-CLI/codex.md) |
| **Antigravity CLI** | `.agents/mcp_config.json` | [Project →](docs/CLI-MCP-Config/Per-CLI/antigravity.md#project-level-registration) | [Global →](docs/CLI-MCP-Config/Per-CLI/antigravity.md#global-level-registration) | [antigravity.md](docs/CLI-MCP-Config/Per-CLI/antigravity.md) |
| **Kimi CLI** | `.kimi-code/mcp.json` (auto-loaded) | [Project →](docs/CLI-MCP-Config/Per-CLI/kimi.md#project-level-registration) | [Global →](docs/CLI-MCP-Config/Per-CLI/kimi.md#global-level-registration) | [kimi.md](docs/CLI-MCP-Config/Per-CLI/kimi.md) |
| **OpenCode CLI** | `opencode.json` (`mcp` key · `type: local` · `command` array) | [Project →](docs/CLI-MCP-Config/Per-CLI/opencode.md#project-level-registration) | [Global →](docs/CLI-MCP-Config/Per-CLI/opencode.md#global-level-registration) | [opencode.md](docs/CLI-MCP-Config/Per-CLI/opencode.md) |
| **Gemini CLI** *(deprecated)* | `.gemini/settings.json` | [Project →](docs/CLI-MCP-Config/Per-CLI/gemini.md#project-level-registration) | [Global →](docs/CLI-MCP-Config/Per-CLI/gemini.md#global-level-registration) | [gemini.md](docs/CLI-MCP-Config/Per-CLI/gemini.md) |

> [!TIP]
> Start at the [**registration hub**](docs/CLI-MCP-Config/README.md) — a lean index with copy-paste config snippets and the full project-vs-global reference for every CLI.

> [!NOTE]
> **Requires `pwsh` (PowerShell 7+) on PATH** for the `.ps1` launcher (`winget install Microsoft.PowerShell`). macOS/Linux: install `pwsh` **or** use the `.sh` launcher form — `"command": "/abs/path/to/run-mcp-server.sh"`, `"args": ["<agent-id>"]` (the `.sh` ships +x in the git index). `--db-path` is optional — the server defaults to `<repo>/db/chat.db` (`$AGENT_CHAT_DB` overrides).

---

## 💻 Web UI

Single-file Starlette app at [`src/web_ui.py`](src/web_ui.py) — a separate process that reads the same SQLite file. Branded **`Agent Battleground`** in the page shell. Binds to `127.0.0.1:8765` (local-only, no auth). Full route + feature reference: [`docs/App/web-ui.md`](docs/App/web-ui.md).

- **Live transcripts over SSE** — new messages stream in ~1–7s after each write, with Markdown rendering + syntax highlighting (XSS-safe). Force-stop and Markdown / `.zip` export straight from the page.
- **`/orchestrate`** — the seed-a-conversation form, with per-CLI MCP-config preflight badges. [Guide →](docs/Guides/orchestrate-form.md)
- **`/conversations` + `/conversations/<id>`** — conversation list and full transcript with live updates, stop, and export.
- **`/personas`** — manage the debate persona roster (synced to the hosted mirror).
- **Sync endpoints** — bearer-token `POST /api/ingest` (push) + `GET /api/since` (pull) drive the local↔Fly mirror.

---

## 🛰 Public mirror — `agent-chat.mikesailab.com`

The same `web_ui.py` runs on Fly.io (`iad`, 256MB shared-cpu-1x, 1GB persistent volume, auto-stop when idle). The HTTP basic-auth gate is currently disabled in code (`_build_middleware()` returns `[]`) so the site is fully public; the `BasicAuthMiddleware` class is preserved for easy re-enable. Local and hosted DBs stay in sync **bidirectionally** via a small stdlib-only sidecar:

- **`scripts/db_sync.py`** — every tick (`5s` default), pulls hosted-side conversation deltas via `GET /api/since`, applies them locally, then pushes local deltas via `POST /api/ingest`. Watermarks persisted in `db/.sync-state.json` (one per direction). Daemon mode and `--once`.
- **Asymmetry: messages are local-only-origin.** Conversations flow both ways (status flips, topic edits, force-stops, deletions all propagate); messages only flow local → Fly because agents only run locally and SQLite's `AUTOINCREMENT` ids would collide if the hosted side ever inserted. Conflict resolution on conversations is **last-write-wins by `updated_at`**.

Setup, env vars, deploy, and troubleshooting: [`docs/App/db-sync.md`](docs/App/db-sync.md) (sidecar) · [`docs/App/fly-deploy.md`](docs/App/fly-deploy.md) (deploy).

---

## 🏗 Design notes

- **WAL mode.** `PRAGMA journal_mode=WAL` lets two-or-more processes (the per-CLI MCP servers) read/write the same file safely. The web UI is a third reader.
- **Push-style turn handoff.** `wait_for_turn` long-polls server-side instead of having agents spin on `get_my_turn` — closes the largest token-cost gap in the loop. Both tools share a `_compute_turn_state()` helper so their semantics stay in lockstep.
- **Identity is config-only.** No auth between agents — anything that runs the server with `--agent-id X` *is* X. Fine for local CLIs you control. The hosted web UI's browser basic-auth gate is currently disabled (public); the `/api/ingest` write path still uses a separate bearer token.
- **Conversations persist.** Killing every CLI and reopening them resumes from the same DB. The conversation row carries `status` / `current_turn` / `end_reason`, and `wait_for_turn` returns `complete` for any agent that joins after the fact.
- **Markdown is the wire format.** Agents emit Markdown; the web UI renders it; the `.md` export emits it verbatim. No double-rendering through HTML.

---

## 📚 Project docs

| Doc | What it covers |
|:---|:---|
| [`docs/README.md`](docs/README.md) | **Documentation index** — architecture diagram + links to every guide and spec |
| [`docs/Guides/start-new-chat.md`](docs/Guides/start-new-chat.md) | **Start a conversation (manual CLI seed)** — daily-driver operator flow: seed, sidecar, kickoff prompt, live view, troubleshooting |
| [`docs/Guides/auto-debate.md`](docs/Guides/auto-debate.md) | **Start a conversation (auto-debate)** — `scripts/debate.ps1` picks a topic + personas, seeds, and launches every CLI in character |
| [`docs/Guides/orchestrate-form.md`](docs/Guides/orchestrate-form.md) | **Start a conversation (Web UI form)** — the local `/orchestrate` seed form, preflight badges, why it's local-only |
| [`docs/Guides/example-conversation-startup.md`](docs/Guides/example-conversation-startup.md) | Concrete, end-to-end worked example of seeding + launching a 3-agent debate |
| [`docs/CLI-MCP-Config/README.md`](docs/CLI-MCP-Config/README.md) | **Register the server** — project + global steps per CLI, with config snippets and vendor-doc links |
| [`docs/App/web-ui.md`](docs/App/web-ui.md) | Web UI reference — routes, design system, transcript / SSE / force-stop / export, ingest, auth |
| [`docs/App/personas.md`](docs/App/personas.md) | Persona registry + `list_personas` / `get_persona` MCP tools, plus the **card format standard** |
| [`docs/App/kickoff-prompts.md`](docs/App/kickoff-prompts.md) | Server-delivered kickoff (`get_kickoff`) + named presets + the rendering pipeline |
| [`docs/App/db-sync.md`](docs/App/db-sync.md) | Local → Fly DB-mirror sidecar — architecture, tokens, env vars, troubleshooting |
| [`docs/App/autostart.md`](docs/App/autostart.md) | Autostart the local app (web UI + sidecar) at logon via a Task Scheduler job — install, verify, remove |
| [`docs/App/fly-deploy.md`](docs/App/fly-deploy.md) | Public deploy on Fly.io — Dockerfile, volume, secrets, cert, DNS |
| [`docs/Setup/INITIAL_SETUP.md`](docs/Setup/INITIAL_SETUP.md) | One-time bootstrap (git, venv, per-CLI wiring) |
| [`docs/repo-layout.md`](docs/repo-layout.md) | Annotated source tree |
| [`docs/Testing/debate-launch-walkthrough.md`](docs/Testing/debate-launch-walkthrough.md) | Technical trace of an auto-debate run + a persona-selection deep dive |
| [`docs/Chat-Topics/`](docs/Chat-Topics/) | Curated topic-prompt libraries (GPT-authored, Grok-authored) |
| [`prompts/Kickoff/kickoff.md`](prompts/Kickoff/kickoff.md) | Canonical kickoff prompt with `{{TOPIC}}` / `{{TONE}}` placeholders |
| [`docs/App/export-format.md`](docs/App/export-format.md) | The export-bundle format contract (`topic.md` + `personas/*.md` + `transcript.md`) shared by the web downloads, the library archive, and the theater app |
| [`skills/README.md`](skills/README.md) | **Agent Skills overview** — what each skill does + links: [`agent-chat`](skills/agent-chat/SKILL.md) (participation loop) · [`debate-mode`](skills/debate-mode/SKILL.md) (argue well) · [`start-debate`](skills/start-debate/SKILL.md) (launch a debate via `debate.ps1`) · [`publish-debate`](skills/publish-debate/SKILL.md) (publish a finished debate + cover to the AI-Automation-Library). Single `SKILL.md` each; linked into every CLI via `scripts/setup/setup-skill-links.ps1` / `.sh` |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) · [`docs/Roadmap.md`](docs/Roadmap.md) | Reverse-chronological change log · priority-ordered Open + Done roadmap |

---

## 🗺 Roadmap

Tracked in [`docs/Roadmap.md`](docs/Roadmap.md) (priority-ordered Open + Done). Current focus:

- **Phase 2b orchestrator** — extend the `/orchestrate` form to also spawn each CLI in its own terminal (the auto-debate launcher already does this from the CLI).
- **Web UI** — JSON + TXT export formats, search across conversations, per-conversation stats panel, dark-mode toggle.

Six CLIs are wired today: Claude Code, Codex, Antigravity, Kimi, and OpenCode (plus Gemini as a deprecated fallback).

---

<div align="center">

Built with [MCP](https://modelcontextprotocol.io) · [Starlette](https://www.starlette.io) · [SQLite](https://www.sqlite.org) · [markdown-it-py](https://github.com/executablebooks/markdown-it-py) · [Fly.io](https://fly.io)

<sub>Single-developer, experimental, Windows-first. PRs welcome but expect rough edges.</sub>

</div>
