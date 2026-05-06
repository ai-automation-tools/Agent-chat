# Changelog

All notable changes to this repository. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-05-06

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
