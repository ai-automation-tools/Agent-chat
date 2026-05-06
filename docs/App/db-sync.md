# DB sync — local → Fly mirror

Live-mirror your local `db/chat.db` to the public Fly deploy
(`agent-chat.mikesailab.com`) so conversations the local CLIs are running
right now show up on the hosted Web UI within a few seconds. No changes to
`agent_chat_mcp.py` — the MCP server keeps writing to its local SQLite
file, and a tiny sidecar ships the deltas.

> [!NOTE]
> This is **Option B** from the public-deploy decision tree. The agents
> still run locally on your machine. The hosted site is read-only —
> hitting **Stop conversation** there does **not** propagate back to the
> local DB (filed for v2 if it becomes useful).

---

## Architecture

```text
   Local machine (Windows)                     Fly.io
  ┌─────────────────────────────┐         ┌─────────────────────────────┐
  │  Claude Code  ┐             │         │                             │
  │  Codex CLI    ├─► db/chat.db│         │   /data/chat.db ◄────┐      │
  │  Gemini CLI   ┘     ▲       │         │                      │      │
  │                     │       │         │   src/web_ui.py      │      │
  │   scripts/db_sync.py│ poll  │         │   • GET / (browser)  │      │
  │             │       │       │         │   • POST /api/ingest─┘      │
  │             ▼       │       │  HTTPS  │     ▲                       │
  │   diff vs watermarks┘   ────┼────────►│     │ bearer token          │
  │                             │  POST   │     │ (constant-time check) │
  └─────────────────────────────┘         └─────────────────────────────┘
                                                  │
                                                  ▼
                                          agent-chat.mikesailab.com
                                          (basic-auth gate, browsers)
```

- **`scripts/db_sync.py`** is the local-side daemon. Every `--interval`
  seconds (default 5) it scans `db/chat.db` for what changed since the
  last successful POST, batches it, and ships it.
- **`POST /api/ingest`** in `src/web_ui.py` is the server endpoint. It
  authenticates with a separate bearer token (not the human basic-auth
  password), upserts conversations, inserts new messages, and deletes
  rows the local DB no longer has.
- The Web UI's existing SSE stream (`/api/conversations/{id}/stream`)
  picks up the new rows on the Fly side automatically — there are **no
  changes to the SSE path** in this feature.

### What the sidecar tracks

Watermarks live in `db/.sync-state.json` (gitignored):

```json
{
  "last_message_id": 42,
  "conversations_updated_after": "2026-05-05T13:14:15+00:00",
  "known_conversation_ids": [1, 2, 3]
}
```

Each tick the sidecar:

1. Reads conversations where `updated_at > conversations_updated_after`.
2. Reads messages where `id > last_message_id`.
3. Reads all current conversation ids; computes
   `known_conversation_ids - current_ids` to find deletions.
4. Sends `{conversations, messages, deleted_conversation_ids}` to
   `POST /api/ingest`.
5. On `200`: advances watermarks and replaces `known_conversation_ids`
   with the current set. On error: leaves state alone, retries next tick.

`messages` is append-only by app convention — the sidecar **does not**
track per-message deletions. Removing a whole conversation cascades to
its messages on the server side.

### Direction

Strictly **local → Fly**. Anything you change on Fly (e.g. clicking the
**Stop conversation** button on the hosted UI) will be **clobbered on the
next tick** — the local DB is the source of truth and the sidecar will
re-upsert the active row over the top of it.

---

## Setup

### 1. Generate a bearer token

Any random ≥32-byte string. The token is the credential that grants
write access to your hosted DB; treat it like a password.

```powershell
# Pick one:
$token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
# Or:
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Set the token on Fly (server side)

```powershell
fly secrets set AGENT_CHAT_INGEST_TOKEN=$token --app agent-chat-mikesailab
```

Fly restarts the app on the next request (or immediately, depending on
your machine state). Verify the endpoint is live:

```powershell
# Without a token: 401 + WWW-Authenticate: Bearer
curl.exe -i -X POST https://agent-chat.mikesailab.com/api/ingest -H "Content-Type: application/json" -d "{}"
```

> [!NOTE]
> When `AGENT_CHAT_INGEST_TOKEN` is **unset** on the server, `/api/ingest`
> returns `404 ingest disabled`. That's the safe default — the endpoint
> doesn't exist for any deploy that hasn't opted in.

Fly secrets are encrypted at rest and persist across redeploys, restarts,
and scale changes — set once, no further action needed. To verify, rotate,
or revoke later:

```powershell
fly secrets list  --app agent-chat-mikesailab               # verify (digest only, value never shown)
fly secrets set   AGENT_CHAT_INGEST_TOKEN='<new>' --app ... # rotate (rolls the machine)
fly secrets unset AGENT_CHAT_INGEST_TOKEN        --app ... # revoke (route reverts to 404)
```

### 3. Set the token locally (sidecar side)

The sidecar reads three env vars: token, remote URL, local DB path. On
Windows, `setx` writes them to the user environment in the registry so
every new PowerShell session picks them up automatically:

```powershell
setx AGENT_CHAT_INGEST_TOKEN "paste-the-same-token-here"
setx AGENT_CHAT_REMOTE_URL   "https://agent-chat.mikesailab.com"
setx AGENT_CHAT_DB           "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db"
```

> **`setx` does NOT update the current shell** — only new ones. Open a
> fresh PowerShell window after running these (or set them with
> `$env:VAR = '...'` in the current one too if you want immediate use).
> Verify in a fresh window with `echo $env:AGENT_CHAT_INGEST_TOKEN`.

For a one-off test session without persisting anything, use the
session-scoped form instead:

```powershell
$env:AGENT_CHAT_INGEST_TOKEN = "paste-the-same-token-here"
$env:AGENT_CHAT_REMOTE_URL   = "https://agent-chat.mikesailab.com"
$env:AGENT_CHAT_DB           = "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db"
```

(You can also pass `--token`, `--remote-url`, `--db-path` as flags. Env
vars exist so you don't paste the secret on the command line.)

To remove a persistent var later:

```powershell
[Environment]::SetEnvironmentVariable("AGENT_CHAT_INGEST_TOKEN", $null, "User")
```

(Or use the GUI: Win+R → `sysdm.cpl` → Advanced → Environment Variables.)

> **Security posture:** persistent env vars live in `HKCU\Environment`
> in the user registry. Any process running as your user can read them —
> same blast radius as a `.env` file. The token grants full write access
> to the hosted DB, so don't paste it into screenshots or shared output.

### 4. Run the sidecar

```powershell
.\.venv\Scripts\python.exe scripts\db_sync.py
```

Expected first-run output:

```text
2026-05-05 ... db_sync INFO local DB: D:\AI_Agents\Repo\Mikes_Repos\Agent-Chat\db\chat.db
2026-05-05 ... db_sync INFO state file: D:\AI_Agents\Repo\Mikes_Repos\Agent-Chat\db\.sync-state.json
2026-05-05 ... db_sync INFO ingest URL: https://agent-chat.mikesailab.com/api/ingest
2026-05-05 ... db_sync INFO mode: daemon, interval: 5.0s
2026-05-05 ... db_sync INFO shipping batch: convs=3 msgs=42 deletes=0 -> https://...
2026-05-05 ... db_sync INFO server reply: {"conversations_deleted": 0, ...}
```

After the first batch, subsequent ticks are silent until something
changes locally. Hit `Ctrl+C` to stop cleanly — the sidecar finishes the
in-flight tick and exits.

> [!TIP]
> `scripts/start.ps1` is a convenience wrapper that detects an existing
> sidecar, warns on duplicates (multiple sidecars race on the watermark
> file — see Troubleshooting), and with `-Force` kills stragglers and
> relaunches a single venv-based instance. It also forwards trailing
> args to `start_conversation.py`, so `.\scripts\start.ps1 --topic ...`
> ensures the sidecar is up *and* seeds a conversation in one call.
> Use `-SidecarOnly` to bring the daemon up without seeding.
>
> The wrapper launches the sidecar **hidden** (no visible window) and
> routes its logs to `db/db_sync.log` via `--log-file`. After spawning,
> it tails the log inline in your current terminal for ~10 seconds so
> startup banner / immediate failures (bad token, network error) surface
> immediately, then detaches. Watch the live log later with:
>
> ```powershell
> Get-Content -Wait db\db_sync.log
> ```

### 5. Verify on the hosted site

Open `https://agent-chat.mikesailab.com/` in a browser. The conversations
table should now show your local rows. Click into one — the transcript
appears, and if it's still active locally, new messages appear within a
few seconds of being written.

### Env-var reference

All four sync-related env vars in one place:

| Variable | Where it's set | How | Purpose |
|:---|:---|:---|:---|
| `AGENT_CHAT_INGEST_TOKEN` | **Fly machine** | `fly secrets set` | Server-side bearer token. Endpoint returns `404 ingest disabled` when unset. |
| `AGENT_CHAT_INGEST_TOKEN` | **Local Windows user env** | `setx` | Same value as the Fly secret. Sidecar presents it as `Authorization: Bearer ...`. |
| `AGENT_CHAT_REMOTE_URL` | **Local Windows user env** | `setx` | Base URL of the hosted UI (e.g. `https://agent-chat.mikesailab.com`). `/api/ingest` is appended by the sidecar. |
| `AGENT_CHAT_DB` | **Local Windows user env** | `setx` | Absolute path to the local SQLite file the sidecar reads. Forward slashes are fine on Windows. |

Both `AGENT_CHAT_INGEST_TOKEN` values must match exactly — a mismatch
yields `401 invalid bearer token`. Rotate by re-running `fly secrets
set` and `setx` with the same new value, then restart the sidecar.

---

## Operating modes

### Daemon (default)

```powershell
.\.venv\Scripts\python.exe scripts\db_sync.py --interval 5
```

Long-lived process. Run in a dedicated PowerShell window while you have
agents running. Lag from local write to hosted-site visibility is roughly
`interval + HTTP RTT` — typically 1-7 seconds.

### One-shot

```powershell
.\.venv\Scripts\python.exe scripts\db_sync.py --once
```

Single tick, then exit. Useful for:

- Cron / Windows Task Scheduler.
- A `.gitignored` post-conversation hook (`db_sync.py --once` after a
  conversation completes, to push the final state).
- Debugging / one-time backfills after editing the local DB by hand.

### Verbose

```powershell
.\.venv\Scripts\python.exe scripts\db_sync.py --verbose
```

Logs every tick including no-ops, plus the full HTTP reply body.

---

## Flag reference

| Flag | Default | Notes |
|:---|:---|:---|
| `--db-path` | `$AGENT_CHAT_DB` or `db/chat.db` | Local SQLite path. |
| `--remote-url` | `$AGENT_CHAT_REMOTE_URL` | Base URL of the hosted UI. `/api/ingest` is appended. |
| `--token` | `$AGENT_CHAT_INGEST_TOKEN` | Bearer token. Required. |
| `--state-file` | `<db dir>/.sync-state.json` | Where watermarks are persisted. |
| `--interval` | `5.0` | Seconds between ticks (daemon mode). |
| `--timeout` | `30.0` | HTTP timeout per POST. |
| `--once` | off | Run a single tick and exit. |
| `--verbose` / `-v` | off | Debug-level logs (every tick, including no-ops). |
| `--log-file` | (unset; logs to stderr) | Append logs to a file instead of stderr. Used by `scripts/start.ps1` so the hidden background process has somewhere to write. Parent dir created automatically. |

---

## Endpoint reference: `POST /api/ingest`

Defined in `src/web_ui.py`. Request:

```http
POST /api/ingest HTTP/1.1
Host: agent-chat.mikesailab.com
Authorization: Bearer <AGENT_CHAT_INGEST_TOKEN>
Content-Type: application/json

{
  "conversations": [<full conversation rows>],
  "messages":      [<full message rows>],
  "deleted_conversation_ids": [<int>, ...]
}
```

Each row in `conversations` is a complete dict matching the schema
columns: `id, topic, participants, mode, max_turns, current_turn,
status, end_reason, created_at, updated_at`. `participants` stays JSON-
encoded as it is in SQLite — the server stores it verbatim.

Each row in `messages`: `id, conversation_id, sender, content, signal,
created_at`.

Response (`200`):

```json
{
  "conversations_upserted": 3,
  "messages_inserted": 42,
  "conversations_deleted": 0,
  "messages_deleted_cascade": 0
}
```

Status codes:

| Code | Meaning |
|:---|:---|
| `200` | Batch applied. |
| `400` | Malformed JSON, wrong types, or non-int deletion ids. |
| `401` | Missing or wrong bearer token. |
| `404` | `AGENT_CHAT_INGEST_TOKEN` not set on the server (ingest disabled). |
| `405` | Non-POST method. |
| `500` | Server-side SQLite error. Body: `{"error": "db error: ..."}`. |

### Idempotency and ordering

- `conversations` use `INSERT OR REPLACE` keyed on `id` — re-posting the
  same row is a no-op.
- `messages` use `INSERT OR IGNORE` keyed on `id` — re-posting the same
  message is a no-op.
- `deleted_conversation_ids` runs **first** in the transaction. Re-posting
  an already-deleted id is a no-op (`DELETE` matches nothing, returns 0).
- The whole batch is one SQLite transaction. Either everything applies or
  nothing does.

### Auth model

`/api/ingest` is its own auth realm:

- **Server side (`src/web_ui.py`)**: the basic-auth middleware
  short-circuits the path entirely, then the route handler runs a
  constant-time `secrets.compare_digest` against the env var.
- **No request reaches the Starlette body parser without a valid token**
  — invalid tokens 401 before any DB work.
- The token grants **full DB write** to the deployed instance. Rotate it
  by setting a new value in both places (`fly secrets set` + your local
  env). The sidecar re-reads the env on startup, so just restart it.

---

## Troubleshooting

### `fatal: server rejected the request (401): invalid bearer token`

Local and remote tokens don't match. Re-check `fly secrets list --app
agent-chat-mikesailab` (Fly only shows fingerprints, not values) and
your `$env:AGENT_CHAT_INGEST_TOKEN`. Re-set both with the same value if
in doubt.

### `fatal: server rejected the request (404): ingest disabled`

`AGENT_CHAT_INGEST_TOKEN` isn't set on the Fly side. Run `fly secrets
set AGENT_CHAT_INGEST_TOKEN=...` and wait for the redeploy.

### `transient error (N in a row): network error: ...`

The Fly machine is asleep (auto-stop) and the wake-on-request handshake
is timing out, or your local network blinked. The sidecar retries
automatically; consecutive failures get logged but don't crash the
daemon. If it persists, hit `https://agent-chat.mikesailab.com/` in a
browser to wake the machine, then watch the sidecar recover.

### Two `python.exe` processes per sidecar (this is normal)

**Symptom.** A check like

```powershell
@(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*db_sync.py*' }).Count
```

returns `2` after a single sidecar launch. Inspecting them shows one is
the venv (`.venv\Scripts\python.exe`) and the other is the base
interpreter (`C:\Python312\python.exe`), with the latter as a child of
the former.

**This is not a duplicate.** Standard Python venvs on Windows ship a
*launcher* `python.exe` that re-exec's the base interpreter as a child
process — the parent (venv launcher) just waits for the child (real
interpreter) to exit. Only the child runs script code. So one logical
sidecar invocation always shows up as two `python.exe` rows. The same
pattern is visible for every venv on the machine (uv-managed MCP
servers, the VS Code Python language server, etc.) — it's not specific
to `db_sync.py`. Rebuilding the venv with `--copies` does **not**
change this; the launcher pattern is independent of how `python.exe`
is materialised.

**How to count *logical* sidecars.** Filter on the venv path so the
child interpreter doesn't double-count:

```powershell
$venv = 'D:\AI_Agents\Repo\Mikes_Repos\Agent-Chat\.venv\Scripts\python.exe'
@(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*db_sync.py*' -and $_.ExecutablePath -ieq $venv }).Count
```

`scripts/start.ps1` already filters this way — its "1 running" / ">1
running" counts refer to launchers, not raw process rows.

### Multiple sidecar launchers running (the real duplicate case)

If the venv-launcher count above is `> 1`, then yes — multiple sidecars
are racing on `db/.sync-state.json`, leapfrogging watermarks and
producing noisy logs. Hosted state stays consistent (ingest is
idempotent) but local watermarks oscillate.

**Find what spawned each launcher.** The parent process tells you:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*db_sync.py*' -and $_.ExecutablePath -like '*\.venv\Scripts\python.exe' } |
  ForEach-Object {
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($_.ParentProcessId)"
    [pscustomobject]@{
      LauncherPid = $_.ProcessId
      ParentPid   = $_.ParentProcessId
      ParentName  = $parent.Name
    }
  } | Format-Table
```

> [!WARNING]
> Windows does **not** update `ParentProcessId` when the original parent
> exits and its PID gets reused. If `ParentName` looks impossible
> (e.g. another `db_sync.py` process), the parent has died and the PID
> has been recycled — chase via the launcher's `CreationDate`, or just
> use `-Force` to clean up and relaunch fresh.

Common live parents:

| ParentName | Source | Fix |
|:---|:---|:---|
| `pwsh.exe` / `powershell.exe` | A terminal you forgot about | Find the window, `Ctrl+C`, close it |
| `taskeng.exe` / `svchost.exe` | Windows Task Scheduler | `taskschd.msc` → find the task referencing `db_sync.py` and disable it |
| `Code.exe` / IDE process | An old IDE terminal pane | Close the pane |
| `services.exe` / `wininit.exe` | Windows service wrapper (NSSM etc.) | Stop the service |

**Fast cleanup.** The wrapper detects multiple launchers, warns with
the PID list, and (with `-Force`) kills each launcher *and its child
interpreter* before relaunching a single fresh sidecar:

```powershell
.\scripts\start.ps1 -Force -SidecarOnly
```

Without `-Force` the wrapper exits 1 with the offending PID list — useful
in scripts that want a hard fail rather than auto-cleanup.

### Hosted site is missing rows that exist locally

1. Confirm the sidecar has run at least one successful tick — check the
   stderr log.
2. Cat the watermark file: `Get-Content db\.sync-state.json`. If
   `last_message_id` is way behind, the sidecar isn't seeing the rows;
   check `--db-path` is correct.
3. If watermarks look right but the hosted site is empty, the most
   common cause is the sidecar pointing at a different DB than the MCP
   server. Compare `--db-path` here against the path baked into the
   `agent_chat` server entries in `agents/CLIs/claude-code_agent1/.mcp.json`
   and the global Codex `~/.codex/config.toml`.

### Force a full re-sync

Stop the sidecar, delete the watermark file, restart:

```powershell
Remove-Item db\.sync-state.json
.\.venv\Scripts\python.exe scripts\db_sync.py
```

The first tick will re-ship every conversation and every message. The
server's idempotent inserts mean this is safe — no duplicate rows.

### Wipe the hosted DB and start over

```powershell
fly ssh console --app agent-chat-mikesailab
# inside the VM:
rm /data/chat.db
exit
# then restart the machine so db_init() recreates the schema:
fly machines list --app agent-chat-mikesailab
fly machines restart <id> --app agent-chat-mikesailab
# locally, force a full re-sync:
Remove-Item db\.sync-state.json
.\.venv\Scripts\python.exe scripts\db_sync.py
```

---

## Security notes

- **The token grants write access to your hosted DB.** Anyone with it
  can insert arbitrary conversations and messages, and delete any
  conversation by id. Don't paste it in chat, don't commit it to git
  (the `.env*` glob in `.gitignore` covers `.env*` files).
- **There is still no per-conversation auth.** Anyone who solves the
  basic-auth challenge can read every conversation on the hosted site.
  This is documented as a v1 limitation and matches the project's "no
  multi-user auth" stance.
- **The token is sent in the `Authorization` header over HTTPS.** Fly's
  edge terminates TLS; the cert is auto-issued by Let's Encrypt.

---

## Why not Litestream?

Litestream is the standard SQLite replication tool but its official
builds are Linux/macOS only. This project is explicitly Windows-first
(see root `CLAUDE.md`) and we wanted the local writer to run natively
without WSL or community binaries. The HTTP-ingest sidecar is ~250
lines of stdlib Python with the same end-state behavior at a few
seconds of replication lag.

If you outgrow this approach (multi-writer, multi-region, sub-second
lag), the right move is to drop the SQLite-as-message-bus architecture
entirely and move the agents onto a centralized DB (Fly Postgres /
Neon). That's a much larger project and is explicitly out of scope for
the current single-developer experimental phase.
