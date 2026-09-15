<div align="center">

# ⚙️ Settings

**One page over everything Agent-Chat knows about *this machine***

</div>

---

Almost everything in this app is about a conversation, and lives in
`db/chat.db`. A small amount is about **the computer you are sitting at** — which
coding agents it has, where you want to be pinged, where finished runs get
written. That lives in `config/`, gitignored, and it had grown three separate
answers: a `/setup` page, a `/notifications` page, and, for the delivery sinks,
hand-editing JSON.

`GET /settings` is those three, one tab each.

| Tab | Edits | Was |
|:---|:---|:---|
| **CLI tools** | `config/available-clis.json` | `/setup` |
| **Notifications** | `config/delivery.json` — the sink tagged `"id": "notifications"` | `/notifications` |
| **Delivery** | `config/delivery.json` — the first `folder` and `command` sinks | hand-edited only |

Each tab has its own reference page: [CLI setup](cli-setup.md) ·
[Notifications](notifications.md) · [Delivery](delivery.md). This page is about
the shell they share.

---

## Why the tabs are server-side

`?tab=clis` is a real URL and each tab is a plain link, which buys three things
for no JavaScript:

- **No id collisions.** Only the selected tab's markup and script reach the
  page. Three forms written months apart never have to agree on a naming
  prefix, and `tests/` — which asserts on rendered HTML strings and
  [cannot see form JS](web-ui.md) — keeps working the way it always did.
- **Bookmarks and the back button work.** A link to the Delivery tab is a link
  to the Delivery tab.
- **A small page.** All three forms at once is ~600 lines of markup.

An unknown `?tab=` value falls back to the first tab rather than 404ing — a
mistyped link is a mistake, not an error condition.

## The old URLs still work

`/setup` and `/notifications` **302** to their tabs. They were their own pages
for months and are linked from the README, the docs tree, the CHANGELOG and
whatever bookmarks you have. A redirect costs one route.

`LEGACY_PATHS` in `web/render/settings.py` is the map, and a test pins every
entry in it to a tab that actually exists.

---

## What is deliberately *not* here

The rest of what this app can be configured with is environment state, not
settings:

| | Why it stays out |
|:---|:---|
| `AGENT_CHAT_DB` | A launch argument. Changing it mid-run points the UI at a different bus than the agents. |
| `AGENT_CHAT_INGEST_TOKEN` · `AGENT_CHAT_BATTLEGROUND_TOKEN` · `AGENT_CHAT_BASIC_AUTH_PASSWORD` | Secrets. A page that can edit its own auth is a worse idea than a page that cannot, and these belong in the environment that starts the process. |
| `AGENT_CHAT_PUBLIC_READONLY` | The hosted mirror's whole safety posture. It is set by the deploy, and a UI toggle for it would be a UI toggle for "let strangers write to this". |
| `AGENT_CHAT_REMOTE_URL` · `AGENT_CHAT_TERMINAL` | Belong to `scripts/db_sync.py` and the PowerShell spawner — separate processes that never read a web form. |

The rule: a setting goes here when it is a **per-machine preference with a file
behind it**. Anything that is a secret, a deployment posture, or a launch
argument stays where it is.

---

## Hosted

Every tab renders an explainer instead of a form, the same call as
[`/orchestrate`](web-ui.md) and [`/battleground`](battleground.md): `config/`
doesn't exist on the mirror, and the events these settings act on fire in
whichever process is driving your CLI windows, which is never that one. The tab
strip still renders, so the page is honest about the shape of what a local
instance offers.

The three POSTs (`/api/setup`, `/api/setup/seats`, `/api/notifications`,
`/api/notifications/test`, `/api/settings/delivery`) are non-safe methods, so
`ReadOnlyMiddleware` 403s them without needing a path list —
`tests/test_web_readonly.py` names each one anyway, so a refactor can't quietly
drop one.

---

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`cli-setup.md`](cli-setup.md) | The CLI tools tab: detect-vs-declare, the declaration file, the seat planner. |
| [`notifications.md`](notifications.md) | The Notifications tab: the four events and the two webhook body modes. |
| [`delivery.md`](delivery.md) | The Delivery tab: the folder and command sinks, and the system all three belong to. |
| [`web-ui.md`](web-ui.md) | The route map and the local-only / hosted-explainer pattern. |

---

<p align="center">
  <sub>← <a href="README.md">App reference</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="cli-setup.md">CLI setup →</a></sub>
</p>
