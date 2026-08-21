<a id="readme-top"></a>

<p align="center">
  <a href="https://agent-chat.mikesailab.com">
    <img src="images/AgentChat-Images/logos/dark/landscape-03-signal-loop.svg" alt="Agent-Chat" width="720">
  </a>
</p>

<h1 align="center">Agent-Chat</h1>

<p align="center">
  <em>A local MCP conversation bus for CLI agents. Put them in a debate or a podcast<br>
  in character, or send one into a real web thread to draft your reply.</em>
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
  <img src="https://img.shields.io/badge/CLIs-Claude_|_Codex_|_Antigravity_|_OpenCode-10b981?style=flat-square" alt="Supported CLI agents">
</p>

<p align="center">
  <a href="#-what-it-does">What it does</a> ·
  <a href="#-three-ways-to-run-a-conversation">Three ways to run one</a> ·
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-operator-workflows">Workflows</a> ·
  <a href="#-companion-sites">Companion sites</a> ·
  <a href="#-documentation-map">Docs</a>
</p>

---

## 💡 What it does

Agent-Chat lets two or more coding agents talk to each other through the same local SQLite-WAL file. Each CLI registers the same FastMCP server with a different `--agent-id`; the server handles turn order, message caps, stop signals, personas, and exportable transcripts.

<p align="center">
  <img src="images/AgentChat-Images/readme-screenshots/topic39.png" alt="A finished Agent-Chat debate showing the live transcript, per-agent message counts, and the cast panel naming each persona" width="880">
</p>

## 🎭 Three ways to run a conversation

The first two put your own CLI agents in a room together, in character. The third sends one of them into a thread real people are already arguing in.

| Format | What happens | Who's talking | Start here |
|:---|:---|:---|:---|
| [**🥊 Debate**](docs/Guides/README.md) | Two to five agents argue a topic in persona. Add a moderator and it opens the debate, chases dodged questions, and wraps up without taking a side. | Your CLI agents | [Auto-debate](docs/Guides/auto-debate.md) · [manual seed](docs/Guides/start-new-chat.md) · [web form](docs/Guides/orchestrate-form.md) |
| [**🎙️ Podcast**](docs/Guides/README.md) | A host interviews one to four guests. The host asks and never answers its own questions; the guests answer at length and don't run the show. | Your CLI agents | [Manual seed](docs/Guides/start-new-chat.md) (`--type podcast`) · [web form](docs/Guides/orchestrate-form.md) |
| [**⚔️ Web thread**](docs/Guides/battleground.md) | The extension captures a real comment thread. An agent reads it, argues your side in persona, and drafts a reply. You approve it, and only then does the text reach the page. | One of your agents, against real people | [AgentBattleground guide](docs/Guides/battleground.md) · [extension](extension/README.md) |

**Debate and podcast are the same machinery.** They're two values of a conversation's `conv_type` column — same message bus, same turn engine, same personas. What differs is who each seat is for: a debate has debaters and an optional moderator, a podcast has a host and guests. Adding a third format is an entry in [`conv_types.py`](src/orchestrator/conv_types.py) and a prompt shape, not a new subsystem — the web form, the filters, and the export pick it up on their own.

**The web thread is a different arena.** The opponent is a real person, which is why one rule sits above every other feature in it: **an agent drafts, a human posts.** Nothing in the server or the extension can submit to a website.

| Around all three | What you get |
|:---|:---|
| **Live watching** | A local Starlette UI streams new messages over SSE while the agents work. |
| **Personas** | A DB-backed registry of character cards with avatars, shared by every format. |
| **Publishing** | Markdown and ZIP exports through one shared contract, then into the library workflow. |

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

Open `http://127.0.0.1:8765/` and go to **`/setup`** first. It probes each supported CLI — is its launcher on your `PATH`, is its MCP config valid — and you tick the ones you actually have. Everything after that offers only those.

Then either seed from the browser at `/orchestrate` or start an automatic debate:

```powershell
.\scripts\debate.ps1
```

> [!TIP]
> **You only need one CLI.** A participant seat is configuration, not a separate program, so a single Claude Code install can hold both chairs: `claude-code` against `claude-code-2`, two personas, one debate. `/setup` will create the extra seat for you. Two CLIs is the more usual shape — one persona each — and that's what you get by default. See [CLI setup](docs/App/cli-setup.md).

> [!NOTE]
> On macOS/Linux, use the `.sh` MCP launcher and `.venv/bin/python` equivalents where needed. The rest of the operator wrappers are Windows-first today.

## 🎬 Operator workflows

Format and launcher are separate choices. The three rows below are ways to *start* an agent-vs-agent run; each one seeds through the same `seed_conversation()`. The fourth is the web-thread arena, which has its own entry point.

| Workflow | Best for | Formats | Start here |
|:---|:---|:---|:---|
| **Auto-debate** | Hands-off. One command picks the topic and cast, seeds, and spawns the CLIs in character. | Debate | [`scripts\debate.ps1`](scripts/debate.ps1) · [guide](docs/Guides/auto-debate.md) |
| **Manual seed** | Full control over topic, cast, seats, and launch order. The daily driver. | Debate · Podcast | [`scripts\start.ps1`](scripts/start.ps1) · [guide](docs/Guides/start-new-chat.md) |
| **Web form** | Clicking rather than typing. Pick the format at the top; per-seat preflight badges tell you what's wired. | Debate · Podcast | `GET /orchestrate` · [guide](docs/Guides/orchestrate-form.md) |
| **AgentBattleground** | Answering a real thread on a real site, with a human approving every reply. | Web thread | [extension](extension/README.md) · [guide](docs/Guides/battleground.md) |

> [!NOTE]
> Podcasts don't have a one-command launcher yet — `debate.ps1` only seeds debates. Use the web form or `start_conversation.py --type podcast --host <agent>`. It's tracked on the [roadmap](docs/Roadmap.md).

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
| **OpenCode CLI** | `opencode.json` | [`docs/CLI-MCP-Config/Per-CLI/opencode.md`](docs/CLI-MCP-Config/Per-CLI/opencode.md) |
| **Gemini CLI** *(deprecated fallback)* | `.gemini/settings.json` | [`docs/CLI-MCP-Config/Per-CLI/gemini.md`](docs/CLI-MCP-Config/Per-CLI/gemini.md) |

</details>

## 🖥️ Web UI

The app is branded **Agent Battleground** in-browser and runs locally at `http://127.0.0.1:8765/`.

| Surface | What it shows |
|:---|:---|
| **Home** | Recent and featured runs, stats, project links, and launch paths. |
| **Conversations** | Searchable two-pane inbox, live transcript, turn badge, message counts, token estimates. Filter chips split the archive by format. |
| **Personas** | DB-backed persona registry with groups, edit/import flows, and uploaded avatars. |
| **Orchestrate** | Local-only conversation seed form, offering only seats on the CLIs you have. |
| **CLI setup** | Which CLI tools this machine has — detected, then confirmed by you. Creates extra seats when one tool is doing the work of two. |
| **Browser extension** | What AgentBattleground is, how to install it, and the draft-never-post rule. |
| **Battleground** | Local arena console: every thread the extension captured, its drafts, and approve/reject — without the original tab open. Never inserts into a page; that still needs the extension. |
| **Exports** | Markdown and ZIP bundles rendered through the shared export contract. |
| **Battleground bridge** | Narrow CORS API used by the browser extension; drafts only, never posts. |

The hosted mirror at [agent-chat.mikesailab.com](https://agent-chat.mikesailab.com) runs the same app in read-only mode: it shows real conversations and says so on every page, but nothing there can be changed or launched.

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
| [**Guides**](docs/Guides/README.md) | The three conversation formats and the launchers that start them. |
| [**App reference**](docs/App/README.md) | Web UI, [CLI setup](docs/App/cli-setup.md), personas, kickoff prompts, export format, and internals. |
| [**CLI MCP config**](docs/CLI-MCP-Config/README.md) | Project-vs-global MCP registration and per-CLI setup. |
| [**Source**](src/README.md) | Entrypoints, packages, and invariants to preserve while coding. |
| [**Scripts**](scripts/README.md) | Operator wrappers, sidecar sync, setup helpers, and publisher. |
| [**Skills**](skills/README.md) | Runtime skills read by participating CLI agents. |
| [**Tests**](tests/README.md) | Ten standalone-runnable suites plus known coverage gaps. |
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

Current priorities live in [`docs/Roadmap.md`](docs/Roadmap.md). Near-term work is focused on browser-shaking AgentBattleground (the `/battleground` operator page shipped 2026-08-20), improving the end-user docs path, expanding tests, and centralizing duplicated schema/migration declarations.

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
