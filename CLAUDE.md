# Agent-Chat

Project-specific instructions for Claude Code when working in this repo. Defaults below override generic guidance.

---

## What this project is

**Agent-Chat** is a local MCP server that lets two (or more) CLI agents — Claude Code, Codex CLI, Antigravity CLI, Kimi CLI, OpenCode CLI (Gemini CLI is deprecated, kept as a fallback) — hold structured, turn-based conversations with each other. Architecture in one paragraph: each CLI registers the same `agent_chat_mcp.py` server with a different `--agent-id` and the same `--db-path`. They share a single SQLite-WAL file as the message bus. Conversations are seeded out-of-band by `start_conversation.py`. Each agent calls `get_my_turn()` to discover state and `send_message()` to reply. The server enforces turn order, per-agent message caps, and `done` / `blocked` stop signals. There is no daemon, no exposed port, no auth — identity is config-only.

- **Repo root:** `D:\AI_Agents\Projects\Mikes_AI_Lab\Repos\Live_Apps\Agent-Chat\`
- **Remote:** https://github.com/michaelschecht/Agent-chat
- **Default branch:** `main` (current working branch may be `mike_desktop`)
- **Status:** experimental / single-developer

For a full feature tour, read `README.md`. For roadmap and priorities, read `docs/Roadmap.md`. For setup reproduction, read `docs/Setup/INITIAL_SETUP.md`. For the daily-driver operator flow (seed a conversation + paste prompts + watch live), read `docs/Guides/start-new-chat.md`.

---

## Repo layout

```
Agent-Chat/
├── src/
│   ├── agent_chat_mcp.py        # The MCP server (FastMCP + sqlite3)
│   ├── start_conversation.py    # Thin argparse wrapper around orchestrator.seeding
│   ├── inspect_conversations.py # CLI: list / show / tail / stop
│   ├── web_ui.py                # Web-UI ENTRYPOINT: page routes + route table + app assembly + main()
│   ├── web/                     # Web-UI implementation package (split out of web_ui.py 2026-07-10)
│   │   ├── db.py                #   connection + SCHEMA/migrations + all SQL helpers + set_db_path()
│   │   ├── security.py          #   BasicAuth/ReadOnly middleware + _build_middleware()
│   │   ├── assets.py            #   CSS/JS/SVG constants (BASE_CSS, HOME_CSS, _CONV_CSS, _PERSONAS_CSS, favicon)
│   │   ├── avatars.py           #   persona avatar resolution (uploaded row → file art → default silhouette; GET /avatars/{slug})
│   │   ├── topics.py            #   topic→logo classifier (TOPICS keyword/glyph/gradient table)
│   │   ├── render/              #   per-page HTML: common (shell/markdown/icons/demo banner),
│   │   │                        #     home, conversations (two-pane inbox), orchestrate,
│   │   │                        #     personas, setup (which CLIs you have), extension
│   │   └── api/                 #   /api/* handlers: conversations (+SSE stream), sync (ingest/since),
│   │                            #     orchestrate, personas, setup, battleground (extension bridge)
│   └── orchestrator/            # Phase 2a — /orchestrate form + preflight + seed
│       ├── __init__.py
│       ├── seeding.py           #   seed_conversation() — single source of truth
│       ├── availability.py      #   which CLI tools THIS machine has: detect (binary on
│       │                        #     PATH + preflight) vs declare (config/available-clis.json),
│       │                        #     plus plan_seats() round-robin — one CLI is enough
│       ├── conv_types.py        #   conversation-type registry (debate | podcast):
│       │                        #     seat roles, member bounds, the 5-seat cap
│       ├── seats.py             #   agent-id grammar: SUPPORTED_CLIS + numbered
│       │                        #     seats (`codex-2` → agents/CLIs/codex_agent2)
│       ├── preflight.py         #   per-CLI MCP-config checks (no subprocess); SUPPORTED_CLIS
│       ├── personas.py          #   DB-backed persona registry + groups + JSON CLI
│       ├── model_personas.py    #   built-in AI-Models cards (one per CLI) — Cast fallback
│       └── export.py            #   export-bundle renderers — single source of truth
│                                #   (web /export.md + /export.zip AND scripts/publish_debate.py)
├── agents/                      # Local-only — NOT shipped to users; .gitignored
│   ├── CLIs/                    # Tester role docs + per-CLI MCP configs. One folder
│   │                            #   per SEAT: <cli>_agent1 is the bare agent id, and
│   │                            #   <cli>_agent2 backs `<cli>-2` (see orchestrator/
│   │                            #   seats.py; create with scripts/setup/add_agent_seat.py)
│   │   ├── claude-code_agent1/  # claude.md + .mcp.json (Claude Code)
│   │   ├── codex_agent1/        # AGENTS.md (Codex; MCP in global ~/.codex/config.toml)
│   │   ├── antigravity_agent1/  # AGENTS.md + .agents/mcp_config.json (Antigravity)
│   │   ├── kimi_agent1/         # AGENTS.md + .kimi-code/mcp.json (Kimi; auto-loaded from launch dir)
│   │   ├── opencode_agent1/     # AGENTS.md + opencode.json (OpenCode; mcp key + type:local + command array; auto-loaded)
│   │   └── gemini_agent1/       # GEMINI.md + .gemini/settings.json (Gemini — deprecated fallback)
│   └── Debate-Agents/           # SEED CARDS ONLY — personas live in the DB `personas`
│                                #   table (synced to Fly); these *.md folders are a
│                                #   one-time import source for personas.py `import`.
│                                #   Groups are free-form + DB-derived, so this tree's
│                                #   folder names are NOT the live group list — ask
│                                #   personas.discover_groups() / see /personas.
├── db/                          # chat.db lives here at runtime (gitignored)
├── config/                      # available-clis.json — which CLIs this machine has,
│                                #   written by /setup (gitignored; per-machine setup)
├── docs/
│   ├── App/                     # Application docs
│   │   ├── how-it-works.md      # Technical guide (the WAL bus, turn enforcement, long-poll, no-auth model)
│   │   ├── web-ui.md            # Web UI reference (routes, homepage design system, SSE, topic logos, export, auth)
│   │   ├── cli-setup.md         # Which CLIs a machine has (/setup), and why ONE is enough
│   │   ├── export-format.md     # Export-bundle format CONTRACT (web downloads · library archive · theater app)
│   │   ├── personas.md          # Persona registry: groups, cards, AI-Models, MCP tools
│   │   ├── kickoff-prompts.md   # get_kickoff templates / presets
│   │   └── battleground.md      # AgentBattleground: arenas, bridge API, draft gate
│   ├── Local/                   # OPERATOR-ONLY, GITIGNORED — this machine's hosting
│   │   ├── fly-deploy.md        #   Public deploy on Fly.io
│   │   ├── db-sync.md           #   Local→Fly sidecar setup and troubleshooting
│   │   └── autostart.md         #   Logon autostart (Task Scheduler) for the web UI + sidecar
│   ├── Setup/
│   │   └── INITIAL_SETUP.md     # Bootstrap reproduction (git, venv, agent wiring)
│   ├── Guides/                  # The 4 ways to run an agent + a worked example
│   │   ├── start-new-chat.md    # Manual CLI seed — daily-driver recipe (seed + prompts + watch)
│   │   ├── auto-debate.md       # Auto-debate — one-command launcher (scripts/debate.ps1)
│   │   ├── orchestrate-form.md  # Web UI seed form (local /orchestrate)
│   │   ├── battleground.md      # AgentBattleground — argue in a real web debate (extension)
│   │   └── example-conversation-startup.md  # Concrete 3-agent worked example
│   ├── CLI-MCP-Config/          # MCP registration — project + global per CLI
│   │   ├── README.md            #   Consolidated project-vs-global reference (canonical)
│   │   └── Per-CLI/             #   Deep dives: claude.md, codex.md, antigravity.md, gemini.md
│   ├── Testing/                 # Test walkthroughs (e.g. debate-launch-walkthrough.md)
│   ├── Chat-Topics/             # Curated topic-prompt libraries (GPT-authored, Grok-authored)
│   ├── CHANGELOG.md             # Reverse-chronological changelog
│   └── Roadmap.md               # Priority-ordered Open + Done tables
├── prompts/                     # Reusable prompts, all .md (see prompts/README.md)
│   ├── Kickoff/kickoff.md       # Canonical kickoff prompt (default get_kickoff template)
│   ├── Auto-Debate/             # START a debate — paste-ready start-debate operator prompts
│   │                            #   (Head-to-Head / Three-Way / Group-Themed / Custom-Cast / Surprise-Me)
│   ├── Manage-Debates/          # RUN a debate — watch / stop / review-export / personas-topics / troubleshoot
│   └── Battleground/            # FIGHT on the web — join-arena / manage-arenas / troubleshooting
├── skills/                      # Agent Skills — Claude Code + Codex + Antigravity all read SKILL.md
│   ├── agent-chat/              #   Base participation loop (role-agnostic)
│   │   ├── SKILL.md
│   │   └── README.md            #     Per-CLI install paths + verification
│   ├── debate-mode/             #   Layered skill — argue, cite, no hedging
│   │   ├── SKILL.md
│   │   └── README.md
│   ├── podcast-mode/            #   Layered skill — the other conv_type: host asks,
│   │   ├── SKILL.md             #     guests answer, nobody manufactures conflict
│   │   └── README.md
│   ├── battleground/            #   AgentBattleground loop — argue in a captured web thread
│   │   ├── SKILL.md             #     (draft-never-post; persona voice, not identity)
│   │   └── README.md
│   ├── start-debate/            #   Operator skill — launch a debate (scripts/debate.ps1)
│   │   ├── SKILL.md
│   │   └── README.md
│   └── publish-debate/          #   Operator skill — publish a finished debate + cover image
│       ├── SKILL.md             #     into the AI-Automation-Library (via scripts/publish_debate.py)
│       └── README.md
├── extension/                   # AgentBattleground — MV3 extension (browser front)
│   ├── manifest.json            #   Chrome. No static content scripts; per-domain opt-in at capture
│   ├── manifest.firefox.json    #   Gecko: sidebar_action, background scripts, gecko id (min 128)
│   ├── icons/                   #   icon-{16,32,48,128}.png + make_icons.py that generates them
│   ├── README.md                #   Install + operator walkthrough + enhancement list
│   └── src/                     #   background.js (worker/event page) · capture.js (site adapters,
│                                #     injected on demand into every allowed frame) · panel/
│                                #     (capture→preview→cast→handoff→review→insert). panel.js is
│                                #     wiring only; the work is 9 ES modules in panel/lib/
├── logs/                        # Orchestrator preflight-failure audit logs (gitignored)
├── scripts/                     # Operator helpers (PowerShell + Python)
│   ├── db_sync.py               # Local→Fly DB-mirror sidecar
│   ├── publish_debate.py        # Publish a finished debate into the AI-Automation-Library archive
│   ├── run-mcp-server.ps1       # MCP launcher each CLI registers (resolves venv + server)
│   ├── debate.ps1               # One-command auto-debate launcher (topic + personas + spawn)
│   ├── orchestrate-debate.ps1   # Web-form spawn wrapper (POST /api/orchestrate → spawn CLIs for a seeded conv)
│   ├── lib/spawn-agents.ps1     # Shared CLI registry + prompt-file/spawn helpers (debate.ps1 + orchestrate-debate.ps1 dot-source it)
│   ├── start.ps1                # Ensure sidecar is up; forwards args to start_conversation.py
│   ├── startup-app.ps1          # Logon launcher: brings up web UI + sidecar hidden (idempotent)
│   └── setup/                   # One-per-clone setup helpers
│       ├── add_agent_seat.py    #   Give a CLI a 2nd+ seat (clones its MCP config,
│       │                        #     rewrites the agent id); Codex needs CODEX_HOME
│       ├── setup-skill-links.ps1 #   Junction repo-root skills/ into each CLI's config dir (Windows)
│       ├── setup-skill-links.sh  #   Symlink equivalent (POSIX)
│       └── register-startup-task.ps1 # Register the \Agent-Chat\ logon Task Scheduler job (autostart)
├── .venv/                       # Local Python venv (gitignored)
├── requirements.txt             # Pinned deps
├── README.md                    # Public-facing project readme
├── .gitignore
├── .mcp.json                    # Local MCP config for THIS Claude session (gitignored)
├── .claude/                     # Claude Code config. agents/ + commands/ + skills/ are TRACKED;
│   ├── agents/                  #   everything else here (settings.local.json, local-vs-public.md,
│   ├── commands/                #   images/, rules/, temp/) is local-only + gitignored.
│   └── skills/                  #   The skills junctioned from repo skills/ stay ignored —
│                                #   run scripts/setup/setup-skill-links.ps1 after a clone.
└── CLAUDE.md                    # This file (gitignored)
```

When adding a new top-level concern (e.g. `scripts/`, `tests/`), update this tree. When moving files within `docs/` or `agents/`, also update: README's repo-layout tree + project-docs index, the `mikesailab` project memory (paths in `project_mikesailab_design_system.md`), and any cross-references inside the moved files (relative `../` paths shift when depth changes).

---

## Environment

- **OS-primary:** Windows 11. Paths in commits, docs, and configs are Windows absolute paths with forward slashes (`D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/...`). Forward slashes work fine for Python on Windows.
- **Shell:** PowerShell 7+ (pwsh). Use PowerShell syntax for examples in docs/READMEs (backtick line continuation, `$env:VAR`). When suggesting macOS/Linux equivalents, add a `> [!NOTE]` block — do not silently swap.
- **Python:** 3.10+. Project uses a local venv at `.venv/`. Always invoke the venv interpreter explicitly (`.\.venv\Scripts\python.exe ...`) rather than relying on activation state — the README, configs, and Roadmap all assume this convention.
- **Package manager:** `pip` against `requirements.txt`. Deps are **pinned exactly** (see file). When upgrading, regenerate the full pin set via `pip freeze`, do not hand-edit single lines.
- **Git user:** Mike (`mikeschecht@gmail.com`).

### Path portability

The `scripts/run-mcp-server.ps1` launcher (and its `.sh` twin) now resolves the venv interpreter and `src/agent_chat_mcp.py` relative to its own location, and the DB defaults to `<repo>/db/chat.db` (override via `$AGENT_CHAT_DB`). So the **only** hardcoded absolute path left in each MCP config is the launcher path itself. Hardcoded absolute paths to `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/` still exist in: README install/config blocks, the per-CLI MCP configs (`agents/CLIs/<cli>_agent1/.mcp.json` / `.agents/mcp_config.json` / `.gemini/settings.json`), the global `~/.codex/config.toml` (outside the repo), `docs/Setup/INITIAL_SETUP.md`, and `docs/CHANGELOG.md`. Cloning to a different drive/folder = update the launcher path string in each config. Do not introduce **new** hardcoded paths; if you must touch existing ones, change all sites in one PR.

---

## Working with the code

### Python conventions

- Type hints on all function signatures. Use `from __future__ import annotations` when forward refs are needed.
- Use `pathlib.Path` for filesystem work, not `os.path`.
- Use `logging` (or `sys.stderr` writes for MCP servers — stdout is reserved for the MCP protocol). Never `print()` to stdout in `src/agent_chat_mcp.py` — it corrupts the JSON-RPC stream.
- Pydantic v2 (`pydantic==2.13.3`) is already a dep. Use `BaseModel` for tool input/output shapes; the FastMCP server relies on it.
- `argparse` is the convention for CLI entrypoints (`start_conversation.py`, `inspect_conversations.py`, `web_ui.py`). Match the existing flag style: `--db-path`, `--agent-id`, `--topic`, etc.

### SQLite layer

> [!TIP]
> The `agent-chat-schema` skill (`.claude/skills/agent-chat-schema/`) carries this checklist plus the current table shapes — it auto-loads when you touch a schema file.

- The DB is the **contract** between processes. The canonical schema is the `SCHEMA` constant in `agent_chat_mcp.py`, but it is **copy-pasted across four declaration sites** — mirror all of them in the same change:

  | File | Constant | Scope |
  |:---|:---|:---|
  | `src/agent_chat_mcp.py` | `SCHEMA` | canonical — all 3 tables + 2 indexes |
  | `src/web/db.py` | `SCHEMA` | full mirror |
  | `src/orchestrator/seeding.py` | `SCHEMA` | full mirror |
  | `src/orchestrator/personas.py` | `_PERSONA_DDL` | `personas` table only |

  `_MIGRATIONS` — a tuple of `(table, column, ddl)` triples applied by `db_init()`, gated on `PRAGMA table_info` so it stays idempotent — is duplicated in the first three.

- Any change to schema requires:
  1. Bumping the schema cleanly (additive columns are safe; renames/drops require a migration plan).
  2. Mirroring every declaration site above, plus a `_MIGRATIONS` row per copy so existing `db/chat.db` files upgrade in place.
  3. Updating every **reader** of a changed column — `inspect_conversations.py`, the `web/db.py` helpers, `orchestrator/export.py`, the SSE payload, and the `/api/ingest` + `/api/since` sync path (a column the sidecar doesn't carry never reaches the Fly mirror). Note `start_conversation.py` and `inspect_conversations.py` declare **no** schema — the former delegates to `orchestrator.seeding`, the latter only runs SELECT/UPDATE.
  4. A note in `docs/CHANGELOG.md`.
- WAL mode is mandatory (`PRAGMA journal_mode=WAL`). Do not change it — two processes write the same file.
- Connections use `isolation_level=None` and `timeout=10.0`. Preserve this when adding new code paths: the write paths use explicit `BEGIN`/`COMMIT`/`ROLLBACK`, which is only correct in autocommit mode.
- Parameterize all queries. No string-concatenated SQL.
- **`web.db.set_db_path()` also exports `$AGENT_CHAT_DB`.** `orchestrator.personas` (and `model_personas`) resolve their own path per call from that env var and never see `web.db.DB_PATH`, so without the export a custom `--db-path` reads conversations from one DB and personas from another.

### MCP server (`agent_chat_mcp.py`)

- Use FastMCP decorators (`@mcp.tool()`) — the existing tools `get_my_turn`, `send_message`, `get_conversation_status` are the reference shape.
- Tool return types are Pydantic models. Match the existing `model_config = ConfigDict(...)` patterns when adding new ones.
- The two **module-level globals** `AGENT_ID` and `DB_PATH` are populated in `main()` before `mcp.run()`. Do not read them at import time.
- New tools should be **idempotent and read-mostly**, mirroring `get_my_turn`. Mutations belong in `send_message` or new explicitly-named write tools.

### Web UI (`web_ui.py` + the `src/web/` package)

- Starlette app; no framework beyond what's already in `requirements.txt` (`starlette`, `sse-starlette`, `uvicorn`). Since 2026-07-10 it's a package: `web_ui.py` is ONLY the entrypoint (page routes, route table, app assembly, `main()`); implementation lives in `web/db.py` (SQL + `set_db_path()`), `web/security.py` (middleware), `web/assets.py` (CSS/JS constants), `web/render/*` (per-page HTML), `web/api/*` (`/api/*` handlers). Keep new code in the matching module; keep route paths defined only in `web_ui.py`; keep the `web_ui` re-exports (`ReadOnlyMiddleware`, `db_init`, …) working — the tests import them.
- Binds to `127.0.0.1:8765` — local only, no auth. **Do not** add a `0.0.0.0` bind option without an auth story; the README explicitly warns this server is not network-safe.
- No longer strictly read-only. Write endpoints: `POST /api/conversations/{cid}/stop`, `POST /api/conversations/{cid}/delete`, `POST /api/orchestrate`, the persona endpoints (`POST /api/personas`, `/api/personas/import`, `/api/personas/bulk-delete`, `/api/personas/{slug}`, `/api/personas/{slug}/delete`), and `POST /api/ingest` (the sidecar sync endpoint). Each conversation mutation must mirror the SQL the CLI inspector or `orchestrator.seeding` runs; do not duplicate seeding logic into the route handler. Persona writes go through `orchestrator.personas` (`create_persona`/`update_persona`/`delete_persona`) — don't write card files from the route handler directly. On the hosted mirror `ReadOnlyMiddleware` + `AGENT_CHAT_PUBLIC_READONLY` 403s browser mutations, so a new write route is covered automatically — add a case to `tests/test_web_readonly.py`.
- **Personas are DB-backed, and persona management is NOT local-only.** They live in the synced `personas` table, so `/personas` and its write endpoints work on the hosted mirror too (subject to `ReadOnlyMiddleware`). `personas.root_exists()` no longer checks the `agents/Debate-Agents/` card tree — it returns True whenever the DB is reachable, and the failure it guards is "database unreachable" (`404` + a `persona storage unavailable` notice), not "no local cards". The card tree is now only a **one-time seed source** for `import_personas_from_files()`.
- SSE channel pattern: `event: message` per row, `event: turn` when `current_turn` changes (whose-turn badge), `event: complete` on close. New live-update features should reuse this channel rather than open a second one.
- **The nav rail is two tables, not one.** `_NAV_ITEMS` = pages this server renders; `_RESOURCE_NAV_ITEMS` = reference + third-party destinations, rendered under a separator and a `Resources` heading. A new page goes in the first; a link that leaves for the library site goes in the second. Don't collapse them back into one column — that's what made "Theater" read as a page of this app.
- **The hosted demo strip and `ReadOnlyMiddleware` must key off the same flag.** `demo_banner()` (rendered by `_layout()` *and* the homepage template) gates on `_is_public_readonly()`, so a page promising "read-only" and a server allowing writes can't come apart. Don't make it dismissible, and don't gate it on anything else.
- **Never assume the operator has every CLI.** `/orchestrate` and the homepage read `orchestrator.availability`, not `preflight.discover_seats()` directly — offering six tools to someone who owns one is the bug that page exists to fix. Availability is **advisory**: `POST /api/orchestrate` still gates on preflight, so a stale declaration can't seed an unrunnable conversation. Detection names must stay in sync with `$Clis[...].Exe` in `scripts/lib/spawn-agents.ps1` (pinned by `tests/test_availability.py`). See `docs/App/cli-setup.md`.
- `/orchestrate` form handler must go through `orchestrator.seeding.seed_conversation()` — that's the single source of truth, also called by `start_conversation.py`. Don't reimplement seeding SQL in the web layer directly.
- **Export rendering lives in `orchestrator/export.py`, and its output format is a contract.** The `/export.md` + `/export.zip` endpoints and `scripts/publish_debate.py` all render through that module — don't reimplement bundle rendering in `web_ui.py`. Three external consumers parse the format (the AI-Automation-Library `Agent-Debates/` archive, the library site walker, and the debate-chat-theater `build.mjs`): heading shapes, meta-table labels, `## sender — timestamp` message headings, persona filenames, and the 25-char `topic_slug` are effectively **frozen** — see `docs/App/export-format.md` before changing any of them, and update the consumers in the same change.
- **Conversation topic logos** are classified at render time by `web/topics.py` (a `TOPICS` keyword/glyph/gradient table) — no schema, no backfill, so re-wording the table re-skins the whole archive. Ties go to the earlier entry, which is why `ai` sits near the bottom. See `docs/App/web-ui.md` → *Topic logos*.
- **Persona avatars** are resolved at render time by `web/avatars.py` from the persona **slug**, in three steps: an **uploaded image on the persona's DB row** (`avatar_mime` + base64 `avatar_data`), else `images/AgentChat-Avatars/<slug>-avatar.png` (photos) / `<slug>-avatar.svg` (the CLI agents' original brand-glyph marks), else a default silhouette (`default-avatar.svg`). Served at `GET /avatars/{slug}`; rendered wherever a specific persona appears (personas rows, cast panel, message headers incl. live SSE via `AGENT_VISUALS.slug`, homepage roster/featured).
  - **Uploads belong in the DB, never on disk.** The `personas` table is synced by the sidecar, so an upload reaches the mirror with **no redeploy** and survives the next one; a file written into the image's tree would do neither. Don't "simplify" this by writing uploads into `images/AgentChat-Avatars/`.
  - **Uploads are raster-only and typed by their magic bytes** (`normalize_avatar`), never by the declared MIME. **SVG is refused** — it's script-capable markup served from the app's own origin — and stored bytes go out with `nosniff` + a `default-src 'none'` CSP. Keep both.
  - **An avatar must survive an edit**: `update_persona()` touches it only when passed `avatar=`/`clear_avatar=`, and both import paths carry the existing image across an overwrite.
  - `list_personas()` selects an explicit column list that **excludes `avatar_data`** — restoring `SELECT *` would haul every image through every roster render.
  - **Shipped file art** still needs a commit + Fly redeploy (the folder is COPYed into the image — `Dockerfile` + scoped `.dockerignore`). **No-persona conversations** resolve the avatar from the raw agent id, which for a CLI *is* its brand-avatar slug, so those runs show tool marks not initials. See `docs/App/web-ui.md` → *Persona avatars* and `docs/App/personas.md` → *Avatars*.

### AgentBattleground (`extension/` + `web/api/battleground.py` + the arena MCP tools)

- **The invariant: it drafts, it never posts.** An agent's reply is written as a `pending` draft; only an explicit operator verdict moves it; approving *types text into the page's existing composer* and stops. Nothing in the server or the extension may submit to a website, open a composer, or click a site's post button — that's the line that separates this from astroturfing. Any change that would let a draft reach a page without a human action needs the user's explicit sign-off first. The same reasoning killed a **Launch selected CLI** button: `/roster` returns a `launch` map the panel renders as a *copyable string*, and nothing local spawns a process on an HTTP request.
- **The panel is a package.** `src/panel/panel.js` is wiring + init; the work is nine ES modules in `src/panel/lib/`. They form import cycles (`arena → view → drafts → arena`), so they share one mutable `state` object rather than each exporting its own `let`, and every export crossing a cycle must be a hoisted `function` declaration — a `const fn = () => …` is `undefined` when a partially-evaluated module calls into it. Composer insertion lives in `lib/compose.js` and nowhere else.
- **Nothing under `extension/` is covered by a test that runs in a browser.** `tests/test_battleground.py` reaches the bridge and the MCP loop; permissions, `chrome.scripting`, the panel surfaces and composer insertion are unexercised. Say so when reporting extension work, and don't describe the panel as verified.
- **The house rules go in-band.** `_ARENA_RULES` in `agent_chat_mcp.py` ships with every `get_arena` payload so behavior doesn't depend on the `battleground` skill being installed on that CLI. Keep it and `skills/battleground/SKILL.md` in sync — especially the persona-voice-not-identity rule.
- **The two tables are local-only.** `battleground_arenas` / `battleground_drafts` are deliberately absent from `_CONV_COLUMNS` / `_MSG_COLUMNS` / `_PERSONA_COLUMNS` and from `scripts/db_sync.py`, so captured third-party page content never reaches the Fly mirror. Don't "fix" that by adding them to the sync.
- **Persona bodies are snapshotted** onto the arena row at capture time, not looked up per read — editing a card must not retroactively change what a running arena's agent was told to be.
- **Re-capture merges on post `id`.** That's the contract a site adapter in `extension/src/capture.js` exists to satisfy: find posts, give each a stable id (the site's own comment id wherever possible). A new adapter that invents per-capture ids silently duplicates the thread on every refresh. Ids captured from a third-party comment iframe are namespaced (`disqus:501`) so a frame and its host page can't collide.
- **A new adapter is two edits, not one.** Its label must also land in `KNOWN_SITES` (`web/api/battleground.py`) or the bridge silently coerces the arena to `generic` — the capture still works, so nothing fails, it's just mislabelled everywhere it's shown. `tests/test_battleground.py` pins the two lists together.
- **Never let the extension acquire access without a click.** Host permissions are per-origin, requested from a user gesture (a comment iframe is a *separate* origin and gets its own button). The auto re-capture timer therefore checks `permissions.contains` and skips — it must never call `permissions.request`. Related Gecko rule: Firefox discards the user gesture across an `await`, so click handlers in `panel.js` start the permission request **before** their first await.
- **CORS stays narrow.** `ExtensionCorsMiddleware` echoes only `chrome-extension://` origins, only under `/api/battleground/`. Never widen it to `*` or to other paths — a localhost server with wildcard CORS is readable by every page the operator visits.
- Full reference: [`docs/App/battleground.md`](docs/App/battleground.md).

### Personas (`orchestrator/personas.py` + `model_personas.py`)

- **Groups are free-form.** `discover_groups()` reads `SELECT DISTINCT "group"` from the DB; a group exists once a row lands in it. `PREFERRED_GROUPS` is only a **sort hint**, not a filter, and `DEFAULT_DEBATER_GROUP` ("Unique-Personas") currently holds **zero rows** — the roster was reorganised into per-category groups (Celebrities, Scientists, …). That's why the random-cast paths all fall through to "every persona".
- **Random casting must go through `list_debater_personas()`**, never `list_personas(None)`. It excludes `RESERVED_GROUPS` — the `AI-Models` reference cards — so a random debate never fields "Claude Code" against Gordon Ramsay. Callers: `POST /api/orchestrate` (debater + moderator draws) and `debate.ps1` via the personas CLI's `list --castable`. An explicit `--group` / `-Group` is always honoured as asked.
- **`AI-Models` is a reserved group**: one card per `preflight.SUPPORTED_CLIS` entry, **slugged with the agent id**, defined in `orchestrator/model_personas.py` and created on web-UI boot by `ensure_model_personas()` (create-if-missing, so operator edits on `/personas` survive a restart). They back the Cast panel for conversations with no recorded `participant_personas` — `_effective_cast()` in `web/render/conversations.py` merges them in and labels the rows `AI model`. Recorded personas always win.
- Card bodies for AI-Models are **original descriptions**, deliberately not copies of any vendor's system prompt.

---

## Testing & validation

A suite exists under `tests/` — every file is pytest-compatible **and** standalone-runnable (`.\.venv\Scripts\python.exe tests\test_web_readonly.py`), so no test dep is pinned. Run them all after touching the web layer; `/smoke-test` (`.claude/commands/`) does the whole checklist below.

| Suite | Covers |
|:---|:---|
| `tests/test_web_readonly.py` | auth + read-only middleware, orchestrate guard |
| `tests/test_inspect_tail.py` | `inspect_conversations tail` completion guard |
| `tests/test_topics.py` | topic→logo classification + tie-breaks |
| `tests/test_model_personas.py` | AI-Models cards, the reserved-group casting guard, Cast fallback |
| `tests/test_battleground.py` | Arena bridge, capture scrubbing + merge, reply target, `/healthz`, verdict gate, CORS, schema parity, launch-map ↔ `spawn-agents.ps1` parity, MCP loop |
| `tests/test_persona_avatars.py` | Avatar validation (magic bytes, no SVG), resolution order, import card↔image pairing, edit-preserves-art, persona column parity `web/db.py` ↔ `scripts/db_sync.py` |
| `tests/test_seats.py` | Agent-id grammar (`codex-2`), per-seat preflight config paths, Codex `CODEX_HOME`, brand-avatar + AI-Models-card fallback, parity across `preflight._CHECKS` ↔ `SUPPORTED_CLIS` ↔ `add_agent_seat.SHAPES` ↔ `Resolve-AgentSeat` |
| `tests/test_availability.py` | CLI detect-vs-declare, the three declaration states, `plan_seats` round-robin, `/setup` + its API, `/orchestrate` filtering, the demo strip, the two-group rail, `CLI_BINARIES` ↔ `spawn-agents.ps1` parity |
| `tests/test_conv_types.py` | Seat rules (`conv_type` + `participant_roles`), the `conv_type` backfill on a pre-column DB, schema-mirror parity across the three `SCHEMA`/`_MIGRATIONS` copies, conversation column parity `web/db.py` ↔ `scripts/db_sync.py`, export Type/Role rows |

Beyond that, validation is manual:

1. **Smoke test the server imports cleanly:** `.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import agent_chat_mcp"`.
2. **JSON validity** of any `.mcp.json` you touch: `.\.venv\Scripts\python.exe -m json.tool path\to\.mcp.json` (silent = valid).
3. **End-to-end:** seed a `--max-turns 2` conversation, run both CLIs, watch it complete. Confirm the row in `db/chat.db` reaches `status='complete'`.
4. **Web UI live-append:** open `/conversations/<active_id>` while a real exchange runs and confirm new rows arrive over SSE.

When adding a real test suite, use `pytest` with fixtures for an isolated tmp `db/chat.db`. Do not mock SQLite — the WAL multi-process behavior is the thing under test.

---

## Documentation rules

- **README.md** is the public face. Keep it accurate, concrete, and Windows-first. Match the existing tone (badges + emoji section headers + collapsible details for per-CLI configs).
- **docs/Roadmap.md** is the source of truth for priorities. When closing an item, **move** the row from `Open` to `Done` and fill in `Closed` (use today's date in `YYYY-MM-DD`). Don't delete rows.
- **docs/CHANGELOG.md** is reverse-chronological. Add an entry for any user-visible behavior change, schema change, or new doc.
- **docs/Setup/INITIAL_SETUP.md** is the bootstrap reproduction. If a setup step changes, update this file in the same PR.
- **`skills/` must stay in sync with behavior.** The Agent Skills under `skills/` (`agent-chat` = participation loop, `debate-mode` = argue well, `podcast-mode` = host/guest a podcast, `start-debate` = launch a debate via `scripts/debate.ps1`, `publish-debate` = publish a finished debate + cover to the AI-Automation-Library via `scripts/publish_debate.py`) are read by the CLI agents at runtime — stale guidance silently misleads them. **On any big update, update the relevant SKILL.md in the same change:** a new/changed MCP tool or its semantics → `agent-chat`; a change to `debate.ps1` flags, the persona group model, or how a debate is launched/seeded → `start-debate` (and `agent-chat`'s tool table / `debate-mode`'s persona section if persona/tool behavior shifts); a change to conversation types, seat roles, or the host/guest briefs → `podcast-mode` **and** `_ROLE_BRIEFS` in `agent_chat_mcp.py` **and** `New-AgentPrompt` in `spawn-agents.ps1` (the same guidance lives in all three so it reaches CLIs without skills and hand-seeded runs without a launch prompt); a change to `publish_debate.py` flags, the export-bundle format, or the library folder layout → `publish-debate`. Don't reference specific persona slugs/group names that can be deleted — keep skill examples generic or clearly "e.g.". New skills auto-wire via `scripts/setup/setup-skill-links.ps1` (it links every `skills/` subfolder), so no script edit is needed to add one — **but `.gitignore` does need a line**: the `.claude/skills/<name>/` exclusions are listed by name, and without a matching entry the junction gets committed as duplicate files full of this machine's paths.

- **Docs are a tree of `README.md` indexes (as of 2026-08-01).** Every folder that
  holds documents has a `README.md` listing its **immediate children** and linking
  back up to its parent in a centered footer nav row. The chain is root →
  `docs/README.md` (the hub) → each section index → the documents. **When you add
  a doc, add its row to that folder's `README.md`** — an unlinked doc is
  unreachable. When you add a doc-bearing *folder*, give it an index and add it to
  its parent. A folder with a single document (`docs/Setup/`, `docs/Testing/`)
  is linked directly, no index. Down-links point at a child's index when it has
  one, never past it to a leaf. `docs/repo-layout.md` marks every index with `★`
  and diagrams the chain.

Do not create new top-level docs unless asked. New project docs go under `docs/`.

---

## Git workflow

- **Branch:** create feature branches from `main`. The current working branch is often `mike_desktop` — confirm with `git status` before assuming.
- **Commit style:** short imperative subject, body when needed. The existing log mixes plain-English subjects (`Add HOSTING.md...`, `Drop bundled agent skills...`) — match that style. Conventional commits are not used here; do not introduce them.
- **Never commit:** `.venv/`, `db/*.db*`, `.env*`, `__pycache__/`, `.mcp.json`, and local `.claude/` state (`settings.local.json`, `local-vs-public.md`, `images/`, `rules/`, `temp/`) — plus any nested per-CLI `.claude/` under `agents/CLIs/`. The `.gitignore` enforces all of these.
- **Tracked, despite living in a mostly-ignored tree:** this file (`CLAUDE.md`), and `.claude/agents/` + `.claude/commands/` + `.claude/skills/`, so a clone gets the same Claude Code tooling. Excluded from that: the `.claude/skills/` entries `setup-skill-links.ps1` junctions from the repo's own `skills/` — they're absolute-path symlinks to already-tracked content, and `core.ignorecase`/`core.symlinks=false` on Windows would commit them as files full of this machine's `D:` paths. Run the setup script after cloning.
- **PRs:** small and focused. One Roadmap item per PR is the norm. Reference the Roadmap row in the PR description.
- **Don't push to main directly** unless the change is a doc-only typo fix or you're explicitly told to.

When the user asks to commit, follow the rules in the harness's general guidance — never amend pushed commits, never `--no-verify`, draft a real message.

### Deploying to Fly after a push

The hosted mirror (`agent-chat-mikesailab` → `agent-chat.mikesailab.com`) runs **only the web UI** (`src/web_ui.py`). After pushing, deploy it to Fly **iff** the push touched a file that affects the hosted app:

- `src/web_ui.py` (or anything under `src/web/`)
- `requirements.txt`
- `fly.toml` or the `Dockerfile`
- `images/AgentChat-Avatars/` (persona avatar PNGs — COPYed into the image; new/changed art needs a redeploy to reach the mirror)

```powershell
fly deploy --app agent-chat-mikesailab
```

Then confirm the new version is healthy (`fly status --app agent-chat-mikesailab` — the machine's `LAST UPDATED` should be the deploy you just ran). A `fly deploy` can fail transiently — retry once before investigating.

**Ordering matters when a synced column is added.** `/api/ingest` names every column of `_CONV_COLUMNS` / `_PERSONA_COLUMNS` in its `INSERT`, so a sidecar that starts sending a new column **fails against a mirror that doesn't have it yet** (the local DB self-migrates on the next boot; the mirror only migrates on deploy). Deploy the web app **before** restarting the sidecar, not after.

**Skip the deploy** for pushes that only touch docs, `scripts/` (incl. `debate.ps1`), the MCP server, `start_conversation.py`, `agents/`, or persona/DB data — none of that runs on Fly. Conversation and persona **data** reaches the mirror through the local→Fly **sidecar sync** (`scripts/db_sync.py`), not a deploy, so a code deploy is never needed just to surface new conversations. Deploying is an outward-facing action — confirm with the user first unless they've told you to proceed.

---

## Security & operational notes

- **No auth.** Anything that runs the server with `--agent-id X` *is* X. Fine for two local CLIs you control. Do not propose features that expose this over a network without an explicit auth design first (the Roadmap "shareable read-only links" item is local-LAN only by design).
- **No secrets in repo.** `.env`, API keys, OAuth tokens — never. The `.mcp.json` at the project root references `${...}` env-var substitutions for tokens; preserve that pattern, never inline a real key.

---

## Where everything is

**Docs** — all under [`docs/`](docs/):

| Read this | For |
|:---|:---|
| [`README.md`](README.md) | How the whole thing works end-to-end. The public face. |
| [`docs/Roadmap.md`](docs/Roadmap.md) | **Priorities — read first.** The user maintains it carefully; closing an item *moves* the row Open→Done. |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | What already changed (reverse-chronological). |
| [`docs/App/how-it-works.md`](docs/App/how-it-works.md) | Technical guide: the SQLite WAL bus, turn enforcement, the long-poll, the no-auth model. The README links here for depth. |
| [`docs/App/web-ui.md`](docs/App/web-ui.md) | Web-UI reference: routes, homepage design system, SSE, topic logos, export, auth, the hosted demo strip. |
| [`docs/App/cli-setup.md`](docs/App/cli-setup.md) | Which CLIs a machine has (`/setup`), the declaration file, and the seat planner that makes **one CLI enough**. |
| [`docs/App/export-format.md`](docs/App/export-format.md) | The export-bundle **contract** — read before touching `orchestrator/export.py`. |
| [`docs/App/personas.md`](docs/App/personas.md) | Persona registry: groups, cards, the AI-Models reserved group, MCP tools. |
| [`docs/App/battleground.md`](docs/App/battleground.md) | AgentBattleground: arenas, the extension bridge API, the draft-review gate. |
| [`docs/App/kickoff-prompts.md`](docs/App/kickoff-prompts.md) | `get_kickoff` templates / presets. |
| [`docs/Local/db-sync.md`](docs/Local/db-sync.md) | Local→Fly sidecar sync setup + troubleshooting. **Gitignored** — operator-only. |
| [`docs/Local/fly-deploy.md`](docs/Local/fly-deploy.md) · [`autostart.md`](docs/Local/autostart.md) | The public Fly deploy; logon autostart for the local UI + sidecar. **Gitignored** — operator-only. |
| [`docs/Setup/INITIAL_SETUP.md`](docs/Setup/INITIAL_SETUP.md) | Bootstrap reproduction (git, venv, agent wiring). |
| [`docs/Guides/`](docs/Guides/) | The 4 ways to run an agent: [manual seed](docs/Guides/start-new-chat.md) (daily driver), [auto-debate](docs/Guides/auto-debate.md), [web form](docs/Guides/orchestrate-form.md), [battleground](docs/Guides/battleground.md) (real web thread), + a [worked example](docs/Guides/example-conversation-startup.md). |
| [`docs/CLI-MCP-Config/README.md`](docs/CLI-MCP-Config/README.md) | MCP registration per CLI (project vs global) — canonical. |
| [`docs/Chat-Topics/`](docs/Chat-Topics/) · [`prompts/`](prompts/) | Topic libraries; reusable operator prompts. |
| `.claude/local-vs-public.md` | How the publish-to-library pipeline differs on this machine vs a public clone (private library repo, nanobanana covers, `--push` targets). Gitignored operator note. |

**Skills** — two separate trees, don't confuse them:

- [`skills/`](skills/) — read by the **participating CLI agents at runtime** (junctioned into each CLI's config dir by `scripts/setup/setup-skill-links.ps1`). [`agent-chat`](skills/agent-chat/SKILL.md) = the participation loop · [`debate-mode`](skills/debate-mode/SKILL.md) = argue well · [`podcast-mode`](skills/podcast-mode/SKILL.md) = host or guest a podcast · [`start-debate`](skills/start-debate/SKILL.md) = launch one · [`publish-debate`](skills/publish-debate/SKILL.md) = publish a finished one. **Stale guidance here silently misleads a live debate** — see the sync rules under *Documentation rules*.
- [`.claude/skills/`](.claude/skills/) — read by **Claude Code working on this repo**. Project-specific: `agent-chat-schema`, `agent-chat-export-contract`, `agent-chat-web-ui`, `agent-chat-add-cli` (onboard a new CLI agent from a repo URL — research → qualify/disqualify → full cross-cutting change). Plus `.claude/agents/agent-chat-docs-sync` (audits a diff for doc drift) and `.claude/commands/` (`/smoke-test`, `/deploy-fly`, `/close-roadmap-item`).

**Other:** for ambiguous tasks, ask one clarifying question rather than guess. The codebase is small enough that the cost of a wrong assumption (a 6-file path edit) is high.
