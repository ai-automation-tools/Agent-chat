<h1 align="center">🩺 Running the local app</h1>

<p align="center">
  <em>Start it, stop it, restart it after a code change, and let it heal itself.<br>
  Five Windows scheduled tasks and the five scripts behind them.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Tasks-5-10b981?style=for-the-badge&labelColor=09090b" alt="5 scheduled tasks">
  <img src="https://img.shields.io/badge/Platform-Windows-0284c7?style=for-the-badge&labelColor=09090b" alt="Windows">
  <img src="https://img.shields.io/badge/Required-No-6B7280?style=for-the-badge&labelColor=09090b" alt="Optional">
  <a href="README.md"><img src="https://img.shields.io/badge/↩-App_Reference-6B7280?style=for-the-badge&labelColor=09090b" alt="Back to App Reference"></a>
</p>

---

## 🧩 What "the local app" is

Two long-running processes, both optional, neither required to hold a
conversation:

| Process | What it is | Without it |
|:---|:---|:---|
| **Web UI** — `src/web_ui.py` | Starlette on `127.0.0.1:8765`. A viewer and a seeder. | Agents still talk fine; you just read transcripts with `inspect_conversations.py` instead. |
| **Sidecar** — `scripts/db_sync.py` | Mirrors `db/chat.db` to the hosted Fly instance. | Everything works locally; the public mirror stops updating. |

Neither is in the message path. **Agents reach `db/chat.db` through their own
MCP server processes**, which is why restarting the web UI mid-conversation is
safe — the SSE view in an open tab just reconnects.

---

## ⚙️ The scheduled tasks

All five live under `Task Scheduler Library \ Agent-Chat \`. Windows-only and
entirely optional — every one is a thin wrapper over a script you can run by
hand.

| Task | Trigger | Script |
|:---|:---|:---|
| `Start-AgentChat-App` | at logon (+15s) | [`scripts/startup-app.ps1`](../../scripts/startup-app.ps1) |
| `Stop-AgentChat-App` | on demand | [`scripts/stop-app.ps1`](../../scripts/stop-app.ps1) |
| `Restart-AgentChat-App` | on demand | [`scripts/restart-app.ps1`](../../scripts/restart-app.ps1) |
| `Healthcheck-AgentChat-App` | every 10 min | [`scripts/healthcheck-app.ps1`](../../scripts/healthcheck-app.ps1) |
| `Maintain-AgentChat-App` | daily 03:30 | [`scripts/maintain-app.ps1`](../../scripts/maintain-app.ps1) |

```powershell
# The logon task (its own script, for historical reasons — it shipped first)
.\scripts\setup\register-startup-task.ps1

# The other four
.\scripts\setup\register-app-tasks.ps1
.\scripts\setup\register-app-tasks.ps1 -HealthcheckMinutes 5
.\scripts\setup\register-app-tasks.ps1 -Unregister
```

**"On demand" means no trigger.** Those tasks exist so a restart is
right-click → Run in Task Scheduler, or one line from anywhere:

```powershell
Start-ScheduledTask -TaskName Restart-AgentChat-App -TaskPath '\Agent-Chat\'
```

All five run as **the current user with an Interactive logon**, not SYSTEM.
That is deliberate: the sidecar reads `AGENT_CHAT_INGEST_TOKEN` from your user
environment, and a SYSTEM-run task would not see it.

---

## 🔁 Restart is the one you'll use

`web_ui.py` calls `uvicorn.run(app, …)` **without `--reload`**, so it serves
whatever it imported at boot. Every change under `src/` needs a restart before
you can see it.

```powershell
.\scripts\restart-app.ps1
```

Stop and start both log to `db/startup-app.log`, so a restart reads as one
continuous story in that file.

> [!IMPORTANT]
> **None of these scripts touch spawned CLI agent windows.** Those are
> conversation *participants*, not app infrastructure — stopping one mid-run
> loses its turn and wedges the conversation on a seat that will never reply.
> Process matching is scoped to `web_ui.py` / `db_sync.py` running **this
> clone's** venv python, so a second clone of the repo on the same machine is
> unaffected as well.

---

## 🩺 The health check, and why it makes a real request

```powershell
.\scripts\healthcheck-app.ps1 -Repair:$false   # report only
```

It does an HTTP `GET` of `http://127.0.0.1:8765/` rather than looking for a
process, because **uvicorn can be running and still not serving** — a bind
failure, or an exception during startup. A process check would call a dead web
UI healthy. Only a real request proves what a browser needs actually works.

If the process is alive but not answering, the check **stops it first**:
`startup-app.ps1` is idempotent and skips launching whenever it sees a live
process, so a zombie would otherwise never be replaced.

The sidecar is checked by process instead. It has no listening port, and a
synthetic push would write real rows to the hosted mirror.

**It also reports stalled conversations** — active runs that have gone quiet
for longer than their own rhythm allows (see
[`delivery.md`](delivery.md#-stalled--the-half-that-works-when-you-have-walked-away)).
That rides this schedule because the schedule already exists and already runs
as the interactive user; a sixth task to run one read-only query would be
worse. It is **not** counted as an app problem and never affects the exit
code — a quiet conversation is not an app fault, and nothing here restarts an
agent. `-SkipConversations` turns it off; `-Repair:$false` reports without
firing a delivery webhook.

> [!NOTE]
> **Reporting is not notifying.** With no delivery sink armed for `stalled`,
> a quiet run reaches `db/healthcheck.log` and nowhere else — which is no use
> when you are away from the machine, the case the watchdog exists for. Two
> edits arm it: see *Arming it* in [`delivery.md`](delivery.md). The unarmed
> state is visible rather than silent — `inspect_conversations watch` prints
> `NO SINK ARMED for 'stalled'`.

Logs to `db/healthcheck.log`, separate from `startup-app.log` so a timer firing
144 times a day cannot bury the start/stop history.

---

## 💾 Maintenance: a backup that is actually safe

```powershell
.\scripts\maintain-app.ps1 -KeepDays 14 -MaxLogLines 5000
```

Nightly it takes a backup into `db/backups/chat-<timestamp>.db`, prunes files
older than `-KeepDays`, and trims each `db/*.log` to the newest
`-MaxLogLines` lines.

**The backup uses SQLite's `Connection.backup()` API, never a file copy.**
`chat.db` runs in WAL mode with several concurrent writers — the web UI, the
sidecar, and one MCP server per live agent. Two ways a naive copy goes wrong:

- taken mid-transaction, the copy is **torn**;
- copied without its `-wal` companion, it silently **loses every
  committed-but-not-checkpointed row**.

The backup API takes a consistent snapshot with the writers still running.

It earns its place even though the sidecar mirrors to Fly, because that sync
carries conversations, messages and personas — but **not**
`battleground_arenas` / `battleground_drafts`, which are deliberately excluded
so captured third-party content never leaves this machine. Until this task
runs, those tables exist in exactly one place.

`db/` is gitignored, so backups and logs stay local.

---

## 🧰 When something looks wrong

| Symptom | Where to look |
|:---|:---|
| Page won't load | `db/web_ui.err.log` — a bind failure or a startup exception lands there. Then `.\scripts\restart-app.ps1`. |
| Port 8765 busy after a stop | The old process hadn't released it. `restart-app.ps1` waits `-SettleSeconds` (default 2) between halves for exactly this. |
| Two web UIs running | `startup-app.ps1` guards on both port and process, but a manually-launched one from another shell can still slip past. `stop-app.ps1` stops every match. |
| Mirror is stale | `db/db_sync.log`. The sidecar is the only thing that pushes; the web UI never does. |
| A conversation stopped advancing | **Not an app problem.** Check the agent's own CLI window — it may be waiting on a permission prompt. See [`cli-setup.md`](cli-setup.md). |

---

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`web-ui.md`](web-ui.md) | What the web UI actually serves — routes, SSE, the read-only posture. |
| [`how-it-works.md`](how-it-works.md) | Why the message bus needs neither of these processes. |
| [`cli-setup.md`](cli-setup.md) | Per-CLI config, and the prompts that can stall a spawned agent. |
| [`../../scripts/README.md`](../../scripts/README.md) | Every script in the repo, grouped by job. |

---

<p align="center">
  <sub>← <a href="README.md">App Reference</a> · <a href="../README.md">Documentation</a> · <a href="../../README.md">Agent-Chat</a></sub>
</p>
