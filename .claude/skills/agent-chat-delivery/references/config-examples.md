# `config/delivery.json` — shape and worked examples

Gitignored, per-machine, no history. **Missing file → delivery is off.** A malformed file is
logged and treated as absent rather than raised: a typo in an optional config must not take the
MCP server down mid-conversation.

Path: `<repo>/config/delivery.json`, beside `available-clis.json` and `delivery-optin.json`.

Start from the shipped template rather than a blank file — it writes `delivery.STARTER_CONFIG`
**disabled**, so nothing delivers until you flip `"enabled": true`:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver --init
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver --show   # what it resolves to
```

---

## Top level

```jsonc
{
  "enabled": true,            // master switch — false disables every sink
  "events": ["complete"],     // DEFAULT events for sinks that don't say.
                              // Defaults to ["complete"] alone: a per-revision
                              // folder rewrite is opt-in.
  "sinks": [ /* … */ ]        // fired in config order
}
```

A sink runs when: top-level `enabled` is true **and** its own `enabled` is true **and** `event` is
in its `events` (falling back to the top-level list) **and** its `scope` admits the conversation.

## Keys every sink may carry

| Key | Default | Meaning |
|:---|:---|:---|
| `type` | — | `folder` · `webhook` · `command` |
| `enabled` | — | required; a sink with no `enabled: true` never fires |
| `events` | top-level `events` | subset of `started` / `result` / `complete` / `stalled` |
| `scope` | `"all"` | `"opt-in"` restricts it to conversations in `delivery-optin.json` |
| `id` | — | only `"notifications"` is meaningful — it marks the sink the Settings tab owns |

---

## 1. Folder — the bundle on disk

```jsonc
{
  "type": "folder",
  "enabled": true,
  "path": "deliveries",        // relative paths resolve against the repo root
  "include_result": true,      // adds result.md — NOT part of the zip bundle
  "events": ["complete", "result"]
}
```

Writes to `<path>/<topic-slug>-<cid>/`. Contents are exactly `export.bundle_files()` — same
entries, same bytes as the `.zip` download. Re-delivering **overwrites in place**, so a run that
posts six results leaves the newest on disk.

`include_result` is off by default because `result.md` is the one file that is not in the bundle,
and the bundle is a contract.

## 2. Webhook — JSON mode (the default)

```jsonc
{
  "type": "webhook",
  "enabled": true,
  "url": "http://127.0.0.1:5678/webhook/agent-chat",
  "timeout": 8,
  "include_transcript": false   // adds the whole rendered markdown to the payload
}
```

The payload — also the template's field set:

`event` · `conversation_id` · `topic` · `status` · `end_reason` · `conv_type` · `preset` ·
`participants` (list) · `message_count` · `result` · `current_turn` · `url` · `delivered_dir`

Two derived fields exist for templates only: **`summary`** (a one-line human summary) and
**`participants_text`** (the list joined with commas — a list renders as its Python repr inside a
template, which is exactly wrong on a lock screen).

On a `stalled` event the watchdog's facts ride along: `quiet_seconds`, `bar_seconds`,
`last_sender`, `last_message_id`. They are added with `setdefault` and can never clobber the
fields above.

**An unknown `{placeholder}` renders empty, never raises.** `quiet_seconds` exists only on
`stalled`, and a config that dies on the day it matters is worse than none.

## 3. Webhook — one-key services

Slack, Discord and Gotify differ by **one string**. That is why there is no per-service module.

```jsonc
{ "type": "webhook", "enabled": true,
  "url": "https://hooks.slack.com/services/…",
  "text_key": "text",                       // discord: "content" · gotify: "message"
  "template": "**{summary}**\n{url}" }
```

## 4. Webhook — text mode (ntfy topic URLs)

```jsonc
{
  "type": "webhook",
  "id": "notifications",
  "enabled": true,
  "service": "ntfy",                        // rendering hint only; delivery ignores it
  "url": "https://ntfy.sh/my-agent-chat",
  "body": "text",
  "template": "{topic}\n{status} — {participants_text}\n{url}",
  "headers": { "X-Title": "Agent-Chat: {event}", "X-Tags": "robot" },
  "events": ["complete", "stalled"],
  "scope": "all",
  "timeout": 8
}
```

`body: "text"` sends `template` as a plain-text body. Title, priority and tags ride in headers
there, so **header values are templated too**.

This is exactly what the Settings → Notifications tab writes. An ntfy topic is a **secret**:
whoever knows it can read your notifications.

## 5. Command — the escape hatch

```jsonc
{
  "type": "command",
  "enabled": true,
  "argv": ["pwsh", "-File", "scripts/publish.ps1", "{dir}", "{cid}"],
  "timeout": 120,
  "events": ["complete"]
}
```

Substitutions: `{dir}` · `{cid}` · `{topic}` · `{event}`. Runs with `cwd` = repo root.

**Requires a folder sink on the same event** — this sink acts on files, so with nothing on disk
there is nothing to hand it. `deliver()` raises a clear error otherwise (and swallows it, as always).

---

## A complete working file

Folder copies for the runs you ticked, a push for every run, and a git commit after the copy.

```json
{
  "enabled": true,
  "events": ["complete"],
  "sinks": [
    {
      "type": "folder",
      "enabled": true,
      "path": "deliveries",
      "include_result": true,
      "scope": "opt-in"
    },
    {
      "type": "command",
      "enabled": true,
      "argv": ["git", "-C", "{dir}", "add", "-A"],
      "scope": "opt-in",
      "timeout": 60
    },
    {
      "type": "webhook",
      "id": "notifications",
      "enabled": true,
      "service": "ntfy",
      "url": "https://ntfy.sh/my-agent-chat",
      "body": "text",
      "template": "{topic}\n{status} — {participants_text}\n{url}",
      "headers": { "X-Title": "Agent-Chat: {event}", "X-Tags": "robot" },
      "events": ["complete", "stalled"],
      "scope": "all",
      "timeout": 8
    }
  ]
}
```

Note the ordering: the **folder sink must come before the command sink**, since sinks fire in
config order and the command needs `{dir}`.

## `config/delivery-optin.json`

Written by the `/orchestrate` Launch checkbox. A flat list of conversation ids:

```json
[51, 54, 57]
```

---

## Verify

```powershell
# Re-deliver a finished run by hand. The CLI passes ignore_scope=True — an
# explicit deliver IS the opt-in.
.\.venv\Scripts\python.exe src\inspect_conversations.py deliver 57 --event complete

# Stall check, read-only.
.\.venv\Scripts\python.exe src\inspect_conversations.py watch --quiet

# Failures land here, never in the conversation.
Get-Content logs\delivery.log -Tail 20
```

The Settings → Notifications tab has a **Send test** button; unlike `deliver()`, `send_test()`
deliberately raises, so a bad URL says so instead of failing quietly.
