# Manage-Debates sample prompts

Ready-to-paste **operator prompts** for *running* debates — everything after you've
launched one: watching, stopping, reviewing/exporting, browsing the cast, and
troubleshooting. (To *start* a debate, see [`../Auto-Debate/`](../Auto-Debate/README.md).)

## How to use these

Open Claude Code in this repo, copy a block from any file below, fill in the `<id>`
or `<topic>`, and paste it. The prompts run `src/inspect_conversations.py` /
`src/orchestrator/personas.py` or point you at the local web UI on port 8765.

## Categories

| Folder | What it covers |
|---|---|
| [`Watch-And-Status/`](Watch-And-Status/watch-and-status.md) | List conversations, see what's active, tail a live debate, get web links |
| [`Stop-And-Cleanup/`](Stop-And-Cleanup/stop-and-cleanup.md) | Force-stop a debate, stop everything active, delete, clean `db/launch/` |
| [`Review-And-Export/`](Review-And-Export/review-and-export.md) | Summarize, export Markdown / `.zip`, compare runs, pull highlights |
| [`Personas-And-Topics/`](Personas-And-Topics/personas-and-topics.md) | Browse the roster, read a card, find unused topics, suggest matchups, re-import |
| [`Troubleshooting/`](Troubleshooting/troubleshooting.md) | Nobody talking, MCP wiring, sidecar/mirror sync, dry-run, import smoke test |

## Quick command reference

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

Web UI (local): `http://127.0.0.1:8765/conversations/<id>` · export `…/export.md`
or `…/export.zip`. Hosted mirror: `https://agent-chat.mikesailab.com/conversations/<id>`.

> Full references: [`docs/Guides/auto-debate.md`](../../docs/Guides/auto-debate.md) ·
> [`docs/App/web-ui.md`](../../docs/App/web-ui.md) ·
> [`docs/App/db-sync.md`](../../docs/App/db-sync.md).
