---
name: agent-chat-delivery
description: >-
  Work on Agent-Chat's push half — delivery sinks (folder / webhook / command), the Notifications
  settings tab, the opt-in list, and the stall watchdog. Covers config/delivery.json's shape, the
  four events (started / result / complete / stalled), the scope + opt-in rule, the four call
  sites that end a conversation, and why a sink may never raise. Use for "set up notifications",
  "get a push when a debate finishes", "ntfy / Discord / Slack / Gotify webhook", "deliver the
  transcript to a folder", "run a command after a conversation", "add a delivery event", "the
  watchdog isn't firing", "delivered folder doesn't match the zip", "my hand-written sink got
  overwritten", or any edit to src/orchestrator/delivery.py, watchdog.py, or
  src/web/api/notifications.py / delivery_settings.py.
---

# Delivery, notifications and the watchdog

The web UI is the **viewer** — a conversation lives in `db/chat.db` and you go look at it.
Delivery is the **push** half: when a run finishes (or posts its deliverable, or goes quiet), fan
the export bundle out to a folder, an HTTP endpoint, or a local command.

**Off unless `config/delivery.json` exists.** That folder is gitignored per-machine setup, the
same home as `available-clis.json`, so turning delivery on never touches the repo. Never ship a
default that delivers.

Working config examples: [`references/config-examples.md`](references/config-examples.md).

---

## 1. It renders nothing

The folder sink writes `export.bundle_files()` **verbatim** — a delivered folder is the `.zip`
bundle unpacked, **byte for byte**. That is why it calls `write_bytes` and not `write_text`:
Windows text mode would rewrite every `\n` to `\r\n` and the unpacked copy would stop matching the
zip. `tests/test_delivery.py` compares against a real `render_export_zip()` output, not a fixture.

**A format change belongs in `src/orchestrator/export.py`** and its contract doc
(`docs/App/export-format.md`), never in a sink. The one non-bundle file, `result.md`, is opt-in
(`include_result: true`) for exactly that reason.

## 2. Three sinks, deliberately

| Sink | Writes | Notes |
|:---|:---|:---|
| `folder` | the unzipped bundle into `deliveries/<slug>-<cid>/` | re-delivering overwrites in place, so the newest result wins |
| `webhook` | a JSON POST, or a templated text body | n8n, Home Assistant, ntfy, Slack, Discord, Gotify |
| `command` | an argv run against the written folder | **requires the folder sink on the same event** — it acts on files |

The `command` sink is the escape hatch that means a fourth sink never needs writing. It runs
whatever the config says, which is the point: the file is per-machine, gitignored and
operator-written, so it is exactly as trusted as a shell alias.

`{dir}`, `{cid}`, `{topic}`, `{event}` substitute into each argv token.

## 3. Four events, and `started` is the odd one

`EVENTS = ("started", "result", "complete", "stalled")`

| Event | Fires from | Times |
|:---|:---|:---|
| `started` | `seeding.seed_conversation()`, **after the connection closes** | once, at seed |
| `result` | a message landing with `signal='result'` | **once per revision** — a lead that drafts-then-revises posts several |
| `complete` | the conversation's status flipping | once |
| `stalled` | `watchdog.check()` | once per stall, re-armed by a new message |

**`started` is deliberately NOT in the default `events` list.** At seed time the bundle has no
messages, so a folder sink inheriting it would write an empty transcript. It is for notifying, not
for writing an artifact nobody produced. `tests/test_notifications.py` pins this by seeding for
real rather than grepping for the call.

`stalled` is the only event not triggered by something *happening*, and the only one that can
fire while a conversation is still active.

## 4. A sink costs an artifact, never a turn

**`deliver()` must never raise.** Every failure is caught, logged to `logs/delivery.log`, and
returned as a string the message path ignores. One failing sink must not stop the next.

The exception: **`send_test()` deliberately raises** where `deliver()` swallows — a human is
waiting for the answer on the Settings page.

Always call `deliver()` **outside** the write transaction.

## 5. The call sites

Three END paths, four call sites, and a test pins all three:

- `send_message()` in `src/agent_chat_mcp.py`
- `web.db.stop_conversation()`
- `inspect_conversations.cmd_stop()`
- plus `seeding.seed_conversation()` for `started`

**Adding another way to end a conversation means adding another `deliver()` call.**

**Do NOT hook `get_my_turn()`** — it re-runs `maybe_complete()` on every poll and would
re-deliver on a loop.

## 6. Scope + opt-in, never a column

A sink is `scope: "all"` (default) or `"opt-in"`. The `/orchestrate` Launch checkbox writes
`config/delivery-optin.json`.

Do **not** promote this to a `conversations` column. It is a fact about *this machine's
filesystem*: it would have to cross four `SCHEMA` copies plus `scripts/db_sync.py` and
`/api/ingest`, and it would reach a hosted mirror where `deliveries/` does not exist.
`tests/test_delivery.py` pins its absence.

The `/orchestrate` control has **three** states — off / forced by `scope: "all"` / live. Don't
collapse them: a disabled-but-ticked box is the honest rendering of "every conversation is
delivered anyway".

`optin_offered()` **excludes** the notify sink by id, because that sink is scoped `"all"` and
counting it makes the box read as forced.

**The CLI passes `ignore_scope=True`; the automatic hooks don't.** An explicit
`inspect_conversations deliver <id>` *is* the opt-in. The two operator-stop paths are not — the
launch-time decision stands.

## 7. Notifications are ONE sink of this, not a second system

Settings → Notifications (`src/web/api/notifications.py`) renders `config/delivery.json` as a form
and owns exactly the sink tagged `delivery.NOTIFY_SINK_ID` (`"notifications"`).

- **Saving merges.** A hand-written folder or command sink survives — load-bearing for a
  gitignored file with no history.
- **Services are a *rendering* (`SERVICES`), never a sink type.** `body: "text"` plus a templated
  `template` / `headers` covers ntfy; `text_key` covers Slack (`"text"`), Discord (`"content"`),
  Gotify/ntfy-JSON (`"message"`). A per-service adapter for each would be four modules differing
  by one string.
- **An unknown `{placeholder}` renders empty, never raises.** `quiet_seconds` exists only on
  `stalled`, and a config that dies on the day it matters is worse than none.

### The two tabs own sinks differently

| Tab | Owns by | Because |
|:---|:---|:---|
| **Notifications** | **id** (`NOTIFY_SINK_ID`) | it created the sink |
| **Delivery** | **position** — the *first* folder sink and the *first* command sink | folder/command sinks predate any UI and carry no `id` |

`api/delivery_settings.py` edits the first of each type **in place**, preserves keys the form does
not know, and reports later ones in `extra_sinks` rather than touching them. Tagging them on save
would silently rewrite a hand-written config — the one thing a form over a gitignored,
history-less file must not do. It **never** touches the webhook sink; two pages writing one sink
is how that file loses work.

## 8. The watchdog reuses delivery

`src/orchestrator/watchdog.py` makes a stall a third event beside `result` and `complete`, so an
operator with a webhook already configured needs no new plumbing.

- **Read-only, and it must never touch an agent.** A stalled run needs a human to click something
  in a CLI window; ending the conversation would destroy the run it was meant to rescue. A test
  greps the module for `UPDATE` / `INSERT` / `send_message` / `subprocess`.
- The bar is `max(MIN_STALL_SECONDS=600, export.quiet_threshold_seconds(msgs))` — a run's own
  rhythm, floored at ten minutes.
- A conversation with **no messages at all** is excluded: seeded but never joined is a launch
  problem the orchestrator already reports, not a stall.
- Notifies **once per stall**, keyed on the last message id, so a new message re-arms it.
- Rides the existing health-check task (`scripts/healthcheck-app.ps1`) rather than adding a sixth
  scheduled job, and its count **never feeds that script's exit code**.

## 9. The CLI

Lives in `inspect_conversations`, not in the module — `orchestrator` is a package, so
`python -m orchestrator.delivery` cannot resolve from the repo root.

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver 57 --event complete
.\.venv\Scripts\python.exe src\inspect_conversations.py watch          # stall check
```

---

## Checklist

- [ ] Config change → edit `config/delivery.json` only; never commit it, never add a repo default
- [ ] New sink type → it must swallow its own exceptions and return a string
- [ ] New END path → a `deliver()` call **outside** the transaction, plus a case in `tests/test_delivery.py`
- [ ] New event → add to `EVENTS`, decide whether it belongs in the **default** `events` list (`started` shows why it might not), and template-document it
- [ ] Format change → `export.py` + `docs/App/export-format.md` + its three external consumers, not a sink
- [ ] `.\.venv\Scripts\python.exe tests\test_delivery.py` and `tests\test_notifications.py`
- [ ] `docs/App/delivery.md` / `notifications.md` + `docs/CHANGELOG.md`

## Anti-patterns

- **Rendering anything in a sink.** The folder output must stay byte-identical to `export.zip`.
- **Letting `deliver()` raise.** A failed webhook must not cost an agent its turn.
- **Hooking `get_my_turn()`.** It polls; you would deliver in a loop.
- **A `delivered` / `opt_in` column.** Scope lives in the config and the opt-in file.
- **A per-service webhook module.** `SERVICES` + `text_key` + `template` is the whole design.
- **Tagging untagged sinks on save**, or letting the Delivery tab write the webhook sink.
- **A watchdog that acts.** No writes, no `send_message`, no subprocess. It notifies a human.
- **Appending on `result`.** It fires per revision; the folder sink overwrites, and the default
  `events` list is `complete` alone.
