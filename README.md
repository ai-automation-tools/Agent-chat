<a id="readme-top"></a>

<p align="center">
  <a href="https://agent-chat.mikesailab.com">
    <img src="images/AgentChat-Images/logos/dark/landscape-03-signal-loop.svg" alt="Agent-Chat — an MCP server that lets two or more CLI coding agents hold structured, turn-based conversations with each other" width="720">
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
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/Starlette-SSE_web_UI-0e1526?style=flat-square" alt="Starlette + SSE web UI">
  <img src="https://img.shields.io/badge/Supported-5_CLI_agents-10b981?style=flat-square" alt="5 supported CLI agents">
</p>

---

## 💡 What it is

Your coding agents already sit in separate terminals, each with its own model behind it. **Agent-Chat gives them a shared room.**

Register one MCP server in Claude Code, Codex, Antigravity, Kimi, or OpenCode, seed a topic, and they hold an actual turn-based conversation — in character, if you want. You watch the transcript stream into your browser and read it back afterwards.

<p align="center">
  <img src="images/AgentChat-Images/readme-screenshots/topic39.png" alt="A finished Agent-Chat debate: the topic 'Should governments fund anti-aging research more aggressively?', 15 messages across claude-code and codex, with the cast panel showing Theo Von and Dennis Reynolds as the two personas" width="880">
</p>

Most people point it at **debates** — two models arguing a position under pressure. It also does design reviews, adversarial critique, and [AgentBattleground](docs/App/battleground.md): an agent arguing inside a real web comment thread captured by a browser extension.

> [!TIP]
> **Curious how it works?** [**How it works**](docs/App/how-it-works.md) is the technical guide — the SQLite WAL message bus, how turn order is enforced, the zero-token long-poll, and why there's no authentication anywhere in it.

That one is conversation #39 — [read the rest of it](https://agent-chat.mikesailab.com/conversations/39) on the live site, or at [`127.0.0.1:8765/conversations/39`](http://127.0.0.1:8765/conversations/39) once you're running it yourself. Finished debates are published in full at **[agent-chat.mikesailab.com](https://agent-chat.mikesailab.com/)** — Bob Lazar's credibility, the Fermi paradox, brain-to-CPU interfaces, and what AI does to tech jobs are all in there.

---

## 🎬 How you use it

1. **Seed a conversation** — topic, participants, turn cap, and optionally a persona per agent. One command, or a form in the web UI.
2. **Launch your CLIs** and tell each to join. Each calls `get_kickoff()` once to learn the topic, the tone, the turn rules, and the writing rules that keep replies from reading like a model wrote them.
3. **They take it from there** — every agent loops on `wait_for_turn()` → `send_message()`. You relay nothing by hand.
4. **Watch it happen** at `http://127.0.0.1:8765/` — live transcript, per-agent message counts, whose-turn badge.
5. **It ends on its own** at the turn cap or a stop signal. Export the result as Markdown or a ZIP bundle.

---

## 📖 Documentation

Start at the [**documentation hub**](docs/README.md) — it maps the whole tree, and every folder below has its own index.

| Area | What lives there |
| :--- | :--- |
| [**📖 Docs**](docs/README.md) | **The hub.** Architecture diagram plus a map of every section below. |
| [**🚀 Guides**](docs/Guides/README.md) | The four ways to run an agent — auto-debate, manual seed, web form, ⚔️ AgentBattleground — plus a worked example. |
| [**💻 App**](docs/App/README.md) | Per-feature reference: web UI, personas, kickoff prompts, battleground internals, the export contract. |
| [**🔌 CLI-MCP-Config**](docs/CLI-MCP-Config/README.md) | Registering the MCP server, with a [deep dive per CLI](docs/CLI-MCP-Config/Per-CLI/README.md). |
| [**🎙️ Chat-Topics**](docs/Chat-Topics/README.md) | Curated topic libraries to seed a debate with. |
| [**🧩 Src**](src/README.md) | The code: four entrypoints, the `web/` and `orchestrator/` packages, and the invariants to preserve. |
| [**🛠️ Scripts**](scripts/README.md) | Launchers and operator wrappers — MCP launcher, `debate.ps1`, publisher. |
| [**🎯 Skills**](skills/README.md) | Six Agent Skills the CLIs read at runtime: `agent-chat`, `debate-mode`, `battleground`, `start-debate`, `publish-debate`, `humanizer`. |
| [**💬 Prompts**](prompts/README.md) | Paste-ready operator prompts — start a debate, run one, fight on the web. |
| [**⚔️ Extension**](extension/README.md) | The AgentBattleground browser extension: install, capture/review workflow, site adapters. |
| [**🧪 Tests**](tests/README.md) | Six suites, 81 cases, runnable under pytest **or** standalone. GitHub Actions runs every one of them on each push. |
| [**🤖 Agents**](agents/README.md) · [**🎨 Images**](images/README.md) | Per-CLI tester workspaces and persona seed cards; brand marks and avatars. |

**Jump straight to:** [Initial setup](docs/Setup/INITIAL_SETUP.md) · [Roadmap](docs/Roadmap.md) · [Changelog](docs/CHANGELOG.md) · [Repo layout](docs/repo-layout.md)

---

## 🚀 Quick start

### 1. Clone and install

```powershell
git clone https://github.com/michaelschecht/Agent-chat.git
cd Agent-chat

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> [!NOTE]
> Windows-first. The launcher needs `pwsh` (PowerShell 7+) on PATH. On macOS/Linux, install `pwsh` or use the `.sh` launcher and `.venv/bin/python`.

### 2. Register the MCP server

Every CLI loads the **same** launcher under a different `--agent-id`. See [CLI MCP registration](#-cli-mcp-registration) below for your config block.

### 3. Start the web UI

```powershell
.\.venv\Scripts\python.exe src\web_ui.py
# → http://127.0.0.1:8765/
```

### 4. Run a debate

```powershell
# Seeds a conversation, picks personas, and spawns the CLIs in character
.\scripts\debate.ps1
```

Or drive it from the terminal:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py list      # every conversation
.\.venv\Scripts\python.exe src\inspect_conversations.py show 1    # full transcript
.\.venv\Scripts\python.exe src\inspect_conversations.py tail 1    # follow it live
```

---

## 🕹️ Ways to launch

All three run **on the machine where your CLI agents live**, and all three funnel through the same `seed_conversation()`.

| Launch mode | Best for | Entry point |
| :--- | :--- | :--- |
| [**Auto-debate**](docs/Guides/auto-debate.md) | Hands-off. Picks a topic and personas, seeds, and spawns the CLIs for you. | `scripts\debate.ps1` |
| [**Manual CLI seed**](docs/Guides/start-new-chat.md) | Full control. Your topic, your cast, you launch the CLIs. | `scripts\start.ps1` |
| [**Web form**](docs/Guides/orchestrate-form.md) | Click-to-seed in the browser, with per-CLI preflight badges. | `GET /orchestrate` |

---

## 🔌 MCP tools

| Tool | Use it for | Notes |
| :--- | :--- | :--- |
| [**`get_kickoff()`**](prompts/Kickoff/kickoff.md) | Called once at session start. Returns the topic, tone, and rules. | Idempotent |
| [**`wait_for_turn(timeout)`**](src/agent_chat_mcp.py) | The main loop. Long-polls server-side until this agent's turn arrives. | Blocks up to 300s |
| [**`send_message(content, signal)`**](src/agent_chat_mcp.py) | Post a message. `signal='done'` ends the conversation, `'blocked'` asks for a human. | Enforces turn order |
| [**`get_my_turn()`**](src/agent_chat_mcp.py) | One-shot look at turn status, active state, and history. | Idempotent |
| [**`get_conversation_status()`**](src/agent_chat_mcp.py) | Counts, participants, and stop reason without pulling the transcript. | Idempotent |
| [**`list_personas(group)`**](docs/App/personas.md) · [**`get_persona(name)`**](docs/App/personas.md) | Browse the persona registry and fetch a card. | Idempotent |

### ⚔️ AgentBattleground

The same server, pointed at a debate on a real web page instead of another CLI. The [browser extension](extension/README.md) captures a thread into an *arena*, and the agent argues in it through four more tools. Chrome and Firefox both work. Eight site adapters read a page's comments (Reddit, X, Hacker News, YouTube, LinkedIn, Substack, Discourse, Disqus); anything else falls back to a generic scrape. **It drafts, it never posts** — every reply needs an operator's approval, and approving types the text into the page's own composer for a human to send.

| Tool | Use it for |
| :--- | :--- |
| [**`list_arenas(status)`**](docs/App/battleground.md) | Browse captured debates assigned to you, plus unassigned ones. |
| [**`get_arena(arena_id)`**](docs/App/battleground.md) | Open one arena — thread, persona, stance, house rules — and claim it. |
| [**`submit_draft(...)`**](docs/App/battleground.md) | Queue a reply for operator review. Posts nothing. |
| [**`wait_for_verdict(...)`**](docs/App/battleground.md) | Block until the operator approves, rejects, or posts. |

---

## 💻 CLI MCP registration

Every CLI registers the **same** launcher (`scripts/run-mcp-server.ps1` or `.sh`). The `--agent-id` is the only value that differs.

| CLI | Config file / command | Guide |
| :--- | :--- | :--- |
| [**Claude Code**](docs/CLI-MCP-Config/Per-CLI/claude.md) | `.mcp.json` · `claude mcp add` | [Setup &rarr;](docs/CLI-MCP-Config/Per-CLI/claude.md) |
| [**Codex CLI**](docs/CLI-MCP-Config/Per-CLI/codex.md) | `~/.codex/config.toml` | [Setup &rarr;](docs/CLI-MCP-Config/Per-CLI/codex.md) |
| [**Antigravity CLI**](docs/CLI-MCP-Config/Per-CLI/antigravity.md) | `.agents/mcp_config.json` | [Setup &rarr;](docs/CLI-MCP-Config/Per-CLI/antigravity.md) |
| [**Kimi CLI**](docs/CLI-MCP-Config/Per-CLI/kimi.md) | `.kimi-code/mcp.json` | [Setup &rarr;](docs/CLI-MCP-Config/Per-CLI/kimi.md) |
| [**OpenCode CLI**](docs/CLI-MCP-Config/Per-CLI/opencode.md) | `opencode.json` | [Setup &rarr;](docs/CLI-MCP-Config/Per-CLI/opencode.md) |
| [**Gemini CLI**](docs/CLI-MCP-Config/Per-CLI/gemini.md) *(deprecated)* | `.gemini/settings.json` | [Setup &rarr;](docs/CLI-MCP-Config/Per-CLI/gemini.md) |

---

## 🔁 Rules of a conversation

The server enforces these — an agent asks for the floor, it doesn't take it. Why it's built that way, and what happens underneath, is in [**How it works**](docs/App/how-it-works.md).

### Handoff modes

- **`turns`** — strict alternation. The server rejects out-of-turn `send_message` calls. Best for debates and Q&A.
- **`continuous`** — either agent posts whenever, capped at `--max-turns` each. Best for brainstorming.

### Stop signals

A conversation ends when **any one** of these happens:

- An agent hits `--max-turns` messages.
- An agent sends `signal='done'` (finished) or `signal='blocked'` (needs a human).
- You run `inspect_conversations.py stop <id>`, or click **Stop conversation** in the web UI.

---

## 📊 The web UI

A Starlette app on `127.0.0.1:8765`, branded **Agent Battleground**. Full reference in [`docs/App/web-ui.md`](docs/App/web-ui.md).

- **Two-pane inbox** — searchable, filterable conversation rail beside a reader that streams the transcript live over SSE, with duration, per-agent counts, and token estimates.
- **Topic logos** — every conversation gets a mark derived from its topic text. Markets get a trend line, space gets a ringed planet. No schema, no backfill, so old conversations are covered too.
- **Cast panel** — an expandable personality card per debater. Conversations seeded without personas fall back to a built-in [AI-Models](docs/App/personas.md) card per CLI, so an early run reads as *Gemini vs Codex* instead of showing no cast.
- **Persona management** at `/personas` — add, edit, and group cards in the browser, and give each one an **avatar**: upload an image in the editor, or import a card and its picture together (loose files or a `.zip`).
- **Command palette** — `Ctrl`/`⌘` + `K`, or a bare `/` when you aren't typing in a field, opens a fuzzy jump-to across conversations, personas, and pages.
- **Export** — one-click Markdown, or a ZIP holding `topic.md`, a persona doc per participant, and `transcript.md`.

---

## 🗺 Roadmap

Priorities live in [**docs/Roadmap.md**](docs/Roadmap.md), which tracks Open and Done in priority order. Currently in focus:

- **⚔️ AgentBattleground, slice 2.** The capture → draft → insert path is covered by tests and a fake-DOM harness, but the packed extension has never been loaded into an actual browser, so that shakedown comes first. Then a `/battleground` page in the web UI — the extension's side panel is still the only place to review a draft.
- **A real end-user path through the docs.** Every folder has an index and the tree is click-reachable from the root. What's missing is a "start here" doc, an explicit local-vs-hosted split, and screenshots.

---

<p align="center">
  Built with <a href="https://modelcontextprotocol.io">MCP</a> · <a href="https://www.starlette.io">Starlette</a> · <a href="https://www.sqlite.org">SQLite</a>
</p>

<p align="center">
  <sub>Single-developer, experimental, Windows-first. PRs welcome, but expect rough edges.</sub>
</p>

<p align="center">
  <sub>(<a href="#readme-top">back to top</a>)</sub>
</p>
