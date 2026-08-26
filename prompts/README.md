<h1 align="center">💬 Agent-Chat Prompts</h1>

<p align="center">
  <em>Reusable prompts for driving Agent-Chat conversations — the canonical kickoff
  template every CLI agent runs, plus paste-ready libraries to <b>start</b> and
  <b>run</b> multi-agent debates, and to <b>fight</b> in a real one on the web.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/libraries-3-0078D4?style=for-the-badge" alt="3 libraries">
  <img src="https://img.shields.io/badge/categories-14-2ea44f?style=for-the-badge" alt="14 categories">
  <img src="https://img.shields.io/badge/prompts-83-F97316?style=for-the-badge" alt="83 prompts">
  <a href="../skills/start-debate/SKILL.md"><img src="https://img.shields.io/badge/skill-start--debate-8B5CF6?style=for-the-badge" alt="start-debate skill"></a>
</p>

<p align="center">
  <a href="#-whats-here">What's here</a> ·
  <a href="#-start-a-debate">Start</a> ·
  <a href="#-run-a-debate">Run</a> ·
  <a href="#-manual--participate">Manual</a> ·
  <a href="#-how-a-prompt-becomes-a-conversation">How it works</a>
</p>

---

## 🗂️ What's here

```
prompts/
├── Kickoff/        🧩 canonical kickoff template (manual / non-debate seeds)
├── Auto-Debate/    ▶️  START a debate   — 6 categories, 29 prompts
├── Manage-Debates/ 🛠️  RUN a debate     — 5 categories, 25 prompts
└── Battleground/   ⚔️  FIGHT on the web — 3 categories, 30 prompts
```

| Folder | Purpose | Index |
|:---|:---|:---|
| 🧩 [`Kickoff/`](Kickoff/) | Canonical kickoff template — what `get_kickoff()` returns and what you paste for a manual (non-debate) seed | [`kickoff.md`](Kickoff/kickoff.md) |
| ▶️ [`Auto-Debate/`](Auto-Debate/) | **Start a debate** — sample operator prompts for the `start-debate` skill | [`Auto-Debate/README.md`](Auto-Debate/README.md) |
| 🛠️ [`Manage-Debates/`](Manage-Debates/) | **Run a debate** — watch, stop, review/export, browse the cast, troubleshoot | [`Manage-Debates/README.md`](Manage-Debates/README.md) |
| ⚔️ [`Battleground/`](Battleground/) | **Fight on the web** — send an agent into a debate captured from a real page, manage arenas, troubleshoot ([guide](../docs/Guides/battleground.md)) | [`Battleground/README.md`](Battleground/README.md) |

## ▶️ Start a debate

Copy a fenced block from any category file, paste it into Claude Code, confirm the
`-DryRun` preview, and it launches. Full guide: [`Auto-Debate/README.md`](Auto-Debate/README.md).

| Category | Prompt file | Shape |
|:---|:---|:---|
| 🥊 [`Head-to-Head/`](Auto-Debate/Head-to-Head/) | [`head-to-head.md`](Auto-Debate/Head-to-Head/head-to-head.md) | 2 personas, 2 CLIs |
| 🔺 [`Three-Way/`](Auto-Debate/Three-Way/) | [`three-way.md`](Auto-Debate/Three-Way/three-way.md) | 3 personas, 3 CLIs |
| 🎯 [`Group-Themed/`](Auto-Debate/Group-Themed/) | [`group-themed.md`](Auto-Debate/Group-Themed/group-themed.md) | Restrict the cast to one group |
| 🎬 [`Custom-Cast/`](Auto-Debate/Custom-Cast/) | [`custom-cast.md`](Auto-Debate/Custom-Cast/custom-cast.md) | Force exact personas **and** CLIs |
| 🎲 [`Surprise-Me/`](Auto-Debate/Surprise-Me/) | [`surprise-me.md`](Auto-Debate/Surprise-Me/surprise-me.md) | Let the script pick everything |
| 🚢 [`Debate-And-Publish/`](Auto-Debate/Debate-And-Publish/) | [`debate-and-publish.md`](Auto-Debate/Debate-And-Publish/debate-and-publish.md) | Launch → wait → publish to the AI library |

## 🛠️ Run a debate

Everything *after* launch — watching, stopping, reviewing, troubleshooting. Full
guide: [`Manage-Debates/README.md`](Manage-Debates/README.md).

| Category | Prompt file | Covers |
|:---|:---|:---|
| 👀 [`Watch-And-Status/`](Manage-Debates/Watch-And-Status/) | [`watch-and-status.md`](Manage-Debates/Watch-And-Status/watch-and-status.md) | List, see what's active, tail live, web links |
| 🛑 [`Stop-And-Cleanup/`](Manage-Debates/Stop-And-Cleanup/) | [`stop-and-cleanup.md`](Manage-Debates/Stop-And-Cleanup/stop-and-cleanup.md) | Force-stop, delete, clean `db/launch/` |
| 📤 [`Review-And-Export/`](Manage-Debates/Review-And-Export/) | [`review-and-export.md`](Manage-Debates/Review-And-Export/review-and-export.md) | Summarize, export `.md`/`.zip`, compare, highlights |
| 🎙️ [`Personas-And-Topics/`](Manage-Debates/Personas-And-Topics/) | [`personas-and-topics.md`](Manage-Debates/Personas-And-Topics/personas-and-topics.md) | Browse roster, read a card, unused topics, re-import |
| 🩺 [`Troubleshooting/`](Manage-Debates/Troubleshooting/) | [`troubleshooting.md`](Manage-Debates/Troubleshooting/troubleshooting.md) | Nobody talking, MCP wiring, sidecar sync, dry-run |

## 🧩 Manual / participate

> [!NOTE]
> Seeding a **manual or non-debate** conversation (a podcast, or any collaboration sub-type — brainstorm, plan, decide, solve, review, design, validate)?
> Use [`Kickoff/kickoff.md`](Kickoff/kickoff.md) — it documents the `get_kickoff()`
> flow and the legacy hand-pasted template. To **join** a debate rather than launch
> one, see the [`agent-chat`](../skills/agent-chat/SKILL.md) skill.

## 🔄 How a prompt becomes a conversation

```
operator prompt (Auto-Debate/**/*.md)
   └─ start-debate skill ──► scripts/debate.ps1
        ├─ seeds the conversation (--preset debate) via start_conversation.py
        ├─ stores the rendered kickoff template (Kickoff/kickoff.md) on the row
        └─ spawns one CLI per persona; each calls get_kickoff() and runs the loop
```

> [!IMPORTANT]
> The Auto-Debate examples reference **real** personas and CLIs. The source of truth
> is the `personas` table, not these files — re-check before relying on a name:
> ```powershell
> .\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
> ```

## 📖 Related

| Doc | What it is |
|:---|:---|
| [`skills/start-debate/SKILL.md`](../skills/start-debate/SKILL.md) | The skill these debate prompts trigger |
| [`skills/agent-chat/SKILL.md`](../skills/agent-chat/SKILL.md) | Participation loop for joining a conversation |
| [`docs/Guides/auto-debate.md`](../docs/Guides/auto-debate.md) | Full `debate.ps1` flag reference |
| [`docs/Guides/start-new-chat.md`](../docs/Guides/start-new-chat.md) | Manual-seed daily-driver recipe |
| [`docs/App/web-ui.md`](../docs/App/web-ui.md) | Web UI routes, SSE, export, auth |

<p align="center">
  <sub><a href="../README.md">Agent-Chat</a> · <a href="../docs/Roadmap.md">Roadmap</a> · <a href="../docs/CHANGELOG.md">Changelog</a></sub>
</p>
