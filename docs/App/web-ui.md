# Web UI

Starlette app entered at [`src/web_ui.py`](../../src/web_ui.py). Reads the
same SQLite file the MCP server writes to (`db/chat.db`). Runs as a separate
process — does **not** wrap or replace the MCP server. Local default bind is
`127.0.0.1:8765`. The same entrypoint is also what's deployed on Fly.io as
[`agent-chat.mikesailab.com`](https://agent-chat.mikesailab.com), which is
publicly readable but **read-only** — browser mutations are rejected with `403` (see [Auth](#auth)).

Since the 2026-07-10 split, `web_ui.py` is only the assembly layer (page
routes, route table, middleware wiring, `main()`); the implementation lives in
the [`src/web/`](../../src/web/) package:

| Module | Holds |
|:---|:---|
| `web/db.py` | Connection, `SCHEMA` + migrations, every SQL helper, `set_db_path()` |
| `web/security.py` | `BasicAuthMiddleware`, `ReadOnlyMiddleware`, `_build_middleware()` |
| `web/assets.py` | CSS / JS / SVG constants (`BASE_CSS`, `HOME_CSS`, `_CONV_CSS`, `_PERSONAS_CSS`, favicon) |
| `web/render/` | Per-page HTML: `common` (shell, Markdown, icons), `home`, `conversations`, `orchestrate`, `personas` |
| `web/api/` | `/api/*` handlers: `conversations` (JSON/export/stop/delete/stream), `sync` (ingest/since), `orchestrate`, `personas` |

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
| `GET` | `/` | **Homepage.** Marketing + intro shell. Live counters from the DB, latest 5 conversations, link grid out to repo / docs / prompt library / sample debates. |
| `GET` | `/orchestrate` | **Seed-a-conversation form.** Topic / participants / **per-CLI persona picker** / preset / max_turns / first speaker / **Launch (auto-spawn + skip-permissions)** / optional system message. Page-load preflight badges next to each CLI checkbox. **On the hosted read-only mirror** (`AGENT_CHAT_PUBLIC_READONLY`) this renders a **local-only explainer** instead — the mirror can't spawn local CLIs. See [Orchestrator](#orchestrator-get-orchestrate--post-apiorchestrate). |
| `POST` | `/api/orchestrate` | **Form handler.** Validates (incl. persona picks) → re-runs preflight on selected CLIs → on failure: `409` + `{kind: "preflight_failed", preflight: [...], log_path}` (writes `logs/orchestrator-<ts>.log`) → on success: `200` + `{ok: true, conversation_id: N, spawn: {...}}`, resolving the persona cast into `participant_personas` and best-effort spawning one CLI window per agent (local Windows). JS redirects to `/conversations/<id>` unless spawn was unavailable. |
| `GET` | `/conversations` | **Two-pane inbox** (2026-07-10 redesign): a left rail (search, filter chips all/active/debates/3-agent/done, agent filter, sort control, dense conversation list with deterministic conversation marks, status dot, topic, cast, `#id · N msg · date`, per-item × delete, collapse toggle) + a main pane. The bare index shows an **overview** (`_render_conversations_overview()`): stat cards (total / active / messages), the 6 most recent conversations with matching conversation marks, `+ New conversation` / JSON-index actions. See [Conversations browser](#conversations-browser-get-conversations). |
| `GET` | `/conversations/{cid}` | The **transcript reader** in the main pane (rail stays on the left). Header strip: deterministic conversation logo, status pill, live **whose-turn badge**, topic, meta line, stats line (messages · per-agent counts · duration · ~tokens); actions: full-screen icon, Export MD/ZIP, Stop (active only), Delete (local only, styled as a solid red X button). Cast rows and message headers include per-agent avatars. Active conversations auto-update via SSE. Fresh conversations (status=active + 0 messages) get a **"Next: launch each CLI"** panel above the transcript with a `Copy prompt` button per participant; panel auto-removes when the first SSE message arrives. `?fullscreen=1` hides rail + topbar and adds prev/next icon nav. |
| `GET` | `/api/conversations` | JSON list (same shape as the table). |
| `GET` | `/api/conversations/{cid}` | JSON detail (conversation + ordered messages). |
| `GET` | `/api/conversations/{cid}/export.md` | Self-contained Markdown transcript. `Content-Disposition: attachment; filename="<topic-slug>.md"`. Falls back to `conversation-{cid}.md` when the topic has no usable ASCII. |
| `GET` | `/api/conversations/{cid}/export.zip` | Comprehensive Markdown **bundle** (`application/zip`): `topic.md` (topic + overview metadata + kickoff framing), `personas/<agent>-<slug>.md` (one per participant — CLI tool + the full personality card), and `transcript.md` (the full debate). Persona docs come from the stored `participant_personas`; conversations without a recorded cast still export, noting the persona wasn't recorded. Filename `<topic-slug>.zip`. |
| `POST` | `/api/conversations/{cid}/stop` | Force-stop. Mirrors `inspect_conversations.py stop`. Idempotent — already-complete returns 200 with `{"already_complete": true, …}`. |
| `POST` | `/api/conversations/{cid}/delete` | **Permanently delete** the conversation + cascade messages. UI affordances: `×` button on `/conversations` list, and red `X` button in detail actions. Idempotent — second delete returns 404. Picked up by the local sidecar on the next pull tick (see [`db-sync.md`](db-sync.md)). |
| `GET` | `/api/conversations/{cid}/stream` | Server-Sent Events. `event: message` per new row, `event: turn` when `current_turn` changes (whose-turn badge), `event: complete` when status flips to `complete`. |
| `GET` | `/personas` | **Persona management page.** A three-pane console: group rail (left), persona list (center), live edit/preview (right). Backed by the synced `personas` table, so it works **local + hosted**; renders an "unavailable" notice only if the DB can't be reached. See [Persona management](#persona-management-get-personas). |
| `POST` | `/api/personas` | Create a persona. JSON `{name, body, group?, tags?}` → `{ok, slug, group}` or `400 {ok:false, error}`. `404` only if the database is unreachable. |
| `POST` | `/api/personas/import` | Bulk-import personas from Markdown cards and/or `.zip` archives. JSON `{group?, overwrite?, files:[{filename, text}], zips:[{filename, b64}]}` → `{ok, imported, skipped, errors[]}`. Each loose file and each `.md`/`.markdown` entry inside a zip (found recursively; other files ignored) is parsed as a seed-style card; the filename stem becomes the slug. Zips are size/entry-capped against zip bombs. `404` if the database is unreachable. |
| `POST` | `/api/personas/bulk-delete` | Delete many personas at once. JSON `{items:[{group, slug}]}` → `{ok, deleted, not_found, errors[]}`. Each item is matched on its `(group, slug)` pair (slugs are only unique within a group). `404` if the database is unreachable. |
| `POST` | `/api/personas/{slug}` | Update a persona (by slug, searched across all groups). JSON `{name?, body?, tags?, group?}` — `group` moves the row to another group. `404` if not found, `400` on validation error. |
| `POST` | `/api/personas/{slug}/delete` | Delete a persona. `{ok:true}` or `404` if not found. |
| `POST` | `/api/ingest` | Bearer-token push endpoint used by [`scripts/db_sync.py`](../../scripts/db_sync.py). Upserts conversations + **personas**, inserts messages, applies deletions. Returns `404 ingest disabled` unless `AGENT_CHAT_INGEST_TOKEN` is set. |
| `GET` | `/api/since` | Bearer-token pull endpoint used by [`scripts/db_sync.py`](../../scripts/db_sync.py). Query: `conversations_updated_after` (required) + `known_ids` (optional CSV); optional `personas_updated_after` + `known_persona_keys` for persona deltas. Returns `{conversations, deleted_conversation_ids, personas, deleted_persona_keys, server_time}`. **Messages excluded** — they flow local-only-origin. Same auth realm as `/api/ingest`. Returns `404 sync disabled` when `AGENT_CHAT_INGEST_TOKEN` is unset. |
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
| Topbar | Brand mark (JetBrains Mono), live pill (`N live` when `active > 0`, else `system online`), section anchors, and styled navigation buttons with specific SVG icons, dividers (`|`), and colored backdrops (Resources, Personas, Orchestrate, Theater, Conversations), plus a **GitHub mark icon** at the far right. |
| Hero | Eyebrow (`INTER-AGENT MESSAGE BUS`), single-line title, lede naming the five active CLIs + a `persona` link, two equal-height CTAs (`Launch a debate` / `Browse conversations`), an info-icon **local-vs-hosted note** (`launch_note` — read-only-demo + `Clone the repo →` on the hosted mirror, light `launch a debate →` nudge locally), an inline **stats row** (conversations / active / messages / CLIs, mono numerals), and — on the right — the **Featured debates panel** (`_render_homepage_featured`). |
| 01 — What it is | Asymmetric **bento** (one tall card + two stacked), single emerald accent: turn engine, push handoff, live viewer. |
| 02 — Supported CLIs | Table of the supported CLIs (name → repo/home link, vendor, `agent-id`, status). Rendered by `_render_homepage_clis_table()` from the `_SUPPORTED_CLIS` tuple — Claude Code, Codex, Antigravity, Kimi, OpenCode (active) + Gemini (deprecated fallback). |
| 03 — Meet the cast | Persona roster preview: up to 9 cards (monogram, name, summary, tag chips) from the registry's debater group, plus an `Explore all N personas →` link to `/personas`. Rendered by `_render_homepage_personas()`; empty-state when the registry has no personas. Reads the synced `personas` table, so it populates on the hosted mirror too. |
| 04 — How to use it | Five numbered steps with real code (clone → register MCP → seed → kickoff → watch). |
| 05 — Latest from the arena | Top 5 conversations with id / topic / **cast** / status. The cast column shows **persona names** (`_conv_cast_label()` reads `participant_personas`) when a conversation recorded one, else the raw agent ids. Empty state suggests `scripts/start.ps1`. |
| 06 — Resources | Five link groups: This project · Prompt library · Sample debates · Stack & protocols · Author. (The CLIs now live in the section-02 table, not a resource tile.) |
| Footer | Monospaced run-tally (`AGENT BATTLEGROUND // N CONVERSATIONS · M MESSAGES`), built-on attribution, repo link. |

### Design system

Aesthetic direction: **editorial-modern** (the 2026-07-08 redesign; was
"console-arena"). Near-black canvas with a **single emerald accent** matching
the favicon, a subtle emerald hero wash, and generous whitespace. Editorial,
intentional, no fluff. Avoids the cliched generic-AI defaults (Inter, Roboto,
system fonts, purple gradients on white) — and, unlike the previous build,
holds to **one accent**: the per-card cyan/violet feature-card glyphs and the
cyan/violet/amber Resources headers were unified to emerald in the redesign.

**Build.** Unlike the rest of the app (the shared `_layout` + `BASE_CSS`),
the homepage is a self-contained template (`_HOMEPAGE_TEMPLATE`, rendered by
`_render_homepage()`) driven by the **Tailwind CDN** + inline utility classes
for layout. It does **not** define a CSS-variable token set — the older
console-arena `--ink` / `--bone` / `--emerald` block was removed when the
homepage moved to the Tailwind layout (see the note at the bottom of
`HOME_CSS`). `HOME_CSS` now carries only the handful of rules Tailwind can't
express ergonomically.

**Color.** `#060606` canvas with Tailwind `zinc-*` neutrals for text and
borders, and a single **emerald** accent — `emerald-400` / `emerald-500`
utilities in the template plus hardcoded `#10b981` in the `HOME_CSS` rules —
matching the favicon. No red/amber on this surface. (The 2026-06-29 retheme
flipped the homepage from a `sky-400` accent to emerald so it matches the rest
of the app and the always-emerald favicon; `BASE_CSS` was flipped to the same
emerald in the same change, so `/` and `/conversations` now share the accent.)

**Typography.** Three families loaded via a single Google-Fonts `<link>` in
the template `<head>` (not an `@import`): **JetBrains Mono**, **IBM Plex
Sans**, **IBM Plex Mono**. Applied in `HOME_CSS`: `body.home` and the
headlines (`body.home h1, h2, h3`) are **IBM Plex Sans** with tight tracking —
the editorial-modern redesign moved headlines off JetBrains Mono, which now
survives only on the brand wordmark (`.mark-txt`). `.mono` (IBM Plex Mono) is
the helper for stat numerals, code chips, and the featured-debate meta. Avoids
the called-out cliches (Inter, Roboto, Arial, Space Grotesk, system mono).

**Featured debates panel** (`_render_homepage_featured`, fed by
`list_featured_debates()`). The hero's right column lists up to four
**completed** debates (newest first, ≥4 messages), each a link to its
transcript with a one-line teaser (opening non-system message, Markdown-stripped
and truncated) and its **debater cast** — persona names via `_conv_debaters()`
when `participant_personas` recorded a cast (debates launched through
`scripts/debate.ps1`), else the raw agent ids. Monogram avatars per debater.
Empty-state (fresh DB / no completed runs) points at `/conversations`.

**What `HOME_CSS` carries** (everything else is Tailwind utilities in the
template):

| Rule | Role |
|:---|:---|
| `.live-pill` (+ `.dot` / `.idle`) | Topbar status pill — emerald pulsing dot + uppercase label; idle state is muted. |
| `.step-code` / `.step-code-inline` | "How to use it" code blocks — near-black, emerald left-rule, mono; `.cmt` muted, `.em` emerald. |
| `.latest-row` (+ `.lid` / `.ltopic` / `.lparts` / `.lstatus`) | "Latest from the arena" rows — slide-in + emerald-tinted hover, mono id/participants, emerald `active` status dot. |
| `.live-tile .glyph` | Per-tile decorative glyph hover transition. |

> [!NOTE]
> The previous console-arena build's CSS-variable tokens, the `body.home`
> `::before` / `::after` grain + gradient layers, and the staggered `rise` /
> `rise-clip` hero reveal animation were all removed when the homepage moved to
> the Tailwind layout — they no longer exist in the code.

**Live counters.** `list_stats()` runs on every render — three indexed
`COUNT(*)` queries, cheap. The "Active now" stat cell swaps its color class
to `text-emerald-400` (from `text-zinc-100`) when `active > 0` via the
`{active_color}` template var, and the topbar live-pill text flips from
`system online` to `N live`. Drawing the live state from the same
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
| **Sample debates** | Bob Lazar, Fermi paradox, Simulation theory, Brain↔CPU interface, Future of tech jobs |
| **Stack & protocols** | modelcontextprotocol.io, MCP Python SDK, Starlette, SQLite WAL, Fly.io, markdown-it-py |
| **The CLIs** | anthropics/claude-code, openai/codex, antigravity.google |
| **Author** | mikesailab.com, github.com/michaelschecht, prompts.mikesailab.com |

When the brand or palette of a sister `mikesailab.com` app changes, the
favicon SVG and the emerald token here should track it (see also
`FAVICON_SVG` in `src/web_ui.py` — same `#10b981` rounded square / dark
glyph convention as `edge-spectrum.mikesailab.com` and
`prompts.mikesailab.com`).

---

## Conversations browser (`GET /conversations`)

A **two-pane inbox** (2026-07-10 redesign — it replaced the short-lived
tri-pane browser, whose preview pane duplicated the list and buried the
transcript behind a second click). Rendered by
`web/render/conversations.py`; styled by `_CONV_CSS` (in `web/assets.py`),
scoped to `.cv2`; full-bleed below the topbar via `main:has(.cv2)`. Each
pane scrolls independently inside a `calc(100dvh - 48px)` shell.

- **Left rail** (`_conversations_rail`) — top to bottom:
  - Head: title, count badge, and a **collapse toggle** (sidebar icon).
    Collapsing sets `.cv2.rail-hidden` (grid column drops to `0`), shows a
    fixed floating reopen button, and persists in
    `localStorage["agentchat.cv.rail"]`.
  - **Search** — client-side substring filter over topic / id /
    participants / cast names.
  - **Filter chips** — All / Active / Debates / 3-agent / Done, each with
    a count.
  - **Sort + agent selects** — sort by newest (default) / oldest /
    recently updated / most messages (persisted in
    `localStorage["agentchat.cv.sort"]`; reorders the DOM from `data-id` /
    `data-updated` / `data-msgs`); the agent select narrows to
    conversations a given CLI participated in.
  - **Conversation list** — dense 3-line items with a deterministic SVG
    conversation mark, status dot (emerald pulse for `active`), topic
    (1-line ellipsis), cast (persona names when recorded, else agent ids),
    mono `#id · N msg · MM-DD` meta line, and a hover **×** delete.
  - Footer: `+ New conversation` → `/orchestrate`.
- **Main pane** — on the bare index, an **overview**: headline stat cards
  (total / active / messages via `list_stats()`), the six most recent
  conversations with the same deterministic marks, and `+ New conversation` /
  JSON-index actions. On `/conversations/{id}` it's the transcript reader
  (next section).

Selecting a conversation is a plain link navigation to
`/conversations/{id}` — the reader page re-renders with the same rail
(active row highlighted), which is what keeps the live SSE / export / stop
behaviour intact (no client-side transcript swapping). Deleting the
currently-open conversation navigates back to `/conversations`. All rail
behaviour (search / filters / sort / collapse / delete) is shared by both
pages via `_conv_rail_js()`.

---

## Orchestrator (`GET /orchestrate` + `POST /api/orchestrate`)

The form seeds a conversation with **strict all-or-nothing preflight** on
each selected CLI's MCP config before any DB write happens. On preflight
failure the row is not created and the operator gets a detailed report
inline; on success the row lands in `chat.db`.

**Phase 2b shipped 2026-07-13:** the form also carries a **per-CLI persona
picker** (fed by `orchestrator.personas`) and a **Launch** section (auto-spawn
+ skip-permissions toggles). On success the handler resolves the persona cast
into the `participant_personas` column and — when auto-spawn is on and the box
is local Windows — best-effort launches one CLI window per agent in character
via `scripts/orchestrate-debate.ps1` (which shares `scripts/lib/spawn-agents.ps1`
with `debate.ps1`). Persona is injected through the per-agent launch prompt file,
so **no schema or kickoff-template change** was needed. The still-open piece is
the optional `continuous`-mode moderator/host.

> [!IMPORTANT]
> **The orchestrator is a local-only entry point — the hosted mirror is a
> viewer, not an orchestrator.** Two independent reasons the form can't seed
> on `agent-chat.mikesailab.com`:
>
> 1. **Preflight can't see the configs.** The handler requires each selected
>    CLI's `agent_chat` config to exist on disk (under `agents/CLIs/`). That
>    tree is gitignored and **excluded from the Fly image**, so on the hosted
>    mirror every CLI fails preflight → `409`, nothing seeded.
> 2. **No agents run on Fly.** The container runs **only this `web_ui.py`** — a
>    Starlette viewer. The CLI agents and the MCP server they launch exist only
>    on your local machine; the cloud can't start processes there, so even a
>    seeded row would be inert.
>
> Conversations are **born and run locally** and *mirror up* to Fly via the
> [DB-sync sidecar](db-sync.md). The hosted site's only writes are the DB-edit
> affordances (stop, delete, persona CRUD), which sync back down. Operator
> walkthrough of the form: [`Guides/orchestrate-form.md`](../Guides/orchestrate-form.md).

### Form (`GET /orchestrate`)

Rendered by `_render_orchestrate(initial_preflight, persona_roster)` (the
GET handler builds `persona_roster` from `orch_personas.discover_groups()` +
`list_personas(g)`). Sits inside the shared `_layout()` shell so it picks up
the topbar nav (`Orchestrate` link), favicon, and BASE_CSS. Page-specific
styles live in `ORCHESTRATE_CSS`, scoped under `.orch-shell`.

**Page-load preflight badges.** The handler calls
`run_preflight(list(SUPPORTED_CLIS))` (`claude-code`, `codex`, `gemini`,
`antigravity`) once on render and
surfaces the per-CLI result as a small monospace pill next to each
checkbox — sky-blue `ready` when `ok=True`, red `<failure-code>` (e.g.
`config_missing`, `command_not_found`) otherwise. This is advisory: the
authoritative preflight runs again server-side on POST against only
the *selected* CLI subset.

**Fields:**

| Field | Type | Notes |
|:---|:---|:---|
| Topic | text, required, max 400 chars | Free text. Phase 2b will add a curated dropdown from `docs/Chat-Topics/`. |
| Participants | multi-checkbox, min 2 | `claude-code` + `codex` pre-checked; `antigravity` opt-in; `gemini` opt-in (deprecated). The selected list drives both server-side preflight + the seeded `participants` JSON column. |
| Preset | `<select>` from `PRESETS` | `debate` / `code-review` / `brainstorm` / `plan`, plus a literal `none` option that skips template rendering and leaves `kickoff_template` NULL (legacy paste-the-prompt flow). |
| Max turns | number, 1-50 | JS auto-fills from the preset's default when preset changes. Explicit value wins. |
| First speaker | `<select>` | Populated dynamically from the checked participants. Empty value falls back to `participants[0]`. |
| Personas | one `<select>` per CLI | Shown only for a **checked** participant (hidden rows are `disabled` so they aren't collected). Options: `none` (default), `🎲 random`, then the roster grouped by `<optgroup>`. A "Cast all selected randomly" button sets every visible row to `__random__`. Posted as `personas: {cli: value}`. |
| Launch | two checkboxes | `spawn` (auto-open a CLI window per agent — local Windows only) and `skip_permissions` (append each CLI's `--yolo`/`--dangerously-skip-permissions`). Both default **on**. |
| Optional system message | textarea | Inserted as the first message in the conversation with `sender='system'`. |

**JS form behaviour:** preset selection triggers max_turns autofill;
checkbox changes re-populate the first-speaker dropdown **and toggle the
matching persona row's visibility/disabled state**; submit serializes to
JSON (topic, participants, preset, max_turns, first, kickoff, **personas,
spawn, skip_permissions**) and posts to `/api/orchestrate`. On success it
redirects to `/conversations/<id>` **unless** the spawn status is
`unavailable`/`error` — then it shows an inline note (why no windows opened
+ the manual command + a link) rather than redirecting silently. Error
responses render in the red `.orch-error` panel. The submit button reflects
state: `Running preflight…` → `Run preflight + start conversation`.

### Handler (`POST /api/orchestrate`)

Validates the JSON body, runs preflight on the *selected* CLIs only,
gates the seeding, and returns one of three response shapes:

**Success (200):** `spawn.status` is one of `launched` (wrapper started —
lists the CLIs), `skipped` (auto-spawn not requested), `unavailable` (hosted
mirror / non-Windows / no `pwsh` — includes a `manual` command), or `error`.
```json
{ "ok": true, "conversation_id": 42,
  "spawn": { "status": "launched", "detail": "spawning 2 CLI window(s)",
             "agents": ["claude-code", "codex"] } }
```

**Validation failure (400):** missing topic, fewer than 2 participants,
unknown preset, max_turns out of range, bad `first` speaker, **`personas`
not an object, or a persona pick that can't be resolved / not enough unused
personas for the random picks**.
```json
{ "ok": false, "kind": "validation", "error": "topic is required" }
```

**Preflight failure (409):**
```json
{
  "ok": false,
  "kind": "preflight_failed",
  "preflight": [
    {
      "cli": "codex",
      "ok": false,
      "config_path": "C:\\Users\\mikes\\.codex\\config.toml",
      "command": null,
      "launcher_path": null,
      "failures": [{ "code": "config_missing", "detail": "Codex MCP config not found at …" }]
    },
    { "cli": "claude-code", "ok": true, "config_path": "…", "failures": [], … }
  ],
  "log_path": "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/logs/orchestrator-2026-05-15T14-32-09.log"
}
```

**Seed-validation failure (400, rare):** the `seed_conversation()` call
raised `SeedError` (e.g. duplicate participants, mode mismatch). Mirrors
the validation shape with `kind: "seed_error"`.

### Preflight checks per CLI

All checks are pure file-system reads — no subprocess, no CLI launch.
That keeps the page-load and POST-time preflights both fast (≪50ms total
on this machine) and safe from hang/timeout edge cases. (The actual CLI
spawn happens *after* a clean preflight + seed, in `scripts/orchestrate-debate.ps1`.)

| Check | claude-code | codex | antigravity | gemini (deprecated) |
|:---|:---|:---|:---|:---|
| Config exists | `agents/CLIs/claude-code_agent1/.mcp.json` | `~/.codex/config.toml` | `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` | `agents/CLIs/gemini_agent1/.gemini/settings.json` |
| Parses | JSON | TOML (`tomllib`, stdlib 3.11+) | JSON | JSON |
| Has `agent_chat` entry | `mcpServers.agent_chat` | `[mcp_servers.agent_chat]` | `mcpServers.agent_chat` | `mcpServers.agent_chat` |
| `command` resolves | `shutil.which()` or file exists | same | same | same |
| Launcher path extractable | `pwsh + ["-File", "<path>", …]` or direct `.sh`/`.ps1` | same | same | same |
| Launcher file exists on disk | ✓ | ✓ | ✓ | ✓ |

**Failure codes** (the `code` field on each `PreflightFailure`) form a
small enum so the UI can render a monospace chip + the human-readable
`detail`, and so a `grep FAIL` on the log file groups by cause:

`config_missing` · `config_parse_error` · `no_mcp_entry` ·
`missing_command` · `command_not_found` · `missing_args` ·
`launcher_not_extractable` · `launcher_missing` · `unknown_cli`

### Audit log

On any preflight failure, the handler writes a self-contained text log
to `<repo>/logs/orchestrator-<YYYY-MM-DDTHH-MM-SS>.log` (UTC; colons
stripped for Windows filename compatibility). Format:

```
# Orchestrator preflight failure — 2026-05-15T14-32-09
# Topic: Whatever the operator typed
# Requested CLIs: claude-code, codex, antigravity

# Preflight: 2/3 OK
  OK   claude-code  D:\...\agents\CLIs\claude-code_agent1\.mcp.json
  FAIL codex        [config_missing] Codex MCP config not found at C:\Users\mikes\.codex\config.toml. See README 'Register the server' section for the [mcp_servers.agent_chat] block.
  OK   antigravity  D:\...\agents\CLIs\antigravity_agent1\.agents\mcp_config.json
```

Successful runs do **not** write a log (the conversation row in
`chat.db` is the audit trail). The `logs/` directory is gitignored.

### "Next: launch each CLI" panel on the redirect target

After a successful seed, the form JS redirects to
`/conversations/<id>`. That page detects the fresh state
(`status='active'` AND 0 messages) and renders a sky-tinted
`.next-steps` panel above the empty transcript. One row per participant
with the agent's id, a sky-blue **FIRST TURN** pill on the
`current_turn` agent, and a **Copy prompt** button per row.

When the conversation was seeded with a preset (the orchestrator always
does), the panel includes a copy button that puts the rendered two-line
kickoff prompt into the clipboard via `navigator.clipboard.writeText`:

```
You're agent <id> on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

`<id>` is substituted per-row. Button flashes `Copied!` for 1.5s on
success. The panel **auto-removes** from the DOM the moment the first
SSE `event: message` lands — handled inside the existing
`_render_conversation` IIFE, no separate listener.

When the conversation was seeded *without* a preset (no rendered
template; `kickoff_template` column is NULL), each row shows a muted
"no template — see start-new-chat.md" hint instead of a copy button.

---

## Conversation transcript (`GET /conversations/{cid}`)

The "real cockpit" for one conversation — since the 2026-07-10 redesign it
IS the main pane of the two-pane browser (`_render_conversation_main()` in
`web/render/conversations.py`): the
[conversations rail](#conversations-browser-get-conversations) stays on
the left (this conversation's row highlighted) and the reader fills
`#cv-main`, its own scroll container, so live-append auto-scroll targets
`#cv-main` rather than the document body. `?fullscreen=1` drops the rail
and topbar for a distraction-free reader with **previous / next / exit
icon buttons** (aria-labelled) navigating the rail order.

**Header strip.** Eyebrow row: status pill (emerald pulse while
`active`), a **whose-turn badge** ("codex is up" — rendered only for
active `turns`-mode conversations, updated live via SSE `turn` events),
and right-aligned actions: **full-screen icon** (⛶-style expand SVG),
**Export MD**, **Export ZIP**, **Stop** (active only). Below: a generated
conversation logo beside the topic h1, a mono meta line (`#id · preset ·
mode, max N/agent · started … · ended: reason`), and a **stats line** —
message count, per-agent message counts, duration (first→last message),
rough token estimate (chars / 4). The logo is deterministic from the
conversation id/topic/participants/preset, so old rows gain visual identity
without a schema migration.

**Cast panel.** One expandable entry per participant (persona name +
personality card) with a per-agent avatar and message count on each row.

**Transcript.** One `.msg` block per message. Sender (persona name +
CLI id when a cast is recorded), per-sender avatar, timestamp, optional
signal pill (`done`/`blocked`). Body rendered through `markdown-it-py`
(see "Markdown rendering" below).

**Live append.** When `status='active'`, the page opens an `EventSource`
on `/api/conversations/{cid}/stream?since=<last_id>`. New messages append
to the transcript via `innerHTML` injection of server-rendered HTML
(`content_html` is included in the SSE payload — no client-side Markdown
library). `event: turn` updates the whose-turn badge text (persona name
included when known). When the server emits `event: complete`, the status
pill flips to `complete` and the turn badge + Stop button are removed.

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

> **The renderers live in `src/orchestrator/export.py`** (since 2026-07-10),
> imported into `web_ui.py` under their old underscore names — the same
> functions also power `scripts/publish_debate.py`, which writes these files
> straight into the AI-Automation-Library archive. The output format is a
> **contract** with downstream parsers — see
> [`export-format.md`](export-format.md) before changing any shape below.

`render_export_markdown(data)` builds a self-contained Markdown document
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

### Bundle export (`GET /api/conversations/{cid}/export.zip`)

`render_export_zip(data)` builds a `.zip` of Markdown files (stdlib `zipfile`
into a `BytesIO`, served as `application/zip`; the file set comes from the
shared `bundle_files()`):

- **`topic.md`** — `render_export_overview()`: the topic + an overview metadata
  table (status, mode, max-turns, participants, dates, end reason, preset), a
  **Cast** list when personas are recorded, and the rendered kickoff/framing
  (`kickoff_template`) when present. No invented subtopics.
- **`personas/<agent>-<slug>.md`** — `persona_doc()`, one per participant: the
  CLI tool (`agent_id`) + the persona name/slug + the full personality card body.
  Source is the conversation's `participant_personas` JSON (recorded by
  `scripts/debate.ps1` at launch). Participants without a recorded persona get a
  doc noting so.
- **`transcript.md`** — the same body as the single-file `export.md`.

`participant_personas` stores the **full card body**, not just a slug, so the
bundle is complete even on the hosted mirror (where `agents/` cards aren't shipped).

---

## Cast panel (conversation page)

When a conversation has a recorded persona cast (`conversations.participant_personas`,
set by `scripts/debate.ps1` at launch), the detail page renders a **Cast** panel
above the transcript — one expandable entry per participant showing the CLI tool
(`agent_id`) and persona name, expanding to the full personality card. Cast rows
include deterministic avatars, and each message header is also labelled with the
persona name (e.g. *Flat-Earth Fred* `claude-code`),
for both the server-rendered initial messages and the live SSE-appended ones (a
`PERSONAS` JS map carries `agent_id → persona_name` to the client, while
`AGENT_VISUALS` carries the avatar initials/styles for live messages).
Conversations without a cast render normally (no panel, bare `agent_id` labels).
Styling is in
`_CAST_CSS`.

## Persona management (`GET /personas`)

A **three-pane management console** for the debate personality roster (the
2026-06-29 redesign replaced the single-column accordion). Emerald-accented to
match the homepage brand and the favicon, scoped to a `.pm3` wrapper so it
doesn't disturb the sky-accented `BASE_CSS` the other app pages use. Full-bleed
below the topbar — overrides the narrow `_layout` `<main>` column via
`main:has(.pm3)`. Styled by `_PERSONAS_CSS`; rendered by `_render_personas_page`.

- **Left rail — group navigator.** A search box, one button per group (folder
  icon, name, count chip) with the active group emerald-highlighted, and a
  `+ New group` action. Clicking a group switches the center list client-side;
  non-active groups carry the `hidden` attribute (`.pm-rows[hidden]` =
  `display:none`).
- **Center pane — persona list.** Header with the group title, a sort `<select>`
  (Name A–Z / Z–A), and `+ New` / `Import` / `Select` actions; a column header;
  then one row per persona (monogram avatar, name, mono slug, emerald tag chips,
  and hover quick-actions: edit / duplicate / delete). The left-rail search
  filters the active group's rows by name/slug/tags. Empty/filtered states show
  an inline notice.
- **Right pane — detail / edit.** One shared form, populated client-side on row
  select (no full re-render). Display name, a group `<select>` (with the
  *＋ Create new group…* escape hatch), a tag chip input, and the Markdown body
  under **Edit / Preview** tabs. Preview is a small inline, escape-first Markdown
  renderer (headings/bold/italic/code/lists) — no CDN dependency, so the page
  works offline. **Save** / **Delete** in the footer. On a narrow viewport
  (≤900px) the rail + list stack and this pane becomes a right slide-over drawer
  (opened on select, closed via its ✕).
- **Duplicate** opens the form in create mode prefilled from the row (name +
  " copy", tags, body) and saves through `POST /api/personas` — there is no
  dedicated duplicate endpoint.
- Persona bodies ride in a `<script type="application/json">` island the detail
  pane reads on selection (lighter than a textarea per row); `<` is escaped to
  `<` so a body containing `</script>` can't break out of the island.
- **Group folder** is a `<select>` of existing groups with a trailing
  *＋ Create new group…* option that reveals an inline text input — picking it
  and typing a name creates the group when the persona is saved (groups are just
  distinct `"group"` values, so a group materializes with its first persona).
- **Tags** use a chip input: type a tag and press comma or Enter (or paste a
  `a, b, c` list) to resolve each into a removable chip; Backspace on the empty
  field deletes the last chip.
- **Import** (a modal opened by the **Import** button) accepts one or more
  `.md` cards (read client-side via `File.text()`)
  and/or `.zip` archives (base64-encoded client-side and unzipped server-side
  with stdlib `zipfile`). All inputs POST to `/api/personas/import` as JSON
  (`files:[{filename, text}]` and/or `zips:[{filename, b64}]`). Each loose card
  and each `.md`/`.markdown` entry inside a zip is parsed as a seed-style
  frontmatter+body card; the filename stem becomes the slug. Zip entries are
  found recursively — any non-Markdown files (images, etc.), directories,
  `__MACOSX` metadata, and dotfiles are ignored. Zips are bounded by
  `_ZIP_MAX_ENTRIES` (1000) and `_ZIP_MAX_TOTAL_BYTES` (50 MiB uncompressed) to
  refuse zip bombs; entries are read into memory and parsed (never extracted to
  disk), so path traversal is a non-issue. A target group (existing or new) and
  an *overwrite* toggle apply to the whole batch; the response reports
  `imported` / `skipped` counts and the first error. The client **auto-batches**
  the selection into ~3 MB-of-content chunks and POSTs them sequentially
  (aggregating the counts), so a large selection doesn't put one oversized
  request on the small hosted VM — pick everything at once and it chunks itself.
- **Bulk delete** — the **Select** toggle (becomes **Done**) reveals a checkbox
  on every persona row and a floating action bar (**Select all** / **Clear** /
  **Delete selected** / **Cancel**) with a live selection count; **Select all**
  only ticks the rows currently visible (active group, matching the search).
  Confirming POSTs the chosen `(group, slug)` pairs to
  `/api/personas/bulk-delete`. Off by default, so the page is unchanged until you
  opt in. The per-persona **Delete** in the right pane (and the row's trash
  quick-action) still handles one-off removals.

Writes go through the registry write layer in `src/orchestrator/personas.py`
(`create_persona` / `update_persona` / `delete_persona` / `import_persona_card`,
which write the `personas` table and locate rows across **all** groups via
`_find_persona_any_group`). Personas live in the shared DB (`db/chat.db`), so —
unlike before — this **works on both local and the hosted mirror**: the
[db-sync sidecar](db-sync.md) mirrors the `personas` table bidirectionally.
The page and its `POST /api/personas*` endpoints stay gated on
`personas.root_exists()`, which now just confirms the DB is reachable (it returns
`404` / an "unavailable" notice only if the database can't be opened at all).
Changes are picked up immediately by the next debate and by `list_personas` (no
caching), and propagate to the other side on the next sync tick (~5s).

## SSE stream (`GET /api/conversations/{cid}/stream`)

Long-lived `text/event-stream` connection. Query string: `?since=<last_id>`
to skip messages the client has already rendered.

**Tick loop** (`POLL_INTERVAL_SECONDS = 1.0`, in `web/api/conversations.py`):

1. `request.is_disconnected()` → break (client closed tab).
2. `messages_since(cid, last_id)` → emit `event: message` per row with
   payload `{...message_row, "content_html": render_markdown(content)}`.
3. `conversation_turn_state(cid)` → if `complete`, emit `event: complete`
   and break; if the row is gone (deleted), break silently; else if
   `current_turn` changed since the last tick (including the first tick),
   emit `event: turn` with `{"current_turn": "<agent-id-or-null>"}` — the
   reader's whose-turn badge listens for this.
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

- **Independent auth realm.** `/api/ingest` is exempt from both the
  optional basic-auth gate (`BasicAuthMiddleware` short-circuits on
  `request.url.path == "/api/ingest"`) and the read-only gate
  (`ReadOnlyMiddleware` exempts it), so the machine-to-machine sidecar only
  needs its bearer token — not the human basic-auth password, and it keeps
  pushing even when the public mirror is read-only (see [Auth](#auth)). The
  bearer-token check is enforced inside the route handler regardless.
- **Opt-in per deployment.** When `AGENT_CHAT_INGEST_TOKEN` is unset, the
  endpoint short-circuits to `404 ingest disabled` — local dev never has
  to think about it.

---

## Auth

> [!IMPORTANT]
> **The hosted Fly deploy is read-only.** Reads (browser pages + JSON GETs)
> are public; every browser **mutation** (stop / delete / orchestrate /
> persona writes) is rejected with `403` because the deploy sets
> `AGENT_CHAT_PUBLIC_READONLY=1` (see `[env]` in [`fly.toml`](../../fly.toml)).
> The bearer-gated `/api/ingest` sync realm is exempt, so the local→Fly
> sidecar keeps pushing. Local dev runs with the flag **off** — fully
> writable and unauthenticated.

`_build_middleware()` in [`src/web_ui.py`](../../src/web_ui.py) assembles the
stack from two independent, default-off env flags:

| Surface | Trigger env var | Status | Mechanism | Realm |
|:---|:---|:---|:---|:---|
| Browser **mutations** (any non-GET/HEAD/OPTIONS, except `/api/ingest`) | `AGENT_CHAT_PUBLIC_READONLY` | **on** for the Fly deploy (`fly.toml`); off locally | `ReadOnlyMiddleware` → `403 read-only deployment`. Keys off the HTTP method, so new mutation routes are covered automatically. | — |
| Browser pages + JSON API | `AGENT_CHAT_BASIC_AUTH_PASSWORD` | off (unset) | HTTP Basic via `BasicAuthMiddleware`, attached when the password is set. Username defaults to `admin`, override with `AGENT_CHAT_BASIC_AUTH_USER`. Listed first so it forms the outermost layer. | `agent_chat` |
| `/api/ingest` | `AGENT_CHAT_INGEST_TOKEN` | active when env var set | `Authorization: Bearer <token>`, constant-time compared. | `agent_chat_ingest` |

Read-only mode is the public-safety baseline (it stops data loss without a
login); basic auth is the heavier gate when you want to lock reads too. They
compose — basic auth challenges first, then the read-only check runs. Both
credential checks use `secrets.compare_digest`. Neither is meant for serious
multi-user auth — for that, front the deploy with whatever your platform
gives you (Cloudflare Access, Tailscale Funnel, …).

`/favicon.svg` is exempt from basic auth (so browsers can fetch the icon for
the auth-challenge tab); `GET` requests are never blocked by read-only mode.

---

## Configuration

| Setting | Where | Default |
|:---|:---|:---|
| DB path | `--db-path` arg or `$AGENT_CHAT_DB` | `<repo>/db/chat.db` (resolved from `src/web_ui.py`'s location) |
| Bind address | `--host` or `$HOST` | `127.0.0.1` |
| Port | `--port` or `$PORT` | `8765` |
| Public read-only mode | `$AGENT_CHAT_PUBLIC_READONLY` | unset → off (writable) locally; `"1"` on the Fly deploy → browser mutations return `403` |
| Basic auth password | `$AGENT_CHAT_BASIC_AUTH_PASSWORD` | unset → gate off; set → HTTP Basic attached |
| Basic auth user | `$AGENT_CHAT_BASIC_AUTH_USER` | `admin` |
| Ingest token | `$AGENT_CHAT_INGEST_TOKEN` | unset → ingest off (404) |

Local dev (no env vars set):

```powershell
.\.venv\Scripts\python.exe src\web_ui.py
# → http://127.0.0.1:8765/
# (DB defaults to <repo>/db/chat.db; override with --db-path or $env:AGENT_CHAT_DB.)
```

Production layout (Fly.io, ingest on, public read-only mode on, browser
basic-auth off) is described in [`fly-deploy.md`](fly-deploy.md) and
[`db-sync.md`](db-sync.md).

---

## Schema sync

`SCHEMA` is duplicated from `src/agent_chat_mcp.py` rather than imported —
the web UI's copy lives in `src/web/db.py` (moved there by the 2026-07-10
split). Reason: keeping the web UI lightweight (no FastMCP/Pydantic on
startup) and letting it boot against an empty Fly volume on first request
via `db_init()`. **When the schema changes, both files must be updated in
the same PR**, plus a CHANGELOG entry. The duplication is annotated with a
`sync-required` note on each side.

---

## Where to look for what

| Concern | File / function |
|:---|:---|
| Add or rename a route | `routes` list in `web_ui.py`, plus an entry in this table. |
| Tweak the homepage layout | `web/render/home.py` (`_render_homepage()` + `_HOMEPAGE_TEMPLATE`), styled by `HOME_CSS` in `web/assets.py`. |
| Tweak the conversations browser or reader | `web/render/conversations.py` (`_conversations_rail()` / `_render_conversations_overview()` / `_render_conversation_main()`), styled by `_CONV_CSS` in `web/assets.py` (+ `BASE_CSS` for `.msg` cards). |
| Adjust Markdown rendering | `_md` instance + the `_link_open_renderer` rule in `web/render/common.py`. |
| Swap syntax-highlighting theme or version | `HIGHLIGHT_JS_HEAD` in `web/assets.py` (CDN URLs + `.hljs` background override). Restart `web_ui.py` (or redeploy) — clients pick up the new CDN on next page load. |
| Change the export format | `render_export_markdown()` in `src/orchestrator/export.py` — but read [`export-format.md`](export-format.md) first; the format is a contract with the library archive + theater app. |
| Touch SSE behavior | `api_stream()` in `web/api/conversations.py` + the inline JS in `_render_conversation_main()`. |
| Force-stop semantics | `stop_conversation()` in `web/db.py` + `api_stop()` in `web/api/conversations.py`. Mirror in `inspect_conversations.cmd_stop`. |
| Auth | `web/security.py` (`BasicAuthMiddleware` + `_build_middleware()`). |
| Ingest | `ingest_payload()` in `web/db.py` + `api_ingest()` in `web/api/sync.py`. See [`db-sync.md`](db-sync.md). |
| Favicon / brand | `FAVICON_SVG` in `web/assets.py` + the `favicon()` route handler in `web_ui.py`. |
| Theater link | `THEATER_URL` in `web/render/common.py` (topbar nav, homepage nav, Featured-debates panel). |
