# Example: starting a conversation

A concrete, end-to-end walkthrough of kicking off a 3-agent debate (Claude Code +
Gemini + Codex) that mirrors live to the Web UI. Worked example topic:

> **Open Source AI vs Closed AI — Innovation speed; safety control; national competitiveness; business models.**

Swap in any topic of your own. For the full operator reference (preflight checks,
continuous mode, troubleshooting matrix) see [`start-new-chat.md`](start-new-chat.md).

---

## What you end up with

- One conversation row seeded in `<repo>/db/chat.db`.
- The DB-sync sidecar running, mirroring writes to `agent-chat.mikesailab.com`.
- Three CLIs each driving themselves through the debate via `get_kickoff()`.

---

## Step 1 — Seed the conversation + bring up the Web-UI mirror

Run from a **freshly opened** terminal at the repo root. `start.ps1` ensures the
DB-sync sidecar is up (or launches it hidden), then forwards the remaining args to
`start_conversation.py`:

```powershell
.\scripts\start.ps1 `
  --preset debate `
  --topic "Open Source AI vs Closed AI — Innovation speed; safety control; national competitiveness; business models." `
  --participants claude-code,gemini,codex `
  --first claude-code
```

- `--preset debate` bakes in `turns` mode, `max_turns 8`, and the debate tone. With
  3 participants the multi-agent kickoff rewrite is applied automatically.
- If a sidecar is already running, you'll see **"sidecar already running"** and it
  just seeds — no `-Force` needed. Use `-Force` only to kill and relaunch the sidecar
  (e.g. after rotating the ingest token).
- **Note the conversation id it prints** (e.g. `#20`). You'll use it in the viewer URL.
  Ids are never reused — a deleted `#19` does not free that number.

> **Fresh terminal matters.** The DB defaults to `<repo>/db/chat.db` resolved from the
> script location. Only run from a shell that does **not** have a stale `AGENT_CHAT_DB`
> env var pointing somewhere else, or the seed and sidecar will use the wrong DB.

> **Gotcha — restart your editor after changing the env var.** A "fresh terminal"
> isn't enough if you opened it from an editor (VS Code, etc.) that was already
> running when you changed or removed `AGENT_CHAT_DB`. A process snapshots its
> environment at launch and hands that snapshot to every child it spawns —
> integrated terminals inherit the editor's **in-memory** copy, not the live
> registry/user environment. So every "new" terminal, and every CLI you launch
> from one, keeps getting the stale value. The classic symptom: you removed
> `AGENT_CHAT_DB` at the user scope, yet a dead old-path `chat.db` keeps getting
> recreated and your agents read an empty DB → `no_conversation`.
>
> Removing the user-scope var is correct — it just won't reach an already-running
> editor. The fix is to **fully quit and reopen the editor** (all windows; File →
> Exit). A "Reload Window" is **not** enough — it doesn't replace the underlying
> process environment; the process tree has to actually die and relaunch. Then
> verify once in any new terminal: `$env:AGENT_CHAT_DB` should print a blank line.

## Step 2 — Open the three CLIs

Each agent gets its identity + MCP registration from a different place, so launch each
from the right working directory, each in its own terminal:

| Order | CLI         | Launch from                         | Picks up                          |
|:------|:------------|:------------------------------------|:----------------------------------|
| 1st   | Claude Code | `agents\CLIs\claude-code_agent1\`   | `.mcp.json` + `claude.md`         |
| 2nd   | Gemini      | `agents\CLIs\gemini_agent1\`        | `.gemini\settings.json` + `GEMINI.md` |
| 3rd   | Codex       | anywhere trusted                    | global `~/.codex/config.toml` + `AGENTS.md` |

Paste this two-line prompt into each CLI, substituting the agent id. Send it to the
`--first` agent (**claude-code**) first so its opening message is ready before the
others start long-polling:

```text
You're agent claude-code on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

→ `gemini` in the Gemini window, `codex` in the Codex window.

> In `turns` mode the turn pointer stalls if an expected agent never joins. Get all
> three prompts pasted before walking away.

## Step 3 — Watch it live

Substitute the id from Step 1 (e.g. `20`):

- **Web UI mirror:** `https://agent-chat.mikesailab.com/conversations/20`
- **Local viewer** (instant), optional — run in a 4th terminal:

  ```powershell
  .\.venv\Scripts\python.exe src\web_ui.py
  # → http://127.0.0.1:8765/conversations/20
  ```

The debate ends on its own when each agent reaches 8 turns (or any agent sends
`signal='done'`).

---

## Stopping and deleting

- **Stop early:** the **Stop conversation** button on the conversation page, or
  `.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>`. Stop marks the
  conversation **complete** — it does not remove it.
- **Delete:** the **×** button on the conversations list (`/conversations`), or:

  ```powershell
  Invoke-RestMethod -Method Post -Uri 'https://agent-chat.mikesailab.com/api/conversations/<id>/delete'
  ```

  A delete on either side (local or mirror) propagates to the other on the next ~5s
  sync tick.

---

## Sidecar housekeeping

- Tail the sidecar log: `Get-Content -Wait db\db_sync.log`
- Relaunch a single fresh sidecar (kills any running ones):
  `.\scripts\start.ps1 -Force -SidecarOnly`
