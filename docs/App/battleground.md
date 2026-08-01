<div align="center">

# ⚔️ AgentBattleground

**Reference for the browser-extension front — arenas, the bridge API, the MCP loop, and the human-in-the-loop gate.**

</div>

---

Agent-Chat's normal mode has two CLI agents argue with each other in `chat.db`. AgentBattleground points the same machinery outward: a debate that already exists on a real web page becomes an **arena**, one CLI agent argues in it in character, and the operator decides whether any of it reaches the page.

- Extension install + operator walkthrough → [`extension/README.md`](../../extension/README.md)
- What the agent is told → [`skills/battleground/SKILL.md`](../../skills/battleground/SKILL.md)

## Architecture

An MCP server here is a stdio subprocess of a CLI — a browser extension can't speak to one. It doesn't need to. The existing architecture already solves this: **SQLite-WAL is the bus**, and the extension is simply another writer to it, going through the local web UI.

```
  Chrome extension                src/web_ui.py                  CLI agent (MCP)
 ┌────────────────┐             ┌──────────────────┐            ┌────────────────┐
 │ capture.js     │  POST       │ web/api/         │            │ get_arena      │
 │   scrape thread│────────────▶│  battleground.py │            │ submit_draft   │
 │                │             │        ↕         │  db/chat.db│ wait_for_verdict│
 │ panel.js       │  GET (3s)   │ web/db.py        │◀──────────▶│                │
 │   review draft │◀────────────│  bg_* helpers    │            │                │
 │   inject text  │             └──────────────────┘            └────────────────┘
 └────────────────┘
```

No daemon, no new port, no new auth surface. The extension needs the web UI running (`src/web_ui.py`), which is the same process the operator already keeps up for `/conversations`.

## The human-in-the-loop gate

**Nothing in this feature posts to a website.** That's structural, not a preference:

| Stage | Who acts | What happens |
|:---|:---|:---|
| Capture | operator | Clicks **Capture**; grants per-domain access the first time. |
| Draft | agent | `submit_draft` writes a row with `status='pending'`. No network egress. |
| Verdict | operator | Approve / reject / edit in the side panel. |
| Insert | extension | Types the approved text into the page's **existing** composer. Never clicks submit. |
| Post | operator | Presses the site's own post button. |

Plus: an AI-disclosure suffix appended at insert time (on by default, editable), house rules delivered in-band with every arena that forbid claiming to *be* a real person, and no static content scripts — the extension holds no standing access to any site.

The reason is straightforward: an agent that autoposts persona-driven replies into live threads is astroturfing, regardless of intent. Approving each reply is what keeps this a writing aid.

## Schema

Two tables, declared in all three `SCHEMA` mirrors (`src/agent_chat_mcp.py`, `src/web/db.py`, `src/orchestrator/seeding.py`) — see the schema rules in `CLAUDE.md`. They're new **tables**, not columns, so `CREATE TABLE IF NOT EXISTS` upgrades existing DBs on the next boot and no `_MIGRATIONS` rows are needed.

**`battleground_arenas`** — one captured debate.

| Column | Notes |
|:---|:---|
| `url` · `site` · `title` | Where it came from. `site` ∈ `reddit` / `x` / `hackernews` / `generic`. |
| `thread` | JSON array of posts: `{id, author, text, permalink?, score?, timestamp?, depth?}`. |
| `stance` | The operator's brief — which side, what to hit. |
| `agent_id` | Assigned CLI, or `NULL` for "whoever picks it up". |
| `persona_slug` · `persona_name` · `persona_body` | **Snapshot** of the card at capture time, so a later persona edit can't retroactively rewrite what a running arena's agent was told to be. |
| `status` | `open` / `closed`. |

**`battleground_drafts`** — one proposed reply.

| Column | Notes |
|:---|:---|
| `arena_id` · `agent_id` · `reply_to` | `reply_to` is the captured post's `id`, or `NULL` for top level. |
| `content` | What the agent wrote. |
| `rationale` | Private note to the operator. **Never posted.** |
| `status` | `pending` → `approved` / `rejected` / `posted`. |
| `verdict_note` | Operator feedback; the agent reads a rejection note as a revision brief. |
| `posted_text` | What actually went on the page — may differ from `content` if the operator edited. |

### Local-only, deliberately

Neither table appears in `_CONV_COLUMNS` / `_MSG_COLUMNS` / `_PERSONA_COLUMNS`, so the sidecar (`scripts/db_sync.py`) never ships them and they never reach the Fly mirror. Captured third-party page content stays on the machine that captured it. `tests/test_battleground.py` pins this.

On the hosted mirror the write routes 403 via `ReadOnlyMiddleware` like every other mutation — nothing special was needed, since the gate keys off HTTP method.

## Bridge API — `/api/battleground/*`

Handlers in `src/web/api/battleground.py`; SQL in `src/web/db.py` (`bg_*`).

| Route | Method | Purpose |
|:---|:---|:---|
| `/roster` | GET | Personas (debater roster only) + supported CLI ids + known sites. One round trip for the panel's pickers. |
| `/arenas` | GET | List, newest first. `?status=open\|closed`, `?agent=<cli>` (that agent's arenas **plus** unassigned ones). |
| `/arenas` | POST | Open an arena from a capture. `{url, site, title, thread[], stance?, agent_id?, persona?}` → `201 {arena}`. |
| `/arenas/{id}` | GET | Arena + all its drafts. This is what the panel polls every 3s. |
| `/arenas/{id}` | POST | Patch `stance` / `agent_id` / `persona` / `status`. Omitted fields are left alone. |
| `/arenas/{id}/capture` | POST | Merge a re-capture: `{thread: [...]}`. |
| `/arenas/{id}/delete` | POST | Delete, cascading drafts. |
| `/drafts/{id}/verdict` | POST | The gate: `{verdict: "approved"\|"rejected"\|"posted", note?, posted_text?}`. |

### Re-capture merging

`bg_merge_thread` matches on each post's `id`: known ids are **refreshed in place** (score and edit churn is normal), unknown ids are **appended** in capture order. That's what lets an operator re-capture a live thread mid-argument — the agent sees exactly the new replies instead of a reshuffled pile of duplicates. It's also why a site adapter's most important job is producing a *stable* post id (the site's own comment id wherever possible).

### Input scrubbing

Everything in a capture came from a page the operator happened to be looking at, so `_clean_posts` keeps only known fields, clips text to 8,000 chars and the thread to 200 posts, drops empty nodes, and coerces an unrecognised `site` to `generic`. Unknown keys are dropped rather than stored.

### Auth + CORS

- **Token (opt-in).** Unset `AGENT_CHAT_BATTLEGROUND_TOKEN` and the endpoints are open, matching the rest of the local web UI. Set it and every request needs `Authorization: Bearer <token>` (paste the same value into the panel's Settings).
- **CORS is narrow on two axes.** `ExtensionCorsMiddleware` (in `web/security.py`, always on) adds headers **only** for paths under `/api/battleground/` **and** only when the `Origin` is `chrome-extension://…`. A web page's origin is never echoed, so no site you visit can read the bridge even if it guesses the port. It sits outermost in the stack so a preflight — which carries no `Authorization` header by spec — isn't challenged by basic auth into failing.

## MCP loop

Four tools in `src/agent_chat_mcp.py`, shaped like the chat loop one layer out:

| Chat mode | Battleground |
|:---|:---|
| `get_kickoff()` | `get_arena(arena_id=None)` |
| `wait_for_turn()` | `wait_for_verdict(draft_id=None, timeout_seconds=120)` |
| `send_message(content)` | `submit_draft(arena_id, content, reply_to?, rationale?)` |
| `list_personas()` | `list_arenas(status="open")` |

`get_arena` is the only one that writes: opening an **unassigned** arena claims it (`agent_id` set to the caller), so a second CLI can't draft over the first. Re-calling it as the same agent is idempotent; another agent gets `assigned_elsewhere`.

Every arena payload carries `rules` — the house rules constant `_ARENA_RULES` — in-band, so an agent behaves correctly even on a CLI where the `battleground` skill isn't installed.

`wait_for_verdict` returns the arena's current thread alongside the verdict, and sets `operator_edited` when `posted_text` differs from what the agent wrote — so the agent can match the voice that actually shipped.

## Extension internals

See [`extension/README.md`](../../extension/README.md) for install and usage; the parts worth knowing from the Python side:

- **`src/capture.js`** is injected on demand as a single IIFE whose completion value is the capture, so `chrome.scripting.executeScript({files: […]})` gets it back directly and re-injection on the same tab can't collide with a previous run's declarations.
- **`src/panel/panel.js`** does all the HTTP. Not the service worker: reviewing a draft is human-paced, and an MV3 worker is torn down after ~30s idle, which would kill the poll.
- **Permissions** are `optional_host_permissions: ["*://*/*"]`, requested per-origin from a user gesture the first time you capture on a domain. The only standing host permissions are `127.0.0.1` and `localhost`.

## Tests

`tests/test_battleground.py` (21 cases, dual-mode like the rest of `tests/`):

```powershell
.\.venv\Scripts\python.exe tests\test_battleground.py
```

Covers the bridge contract, input scrubbing, re-capture merging, the verdict state machine, the "draft is born pending" invariant, the persona snapshot, the CORS gate on both axes, schema parity across all three `SCHEMA` mirrors, the sync exclusion, and the full MCP agent loop including arena claiming.

## Not built yet

Tracked on the [Roadmap](../Roadmap.md) row: a `/battleground` page in the web UI (the side panel is currently the only operator surface), adapters beyond the four, auto-recapture on a timer, a Firefox manifest, and folding arena outcomes into the model-comparison dashboard.
