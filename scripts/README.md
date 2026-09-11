<h1 align="center">🛠️ Scripts</h1>

<p align="center">
  <em>The launchers and operator wrappers — one command to register the MCP server,<br>
  run a debate, sync to Fly, publish a finished transcript, or set the machine up.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Shell-PowerShell_7+-5391FE?style=for-the-badge&labelColor=09090b&logo=powershell&logoColor=white" alt="PowerShell 7+">
  <img src="https://img.shields.io/badge/POSIX-partial-71717a?style=for-the-badge&labelColor=09090b" alt="POSIX partial">
</p>

---

> [!NOTE]
> **Windows-first.** Most wrappers are `.ps1` and require `pwsh` (PowerShell 7+)
> on PATH. Only the MCP launcher and the skill linker ship `.sh` twins today —
> POSIX siblings for the rest are an open Roadmap row.

## 🔌 Wiring (run once per clone)

| Script | What it does |
|:---|:---|
| [**`run-mcp-server.ps1`**](run-mcp-server.ps1) · [`.sh`](run-mcp-server.sh) | **The launcher every CLI registers.** Resolves the venv interpreter and `src/agent_chat_mcp.py` relative to itself; the DB defaults to `<repo>/db/chat.db` (override with `$AGENT_CHAT_DB`). Its own path is the only absolute string left in each MCP config. |
| [**`setup/setup-skill-links.ps1`**](setup/setup-skill-links.ps1) · [`.sh`](setup/setup-skill-links.sh) | Junctions (Windows) or symlinks (POSIX) every folder under [`skills/`](../skills/README.md) into each CLI's config dir, so edits to a `SKILL.md` propagate everywhere. Links are gitignored — re-run per clone. |
| [**`setup/gen_agent_role_docs.py`**](setup/gen_agent_role_docs.py) | Regenerates the five per-seat role docs under [`agents/CLIs/`](../agents/README.md) — the file each CLI reads on startup from its launch folder (`claude.md` / `GEMINI.md` / `AGENTS.md`). They say the same thing with per-CLI details swapped in, so they're generated: edit the template in the script, never the output. Run it after changing a conversation type, a signal, the participation loop, or a CLI's config location. |
| [**`setup/register-startup-task.ps1`**](setup/register-startup-task.ps1) | Registers the `\Agent-Chat\Start-AgentChat-App` logon job in Task Scheduler, bringing the web UI + sidecar up at sign-in. Optional, Windows-only; `-Unregister` removes it. |
| [**`setup/register-app-tasks.ps1`**](setup/register-app-tasks.ps1) | Registers the other four `\Agent-Chat\` jobs — **Stop**, **Restart** (both on demand), **Healthcheck** (hourly, repairs what's down) and **Maintain** (nightly backup + log trim). Leaves the logon task to the script above. `-Unregister` removes the four. |
| [**`run-hidden.vbs`**](run-hidden.vbs) | The windowless launcher every scheduled job above runs its script through. Task Scheduler builds a console app's conhost window before PowerShell can read `-WindowStyle Hidden`, so `pwsh.exe` as a task action flashes a window on the desktop every time it fires; `wscript.exe` has no window and starts the child hidden, while still waiting on it so the exit code reaches the task. Keep it ASCII with no BOM. |

### 🩺 Operating the local app

These are the scripts behind the scheduled jobs. All are safe to run by hand, all are idempotent, and all log to `db/` — start/stop/restart share `db/startup-app.log` so a restart reads as one story.

| Script | What it does |
|:---|:---|
| [**`startup-app.ps1`**](startup-app.ps1) | Bring up the web UI and the sidecar, skipping whatever is already running. |
| [**`stop-app.ps1`**](stop-app.ps1) | Stop both. Matches processes on **this clone's venv python**, so a second clone's app is never touched — and deliberately leaves spawned CLI agent windows alone, since killing one mid-run wedges the conversation on a seat that will never reply. |
| [**`restart-app.ps1`**](restart-app.ps1) | Stop then start. The everyday one: `web_ui.py` runs uvicorn **without** `--reload`, so any change under `src/` needs this. Does not disturb a live conversation — agents reach `chat.db` through their own MCP servers, and the web UI is only a viewer and seeder. |
| [**`healthcheck-app.ps1`**](healthcheck-app.ps1) | HTTP-probe `127.0.0.1:8765` and check the sidecar process; restart what's down. Probes with a real request rather than a process check, because uvicorn can be running and still not serving. `-Repair:$false` makes it report-only. **Also reports stalled conversations** (`inspect_conversations watch`) — riding this schedule instead of a sixth task, never counted as an app problem, and never restarting an agent. `-SkipConversations` turns that half off. |
| [**`maintain-app.ps1`**](maintain-app.ps1) | Nightly: back up `db/chat.db` via SQLite's **backup API** (a file copy of a live WAL database is torn, and copying without the `-wal` file loses committed rows), prune backups older than 14 days, trim `db/*.log`. |


## ▶️ Running a debate

| Script | What it does |
|:---|:---|
| [**`debate.ps1`**](debate.ps1) | **One-command auto-debate.** Picks a topic, casts personas from the registry, seeds, and spawns one CLI per persona in character. Flags: topic, persona group, agent count, exact CLI set, forced cast, `-DryRun`. → [guide](../docs/Guides/auto-debate.md) |
| [**`start.ps1`**](start.ps1) | Ensures the sync sidecar is up, then forwards its args to `start_conversation.py`. The manual-seed daily driver. → [guide](../docs/Guides/start-new-chat.md) |
| [**`orchestrate-debate.ps1`**](orchestrate-debate.ps1) | The web-form spawn wrapper: `POST /api/orchestrate`, then spawn CLIs for the conversation it seeded. → [guide](../docs/Guides/orchestrate-form.md) |
| [**`lib/spawn-agents.ps1`**](lib/spawn-agents.ps1) | Shared CLI registry + prompt-file and spawn helpers. Dot-sourced by both `debate.ps1` and `orchestrate-debate.ps1` — **the one place to add a new CLI's spawn command.** |

## 🛰️ Running the app

| Script | What it does |
|:---|:---|
| [**`startup-app.ps1`**](startup-app.ps1) | Logon launcher — brings the web UI and sidecar up hidden. Idempotent, so it's safe to re-run. |
| [**`db_sync.py`**](db_sync.py) | Optional sidecar that mirrors the local DB to a self-hosted read-only viewer. Pushes local deltas (`POST /api/ingest`) and pulls remote state (`GET /api/since`) every 5s. Deliberately does **not** carry battleground tables. Not needed to run a debate. `--force-push` rewinds the push watermarks for one run and re-ships everything — the repair path when the mirror has drifted. |

## 📤 After a debate

| Script | What it does |
|:---|:---|
| [**`publish_debate.py`**](publish_debate.py) | Publishes a finished debate into the AI-Automation-Library archive — bundles straight from `chat.db` through `orchestrator.export`, no ZIP round-trip. Paired with the [`publish-debate`](../skills/publish-debate/SKILL.md) skill. |

## ⚔️ Extension

| Script | What it does |
|:---|:---|
| [**`build-extension.ps1`**](build-extension.ps1) | Stages the Firefox build into `extension/dist/firefox/` (gitignored) — the same `src/` and `icons/` with the Gecko manifest dropped in as `manifest.json`. Chrome needs no build step. |

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../docs/Guides/README.md`](../docs/Guides/README.md) | The operator guides these scripts implement. |
| [`../docs/CLI-MCP-Config/README.md`](../docs/CLI-MCP-Config/README.md) | Where `run-mcp-server.ps1` gets referenced per CLI. |
| [`../src/README.md`](../src/README.md) | The Python modules these wrappers call. |
| [`../prompts/README.md`](../prompts/README.md) | Paste-ready prompts that trigger these scripts through a skill. |

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../docs/Guides/README.md">Guides</a></sub>
</p>
