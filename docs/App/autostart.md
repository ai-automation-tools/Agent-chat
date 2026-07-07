# Autostart — bring up the local app at logon

Run the Agent-Chat local app automatically when you log in to Windows, via a
Task Scheduler job in a dedicated **`Agent-Chat`** folder. The job brings up
two components, both hidden (no console window):

1. **Web UI** — `src/web_ui.py`, the local viewer at
   <http://127.0.0.1:8765>. Reads `db/chat.db`; nothing else is required for
   it to render.
2. **`db_sync` sidecar** — `scripts/db_sync.py`, the local→Fly mirror daemon
   that keeps `agent-chat.mikesailab.com` in sync. Needs your
   `AGENT_CHAT_*` env vars (see [`db-sync.md`](db-sync.md)).

The MCP server is **not** autostarted — it's launched per-CLI on demand (each
CLI spawns its own via `scripts/run-mcp-server.ps1`), not run as a daemon.

---

## Why logon (not boot)

The trigger is **at logon of your user**, and the task runs with your
**interactive** token. That's deliberate:

- The web UI is a local viewer you open in your own browser — there's no
  point serving `127.0.0.1` before anyone is logged in.
- The sidecar reads `AGENT_CHAT_INGEST_TOKEN` / `AGENT_CHAT_REMOTE_URL` from
  your **user** environment (`setx` writes to `HKCU\Environment`). A SYSTEM
  task at boot wouldn't see them, so the mirror would fail to authenticate.
- No stored password is required (Interactive logon type), and the task runs
  unelevated (`RunLevel Limited`) — binding loopback needs no admin rights.

A 15-second post-logon delay lets the desktop and network settle before the
sidecar's first HTTPS tick.

---

## Install / update

From the repo root, in `pwsh`:

```powershell
.\scripts\setup\register-startup-task.ps1
```

Re-running updates the task in place (`Register-ScheduledTask -Force`). It
auto-detects the current user and the repo path — no arguments needed. Options:

| Flag | Default | Effect |
|:---|:---|:---|
| `-StartDelaySeconds <n>` | `15` | Seconds to wait after logon before firing. |
| `-Unregister` | — | Remove the task (leaves the empty `\Agent-Chat\` folder). |

The task it creates:

| Field | Value |
|:---|:---|
| Location | `Task Scheduler Library \ Agent-Chat \ Start-AgentChat-App` |
| Trigger | At log on of the current user, `+15s` delay |
| Action | `pwsh -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File scripts\startup-app.ps1` |
| Principal | Current user, Interactive logon, `RunLevel Limited` |
| Settings | Start on battery, don't stop on battery, start-when-available, no time limit, `MultipleInstances=IgnoreNew`, restart ×2 @ 1 min |

---

## What the launcher does

`scripts/startup-app.ps1` is what the task actually runs. It's **idempotent**,
so a re-logon or an accidental double-fire never spawns duplicates:

- **Web UI** — skipped if port `8765` is already listening, or a venv-python
  `web_ui.py` process is already running. Otherwise launched hidden, with
  stdout/stderr → `db/web_ui.out.log` / `db/web_ui.err.log`.
- **Sidecar** — delegated to `scripts/start.ps1 -SidecarOnly`, which has its
  own single-launcher guard (won't start a second racing sidecar) and logs to
  `db/db_sync.log`.

Every run appends a summary to **`db/startup-app.log`**. Flags: `-SkipSidecar`
(web UI only) and `-SkipWebUI` (sidecar only).

You can run it by hand at any time — same effect as the scheduled trigger:

```powershell
.\scripts\startup-app.ps1
```

---

## Verify / operate

```powershell
# Fire it now without logging out:
Start-ScheduledTask -TaskPath '\Agent-Chat\' -TaskName 'Start-AgentChat-App'

# Last run result (0 = success):
Get-ScheduledTaskInfo -TaskPath '\Agent-Chat\' -TaskName 'Start-AgentChat-App' |
  Select-Object LastRunTime, LastTaskResult

# Is the web UI up?
(Invoke-WebRequest http://127.0.0.1:8765/ -UseBasicParsing).StatusCode   # 200

# Tail the run log:
Get-Content .\db\startup-app.log -Tail 20
```

Inspect it in the GUI: `taskschd.msc` → **Task Scheduler Library → Agent-Chat**.

> [!NOTE]
> A `LastTaskResult` of `267009` (`0x41301`, *task currently running*) right
> after triggering is normal — the sidecar delegate tails its startup log for
> ~10s before the action returns. It settles to `0` once complete.

---

## Remove

```powershell
.\scripts\setup\register-startup-task.ps1 -Unregister
```

This only removes the scheduled task — it does **not** stop an
already-running web UI or sidecar. Stop those with the normal tools (e.g.
`.\scripts\start.ps1 -Force -SidecarOnly` cleans up sidecars; kill the
`web_ui.py` process to stop the viewer).

---

## Troubleshooting

| Symptom | Cause / fix |
|:---|:---|
| Task result `267009` and stays there | Still running — the child `start.ps1` tails for ~10s. Re-check after ~15s; should be `0`. |
| Web UI didn't come up | Check `db/web_ui.err.log`. Most common: port `8765` taken by a stale process (`Get-NetTCPConnection -LocalPort 8765`). |
| Hosted mirror not updating | Sidecar env vars missing — see [`db-sync.md`](db-sync.md) §3. Check `db/db_sync.log` for `401 invalid bearer token` or a missing token. |
| Two sidecars running | The launcher delegates to `start.ps1`'s guard, but a manually-started extra can still race. `\scripts\start.ps1 -Force -SidecarOnly` kills strays and relaunches one. |
| Nothing happened at logon | `taskschd.msc` → History tab for the task; confirm the trigger user matches the account you logged in as. |
