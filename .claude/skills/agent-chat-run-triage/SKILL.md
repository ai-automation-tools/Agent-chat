---
name: agent-chat-run-triage
description: >-
  Diagnose a live Agent-Chat conversation that is stuck, silent, ending early, or behaving wrong —
  a run that will not advance, a seat that is never handed a turn, "not your turn" rejections, a
  room that closed before the deliverable landed, an agent window that never joined, a database
  that is locked, or a conversation missing from the web UI or the hosted mirror. Works from the
  DB outward: read the row, read the rotation, then look at a CLI window. Use for "the debate is
  stuck", "conversation 57 isn't moving", "the agent isn't taking its turn", "why did this end at
  max_turns", "it says it's not my turn", "nothing shows in the UI", "database is locked", "the
  watchdog fired", or any Agent-Chat run that is not doing what it should.
---

# Triaging a live run

**Diagnose from the database outward.** The DB is the contract between processes; a CLI window
telling you what it thinks is happening is a *second-hand* account of that row. Read the row
first, and you will usually know the answer before you look at a terminal.

Copy-paste probes: [`references/sql-probes.md`](references/sql-probes.md).

**Read-only until you know the cause.** Stopping a conversation destroys the run you were trying
to rescue, and it is the one action you cannot undo.

---

## 0. Two facts to have in hand

- `mode` is `turns` or `continuous`. In `turns`, `conversations.current_turn` holds the agent id
  that may speak; every other sender is rejected. In `continuous`, anyone may.
- `max_turns` is a **per-agent** cap, not a total.

## 1. Triage in order

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py list
.\.venv\Scripts\python.exe src\inspect_conversations.py show 57
.\.venv\Scripts\python.exe src\inspect_conversations.py watch --quiet   # stall check, no sinks fired
```

Then walk the table. Stop at the first row that matches.

| Symptom | Almost always | Confirm with |
|:---|:---|:---|
| `status='active'`, **zero messages** | seeded but never joined — a *launch* problem, not a stall. The watchdog deliberately ignores this case | the CLI window: did it start, did it register the MCP server, is it waiting on an approval prompt |
| Messages stop, `current_turn` names agent **N** | agent N's window is not polling — it exited, it is asking the operator a question, or it never loaded the `agent-chat` skill | look at **that** window; `current_turn` is the address of the one you need |
| `current_turn` names an agent that is **spent** | a rotation bug — `next_turn_agent()` must skip seats at their cap. A parked pointer deadlocks the room | probe 4 in the reference: per-sender counts vs `max_turns` |
| A seat never got a turn at all | it is not in `participants`, or the seat id in its MCP config does not match the id in the row (`claude-code` vs `claude-code-2`) | probe 1; then the seat's `agents/CLIs/<cli>_agentN/` config |
| "It's not your turn" from an agent that should be up | the agent's `--agent-id` differs from what the row holds — identity is **config-only**, there is no auth | compare `participants` against each window's launch args |
| Ended at `max_turns` with fewer messages than expected | correct behaviour if **every** seat is spent. If one seat still had turns, that is the old first-agent-wins bug | probe 4 + `end_reason` |
| Ended with no deliverable, `conv_type` produces one | a non-lead signalled `done`. `blocks_premature_done()` should have refused it before the insert | probe 5: the last message's `signal` and `sender` vs `participant_roles` |
| Quiet but under the bar | not a stall yet. The bar is `max(600s, the run's own rhythm)` | `inspect_conversations.py watch --quiet` prints the bar |
| Nothing renders in the web UI | the UI reads `db/chat.db`; a custom `--db-path` on the agents writes a *different* file | probe 0 — resolve the path each side is actually using |
| `database is locked` | WAL missing, or a writer holding a transaction | probe 6 |
| Live locally, absent on the hosted mirror | the sidecar (`scripts/db_sync.py`) is down, or the column is not in its list | `scripts/healthcheck-app.ps1 -Repair:$false` |

## 2. The rotation rules worth knowing cold

Two rules that are **inseparable** — a change to one without the other deadlocks the room:

1. **`evaluate_stop()` ends a run when EVERY seat is spent, not the first.** It used to return on
   the first agent at `max_turns`, which in a round-robin is always agent 1 — so every later seat
   lost a turn, and a lead seated late lost the very turn it was briefed to post `signal='result'`
   on. Run #51 ended at 28 messages for "10 per agent" across three agents: 10 + 9 + 9.
2. **`next_turn_agent()` skips spent seats** and returns `None` when nobody is left. The stop rule
   alone parks the pointer on a finished agent, every send is rejected, and the pointer never
   advances again.

`tests/test_mcp_turns.py` pins both. If you touch either, run it.

Stops are `done` and `blocked` **only**. `result` is a deliverable marker, not a stop signal, and
a run may hold several — the **last one wins**.

## 3. When the row is fine, look at the window

If `current_turn` names a healthy-looking agent and the DB is consistent, the problem is in that
CLI process. In order of likelihood:

1. **It is waiting on an operator prompt.** A project `.mcp.json` in a Claude Code seat makes it
   ask for approval on every launch and stall a spawned agent — which is why seat 1 for Claude
   Code is *expected* to have no project `.mcp.json`.
2. **It exited.** Scroll its window for a traceback; the MCP server logs to stderr, never stdout
   (stdout is the JSON-RPC stream).
3. **It is asking *you* something between turns.** The `agent-chat` skill tells participants not
   to — if the skill is not installed, the agent has no idea it is in a turn-based loop.
   `get_kickoff()`'s `role_brief` reaches it even without skills; check the agent actually called it.
4. **Wrong seat id.** Identity is config-only: anything running with `--agent-id X` *is* X.

**Never kill an agent window to "reset" a run.** `scripts/healthcheck-app.ps1` deliberately never
touches spawned CLI windows for this reason — they are conversation participants.

## 4. Ending a run, when you have decided to

Three END paths, and each one fires delivery:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py stop 57
```

…or the web UI's stop button, or an agent signalling `done` / `blocked`. The two operator-stop
paths do **not** pass `ignore_scope`, so the launch-time delivery opt-in still stands.

Re-deliver afterwards if you need the bundle again — an explicit `deliver` *is* the opt-in:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver 57 --event complete
```

---

## Anti-patterns

- **Hand-editing `db/chat.db` to unstick a run.** Two processes write that file. If the row is
  genuinely wrong, the bug is in the rotation and belongs in `next_turn_agent()` /
  `evaluate_stop()`, where `tests/test_mcp_turns.py` will hold the fix.
- **Stopping before you have read the row.** It is irreversible and it destroys the transcript's
  natural ending.
- **Killing CLI windows.** They are participants.
- **Blaming the web UI for a missing conversation** before checking which `db/chat.db` each side
  resolved. `web.db.set_db_path()` also exports `$AGENT_CHAT_DB`; without that export a custom
  path reads conversations from one DB and personas from another.
- **Reading stdout for diagnostics.** `src/agent_chat_mcp.py` must never `print()` — use the
  stderr stream and `logs/`.
- **Treating a quiet run as a stall.** The bar is the run's own rhythm, floored at ten minutes.
- **Asking the watchdog to fix it.** It is read-only by design and a test greps it for `UPDATE` /
  `INSERT` / `send_message` / `subprocess`. A stalled run needs a human in a CLI window.
