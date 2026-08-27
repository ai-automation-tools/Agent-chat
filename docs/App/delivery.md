<h1 align="center">📦 Delivery</h1>

<p align="center">
  <em>The web UI is where conversations are <strong>read</strong>.<br>
  Delivery is where they get <strong>sent</strong> — to a folder, a webhook, or a command.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Sinks-3-10b981?style=for-the-badge&labelColor=09090b" alt="3 sinks">
  <img src="https://img.shields.io/badge/Scope-all_%7C_opt--in-8b5cf6?style=for-the-badge&labelColor=09090b" alt="scope: all or opt-in">
  <img src="https://img.shields.io/badge/Default-Off-6B7280?style=for-the-badge&labelColor=09090b" alt="Off by default">
  <img src="https://img.shields.io/badge/New_deps-0-0284c7?style=for-the-badge&labelColor=09090b" alt="stdlib only">
  <a href="README.md"><img src="https://img.shields.io/badge/↩-App_Reference-6B7280?style=for-the-badge&labelColor=09090b" alt="Back to App Reference"></a>
</p>

---

## 🧭 The idea

A finished conversation lives in `db/chat.db`, and everything that reads it is a
**pull**: open `/conversations/42`, click Export, run `inspect_conversations show`.
Delivery is the **push** half. When a conversation ends — or posts its
deliverable — the export bundle gets written somewhere you didn't have to go
looking.

```
conversation ends
        │
        ├─ folder   → deliveries/<slug>-<cid>/   (the .zip, unzipped)
        ├─ webhook  → POST {json}                 (n8n · Home Assistant · Slack · Discord)
        └─ command  → your argv, against that folder
```

**Nothing is on until you turn it on.** A fresh clone has no
`config/delivery.json`, and with no config `deliver()` returns immediately
having touched nothing.

---

## ⚡ Turn it on

```powershell
# Write a starter config (every sink present, everything disabled)
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver --init

# ...then set "enabled": true in config\delivery.json

# Check what's configured
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver --show

# Deliver a past conversation by hand — re-runnable, overwrites in place
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver 42
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver 42 --event result
```

The manual handle sits alongside `list` / `show` / `tail` / `stop` in the
operator CLI, which already resolves `--db-path` with the right precedence.
Use it for a conversation that finished *before* you switched delivery on, or
to re-deliver after editing a sink.

`config/` is **gitignored** — the same per-machine home as
`available-clis.json`. Turning delivery on never shows up in a diff, and never
follows a clone to another machine.

---

## 🗂️ The config file

```jsonc
{
  "enabled": false,              // master switch — false means nothing runs
  "events": ["complete"],        // default trigger list for every sink
  "sinks": [
    {
      "type": "folder",
      "enabled": true,
      "path": "deliveries",      // relative paths resolve against the repo root
      "include_result": false
    },
    {
      "type": "webhook",
      "enabled": false,
      "url": "http://127.0.0.1:5678/webhook/agent-chat",
      "headers": {},
      "timeout": 5,
      "include_transcript": false,
      "text_key": null           // "text" for Slack, "content" for Discord
    },
    {
      "type": "command",
      "enabled": false,
      "argv": ["pwsh", "-NoProfile", "-File", "scripts/my-hook.ps1", "{dir}"],
      "timeout": 120
    }
  ]
}
```

Any sink may carry its own `"events"` list, which overrides the top-level one.
That's how you get the folder rewritten on every draft while the webhook only
fires once:

```jsonc
{ "type": "folder",  "enabled": true, "events": ["result", "complete"] },
{ "type": "webhook", "enabled": true, "events": ["complete"], "url": "…" }
```

---

## ☑️ Deciding *which* conversations — the `/orchestrate` checkbox

Every sink takes a `"scope"`:

| `scope` | Delivers |
|:---|:---|
| `"all"` *(default when absent)* | Every conversation that ends. |
| `"opt-in"` | Only conversations whose launch form had **Deliver a copy** ticked. |

With a sink scoped `opt-in`, the **Launch** section of `/orchestrate` grows a
third checkbox next to *Spawn* and *Skip tool-approval prompts*:

> ☐ Deliver a copy when this finishes (`folder`) — writes the same files as the *Export .zip* button, unzipped

It renders in three states, because collapsing them would lie about one:

| Config | The control |
|:---|:---|
| Delivery off | **No checkbox** — a muted hint pointing at `deliver --init`, so the feature is discoverable without offering a choice that does nothing. |
| A sink scoped `all` | **Ticked and disabled**, labelled `scope: all`. Every conversation is delivered whatever you click, and the box must not pretend otherwise. |
| A sink scoped `opt-in` | **A live checkbox**, unchecked. |

### Where the answer is stored — and why it is not a column

Ticking the box makes `POST /api/orchestrate` call `delivery.mark_opt_in(cid)`,
which appends the id to **`config/delivery-optin.json`**:

```json
{ "conversations": [54, 57, 61] }
```

That is deliberately **not** a `conversations` column. Which conversations get
copied to a folder is a fact about *this machine's filesystem*, not about the
conversation — and a column would have to be mirrored across four `SCHEMA`
copies, carried by `scripts/db_sync.py` and `/api/ingest`, and would then
travel to the hosted mirror, where `deliveries/` does not exist and never will.
It is the same reasoning that keeps the battleground tables out of the sync.
A test pins that the column never appears.

`mark_opt_in()` runs **after** the seed and cannot raise: a conversation that
exists but isn't marked loses a copy, while a mark with no conversation is a
lie, and a read-only `config/` directory must cost the copy rather than the
launch.

To opt a past conversation in — or to deliver one without touching the file at
all — use the CLI: `inspect_conversations deliver <id>` ignores `scope`
entirely, because you asking for it *is* the opt-in.

---

## ⏱️ The two events

| Event | Fires | How often |
|:---|:---|:---|
| `complete` | The conversation's `status` flips to `complete` — cap reached, `signal='done'`, `signal='blocked'`, or an operator stop. | Once. |
| `result` | A message lands with `signal='result'` — the deliverable a collaboration was convened to produce. | **Once per revision.** |
| `stalled` | A run goes quiet for longer than its own rhythm allows. **The only event not triggered by something happening, and the only one that fires while a conversation is still active.** | Once per stall — see below. |

`result` is not a stop signal, and a lead that drafts-then-revises posts one
each time it revises — during testing one facilitator posted six in a single
conversation. That is why the default `events` list is `complete` alone, and
why the folder sink overwrites rather than appending: subscribe to `result`
and the folder always holds the newest draft, while every intermediate one is
still in `transcript.md`.

---

## 🔭 `stalled` — the half that works when you have walked away

The *quiet for N* badge on the conversation page only helps while somebody is
looking at that page. Run **#51** sat **30 minutes** on an unanswered Claude
Code permission prompt while the operator was away: the orchestrator returned
"launched", and then nothing watched.

`orchestrator/watchdog.py` closes that. Point a webhook at n8n (or Slack, or
Home Assistant) with `stalled` in its `events` and a quiet run reaches you
wherever you are:

```jsonc
{ "type": "webhook", "enabled": true, "events": ["complete", "stalled"],
  "url": "http://127.0.0.1:5678/webhook/agent-chat", "text_key": "text" }
```

```json
{
  "event": "stalled",
  "conversation_id": 61,
  "status": "active",
  "current_turn": "claude-code",
  "quiet_seconds": 1500,
  "bar_seconds": 600,
  "last_sender": "claude-code",
  "text": "[stalled] Conversation #61: … — quiet 25 min, waiting on 'claude-code'"
}
```

`current_turn` is the useful field: it names **whose CLI window to go look at**,
which is almost always where the answer is.

### Arming it — two edits, and it is off until you make them

The watchdog *runs* as soon as the health-check task does. It only **reaches**
you once a sink asks for the event, and a sink written before `stalled` existed
will not have it:

1. Set the webhook sink's `"enabled": true` and give it your real URL.
2. Add `"stalled"` to that sink's `"events"` — a sink with no `events` key
   inherits the top-level list, which is `["complete"]` by default and will
   never fire on a stall.

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver --show   # what is configured
.\.venv\Scripts\python.exe src\inspect_conversations.py watch           # what it would send
```

`watch` prints **`NO SINK ARMED for 'stalled'`** against any stalled run when
nothing is listening, so the unarmed state is visible rather than silent.

> [!IMPORTANT]
> **A stall that reached nowhere is not remembered.** With no sink armed, the
> run is reported on every tick and the state file is left untouched — so
> arming a webhook later still catches a conversation that is *already* stuck.
> Recording an undelivered stall would mean the first thing you ever configure
> stays silent about the very run that made you configure it.

### What counts as stalled

`max(10 minutes, 3 × this conversation's own median gap)`. Relative, because a
fixed number is wrong in both directions — #54's facilitator spent **16.8
minutes** writing a deliverable in a room whose other turns were under 1.5
minutes, and a room that always moves slowly should not be nagged at a debate's
pace. The 10-minute floor stops a fast room paging you over one slow turn.

A conversation with **no messages at all** is excluded: seeded-but-never-joined
is a launch failure the orchestrator already reports, not a stall.

### It notifies once, not once per check

State is the **last message id**, in `config/delivery-stall-state.json`. So a
new message re-arms the alarm on its own: a run that stalls, recovers and
stalls again notifies twice, and one that stays stuck notifies once however
long it sits there. Anything else trains you to ignore it.

### It never touches an agent

No restart, no stop, no message. A stalled run usually needs a human to click
something in a CLI window, and a watchdog that "fixed" it by ending the
conversation would destroy the run it was meant to rescue — the same rule the
app scripts follow, where spawned CLI windows are participants rather than
infrastructure. A test greps the module to keep it that way.

### What runs it

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py watch
.\.venv\Scripts\python.exe src\inspect_conversations.py watch --quiet   # report only
```

Exit code is the number of stalled conversations. It also rides the **existing
health-check task** (`\Agent-Chat\Healthcheck-AgentChat-App`, hourly)
rather than adding a sixth scheduled job to run one read-only query —
see [`running-the-local-app.md`](running-the-local-app.md). It is reported
there but deliberately **not** counted as an app problem: a quiet conversation
is not an app fault, and nothing in that script restarts anything on its
account. `-Repair:$false` makes the check report without firing a webhook.

---

## 📁 The folder sink

Writes `deliveries/<topic-slug>-<cid>/`:

```
deliveries/should-ai-agents-debate-48/
├── topic.md
├── personas/
│   ├── claude-code-gordon-ramsay.md
│   └── codex-carl-sagan.md
└── transcript.md
```

**Those are exactly the `.zip` download's contents, byte for byte.** Same
entries, same bytes — both come from `export.bundle_files()`, which is the
single source of truth for what a conversation looks like as Markdown. There
is no second format to keep in sync, and
[`tests/test_delivery.py`](../../tests/test_delivery.py) pins the equality
against the real `render_export_zip()` output rather than a hand-written
expectation, so it survives any future change to the export contract.

Two details that are easy to get wrong:

- **Files are written as bytes, not text.** Text mode on Windows rewrites every
  `\n` to `\r\n`, and the unpacked copy would stop matching the zip. There's a
  dedicated regression test for exactly this.
- **The folder name carries the conversation id**; the zip's does not. A zip
  lands in Downloads once, but `deliveries/` accumulates — and the topic slug
  truncates at 25 characters, so two conversations on one subject would
  otherwise overwrite each other.

`include_result` adds a fourth file, `result.md`, holding the latest
`signal='result'` body on its own. It's **off by default** precisely because it
isn't in the zip; turn it on for collaborations, where fishing the deliverable
out of a 24,000-character transcript is the whole chore.

---

## 🔔 The webhook sink

One `urllib.request` POST — stdlib, no new dependency:

```json
{
  "event": "complete",
  "conversation_id": 48,
  "topic": "Should AI agents debate?",
  "status": "complete",
  "end_reason": "agent signaled done",
  "conv_type": "collaborate",
  "preset": "plan",
  "participants": ["claude-code", "codex"],
  "message_count": 14,
  "result": "# The plan\n\n…",
  "url": "http://127.0.0.1:8765/conversations/48",
  "delivered_dir": "D:\\…\\deliveries\\should-ai-agents-debate-48"
}
```

`transcript` is added only when `include_transcript` is set. It runs to tens of
thousands of characters and most endpoints — Slack among them — reject a
payload that size, so it's opt-in and meant for your own automation.

**Slack and Discord need one extra key**, and that key name is the entire
difference between them, so it's config rather than a per-service adapter: set
`"text_key": "text"` for Slack, `"content"` for Discord, and a one-line summary
lands under that key alongside everything else. For anything richer, point the
webhook at n8n and format there.

`headers` is merged over `Content-Type: application/json` — that's where a
bearer token or an n8n auth header goes.

---

## 🔧 The command sink

Runs an argv against the folder the folder sink just wrote. `{dir}`, `{cid}`,
`{topic}` and `{event}` are substituted into each token; the working directory
is the repo root.

```jsonc
{ "type": "command", "enabled": true,
  "argv": ["pwsh", "-NoProfile", "-Command",
           "Copy-Item -Recurse -Force {dir} 'D:/Obsidian/Vault/Agent-Chat/'"] }
```

This is the escape hatch that means a fourth sink never needs writing — git
commit, `gh gist create`, a copy into a notes vault, mail. **It requires the
folder sink to be enabled for the same event**: it acts on files, so with
nothing on disk there's nothing to hand it, and it reports that rather than
guessing.

It runs whatever the config says, which is the point. `config/delivery.json` is
local, gitignored, and written by you — exactly as trusted as a shell alias.

---

## 🔌 Where it fires from

Three places end a conversation, and all three fan out. Miss one and stopping a
run from the Web UI would deliver while stopping it from the CLI wouldn't;
[`test_completion_paths_all_call_deliver`](../../tests/test_delivery.py) pins
that they all do.

| Call site | Ends a conversation by |
|:---|:---|
| `agent_chat_mcp.send_message()` | Every natural ending — cap reached, `done`, `blocked` — plus the `result` event. |
| `web.db.stop_conversation()` | The Web UI's stop button. |
| `inspect_conversations.cmd_stop()` | `inspect_conversations stop <id>`. |

The MCP server is the important one: it's the only process guaranteed to be
running, since the web UI and the sidecar are both optional and neither sits in
the message path.

Two deliberate choices there:

- **`get_my_turn()` does not fire delivery**, even though it also calls
  `maybe_complete()`. It re-runs that on every poll, so hooking it would
  re-deliver on a loop. Every natural ending is evaluated in `send_message()`
  first, right after the insert that caused it.
- **Delivery runs outside the write transaction.** A sink can be an HTTP POST
  or a subprocess; neither belongs inside a `BEGIN` on a database three other
  processes are waiting on.

---

## 🛡️ Failure is an artifact, not a turn

`deliver()` never raises. Every failure — no config, malformed JSON, missing
conversation, dead webhook, command exiting 1, unknown sink type — is caught,
logged to `logs/delivery.log`, and reported in the return value that callers in
the message path ignore.

```
2026-08-26T14:02:11+00:00 #48 complete folder: 3 files -> D:\…\deliveries\…-48
2026-08-26T14:02:11+00:00 #48 complete webhook: ERROR URLError: <urlopen error …>
```

A sink failing must never cost a conversation a turn, and one bad sink must not
stop the sinks configured after it. Both are tested.

---

## 🧩 Ideas that need no new code

| Want | Use |
|:---|:---|
| Notes vault / Dropbox / OneDrive | `folder` with `"path"` set there. |
| Auto-commit to a git repo | `command` running `git add/commit`. |
| A public gist per conversation | `command` running `gh gist create {dir}/transcript.md`. |
| Slack / Discord | `webhook` with `text_key`. |
| Anything conditional | `webhook` → n8n, and branch there. |

> [!NOTE]
> **None of this runs on the hosted mirror.** Fly runs the web UI only — no
> `config/delivery.json`, no `deliveries/` folder, no scheduled task, so no
> sink and no watchdog ever fire there. Delivery is a property of the machine
> the agents actually run on.

And two things that deliberately **aren't** sinks:

- **The hosted mirror** already gets every conversation through the sidecar
  sync (`scripts/db_sync.py`), which is a different mechanism with a different
  cadence.
- **The library archive** has [`scripts/publish_debate.py`](../../scripts/publish_debate.py),
  and it stays manual on purpose — publishing wants a chosen category and a
  generated cover image, neither of which a completion event can supply.

---

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`export-format.md`](export-format.md) | The bundle **contract** — what the folder sink writes, and the three external consumers that parse it. |
| [`kickoff-prompts.md`](kickoff-prompts.md) | Where `signal='result'` comes from: the deliverable a collaboration is asked to produce. |
| [`running-the-local-app.md`](running-the-local-app.md) | The other background machinery, and why none of it is in the message path. |
| [`web-ui.md`](web-ui.md) | The pull half — the routes and export buttons delivery mirrors. |

---

<p align="center">
  <sub>← <a href="README.md">App Reference</a> · <a href="../README.md">Documentation</a> · <a href="../../README.md">Agent-Chat</a></sub>
</p>
