# DB sync — bidirectional mirror

Keep your local `db/chat.db` and the public Fly deploy
(`agent-chat.mikesailab.com`) in sync **in both directions**. Local-side
agent activity (new messages, status flips, conversation seeds) flows up
to the hosted UI within a few seconds; hosted-UI mutations (force-stop,
delete-conversation, **persona create/edit/delete**, future edit-topic /
seed-form) flow back down to the local DB on the next pull tick. No changes
to `agent_chat_mcp.py` — the MCP server keeps writing to its local SQLite
file; a tiny stdlib-only sidecar reconciles the two sides.

> [!NOTE]
> **Personas sync too (since 2026-06-22).** The `personas` table syncs
> bidirectionally alongside conversations — same watermark + set-difference
> machinery, the one difference being that personas key on a composite
> `(group, slug)` rather than an int `id` (serialized on the wire as
> `group␟slug`, ASCII Unit Separator `0x1F`). This is what makes the
> [`/personas`](web-ui.md) management page work on the hosted mirror. State
> files from before this date default the new persona watermarks to epoch,
> producing one full persona sync on first tick.

> [!NOTE]
> Bidirectional sync landed 2026-05-06. The earlier push-only design is
> documented in CHANGELOG (2026-05-05) for reference. State files written
> by the push-only version are loaded forward-compatibly — the new
> `pulled_updated_at` watermark defaults to `1970-01-01T00:00:00+00:00`
> on first read, which produces one big initial pull (acceptable cost).

---

## Architecture

```text
   Local machine (Windows)                     Fly.io
  ┌─────────────────────────────┐         ┌─────────────────────────────┐
  │  Claude Code  ┐             │         │                             │
  │  Codex CLI    ├─► db/chat.db│  pull   │   /data/chat.db             │
  │  Antigravity  ┘     ▲       │ ◄──────┐│        ▲                    │
  │                     │       │  HTTPS ││        │                    │
  │   scripts/db_sync.py│       │  GET   ││ src/web_ui.py               │
  │   ┌────────────────┐│       │ /since ││  • GET / (browser)          │
  │   │ tick:          ││       │        ││  • GET /api/since ──────────┘
  │   │  1. PULL       ││       │  push  ││  • POST /api/ingest ◄───────┐
  │   │  2. apply local││       │ ──────►││  • POST .../delete          │
  │   │  3. PUSH       ││  diff │  HTTPS ││    (cascades messages)      │
  │   │  4. save state ││ vs    │  POST  ││                             │
  │   └────────────────┘│ marks │ /ingest││  bearer token (constant-    │
  │             ▼       │       │        ││  time check) — same token   │
  │   db/.sync-state.json       │        ││  for pull + push for now.   │
  └─────────────────────────────┘         └─────────────────────────────┘
                                                  │
                                                  ▼
                                          agent-chat.mikesailab.com
                                          (basic-auth gate, browsers)
```

- **`scripts/db_sync.py`** is the local-side daemon. Every `--interval`
  seconds (default 5) it pulls the latest hosted-side conversation
  deltas, applies them locally, then pushes its own deltas in the other
  direction.
- **`GET /api/since`** in `src/web_ui.py` returns conversation deltas:
  rows whose `updated_at` is strictly greater than the watermark, plus
  the subset of `known_ids` that no longer exist on the server (so the
  sidecar can delete them locally too). It also returns **persona**
  deltas the same way (keyed on composite `(group, slug)` via
  `personas_updated_after` + `known_persona_keys`). Messages are **not**
  included in the pull payload — they flow local-only-origin.
- **`POST /api/ingest`** is the existing push endpoint. Upserts
  conversations + personas, inserts new messages, deletes rows the local
  DB no longer has (conversations by id, personas by composite key).
  Idempotent.
- The Web UI's SSE stream (`/api/conversations/{id}/stream`) picks up
  pushed rows automatically — no changes to the SSE path in this
  feature.

### Asymmetry: messages flow local-only-origin

**Conversations are bidirectional. Messages are not.** The pull payload
deliberately excludes messages because:

1. Agents only run locally. The Fly deploy doesn't host MCP servers, so
   no message can ever originate there.
2. SQLite's `INTEGER PRIMARY KEY AUTOINCREMENT` means hosted-side
   inserts would collide with local-side ids. Avoiding hosted-side
   message inserts dodges the schema-migration-to-UUIDs rabbit hole.
3. Future hosted affordances (seed-conversation form, edit-topic
   button) all mutate **conversation rows**, not messages. Agents fill
   in the messages locally afterward, those flow up via push.

If a hosted-side message-insert use case ever appears (e.g., a
moderator interjection), revisit. Until then, the asymmetry is the
simplification that makes bidirectional sync tractable.

### Conflict resolution

**Last-write-wins by `updated_at`** for conversation rows. The two
sides converge because:

- Hosted-UI mutations (Stop, Delete, future Edit Topic) bump
  `updated_at` server-side.
- Local mutations (agent posts, MCP server flipping `current_turn`,
  `start_conversation.py` seeds) bump `updated_at` locally.
- Whichever side bumped most recently wins via `INSERT OR REPLACE`
  semantics on the receiver. Edits on both sides simultaneously are
  rare in practice and lose the older edit cleanly.

Deletes are authoritative from either side. If the server reports a
conversation as gone, the sidecar removes it locally (cascading
messages); if the local DB drops a row, the next push includes the id
in `deleted_conversation_ids` and the server removes it (also
cascading).

### What the sidecar tracks

Watermarks live in `db/.sync-state.json` (gitignored):

```json
{
  "last_message_id": 42,
  "conversations_updated_after": "2026-05-05T13:14:15+00:00",
  "pulled_updated_at": "2026-05-06T19:00:00+00:00",
  "known_conversation_ids": [1, 2, 3],
  "personas_updated_after": "2026-06-22T10:00:00+00:00",
  "pulled_personas_updated_at": "2026-06-22T10:00:00+00:00",
  "known_persona_keys": ["Unique-Personascrypto-chad", "..."]
}
```

| Field | Direction | Advanced when |
|:---|:---|:---|
| `last_message_id` | push | Pushed message batch returned `200`. |
| `conversations_updated_after` | push | Pushed conversation batch returned `200`. **Also** bumped to `server_time` after a successful pull, so just-pulled rows don't re-trigger the push delta query (avoids ping-pong). |
| `pulled_updated_at` | pull | `GET /api/since` returned `200`; advanced to the response's `server_time` (avoids local-vs-Fly clock-skew). |
| `known_conversation_ids` | both | Replaced after each successful tick with the current local set. The push step uses this to compute deletions to send up. |
| `personas_updated_after` | push | Persona push counterpart of `conversations_updated_after` — same `max(old, max updated_at, server_time)` advance. |
| `pulled_personas_updated_at` | pull | Persona pull counterpart of `pulled_updated_at` — advanced to the same `server_time`. |
| `known_persona_keys` | both | Current local set of `group␟slug` keys; the push step diffs against it to compute persona deletions. |

### Tick order: pull-then-push

Each tick:

1. **Pull** — `GET /api/since?conversations_updated_after=…&known_ids=…`
2. **Apply** the pull payload locally (`INSERT OR REPLACE` for
   conversations, cascade `DELETE` for deletions).
3. **Push** — read local deltas (conversations, messages, deletions),
   `POST /api/ingest`.
4. **Save state** with both watermarks advanced.

Pull-first prevents a hosted-side delete from racing with a local
re-upsert. If the order were flipped, push would re-create the
just-deleted row before the next pull caught up.

### Mixed-version handling

If the remote server is older than the sidecar (e.g., new sidecar
running locally, old build still deployed), `GET /api/since` returns
`404` and the sidecar treats this as a soft `PullNotSupported` error:
**logs a warning** and **skips the pull step** but still runs push.
Hosted-side stops/deletes are clobbered until the user redeploys, but
the sidecar stays alive.

The reverse direction (old sidecar, new server) just keeps doing
push-only — the new pull endpoint goes unused. No version coordination
is required.

### Direction

**Bidirectional**, with the message asymmetry above. Hosted-UI affordances
that mutate conversation rows (Stop, Delete, future Edit Topic) propagate
back to the local DB on the next pull tick (~5s). Hosted-UI affordances
that would create messages don't exist yet (and probably shouldn't —
agents do that locally).

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
setx AGENT_CHAT_DB           "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/db/chat.db"
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
$env:AGENT_CHAT_DB           = "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/db/chat.db"
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
2026-05-05 ... db_sync INFO local DB: D:\AI_Agents\Projects\Mikes_AI_Lab\Repos\Live_Apps\Agent-Chat\db\chat.db
2026-05-05 ... db_sync INFO state file: D:\AI_Agents\Projects\Mikes_AI_Lab\Repos\Live_Apps\Agent-Chat\db\.sync-state.json
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
  "deleted_conversation_ids": [<int>, ...],
  "personas":      [<full persona rows>],
  "deleted_persona_keys": ["<group><slug>", ...]
}
```

Each row in `conversations` is a complete dict matching the schema
columns: `id, topic, participants, mode, max_turns, current_turn,
status, end_reason, created_at, updated_at`. `participants` stays JSON-
encoded as it is in SQLite — the server stores it verbatim.

Each row in `messages`: `id, conversation_id, sender, content, signal,
created_at`.

Each row in `personas`: `group, slug, name, tags, category, subcategory,
body, created_at, updated_at` (`tags` is a JSON array string or null).
`personas` / `deleted_persona_keys` are **optional** — an older sidecar
omits them and the server no-ops. Each entry in `deleted_persona_keys` is
a composite key `group␟slug` (Unit Separator `0x1F`).

Response (`200`):

```json
{
  "conversations_upserted": 3,
  "messages_inserted": 42,
  "conversations_deleted": 0,
  "messages_deleted_cascade": 0,
  "personas_upserted": 29,
  "personas_deleted": 0
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
- `personas` use `INSERT OR REPLACE` keyed on `(group, slug)`; deletions by
  composite key run before the persona upserts. Same idempotency guarantees.
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

### Edited `db_sync.py` (or its column lists)? Restart the sidecar

The sidecar is a long-running Python process — it does **not** hot-reload. A
running sidecar keeps using the code it was launched with, so any edit to
`scripts/db_sync.py` (notably `CONV_COLUMNS` / `MSG_COLUMNS` / `PERSONA_COLUMNS`
when a schema column is added) has **no effect until you restart it**:

```powershell
.\scripts\start.ps1 -Force -SidecarOnly   # kill the old launcher + relaunch with current code
```

Symptom if you forget: new columns never reach the hosted DB even though the
local writes succeed (e.g. a freshly added `participant_personas` shows up
locally but the hosted export shows "not recorded"). Note that a restarted
sidecar only re-pushes conversations whose `updated_at` is newer than its
watermark — to force a **completed** conversation to re-sync after the restart,
bump its `updated_at` (`UPDATE conversations SET updated_at=<now> WHERE id=<id>`)
or see "Force a full re-sync" below.

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
$venv = 'D:\AI_Agents\Projects\Mikes_AI_Lab\Repos\Live_Apps\Agent-Chat\.venv\Scripts\python.exe'
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
   server. Both default to `<repo>/db/chat.db` since 2026-05-12 — so
   confirm neither side has `AGENT_CHAT_DB` set to a different path,
   and that neither config (your sidecar invocation or the `agent_chat`
   server entries in `agents/CLIs/claude-code_agent1/.mcp.json` /
   `~/.codex/config.toml`) appends an explicit `--db-path` pointing
   elsewhere.

### Hosted-side Stop/Delete didn't reach the local DB

The pull side of bidirectional sync is what propagates hosted-UI
mutations back. Three things to check, in order of likelihood:

1. **Running sidecar is an old build.** Python doesn't hot-reload —
   editing `scripts/db_sync.py` while the daemon is running is silent
   until the process restarts. Confirm by tailing the log: a
   bidirectional sidecar logs `since URL: …` in its startup banner
   and produces `pull: convs=… deletes=…` lines on every tick. A
   push-only sidecar only ever logs `shipping batch: …`. If you see
   the latter, restart with `.\scripts\start.ps1 -Force -SidecarOnly`.

2. **Remote returned 404 from `/api/since`.** Old build deployed on
   Fly. The sidecar treats this as a soft `PullNotSupported` and skips
   pull (still pushes). Search the log for `PullNotSupported`. Fix:
   `fly deploy` from the repo root.

3. **State file `pulled_updated_at` is wedged at a future timestamp.**
   Rare — would happen if the system clock skewed and the watermark
   advanced past now. Force-resync (next section) clears it.

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
