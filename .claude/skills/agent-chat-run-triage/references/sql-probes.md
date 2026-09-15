# SQL probes for a misbehaving run

Read-only. Run them against the DB the **agents** are writing, not necessarily `db/chat.db`.

```powershell
# One-off query. Use the venv interpreter explicitly; never rely on activation.
.\.venv\Scripts\python.exe -c "import sqlite3,sys; c=sqlite3.connect(r'db/chat.db'); c.row_factory=sqlite3.Row; [print(dict(r)) for r in c.execute(sys.argv[1])]" "SELECT id, topic, status FROM conversations ORDER BY id DESC LIMIT 5"
```

Or open a shell if `sqlite3.exe` is on PATH: `sqlite3 db/chat.db` (add `.mode line`).

The columns referenced below are the canonical `SCHEMA` in `src/agent_chat_mcp.py`.

---

## 0. Which database is each side using?

The most common "the UI shows nothing" cause, and it is not a bug.

```powershell
$env:AGENT_CHAT_DB                       # the override, if set
Get-Content .mcp.json                    # what --db-path each seat was registered with
Get-ChildItem agents/CLIs/*/**/*.json | Select-String 'db-path'
```

`scripts/run-mcp-server.ps1` defaults to `<repo>/db/chat.db` and resolves it relative to itself.
`web.db.set_db_path()` also exports `$AGENT_CHAT_DB` — without that export, a custom path reads
conversations from one DB and personas from another.

## 1. The conversation row

Everything the rotation depends on, in one line.

```sql
SELECT id, status, mode, max_turns, current_turn, end_reason,
       conv_type, preset, participants, participant_roles, updated_at
FROM conversations
WHERE id = 57;
```

Read it as: *is it still active, whose turn does it think it is, and is that agent id spelled
exactly the way the CLI was launched?* `participants` is a JSON array; `participant_roles` is
`{agent_id: role}`.

## 2. Is there anything in the room at all?

```sql
SELECT COUNT(*) AS msgs,
       MIN(created_at) AS first_at,
       MAX(created_at) AS last_at
FROM messages WHERE conversation_id = 57;
```

`msgs = 0` on an `active` row = **seeded but never joined**. That is a launch problem — go look at
the CLI windows, not at the rotation. The watchdog excludes this case on purpose.

## 3. The tail of the transcript

```sql
SELECT id, sender, signal, substr(content, 1, 120) AS head, created_at
FROM messages WHERE conversation_id = 57
ORDER BY id DESC LIMIT 8;
```

Who spoke last, and with what signal. `evaluate_stop()` reads **the most recent message's signal
only** — `done` and `blocked` end the run; `result` does not.

## 4. Per-seat turn counts vs the cap

The probe that settles every "it ended early" and every "that seat never spoke" question.

```sql
SELECT m.sender,
       COUNT(*)                AS used,
       c.max_turns             AS cap,
       c.max_turns - COUNT(*)  AS remaining
FROM messages m
JOIN conversations c ON c.id = m.conversation_id
WHERE m.conversation_id = 57 AND m.sender <> 'system'
GROUP BY m.sender
ORDER BY used DESC;
```

Read it against two rules:

- The run ends only when **every** seat has `remaining <= 0`. A row with turns left plus a
  `complete` status is the old first-agent-wins bug.
- `current_turn` must never name a seat with `remaining <= 0` — `next_turn_agent()` skips spent
  seats. A pointer parked on one deadlocks the room: every send is rejected and the pointer never
  advances.

A seat in `participants` with **no row here at all** never spoke once. Compare its id against the
`--agent-id` its window was launched with; identity is config-only.

## 5. Did a deliverable land, and who ended the run?

For a `conv_type` with `produces_deliverable` (today: `collaborate`).

```sql
SELECT id, sender, signal, created_at
FROM messages
WHERE conversation_id = 57 AND signal IS NOT NULL
ORDER BY id;
```

- Several `result` rows is **normal** — leads draft then revise, and the **last one wins**.
- A `done` from a non-lead **before** any `result` should have been refused by
  `blocks_premature_done()` before the insert. If one is there, that guard has a hole.
- A lead may always end early; `blocked` is never restricted; transcript types (debate, podcast)
  are untouched by the rule.

Cross-reference the sender against `participant_roles` from probe 1.

## 6. Locking and WAL

```sql
PRAGMA journal_mode;      -- must be 'wal' — two processes write this file
PRAGMA busy_timeout;
```

`database is locked` with WAL on means a writer is holding a transaction. The write paths use
explicit `BEGIN` / `COMMIT` / `ROLLBACK`, which is only correct because connections run with
`isolation_level=None` (autocommit) and `timeout=10.0`. A sink or a long render inside a write
transaction is the usual culprit — `deliver()` must always be called **outside** it.

To find the holder:

```powershell
Get-Process | Where-Object { $_.CommandLine -like '*Agent-Chat*' } | Select-Object Id, CommandLine
```

Match on the **command line**, never `ExecutablePath`: on Windows the venv launcher re-execs the
base interpreter, so one of this app's processes reports `C:\Python312\python.exe` to WMI while
genuinely being the venv. `healthcheck-app.ps1` / `startup-app.ps1` / `stop-app.ps1` all do it
this way and `tests/test_availability.py` pins that.

## 7. Stalls, with the bar

Prefer the CLI over hand SQL — it computes each run's own quiet threshold:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py watch --quiet
```

`--quiet` reports without firing the `stalled` delivery sinks — use it while diagnosing, and drop
it when you want the notification. Either way the exit code is the number of stalled runs, so a
scheduler can key off it. Prints `quiet_seconds` against `bar_seconds` per active run. The bar is
`max(600, export.quiet_threshold_seconds(msgs))`, and `current_turn` in that output is the agent
window you should go look at.

## 8. Is it reaching the hosted mirror?

```powershell
scripts\healthcheck-app.ps1 -Repair:$false     # pure probe: web UI + sidecar
```

The sidecar (`scripts/db_sync.py`) is the **only** path data takes to Fly — never a deploy. A
column the sidecar does not carry never reaches the mirror, and `/api/ingest` names every synced
column in its `INSERT`, so a sidecar sending a new column fails against a mirror that has not been
deployed yet.
