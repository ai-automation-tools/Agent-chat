<div align="center">

# 🔔 Notifications

**Be told when a run finishes, gets stuck, starts, or ships something**

</div>

---

A conversation runs in CLI windows you have almost certainly walked away from.
Run **#51** stalled for **30 minutes** on an unanswered Claude Code permission
prompt while nobody was at the machine — the orchestrator said "launched" and
then nothing watched.

This is the surface that fixes that: pick a service, paste a topic or a URL,
tick what you want to hear about, send yourself a test.

> [!IMPORTANT]
> **Notifications are not a new subsystem.** They are one sink of
> [delivery](delivery.md), which already fanned a finished conversation out to a
> webhook and already carried the stall event. What was missing was a way to turn
> it on without knowing the shape of `config/delivery.json`. Everything on this
> page is that config file, rendered as a form.

---

## The page — `GET /settings?tab=notifications`

One of three tabs on [Settings](web-ui.md), beside **CLI tools** and **Delivery**
— every tab edits something under `config/`. (`/notifications` still works; it
redirects here.) Local only: the config file is per-machine, and
the events fire in whichever process is driving your CLI windows, which is never
the hosted mirror. Hosted, the route renders an explainer rather than a dead
form.

| Control | What it does |
|:---|:---|
| **Service** | ntfy · Gotify · Discord · Slack · raw webhook. One at a time. |
| **Topic / URL** | The one thing that differs per service. The label and the hint change with the radio. |
| **Server** | Only shown for the two you can self-host (ntfy, Gotify). |
| **Tell me when…** | The four events, ticked independently. `complete` + `stalled` are the default pair. |
| **Send me these notifications** | Keeps the settings, stops the sending. |
| **Send test notification** | Posts stand-in facts through the **real** transport, using what's in the form — so it answers "will this work" *before* a save, not after. |

Saving **merges**: it replaces the one sink tagged `"id": "notifications"` and
leaves every other sink in the file alone. A folder or command sink you wrote by
hand survives a save from the browser — which matters, because the config is
gitignored with no history, so clobbering it would lose work with no way back.

---

## The four events

| Event | Fires | Notes |
|:---|:---|:---|
| **`complete`** | Once, when the run ends | Whatever ended it — a `done`/`blocked` signal, the turn cap, or you stopping it from the UI or the CLI. |
| **`stalled`** | While the run is **still open**, once per stall | The [watchdog](delivery.md)'s event. The bar is the conversation's own rhythm, not a fixed number — a debate turn is seconds, and a facilitator writing a deliverable legitimately took 16.8 minutes in run #54. Never before 10 minutes, whatever the rhythm says. A new message re-arms it. |
| **`started`** | The moment a run is seeded | From `/orchestrate` or `start_conversation.py`. The **only** event where the bundle is empty — there are no messages yet — which is why it is not in the default `events` list: a folder sink that inherited it would write an empty transcript. |
| **`result`** | Each time a message lands with `signal='result'` | Collaborations only. A lead that drafts-then-revises posts one per revision, so this can fire several times in one run. |

> [!NOTE]
> **Nothing here can fail a conversation.** `deliver()` swallows every
> exception and logs to `logs/delivery.log`; a dead endpoint, a wrong token or
> a full disk costs you the message, never the turn. That guarantee is
> load-bearing enough to have its own test.

---

## What the page writes

One ordinary delivery sink. This is the ntfy shape — the others differ by a
handful of keys:

```json
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
```

`scope` is **always `"all"`** here. Notifications are about every run, not the
ones ticked for a filesystem copy — and `optin_offered()` excludes this sink by
id, so the `/orchestrate` *save a copy* checkbox doesn't render as
forced-and-ticked just because you asked to be pinged. Different question,
different sink.

---

## Two body modes, and no per-service adapters

Notification services split cleanly in half, and the split is the whole reason
this needed any code at all.

| Mode | Sends | For |
|:---|:---|:---|
| **`json`** (default) | The full payload. `text_key` adds a human summary under a key the receiver reads. | Discord (`content`), Slack (`text`), Gotify (`message`), n8n, Home Assistant, your own script. |
| **`text`** | `template`, rendered as a plain-text body. Title, priority and tags ride in **headers**, so header *values* are templated too. | ntfy's topic-URL mode, and anything that wants a string. |

An ntfy adapter, a Gotify adapter, a Slack adapter and a Discord adapter would
be four modules that differ by one string each. Naming the key or the template
in config is deliberately all there is — the same call `delivery.py` made when
it added `text_key` rather than a Slack module.

### Template fields

Any key of the webhook payload, plus two conveniences:

| Field | |
|:---|:---|
| `{summary}` | The one-line human summary — `[complete] Conversation #7: AI jobs — complete`. The default text body. |
| `{participants_text}` | `claude-code, codex`. `{participants}` is the JSON array and renders as a Python list on a lock screen, which is exactly wrong; reshaping it would break whatever automation is already parsing that key. |
| `{event}` `{conversation_id}` `{topic}` `{status}` `{end_reason}` `{conv_type}` `{preset}` `{message_count}` `{result}` `{current_turn}` `{url}` | The payload proper. |
| `{quiet_seconds}` `{bar_seconds}` `{last_sender}` | Watchdog facts — present on `stalled` and nowhere else. |

**An unknown `{placeholder}` renders empty rather than raising.** A template
naming `quiet_seconds` must not blow up on the three events that lack it — a
notification config that works until the day it matters (the stall it was
configured to catch) is worse than no config.

---

## Setting it up by hand

The page is a convenience, not a gate. Everything it writes you can write
yourself — and for a second sink, or a folder/command sink, you have to.
`inspect_conversations deliver --init` writes a starter file with one example of
each, including the ntfy block above.

Recipes, all as entries in `sinks`:

**ntfy** — no account, self-hostable. See the JSON above.

**Gotify** — `"url": "https://your-server/message?token=APPTOKEN"`,
`"text_key": "message"`.

**Discord** — `"url"` is the channel webhook, `"text_key": "content"`.

**Slack** — `"url"` is the incoming webhook, `"text_key": "text"`.

**Anything else** — leave `body` and `text_key` off and it gets the full JSON
payload. That is the n8n / Home Assistant / own-script path, and it is why a
sixth service never needs code.

---

## Where to look when nothing arrives

1. **`logs/delivery.log`** — every attempt, every failure, with the exception
   text. A sink that fails is logged and ignored; it is never raised.
2. **Both switches.** Delivery has a master `enabled` and each sink has its own.
   The page reports them separately so it can say *which* is off.
3. **The event.** `stalled` needs the [health-check task](running-the-local-app.md)
   running — the watchdog rides it rather than adding a sixth scheduled job.
4. **Send test notification.** It goes through the same `post_webhook()` a real
   event uses. If the test lands and the event doesn't, the problem is the
   event, not the service.

---

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`delivery.md`](delivery.md) | The system this is one sink of — the folder and command sinks, the three completion call sites, the opt-in model. |
| [`running-the-local-app.md`](running-the-local-app.md) | The scheduled health check the stall watchdog rides on. |
| [`web-ui.md`](web-ui.md) | Route map and the local-only / hosted-explainer pattern this page follows. |

---

<p align="center">
  <sub>← <a href="README.md">App reference</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="delivery.md">Delivery →</a></sub>
</p>
