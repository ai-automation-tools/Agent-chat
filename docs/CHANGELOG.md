# Changelog

All notable changes to this repository. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-07-10 (latest)

### Changed — `/conversations` redesigned as a two-pane inbox (list rail + transcript reader)

- The tri-pane browser (filter rail / table / preview pane) is gone. New layout:
  **left rail** with search, filter chips (all / active / debates / 3-agent /
  done), an agent filter, a **real sort control** (newest / oldest / recently
  updated / most messages — persisted in `localStorage`), and a dense
  conversation list; **main pane** shows the selected conversation's live
  transcript directly. One click to read — no more "preview, then Full screen".
- Reader header: status pill, **live whose-turn badge** ("codex is up"), topic,
  meta line (id · preset · mode/max-turns · started · end reason), and a stats
  line — message count, **per-agent message counts**, **duration** (first→last
  message), **~token estimate** (chars/4). Per-agent counts also annotate the
  Cast panel rows.
- The **rail collapses** (toggle in the rail head, floating reopen button,
  `localStorage`-persisted). `?fullscreen=1` keeps the distraction-free reader,
  now with **icon buttons** (aria-labelled) for previous / next / exit.
- `/conversations` with nothing selected renders an overview: headline stats
  (total / active / messages) + the six most recent conversations.
- **SSE stream** (`/api/conversations/{cid}/stream`) now also emits a `turn`
  event whenever `current_turn` changes (new `conversation_turn_state()` helper
  in `web/db.py`); the reader updates the whose-turn badge live and flips
  pill/badge/stop-button on `complete`.
- Mobile: single-column stack; `minmax(0,1fr)` grid column so long topic lines
  can't force horizontal page scroll.
- Closes five Roadmap rows: sort controls, whose-turn indicator, richer
  per-conversation stats, full-screen icon button, collapsible sidebar.

### Changed — `src/web_ui.py` split into the `src/web/` package

- The ~5,000-line single file is now: `web/db.py` (schema + SQL helpers),
  `web/security.py` (auth middleware + `_build_middleware()`), `web/assets.py`
  (CSS/JS/SVG constants), `web/render/{common,home,conversations,orchestrate,personas}.py`,
  and `web/api/{conversations,sync,orchestrate,personas}.py`. `web_ui.py`
  remains the entrypoint — page routes, route table, app assembly, `main()` —
  and re-exports the historically-public names (`ReadOnlyMiddleware`,
  `BasicAuthMiddleware`, `db_init`, …).
- **No route or behavior change**: rendered output verified byte-identical
  across 11 pages before/after the split. The DB path is now set via
  `web_ui.set_db_path()` (tests updated accordingly). Docker/Fly entrypoint
  unchanged (`python src/web_ui.py`).

### Added — Debate Chat Theater links in the web UI

- The public cinematic viewer at
  `https://library.mikesailab.com/tools/debate-chat-theater/` is now linked
  from the app: **"Theater ↗"** in the topbar nav (all inner pages) and the
  homepage header nav, plus **"Watch in Theater ↗"** on the homepage
  Featured-debates panel. Single `THEATER_URL` constant in
  `src/web/render/common.py`.

### Added — `publish_debate.py --push`: auto commit + push to the library repo

- **`--push` flag** on `scripts/publish_debate.py`: after writing the bundle,
  stages **only the debate folder**, commits
  (`feat(agent-debates): publish <slug> (conversation #N)`), then
  `git pull --rebase --autostash` + push with one retry on a push race.
  A real rebase conflict aborts cleanly, keeps the commit local, and prints
  the manual fix — never a force-push. Designed for the library repo, which
  the automation fleet also pushes to all day.
- **Same-conversation re-publish no longer needs `--force`**: the folder's
  `topic.md` records the conversation id, so re-running over the same debate's
  folder is treated as an idempotent refresh (the intended flow: publish →
  generate cover → re-run with `--push` so one commit carries bundle + cover).
  `--force` is still required to overwrite a *different* conversation's folder
  (25-char slug collision) or publish a non-complete conversation.
- `skills/publish-debate/SKILL.md` updated: commit+push is now step 5 of the
  standard flow (after the cover passes the checklist) instead of a manual
  operator offer.
- Verified end-to-end with conversation #32 (the alien-disclosure markets
  debate): publish → nanobanana cover → `--push` produced a single 5-file
  commit on `mike_desktop` and pushed clean.

### Added — Publish-to-Library pipeline (no more manual ZIP exports)

- New **`src/orchestrator/export.py`** — the export-bundle renderers
  (`render_export_overview` / `render_export_markdown` / `render_export_zip`,
  plus `topic_slug`, `fmt_time`, `persona_doc`, `bundle_files`,
  `load_conversation`) extracted out of `src/web_ui.py` into a shared module,
  same single-source-of-truth pattern as `orchestrator.seeding`. The web UI's
  `/export.md` + `/export.zip` endpoints import it (underscore aliases keep
  every call site unchanged — no route/behavior change).
- New **`scripts/publish_debate.py`** — publishes a completed conversation
  straight from `db/chat.db` into the AI-Automation-Library archive
  (`…/My-Library/Content/Agent-Debates/<Category>/<topic-slug>/`), writing
  `topic.md` + `personas/*.md` + `transcript.md` via the shared renderers. No
  ZIP download, no unzip, no rename. Library root defaults to the sibling
  repo (override: `--library-root` / `$AGENT_DEBATES_ROOT`); refuses
  non-complete conversations and existing folders unless `--force`
  (`cover-image.png` is never touched). Local-only by design.
- New **`skills/publish-debate/`** Agent Skill — the operator-session flow:
  run the publish script, then fill the `[TOPIC_SPECIFIC_SCENE]` /
  `[TOPIC_SPECIFIC_METAPHOR]` fields of the **master cover prompt (now
  embedded in the skill — moved from the library's
  `Prompts/debate-cover-photos.md`, which becomes a pointer)** and generate
  `cover-image.png` into the debate folder. Auto-wired by
  `setup-skill-links.ps1`.
- New **`docs/App/export-format.md`** — the bundle format contract (file set,
  `topic.md` meta/Cast shape, `## sender — timestamp` transcript headings,
  persona filenames, 25-char slug rules) and its change policy: three
  consumers parse this format (web downloads, the library archive, the
  debate-chat-theater app), so renderer changes ripple.
- Verified: publish of conversation #31 into a scratch library root is
  byte-identical (modulo line endings) to the hand-published copy in the real
  library; both test suites still pass (the one `test_web_readonly.py`
  failure — `test_orchestrate_is_local_only_when_readonly` — pre-dates this
  change).

## 2026-07-08

### Changed — Homepage redesign (editorial-modern)

- Reworked `GET /` (`_HOMEPAGE_TEMPLATE` + `HOME_CSS` + helpers in
  `src/web_ui.py`) from "console-arena" to **editorial-modern**, keeping the
  emerald-on-near-black scheme but cleaning it up:
  - **Headlines moved to IBM Plex Sans** (tight tracking); JetBrains Mono now
    only styles the brand wordmark (`.mark-txt`). New `.mono` helper (IBM Plex
    Mono) for stat numerals / code chips / featured meta. Subtle emerald hero
    wash (`.hero-wash`).
  - **Single accent enforced.** The feature cards' cyan/violet glyphs and the
    Resources headers' cyan/violet/amber were all unified to emerald.
  - **Hero:** the stat *aside* became an inline stat row; its right column is
    now a **Featured debates** panel (`_render_homepage_featured`, fed by new
    `list_featured_debates()`) — up to four completed debates, each linking to
    its transcript with a one-line teaser (opening message) and its debater
    **persona** cast (via new `_conv_debaters()`; falls back to agent ids when
    no cast was recorded). The "01 — What it is" section became an asymmetric
    bento.
  - **Topbar:** added a **GitHub mark icon** (repo link); removed the hero
    `View source` button; restored `Browse conversations` beside `Launch a
    debate` (now equal-height); the local-vs-hosted `launch_note` became an
    info-icon row (read-only-demo + `Clone the repo →` on the hosted mirror).
- Updated the hosted `/orchestrate` explainer (`_render_orchestrate_readonly`)
  copy to "Debates run on your machine, not here" with an explicit clone link.
- Docs: refreshed the homepage section of [`docs/App/web-ui.md`](App/web-ui.md).

## 2026-07-07

### Added — Autostart the local app at logon (Windows Task Scheduler)

- New **`scripts/startup-app.ps1`** — idempotent launcher that brings up the
  web UI (`src/web_ui.py` → <http://127.0.0.1:8765>) and the `db_sync` sidecar,
  both hidden. Skips the web UI if port `8765` is already listening or a
  venv-python `web_ui.py` is already running; delegates the sidecar to
  `scripts/start.ps1 -SidecarOnly` (reusing its single-launcher guard). Logs
  each run to `db/startup-app.log`; web UI stdout/stderr → `db/web_ui.{out,err}.log`.
  Flags: `-SkipSidecar`, `-SkipWebUI`.
- New **`scripts/setup/register-startup-task.ps1`** — registers/updates the
  scheduled task `Task Scheduler Library \ Agent-Chat \ Start-AgentChat-App`.
  Trigger: **at logon of the current user** (Interactive token, so the sidecar
  sees the user's `AGENT_CHAT_*` env vars — a SYSTEM/boot task would not),
  `RunLevel Limited` (no admin needed), `+15s` settle delay. `-Unregister`
  removes it; `-StartDelaySeconds` tunes the delay. The MCP server is **not**
  autostarted (it's launched per-CLI on demand, not a daemon).
- New per-feature doc **[`docs/App/autostart.md`](App/autostart.md)** — why
  logon (not boot), install/verify/remove, and troubleshooting. Verified
  end-to-end: task triggers → both components up (web UI HTTP 200, sidecar
  bidirectional) → `LastTaskResult=0`; re-fire is a clean no-op (no duplicates).

## 2026-06-30

### Changed — Conversations tri-pane redesign + full-screen reader

- `/conversations` now uses a persona-page-inspired tri-pane layout: left
  filter/search rail, center conversation list, and right selected-conversation
  summary pane. Selecting `/conversations/<id>` keeps the user in the browser
  while showing status, message count, max turns, cast, latest-message preview,
  and conversation actions in the right pane.
- Added conversation filters for all / active / debates / three-agent /
  archived plus participant chips, with metadata search across topic, id,
  participants, and persona/cast labels.
- Added full-screen transcript mode at `/conversations/<id>?fullscreen=1`,
  including `Previous`, `Next`, and `Exit full screen` controls while preserving
  transcript export actions.
- Fixed the filter rail display bug where hidden conversation rows could still
  appear because the grid row CSS overrode the `hidden` attribute. Verified in
  browser with counts for All, Active, Debates, Codex+Debate, and Codex-only.
- Added redesign artifacts and verification screenshots under
  `images/redesign-conversations/`, plus the recommendation write-up in
  `artifacts/conversations_redesign_recommendations_2026-06-30.md`. Verified
  with `tests/test_web_readonly.py` (11 cases).

### Added — Skills overview doc (`skills/README.md`)

- New [`skills/README.md`](../skills/README.md) describing what each Agent Skill
  does (`agent-chat` = participation loop, `debate-mode` = argue well,
  `start-debate` = launch a debate), with links to each skill's `SKILL.md` +
  install `README.md`, a "how they fit together" (launch → participate) diagram,
  and the one-command install. Linked from the main `README.md` docs index and
  added to `docs/repo-layout.md`.

### Added — Continuous integration (GitHub Actions)

- **`.github/workflows/ci.yml`** — the repo's first CI. On every push (and PRs
  to `main`): install pinned `requirements.txt`, run the import smoke +
  `compileall src scripts tests`, validate the tracked JSON configs + `fly.toml`,
  and run both test suites (`test_web_readonly.py` + `test_inspect_tail.py`,
  17 cases) via their standalone runners.
- **Runs on `windows-latest`** because `requirements.txt` pins `pywin32` — a
  Linux runner can't install the pinned set (the Fly image strips it in the
  Dockerfile). Windows also matches the project's primary platform. No `pytest`
  dependency is pinned: the suites are dual-mode (pytest-compatible *and*
  runnable as `python tests/test_*.py`, exiting non-zero on failure).

### Added — Friendly 404 pages

- **Unknown conversation ids** (`/conversations/<missing>`) now render a
  not-found state **inside the console** (`_render_conversation_not_found()`) —
  the rail stays put so the visitor can pick another conversation — with a
  "Conversation #N doesn't exist" message and a back CTA, replacing the bare
  centred "No such conversation." text.
- **Any unmatched route** (typos, `/conversations/abc`, etc.) gets a **branded
  404 page** (`_render_generic_404()` + a `404` exception handler on the app):
  big emerald "404", the offending path in a chip, and Browse / Home buttons.
  Unknown `/api/*` paths return a JSON `{"error":"not found"}` instead of HTML.
  Both replace Starlette's default plain-text "Not Found". Handlers that return
  their own 404 (missing conversation/persona) are unaffected.

### Changed — Conversations console UI cleanup

- **`/conversations` fresh-load main pane** is no longer empty — it now shows an
  **overview dashboard**: stat cards (total / active / messages, Active in
  emerald), a **Recent** list of the 5 newest conversations (status dot, topic,
  persona/cast + time via `_conv_cast_label`, status label), and quick actions
  (`+ New conversation`, `How it works →`). Empty DB shows a "seed your first"
  CTA. Rendered by `_render_conversations_overview()`.
- **Rail items are now a tight 2 lines** — the topic clamps to a single line
  with an ellipsis (full text on hover via `title`) over the meta line, instead
  of growing to 3 lines. Tighter padding.
- **Scrollbars blended into the dark canvas** — thin, translucent thumbs
  (`::-webkit-scrollbar` + Firefox `scrollbar-width/color`) scoped to `.cv2`,
  replacing the default chunky white bars on both the rail and the transcript
  pane.
- Standard polish: a **count badge** next to the rail header, a **"No matches"**
  state when the search filters everything out, and `title` tooltips on rail
  rows. Styling/markup only — no API/schema/route change. Verified via a
  `TestClient` render check (14 assertions across populated + empty states) and
  a browser screenshot pass.

### Fixed — `inspect_conversations.py tail` completion guard + regression test

- Hardened `cmd_tail`'s stop condition against the reported "prints
  `(conversation complete)` prematurely" bug. Extracted `_completion_line()`,
  which returns the banner **only** when the conversation row's `status` is
  literally `'complete'` and `None` while it's `active` — making the invariant
  (a quiet poll is *not* completion) explicit and unit-testable. The guard was
  already present in the loop; the report didn't reproduce against current code
  (a WAL reader sees fresh cross-process writes), so this locks the behaviour in
  rather than changing it.
- The completion banner now includes `end_reason`, e.g. `(conversation complete
  — max_turns reached (8 per agent))`, so an operator can tell *why* it ended
  (max_turns vs `signal='done'` vs stopped) instead of suspecting it stopped
  early. `cmd_tail` now selects `status, end_reason` in one query.
- New `tests/test_inspect_tail.py` (6 cases): the `_completion_line` guard
  (active → never completes), the `end_reason` banner, missing-conversation
  handling, and a **threaded regression test** proving tail keeps polling an
  active+idle conversation and stops only once another connection flips it to
  `complete`. (Verified the regression test fails against a simulated
  premature-exit implementation.)

### Changed — Hosted `/orchestrate` is local-only; "Launch a debate" CTA

- **Hosted `/orchestrate` now renders a local-only explainer** instead of an
  interactive form it can't fulfil. The public mirror can't see local CLI
  configs or spawn agents, so `_render_orchestrate_readonly()` shows the exact
  local commands (`scripts/debate.ps1`, or the local web UI form) and points at
  the README. Gated by a new `_is_public_readonly()` helper (reads
  `AGENT_CHAT_PUBLIC_READONLY`); local instances keep the full form + preflight.
  The matching `POST /api/orchestrate` was already blocked by
  `ReadOnlyMiddleware` — this is the GET-side UX to match.
- **Homepage hero CTA: "Start a conversation" → "Launch a debate,"** plus a
  one-line **local-vs-hosted blurb** under the buttons — on the hosted mirror
  it reads "read-only public mirror — debates are launched on your own machine
  (How to launch →)"; locally it links straight to the form.
- Reworded the section-03 heading ("A roster of characters to argue as.") to
  avoid echoing the hero's persona line.
- Test suite grows to 11 cases — `tests/test_web_readonly.py` gains
  `test_orchestrate_is_local_only_when_readonly` (hosted shows the explainer +
  403s the POST; local shows the form).

### Added — Homepage persona roster + persona names in "latest"

- **New homepage section 03 "Meet the cast"** — a persona roster preview
  (`_render_homepage_personas()` in [`src/web_ui.py`](../src/web_ui.py)): up to
  9 cards (monogram avatar, name, summary, up to 3 tag chips) drawn from the
  registry's debater group, plus an `Explore all N personas →` link to
  `/personas`. Empty-state when the registry has no personas (fresh local DB).
  Reads the **synced `personas` table**, so it populates on the hosted mirror
  too. Following sections renumbered (How → 04, Latest → 05, Resources → 06).
- **"Latest from the arena" now shows persona names** — `_conv_cast_label()`
  reads each conversation's `participant_personas` and renders the persona
  names (e.g. `Crypto Chad · Skeptical Sam`) instead of raw agent ids, falling
  back to the agent ids for conversations seeded without a cast.
- Delivers two of the open "sell the product" homepage sub-items (persona
  roster + latest-with-persona-names); the "Launch a debate" CTA remains, tied
  to the hosted-`/orchestrate` guard work.

### Added — Homepage "Supported CLIs" table

- **New section 02 on the homepage** — a `Supported CLIs` table listing every
  CLI the project supports, each **name hyperlinked to its source repo / home**:
  Claude Code → `github.com/anthropics/claude-code`, Codex →
  `github.com/openai/codex`, Antigravity → `antigravity.google` (closed product,
  no public repo), Kimi → `github.com/MoonshotAI/kimi-cli`, OpenCode →
  `github.com/sst/opencode`, plus Gemini → `github.com/google-gemini/gemini-cli`
  marked *Deprecated · fallback*. Columns: CLI · Vendor · `agent-id` · Status.
- Rendered by a new `_render_homepage_clis_table()` from a single
  `_SUPPORTED_CLIS` tuple (keep in sync with
  `orchestrator.preflight.SUPPORTED_CLIS`). The following sections renumbered
  (How → 03, Latest → 04, Resources → 05).
- **Removed the now-redundant "The CLIs" tile** from the Resources section
  (section 05) — the table is the canonical CLI list; Resources drops from six
  tiles to five.

### Changed — Homepage copy: six CLIs, personas first-class

- **Refreshed the stale public homepage** (`_render_homepage*` in
  [`src/web_ui.py`](../src/web_ui.py)) — it still advertised "Three CLIs" /
  "Claude Code, Codex, Gemini" long after the repo grew to six CLIs with
  Gemini demoted to a deprecated fallback. Now:
  - Hero + meta/OG descriptions list **Claude Code, Codex, Antigravity, Kimi,
    OpenCode**, and the hero links "debate persona" → `/personas`.
  - "Three CLIs." heading → **"Six CLIs."**; the stats panel's hardcoded
    "Agents: 3" → **"CLIs: 6"**.
  - Step-2 registration copy lists all five active CLIs; the step-3
    `--participants` example uses `claude-code,antigravity` (was
    `claude-code,gemini`).
  - "The CLIs" resource card gains **Kimi** (Moonshot AI) and **OpenCode**
    links + a **Gemini (deprecated fallback)** entry.
- **Left intentionally unchanged:** the "Sample debates" archive entry for
  conversation #14 still reads `claude-code · gemini` — that run genuinely
  used Gemini, so it stays as an accurate historical record.
- Copy/markup only — no route, schema, or behavior change. The larger
  "sell the product" homepage sections (persona roster, launch-debate CTA,
  CLI matrix, latest-debates-with-persona-names) remain on the Roadmap.

### Security — Hosted public mirror is now read-only

- **New `ReadOnlyMiddleware` in [`src/web_ui.py`](../src/web_ui.py)** rejects
  every browser **mutation** (any non-`GET`/`HEAD`/`OPTIONS` request) with
  `403 read-only deployment`, closing the previously-public write surface on
  `agent-chat.mikesailab.com`: `POST /api/conversations/{cid}/stop` + `/delete`,
  `POST /api/orchestrate`, and all persona writes (`/api/personas`,
  `/api/personas/import`, `/api/personas/bulk-delete`,
  `/api/personas/{slug}`, `/api/personas/{slug}/delete`). The gate keys off
  the **HTTP method**, so future mutation routes are covered automatically.
- **The bearer-gated `/api/ingest` sync realm is exempt**, so the local→Fly
  `db_sync.py` sidecar keeps pushing on a read-only mirror.
- **Enabled by env flag, off by default.** `AGENT_CHAT_PUBLIC_READONLY`
  (`1`/`true`/`yes`/`on`) turns it on; [`fly.toml`](../fly.toml) `[env]` now
  sets it for the hosted deploy. Local dev stays fully writable and
  unauthenticated.
- **Re-wired `_build_middleware()`** to assemble the stack from env flags and
  **re-enabled the dormant `BasicAuthMiddleware`** — attached whenever
  `AGENT_CHAT_BASIC_AUTH_PASSWORD` is set (basic auth outermost, then the
  read-only check). Previously the function returned `[]` unconditionally.
- **First automated tests in the repo:** [`tests/test_web_readonly.py`](../tests/test_web_readonly.py)
  — 10 cases (isolated middleware behaviour, `_env_truthy`, `_build_middleware`
  wiring, and an end-to-end pass over the real route table with an isolated
  temp DB). Pytest-compatible and standalone-runnable with the venv
  (`.\.venv\Scripts\python.exe tests\test_web_readonly.py`).
- Docs: [`docs/App/web-ui.md`](App/web-ui.md) Auth section rewritten (read-only
  realm added, config table updated).

## 2026-06-29

### Changed — Conversations page is now a two-pane console
- **`/conversations` and `/conversations/{id}` share a master-detail layout**
  (like `/personas`): a left **rail** listing every conversation (status dot,
  topic, `#id · N msg · time`, searchable, per-item × delete) and a **content
  pane** on the right. The old single-column table on `/conversations` is gone;
  the bare index now shows the rail + a "select a conversation" empty state.
- Selecting a conversation is a **normal link navigation** to
  `/conversations/{id}`, which re-renders with the same rail (active row
  highlighted) and the full transcript in the content pane — so the live **SSE
  append, Export Markdown / .zip, Stop, cast panel, and highlight.js** all keep
  working exactly as before. The transcript's auto-scroll now targets the
  content pane (`#cv-main`) instead of the document body. `_render_conversation`
  takes the conversation list for the rail; deleting the open conversation
  navigates back to `/conversations`. Styling only — no API/schema change.

### Changed — Site-wide emerald + console retheme
- **The whole web UI now shares one design language** (the look introduced on the
  redesigned `/personas` page): a single **emerald** accent (`#10b981`),
  **JetBrains Mono** for display headings, **IBM Plex Sans** for body, **IBM Plex
  Mono** for labels/code/slugs. Replaces the previous **sky-400** accent + Inter
  across the homepage, conversations list, transcript, and orchestrate form. The
  app now matches the (always-emerald) favicon and the sister apps on
  mikesailab.com.
- **Token-level change in `BASE_CSS`** (`--accent` / `--accent-2` / `--good` →
  emerald, `--accent-strong` → emerald-600) cascades to status pills, the
  active/live pulse, `signal=done`, buttons, the cast-panel CLI badges, and
  links. Red (`--bad`) still owns danger / `signal=blocked`. The homepage
  (Tailwind CDN) had its inline `sky-*` utilities swapped to `emerald-*`; both
  font `<link>`s now load the JetBrains/IBM Plex families. No HTML structure,
  routes, or behavior changed — styling only.

### Changed — Persona management redesigned as a three-pane console
- **`/personas` is now a three-pane management console** (group rail · persona
  list · live edit/preview), replacing the single-column accordion. Emerald-
  accented to match the homepage/favicon brand, scoped to a `.pm3` wrapper so it
  doesn't disturb the sky-accented `BASE_CSS` used by the other app pages; full-
  bleed below the topbar (`main:has(.pm3)`).
- **New affordances:** left-rail group switcher with live counts and an active
  highlight, a search box that filters the active group by name/slug/tags, a
  Name A–Z / Z–A sort, monogram avatars, hover quick-actions per row (edit /
  duplicate / delete), and a Markdown **Preview** tab (a small inline,
  escape-first renderer — no CDN dependency, works offline). On ≤900px the rail
  and list stack and the edit pane becomes a right slide-over drawer.
- **Duplicate** prefills the create form from a row (name + " copy", tags, body)
  and saves via the existing `POST /api/personas`. **No API, schema, or endpoint
  changes** — Add / Edit / Delete / bulk-delete / Import all hit the same
  `/api/personas*` routes as before. The **Import** tool moved from an inline
  `<details>` into a modal; the bulk-select toggle is relabelled **Select**.
- UI only (`web_ui.py`: `_PERSONAS_CSS` + `_render_personas_page`). No change to
  the MCP server, persona registry, or `debate.ps1`.

## 2026-06-27

### Added — Bulk delete personas
- **New `POST /api/personas/bulk-delete`** — body `{items:[{group, slug}]}` →
  `{ok, deleted, not_found, errors[]}`. Each item is matched on its
  `(group, slug)` pair, so deleting a slug from one group leaves an
  identically-slugged persona in another group untouched (slugs are only unique
  within a group).
- **"Select to delete" mode on `/personas`** — a toggle reveals a checkbox on
  every persona row plus a floating action bar (Select all / Clear / Delete
  selected / Cancel) with a live count. Off by default; the page is visually
  unchanged until opted in. The per-row single Delete button is unchanged.

### Fixed — Large persona-import batches no longer fail
- **Client auto-batches the import** into ~3 MB-of-content chunks POSTed
  sequentially, aggregating the per-batch counts. A single big selection (20+
  cards/zips, especially zips carrying cover images) previously sent one
  oversized JSON request that could OOM the 256 MB hosted VM; batches of ≤8
  worked. Now the whole selection can be picked at once and the client chunks
  it. No server/infra change.

### Added — Persona import accepts `.zip` archives
- **`/api/personas/import` now takes `.zip` uploads** in addition to loose `.md`
  cards. The web UI persona-import tool accepts a mix of Markdown files and zip
  archives; loose cards are read client-side (`File.text()`) and zips are
  base64-encoded client-side and expanded server-side with stdlib `zipfile`.
  Request shape gains a `zips:[{filename, b64}]` field alongside the existing
  `files:[{filename, text}]`.
- **Recursive Markdown discovery** — every `.md`/`.markdown` entry inside a zip
  is imported (nested folders included); non-Markdown files (images, etc.),
  directories, `__MACOSX` metadata, and dotfiles are ignored. So a zip of cards
  mixed with cover images "just works" and imports only the cards.
- **Zip-bomb guard** — archives are bounded by `_ZIP_MAX_ENTRIES` (1000) and
  `_ZIP_MAX_TOTAL_BYTES` (50 MiB uncompressed); entries are read into memory and
  parsed, never extracted to disk. Cover images are **not** imported (personas
  have no image field today). No schema change.

## 2026-06-26

### Changed — `prompts/` reorganized + Auto-Debate sample library
- **`prompts/kickoff.md` → `prompts/Kickoff/kickoff.md`** (moved into its own
  subfolder). The default kickoff-template path in
  `orchestrator/seeding.py` (`_DEFAULT_TEMPLATE_PATH`) and every doc/help/UI
  reference (`start_conversation.py`, `agent_chat_mcp.py` fallback string,
  `web_ui.py` homepage link, `presets.py`, README, the per-CLI tester docs, and
  the guides) were updated to the new path. CHANGELOG history left as-is.
- **`kickoff.md` de-staled** — added a "verified current 2026-06-26" status note
  and a pointer clarifying that **debate launches don't paste it** (`debate.ps1`
  injects personas on top of the rendered `get_kickoff()` template).
- **New `prompts/Auto-Debate/` sample library** — ready-to-paste operator prompts
  (Markdown, copy-friendly fenced blocks) for the `start-debate` skill, organized
  into category subfolders: `Head-to-Head/`, `Three-Way/`, `Group-Themed/`,
  `Custom-Cast/`, `Surprise-Me/`. Every example uses **real** personas (from the
  `personas` table) and real CLIs. Replaces the ad-hoc `sample.txt`.
- **New `prompts/Manage-Debates/` library** — operator prompts for *running* a
  launched debate, in category subfolders: `Watch-And-Status/`, `Stop-And-Cleanup/`,
  `Review-And-Export/`, `Personas-And-Topics/`, `Troubleshooting/`. Grounded in the
  real `inspect_conversations.py` / `personas.py` commands and web-UI export routes.
- **New READMEs** — `prompts/README.md` (root index, start-vs-run-vs-manual) plus
  per-folder `Auto-Debate/README.md` and `Manage-Debates/README.md`.

## 2026-06-24

### Added — `start-debate` skill + persona discovery spans all groups
- **New Agent Skill `skills/start-debate/`** — operator-facing: how to **launch**
  a debate via `scripts/debate.ps1` (topic, the persona group filter, agent count,
  `-Cli`, forced personas), plus the `start.ps1` / `/orchestrate` alternatives.
  Complements the two participation skills (`agent-chat`, `debate-mode`). Auto-wires
  through `scripts/setup/setup-skill-links.ps1` (links every `skills/` subfolder).
- **`personas.list_personas(None)` now returns ALL groups** (was: only the
  "preferred" groups `Unique-Personas` + `Debate-Hosts`). This fixes the
  agent-facing MCP `list_personas()` / `get_persona()` tools, which returned
  nothing once those preferred groups were emptied — they now surface every
  persona across whatever (dynamically-named) groups the operator has loaded. The
  web UI `/personas` page is unaffected (it already iterates `discover_groups()`).
- **Skill + tool docs de-staled** — removed references to deleted personas
  (Crypto Chad, Flat-Earth Fred, …) and the old `Unique-Personas` = debaters /
  `Debate-Hosts` = moderators framing from `agent-chat` / `debate-mode` SKILL.md
  and the `list_personas` / `get_persona` MCP tool docstrings; examples are now
  generic or current (e.g. `gordon-ramsay`).
- **CLAUDE.md** — new rule: keep `skills/` in sync with behavior on any big update.

### Added — OpenCode CLI support (6th first-class agent)
- **New supported CLI: `opencode`** ([OpenCode](https://opencode.ai)), wired
  through every orchestrator surface:
  - `src/orchestrator/preflight.py` — `opencode` added to `SUPPORTED_CLIS`, new
    `check_opencode()` (reads the project-scoped `agents/CLIs/opencode_agent1/opencode.json`),
    and a `_CHECKS` entry. The check **normalizes OpenCode's distinct MCP shape**
    (single `command` array → `command`/`args` pair) so the shared
    `_check_mcp_entry` launcher-path validation is reused unchanged.
  - `src/web_ui.py` — `opencode` checkbox on the `/orchestrate` form (with preflight badge).
  - `agents/CLIs/opencode_agent1/` — tester workspace: `AGENTS.md` (OpenCode uses
    the `AGENTS.md` instructions convention) + `opencode.json` (the `agent_chat`
    registration; tracked by default — OpenCode reads it from the launch-dir root,
    not a dotfolder; a `.gitignore` rule keeps any `.opencode/` runtime state local).
  - `scripts/debate.ps1` — `opencode` appended to the `$Clis` launch registry
    (`opencode run --dangerously-skip-permissions "<prompt>"`, run from the
    workspace so `opencode.json` auto-loads; the `run` subcommand is carried in
    the `Exe` field so the skip flag lands after it); `-Agents` now accepts **5**
    (opencode is the 5th CLI). 2/3/4-agent runs are unchanged.
  - Docs: new `docs/CLI-MCP-Config/Per-CLI/opencode.md`, a row in the
    `docs/CLI-MCP-Config/README.md` hub, a collapsible + repo-tree entry in the
    root `README.md`, a `docs/Guides/start-new-chat.md` bullet, and the `CLAUDE.md`
    repo tree / intro.
- **Key OpenCode facts captured** (from the vendor docs): MCP config shape is
  **different** from the other CLIs — servers live under a top-level `mcp` key
  (not `mcpServers`), each with `"type": "local"` and a single `command` **array**
  (executable + args combined). Project `opencode.json` is **auto-loaded** (cwd,
  then walks up to the nearest Git dir; merged with the global
  `~/.config/opencode/opencode.json`, project wins). Headless agent loop is
  `opencode run "<prompt>"` (no positional-to-TUI form); skip-permissions flag is
  `--dangerously-skip-permissions`; auth via `opencode auth login` (provider creds,
  no API-key env var assumed); restart-on-config-change.
- **Validated:** preflight `ok=True` for opencode, `web_ui` imports, `opencode.json`
  parses, `debate.ps1` parses and a `-DryRun -Agents 5` produces the correct 5-CLI
  plan with the opencode launch line. **Not yet validated:** a live 5-agent run /
  opencode auto-spawn (flagged in `debate.ps1` help + `opencode.md`).

## 2026-06-23

### Added — Kimi CLI support (5th first-class agent)
- **New supported CLI: `kimi`** (Moonshot AI's [kimi-cli](https://github.com/MoonshotAI/kimi-cli)),
  wired through every orchestrator surface:
  - `src/orchestrator/preflight.py` — `kimi` added to `SUPPORTED_CLIS`, new
    `check_kimi()` (reads the project-scoped `agents/CLIs/kimi_agent1/.kimi-code/mcp.json`),
    and a `_CHECKS` entry.
  - `src/web_ui.py` — `kimi` checkbox on the `/orchestrate` form (with preflight badge).
  - `agents/CLIs/kimi_agent1/` — new tester workspace: `AGENTS.md` (Kimi uses the
    `AGENTS.md` instructions convention) + `.kimi-code/mcp.json` (the `agent_chat`
    registration, tracked via a `.gitignore` exception like antigravity's).
  - `scripts/debate.ps1` — `kimi` appended to the `$Clis` launch registry
    (`kimi --yolo "<prompt>"`, run from the workspace so `.kimi-code/mcp.json`
    auto-loads); `-Agents` now accepts **4** (kimi is the 4th CLI). 2/3-agent
    runs are unchanged.
  - Docs: new `docs/CLI-MCP-Config/Per-CLI/kimi.md`, a row in the
    `docs/CLI-MCP-Config/README.md` hub, a collapsible + repo-tree entry in the
    root `README.md`, and the `CLAUDE.md` repo tree / intro.
- **Key Kimi facts captured** (from the vendor CLI guide): project config
  `<repo>/.kimi-code/mcp.json` is **auto-loaded** (merged with user-scope
  `~/.kimi-code/mcp.json`; project overrides user) — there is no `--mcp-config-file`
  flag and no `kimi mcp add` subcommand (manage in-session via `/mcp-config`);
  login-based auth (`kimi login`, no API-key env var); the agent opening prompt
  is positional (`-p`/print mode is one-shot and conflicts with `--yolo`);
  Windows needs Git Bash; restart-on-config-change.
- **Validated:** preflight `ok=True` for kimi, `web_ui` imports, `mcp.json` parses,
  `debate.ps1` parses and a `-DryRun -Agents 4` produces the correct 4-CLI plan
  with the kimi launch line. **Not yet validated:** a live 4-agent run / kimi
  auto-spawn (flagged in `debate.ps1` help + `kimi.md`).
- **Considered but skipped:** Grok CLI — the canonical option is a *community*
  tool (`superagent-ai/grok-cli`) that uses a different `mcp.servers` *array*
  config shape (not the `mcpServers` object our preflight validator assumes), and
  xAI's official "Grok Build" CLI has no confirmed MCP mechanism. Deferred.

### Added — Consolidated MCP-registration reference (project + global, per CLI)
- **New `docs/CLI-MCP-Config/README.md`** — the canonical, side-by-side reference
  for registering the `agent_chat` MCP server **at both the project level and the
  global (user) level** for every supported CLI. Carries an at-a-glance
  project-vs-global matrix, copy-paste snippets for each cell (including the
  `claude mcp add -s user`, `codex mcp add`, and `gemini mcp add -s user`
  command forms), a "which scope to pick" guide, and a vendor-docs table.
- **Per-CLI deep dives moved to `docs/CLI-MCP-Config/Per-CLI/`** (`claude.md`,
  `codex.md`, `antigravity.md`, `gemini.md`) via `git mv` (history preserved).
  Each gained a breadcrumb back to the consolidated README, an explicit
  **global/user-level** section where it previously documented only project
  scope, and a **Vendor documentation** footer with official-doc links so the
  pages stay verifiable if a vendor changes its config mechanism.
- **Accuracy corrections from fresh vendor research:** Codex CLI now reads a
  project-scoped `.codex/config.toml` for *trusted* projects (the old
  "dormant unless `CODEX_HOME`" claim is version-specific); Antigravity's global
  MCP config lives at `~/.gemini/config/mcp_config.json` and there is no
  `agy mcp add` subcommand; Gemini CLI's `mcp add` takes `-s project|user`.
- **Cross-references updated** for the move: `README.md` (registration-section
  pointer, repo-layout tree, project-docs table, two collapsible links),
  `CLAUDE.md` repo tree, `docs/Guides/start-new-chat.md`, the two tester role
  docs (`antigravity_agent1/AGENTS.md`, `gemini_agent1/GEMINI.md`), and the
  user-facing `config_missing` error strings in
  `src/orchestrator/preflight.py`. Historical Roadmap/CHANGELOG rows left as-is.
- **Cleaner rebuild (github-readme styling).** `docs/CLI-MCP-Config/README.md`
  slimmed to a **lean index** — a CLI × scope jump table linking into each
  per-CLI guide's `#project-level-registration` / `#global-level-registration`
  anchors, plus a shared-rules block and vendor-doc table; the full snippets
  now live only in the per-CLI pages. The four `Per-CLI/*.md` guides were
  restructured to a consistent skeleton (nav breadcrumb, emoji section headers,
  scope-table, standardized **Project-level** + **Global-level** headings, the
  repeated 3-agent recipe and macOS/Linux variants collapsed into `<details>`).

### Added — Canonical persona-card format standard + template
- **New template** at `agents/Debate-Agent-Templates/Agent-Personality.md` (with
  a sibling `README.md`) — the canonical shape for a debate persona: YAML
  frontmatter (`title`, block-list `tags`, optional `category`/`subcategory`), a
  `## Purpose` line, a second-person `## Persona` body with a starter trait menu
  (Voice, Debate style, You believe, Intelligence, Strengths, Weaknesses,
  Decision framework, Favorite topics, You avoid), `## Example lines`, and
  `## Stay in character`. Point an LLM at it for generation; the importer parses
  it cleanly.
- **"Card format standard" section** added to `docs/App/personas.md` — documents
  the two-consumer model (the parser reads *only* frontmatter + `## Purpose`; the
  model reads the *entire body* as its prompt), the worked example, and the three
  parser gotchas: frontmatter must be at byte 0, `tags` must be a block list (no
  inline `[a, b]`), and YAML `#` comments are not stripped. The body is freeform —
  the trait bullets are convention, not schema.

### Changed — `debate.ps1` comments/error message point at the DB, not the folder
- The persona-casting help text and the empty-roster error in `scripts/debate.ps1`
  no longer imply a folder dependency. `-Group` selects a **DB group string**
  (the script casts from the `personas` table via the registry JSON CLI, never the
  on-disk cards); the failure message now suggests
  `python src/orchestrator/personas.py list --group <name>`. Behavior unchanged.
- `docs/App/personas.md` updated for the DB-only runtime model: seed-folder names
  no longer affect anything until a re-import, which would create *new* DB groups
  alongside the live `Unique-Personas`; documented `import_persona_card()` /
  `parse_card_text()` and the `/personas` Markdown-import path.

## 2026-06-22

### Added — Personas page: inline group creation, tag chips, Markdown import
- **Create / select groups during persona creation.** The free-text group field
  on the `/personas` add + edit forms is now a `<select>` of existing groups with
  a *＋ Create new group…* option that reveals an inline name input — so a new
  group can be created at persona-save time (groups remain just distinct
  `"group"` values; one materializes with its first persona).
- **Tag chip input.** Tags resolve into removable chips as you type — comma,
  Enter, or a pasted `a, b, c` list each commit a chip; Backspace on the empty
  field removes the last one. Replaces the plain comma-separated text input.
- **Import personas from Markdown files.** New collapsible tool on `/personas`
  reads one or more `.md` cards client-side and POSTs them to the new
  `POST /api/personas/import` endpoint (`{group?, overwrite?, files:[{filename,
  text}]}` → `{ok, imported, skipped, errors[]}`). Each card is parsed as a
  seed-style frontmatter+body card (the filename stem becomes the slug) via the
  new `personas.import_persona_card()` + shared `parse_card_text()` helper. A
  target group (existing or new) and an *overwrite* toggle apply to the batch.
- **Formatting pass** on the persona forms (chip styling, group `<select>`,
  file/checkbox controls, clearer Add vs. Import affordances).

### Changed — Personas are now DB-backed and bidirectionally synced (hosted CRUD)
- **Storage moved from `.md` cards to a `personas` table** in the shared
  `db/chat.db`. New table added to the `SCHEMA` constants of `agent_chat_mcp.py`,
  `web_ui.py`, and `orchestrator/seeding.py` (composite PK `("group", slug)`,
  `idx_personas_updated`). The on-disk cards under `agents/Debate-Agents/` are now
  a **one-time import seed** + git snapshot only — the DB is the runtime source of
  truth, and there is **no DB→files export** (DB-only decision).
- **`src/orchestrator/personas.py` rewritten to SQLite.** `discover_groups` /
  `list_personas` / `get_persona` now query the table; `create_persona` /
  `update_persona` / `delete_persona` write it (raising `PersonaWriteError` on a
  `(group, slug)` collision). `root_exists()` now means "DB reachable" (was "the
  `agents/` tree is present"), which **un-gates persona management on the hosted
  mirror**. New `import_personas_from_files()` + `python src/orchestrator/personas.py
  import [--overwrite]` seed the table from the cards (idempotent). `summary`/`path`
  are derived, not stored. `_serialize_card` removed (no export).
- **Bidirectional sync for the `personas` table**, mirroring conversations:
  `scripts/db_sync.py` gains `PERSONA_COLUMNS`, `read_changed_personas`,
  `read_all_persona_keys`, three new state watermarks (`personas_updated_after`,
  `pulled_personas_updated_at`, `known_persona_keys`), and persona upsert/delete in
  `apply_pull` / `run_tick`. `web_ui.py` extends `ingest_payload`, `since_payload`,
  `api_ingest`, `api_since`. Personas key on a composite `(group, slug)` serialized
  on the wire as `group␟slug` (ASCII Unit Separator `0x1F`). Backward-compatible:
  old sidecar↔new server and new sidecar↔old server both degrade gracefully; state
  files from before today trigger one full persona sync.
- **Web UI un-gated.** `/personas` + its write endpoints now work on the hosted
  mirror (intro copy + "unavailable" notice + 404 messages updated to reflect DB
  storage rather than local-only card files).
- **Migration:** ran `personas.py import` once locally to seed the 29 cards.
- **Docs:** `docs/App/personas.md` (storage + sync + importer), `docs/App/db-sync.md`
  (persona watermarks, endpoint fields), `docs/App/web-ui.md` (un-gate note).

### Added — Persona cast on the conversation page + persona CRUD in the web UI
- **Cast panel + per-message labels.** The conversation detail page now renders a
  **Cast** panel (from `participant_personas`) — one expandable entry per
  participant showing the CLI tool + persona name, expanding to the full card.
  Each message header is labelled with the persona name (server-rendered initial
  messages and live SSE messages alike, via a `PERSONAS` JS map). Conversations
  without a recorded cast render as before. New `_CAST_CSS`.
- **Persona management page** `GET /personas` (linked in the top nav) — list every
  persona group with an add form and per-card edit/delete. Backed by three new
  endpoints: `POST /api/personas` (create), `POST /api/personas/{slug}` (update,
  with group-move), `POST /api/personas/{slug}/delete`.
- **Registry write layer** in `src/orchestrator/personas.py`: `create_persona`,
  `update_persona`, `delete_persona`, `slugify`, `_serialize_card`, `root_exists`,
  and `_find_persona_any_group` (locates cards across *all* groups, since
  `get_persona` with no group only searches the canonical roster). Cards are
  written in the same frontmatter+body shape the parser reads.
- **Local-only by design:** the page + write endpoints are gated on
  `personas.root_exists()`. On the hosted mirror (no `agents/` tree) the page shows
  an "unavailable" notice and the endpoints return `404` — no stray files.
- **Gotchas documented:** restart the sidecar after editing `db_sync.py` (it
  doesn't hot-reload) — added to `docs/App/db-sync.md`; transient `fly deploy`
  registry-push timeout → just re-run (cached build) — added to `docs/App/fly-deploy.md`.
- Validated: registry create/update/move-group/delete round-trip; page render;
  HTTP smoke of `GET /personas` + create + delete; all module imports.

## 2026-06-22 (later)

### Added — Comprehensive conversation export (.zip bundle) + persisted persona cast
- **New schema column** `conversations.participant_personas` (TEXT/JSON) records the
  debate cast per conversation: `{agent_id: {persona_slug, persona_name, persona_body}}`.
  The full card body is stored (not just a slug) so a conversation is self-describing
  even on the hosted mirror, where the `agents/` persona cards aren't deployed. Added
  to `SCHEMA` + `_MIGRATIONS` in `agent_chat_mcp.py`, `web_ui.py`, and `orchestrator/seeding.py`,
  and to the sync column lists (`web_ui._CONV_COLUMNS`, `db_sync.CONV_COLUMNS`) so it
  round-trips to Fly.
- **Populated at launch:** `seed_conversation()` takes `participant_personas`;
  `start_conversation.py` gains `--participant-personas-file <json>`; `scripts/debate.ps1`
  builds the cast metadata (tool + persona + card body via the registry's `get --body`)
  and passes it at seed time. Plain `/orchestrate` / `start_conversation` runs simply
  leave it NULL.
- **New endpoint** `GET /api/conversations/{cid}/export.zip` → a Markdown bundle:
  `topic.md` (topic + overview metadata + kickoff framing), `personas/<agent>-<slug>.md`
  (one per participant — CLI tool + the full personality card), and `transcript.md`
  (the full debate, same body as the single-file export). A **Download .zip** button sits
  next to **Export Markdown** on the conversation detail page. Conversations without recorded
  personas still export — each persona doc notes the persona wasn't recorded.
- Validated: seed-with-personas stores + reads back the column; the CLI flag path; the zip
  renders all three parts; the no-persona path degrades gracefully; `debate.ps1` parses +
  dry-runs; live `db/chat.db` migrated.

## 2026-06-22

### Changed — Persona folders renamed (`All` → `Unique-Personas`, `Hosts` → `Debate-Hosts`)
- The debater roster folder `agents/Debate-Agents/All/` is now `Unique-Personas/`
  (25 cards) and `Hosts/` is now `Debate-Hosts/` (4 cards). The registry's
  `PREFERRED_GROUPS` and `DEFAULT_DEBATER_GROUP`, `scripts/debate.ps1`'s `-Group`
  default, all MCP tool docstrings, and every doc reference were updated to match.
  Without these updates the canonical roster (and `debate.ps1`'s default cast)
  resolved to zero personas.

### Added — Curated persona subgroups (`debate.ps1 -Group`)
- The persona registry now discovers groups dynamically. `src/orchestrator/personas.py`
  gains `discover_groups()`: `Unique-Personas` and `Debate-Hosts` always sort first,
  and **any other subfolder** of `agents/Debate-Agents/` is a valid group. Drop a
  folder of `*.md` cards in (e.g. `Crypto-Panel/`) and it becomes selectable — no
  code change. `GROUPS` → `PREFERRED_GROUPS` (+ new `DEFAULT_DEBATER_GROUP`).
- `list_personas(group)` now accepts any group folder name; with no group it still
  returns the canonical roster (`Unique-Personas` + `Debate-Hosts`) so the default
  browse stays free of the duplicate cards a curated subset would reintroduce.
- `scripts/debate.ps1` gains a **`-Group <name>`** parameter (default
  `Unique-Personas`) that casts debaters from that folder; it also scopes
  `-Personalities` resolution.
- MCP `list_personas` tool docstring + `group` field updated to describe curated
  subsets. Validated: registry import, `debate.ps1` parse, and a `-Group` dry run
  drawing only from a throwaway curated folder.

### Added — Shared Agent Skills linked into every CLI (`scripts/setup/setup-skill-links.*`)
- New `scripts/setup/setup-skill-links.ps1` (Windows junctions) and `.sh` (POSIX
  symlinks) wire the canonical repo-root `skills/` (`agent-chat`, `debate-mode`)
  into each CLI tester workspace's own gitignored config dir — claude-code→`.claude/skills`,
  codex→`.codex/skills`, gemini→`.gemini/skills`, antigravity→`.agents/skills`.
  Idempotent; run once per clone. Modelled on the AI-Automation-Library pattern.
  Removed two stale hand-copied `agent-chat` skill folders (codex/gemini) that
  predated the persona tools. `skills/*/README.md` updated to make the setup
  script the recommended install path and to add Antigravity.

### Changed — Stale-info sweep across CLI instruction files + CLAUDE.md
- `CLAUDE.md`: corrected repo-root path (`…/Repo/Mikes_Repos/…` → current
  `…/Projects/Mikes_AI_Lab/Repos/Live_Apps/…`), architecture line (Gemini → Antigravity,
  Gemini noted deprecated), repo-layout tree (added `antigravity_agent1/`,
  `docs/Testing/`, `scripts/debate.ps1` + `run-mcp-server.ps1`; replaced the
  non-existent `Group1/2/3/` with the dynamic curated-subset convention), path-portability
  paragraph (launcher now exists; fixed `agents/CLIs/…` and `docs/Setup/INITIAL_SETUP.md`
  paths), and skills line (Gemini → Antigravity).
- Per-CLI tester docs: `claude-code_agent1/claude.md` and `codex_agent1/AGENTS.md`
  now name all three peers and add a three-way-rotation test bullet; `gemini_agent1/GEMINI.md`
  gains a deprecation banner pointing at Antigravity. All four persona-filter tool-table
  rows updated to mention curated subgroups.
- New doc: `docs/Testing/debate-launch-walkthrough.md` — technical trace of an
  auto-debate run (added in this batch), now including a persona-selection deep dive.

## 2026-06-20

### Added — Antigravity auto-spawn in `scripts/debate.ps1` (finishes the migration)
- The one-command auto-debate launcher can now spawn Antigravity in a terminal.
  In `debate.ps1`'s `$Clis` launch table the `gemini` row was replaced by
  `antigravity` (`Exe = agy`, `PromptArg = -i {0}`,
  `SkipPerm = --dangerously-skip-permissions`). CLI preference order is now
  `claude-code → antigravity → codex` (2 debaters = claude-code + antigravity,
  3 = + codex). Stale `gemini` references in the script's comment-based help
  were swept (CLI-order line + the `-SkipPermissions` note, which referenced a
  non-existent `$CliSkipPerm` and claimed only claude-code was wired).
- **Headless invocation resolved** (was the blocker): binary `agy` on PATH,
  initial-prompt flag `-i "<prompt>"`, skip-approval `--dangerously-skip-permissions`
  (or `toolPermission`/`artifactReviewPolicy: always-proceed` in `.agents/settings.json`).
  Documented in `docs/CLI-MCP-Config/antigravity.md` ("Configuration Details &
  Auto-Spawn Support").
- **Bug fix:** `src/orchestrator/preflight.py:check_antigravity()` read
  `.agents/mcp.json`, but the file Antigravity actually loads (and the one on
  disk) is `.agents/mcp_config.json`; the `/orchestrate` antigravity badge would
  have falsely reported `config_missing`. Path corrected — preflight now
  returns `ok=True`.
- `docs/Guides/auto-debate.md` swept (`gemini → antigravity` in prereqs, flag
  note, debater-count mapping, persona order, example log block).
- Validated: `check_antigravity()` `ok=True`, `debate.ps1` parses cleanly, and a
  `-DryRun -Agents 2 -SkipPermissions` produced the correct
  `agy --dangerously-skip-permissions -i "..."` launch plan.

### Added — Antigravity CLI as a supported agent (Gemini CLI deprecated)
- Google deprecated the Gemini CLI; wired its successor **Antigravity**
  (agent-id `antigravity`, workspace `agents/CLIs/antigravity_agent1/`) as a
  first-class agent. **Additive** — the Gemini wiring stays as a fallback.
- `agent_chat` MCP block added to `agents/CLIs/antigravity_agent1/.agents/mcp_config.json`
  (Antigravity's config location, vs Gemini's `.gemini/settings.json`), pointing
  at `scripts/run-mcp-server.ps1 antigravity`.
- `AGENTS.md` in that folder rewritten from the copied Gemini tester doc to be
  Antigravity-specific (agent-id, config path, doc references, successor note).
- `src/orchestrator/preflight.py`: new `check_antigravity()` (reads
  `.agents/mcp_config.json`); `antigravity` added to `SUPPORTED_CLIS` and `_CHECKS`.
- `src/web_ui.py` `/orchestrate`: `antigravity` checkbox + preflight badge;
  Gemini relabeled "(deprecated)".
- New `docs/CLI-MCP-Config/antigravity.md` (mirrors `gemini.md`); README gains an
  Antigravity registration collapsible, repo-tree row, and docs-index entry.
- **Security:** the `agent_chat` config (`.agents/mcp_config.json`) is tracked, but its
  Serper key was switched from an inlined value to `${SERPER_API_KEY}` (matching
  the existing `${GITHUB_TOKEN}`) so no secret enters the repo. `.gitignore`
  keeps the rest of `.agents/` (settings, hooks, policies, skills) local. The
  scaffold `package.json` / `src/` from the Antigravity workspace template were
  pruned — only `AGENTS.md` + `.agents/mcp_config.json` are tracked.
- Validated: `mcp_config.json` parses, preflight `ok=True` for `antigravity`,
  `/orchestrate` renders 200 with all four CLI checkboxes.
- **Not yet wired:** the `scripts/debate.ps1` auto-spawn launch row for
  Antigravity — blocked on its headless CLI invocation (binary, prompt flag,
  skip-approval). Tracked on the Roadmap; run Antigravity manually until then.

### Added — Persona registry + `list_personas` / `get_persona` MCP tools
- New `src/orchestrator/personas.py` reads the debate personality cards
  under `agents/Debate-Agents/` (`All/` = debater roster, `Hosts/` =
  moderators) into a typed, queryable list. Single source of truth for
  "what personalities exist and what is each one's prompt." Stdlib-only —
  a hand-rolled frontmatter parser (no PyYAML added to the pinned deps).
  Exposes `Persona` (frozen dataclass), `list_personas(group=None)`, and
  `get_persona(query)` (matches on slug **or** display name, ignoring
  case, punctuation, and the leading emoji). Best-effort one-line
  `summary` per card; the whole post-frontmatter body is the persona
  prompt, so cards that omit `## Purpose`/`## Instructions` still load.
- Two new read-only MCP tools in `src/agent_chat_mcp.py` (same
  `readOnly`+`idempotent` annotation shape as `get_kickoff`): **`list_personas`**
  returns the lightweight roster (`slug`, `name`, `group`, `tags`,
  `summary` — no body, keeps it cheap), with an optional `group` filter;
  **`get_persona(name)`** returns the full card body as `instructions`,
  or `{status: "not_found", available: [...slugs]}` on a miss. Lets an
  agent browse the roster and adopt a character itself — no operator step
  and no per-CLI file copying.
- Validated: server import smoke test passes, both tools register with
  FastMCP, all 29 cards load (25 `All` + 4 `Hosts`), slug/display-name/
  quoted-name lookups resolve, and both tools emit valid JSON.
- Docs: new per-feature doc `docs/App/personas.md` (cards, registry,
  tool shapes, how an agent adopts one); the `debate-mode` skill gained
  an "Optional: adopt a persona" section; the `agent-chat` skill + README
  + all three tester role docs (`claude.md` / `AGENTS.md` / `GEMINI.md`)
  picked up the two tools in their tool tables. README repo-layout tree
  + project-docs index gained the new doc (and the previously-missing
  `kickoff-prompts.md` row).

### Changed — `scripts/debate.ps1` casts from the shared registry
- `debate.ps1` no longer re-scans `agents/Debate-Agents/All/` or parses
  frontmatter titles itself. It now shells out to a new JSON CLI on the
  registry — `python src/orchestrator/personas.py {list,get} --group All` —
  for the roster (random pick stays in PowerShell) and for resolving
  `-Personalities`. The deleted `Get-PersonaName` PowerShell helper and the
  folder glob are gone; persona discovery, display names, and name matching
  now have exactly one implementation. **Bonus:** `-Personalities` accepts a
  slug **or** display name now (e.g. `crypto-chad` or `"Crypto Chad"`), not
  just an exact file name, via the registry's forgiving matcher. The
  per-agent prompt body is still read from the card file (path supplied by
  the registry), so the launched-prompt content is unchanged. Validated with
  `-DryRun`: forced-by-slug, forced-by-display-name, random 3-agent cast, and
  the not-found error path.

## 2026-06-16

### Added — One-command auto-debate launcher (`scripts/debate.ps1`)
- New `scripts/debate.ps1` runs the whole debate pipeline in one call:
  picks a random unused topic from `docs/Chat-Topics/Topics.md`, reads
  that topic's `- Debaters: N` line to choose the cast size
  (`2` → claude-code + gemini, `3` → + codex), draws N random personas
  from `agents/Debate-Agents/All/`, maps one per CLI, seeds via
  `scripts/start.ps1 --preset debate`, then **auto-launches one terminal
  per agent already prompted in character** (first speaker first).
- **Persona injection at launch.** Because `get_kickoff()` returns one
  shared template per conversation, each agent's persona is injected via
  a per-agent prompt file at `db/launch/conv<id>-<cli>.txt`; the CLI is
  handed a tiny "read this file and follow it" opener, so persona length
  or quoting can't break the command line. Windows are spawned via
  `pwsh -EncodedCommand` to sidestep quote mangling.
- **Topic check-off.** On a successful seed the chosen topic's line in
  `Topics.md` gets a ✅ marker appended
  (`… ✅ <!--used YYYY-MM-DD conv#N-->`); the parser skips ✅-marked
  topics on the next run and aborts cleanly when the list is exhausted.
- **Run history log.** Each real run appends a block to
  `logs/debate-history.log` recording the timestamp, conversation id,
  topic, and the persona→CLI cast — the one greppable place to see which
  personality each CLI played. (The message transcript itself stays in
  the DB — `inspect_conversations.py` / web UI / Export.)
- Flags: `-DryRun`, `-SkipPermissions` (appends each CLI's hands-off
  flag — `claude --dangerously-skip-permissions`, `gemini --yolo`,
  `codex --yolo`), `-Topic`, `-Agents`, `-Personalities`, `-MaxTurns`,
  `-DefaultAgents`, `-TopicsGlob`, `-ForceSidecar`.
- New guide: [`docs/Guides/auto-debate.md`](Guides/auto-debate.md).

### Changed — Chat-Topics library
- `docs/Chat-Topics/Topics.md` is now the active 100-topic library with a
  per-topic `- Debaters: N` annotation. The earlier `50-Topics-GPT` /
  `50-Topics-Grok` sets moved to `docs/Chat-Topics/Legacy/`. README
  repo-layout tree updated to match.

## 2026-05-15

### Added — Orchestrator entry points + "Next: launch each CLI" panel on fresh conversations
- **Homepage hero** gained a primary `Start a conversation →` CTA
  pointing at `/orchestrate` (sky-solid). The previous primary
  `Browse conversations` demoted to a secondary outline button next to
  it; `View source` stays as the tertiary outline.
- **Homepage nav** gained an `Orchestrate` link between `Resources`
  and `Conversations →`.
- **`/conversations` page** gained a primary `+ New conversation`
  button (`btn-primary`) on the right side of the page header, aligned
  with the title. New `.page-header-row` flex shell handles the
  layout and wraps gracefully on narrow viewports. Empty-state copy
  rewritten to point at `/orchestrate` first (`scripts/start.ps1`
  still mentioned as the legacy alternative).
- **Topbar nav** in `_layout()` (used by the conversations index and
  every transcript page) gained an `Orchestrate` link between
  `Conversations` and `Home`.
- **"Next: launch each CLI" panel** on the conversation transcript
  page — only renders when `status='active'` AND the messages list is
  empty (i.e. the orchestrator just seeded the row and the operator
  hasn't launched any CLI yet). Shows one row per participant with
  the agent's id in monospace, a sky-blue `FIRST TURN` pill on the
  `current_turn` agent, and a `Copy prompt` button that puts the
  rendered two-line kickoff prompt (with the agent's id substituted)
  into the clipboard via `navigator.clipboard.writeText`. Button
  flashes `Copied!` for 1.5s as confirmation. Panel self-removes via
  the existing SSE `event: message` handler the moment the first
  reply lands. When the conversation was seeded **without** a preset
  (no rendered kickoff template), each row shows a muted "no template
  — see start-new-chat.md" hint instead of a copy button, pointing the
  operator at the legacy paste-the-prompt flow.
- **`.next-steps` CSS** — sky-tinted panel
  (`rgba(56,189,248,0.04)` background, 25%-alpha sky border) so it
  reads as a guide rather than an alert. Scoped under the panel id so
  no leakage into other pages.
- **JS additions** to the `_render_conversation` IIFE: copy-button
  wiring + `nextSteps.remove()` on first SSE message. Both share the
  existing `nextSteps` reference fetched alongside `transcript`,
  `live`, `stopBtn`.
- **Smoke-tested** via Starlette `TestClient`: fresh debate-preset
  conversation seeded through `POST /api/orchestrate` renders the
  panel with three participant rows + first-turn badge on
  `claude-code` + three `Copy prompt` buttons + `get_kickoff()` in
  `data-prompt`; after inserting a message into the DB, the
  re-rendered page no longer includes the panel.

### Added — Orchestrator Phase 2a: `/orchestrate` form + per-CLI preflight + DB row creation
- New top-level surface at **`GET /orchestrate`** — a form to seed a
  conversation with strict preflight gating. Closes the long-standing
  "Web UI: seed-new-conversation form" Open row and lands the
  preflight half of the ultimate-goal orchestrator. Phase 2b (next
  PR) will add the personality bundle picker + CLI spawning via a
  PowerShell wrapper.
- **New `src/orchestrator/` package** (3 files):
  - `seeding.py` — `seed_conversation(...)` extracted from
    `start_conversation.py:main()`. Pure function (no argparse, no
    stdout), takes structured kwargs, returns a `SeedResult` dataclass.
    Reuses `SCHEMA` + `_MIGRATIONS` constants (kept in sync with the
    MCP server + web_ui). Raises `SeedError` on validation failure
    (caller renders the message).
  - `preflight.py` — `PreflightResult` + `PreflightFailure` dataclasses
    + per-CLI checkers (`check_claude_code`, `check_codex`,
    `check_gemini`) + `run_preflight(clis)` dispatcher +
    `format_preflight_log(results)` for the audit log. Pure
    file-system checks (no subprocess) — config file exists, parses
    (JSON for claude-code/gemini, TOML for codex), has `agent_chat`
    entry, `command` resolves (PATH lookup or file exists), launcher
    script referenced in `args` exists on disk. Surfaces extracted
    `command` + `launcher_path` even on partial failure so the
    operator sees what *was* found alongside what failed.
  - `__init__.py` — package marker + Phase 2a/2b note for the next
    contributor.
- **`src/start_conversation.py` refactored** to a thin argparse wrapper
  around `seeding.seed_conversation()`. CLI behaviour unchanged: same
  flags, same stdout messages, same exit codes (0 on success, 2 on
  validation error). All the seeding SQL + template-rendering logic
  now lives in one place.
- **`src/web_ui.py` additions**:
  - `GET /orchestrate` handler — runs page-load preflight on all three
    supported CLIs, renders the form with **per-CLI status badges**
    (green "ready" or red "<failure-code>") next to each checkbox.
  - `POST /api/orchestrate` handler — accepts JSON body
    `{topic, participants, preset, max_turns, first, kickoff}`,
    validates (topic required, min 2 participants, preset must be
    known, max_turns 1-50), runs preflight on the **selected** CLIs,
    aborts with 409 + `{ok: false, kind: "preflight_failed",
    preflight: [...], log_path: "..."}` on any failure (writing a
    full report to `<repo>/logs/orchestrator-<timestamp>.log`),
    otherwise calls `seeding.seed_conversation()` and returns
    `{ok: true, conversation_id: N}`.
  - `_render_orchestrate(initial_preflight)` HTML render with embedded
    JS that handles preset-driven max_turns auto-fill, dynamic
    first-speaker dropdown population from checked participants, JSON
    POST submit, inline error-panel rendering, and redirect to
    `/conversations/<id>` on success.
  - `ORCHESTRATE_CSS` — scoped under `.orch-shell`, reuses BASE_CSS
    design tokens (`--accent` sky-400, `--bad` red-500, `--good`
    sky-500, monospace family JetBrains Mono for CLI ids). No layout
    leakage into other pages.
  - Topbar nav gained an "Orchestrate" link in `_layout()` between
    "Conversations" and "Home".
- **Validation/error shape** designed for both the form's inline
  re-render and the audit log: each failure is `{code, detail}` with
  `code` from a small enum (`config_missing`, `config_parse_error`,
  `no_mcp_entry`, `missing_command`, `command_not_found`,
  `missing_args`, `launcher_not_extractable`, `launcher_missing`,
  `unknown_cli`). UI surfaces the `code` as a monospace chip in front
  of the human-readable `detail`; the log file format is
  `FAIL <cli> [<code>] <detail>` so a `grep FAIL logs/orchestrator-*`
  one-liner gives you the punch list.
- **Smoke-tested** end-to-end via Starlette `TestClient`: form renders
  with three "ready" badges against the actual machine config; six
  validation paths return 400 (missing topic, 1 participant, unknown
  preset, bad max_turns, etc.); preflight failure with a bogus CLI id
  returns 409 with the right shape and writes a log; happy-path POST
  creates the conversation row with debate preset + max_turns=2 +
  rendered kickoff template (1372 chars).
- **Not in Phase 2a** (Phase 2b): personality bundle picker from
  `agents/Debate-Agents/`, PowerShell wrapper that spawns each CLI in
  its own terminal with the chosen personality, automatic Web UI
  open. The current flow stops at "row seeded, redirect to
  `/conversations/<id>`" — operator still launches CLIs manually for
  now, but with preflight already confirmed.

### Added — `debate-mode` skill — layered on top of `agent-chat`
- New `skills/debate-mode/SKILL.md` ships a second Agent Skill that
  composes on top of the base `agent-chat` participation skill. Where
  `agent-chat` covers the loop mechanics (when to call `get_kickoff`,
  `wait_for_turn`, `send_message`), `debate-mode` shapes the *content*
  of each reply: argue a position, cite the other side specifically,
  avoid hedging filler.
- **Three core teachings**, drawn from analysing the
  `future-of-tech-jobs` (Conversation #3)
  reference debate:
  1. Argue a position — don't survey the question. Commit to a
     falsifiable claim; concrete predictions beat abstractions.
  2. Cite the other side specifically — quote or paraphrase the actual
     argument, engage the strongest version, no strawmen.
  3. Concede partial points where warranted, hold ground where you can
     — full concession when the opponent's point genuinely defeats
     yours; partial concession plus counter when they're directionally
     right; direct counter when you actually disagree.
- **Anti-patterns table** in the SKILL.md calls out the specific
  hedging phrases to avoid ("that's a great point", "valid arguments
  on both sides", "it really depends on how we define X", restating
  your previous position with more words).
- **Phrases that signal good debate** — concrete openings lifted from
  the reference conversation that the agent can pattern-match on
  ("Your strongest point is…", "I buy A, but I think you understate
  B", "Concrete bet I'll stake on the table…", "A piece neither of us
  has named…").
- **When to signal `done`** — guidance on the three natural ending
  states (mutual convergence, decisive concession, argument has
  cycled) and what to do in each. Specifically calls out the cycle
  failure mode and three escape tactics before defaulting to `done`.
- **Composes with `agent-chat`** — frontmatter `description` triggers
  on debate-specific phrases ("argue for X", "defend the position",
  "kickoff preset: debate"), independent of the base skill's triggers,
  so both fire when appropriate without conflict. Table in SKILL.md
  maps "where each concern lives" between the two skills.
- **Companion `README.md`** covers per-skill install (same per-CLI
  paths as the base skill — substitute `debate-mode` for
  `agent-chat`), a **one-symlink-per-machine recipe that covers both
  skills in one shot** (symlink `~/.claude/skills` and
  `~/.agents/skills` directly to this repo's `skills/` folder), and
  verification (seed a `--preset debate` conversation with a
  `--max-turns 4` cap and watch for hedging filler in the transcript).
- **Documentation-only change** — pure markdown; no new Python deps,
  no schema changes, no MCP-tool changes.

### Added — `agent-chat` Agent Skill (single SKILL.md across all three CLIs)
- New `skills/agent-chat/SKILL.md` ships a **role-agnostic** participation
  skill consumed natively by Claude Code, Codex, and Gemini. All three
  CLIs support the open [Agent Skills](https://developers.openai.com/codex/skills)
  standard with the same YAML-frontmatter `SKILL.md` format and the same
  lazy-load model — one canonical file, three CLIs.
- **What the skill teaches:** drive the `get_kickoff()` → `wait_for_turn`
  → `send_message` loop autonomously. Explicit rules on signal usage,
  turn-taking, and the "don't ask the operator between turns"
  expectation. Frontmatter `description` triggers on phrases like "join
  the agent_chat conversation", "call `get_kickoff`", or being spawned
  by the orchestrator.
- **Per-CLI discovery paths** (covered in
  `skills/agent-chat/README.md`):
  - Claude Code: `.claude/skills/agent-chat/` (project) or
    `~/.claude/skills/agent-chat/` (user).
  - Codex: `$CWD/.agents/skills/agent-chat/` (project, walks up to repo
    root) or `~/.agents/skills/agent-chat/` (user).
  - Gemini: `.gemini/skills/` or `.agents/skills/` (project) plus the
    same paths under `~/`. **`.agents/skills/` is recognised by both
    Codex and Gemini**, so a single symlink at
    `~/.agents/skills/agent-chat/` covers both CLIs.
- **README.md** in the same folder covers per-CLI install (copy or
  symlink the canonical `SKILL.md` into each CLI's discovery path),
  verification (a 2-turn smoke conversation that should run autonomously
  from a one-line "join the conversation" prompt), and a
  one-symlink-per-machine recipe that covers all three discovery roots.
- **Why it matters:** removes the "paste a 30-line kickoff prompt into
  every CLI" step. After installing once per CLI, the operator (or the
  future one-click orchestrator) only has to say "join the agent_chat
  conversation" and each agent runs the loop on its own until the
  conversation completes. Building block for the **debate-mode skill**
  and the **ultimate-goal orchestrator** rows on the roadmap.
- **No code changes** — pure documentation + skill content. No new
  Python deps, no schema changes, no MCP-tool changes. The skill is
  markdown consumed by each CLI's native Agent Skills loader.
- **Tester role docs left alone** as agreed. The files under
  `agents/CLIs/*/{claude.md,CLAUDE.md,AGENTS.md,GEMINI.md}` continue
  to carry their tester-specific sections ("What to test for",
  "Reporting") on top of the same participation loop; the skill is
  canonical for the loop content and the tester docs should reference
  it if they grow out of sync.

### Changed — README repo-layout tree, project docs index, roadmap section
- Added `skills/` directory to the repository-layout tree (between
  `prompts/` and `agents/`), showing just `SKILL.md` + `README.md`.
- Added a `skills/agent-chat/` row to the Project docs table next to
  `prompts/kickoff.md`.
- Rewrote the Roadmap highlights: skill rows dropped (shipped),
  surfaced the debate-mode skill + ultimate-goal orchestrator as the
  next two short-term items.

## 2026-05-12

### Added — Code-block syntax highlighting on the conversation transcript
- Wired up [highlight.js v11.10.0](https://highlightjs.org/) (client-side,
  CDN-hosted) on the conversation detail page. The Markdown renderer
  already emits `<pre><code class="language-X">` for fenced blocks, so
  highlight.js uses the language hints directly and auto-detects when
  the hint is missing.
- **Scoped** to the conversation detail page only — the homepage and the
  conversations list don't load the library. Added an optional
  `head_extras=""` parameter to `_layout()` (backward-compatible
  default) and passed `HIGHLIGHT_JS_HEAD` only from
  `_render_conversation()`.
- **Theme:** `github-dark` from highlight.js's bundled stylesheets.
  Matches the BASE_CSS dark palette closely; one small CSS override
  (`.msg-body pre code.hljs { background: transparent; padding: 0 }`)
  lets the surrounding `<pre>` box style win so highlight.js doesn't
  fight the existing message-body chrome.
- **SSE compatibility:** the existing live-append path
  (`tmp.innerHTML = renderMsg(m); transcript.appendChild(...)`) now
  also runs `node.querySelectorAll('pre code').forEach(el =>
  hljs.highlightElement(el))` on the newly-inserted node, so messages
  arriving over the wire mid-conversation get the same treatment as
  the initial server-rendered batch. Initial-load highlighting fires
  via `document.querySelectorAll('#transcript pre code')` inside the
  existing IIFE.
- **No new Python deps.** Single CDN bundle (highlight.min.js +
  github-dark.min.css). Skipped Pygments / server-side rendering
  because the brief unstyled-code-flash on first paint is acceptable
  for a personal app and the integration touches one constant + one
  layout-param + a few JS lines instead of a new dependency.
- **Smoke-tested** end-to-end on a synthetic conversation with both
  ` ```python ` and ` ```javascript ` fences: confirmed the CDN refs
  land in `<head>`, the language classes survive through Markdown
  rendering, the initial-load + per-SSE-message highlight calls are
  both present, and the conversations list page does NOT carry the
  highlight.js refs (scoping verified).
- Closes the **High** Roadmap row "Web UI: code block syntax
  highlighting".

### Added — Server-delivered kickoff + named presets
- **New MCP tool: `get_kickoff()`** in `src/agent_chat_mcp.py`. No
  parameters; reads `AGENT_ID` from server config. Returns the rendered
  kickoff template stored on the latest conversation row this agent
  participates in, plus topic + preset + conversation_id. Three response
  shapes: `status="ok"` (rendered template found), `status="fallback"`
  (row exists but `kickoff_template` is NULL — pre-existing rows or
  conversations seeded without `--preset`/`--tone`), and
  `status="no_conversation"`. Annotations mirror `get_my_turn`
  (`readOnlyHint=True`, `idempotentHint=True`). The fallback string
  references `prompts/kickoff.md` so the old paste-the-prompt flow keeps
  working on legacy rows.
- **New module: `src/presets.py`** exposes a `PRESETS` dict mapping
  preset name → `{tone, mode, max_turns}` for four built-ins:
  `debate` (turns/8), `code-review` (turns/6), `brainstorm`
  (continuous/10), `plan` (turns/8). Tone strings are copied verbatim
  from `prompts/kickoff.md`'s `{{TONE_INSTRUCTION}}` examples — keep
  the two in sync. `get_preset(name)` raises `KeyError` with the valid
  list on unknown names.
- **`start_conversation.py` gains three flags**:
  `--preset {debate,code-review,brainstorm,plan}` (looks up the preset
  and uses its mode + max_turns as defaults), `--tone "<sentence>"`
  (overrides the preset's tone, or supplies a tone without a preset),
  `--kickoff-template-file <path>` (override the default
  `prompts/kickoff.md` source). Precedence for mode/max_turns:
  explicit flag > preset default > script default. When any of these
  three flags are set, the seeder renders the template (substitutes
  `{{TOPIC}}` + `{{TONE_INSTRUCTION}}`, applies a "with another AI
  agent" → "with N other AI agents" rewrite for 3+ participant
  conversations) and stores the body on the row's new
  `kickoff_template` column. Without any of those flags, the column
  stays NULL and the old workflow is preserved end-to-end. The printed
  end-of-script message now shows the new two-line prompt when a
  template was rendered, or points at `start-new-chat.md` §3 otherwise.
- **Schema additions** (idempotent migration in `db_init()` across both
  server modules + an inline migration block in
  `start_conversation.main()`): `conversations.preset TEXT`,
  `conversations.kickoff_template TEXT`. Both nullable so pre-existing
  rows migrate cleanly. `_MIGRATIONS` constant in `agent_chat_mcp.py`,
  `web_ui.py`, and `start_conversation.py`; mirrored sync column lists
  in `web_ui.py._CONV_COLUMNS` + `scripts/db_sync.py.CONV_COLUMNS` so
  the new fields round-trip through the bidirectional-sync sidecar.
- **Template loader.** `_load_template(path)` supports two source
  shapes: Markdown with a `` ```text `` fenced block (extracts the
  first block's body) or plain text (whole file, stripped). Default
  source is `prompts/kickoff.md`. Custom templates via
  `--kickoff-template-file`.
- **Docs:** rewrote `prompts/kickoff.md` to lead with the
  `--preset`/`get_kickoff()` flow and demote the paste-the-prompt
  workflow to a "Legacy" section (still documented in full as a
  fallback). Updated the three tester role docs
  (`agents/CLIs/claude-code_agent1/claude.md`,
  `agents/CLIs/codex_agent1/AGENTS.md`,
  `agents/CLIs/gemini_agent1/GEMINI.md`) so step 1 of every "How to
  participate" section is now "call `get_kickoff()` once"; the tools
  table grew a row for `get_kickoff()` in each. New per-feature doc
  `docs/App/kickoff-prompts.md` (architecture diagram, CLI flag
  reference, preset table, rendering pipeline, response shapes,
  custom-template authoring, schema sync surface, backward-compat
  story, "where to look for what" table).
- **Backward compatible** all the way down: existing rows migrate with
  NULL in both new columns; agents that don't call `get_kickoff()`
  keep working unchanged; seeding without the new flags preserves the
  old behavior end-to-end.
- **Smoke-tested** via a 6-case in-process script: (1) `PRESETS` shape
  + tone trailing punctuation, (2) renderer on 2-/3-/4-agent topics
  (placeholders substituted, "N other AI agents" rewrite fires only
  for N>=3), (3) migration of a legacy-schema DB (columns added,
  legacy row preserved with NULLs, idempotent re-run is a no-op),
  (4) end-to-end seed + `get_kickoff()` returning `status="ok"` with
  rendered debate-preset body, (5) legacy row returning
  `status="fallback"`, (6) empty DB returning `status="no_conversation"`.
- Closes the **High** Roadmap row "Server-delivered kickoff + presets".
  Unblocks the still-open "Web UI: seed-new-conversation form" row
  (which can now expose the preset dropdown directly).

### Added — `scripts/run-mcp-server.{ps1,sh}` launcher for portable MCP configs
- **New `scripts/run-mcp-server.ps1`** (Windows). Param: positional
  `--agent-id`. Resolves `<repo>/.venv/Scripts/python.exe` and
  `<repo>/src/agent_chat_mcp.py` from `$PSScriptRoot/..`. Validates both
  paths exist with helpful error messages. Forwards extra args to the
  Python child via splatting (`@forwarded`). Exits with `$LASTEXITCODE`.
  Same pattern `scripts/start.ps1` already uses for the sidecar — proven
  precedent in this repo.
- **New `scripts/run-mcp-server.sh`** (POSIX sibling). Bash, `set -euo
  pipefail`, resolves `.venv/bin/python` + `src/agent_chat_mcp.py` via
  `$BASH_SOURCE` (handles symlinks). Execs Python directly so the MCP
  loader's signals reach the server unmediated. +x bit set in the git
  index (`git update-index --chmod=+x`).
- **New `.gitattributes`** with one line: `*.sh text eol=lf`. Required
  for cross-platform safety — Windows's default `core.autocrlf` would
  otherwise convert the shebang's LF to CRLF and POSIX bash would fail
  with `bad interpreter: no such file or directory`.
- **MCP config impact:** the venv interpreter and the server script path
  drop out of every CLI registration. Each config now references just
  the launcher path. Cloning to a different drive = edit **one** string
  per config instead of two.
  ```json
  // before
  "command": "<repo>/.venv/Scripts/python.exe",
  "args": ["<repo>/src/agent_chat_mcp.py", "--agent-id", "claude-code"]
  // after
  "command": "pwsh",
  "args": ["-NoProfile", "-File",
           "<repo>/scripts/run-mcp-server.ps1", "claude-code"]
  ```
- **Trade-off:** the new form requires `pwsh` (PowerShell 7+) on PATH.
  Mike's primary OS is Windows + the root CLAUDE.md already standardises
  on `pwsh`, so this is consistent with the rest of the project. For
  POSIX clones (or operators without pwsh), swap to the `.sh` launcher
  directly — `"command": "/abs/path/to/scripts/run-mcp-server.sh",
  "args": ["claude-code"]`. The `.sh` is +x out of the box.
- **`--db-path` still optional** (today's earlier work) — the launcher
  forwards extra args verbatim, so `pwsh -NoProfile -File <launcher>
  codex --db-path D:/custom/chat.db` works for explicit overrides.
- **Doc sweep:** updated config snippets in `README.md` (Claude Code /
  Codex / Gemini blocks + a [!NOTE] explaining the pwsh-on-PATH
  requirement and the `.sh` alternative), `docs/CLI-MCP-Config/{claude,
  codex,gemini}.md` (registration block + the manual stderr-debug
  command in `codex.md`), and `docs/Setup/INITIAL_SETUP.md` (both
  registration blocks under §3). Stale macOS/Linux notes about
  swapping `.venv/Scripts/python.exe` for `.venv/bin/python` removed —
  the launcher handles that internally.
- **Adjacent doc-accuracy fixes** caught in the same pass:
  - `docs/App/fly-deploy.md` "What's already in the repo" bullet — the
    `web_ui.py` `--db-path` resolution now has a computed
    `<repo>/db/chat.db` fallback (today's morning work) on top of
    `$AGENT_CHAT_DB`. Reworded.
  - `docs/App/db-sync.md` "Hosted site is missing rows" troubleshooting
    step — the old wording said "compare `--db-path` here against the
    path baked into the `agent_chat` server entries." With the launcher
    + the new defaults, there is no path baked into MCP configs at all.
    Reworded to direct the operator at `$AGENT_CHAT_DB` and any explicit
    `--db-path` overrides instead.
- **Smoke-tested:** `pwsh -NoProfile -File scripts\run-mcp-server.ps1
  test-launcher --help` prints the server's argparse help (proving the
  launcher resolves the venv + server script, and that extra-arg
  forwarding works). Positional form `... run-mcp-server.ps1 codex
  --help` also tested — that's the shape MCP loaders use.
- **Backward compatible:** existing MCP configs that still invoke the
  venv Python directly keep working — nothing was removed from
  `agent_chat_mcp.py`. The launcher is an additive operator-flow
  convenience.
- Closes Roadmap row "Make venv interpreter path portable" and narrows
  the still-open "Repo-path duplication across configs and docs" to
  just the launcher path itself.

### Changed — `--db-path` default extended to operator scripts + web UI
- Followed up the MCP-server change (below) with the same flag → env →
  computed-default precedence in the three remaining entry points so
  every script in the project behaves identically. `--db-path` is now
  optional everywhere; configs and operator commands collapse to the
  minimum signal.
- **`src/start_conversation.py`**: `--db-path required=True` → optional,
  new `_default_db_path()` helper, resolution in `main()` after
  `parse_args()`. Module docstring rewritten with the new minimal
  invocation. The seeder's existing `makedirs` of the parent dir keeps
  fresh-clone-with-no-db-yet Just Working.
- **`src/inspect_conversations.py`**: same pattern. `db-not-found`
  error preserved (`list` / `show` / `tail` / `stop` need a real DB),
  it now references the resolved default path. Docstring rewritten.
- **`src/web_ui.py`**: already honoured `$AGENT_CHAT_DB`; added the
  computed `<repo>/db/chat.db` fallback (new `_default_db_path()`
  helper mirrored from the other scripts) and dropped the
  `parser.error("--db-path is required...")` branch. Docstring + the
  config-table row in `docs/App/web-ui.md` updated.
- **No `scripts/start.ps1` code change** — it just forwards args to
  `start_conversation.py`. Only the synopsis-comment example was
  updated.
- **Doc sweep** — operator examples that passed `--db-path db\chat.db`
  now drop the flag, with a one-liner pointer to the new default each
  place an example appears: `README.md` (quick-start, daily-driver
  single-line form, inspection block), `docs/Guides/start-new-chat.md`
  (stale-conversation check, multi+single-line start.ps1 examples,
  while-it's-running inspect commands, three-agent variation),
  `docs/Setup/INITIAL_SETUP.md` (the two registration blocks under
  §3 + smoke-test commands under §5), `docs/CLI-MCP-Config/{claude,
  codex,gemini}.md` (the "Run a 3-agent conversation" recipe in each),
  `docs/App/web-ui.md` (config table + bind example),
  `prompts/kickoff.md` (seed snippet at the top).
- **Backward compatible** — every script still accepts `--db-path
  <path>`; the flag takes precedence over the env var and the computed
  default. Old scripts and pasted commands keep working unchanged.
- **Scope intentionally limited** to operator-facing entry points.
  `scripts/db_sync.py` (the sidecar) already has its own
  `$AGENT_CHAT_DB`-or-`db/chat.db` defaulting and was not touched —
  see `docs/App/db-sync.md` "Flag table" for its behaviour.
- Validated locally via a 4-case smoke script per entry point: import
  cleanly, default branch resolves to `<repo>/db/chat.db`, env branch
  honours `$AGENT_CHAT_DB`, flag still wins when both are set.

### Changed — `--db-path` is no longer required on `agent_chat_mcp.py`
- `src/agent_chat_mcp.py` `parse_args()` now treats `--db-path` as
  optional. Resolution precedence in `main()`:
  1. `--db-path <path>` flag (explicit override, still wins)
  2. `$AGENT_CHAT_DB` environment variable
  3. Computed default: `<repo>/db/chat.db`, resolved from the script's
     own location (`Path(__file__).resolve().parent.parent / "db" /
     "chat.db"`). A fresh clone Just Works with no flag and no env var.
- New helper `_default_db_path()` centralises the env-var-and-default
  logic; `db_init()` continues to `makedirs` the parent on first run
  so the path resolves even before `db/` exists.
- Module docstring rewritten to show the new minimal invocation
  (`python agent_chat_mcp.py --agent-id claude-code`) and the two
  override paths.
- **MCP config impact:** the `--db-path` arg (and its hardcoded DB
  path) can be dropped from every CLI registration. Old configs that
  still pass `--db-path` keep working — the flag takes precedence over
  both the env var and the computed default, so this is purely
  additive. Updated config snippets in `README.md` (Claude Code /
  Codex / Gemini blocks) and `docs/CLI-MCP-Config/{claude,codex,gemini}.md`,
  plus the manual stderr-debug invocation in `docs/CLI-MCP-Config/codex.md`.
- Scope intentionally limited to the MCP server — `start_conversation.py`,
  `inspect_conversations.py`, and `web_ui.py` still require `--db-path`
  (web_ui already honours `$AGENT_CHAT_DB` as a fallback). Extending
  the same default-resolution to the operator-facing scripts is a
  follow-up if the duplication starts to bite.
- Closes Roadmap row "`--db-path` default-from-env".

## 2026-05-11

### Changed — Basic-auth gate temporarily disabled; site is now fully public
- `_build_middleware()` in `src/web_ui.py` now returns `[]`
  unconditionally — the `AGENT_CHAT_BASIC_AUTH_PASSWORD` env var is
  ignored and `BasicAuthMiddleware` is no longer attached. All browser
  pages + JSON API routes on `agent-chat.mikesailab.com` are public.
- `BasicAuthMiddleware` class is left intact so the gate can be
  re-enabled by restoring the env-var check in `_build_middleware()`.
- Startup banner now prints `basic auth: off (gate disabled)` and
  no longer reads `AGENT_CHAT_BASIC_AUTH_PASSWORD`.
- `/api/ingest` and `/api/since` (bearer-token realm) are unchanged —
  still gated by `AGENT_CHAT_INGEST_TOKEN` inside the route handlers.
- Apex landing page (`michaelschecht.github.io`) Agent Chat tile
  flipped from amber **Auth Required** → emerald **Live**.
- Docs updated to reflect the disabled state: `README.md`,
  `docs/App/web-ui.md`, `docs/App/fly-deploy.md`.

## 2026-05-06

### Added — Bidirectional DB sync + hosted-UI delete-conversation button
- **The architectural call:** conversations sync **both ways**;
  messages stay **local-only-origin**. Agents only run locally so
  messages never originate on the hosted side; SQLite's
  `INTEGER PRIMARY KEY AUTOINCREMENT` would collide if the hosted side
  ever inserted. Bidirectional sync covers conversation-row mutations
  (status, topic, end_reason, deletion) — sufficient for force-stop,
  delete, future edit-topic, and even a future hosted seed-conversation
  form (creates a row; agents fill in messages locally afterward).
- **New endpoint: `GET /api/since`** in `src/web_ui.py`.
  - Auth: `Authorization: Bearer <token>` matched against
    `$AGENT_CHAT_INGEST_TOKEN` (same realm as `/api/ingest` — one
    less rotation surface for now; can split later if the threat model
    needs read/write separation).
  - Query params: `conversations_updated_after` (ISO timestamp;
    required) + `known_ids` (CSV of int ids; optional, used to compute
    deletions via set-difference).
  - Returns `{conversations, deleted_conversation_ids, server_time}`.
    Messages are intentionally not included.
  - `BasicAuthMiddleware` short-circuits on `/api/since` so the
    bearer-token check is reachable (matches the existing pattern for
    `/api/ingest` and `/favicon.svg`).
  - When `AGENT_CHAT_INGEST_TOKEN` is unset → `404 sync disabled`,
    same opt-in posture as `/api/ingest`.
- **New endpoint: `POST /api/conversations/{cid}/delete`.**
  - Permanently deletes the conversation + cascades messages in one
    transaction.
  - Idempotent — second delete on the same id returns 404.
  - The local sidecar picks up the deletion on the next pull tick (~5s)
    and applies it locally, so the two sides converge.
- **New helpers in `src/web_ui.py`:** `delete_conversation(cid)` and
  `since_payload(updated_after, known_ids)`. Both use the existing
  `_CONV_COLUMNS` tuple so they stay in lockstep with the schema and
  the ingest path.
- **Hosted UI: × delete button per row on `/conversations`.** Small
  emerald-on-hover icon button with a `confirm()` that names the
  topic + message count + warns the local sidecar will pick up the
  deletion. On success, the row is removed from the table without a
  full reload. CSS for the icon-button variant + `.row-actions` cell
  added inline (kept on the index page; the rest of the app's
  `BASE_CSS` doesn't need it).
- **Sidecar (`scripts/db_sync.py`) becomes bidirectional.**
  - State file gains `pulled_updated_at` (defaults to epoch on first
    load — old state files written by the push-only version are
    backward-compatible; the first tick after upgrade does one big
    pull, paid once).
  - New `get_since(...)`, `apply_pull(...)`, and `PullNotSupported`
    exception. `apply_pull` does `INSERT OR REPLACE` for conversations
    + cascade `DELETE` for removals in one transaction (mirrors the
    server's `ingest_payload`).
  - `run_tick()` reordered to **pull → push**. Pull-first prevents a
    hosted-side delete from racing with a local re-upsert.
  - After a successful pull, `conversations_updated_after` (the push
    watermark) is bumped to `max(it, server_time)` so just-pulled rows
    are excluded from the next push delta query — avoids ping-pong.
  - `pulled_updated_at` is advanced to the response's `server_time`
    each tick (avoids local-vs-Fly clock-skew bugs).
  - **Mixed-version handling:** a 404 from `/api/since` raises
    `PullNotSupported`, the sidecar logs a warning, **skips the pull
    step**, and still runs push. So a new sidecar can talk to an old
    server without erroring out — the user just doesn't get
    hosted-→-local propagation until the next deploy. The reverse
    direction (old sidecar, new server) just keeps doing push-only;
    `/api/since` goes unused.
- **Conflict model:** **last-write-wins by `updated_at`** for
  conversations. Both sides bump `updated_at` on mutation; whichever
  side bumped most recently wins via `INSERT OR REPLACE` semantics on
  the receiver. Deletes are authoritative from either side.
- **Smoke-tested** in-process via Starlette's `TestClient` against
  hosted + local temp DBs. Coverage:
  - `/api/since` auth (401 missing/wrong bearer), param validation
    (400 missing watermark), happy path (returns 2 conversations, no
    `messages` key), set-difference deletion computation
    (`known_ids=[1,2,99,100]` with only 1,2 in DB → `[99, 100]`).
  - `/api/conversations/{cid}/delete`: 404 missing, success returns
    `{"deleted": True, "cascaded_messages": 2}`, idempotent re-delete
    returns 404, only the targeted row is removed.
  - `/conversations` page renders the × button + click-handler JS
    with the right fetch URL.
  - **Sidecar round-trip simulation:** local DB starts empty; tick 1
    pulls a hosted-created conversation and applies it locally; tick
    2 is a clean no-op (watermarks correctly advanced — no ping-pong);
    tick 3 propagates a hosted-side delete down to local. Watermark
    invariants verified after each tick.
  - **`PullNotSupported` path:** simulated `404` from `/api/since`
    does not crash; tick still returns a state.
- **Docs updated:**
  - `docs/App/db-sync.md` rewritten — new architecture diagram with
    pull arrow, conflict-resolution + asymmetry sections, mixed-version
    handling, `pull-then-push` tick order, watermark table.
  - `docs/App/web-ui.md` route map adds `/api/since` + delete endpoint.
  - `README.md` Web UI route table + Public-mirror section updated.
- **Roadmap:** closes the **"DB sync: bidirectional (Fly → local)"**
  Open row. The **"Web UI: editable topic + delete-conversation
  button"** Open row narrowed to edit-topic-only (delete shipped).

### Changed — Folder reorganization under `docs/` and `agents/`
- **`docs/` reshape.** Top-level docs moved into themed subfolders:
  `docs/App/` (`web-ui.md`, `db-sync.md`, `fly-deploy.md`),
  `docs/Setup/` (`INITIAL_SETUP.md`),
  `docs/Guides/` (`start-new-chat.md`).
  `docs/clis/` was renamed `docs/CLI-MCP-Config/` and gained two new
  files alongside the existing `gemini.md`: `claude.md` and `codex.md`
  (closes the Open "Backfill `docs/clis/claude-code.md` +
  `docs/clis/codex.md`" Roadmap row at the new path).
  `docs/agent-conversations/` capitalized to `docs/Agent-Conversations/`.
  New `docs/Chat-Topics/` houses curated topic-prompt libraries
  (`50-Topics-GPT_4-25-26.md`, `50-Topics-Grok_4-25-26.md`).
  `CHANGELOG.md` and `Roadmap.md` stay at `docs/` top level.
- **`agents/` reshape.** Per-CLI tester workspaces nested under
  `agents/CLIs/`: `agents/CLIs/claude-code_agent1/`,
  `agents/CLIs/codex_agent1/`, `agents/CLIs/gemini_agent1/`. New
  `agents/Debate-Agents/` houses personality bundles for debate-mode
  runs (`All/`, `Group1/`, `Group2/`, `Group3/`, `Hosts/`).
- **Cross-references swept across the repo** to match the new paths
  rather than 404. Updated:
  - `README.md`: repo-layout tree, project-docs index, archived-debates
    table, all in-text doc links, the Web UI section pointer.
  - `CLAUDE.md`: repo-layout tree + closing reminder to also update
    README + the `mikesailab` project memory + relative-`../` paths
    inside moved files when reshaping further.
  - `src/web_ui.py`: the homepage's outbound GitHub blob URLs (visible
    on the live site at `agent-chat.mikesailab.com`) — `docs/start-new-
    chat.md` → `docs/Guides/start-new-chat.md`, `docs/db-sync.md` →
    `docs/App/db-sync.md`, `docs/agent-conversations/...` →
    `docs/Agent-Conversations/...`.
  - `docs/Guides/start-new-chat.md`: relative paths shifted by one
    level — `INITIAL_SETUP.md` → `../Setup/INITIAL_SETUP.md`,
    `db-sync.md` → `../App/db-sync.md`, `clis/gemini.md` →
    `../CLI-MCP-Config/gemini.md`, `prompts/kickoff.md` →
    `../../prompts/kickoff.md`. The per-CLI bullet now points at all
    three CLI-MCP-Config docs (was just gemini).
  - `docs/App/web-ui.md`: `../src/` → `../../src/`, `../scripts/` →
    `../../scripts/`. The "where the homepage links go" table prose
    updated to the new doc paths.
  - `docs/App/fly-deploy.md`: in-text reference updated.
  - `docs/CLI-MCP-Config/{claude,codex,gemini}.md`,
    `docs/Setup/INITIAL_SETUP.md`, `agents/CLIs/gemini_agent1/GEMINI.md`,
    `docs/App/db-sync.md`: `agents/<x>_agent1/` paths in prose updated
    to `agents/CLIs/<x>_agent1/`.
  - `fly.toml`, `scripts/db_sync.py`, `scripts/start.ps1` comments
    referencing `docs/db-sync.md` / `docs/fly-deploy.md` updated to
    `docs/App/...`.
  - Memory: `project_mikesailab_design_system.md` updated so its
    pointer at `docs/web-ui.md` now reads `docs/App/web-ui.md`.
- Historical entries in `CHANGELOG.md` and `Roadmap.md` are
  intentionally **not** rewritten (they reference paths that were
  correct at the time of writing — that's what archives are for).
  Future entries should use the new paths.
- Smoke-tested in-process via Starlette's `TestClient`: homepage
  renders with the new GitHub blob URLs (`docs/Guides/start-new-chat.md`,
  `docs/App/db-sync.md`, `docs/Agent-Conversations/...`) and contains
  zero stale-path leaks.

### Added — Public landing page at `GET /` + `docs/web-ui.md`
- New homepage at `agent-chat.mikesailab.com/` (formerly the conversations
  table). Self-contained HTML rendered by `_render_homepage(stats, latest)`
  in `src/web_ui.py`. Sections: topbar (brand + live-pill + nav + CTA),
  asymmetric hero (oversized two-row title, lede, dual CTAs, stats panel
  pulling from `list_stats()`), three "what" cards, five numbered "how"
  steps with real code, latest-5 conversations list, six-group resources
  grid (this project / prompt library — including the
  [Agents page](https://prompts.mikesailab.com/?library=public&section=agents)
  / archived debates / stack / CLIs / author), monospaced footer.
- **Aesthetic:** "console-arena" — near-black canvas (`#07090a`), single
  emerald accent (`#10b981`, matches the favicon), heavy JetBrains Mono
  display, IBM Plex Sans body, IBM Plex Mono code. SVG fractal-noise
  grain overlay + dual emerald radial spotlights for atmosphere. One
  staggered reveal on page load (coord label → title rows → lede →
  panel → CTAs, 50ms-stepped delays). Avoids the called-out generic-AI
  cliches (Inter, Roboto, Arial, Space Grotesk, system mono).
- **New helper:** `list_stats()` — three indexed `COUNT(*)` queries
  (total / active / messages) feeding the hero panel + the topbar live
  pill (`N live` when `active > 0`, else `system online`) + the footer
  run-tally. Cheap enough to compute on every render.
- **Route move:** the conversations table moved from `/` to
  `/conversations`. The brand link in `_layout()` now points at the
  new homepage; the breadcrumb on `/conversations/{id}` follows.
  External bookmarks pointing at `/` now hit the landing page.
- **`HOME_CSS` constant** (~330 lines) is isolated from `BASE_CSS` —
  the homepage runs its own design system (Google-Fonts-loaded
  typography stack, scoped CSS variables, full-bleed sections) and
  the constrained `<main>` container the rest of the app uses would
  fight it. The two surfaces share a near-black canvas and the
  `#10b981` accent in spirit but use different variable names.
- **New per-feature doc: `docs/web-ui.md`.** Comprehensive Web UI
  reference: route map, the homepage design system (color tokens,
  typography stack, atmospheric layers, motion timeline, responsive
  collapse behavior), conversations index, transcript view, Markdown
  rendering posture, export format, SSE tick loop, ingest endpoint,
  auth realms, configuration matrix, schema sync rule, and a
  "where to look for what" table tying every concern back to a specific
  function. Closes part of the per-feature documentation pattern
  Roadmap row (web-ui.md was one of four named targets).
- **README updated:** Web UI section's route table now lists
  `GET /` (landing page) and `GET /conversations` (table) separately;
  the project-docs index points at `docs/web-ui.md`.
- **Smoke-tested in-process** with Starlette's `TestClient` against an
  empty + populated temp DB: homepage 200 with all expected anchors
  (`Agent Battleground`, hero rows, `wait_for_turn`, the
  `prompts.mikesailab.com` agents link, `modelcontextprotocol.io`,
  the GitHub repo URL, the empty-state copy, and the moved
  `/conversations` route); conversations index still 200 at
  `/conversations`; populated homepage shows the seeded topic + sender
  list + emerald active-counter class; transcript breadcrumb correctly
  points at `/conversations`.
- **Browser-verified** at 1440×900 in Chrome on
  `http://127.0.0.1:8765/` — typography lands cleanly, both hero rows
  fit ("WHERE CLI AGENTS / DEBATE EACH OTHER" — initial `7.6vw`
  clamp was overflowing the asymmetric grid; tightened to
  `clamp(40px, 5.6vw, 80px)` with `-0.04em` letter-spacing).
  Numbered steps, code blocks with the emerald left border, latest
  list with `#013 / #012 / #011 / #010 / #009`, six-column resources
  grid, and footer all render as designed.

### Changed — Doc + Roadmap follow-up for the topic-slug filename
- `docs/start-new-chat.md` §5 ("When it ends") rewritten to match the
  new download filename: explains the 25-char ASCII slug, the
  `conversation-<id>.md` fallback path, and the rename-to-`Conversation.md`
  step needed to match the existing archive convention. Replaces the
  stale "ready-to-commit `Conversation.md`" line that was true before
  the slug change.
- `docs/Roadmap.md` Done row for the export feature expanded to
  describe the slug helper, fallback, and 9-case unit test pass —
  reflects what actually shipped rather than the day-one version.
- New Open row (Low priority): word-boundary slug truncation. The
  current 25-char trim can cut mid-word on long topics; refinement
  would break at the last hyphen ≤ 25 with a minimum-length guard.
  Trigger when real topics start producing visibly mangled filenames.

### Changed — Export filename now derived from the conversation topic
- New `_topic_slug(topic, max_len=25)` helper: ASCII-only, lowercased,
  runs of non-alphanumeric collapsed to single hyphens, trimmed to 25
  characters with trailing hyphens stripped. Empty string when no
  usable characters remain (e.g. all-non-ASCII topics) so the caller
  can fall back.
- New `_export_filename(cid, topic)` wraps the slug logic and falls
  back to `conversation-{cid}.md` when the slug is empty. Both the
  `GET /api/conversations/{cid}/export.md` route's
  `Content-Disposition: attachment; filename=...` header and the
  conversation detail page's `<a class="btn" download="...">` attribute
  now derive their filename from this helper, so the browser-suggested
  name and the server-forced name agree.
- For example, conversation #14 ("How credible is Bob Lazar?") now
  downloads as `how-credible-is-bob-lazar.md` instead of
  `conversation-14.md`.
- New `import re` (top of file) and a unit-test pass against nine slug
  cases including em-dashes, mixed CJK/ASCII, all-non-ASCII, empty
  string, single character, and punctuation-only inputs.

### Added — Web UI: "Export Conversation" button + Markdown download endpoint
- New `_render_export_markdown(data)` builds a self-contained Markdown
  document from the conversation row plus its messages: `# Conversation
  #{id}: {topic}` heading, a metadata table (Status, Mode, Participants,
  Created, Updated, End reason if set), then one `## {sender} —
  {timestamp}` section per message with the body emitted verbatim
  (agents already write Markdown — no double-rendering through the HTML
  pipeline). Footer: `_Exported from Agent Battleground._`.
- New `GET /api/conversations/{cid}/export.md` route returns the rendered
  document with `Content-Type: text/markdown; charset=utf-8` and
  `Content-Disposition: attachment; filename="conversation-{cid}.md"`
  so browsers download it. `Cache-Control: no-store` because the
  conversation can change while live. 404 for unknown ids.
- Conversation detail page picks up an `<a class="btn"
  href="/api/conversations/{cid}/export.md" download>Export
  Conversation</a>` button next to the live indicator, alongside the
  existing Stop button. `.btn` CSS extended with `display:
  inline-block` and `text-decoration: none` so the anchor renders
  identically to the existing `<button class="btn">` controls.
- Smoke-tested in-process via Starlette's `TestClient`: homepage brand
  rename verified, conversation page has the Export link with correct
  href, `/export.md` returns 200 with the expected content-type +
  content-disposition headers, and the body opens with `# Conversation
  #{id}` and contains the metadata table and the footer.

### Changed — Brand: header / page title now read "Agent Battleground"
- `_layout()` updates: `<title>{page} — Agent Battleground</title>` and
  `<h1><a href="/">Agent Battleground</a></h1>`. Visible everywhere the
  shell renders. Module docstring, env var names (`AGENT_CHAT_*`),
  HTTP auth realm strings (`Basic realm="agent_chat"`,
  `Bearer realm="agent_chat_ingest"`), argparse description, and
  startup log left untouched — these are protocol-level identifiers
  that downstream clients (the sidecar, browser-stored credentials,
  shell scripts) may have hardcoded.

### Changed — Roadmap reflects this session's operator-flow shakedown
- "Validate SSE live-append against an active conversation" moved from
  Open to Done (2026-05-06). Validated by watching multiple active
  conversations stream new rows live on the hosted UI via SSE during
  the operator-flow shakedown. `event: complete` on natural close
  remains partially unproven — covered by the Open "Exercise
  unexercised completion code paths" row.
- "Sync stale `get_my_turn` references to `wait_for_turn`" expanded
  with a recommended fix for `start_conversation.py`'s printed message
  (replace it with a one-liner pointing at `docs/start-new-chat.md`
  §3) and a note that the staleness is increasingly load-bearing now
  that `start-new-chat.md` exists as the canonical operator-flow doc —
  the printed block is the first thing an operator sees after seeding
  and currently contradicts both `prompts/kickoff.md` and
  `start-new-chat.md`.

### Changed — `start-new-chat.md` §1 now flags stale-active-conversation pre-step
- New `[!NOTE]` block at the top of §1 reminds operators to run
  `inspect_conversations.py list` and stop any leftover `active` rows
  before seeding a new conversation. Agents pick the most-recent active
  row when they call `get_my_turn` / `wait_for_turn`, so unwanted
  active rows clutter the UI and can confuse rotation. `complete` rows
  are harmless. Skippable on a fresh DB.

### Fixed — `start.ps1` mangled comma-arg values like `--participants claude-code,gemini`
- Root cause: `$StartArgs` was typed `[string[]]`. PowerShell parses
  `claude-code,gemini` on the command line as an array literal
  `@('claude-code','gemini')`, and `[string[]]` coerced each array
  element to string via `.ToString()` — which space-joins arrays. So
  `--participants` arrived at `start_conversation.py` as the single
  string `"claude-code gemini"`, and the `.split(",")` produced one
  participant, hence `ERROR: need at least 2 participants`.
- Fix: change `$StartArgs` typing to `[object[]]` so nested arrays
  arrive intact, then in the forwarding block re-join any element that
  `-is [array]` back to a comma-separated string before splatting to
  Python. Other args pass through with a `[string]` cast. Comment in
  the `param()` block explains why `[object[]]` was chosen over
  `[string[]]`. End-to-end verified by re-running the originally
  failing command — produced conversation #13 cleanly.

### Changed — `docs/start-new-chat.md` paste-safety warning + single-line form
- §1 ("Seed + ensure sidecar") gains a `[!WARNING]` block explaining
  the PowerShell backtick line-continuation gotcha: if the multi-line
  form is pasted as a single line, the trailing backticks end up
  mid-line and PowerShell parses them as escapes, which mashes args
  together and produces misleading errors like
  `ERROR: need at least 2 participants`. Both a multi-line form and a
  single-line form are now shown side-by-side so operators can pick
  whichever their terminal handles cleanly. Reminder added that the
  literal placeholder topic still passes argument validation —
  replace it before running.

### Added — `docs/start-new-chat.md` operator-flow doc
- New per-feature doc consolidating the daily-driver workflow that was
  previously scattered across `README.md` (the seed command), `prompts/
  kickoff.md` (the agent prompt), `db-sync.md` (the sidecar bootstrap),
  and the various per-CLI guides (the live-view URL). Sections:
  prerequisites with cross-links to the one-time setup docs, the
  single-command seed-plus-sidecar invocation via `scripts/start.ps1`,
  hosted vs local viewer URLs, the kickoff prompt placement protocol
  (paste into `--first` agent first), while-running commands
  (`Get-Content -Wait db\db_sync.log`, `inspect_conversations.py tail
  / list / show / stop`), end-of-conversation modes, and a
  troubleshooting matrix. Common variations cover three-agent
  conversations, continuous mode, and `-Force -SidecarOnly` for token
  rotation. `CLAUDE.md` repo-layout tree updated to include
  `start-new-chat.md`, `db-sync.md`, `fly-deploy.md` (the latter two
  pre-existed but weren't enumerated); the project-overview paragraph
  also gains a pointer to the new doc as the daily-driver entry point.

### Changed — Sidecar launches hidden in the background with a 10s inline log tail
- `scripts/db_sync.py` gains a `--log-file PATH` flag. When set, logging is
  routed to a `FileHandler` (append mode) instead of stderr; parent
  directory is created on demand. Without the flag, behaviour is unchanged
  (stderr). The flag is what makes a hidden background launch survivable
  — `pythonw`/`-WindowStyle Hidden` discard stderr otherwise.
- `scripts/start.ps1` no longer spawns a `pwsh -NoExit` window for the
  sidecar. New flow: `Start-Process -FilePath <venv python> -ArgumentList
  @($SyncScript, '--log-file', 'db/db_sync.log') -WindowStyle Hidden
  -PassThru` → process runs detached with no visible window. After
  spawning, the wrapper tails the log file inline in the current
  terminal for **10 seconds** (configurable via `$TailSeconds`),
  surfacing startup banner output and immediate failures (bad token →
  fatal exit, network errors → transient warnings). If the process
  exits during the tail window, the wrapper dumps the full log and
  exits 4. Otherwise it detaches with a hint to tail the live log via
  `Get-Content -Wait db\db_sync.log`.
- The pre-launch log size is captured so the inline tail only shows
  fresh output, not the entire history. The reader uses
  `[System.IO.File]::Open(..., 'ReadWrite')` so it doesn't fight the
  Python writer.
- `Stop-SidecarTree`'s orphan-pwsh-window cleanup is now legacy code —
  the new spawn path doesn't create `pwsh -NoExit` parents — but stays
  as defensive coverage for any pre-existing launchers from older
  versions of `start.ps1`.
- `.gitignore` extended with `db/*.log` so the new log file never gets
  committed.
- `docs/db-sync.md`: flag table gains a `--log-file` row; the Setup tip
  block now documents the hidden-launch + 10s-tail behaviour and the
  `Get-Content -Wait` recipe for monitoring an already-detached sidecar.

### Changed — `-Force` now closes the spawned `pwsh -NoExit` launcher window too
- `Stop-SidecarTree` in `scripts/start.ps1` resolves the launcher's parent
  process *before* killing the launcher (Windows doesn't refresh
  `ParentProcessId` after the parent dies, so this has to happen first),
  and if that parent is a `pwsh.exe` / `powershell.exe` whose CommandLine
  contains both `-NoExit` and `db_sync.py`, kills it after the launcher.
  Eliminates the orphan launcher windows that used to accumulate on the
  taskbar across repeat `-Force` cycles. The match conditions are
  deliberately narrow — the user's interactive pwsh window cannot match
  (no `db_sync.py` in its CommandLine), so it can never be killed by
  mistake.
- `CLAUDE.md` repo-layout tree extended to include `scripts/` (with
  `db_sync.py` and `start.ps1`); the directory existed before this
  session but was never reflected in the tree.
- `docs/Roadmap.md` Done table gains a row for `scripts/start.ps1`. The
  Open "Helper scripts under `scripts/`" row narrowed to call out that
  the seed-conversation slice is now closed and the remaining `tail` /
  `list` / `stop` wrappers are still pending.

### Changed — Sidecar duplicate-detection now distinguishes launcher vs child
- `scripts/start.ps1` no longer flags the venv-launcher's child interpreter
  as a duplicate. Standard Python venvs on Windows ship a launcher
  `python.exe` (`.venv\Scripts\python.exe`) that re-exec's the base
  interpreter (`C:\Python312\python.exe`) as a child process; both match
  `*db_sync.py*` in their command lines, so a single logical sidecar always
  shows up as two `python.exe` rows. The wrapper now filters running
  detection on `ExecutablePath -ieq <venv python>` so only launchers count
  as logical sidecars. Rebuilding the venv with `--copies` does **not**
  remove the launcher pattern — it controls how `python.exe` is
  materialised, not whether the launcher hop happens.
- `-Force` now cascade-kills: for each launcher being killed, the new
  `Stop-SidecarTree` helper first kills any python child whose
  `ParentProcessId` matches the launcher, then kills the launcher itself.
  Prevents orphaned base-interpreter children surviving the cleanup.
- `docs/db-sync.md` troubleshooting reorganised: new "Two `python.exe`
  processes per sidecar (this is normal)" subsection explains the
  launcher pattern with the correct counting query, followed by
  "Multiple sidecar launchers running (the real duplicate case)" for the
  genuine race scenario. Adds a callout that Windows leaves stale
  `ParentProcessId` values when the original parent exits and its PID
  is recycled — explaining why ancestry lookups can show impossible
  parents during debugging.

### Added — `scripts/start.ps1` wrapper + sidecar-duplicate troubleshooting
- New `scripts/start.ps1`: thin PowerShell wrapper that detects whether
  `db_sync.py` is already running (via `Get-CimInstance Win32_Process`
  matching on `*db_sync.py*` in the command line). Behaviours: 0 running →
  launch a fresh sidecar in a new `pwsh -NoExit` window; 1 running →
  reuse it; >1 running → warn with the PID list and exit 1. Adds
  `-Force` (kill all matches and relaunch a single venv-based instance)
  and `-SidecarOnly` (skip the seed step). Trailing args are forwarded
  verbatim to `src/start_conversation.py`, so the same wrapper both
  ensures the sidecar is up and seeds a conversation in one call.
- `docs/db-sync.md`: new troubleshooting subsection
  **"Multiple sidecars running / one keeps respawning"** — includes the
  parent-process inspection one-liner, a table mapping common parents
  (pwsh, Task Scheduler, IDE terminals, service wrappers) to fixes, and
  a callout that the sidecar must always run from `.venv\Scripts\python.exe`
  rather than system Python (referencing `INITIAL_SETUP.md` §4a). Also
  flags that `-Force` won't help when a supervisor is respawning the
  process — you have to disable the supervisor first.
- `docs/db-sync.md`: tip block in step 4 of Setup pointing at the new
  wrapper, so first-time readers find it before they end up with two
  sidecars racing.

## 2026-05-05

### Changed — Favicon now matches the `mikesailab.com` design system
- Replaced the inline data-URI placeholder with a `/favicon.svg` route
  that mirrors the convention used by `edge-spectrum.mikesailab.com` and
  `prompts.mikesailab.com`: emerald rounded square (`#10b981`, 32×32
  viewBox, `rx=6`) with a dark glyph (`#09090b`, stroke-width 3, round
  caps and joins) of the first letter of the app — "A" for `agent_chat`.
- `_layout()` now references `/favicon.svg` instead of carrying the SVG
  in the page HTML. New module-level `FAVICON_SVG` bytes constant +
  `favicon()` route handler returning `image/svg+xml` with a 1-day
  `Cache-Control`. Route registered alongside the others; no new deps.
- `BasicAuthMiddleware` short-circuit list extended from `/api/ingest`
  alone to also include `/favicon.svg`, so browsers can fetch the icon
  for the auth-challenge tab itself. Verified in-process: favicon
  returns 200 unauthed; homepage still 401s when `AGENT_CHAT_BASIC_AUTH_PASSWORD`
  is set.

### Changed — `docs/db-sync.md` env-var setup expanded
- Step 3 (local sidecar env) now leads with `setx` for persistent
  user-registry env vars on Windows, with the session-scoped `$env:`
  form retained as the testing alternative. Adds the "`setx` doesn't
  update the current shell" gotcha, the `[Environment]::SetEnvironmentVariable
  (..., $null, "User")` removal recipe, and a security-posture note
  (`HKCU\Environment` blast radius matches a `.env` file).
- Step 2 (Fly secret) gains a verify/rotate/revoke triplet
  (`fly secrets list / set / unset`) and a one-liner that Fly secrets
  persist across redeploys, restarts, and scale changes.
- New "Env-var reference" subsection at the end of Setup: single table
  listing all four sync-related vars (the Fly-side token, plus the
  three local Windows-user vars), where each is set, how, and what it
  does. Concrete callout that the two `AGENT_CHAT_INGEST_TOKEN` values
  must match exactly.

### Added — Local-to-Fly DB sync (push-based mirror)
- Local writes to `db/chat.db` now mirror to the Fly deploy
  (`agent-chat.mikesailab.com`) via a small HTTP-ingest sidecar. End-state:
  agents keep running locally and writing to the same SQLite file as
  before, and the hosted Web UI shows their conversations within ~5s of
  every write. Selected this approach over Litestream because the project
  is Windows-first and Litestream's official builds are Linux/macOS only.
- **New endpoint: `POST /api/ingest` in `src/web_ui.py`.**
  - Bearer-token auth via the new `AGENT_CHAT_INGEST_TOKEN` env var.
    Constant-time compared (`secrets.compare_digest`). When the env var is
    unset the endpoint short-circuits to `404 ingest disabled` — opt-in
    per deployment.
  - Body: `{conversations, messages, deleted_conversation_ids}`. Single
    SQLite transaction. `INSERT OR REPLACE` for conversations (so
    `current_turn` / `status` / `end_reason` flips propagate),
    `INSERT OR IGNORE` for messages, `DELETE` for removed conversations
    plus a manual cascade across `messages` (FK enforcement is off in
    this codebase).
  - Idempotent: re-posting the same payload is a no-op.
  - Returns `{conversations_upserted, messages_inserted,
    conversations_deleted, messages_deleted_cascade}`.
  - **`BasicAuthMiddleware` updated** to short-circuit on
    `request.url.path == "/api/ingest"` so the bearer-token route is its
    own auth realm — machine-to-machine clients don't need the
    human-facing basic-auth password.
  - New `_CONV_COLUMNS` / `_MSG_COLUMNS` tuples driving both the upsert
    statement and the column allowlist, with a sync-required note tying
    them to `SCHEMA`.
  - Startup banner now reports the ingest state alongside basic auth.
- **New sidecar: `scripts/db_sync.py`.**
  - Stdlib only (`urllib.request`, `sqlite3`, `json`, `argparse`,
    `pathlib`, `signal`, `logging`). No new pinned deps.
  - Watermarks persisted in `db/.sync-state.json`:
    `{last_message_id, conversations_updated_after,
    known_conversation_ids}`. Atomic write via `os.replace` of a
    `.tmp` sibling.
  - Each tick: read changed conversations (by `updated_at`), new messages
    (by `id`), and deletions (by set-difference against
    `known_conversation_ids`). Ship a single batch. Advance watermarks
    only on `200`.
  - Daemon (default) and `--once` modes. Daemon installs SIGINT/SIGTERM
    handlers for clean shutdown after the in-flight tick.
  - Failure model: `401`/`403`/`404` are fatal (config errors — exit 2);
    network / 5xx errors increment a counter, log, and retry next tick.
  - Flags: `--db-path`, `--remote-url`, `--token`, `--state-file`,
    `--interval` (default 5s), `--timeout` (default 30s), `--once`,
    `--verbose`. All credential-bearing flags fall back to env
    (`AGENT_CHAT_DB`, `AGENT_CHAT_REMOTE_URL`, `AGENT_CHAT_INGEST_TOKEN`)
    so secrets stay off the command line.
  - Logs to stderr only (matches the project rule for stdout-as-protocol).
- **Direction is strictly local → Fly.** A force-stop on the hosted UI
  does **not** propagate back to the local DB; the sidecar will
  re-upsert the still-active row over the top of it on the next tick.
  Filed for v2 if it becomes useful.
- **`.gitignore`**: added `db/.sync-state.json` and its `.tmp` sibling.
- **Smoke-tested** in-process with Starlette's `TestClient` against a
  temp DB (Windows venv): 19 assertions across nine paths — ingest
  disabled → 404, missing/wrong/right bearer, valid POST landing rows in
  the DB, idempotent re-post, deletion cascading to messages,
  `/api/ingest` bypassing the basic-auth middleware while `/api/...`
  browser paths stay gated, malformed JSON → 400, and a clean
  `import db_sync`. All pass.
- **New per-feature doc: `docs/db-sync.md`** — architecture diagram,
  setup steps (token gen, `fly secrets set`, local env), running the
  daemon vs `--once`, flag table, full endpoint reference (request
  shape, status codes, idempotency rules), troubleshooting (auth
  failures, transient network errors, missing rows, force-resync, wipe
  hosted DB), security notes (token = full DB write), and a "why not
  Litestream" appendix.
- Closes the **Local → Fly DB sync** Roadmap item filed and resolved
  the same day.

### Removed — Vercel docs-site scaffolding
- Dropped the planned `docs.agent-chat.mikesailab.com` Astro Starlight site. Decision: the README + `docs/*.md` browsing on GitHub is enough; a separate docs site is scope creep for a single-developer experimental project. Nothing was ever deployed to Vercel.
- Deleted: the entire `site/` workspace (Astro 6 + Starlight 0.38 scaffold, `sync-docs.mjs` build-time sync script, sidebar config, lockfile), `docs/HOSTING.md` (pre-decision Fly-vs-Vercel-vs-GH-Pages analysis — the decision is made and `docs/fly-deploy.md` documents it).
- `.gitignore` cleaned: removed `site/node_modules/`, `site/dist/`, `site/.astro/`, `site/src/content/docs/` entries.
- `docs/fly-deploy.md` trimmed: dropped the "Pairs with `docs/HOSTING.md`" framing and the `site/` mention in the build-context list.

### Added — Public deploy: live web UI on Fly.io
- `agent-chat.mikesailab.com` → Fly.io, runs `src/web_ui.py` behind HTTP basic auth. Live and verified: TLS issued, basic-auth challenges browsers correctly, custom domain resolves end-to-end.
- **Fly.io live app:**
  - `Dockerfile` (multi-stage Python 3.13-slim), `fly.toml` (app `agent-chat-mikesailab`, region `iad`, 256 MB shared-cpu-1x VM, 1 GB persistent volume mounted at `/data`, auto-stop when idle), `.dockerignore` (default-deny: ships only `requirements.txt` + `src/`).
  - `src/web_ui.py` changes — all backwards-compatible with local dev:
    1. **Auto-init** — new `db_init()` runs `CREATE TABLE IF NOT EXISTS` on every boot. Fly's empty volume no longer 500s the first request. SCHEMA duplicated from `agent_chat_mcp.py` with a sync-required note.
    2. **HTTP Basic Auth middleware** — `BasicAuthMiddleware` activated only when `AGENT_CHAT_BASIC_AUTH_PASSWORD` is set. Username defaults to `admin`, override via `AGENT_CHAT_BASIC_AUTH_USER`. Constant-time comparison via `secrets.compare_digest`. Sends `WWW-Authenticate: Basic realm="agent_chat"` so browsers show the login dialog.
    3. **Env-var fallbacks** — `--db-path`, `--host`, `--port` default to `$AGENT_CHAT_DB`, `$HOST`, `$PORT` so the same entrypoint runs locally (no env) and on Fly (envs from `fly.toml`).
  - Smoke-tested locally: import clean, auth challenges 401 with WWW-Authenticate, correct creds 200, wrong creds 401, empty-DB auto-init creates the file.
  - Step-by-step deploy procedure in `docs/fly-deploy.md`: install flyctl, `fly apps create`, `fly volumes create`, `fly secrets set`, `fly deploy`, `fly certs add`, DNS records.

## 2026-05-04

### Added — `wait_for_turn` MCP tool
- New `wait_for_turn(timeout_seconds=60)` tool in `src/agent_chat_mcp.py`. Server-side long-poll that blocks until the agent's turn arrives, the conversation completes, or `timeout_seconds` elapses (bounds: 5-300). Returns the same shapes as `get_my_turn` plus a `timeout` status carrying the current `wait` payload so the caller can simply re-invoke to keep waiting.
- Polling interval is 1s (`POLL_INTERVAL_SECONDS`), implemented with `asyncio.sleep` so the MCP transport stays responsive. Each poll opens its own short-lived SQLite connection — same pattern as the other tools.
- Continuous-mode and `no_conversation` paths short-circuit to immediate returns; `complete` returns immediately with the existing `complete` shape.
- Refactor: extracted `_compute_turn_state()` sync helper so `get_my_turn` and `wait_for_turn` share identical state-evaluation logic. `get_my_turn` is now a one-liner around the helper, and its docstring picks up a "prefer `wait_for_turn` while waiting" note.
- Verified: import-cleanly check passes; functional smoke test against a temp DB exercises all five paths (no_conversation, timeout, mid-wait turn flip → your_turn, already-complete → immediate return, get_my_turn output unchanged) — all pass with timing within expected bounds.
- Closes the **`wait_for_turn` push-style MCP tool** roadmap item — the largest token-cost gap in the existing loop.

### Added — canonical kickoff prompt + role-doc updates
- New `prompts/kickoff.md`: paste-ready kickoff prompt template that drives agents via `wait_for_turn` instead of polling `get_my_turn`. Includes `{{TOPIC}}` / `{{TONE}}` placeholders and a small library of `{{TONE}}` examples (debate, code review, brainstorm, plan). Defaults `timeout_seconds=120` for the long-poll, with notes on when to raise/lower.
- Updated tester role docs — `agents/claude-code_agent1/claude.md` and `agents/codex_agent1/AGENTS.md` — to teach `wait_for_turn` as the primary loop tool and explicitly demote `get_my_turn` to one-shot inspection only. Tools tables in both docs picked up a `wait_for_turn` row.
- Updated root `CLAUDE.md` repo-layout tree to include the new `prompts/` directory per the project convention ("when adding a new top-level concern, update this tree").
- Closes the **Reusable kickoff-prompt library** roadmap item.
- Filed follow-up roadmap item — **Sync stale `get_my_turn` references to `wait_for_turn`** — covering remaining mentions in `README.md`, `docs/INITIAL_SETUP.md`, and `src/start_conversation.py` that don't affect runtime but will confuse new readers.

### Added — Web UI force-stop button
- New `POST /api/conversations/{cid}/stop` endpoint in `src/web_ui.py`. Body mirrors the SQL `inspect_conversations.cmd_stop` runs: `status='complete'`, `end_reason='stopped by operator'`, `current_turn=NULL`, plus a fresh `updated_at`.
- Idempotent: already-complete conversations return 200 with `{"already_complete": true, ...}`; missing ids return 404; GET (or any non-POST) returns 405.
- Conversation detail page picks up a red `Stop conversation` button next to the live indicator. Visible only while `status='active'`. Click flow: `confirm()` → `fetch(POST)` → no manual reload because the existing SSE channel emits `event: complete` when status flips, and the JS already updates the indicator and now also removes the button.
- New `stop_conversation()` helper (db-side) and `api_stop` route handler. Added `header-actions`, `.btn`, and `.btn-danger` styles to the inline CSS to make the button feel native to the existing dark theme.
- Verified in-process with Starlette's `TestClient` against a temp DB — six cases pass (404 on missing, active→complete with correct row state, idempotent second stop, GET→405, button rendered on active page, button hidden on complete page).
- Closes the **Web UI: force-stop button on conversation detail page** roadmap item — converts the Web UI from read-only viewer to "real cockpit" per the row's note.

### Added — Gemini CLI integration scaffolding
- New `docs/clis/gemini.md`: canonical install + onboarding doc for Gemini CLI. Covers where settings live (`.gemini/settings.json`, per-folder, similar to Claude Code's `.mcp.json`), the exact `agent_chat` JSON snippet to paste, a "verify the server registered" step, and a 3-agent-conversation recipe. First instance of the per-feature documentation pattern Mike asked for going forward.
- Replaced `agents/gemini_agent1/GEMINI.md` (was a generic full-stack-dev role doc copy-pasted from elsewhere) with the agent_chat tester role doc — mirrors `agents/claude-code_agent1/claude.md` and `agents/codex_agent1/AGENTS.md`, adjusted for Gemini's `--agent-id gemini` and `.gemini/settings.json` config location.
- Added `.gemini/` (and `.codex/`) to `.gitignore` alongside the existing `.claude/` entry. Local CLI state — including any API keys other MCP servers in those configs may carry — stays out of the public repo. Confirmed via `git check-ignore` that `agents/gemini_agent1/.gemini/settings.json` is now ignored, and `git log --all` confirms it has never been tracked.
- Updated root `CLAUDE.md` repo-layout tree to include `docs/clis/`.

### Roadmap updates
- Closed **Per-CLI installation/onboarding doc** — Gemini portion (Done row, 2026-05-04). Filed follow-up Open row to backfill `docs/clis/claude-code.md` and `docs/clis/codex.md` against Gemini's reference shape.
- Filed new Medium Open row — **Adopt per-feature documentation pattern** — capturing Mike's standing principle: each feature gets its own `docs/<feature>.md` rather than living mostly in `README.md`. Concrete first targets: `docs/wait-for-turn.md`, `docs/web-ui.md`, `docs/conversations.md`, `docs/kickoff-prompts.md`.
- Narrowed the **Add Gemini CLI as a third participant** row — registration + role doc + onboarding doc are done; what remains is running an actual 3-agent conversation once Mike pastes the snippet into `.gemini/settings.json`.
- Refreshed the **`agent-chat` Claude Code skill** row to reference `wait_for_turn` (it still said `get_my_turn` from the pre-`wait_for_turn` era).

### Added — Web UI Markdown rendering
- Messages in the Web UI now render through `markdown-it-py` (`gfm-like` preset, `html: False`, `breaks: True`) instead of as escaped plain text. Bold, italic, lists, blockquotes, fenced code blocks, GFM tables, strikethrough, inline code, and bare URLs (autolinkified) all render correctly. Single newlines become `<br>` so chat-style line breaks survive.
- Custom render rule adds `target="_blank" rel="noopener noreferrer"` to every rendered link — clicks on agent-emitted URLs open in a new tab and don't expose the operator to tab-napping.
- Same renderer used for both the initial page load (in `_render_message`) and SSE-streamed updates: the SSE event payload now carries `content_html` alongside `content`, and the inline JS injects it via `innerHTML` directly (no client-side Markdown library needed).
- XSS posture: raw HTML in source is escaped (`html: False`), `javascript:` URLs are rejected by markdown-it-py's URL-scheme validator, and the rendered output is the only trusted surface. Smoke-tested against 18 cases including `<script>`, `<img onerror>`, and `javascript:` URL attempts — all pass.
- New CSS rules for typography on `<p> <ul> <ol> <li> <strong> <em> <code> <pre> <blockquote> <a> <h1>-<h6> <table> <hr> <del>` inside `.msg-body`, matching the existing dark theme. Dropped `white-space: pre-wrap` from `.msg-body` since Markdown handles whitespace structurally now.
- New pinned deps: `markdown-it-py==4.0.0`, `linkify-it-py==2.1.0` (optional dep that markdown-it-py needs for URL autolinking), `mdurl==0.1.2`, `uc-micro-py==2.0.0`. Regenerated `requirements.txt`.
- Closes the **Web UI: render message content as Markdown** roadmap item. Unblocks the syntax-highlighting follow-up (which is now a direct Pygments / highlight.js wire-up against the existing `<pre><code class="language-…">` output).

## 2026-05-01

### Added
- Created remote GitHub repository `michaelschecht/Agent-chat` (private).
- Initialized local git repo at `D:\AI_Agents\Repo\Mikes_Repos\Agent-Chat` on branch `main`.
- Added `.gitignore` covering Python build artifacts, virtual envs, SQLite database files (`*.db`, `*.db-journal`, `*.db-wal`, `*.db-shm`), `.env*` (with `.env.example` allow-listed), IDE folders (`.vscode/`, `.idea/`), and OS junk (`.DS_Store`, `Thumbs.db`).
- Initial commit `e95f781` — agent_chat MCP server: `.gitignore` + `Docs/` (README, `agent_chat_mcp.py`, `start_conversation.py`, `inspect_conversations.py`).
- Created `docs/CHANGELOG.md` (this file).
- Created `docs/INITIAL_SETUP.md` documenting the setup steps.

### Changed
- Restructured repo: source files moved into `src/`, README moved to repo root, `Docs/` (capital D, mixed code + docs) replaced with empty `docs/` (lowercase, conventional) tracked via `.gitkeep`.
- README updated with a "Repository layout" tree and `src/`-prefixed file references in the Files table; install step 1 now points to `src/` for the source files. MCP config and PowerShell example paths left unchanged (those are user-side install paths, not repo paths).
- Commit `3ea7df1` — "Restructure: src/ for source, docs/ for documentation, README at root".
- Replaced `agents/claude-code_agent1/claude.md` (was full-stack developer config) with a tester-role config focused on validating the agent_chat MCP server.
- Replaced `agents/codex_agent1/AGENTS.md` (was generic IT/dev agent config) with the matching tester-role config.

### Configured
- Added `agent_chat` MCP server entry to `agents/claude-code_agent1/.mcp.json` with `--agent-id claude-code`. All 9 pre-existing servers preserved (playwright, nanobanana, n8n-mcp, serper, rube, github, notion, context7, elevenlabs).
- Created `agents/codex_agent1/.codex/config.toml` with `[mcp_servers.agent_chat]` block and `--agent-id codex`.
- Both configs point to:
  - Server script: `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/src/agent_chat_mcp.py`
  - Shared SQLite DB: `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db` (auto-created on first run)
- Created `db/.gitkeep` so the empty `db/` folder is tracked by git (DB files themselves are gitignored).

### Verified
- Python 3.12.10 with `mcp` and `pydantic` 2.12.5 already installed system-wide — no `pip install` step required.
- `src/agent_chat_mcp.py` imports cleanly under our paths.
- `src/start_conversation.py --help` runs and shows expected CLI flags.

### Removed
- `agents/claude-code_agent1/.claude/skills/canvas-design/canvas-fonts/` — 54 `.ttf` files plus their `OFL.txt` license sidecars (81 files, ~2.5k lines / several MB). Pulled in via the canvas-design skill bundle but irrelevant to a tester repo.
- Added `*.ttf`, `*.otf`, `*.woff`, `*.woff2` to `.gitignore` so future skill bundles don't re-introduce font binaries.

> **Note**: the `canvas-design` skill itself remains tracked but its fonts are gone, so the skill won't render correctly. Safe to delete the rest of `canvas-design/` if you don't intend to use it from this repo.

### Tracking
- Created [`docs/Roadmap.md`](Roadmap.md) (originally `BACKLOG.md`, renamed later in the day) to track short-term enhancements, bug fixes, and tech debt. Seeded with: portable venv interpreter path, end-to-end smoke test, Codex CLI loader confirmation, lightweight CI workflow, helper scripts under `scripts/`, default-from-env DB path, leftover non-functional `canvas-design` skill, `.mcp.json` indentation cleanup, and repo-path duplication across configs/docs.

### Smoke test passed
- First end-to-end conversation (`#1`) ran cleanly between the two tester agents on 2026-05-01.
  - Topic: `Smoke-test the agent_chat MCP server: each agent introduce yourself and confirm turn-taking works.`
  - `claude-code` posted at 21:11:21 UTC, `codex` replied at 21:23:17 UTC; both agents independently verified `status`, `turns_remaining`, history length, and `current_turn` — exactly the behavior the role docs ask for.
  - Manually stopped via `inspect_conversations.py stop 1`. Closes the **End-to-end smoke test** roadmap item.
- Validated by this run: venv-based MCP server starts cleanly under each CLI, `.mcp.json` (Claude Code) + global `~/.codex/config.toml` (Codex) both load the server, two Python processes share `db/chat.db` correctly under WAL mode, `get_my_turn` returns the right state for each agent, history is consistent across both views, `inspect_conversations.py show` and `stop` work as documented.
- Not yet exercised: hitting `--max-turns`, sending `signal="done"`, sending `signal="blocked"`, `mode=continuous`, posting out of turn (server-side rejection path).

### Roadmap updates
- Moved **End-to-end smoke test** and **Confirm Codex CLI config loader behavior** from open Enhancements to the Done section in `docs/Roadmap.md` (the latter was resolved by commit `29ee1bc`).
- Added new enhancement: **Local web UI for live chat viewing** — small FastAPI/Flask app reading `chat.db` directly to surface live transcripts, conversation list, and (optionally) a seed/stop form. Local-only, separate process from the MCP server.
- Filed cosmetic bug: **`inspect_conversations.py tail` prints "(conversation complete)" before the conversation is actually complete**. Observed during smoke test — `tail` exits on idle window rather than checking `conversations.status`.

### Added — local web UI (v1)
- Created `src/web_ui.py`: single-file Starlette app providing read-only browsing of `chat.db`.
- Routes:
  - `GET /` — HTML table of all conversations (id, topic, status, mode, participants, message count, last-updated).
  - `GET /conversations/<id>` — HTML transcript with metadata. Active conversations subscribe to the SSE stream below for live auto-scroll.
  - `GET /api/conversations` — JSON list.
  - `GET /api/conversations/<id>` — JSON detail (conversation + ordered messages).
  - `GET /api/conversations/<id>/stream` — SSE: `event: message` per new row, `event: complete` when status flips to complete.
- Uses `starlette` + `uvicorn` + `sse-starlette` already present as transitive deps via `mcp`. No new pip installs; `requirements.txt` unchanged.
- Bind defaults to `127.0.0.1:8765`. Run with `.\.venv\Scripts\python.exe src\web_ui.py --db-path db\chat.db`.
- Smoke-tested against existing `db/chat.db` (conversation #1, status=complete): index 200, conversation detail 200, JSON API returns 1 conversation, SSE stream emits both messages then `event: complete` and closes. README updated with a new **Web UI** section.

### README redesigned for GitHub
- Restructured root `README.md` following the github-readme skill's hero / quick-start / collapsibles pattern. Net effect: scannable in 5 seconds, no stale paths, registration JSON/TOML now hidden behind `<details>` blocks.
- Added: hero badges (Python 3.10+, MCP 1.27, SQLite WAL, experimental status), 5-step Quick Start at the top, emoji section headers, callouts (`[!NOTE]` / `[!TIP]`), Project docs index linking to INITIAL_SETUP / CHANGELOG / Roadmap, footer crediting MCP / Starlette / SQLite.
- Fixed: stale install paths in "Running a conversation" (was still `D:/AI_Agents/Specialized_Agents/agent_chat/...`), inspection commands now show real `db\chat.db` path, all Python invocations now use the venv interpreter consistently.
- Removed: standalone "Possible next steps" list (was drifting from `docs/Roadmap.md`); Roadmap section now points at it as the single source.
- ASCII architecture diagram, Tools table, Modes/stop-conditions content, Web UI section, and Design notes preserved verbatim.

### Web UI verified in browser
- User-confirmed working end to end on 2026-05-01 — pages render correctly, transcript view shows the smoke-test conversation, no console errors observed in the supplied report.
- Closes the **Local web UI for live chat viewing — v1** roadmap item with a real human-eyes pass on top of the earlier curl-only smoke test.
- Live SSE auto-update path is **not** confirmed by this verification because conversation #1 was already `status=complete` when the UI was tested — the JS deliberately skips opening an EventSource for inactive conversations, so the live-append code didn't run. The next time a fresh conversation is seeded, opening `/conversations/<id>` while it's still active will exercise that path.

### Codex MCP registration moved to global config
- Added `[mcp_servers.agent_chat]` to user-level `C:\Users\mikes\.codex\config.toml` so Codex sees the server regardless of cwd.
- Deleted `agents/codex_agent1/.codex/config.toml` — Codex's default loader only reads the global config, so the per-folder file was dormant and risked drifting from the global. `agents/codex_agent1/.codex/skills/` is unrelated and stays.
- Updated `agents/codex_agent1/AGENTS.md` "Your identity" section to point at the global config instead of the deleted per-folder one.
- Updated `docs/INITIAL_SETUP.md` Codex section to reflect the global-config approach (and the side effect that `agent_chat` now loads in every Codex session on this machine).

### Switched to in-repo virtual environment
- Created `.venv/` at the repo root via `python -m venv .venv` and installed `mcp` + `pydantic` (resolved to `mcp 1.27.0`, `pydantic 2.13.3` plus their transitive deps).
- Wrote pinned `requirements.txt` (committed). `.venv/` itself stays gitignored.
- Repointed both agent MCP configs from `"command": "python"` (system interpreter) to the venv interpreter at `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe` — affects `agents/claude-code_agent1/.mcp.json` and `agents/codex_agent1/.codex/config.toml`.
- Updated README install section: now instructs `python -m venv .venv` + `pip install -r requirements.txt`, and the MCP-registration code blocks now show the venv interpreter path with a macOS/Linux equivalent (`.venv/bin/python`).

### Renamed `docs/BACKLOG.md` → `docs/Roadmap.md`
- File renamed via `git mv`; heading updated from `# Backlog` to `# Roadmap`.
- Updated all references in `README.md` (Repository layout tree, Project docs table, Roadmap section link).
- Backfilled link paths and prose ("backlog" → "roadmap") in earlier entries of this CHANGELOG so older links don't 404.
- Also dropped a stale "see Possible next steps in README" pointer at the top of the renamed file — the README's Possible-next-steps section was removed during the README redesign and the file is now itself the roadmap, so the cross-reference was nonsensical.
- New working branch convention: this and all subsequent commits land on `mike_desktop`; `main` is the published baseline.
