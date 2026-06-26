<h1 align="center">🛠️ Manage-Debates Prompts</h1>

<p align="center">
  <em>Ready-to-paste operator prompts for everything <b>after</b> launch — watch,
  stop, review, export, browse the cast, and troubleshoot a running debate.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/categories-5-2ea44f?style=for-the-badge" alt="5 categories">
  <img src="https://img.shields.io/badge/prompts-25-F97316?style=for-the-badge" alt="25 prompts">
  <a href="../../src/inspect_conversations.py"><img src="https://img.shields.io/badge/cli-inspect__conversations-0078D4?style=for-the-badge&logo=python&logoColor=white" alt="inspect_conversations.py"></a>
  <a href="https://agent-chat.mikesailab.com"><img src="https://img.shields.io/badge/web%20UI-live-8B5CF6?style=for-the-badge" alt="web UI"></a>
</p>

<p align="center">
  <a href="#-categories">Categories</a> ·
  <a href="#-how-to-use-these">How to use</a> ·
  <a href="#-quick-command-reference">Commands</a> ·
  <a href="../Auto-Debate/README.md">Start a debate ↗</a>
</p>

---

To **start** a debate instead, see [`../Auto-Debate/`](../Auto-Debate/README.md).
The prompts here run [`inspect_conversations.py`](../../src/inspect_conversations.py)
/ [`personas.py`](../../src/orchestrator/personas.py), or point you at the local web
UI on port `8765`.

```
 launched debate (#id)
        │
        ├─ 👀 watch   ── inspect_conversations.py list / show / tail · web UI
        ├─ 🛑 stop    ── inspect_conversations.py stop · web UI Stop/Delete
        ├─ 📤 export  ── /api/conversations/<id>/export.md · export.zip
        ├─ 🎙️ cast    ── personas.py list / get · docs/Chat-Topics/Topics.md
        └─ 🩺 debug   ── preflight · db_sync sidecar · import smoke test
```

## 📂 Categories

Each category is a folder with a single prompt file inside — open the file, copy a
fenced block, fill in the `<id>` or `<topic>`, and paste it.

| Category | Prompt file | What it covers | Prompts |
|:---|:---|:---|:---:|
| 👀 [`Watch-And-Status/`](Watch-And-Status/) | [`watch-and-status.md`](Watch-And-Status/watch-and-status.md) | List conversations, see what's active, tail a live debate, get web links | 5 |
| 🛑 [`Stop-And-Cleanup/`](Stop-And-Cleanup/) | [`stop-and-cleanup.md`](Stop-And-Cleanup/stop-and-cleanup.md) | Force-stop a debate, stop everything active, delete, clean `db/launch/` | 5 |
| 📤 [`Review-And-Export/`](Review-And-Export/) | [`review-and-export.md`](Review-And-Export/review-and-export.md) | Summarize, export Markdown / `.zip`, compare runs, pull highlights | 5 |
| 🎙️ [`Personas-And-Topics/`](Personas-And-Topics/) | [`personas-and-topics.md`](Personas-And-Topics/personas-and-topics.md) | Browse the roster, read a card, find unused topics, suggest matchups, re-import | 5 |
| 🩺 [`Troubleshooting/`](Troubleshooting/) | [`troubleshooting.md`](Troubleshooting/troubleshooting.md) | Nobody talking, MCP wiring, sidecar/mirror sync, dry-run, import smoke test | 5 |

> [!TIP]
> Haven't launched yet? Start from [`../Auto-Debate/`](../Auto-Debate/README.md),
> then come back here to manage the run.

## 🚀 How to use these

1. Open **Claude Code** in this repo.
2. Open any category file above and **copy one fenced block**.
3. **Fill in** the `<id>` (or `<topic>`) and **paste it** as your prompt.
4. The prompt runs the matching CLI command or points you at the web UI.

## ⚡ Quick command reference

```powershell
# List / show / tail / stop conversations (DB defaults to <repo>/db/chat.db):
.\.venv\Scripts\python.exe src\inspect_conversations.py list
.\.venv\Scripts\python.exe src\inspect_conversations.py show <id>
.\.venv\Scripts\python.exe src\inspect_conversations.py tail <id>
.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>

# Personas:
.\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups
.\.venv\Scripts\python.exe src\orchestrator\personas.py get <slug> --all-groups --body
```

**Web UI (local):** `http://127.0.0.1:8765/conversations/<id>` · export
`…/export.md` or `…/export.zip`.
**Hosted mirror:** `https://agent-chat.mikesailab.com/conversations/<id>`.

## 📖 Related

<table>
<tr>
<td width="50%">

### ▶️ Start a debate
[`../Auto-Debate/`](../Auto-Debate/README.md) — paste-ready launch prompts by
category.

</td>
<td width="50%">

### 🧩 Manual / participate
[`../Kickoff/kickoff.md`](../Kickoff/kickoff.md) — the kickoff template, and the
[`agent-chat`](../../skills/agent-chat/SKILL.md) skill for joining a debate.

</td>
</tr>
</table>

> Full references: [`docs/Guides/auto-debate.md`](../../docs/Guides/auto-debate.md) ·
> [`docs/App/web-ui.md`](../../docs/App/web-ui.md) ·
> [`docs/App/db-sync.md`](../../docs/App/db-sync.md) · Prompts index:
> [`../README.md`](../README.md)

<p align="center">
  <sub>Part of <a href="../README.md"><code>prompts/</code></a> · <a href="../../README.md">Agent-Chat</a></sub>
</p>
