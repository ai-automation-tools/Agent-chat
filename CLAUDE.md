# Agent-Chat

Project-specific instructions for Claude Code. These override generic guidance.

---

## What this project is

**Agent-Chat** is a local MCP server that lets two or more CLI agents — Claude Code, Codex, Antigravity, OpenCode (Gemini is deprecated, kept as a fallback) — hold structured, turn-based conversations with each other. Each CLI registers the same `agent_chat_mcp.py` with a different `--agent-id` and the same `--db-path`; one SQLite-WAL file is the message bus. Conversations are seeded out-of-band by `start_conversation.py`. Agents call `get_my_turn()` to discover state and `send_message()` to reply. The server enforces turn order, per-agent message caps, and `done` / `blocked` stop signals. No daemon, no port, no auth — identity is config-only.

- **Repo root:** `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/`
- **Remote:** https://github.com/michaelschecht/Agent-chat · **Default branch:** `main` (working branch is often `mike_desktop`)
- **Status:** experimental / single-developer

---

## Repo map

`docs/repo-layout.md` carries the full annotated tree and `src/README.md` the module tour — this is the short version.

```
src/
├── agent_chat_mcp.py        # The MCP server (FastMCP + sqlite3) — canonical SCHEMA
├── start_conversation.py    # argparse wrapper around orchestrator.seeding
├── inspect_conversations.py # CLI: list / show / tail / stop
├── presets.py               # Named kickoff presets (tone + mode + max_turns)
├── web_ui.py                # Web-UI ENTRYPOINT only: page routes + route table + app assembly + main()
├── web/                     # Web-UI implementation: db.py (SQL + set_db_path) · security.py
│                            #   (auth/read-only middleware) · assets.py (CSS/JS) · avatars.py ·
│                            #   topics.py · render/ (per-page HTML) · api/ (/api/* handlers)
└── orchestrator/            # seeding.py (single source of truth for seeding) · availability.py
                             #   (which CLIs this machine has + seat planner) · conv_types.py ·
                             #   seats.py (agent-id grammar) · preflight.py · personas.py ·
                             #   model_personas.py · media_prompts.py · export.py (bundle contract) ·
                             #   delivery.py (push a finished conversation out — off by default)

agents/         # LOCAL-ONLY, gitignored. CLIs/<cli>_agent1|2 = one folder per SEAT (role doc +
                #   MCP config; make new seats with scripts/setup/add_agent_seat.py).
                #   Debate-Agents/ = one-time seed cards; live personas are DB rows.
db/ config/     # chat.db at runtime; available-clis.json written by /setup. Both gitignored.
docs/           # App/ · Guides/ · Setup/ · CLI-MCP-Config/ · Testing/ · Chat-Topics/ ·
                #   Local/ (operator-only, gitignored) · Roadmap.md · CHANGELOG.md
prompts/        # Reusable operator prompts: Kickoff/ · Auto-Debate/ · Manage-Debates/ · Battleground/
skills/         # Agent Skills read by the PARTICIPATING CLIs at runtime
extension/      # AgentBattleground MV3 extension (Chrome + Firefox manifests, src/panel/lib/ modules)
scripts/        # Operator helpers — debate.ps1, db_sync.py, publish_debate.py, run-mcp-server.ps1,
                #   lib/spawn-agents.ps1 (shared CLI registry), setup/ (one-per-clone helpers)
tests/          # pytest-compatible AND standalone-runnable
.claude/        # Claude Code config. agents/ + commands/ + skills/ are TRACKED; the rest is local.
```

When you add a new top-level concern, update this map, `docs/repo-layout.md`, and the README's layout tree. When moving files under `docs/` or `agents/`, also update the README doc index, the `mikesailab` project memory (`project_mikesailab_design_system.md`), and relative `../` paths inside the moved files.

---

## Environment

- **Windows 11, PowerShell 7+ (pwsh).** Paths in commits, docs, and configs are Windows absolute paths with forward slashes. Use PowerShell syntax in docs; add a `> [!NOTE]` block for macOS/Linux equivalents rather than silently swapping.
- **Python 3.10+** in a local venv. Always invoke it explicitly: `.\.venv\Scripts\python.exe ...` — never rely on activation state.
- **Deps** are pinned exactly in `requirements.txt`. Upgrade by regenerating the full pin set with `pip freeze`, not by hand-editing lines.
- **Git user:** Mike (`mikeschecht@gmail.com`).
- **Paths:** `scripts/run-mcp-server.ps1` resolves the venv and server relative to itself, and the DB defaults to `<repo>/db/chat.db` (override with `$AGENT_CHAT_DB`), so the launcher path is the only absolute path left in each MCP config. Others still live in the README install blocks, the per-CLI configs under `agents/CLIs/`, the global `~/.codex/config.toml`, `docs/Setup/INITIAL_SETUP.md`, and the CHANGELOG. Don't add **new** hardcoded paths; if you touch existing ones, change all sites in one PR.

---

## Working with the code

### Python conventions

- Type hints on all signatures; `pathlib.Path` over `os.path`; Pydantic v2 models for tool input/output shapes; `argparse` for CLI entrypoints, matching the existing flag style (`--db-path`, `--agent-id`, `--topic`).
- **Never `print()` to stdout in `src/agent_chat_mcp.py`** — stdout is the JSON-RPC stream. Use `logging` or `sys.stderr`.

### SQLite layer

> [!TIP]
> The `agent-chat-schema` skill carries this checklist plus current table shapes; it auto-loads when you touch a schema file.

The DB is the **contract** between processes. The canonical schema is `SCHEMA` in `agent_chat_mcp.py`, but it is copy-pasted across four sites — mirror all of them in the same change:

| File | Constant | Scope |
|:---|:---|:---|
| `src/agent_chat_mcp.py` | `SCHEMA` | canonical — all 3 tables + 2 indexes |
| `src/web/db.py` | `SCHEMA` | full mirror |
| `src/orchestrator/seeding.py` | `SCHEMA` | full mirror |
| `src/orchestrator/personas.py` | `_PERSONA_DDL` | `personas` table only |

`_MIGRATIONS` — `(table, column, ddl)` triples applied by `db_init()`, gated on `PRAGMA table_info` so they stay idempotent — is duplicated in the first three.

Any schema change requires: additive columns (renames/drops need a migration plan) · a `_MIGRATIONS` row per copy so existing `db/chat.db` files upgrade in place · updating every **reader** of a changed column — `inspect_conversations.py`, the `web/db.py` helpers, `orchestrator/export.py`, the SSE payload, and the `/api/ingest` + `/api/since` sync path (a column the sidecar doesn't carry never reaches the Fly mirror) · a CHANGELOG note. `start_conversation.py` and `inspect_conversations.py` declare no schema.

Other rules: WAL mode is mandatory — two processes write the same file. Connections use `isolation_level=None` and `timeout=10.0`; the write paths use explicit `BEGIN`/`COMMIT`/`ROLLBACK`, which is only correct in autocommit mode. Parameterize all queries. And **`web.db.set_db_path()` also exports `$AGENT_CHAT_DB`** — `orchestrator.personas` resolves its own path from that env var per call and never sees `web.db.DB_PATH`, so without the export a custom `--db-path` reads conversations from one DB and personas from another.

### MCP server (`agent_chat_mcp.py`)

- Use `@mcp.tool()`; `get_my_turn`, `send_message`, `get_conversation_status` are the reference shape. Return types are Pydantic models — match the existing `model_config = ConfigDict(...)` patterns.
- `AGENT_ID` and `DB_PATH` are module globals populated in `main()` before `mcp.run()`. Don't read them at import time.
- New tools should be idempotent and read-mostly. Mutations belong in `send_message` or an explicitly-named write tool.
- **The per-agent cap ends a run when EVERY seat is spent, not the first.** `evaluate_stop()` used to return on the first agent at `max_turns`, which in a round-robin is always agent 1 — every later seat lost a turn, and a lead seated late lost the turn it was briefed to post `signal='result'` on. `next_turn_agent()` **skips spent seats** and returns None when nobody is left; the two are inseparable, since the stop rule alone parks the pointer on a finished agent and deadlocks the rotation. Pinned by `tests/test_mcp_turns.py`.

### Web UI (`web_ui.py` + the `src/web/` package)

- Starlette only — `starlette`, `sse-starlette`, `uvicorn`, nothing new. `web_ui.py` is ONLY the entrypoint; implementation goes in the matching `web/` module. Keep route paths defined only in `web_ui.py`, and keep the `web_ui` re-exports (`ReadOnlyMiddleware`, `db_init`, …) working — the tests import them.
- Binds to `127.0.0.1:8765`. **Do not add a `0.0.0.0` bind without an auth story.**
- Write endpoints exist: conversation stop/delete, `POST /api/orchestrate`, the persona endpoints, and `POST /api/ingest` (sidecar sync). A conversation mutation must mirror the SQL the CLI inspector or `orchestrator.seeding` runs; persona writes go through `orchestrator.personas`. Never reimplement seeding SQL or card-writing in a route handler. On the hosted mirror `ReadOnlyMiddleware` + `AGENT_CHAT_PUBLIC_READONLY` 403s browser mutations, so add a case to `tests/test_web_readonly.py` for each new write route.
- **The hosted demo strip and `ReadOnlyMiddleware` key off the same flag** (`_is_public_readonly()`), so a page promising "read-only" and a server allowing writes can't come apart. Not dismissible, not gated on anything else.
- **Personas are DB-backed, so persona management is NOT local-only** — `/personas` works on the hosted mirror too. `personas.root_exists()` returns True whenever the DB is reachable; the failure it guards is "database unreachable" (404 + `persona storage unavailable`), not "no local cards". The `agents/Debate-Agents/` card tree is only a one-time seed source for `import_personas_from_files()`.
- **SSE is one channel:** `event: message` per row, `event: turn` on a `current_turn` change, `event: complete` on close. Reuse it rather than opening a second.
- **The nav rail is two tables:** `_NAV_ITEMS` = pages this server renders; `_RESOURCE_NAV_ITEMS` = reference + third-party destinations under a separator. Don't collapse them — that's what made "Theater" read as a page of this app.
- **Never assume the operator has every CLI.** `/orchestrate` and the homepage read `orchestrator.availability`, not `preflight.discover_seats()`. Availability is advisory — `POST /api/orchestrate` still gates on preflight. Detection names must stay in sync with `$Clis[...].Exe` in `scripts/lib/spawn-agents.ps1` (pinned by `tests/test_availability.py`).
- **`/orchestrate` must seed through `orchestrator.seeding.seed_conversation()`** — the same function `start_conversation.py` calls.
- **Export rendering lives in `orchestrator/export.py` and its output is a contract.** `/export.md`, `/export.zip`, and `scripts/publish_debate.py` all render through it. Three external consumers parse the format (the AI-Automation-Library `Agent-Debates/` archive, the library site walker, the debate-chat-theater `build.mjs`): heading shapes, meta-table labels, `## sender — timestamp` headings, persona filenames, and the 25-char `topic_slug` are effectively frozen — read `docs/App/export-format.md` first and update the consumers in the same change.
- **Topic logos** are classified at render time by `web/topics.py` — no schema, no backfill, so re-wording the `TOPICS` table re-skins the whole archive. Ties go to the earlier entry, which is why `ai` sits near the bottom.
- **Persona avatars** resolve at render time from the persona **slug** (`web/avatars.py`, served at `GET /avatars/{slug}`): an uploaded image on the DB row → `images/AgentChat-Avatars/<slug>-avatar.png|svg` → `default-avatar.svg`.
  - **Uploads belong in the DB, never on disk** — the `personas` table syncs to the mirror with no redeploy and survives the next one; a file wouldn't.
  - **Uploads are raster-only, typed by magic bytes** (`normalize_avatar`), never by declared MIME. **SVG is refused** (script-capable markup on the app's own origin); stored bytes ship with `nosniff` + `default-src 'none'`.
  - **An avatar must survive an edit:** `update_persona()` touches it only when passed `avatar=`/`clear_avatar=`, and both import paths carry the image across an overwrite.
  - `list_personas()` selects an explicit column list **excluding `avatar_data`** — `SELECT *` would haul every image through every roster render.
  - Shipped file art needs a commit + Fly redeploy (the folder is COPYed into the image). No-persona conversations resolve from the raw agent id, which for a CLI *is* its brand-avatar slug.

### AgentBattleground (`extension/` + `web/api/battleground.py` + `web/render/battleground.py` + the arena MCP tools)

Full reference: [`docs/App/battleground.md`](docs/App/battleground.md).

- **The invariant: it drafts, it never posts.** A reply is written as a `pending` draft; only an explicit operator verdict moves it; approving *types text into the page's existing composer* and stops. Nothing may submit to a website, open a composer, or click a post button — that's the line between this and astroturfing. Any change that lets a draft reach a page without a human action needs the user's explicit sign-off. The same reasoning killed a "Launch selected CLI" button: `/roster` returns a `launch` map the panel renders as a *copyable string*; nothing local spawns a process on an HTTP request.
- **The `/battleground` console renders; it does not act.** Its buttons call bridge routes that already existed (`/drafts/{id}/verdict`, `/arenas/{id}`, `/arenas/{id}/delete`) — no new write route, and **approving there does not insert into a page**, which needs the tab. Say so on the page, not just in the docs. Hosted, it renders an explainer rather than an empty list: the arena tables never sync, so "no arenas" there would read as the opposite of the guarantee.
- **The panel is a package.** `src/panel/panel.js` is wiring + init; the work is nine ES modules in `src/panel/lib/`. They form import cycles, so they share one mutable `state` object, and every export crossing a cycle must be a hoisted `function` declaration — a `const fn = () => …` is `undefined` when a partially-evaluated module calls it. Composer insertion lives in `lib/compose.js` and nowhere else.
- **Nothing under `extension/` has a test that runs in a browser.** `tests/test_battleground.py` reaches the bridge and the MCP loop only. Say so when reporting extension work; don't describe the panel as verified.
- **House rules go in-band:** `_ARENA_RULES` ships with every `get_arena` payload so behavior doesn't depend on the `battleground` skill being installed. Keep it in sync with `skills/battleground/SKILL.md` — especially persona-voice-not-identity.
- **The two tables are local-only.** `battleground_arenas` / `battleground_drafts` are deliberately absent from the sync column lists and `scripts/db_sync.py`, so captured third-party content never reaches the mirror. Don't "fix" that.
- **Persona bodies are snapshotted** onto the arena row at capture time — editing a card must not retroactively change what a running arena's agent was told to be.
- **An arena can be cast with a persona that isn't in the registry.** `✎ custom instructions…` sends `persona_instructions`, landing in the same snapshot columns with **`persona_slug` NULL**. So: `get_arena` gates the persona on **`persona_body`, never `persona_slug`**; re-casting onto a custom card must pass `bg_update_arena`'s `clear_persona_slug`; and passing both `persona` and `persona_instructions` is a **400, not a precedence rule**. Never write a one-off card into the `personas` table.
- **The tab→arena link is keyed on tab id alone** — navigating a tab keeps the old arena attached. **↺ Start over** (`#unlink`) is the way out, and must clear `state.capture` as well as `state.arena`, or the Cast card re-offers the *previous* page's posts. Both callers use `clearCapture()`. Start over is deliberately **not** destructive — the arena and drafts survive; **Close arena** is the separate control that stops drafting.
- **Re-capture merges on post `id`** — that's the contract a site adapter in `extension/src/capture.js` exists to satisfy: stable ids, the site's own comment id wherever possible, namespaced for third-party iframes (`disqus:501`). Ids invented per capture silently duplicate the thread on every refresh.
- **A new adapter is two edits:** its label must also land in `KNOWN_SITES` (`web/api/battleground.py`) or the bridge silently coerces the arena to `generic`. `tests/test_battleground.py` pins the lists together.
- **Never let the extension acquire access without a click.** Host permissions are per-origin, requested from a user gesture (a comment iframe is a separate origin and gets its own button). The auto re-capture timer checks `permissions.contains` and skips — it must never call `permissions.request`. Firefox discards the gesture across an `await`, so click handlers start the request **before** their first await.
- **CORS stays narrow.** `ExtensionCorsMiddleware` echoes only `chrome-extension://` origins, only under `/api/battleground/`. Never widen it.

### Delivery (`orchestrator/delivery.py`)

Full reference: [`docs/App/delivery.md`](docs/App/delivery.md).

- **It renders nothing.** The folder sink writes `export.bundle_files()` verbatim, so a delivered folder is the `.zip` bundle unpacked — **byte for byte**, which is why it writes `write_bytes` and not `write_text` (Windows text mode would turn every LF into CRLF). A format change belongs in `export.py` and its contract doc. `tests/test_delivery.py` compares against the real `render_export_zip()` output, not a fixture. The one non-bundle file, `result.md`, is opt-in for exactly that reason.
- **Off unless `config/delivery.json` exists** — gitignored, same per-machine home as `available-clis.json`. Never ship a default that delivers.
- **`deliver()` must never raise.** Every failure is caught, logged to `logs/delivery.log`, and returned as a string the message path ignores. A sink costs an artifact, never a turn — and one failing sink must not stop the next.
- **Three call sites, and a test pins all three**: `send_message()`, `web.db.stop_conversation()`, `inspect_conversations.cmd_stop()`. Adding a fourth way to end a conversation means adding a fourth `deliver()` call. Do **not** hook `get_my_turn()` — it re-runs `maybe_complete()` on every poll and would re-deliver on a loop — and always call it **outside** the write transaction.
- **`result` fires per revision, `complete` fires once.** A lead that drafts-then-revises posts several results, so the default `events` list is `complete` alone and the folder sink overwrites rather than appends.
- **Which conversations get delivered is `scope` + `config/delivery-optin.json`, never a column.** A sink is `scope: "all"` (default) or `"opt-in"`; the `/orchestrate` Launch checkbox writes the opt-in list. Do **not** promote it to a `conversations` column — it is a fact about this machine's filesystem, it would have to cross four `SCHEMA` copies plus `db_sync.py` and `/api/ingest`, and it would reach a mirror where `deliveries/` doesn't exist. `tests/test_delivery.py` pins its absence. The `/orchestrate` control has **three** states (off / forced by `scope: all` / live) — don't collapse them, a disabled-but-ticked box is the honest rendering of "every conversation is delivered anyway".
- **The CLI passes `ignore_scope=True`; the automatic hooks don't.** An explicit `deliver <id>` is itself the opt-in. The two operator-stop paths are not — the launch-time decision stands.
- The CLI lives in `inspect_conversations deliver`, not in the module: `orchestrator` is a package, so `python -m orchestrator.delivery` cannot resolve from the repo root.

### Conversation types + sub-types (`orchestrator/conv_types.py` + `presets.py`)

- **Two axes, and keeping them separate is the point.** `conv_type` is the room's *structure* — who is in it, what each chair is for. `preset` is the *sub-type* — the tone, and for a type that makes something, the artifact's shape. A structure is expensive (seats, role briefs, a skill, a guide); a flavour is a dict entry. **Only add a `conv_type` when the seats genuinely differ.** Brainstorm / plan / review are presets of `collaborate`, not types, because they're the same room pointed at different work.
- **Adding a type is: a `CONV_TYPES` entry, a `_ROLE_BRIEFS` entry per seat, a `skills/<type>-mode/` (plus its `.gitignore` line), and a `docs/Guides/<type>.md` with its row in the Guides index.** The `/orchestrate` radios, the `/conversations` filter chips, export's Type/Role rows, and media prompts all generate from the registry. **No PowerShell edit** — `New-AgentPrompt` is role-agnostic.
- **A type that produces a deliverable** sets `produces_deliverable` + `deliverable_label`; its lead posts the artifact on its closing turn with **`signal='result'`**. That is a `messages.signal` value, deliberately not a column: `signal` already rides the sync, the SSE payload, and export's `` `signal=<value>` `` heading suffix, so a deliverable needs no schema change and **no export-contract change**. `maybe_complete()` must keep stopping on `done`/`blocked` only — a result is not a stop signal.
- **`lead_forces_turns`** decides whether seating a lead overrides the preset's mode. True for a room the lead *runs* (a continuous moderator or host is a free-for-all); False for one it merely *lands* — a collaboration, where `brainstorm` sets `continuous` on purpose. `POST /api/orchestrate` reads it; don't reintroduce an unconditional `mode='turns'`.
- **`lead_needs_own_seat`** says whether the lead is a *participant* or an *observer*. True for a debate's moderator and a podcast's host — neither argues or answers, so `/orchestrate` asks for the seat separately and prepends it. False for a collaboration's facilitator, which is one of the collaborators: the form hides the lead section entirely and the lead is **whoever speaks first**, assigned by `conv_types.default_roles()` from seat order. Getting this wrong deals an unpicked third CLI into a two-agent run. Use `min_participants`/`max_participants` (not `min_members`/`max_members`) anywhere the count includes the lead.
- **`Preset.for_types` is advisory** — it filters the `/orchestrate` picker, exactly like CLI availability does. Nothing rejects an odd pairing, and a preset with no `for_types` is offered everywhere.

### Personas (`orchestrator/personas.py` + `model_personas.py`)

- **Groups are free-form** — `discover_groups()` reads `SELECT DISTINCT "group"`; a group exists once a row lands in it. `PREFERRED_GROUPS` is a sort hint, not a filter, and `DEFAULT_DEBATER_GROUP` ("Unique-Personas") currently holds zero rows, which is why the random-cast paths fall through to "every persona".
- **Random casting must go through `list_debater_personas()`**, never `list_personas(None)` — it excludes `RESERVED_GROUPS` so a random debate never fields "Claude Code" against Gordon Ramsay. Callers: `POST /api/orchestrate` and `debate.ps1` via `list --castable`. An explicit `--group` / `-Group` is always honoured.
- **`AI-Models` is a reserved group**: one card per `preflight.SUPPORTED_CLIS` entry, slugged with the agent id, defined in `model_personas.py`, created on web-UI boot by `ensure_model_personas()` (create-if-missing, so operator edits survive a restart). They back the Cast panel when a conversation has no recorded `participant_personas`; recorded personas always win. Bodies are original descriptions, deliberately not copies of any vendor's system prompt.

---

## Testing & validation

Every file under `tests/` is pytest-compatible **and** standalone-runnable (`.\.venv\Scripts\python.exe tests\test_web_readonly.py`), so no test dep is pinned. Run them all after touching the web layer; `/smoke-test` does the whole checklist.

| Suite | Covers |
|:---|:---|
| `test_web_readonly.py` | auth + read-only middleware, orchestrate guard |
| `test_inspect_tail.py` | `inspect_conversations tail` completion guard |
| `test_topics.py` | topic→logo classification + tie-breaks |
| `test_model_personas.py` | AI-Models cards, reserved-group casting guard, Cast fallback |
| `test_battleground.py` | Arena bridge, capture scrubbing + merge, verdict gate, CORS, schema parity, launch-map ↔ `spawn-agents.ps1` parity, MCP loop |
| `test_persona_avatars.py` | Avatar validation, resolution order, edit-preserves-art, persona column parity `web/db.py` ↔ `scripts/db_sync.py` |
| `test_seats.py` | Agent-id grammar (`codex-2`), per-seat config paths, Codex `CODEX_HOME`, parity across `preflight._CHECKS` ↔ `SUPPORTED_CLIS` ↔ `add_agent_seat.SHAPES` ↔ `Resolve-AgentSeat` |
| `test_availability.py` | CLI detect-vs-declare, `plan_seats` round-robin, `/setup`, `/orchestrate` filtering, demo strip, two-group rail, `CLI_BINARIES` ↔ `spawn-agents.ps1` parity |
| `test_media_prompts.py` | Image/audio prompt builders + the `/prompts/{kind}.md` route |
| `test_mcp_turns.py` | Turn rotation, the **per-agent cap rule** (all seats spent, not the first), spent-seat skipping, out-of-turn rejection, `done`/`blocked`/`result`, continuous mode |
| `test_delivery.py` | Delivery sinks; **folder output == `export.zip`, byte for byte**; off-unless-configured; failure isolation; all three completion paths call `deliver()` |
| `test_conv_types.py` | Seat rules, the `conv_type` backfill, schema-mirror parity across the three `SCHEMA` copies, conversation column parity `web/db.py` ↔ `scripts/db_sync.py`, export Type/Role rows, the `signal='result'` deliverable, sub-type presets, and that the launch prompt stays role-agnostic |

Beyond that, validation is manual: import the server cleanly · `python -m json.tool` any `.mcp.json` you touch · seed a `--max-turns 2` conversation end-to-end and confirm the row reaches `status='complete'` · watch a live exchange append over SSE. New tests use `pytest` with an isolated tmp `db/chat.db` — **do not mock SQLite**, the WAL multi-process behavior is the thing under test.

---

## Documentation rules

- **README.md** is the public face — accurate, concrete, Windows-first, matching the existing tone.
- **docs/Roadmap.md** is the source of truth for priorities. Closing an item **moves** the row Open→Done with a `YYYY-MM-DD` `Closed` date. Never delete rows.
- **docs/CHANGELOG.md** is reverse-chronological — add an entry for any user-visible behavior change, schema change, or new doc.
- **docs/Setup/INITIAL_SETUP.md** must change in the same PR as any setup step.
- **Docs are a tree of `README.md` indexes.** Every doc-bearing folder has one listing its immediate children, with a centered footer nav back to its parent: root → `docs/README.md` → each section index → the documents. **Adding a doc means adding its row to that folder's README** — an unlinked doc is unreachable. A new doc-bearing folder gets an index and a row in its parent. Single-document folders (`docs/Setup/`, `docs/Testing/`) are linked directly. Down-links point at a child's index, never past it to a leaf.
- **`skills/` must stay in sync with behavior** — the CLI agents read it at runtime, so stale guidance silently misleads a live debate. On any big update, change the relevant SKILL.md in the same commit:
  - a new/changed MCP tool or its semantics → `agent-chat`
  - `debate.ps1` flags, the persona group model, or how a debate is launched → `start-debate` (plus `agent-chat`'s tool table / `debate-mode`'s persona section if tool or persona behavior shifted)
  - conversation types, seat roles, or the per-seat briefs → the matching `<type>-mode` skill (`podcast-mode`, `collaborate-mode`) **and** `_ROLE_BRIEFS` in `agent_chat_mcp.py`. **Two places, not three** — `New-AgentPrompt` in `spawn-agents.ps1` used to carry a per-role copy and no longer does; it is role-agnostic and points every agent at `get_kickoff()`'s `role_brief`, so adding a seat touches no PowerShell. `_ROLE_BRIEFS` is the single source and reaches CLIs without skills and hand-seeded runs without a launch prompt.
  - `publish_debate.py` flags, the export format, or the library folder layout → `publish-debate`
  - Don't reference persona slugs or group names that can be deleted. New skills auto-wire via `scripts/setup/setup-skill-links.ps1`, **but `.gitignore` needs a line** — the `.claude/skills/<name>/` exclusions are listed by name, and without one the junction gets committed as duplicate files full of this machine's paths.

Don't create new top-level docs unless asked; new project docs go under `docs/`.

---

## Git workflow

- Feature branches off `main`. Confirm the current branch with `git status` — it's often `mike_desktop`.
- **Commit style:** short imperative subject, body when needed, plain English. Conventional commits are **not** used here.
- **Never commit:** `.venv/`, `db/*.db*`, `.env*`, `__pycache__/`, `.mcp.json`, local `.claude/` state (`settings.local.json`, `local-vs-public.md`, `images/`, `rules/`, `temp/`), or any nested per-CLI `.claude/`. Tracked despite the mostly-ignored tree: this file, plus `.claude/agents/` + `.claude/commands/` + `.claude/skills/` — except the skill entries `setup-skill-links.ps1` junctions from `skills/`, since Windows would commit those as files full of this machine's `D:` paths.
- **PRs:** small and focused, one Roadmap item each, referencing the Roadmap row. **Don't push to `main` directly** unless it's a doc-only typo fix or you're told to.

### Deploying to Fly after a push

The hosted mirror (`agent-chat-mikesailab` → `agent-chat.mikesailab.com`) runs **only the web UI**. Deploy after a push **iff** it touched `src/web_ui.py` or `src/web/`, `requirements.txt`, `fly.toml`/`Dockerfile`, or `images/AgentChat-Avatars/`:

```powershell
fly deploy --app agent-chat-mikesailab
```

Then confirm with `fly status --app agent-chat-mikesailab` (the machine's `LAST UPDATED` should be this deploy). A deploy can fail transiently — retry once before investigating.

**Ordering matters when a synced column is added:** `/api/ingest` names every synced column in its `INSERT`, so a sidecar sending a new column fails against a mirror that doesn't have it yet. Deploy the web app **before** restarting the sidecar.

**Skip the deploy** for pushes touching only docs, `scripts/`, the MCP server, `start_conversation.py`, `agents/`, or persona/DB data — none of that runs on Fly, and data reaches the mirror through the sidecar sync (`scripts/db_sync.py`), never a deploy. Deploying is outward-facing — confirm with the user first unless they've said to proceed.

---

## Security & operational notes

- **No auth.** Anything running the server with `--agent-id X` *is* X. Fine for local CLIs you control. Don't propose network exposure without an auth design first (the Roadmap's "shareable read-only links" item is local-LAN only by design).
- **No secrets in repo.** The root `.mcp.json` uses `${...}` env-var substitution for tokens — preserve that pattern, never inline a key.

---

## Where everything is

| Read this | For |
|:---|:---|
| [`docs/Roadmap.md`](docs/Roadmap.md) | **Priorities — read first.** Carefully maintained; closing an item *moves* the row. |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | What already changed. |
| [`README.md`](README.md) · [`docs/repo-layout.md`](docs/repo-layout.md) | End-to-end tour; the full annotated tree. |
| [`docs/App/how-it-works.md`](docs/App/how-it-works.md) | The WAL bus, turn enforcement, the long-poll, the no-auth model. |
| [`docs/App/web-ui.md`](docs/App/web-ui.md) | Routes, homepage design system, SSE, topic logos, avatars, export, auth, demo strip. |
| [`docs/App/export-format.md`](docs/App/export-format.md) | The export-bundle **contract** — read before touching `orchestrator/export.py`. |
| [`docs/App/cli-setup.md`](docs/App/cli-setup.md) | Which CLIs a machine has, the declaration file, and why one CLI is enough. |
| [`docs/App/personas.md`](docs/App/personas.md) · [`battleground.md`](docs/App/battleground.md) · [`kickoff-prompts.md`](docs/App/kickoff-prompts.md) | Persona registry; arenas + the draft gate; `get_kickoff` templates. |
| [`docs/Guides/`](docs/Guides/) | One front door per format — [debate](docs/Guides/debate.md), [podcast](docs/Guides/podcast.md), [online forums](docs/Guides/online-forums.md) — each linking down to the launchers ([manual seed](docs/Guides/start-new-chat.md) is the daily driver). Keep `ConvType.guide_url` pointed at the three. |
| [`docs/CLI-MCP-Config/README.md`](docs/CLI-MCP-Config/README.md) | MCP registration per CLI (project vs global) — canonical. |
| [`docs/Local/`](docs/Local/) | **Operator-only, gitignored:** the Fly deploy, the sidecar sync, logon autostart. |
| `.claude/local-vs-public.md` | How the publish-to-library pipeline differs on this machine. Gitignored. |

**Two skill trees — don't confuse them.** [`skills/`](skills/) is read by the **participating CLI agents at runtime** (junctioned into each CLI's config dir by `scripts/setup/setup-skill-links.ps1`): `agent-chat` = the participation loop · `debate-mode` · `podcast-mode` · `collaborate-mode` · `battleground` · `start-debate` · `publish-debate`. [`.claude/skills/`](.claude/skills/) is read by **Claude Code working on this repo**: `agent-chat-schema`, `agent-chat-export-contract`, `agent-chat-web-ui`, `agent-chat-add-cli` — plus `.claude/agents/agent-chat-docs-sync` (audits a diff for doc drift) and `.claude/commands/` (`/smoke-test`, `/deploy-fly`, `/close-roadmap-item`).

For ambiguous tasks, ask one clarifying question rather than guess — the codebase is small enough that a wrong assumption costs a six-file edit.
