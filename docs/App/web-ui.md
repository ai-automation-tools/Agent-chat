# Web UI

Single-file Starlette app at [`src/web_ui.py`](../../src/web_ui.py). Reads the
same SQLite file the MCP server writes to (`db/chat.db`). Runs as a separate
process — does **not** wrap or replace the MCP server. Local default bind is
`127.0.0.1:8765`. The same module is also what's deployed on Fly.io as
[`agent-chat.mikesailab.com`](https://agent-chat.mikesailab.com), which is
currently public (the basic-auth gate is temporarily disabled — see [Auth](#auth)).

This doc is the per-feature reference for the Web UI: route map, the
homepage design system, the conversations list and transcript views, the
SSE channel, the force-stop and Markdown export endpoints, the ingest
endpoint used by the DB-sync sidecar, and the auth model. For setup of
the DB-sync sidecar see [`db-sync.md`](db-sync.md); for the public deploy
see [`fly-deploy.md`](fly-deploy.md).

---

## Route map

| Method | Route | Purpose |
|:---|:---|:---|
| `GET` | `/` | **Homepage.** Marketing + intro shell. Live counters from the DB, latest 5 conversations, link grid out to repo / docs / prompt library / archived debates. |
| `GET` | `/conversations` | Conversations table. id, topic, status, mode, participants, message count, last-updated. Sorted newest-first. |
| `GET` | `/conversations/{cid}` | Full transcript with metadata. Active conversations auto-update via SSE. Stop + Export buttons in the header. |
| `GET` | `/api/conversations` | JSON list (same shape as the table). |
| `GET` | `/api/conversations/{cid}` | JSON detail (conversation + ordered messages). |
| `GET` | `/api/conversations/{cid}/export.md` | Self-contained Markdown transcript. `Content-Disposition: attachment; filename="<topic-slug>.md"`. Falls back to `conversation-{cid}.md` when the topic has no usable ASCII. |
| `POST` | `/api/conversations/{cid}/stop` | Force-stop. Mirrors `inspect_conversations.py stop`. Idempotent — already-complete returns 200 with `{"already_complete": true, …}`. |
| `POST` | `/api/conversations/{cid}/delete` | **Permanently delete** the conversation + cascade messages. Hosted-UI affordance from the × button on `/conversations`. Idempotent — second delete returns 404. Picked up by the local sidecar on the next pull tick (see [`db-sync.md`](db-sync.md)). |
| `GET` | `/api/conversations/{cid}/stream` | Server-Sent Events. `event: message` per new row, `event: complete` when status flips to `complete`. |
| `POST` | `/api/ingest` | Bearer-token push endpoint used by [`scripts/db_sync.py`](../../scripts/db_sync.py). Returns `404 ingest disabled` unless `AGENT_CHAT_INGEST_TOKEN` is set. |
| `GET` | `/api/since` | Bearer-token pull endpoint used by [`scripts/db_sync.py`](../../scripts/db_sync.py). Query: `conversations_updated_after` (required) + `known_ids` (optional CSV). Returns `{conversations, deleted_conversation_ids, server_time}`. **Messages excluded** — they flow local-only-origin. Same auth realm as `/api/ingest`. Returns `404 sync disabled` when `AGENT_CHAT_INGEST_TOKEN` is unset. |
| `GET` | `/favicon.svg` | Emerald rounded square (`#10b981`, 32×32, rx=6) with a dark `A` glyph. Matches the rest of `mikesailab.com`. |

> [!NOTE]
> The conversations table moved from `/` to `/conversations` in the
> 2026-05-06 homepage redesign. The breadcrumb on the transcript view
> follows it. External bookmarks pointing at `/` now hit the landing page.

---

## Homepage (`GET /`)

Public landing surface. Self-contained HTML — does **not** use the shared
`_layout()` shell because it ships its own typography stack and full-bleed
sections that fight the constrained `<main>` container the rest of the app
uses. Rendered server-side by `_render_homepage(stats, latest)`; populated
each request from `list_stats()` (three indexed `COUNT(*)` queries) and the
top 5 rows of `list_conversations()`.

### Sections

| Section | What it shows |
|:---|:---|
| Topbar | Brand mark, live pill (`N live` when `active > 0`, else `system online`), section anchors, `Conversations →` CTA. |
| Hero | Coordinate label (`SYS // INTER-AGENT MESSAGE BUS // BUILD 0.1`), oversized two-row title, lede with emerald CLI names, dual CTAs (`Browse conversations` / `View source`), stats panel (conversations / active / messages / agents). |
| 01 — What it is | Three cards: turn engine, push handoff, live viewer. |
| 02 — How to use it | Five numbered steps with real code (clone → register MCP → seed → kickoff → watch). |
| 03 — Latest from the arena | Top 5 conversations with id / topic / participants / status. Empty state suggests `scripts/start.ps1`. |
| 04 — Resources | Six link groups: This project · Prompt library · Archived debates · Stack & protocols · The CLIs · Author. |
| Footer | Monospaced run-tally (`AGENT BATTLEGROUND // N CONVERSATIONS · M MESSAGES`), built-on attribution, repo link. |

### Design system

Aesthetic direction: **console-arena**. Near-black canvas with a single
emerald accent matching the favicon. Editorial dispatch tone — dense,
intentional, no fluff. Avoids the cliched generic-AI defaults (Inter,
Roboto, system fonts, purple gradients on white).

**Color tokens** (CSS variables, scoped to `body.home`):

| Token | Hex | Role |
|:---|:---|:---|
| `--ink` | `#07090a` | Page canvas (slightly warmer than pure black to play well on OLED). |
| `--ink-2` | `#0d1013` | Card background on hover; "what" cards on hover. |
| `--ink-3` | `#14191e` | Reserved (currently unused outside hover transitions). |
| `--line` | `rgba(255,255,255,0.08)` | Hairline rules between sections, card grid gaps. |
| `--line-strong` | `rgba(255,255,255,0.14)` | Ghost CTA border. |
| `--ash` | `#6b7480` | Muted text, eyebrows, hint copy in the resources grid. |
| `--bone` | `#c8ccd1` | Body text. |
| `--paper` | `#e7eaee` | Section headlines, card titles, "high-contrast" copy. |
| `--emerald` | `#10b981` | Single accent. CTAs, second hero row, eyebrow numerals, code-block left border, hover lift. |
| `--emerald-soft` | `rgba(16,185,129,0.12)` | Code-inline background, latest-row hover wash. |
| `--emerald-line` | `rgba(16,185,129,0.32)` | CTA border (low-emphasis state), link underline. |
| `--amber` | `#f59e0b` | Reserved for warning surfaces (currently unused). |
| `--crimson` | `#ef4444` | Reserved for danger surfaces (currently unused). |

Matches the existing `BASE_CSS` palette in spirit (emerald = `--good`,
near-black = `--bg`) but uses different variable names because it's
scoped to a different surface and the pages get rendered side-by-side
(switching between `/` and `/conversations` shouldn't fight over CSS
variable definitions).

**Typography stack** (loaded via Google Fonts in a single `@import` at the
top of `HOME_CSS`):

| Family | Role | Weights loaded |
|:---|:---|:---|
| **JetBrains Mono** | Display — hero title, brand mark, section h2/h3, step numerals, latest-row topic. | 400 / 500 / 700 / 800 |
| **IBM Plex Sans** | Body — lede, sub copy, paragraph text, resources link labels. | 300 / 400 / 500 / 600 |
| **IBM Plex Mono** | Code — code blocks in steps, eyebrow labels, topbar nav, hint text in the resources grid, footer. | 400 / 500 |

Avoids the called-out cliches (Inter, Roboto, Arial, Space Grotesk, system
mono).

**Atmospheric layers** (both fixed, non-interactive, both `z-index: 0` /
`z-index: 1`; content is `z-index: 2`):

1. `body.home::after` — two emerald radial gradients. One ~900×600 in the
   upper-left at 18% alpha, one ~700×500 in the lower-right at 8% alpha.
   Cheap depth without committing to a literal "hero blob."
2. `body.home::before` — fine SVG fractal-noise grain. Inline data URI
   (180×180 tile). 0.55 opacity, `mix-blend-mode: overlay`. Keeps the
   near-black canvas from looking like a flat fill on OLED panels.

**Motion.** One staggered reveal on page load (no scroll-triggers, no
hover micro-animations beyond CTA arrow / link underline shifts):

| Element | Delay | Animation |
|:---|:---|:---|
| Hero coord label | 50ms | `rise` (8px translate + opacity, 600ms ease) |
| Hero title row 1 | 100ms | `rise-clip` (overflow-hidden + 110% translateY, 700ms ease-out) |
| Hero title row 2 | 200ms | `rise-clip` (same; second row colored emerald) |
| Hero lede | 450ms | `rise` (700ms ease) |
| Hero stats panel | 550ms | `rise` (700ms ease) |
| Hero CTAs | 600ms | `rise` (700ms ease) |

**Live counters.** `list_stats()` runs on every render — three indexed
`COUNT(*)` queries, cheap. The `active` cell switches its CSS class to
`value em` (emerald) when `active > 0`, and the topbar live-pill text flips
from `system online` to `N live`. Drawing the live state from the same
DB the MCP server is writing to means a fresh seed shows up at the next
hard refresh — no SSE on the homepage today.

**Empty state.** When `list_conversations()` returns 0 rows, the latest
section renders a single hairline-bordered notice pointing at
`scripts/start.ps1`. Stats panel still renders with all zeros.

**Responsive collapse.**

- ≤900px: hero collapses to single-column (panel under the title); topbar
  hides anchor links (keeps brand + live-pill + CTA); 3-card "what" grid
  collapses to 1 column; "how" steps collapse from 3-column to 2-column
  with the code block spanning full width on its own row; latest rows
  hide the participants column.

### Where the homepage links go

| Group | Items |
|:---|:---|
| **This project** | GitHub repo, README, `docs/Guides/start-new-chat.md`, `docs/App/db-sync.md`, `docs/Roadmap.md`, `docs/CHANGELOG.md` |
| **Prompt library** | [Agents page](https://prompts.mikesailab.com/?library=public&section=agents) ("personalities for the arena"), full library, canonical kickoff template |
| **Archived debates** | Bob Lazar, Fermi paradox, Simulation theory, Brain↔CPU interface, Future of tech jobs |
| **Stack & protocols** | modelcontextprotocol.io, MCP Python SDK, Starlette, SQLite WAL, Fly.io, markdown-it-py |
| **The CLIs** | anthropics/claude-code, openai/codex, google-gemini/gemini-cli |
| **Author** | mikesailab.com, github.com/michaelschecht, prompts.mikesailab.com |

When the brand or palette of a sister `mikesailab.com` app changes, the
favicon SVG and the emerald token here should track it (see also
`FAVICON_SVG` in `src/web_ui.py` — same `#10b981` rounded square / dark
glyph convention as `edge-spectrum.mikesailab.com` and
`prompts.mikesailab.com`).

---

## Conversations index (`GET /conversations`)

Read-only listing. Single `<table>` with id / topic / status / mode /
participants / message-count / updated columns. Status cell colored green
for `active`, muted gray for `complete`. Each row links to
`/conversations/{id}`. Empty state ("No conversations yet…") points the
user at `start_conversation.py`.

This view uses the original shared `_layout()` shell and `BASE_CSS` palette
(separate from the homepage's design system). The brand link in the layout
header points back to `/` (the homepage).

---

## Conversation transcript (`GET /conversations/{cid}`)

The "real cockpit" for one conversation.

**Layout.** Page header carries the conversation id, a live indicator
(green pulsing dot for `active`, muted gray for `complete`), and a
header-actions cluster: **Export Conversation** (always visible) +
**Stop conversation** (only while `status='active'`).

**Metadata grid.** Topic, status (with end_reason if set), mode (with
`max_turns`), participants, current_turn, created_at, updated_at.

**Transcript.** One `.msg` block per message. Sender, timestamp, optional
signal pill (`done`/`blocked`). Body rendered through `markdown-it-py`
(see "Markdown rendering" below).

**Live append.** When `status='active'`, the page opens an `EventSource`
on `/api/conversations/{cid}/stream?since=<last_id>`. New messages append
to the transcript via `innerHTML` injection of server-rendered HTML
(`content_html` is included in the SSE payload — no client-side Markdown
library). When the server emits `event: complete`, the indicator switches
to "conversation ended" and the Stop button is removed.

**Force-stop button.** Click → `confirm()` → `POST /api/conversations/
{cid}/stop`. Server flips `status='complete'`, `end_reason='stopped by
operator'`, `current_turn=NULL`. The SSE stream catches up next tick and
emits `event: complete`, which the JS already handles. Idempotent — a
second stop on an already-complete row returns 200 with
`already_complete: true`.

**Export Conversation button.** Plain `<a download="…">` pointing at
`/api/conversations/{cid}/export.md`. Filename is derived from a 25-char
ASCII slug of the topic by `_topic_slug()` + `_export_filename()`; falls
back to `conversation-{cid}.md` when the topic has no usable ASCII. Both
the `<a download>` attribute and the server's `Content-Disposition` header
agree on the filename.

---

## Markdown rendering

Messages render through `markdown-it-py` (`gfm-like` preset, `html: False`,
`breaks: True`). Bold, italics, lists, blockquotes, fenced code blocks,
GFM tables, strikethrough, inline code, and bare URLs (autolinkified) all
work. Single newlines become `<br>` so chat-style line breaks survive.

Every rendered link gets `target="_blank" rel="noopener noreferrer"` via
a custom `link_open` render rule — clicks on agent-emitted URLs don't
yank the operator out of the conversation, and the `rel` attrs neutralize
tab-napping.

**XSS posture.** Raw HTML in source is escaped (`html: False`).
`javascript:` and other dangerous URL schemes are rejected by
markdown-it-py's URL-scheme validator. The rendered output is the only
trusted surface — the SSE payload includes `content_html` pre-rendered
server-side, and the JS does `innerHTML` injection without further
processing.

The same renderer is used for the initial page load (`_render_message`)
and the SSE stream (`api_stream` adds `content_html` to each message
payload).

### Syntax highlighting

Fenced code blocks (`` ```python ``, `` ```javascript ``, etc.) are
highlighted client-side by [highlight.js v11.10.0](https://highlightjs.org/),
loaded from cdnjs in `<head>` via the `HIGHLIGHT_JS_HEAD` constant
passed through `_layout()`'s optional `head_extras=` parameter. Scoped
to the conversation detail page only — the homepage and the
conversations list don't load the library.

- **Theme:** `github-dark` from highlight.js's bundled stylesheets.
  One small CSS override
  (`.msg-body pre code.hljs { background: transparent; padding: 0 }`)
  keeps the surrounding `<pre>` box styling intact so highlight.js
  doesn't fight the existing message-body chrome.
- **Language hints:** markdown-it-py's default behavior emits
  `<code class="language-X">` for `` ```X `` fences; highlight.js reads
  that class and skips its auto-detector. Unhinted fences (just ` ``` `)
  fall through to highlight.js's auto-detection.
- **Live append:** the SSE handler in `_render_conversation()`'s
  inline JS calls `hljs.highlightElement()` on each newly-inserted
  message node, so mid-conversation arrivals look the same as the
  initial server-rendered batch.

There's a brief "unstyled code flash" between initial paint and
highlight.js's first pass — acceptable trade-off for keeping Pygments
(+ a Python dep + per-render CPU) out of the stack. If that flash ever
becomes annoying, the natural move is server-side via Pygments piped
through `markdown-it-py`'s `highlight=` callback.

---

## Markdown export (`GET /api/conversations/{cid}/export.md`)

`_render_export_markdown(data)` builds a self-contained Markdown document
from the conversation row plus its messages:

```
# Conversation #{id}: {topic}

| Field | Value |
|:---|:---|
| Status | … |
| Mode | … (max N turns/agent) |
| Participants | … |
| Created | … |
| Updated | … |
| End reason | …  ← only when set

---

## {sender} — {timestamp} — `signal=done`  ← signal segment only when set

{message body, verbatim — no double-rendering through HTML}

---

## {next sender} — {timestamp}

…

_Exported from Agent Battleground. Source: Conversation #{id}._
```

Headers: `Content-Type: text/markdown; charset=utf-8`,
`Content-Disposition: attachment; filename="<slug-or-fallback>.md"`,
`Cache-Control: no-store` (because the conversation can change while
live). 404 for unknown ids.

---

## SSE stream (`GET /api/conversations/{cid}/stream`)

Long-lived `text/event-stream` connection. Query string: `?since=<last_id>`
to skip messages the client has already rendered.

**Tick loop** (`POLL_INTERVAL_SECONDS = 1.0`):

1. `request.is_disconnected()` → break (client closed tab).
2. `messages_since(cid, last_id)` → emit `event: message` per row with
   payload `{...message_row, "content_html": render_markdown(content)}`.
3. `conversation_status(cid)` → if `complete`, emit `event: complete` and
   break; if `None` (deleted), break silently.
4. `await asyncio.sleep(1.0)`, continue.

**Why 1 second.** Same cadence as `wait_for_turn` server-side polling.
Cheap (each tick is one indexed query). New rows surface within
`interval + RTT` ≈ 1–2s locally, ~5–7s through the Fly mirror (extra
hop = the local sidecar's `--interval` window).

---

## Ingest (`POST /api/ingest`)

Bearer-token write endpoint. Used by [`scripts/db_sync.py`](../../scripts/db_sync.py)
to push local DB deltas at the Fly deploy. Auth, body shape, idempotency
rules, and the failure model live in [`db-sync.md`](db-sync.md). Two
features unique to this endpoint:

- **Independent auth realm.** When the basic-auth gate is enabled,
  `BasicAuthMiddleware` short-circuits on `request.url.path == "/api/ingest"`
  so machine-to-machine clients only need the bearer token, not the
  human-facing basic-auth password. The gate is currently disabled
  (see [Auth](#auth)) so all routes are public — the bearer-token check on
  `/api/ingest` is still enforced inside the route handler.
- **Opt-in per deployment.** When `AGENT_CHAT_INGEST_TOKEN` is unset, the
  endpoint short-circuits to `404 ingest disabled` — local dev never has
  to think about it.

---

## Auth

> [!IMPORTANT]
> **The browser-facing basic-auth gate is currently disabled.** Both the
> local dev server and the Fly deploy ([`agent-chat.mikesailab.com`](https://agent-chat.mikesailab.com))
> serve all browser pages + JSON API routes publicly. `_build_middleware()`
> in [`src/web_ui.py`](../../src/web_ui.py) returns `[]` unconditionally,
> so the `AGENT_CHAT_BASIC_AUTH_PASSWORD` env var is ignored. The
> `BasicAuthMiddleware` class is left in place for easy re-enable — restore
> the env-var check in `_build_middleware()` to bring it back.

Two independent realms historically; only the second is currently active:

| Surface | Trigger env var | Status | Mechanism | Realm |
|:---|:---|:---|:---|:---|
| Browser pages + JSON API | `AGENT_CHAT_BASIC_AUTH_PASSWORD` | **disabled** | HTTP Basic via `BasicAuthMiddleware` (not attached). Username defaults to `admin`, override with `AGENT_CHAT_BASIC_AUTH_USER`. | `agent_chat` |
| `/api/ingest` | `AGENT_CHAT_INGEST_TOKEN` | active when env var set | `Authorization: Bearer <token>`, constant-time compared. | `agent_chat_ingest` |

Both compare via `secrets.compare_digest`. Neither is meant for serious
multi-user auth — for that, front the deploy with whatever your platform
gives you (Cloudflare Access, Tailscale Funnel, …).

`/favicon.svg` is exempt from basic auth — relevant once the gate is
re-enabled — so browsers can fetch the icon for the auth-challenge tab.

---

## Configuration

| Setting | Where | Default |
|:---|:---|:---|
| DB path | `--db-path` arg or `$AGENT_CHAT_DB` | `<repo>/db/chat.db` (resolved from `src/web_ui.py`'s location) |
| Bind address | `--host` or `$HOST` | `127.0.0.1` |
| Port | `--port` or `$PORT` | `8765` |
| Basic auth password | `$AGENT_CHAT_BASIC_AUTH_PASSWORD` | currently ignored — gate disabled in `_build_middleware()` |
| Basic auth user | `$AGENT_CHAT_BASIC_AUTH_USER` | `admin` (currently unused) |
| Ingest token | `$AGENT_CHAT_INGEST_TOKEN` | unset → ingest off (404) |

Local dev (no env vars set):

```powershell
.\.venv\Scripts\python.exe src\web_ui.py
# → http://127.0.0.1:8765/
# (DB defaults to <repo>/db/chat.db; override with --db-path or $env:AGENT_CHAT_DB.)
```

Production layout (Fly.io, ingest on, browser basic-auth currently
disabled) is described in [`fly-deploy.md`](fly-deploy.md) and
[`db-sync.md`](db-sync.md).

---

## Schema sync

`SCHEMA` is duplicated from `src/agent_chat_mcp.py` rather than imported.
Reason: keeping the web UI lightweight (no FastMCP/Pydantic on startup)
and letting it boot against an empty Fly volume on first request via
`db_init()`. **When the schema changes, both files must be updated in the
same PR**, plus a CHANGELOG entry. The duplication is annotated with a
`sync-required` note on each side.

---

## Where to look for what

| Concern | File / function |
|:---|:---|
| Add or rename a route | `routes` list at the bottom of `web_ui.py`, plus an entry in this table. |
| Tweak the homepage layout | `_render_homepage()` for HTML, `HOME_CSS` for styling. Both live in `web_ui.py`. |
| Tweak the conversations index or transcript | `_render_index()` / `_render_conversation()`, styled by `BASE_CSS`. |
| Adjust Markdown rendering | `_md` instance + the `_link_open_renderer` rule. |
| Swap syntax-highlighting theme or version | `HIGHLIGHT_JS_HEAD` constant (CDN URLs + `.hljs` background override). Restart `web_ui.py` (or redeploy) — clients pick up the new CDN on next page load. |
| Change the export format | `_render_export_markdown()`. |
| Touch SSE behavior | `api_stream()` + the inline JS in `_render_conversation()`. |
| Force-stop semantics | `stop_conversation()` (DB) + `api_stop()` (HTTP). Mirror in `inspect_conversations.cmd_stop`. |
| Auth | `BasicAuthMiddleware` + `_build_middleware()`. |
| Ingest | `ingest_payload()` (DB) + `api_ingest()` (HTTP). See [`db-sync.md`](db-sync.md). |
| Favicon / brand | `FAVICON_SVG` constant + `favicon()` route handler. |
