<div align="center">

# ⚔️ AgentBattleground

**Reference for the browser-extension front — arenas, the bridge API, the MCP loop, and the human-in-the-loop gate.**

</div>

---

Agent-Chat's normal mode has two CLI agents argue with each other in `chat.db`. AgentBattleground points the same machinery outward: a debate that already exists on a real web page becomes an **arena**, one CLI agent argues in it in character, and the operator decides whether any of it reaches the page.

> **Just want to use it?** Start with the step-by-step operator guide:
> [`docs/Guides/battleground.md`](../Guides/battleground.md). This page is the
> reference behind it.

- Step-by-step walkthrough → [`docs/Guides/battleground.md`](../Guides/battleground.md)
- In-app explainer + install steps → **`GET /extension`** (renders on the local instance and the hosted mirror; the local copy also probes `/api/battleground/healthz` so you can see whether the bridge is reachable). The pitch, not the controls.
- Arena **console** → **`GET /battleground`** (local only) — every arena, every draft, and the verdict buttons, without the captured tab open. See [The arena console](#the-arena-console-get-battleground).
- Extension install + site adapters → [`extension/README.md`](../../extension/README.md)
- What the agent is told → [`skills/battleground/SKILL.md`](../../skills/battleground/SKILL.md)
- Paste-ready operator prompts → [`prompts/Battleground/`](../../prompts/Battleground/README.md)

## Architecture

An MCP server here is a stdio subprocess of a CLI — a browser extension can't speak to one. It doesn't need to. The existing architecture already solves this: **SQLite-WAL is the bus**, and the extension is simply another writer to it, going through the local web UI.

```
  browser extension               src/web_ui.py                  CLI agent (MCP)
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

Two tables, declared in all three `SCHEMA` mirrors (`src/agent_chat_mcp.py`, `src/web/db.py`, `src/orchestrator/seeding.py`) — see the schema rules in `CLAUDE.md`. They arrived as new **tables**, so `CREATE TABLE IF NOT EXISTS` covered existing DBs; the one column added since (`battleground_arenas.reply_to`, 2026-08-01) carries a `_MIGRATIONS` row in each of the three mirrors, so an older `db/chat.db` picks it up on the next boot of whichever process opens it first.

**`battleground_arenas`** — one captured debate.

| Column | Notes |
|:---|:---|
| `url` · `site` · `title` | Where it came from. `site` is an adapter label — `KNOWN_SITES` in `web/api/battleground.py` (`reddit` / `x` / `hackernews` / `youtube` / `linkedin` / `substack` / `discourse` / `disqus` / `generic`); anything else is coerced to `generic`. |
| `thread` | JSON array of posts: `{id, author, text, permalink?, score?, timestamp?, depth?}`. |
| `stance` | The operator's brief — which side, what to hit. |
| `reply_to` | The captured post the **operator** picked for the agent to answer (**Answer this one** in the panel's capture preview), or `NULL` for "you choose". Validated against the stored thread on write. Distinct from the drafts table's `reply_to`, which is what the agent actually answered. |
| `agent_id` | Assigned CLI, or `NULL` for "whoever picks it up". |
| `persona_slug` · `persona_name` · `persona_body` | **Snapshot** of the card at capture time, so a later persona edit can't retroactively rewrite what a running arena's agent was told to be. `persona_slug` is `NULL` for a [custom card](#custom-personas) — there's no registry row to point at. |
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
| `/healthz` | GET | `{ok, db, schema, readonly, token_required, error?}`. **The one route outside the token check** — its whole job is explaining why the others fail, and "your token is wrong" is one of the answers. It returns no data, and the CORS gate still limits readers to `chrome-extension://` origins. |
| `/roster` | GET | Personas (debater roster only) + supported CLI ids + known sites + `launch` (per-CLI `{dir, exe}` for the panel's handoff card). One round trip for the panel's pickers. |
| `/arenas` | GET | List, newest first. `?status=open\|closed`, `?agent=<cli>` (that agent's arenas **plus** unassigned ones). |
| `/arenas` | POST | Open an arena from a capture. `{url, site, title, thread[], stance?, reply_to?, agent_id?, persona?, persona_instructions?, persona_name?}` → `201 {arena}`. |
| `/arenas/{id}` | GET | Arena + all its drafts. This is what the panel polls every 3s. |
| `/arenas/{id}` | POST | Patch `stance` / `reply_to` / `agent_id` / `persona` (or `persona_instructions`) / `status`. Omitted fields are left alone; `reply_to: ""` clears the target, since omission already means "leave it". |
| `/arenas/{id}/capture` | POST | Merge a re-capture: `{thread: [...]}`. |
| `/arenas/{id}/delete` | POST | Delete, cascading drafts. |
| `/drafts/{id}/verdict` | POST | The gate: `{verdict: "approved"\|"rejected"\|"posted", note?, posted_text?}`. |

`CLI_LAUNCH` (the `launch` map) duplicates the `Dir`/`Exe` columns of the `$Clis` registry in `scripts/lib/spawn-agents.ps1`, in a different language in a different directory — the same footgun as `KNOWN_SITES` ↔ `capture.js`, and pinned the same way by `tests/test_battleground.py`. It is only ever rendered as a string for the operator to copy; **nothing in the bridge or the extension spawns a process.**

### Re-capture merging

`bg_merge_thread` matches on each post's `id`: known ids are **refreshed in place** (score and edit churn is normal), unknown ids are **appended** in capture order. That's what lets an operator re-capture a live thread mid-argument — the agent sees exactly the new replies instead of a reshuffled pile of duplicates. It's also why a site adapter's most important job is producing a *stable* post id (the site's own comment id wherever possible).

Posts captured from a third-party comment iframe carry a namespaced id (`disqus:501`) so the host page and the frame can't collide on a bare numeric id. The namespace is derived from the platform, not the capture, so it stays stable across re-captures like everything else.

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

**`rules` is read live from the module constant on every `get_arena` call — it is never stored on the arena row.** Two consequences worth knowing:

- Editing `_ARENA_RULES` reaches **every arena, including ones captured before the edit**. No re-capture, no migration. This is the opposite of a conversation's `kickoff_template`, which is snapshotted onto the row at seed time and so only affects newly seeded runs.
- The change reaches an agent only after its **CLI restarts** — each CLI runs its own MCP server process, which holds the imported module in memory. A session started before the edit keeps serving the old rules.

Persona bodies follow the *snapshot* rule instead (`persona_body` is copied onto the arena at capture time), so a persona-card edit does need a fresh capture. Rules and personas deliberately differ here: house rules are policy and should apply everywhere at once; a persona is the identity a specific arena was opened with.

**Rule 7 (`write like a person`)** carries the distilled [`humanizer`](../../skills/humanizer/SKILL.md) guidance and is explicitly subordinate to rule 3 — humanizing the prose never means hiding that an AI wrote it, and the disclosure suffix is appended at insert time regardless of what the agent drafted.

`wait_for_verdict` returns the arena's current thread alongside the verdict, and sets `operator_edited` when `posted_text` differs from what the agent wrote — so the agent can match the voice that actually shipped.

### Custom personas

The panel's persona picker has a third entry beside the roster and 🎲 random: **✎ custom instructions…**, which reveals a name field and a textarea and casts the arena as a card the operator types on the spot. It exists for the character you want *once* — a specific voice for a specific thread — where adding a row to the registry would be clutter.

It needs no schema, because the storage a registry persona uses is **already a copy**. Both paths land in the same three snapshot columns; the only difference is that a custom card leaves `persona_slug` NULL, since there's no row to point at:

| | `persona_slug` | `persona_name` | `persona_body` |
|:---|:---|:---|:---|
| Registry card (`persona`) | the card's slug | the card's name | snapshot of the card |
| Custom card (`persona_instructions`) | `NULL` | the operator's label, or `Custom persona` | what they typed |

Consequences worth knowing:

- **`get_arena` gates the persona on `persona_body`, not `persona_slug`.** Keyed off the slug — as it was before this existed — a custom-cast agent would receive `persona: null` and argue as nobody. The agent gets `{slug: null, name, instructions}` and treats it exactly like a registry card.
- **Passing both `persona` and `persona_instructions` is a 400**, not a precedence rule. The panel sends one or the other; guessing which the caller meant is how an arena ends up cast as the wrong character.
- **Re-casting an arena onto a custom card clears the previous slug** (`bg_update_arena`'s `clear_persona_slug`, the same escape hatch as `clear_reply_to`). Without it, "skip on None" would leave the old card's slug beside the new name — an arena claiming to be one character and reading as another.
- **Nothing is written to the registry.** A one-off card never appears in `/personas` or in the next capture's picker. It's persisted in `chrome.storage.local` so the panel can restore a half-written card, and that's the only place it survives.
- **The house rules still win.** `_ARENA_RULES` ships in the same `get_arena` payload and is not something a card can edit, so a custom persona that asks the agent to claim it's a real person, or to hide that an AI wrote the reply, loses to rules 2 and 3.

### The operator's reply target

When the arena carries a `reply_to`, `get_arena` returns three things rather than one: the id on `arena.reply_to`, the post itself as a top-level `reply_target` (pulled out of the thread so the agent doesn't have to scan for it), and a `next` line naming the author and the exact `submit_draft(…, reply_to=…)` call to make. With no target set, all three revert to the agent choosing — the skill already tells it to answer someone specific, and a vague reply to the thread-in-general is the clearest bot tell there is.

The target is read live off the row like `rules`, not snapshotted, so re-targeting a running arena in the panel reaches the agent on its next `get_arena`.

## The arena console (`GET /battleground`)

The extension's side panel is bound to a tab. That's right for capture and for insertion — both need the page — but it made everything *after* the draft awkward: no way to see arenas across tabs, no way to review a draft once you'd closed the article, no draft history for an argument you ran last week. The console (shipped 2026-08-20) is the same arenas read from the same `bg_*` helpers, without a tab.

| View | What's on it |
|:---|:---|
| `/battleground` | Every arena, newest first — site chip, title, cast, assigned agent, post count, draft count, a **pending** badge when a draft is waiting on you, and last-updated. Filter chips for **All / Open / Closed** (`?status=`). Empty state points at `/extension`, because arenas only come from a capture. |
| `/battleground/{id}` | The captured thread (reply target highlighted, replies indented by `depth`), the stance brief, the persona snapshot **as captured**, and every draft with its status, rationale, your note, and any edit you made before posting. |

**It drafts, it never posts — and here it doesn't even insert.** Approving on this page flips the draft to `approved` and stops. Typing an approved reply into a site's composer is `lib/compose.js` in the extension, on the tab the thread lives in, and the site's own post button is still a human's click. The page says exactly that in a banner on both views, and `test_console_never_offers_to_post_to_the_page` pins both the wording and the fact that the only endpoints its buttons call are the verdict and arena routes.

Other things worth knowing:

- **No new write route.** Every action posts to a bridge endpoint that already existed (`/drafts/{id}/verdict`, `/arenas/{id}`, `/arenas/{id}/delete`), so there was no new surface for `ReadOnlyMiddleware` to cover and no new auth question. The console is a *renderer*.
- **Which verdicts are offered depends on state.** Pending → Approve / Reject; approved → **I posted this** / Reject; rejected → Approve (you changed your mind). A **closed** arena offers none of them: the agent can't draft into it, so re-litigating what's already there is noise. Reopen it first.
- **A rejection prompts for a note**, seeded with the same quick-action briefs the panel offers ("too long", "sounds like an LLM", "needs a source", "wrong target"). The agent reads that note as a revision brief on its next `wait_for_verdict`; a rejection without one just reads as "no".
- **The cast label is gated on `persona_name`, not `persona_slug`** — the same NULL-slug trap `get_arena` has to dodge. A [custom card](#custom-personas) typed into the panel has a name and a body and no registry row, and reading the slug would show a cast arena as uncast.
- **Everything on the page is escaped, not rendered.** Titles, authors and post text came off a third-party website; unlike a conversation message (rendered as Markdown), captured content is emitted as text in a `white-space: pre-wrap` block. Draft content too — it's destined for a plain comment box, so what you review should be exactly what would be typed.
- **The hosted mirror gets an explainer**, not an empty list. Both arena tables are excluded from the sidecar sync, so a list there wouldn't be "no arenas yet", it would be permanently empty — which reads as the opposite of the guarantee. Same shape `/orchestrate` uses when hosted.

Implementation: [`src/web/render/battleground.py`](../../src/web/render/battleground.py) (rendering), the two page routes in [`src/web_ui.py`](../../src/web_ui.py), `BATTLEGROUND_CSS` in `web/assets.py`.

## Extension internals

See [`extension/README.md`](../../extension/README.md) for install and usage; the parts worth knowing from the Python side:

- **`src/capture.js`** is injected on demand as a single IIFE whose completion value is the capture, so `chrome.scripting.executeScript({files: […]})` gets it back directly and re-injection on the same tab can't collide with a previous run's declarations.
- **`src/panel/`** does all the HTTP. Not the service worker: reviewing a draft is human-paced, and an MV3 worker is torn down after ~30s idle, which would kill the poll. Since 2026-08-01 it's a package — `panel.js` is wiring and init only, with the work in nine ES modules under `src/panel/lib/` (`state`, `settings`, `bridge`, `permissions`, `capture`, `arena`, `compose`, `drafts`, `view`). They form import cycles (`arena → view → drafts → arena`), which is why they share a single mutable `state` object and why every export crossing a cycle is a hoisted `function` declaration rather than a `const` arrow.
- **Composer insertion** (`lib/compose.js`) is the only code that touches the page's reply box, and it types — it never submits, never opens a composer, never clicks. It probes **every** reachable frame and inserts into exactly one (a Disqus reply box lives in its own iframe), keeps per-site selectors for the supported sites with focus as the override, asks replace/append/prepend rather than clobbering text the operator was already writing, and **reads the box back** afterwards. "Approved but nothing happened" is the worst failure mode this feature has, because the operator's next action is to hit post.
- **The tab→arena link is keyed on tab id alone.** `linkArena()` writes `{arenaId, url}` into `chrome.storage.local` under `arena:<tabId>`, but nothing ever reads that `url` back — `refreshTab()` looks the link up by tab id only. So a tab stays attached to its arena across navigation, and browsing to a different article leaves the panel offering **Re-capture this thread** for the *old* arena. **↺ Start over** (`#unlink`) is the escape hatch: it drops the link, the arena, and — this is the part that was wrong until 2026-08-13 — the held **capture**. `render()` shows the Cast card whenever there's a capture and no arena, so clearing only the arena re-offers the previous page's posts with **Open arena** live, one click from a second arena built on a stale thread. `clearCapture()` in `panel.js` is shared with the tab-switch path that always did this correctly. Start over is **not** destructive: the arena and its drafts stay on the server, and **Close arena** remains the separate control that stops the agent drafting.
- **Permissions** are `optional_host_permissions: ["*://*/*"]`, requested per-origin from a user gesture the first time you capture on a domain. The only standing host permissions are `127.0.0.1` and `localhost`.
- **Frames.** The capture is injected with `allFrames: true` and the panel folds the results into one thread, because a large share of news-site comment sections live in a third-party iframe. Only the top frame contributes the page lead; a subframe contributes only when it is a recognised comment platform or an origin the operator opted into from a per-frame permission button. Everything else — ads, embeds, trackers — is dropped even when readable.
- **Auto re-capture** is a panel-side timer (30s floor, off by default). It never asks for a permission it doesn't already hold, skips while a draft is being edited or the tab has drifted off the arena, and disables itself after three consecutive failures. There is still no auto-*post* path anywhere in the loop: it only refreshes what the agent can read.

### Firefox

`manifest.firefox.json` is a real second manifest, not a copy: Gecko MV3 has no `chrome.sidePanel` (it uses `sidebar_action`), takes a background `scripts` array rather than a `service_worker`, and needs a `browser_specific_settings.gecko.id`. The browser fork lives entirely in `src/background.js` — the panel is shared. Two Gecko rules shaped the shared code:

- `permissions.request()` must be called **synchronously from a user gesture**; Firefox discards the gesture across an `await`. Every click handler in `panel.js` therefore starts its permission request as the first statement and awaits the promise later.
- `strict_min_version` is `128.0`, the first release with `scripting.executeScript` (`files` *and* `func`) plus `optional_host_permissions` in MV3.

`scripts/build-extension.ps1` stages `extension/dist/firefox/` (gitignored) from the shared `src/` + `icons/` and the Gecko manifest; Chrome still loads `extension/` unpacked with no build step.

## Tests

`tests/test_battleground.py` (42 cases, dual-mode like the rest of `tests/`):

```powershell
.\.venv\Scripts\python.exe tests\test_battleground.py
```

Covers the bridge contract, input scrubbing, re-capture merging (including namespaced frame ids), the reply-target round trip and its validation, `/healthz` answering through a token challenge, the verdict state machine, the "draft is born pending" invariant, the persona snapshot, [custom personas](#custom-personas) (the NULL slug, the double-cast refusal, the slug clear on re-cast, and `get_arena` handing one over), the CORS gate on both axes, schema parity across all three `SCHEMA` mirrors, the sync exclusion, and the full MCP agent loop including arena claiming and the operator's reply target — and, since 2026-08-20, the [`/battleground` console](#the-arena-console-get-battleground): the list and its pending counts, the status filter, the detail view's thread and drafts, the verdict buttons tracking draft state, the hosted explainer, and the escaping of captured page content (every string on that page came off somebody else's website).

Two cases reach out of Python, both pinning a list that's duplicated across languages and directories, where a mismatch is silent rather than loud:

- `test_every_shipped_adapter_label_survives_a_capture` — each label in `KNOWN_SITES` is emitted by `extension/src/capture.js` and comes back from the bridge unchanged. A mismatch still opens a working arena; it's just labelled `generic` everywhere it's shown.
- `test_roster_launch_commands_match_the_spawn_registry` — each `CLI_LAUNCH` entry's folder and binary appear in `scripts/lib/spawn-agents.ps1`. A mismatch sends the operator to a folder or binary that isn't there.

### What the tests can't reach

Everything that needs a real browser: `chrome.permissions` prompts, `chrome.scripting` injection, the side panel / sidebar surfaces, and composer insertion. The panel is exercised only by a Node stub during development, so **a browser shakedown is the standing top item** on the [extension README's enhancement list](../../extension/README.md#enhancements--updates).

## Not built yet

Tracked on the [Roadmap](../Roadmap.md) row: the **browser shakedown** (nothing under `extension/` has a test that runs in a browser — see [What the tests can't reach](#what-the-tests-cant-reach)) and folding arena outcomes into the model-comparison dashboard.

Console follow-ups that were deliberately left to the panel: **re-casting a persona, re-targeting the reply, and editing the stance**. Those are capture-time decisions the panel already owns, and the bridge's `POST /arenas/{id}` accepts them from either surface if that changes.

The `/extension` page added 2026-08-12 is **not** the console — it explains the feature and how to install it, so people who aren't reading the source can find it at all. It has no arena list and no verdict actions. Its header links [`Guides/battleground.md`](../Guides/battleground.md) ("How to argue in an online forum") — the homepage's *Participate in online forums* CTA lands here, so the how-do-I-run-one answer has to be above the fold, not only in the *Read more* tiles at the foot of the page.
