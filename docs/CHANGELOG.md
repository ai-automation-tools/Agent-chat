# Changelog

All notable changes to this repository. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-05-05

### Added — Public deploy: live web UI on Fly.io + docs site on Vercel (hybrid per HOSTING.md §6.3)
- Final layout decided after first-pass scope mismatch:
  - `agent-chat.mikesailab.com` → Fly.io, runs `src/web_ui.py` behind HTTP basic auth
  - `docs.agent-chat.mikesailab.com` → Vercel, static Astro Starlight docs built from `README.md` + `docs/*.md`
- **Fly.io live app:**
  - `Dockerfile` (multi-stage Python 3.13-slim), `fly.toml` (app `agent-chat-mikesailab`, region `iad`, 256 MB shared-cpu-1x VM, 1 GB persistent volume mounted at `/data`, auto-stop when idle), `.dockerignore` (default-deny: ships only `requirements.txt` + `src/`).
  - `src/web_ui.py` changes — all backwards-compatible with local dev:
    1. **Auto-init** — new `db_init()` runs `CREATE TABLE IF NOT EXISTS` on every boot. Fly's empty volume no longer 500s the first request. SCHEMA duplicated from `agent_chat_mcp.py` with a sync-required note.
    2. **HTTP Basic Auth middleware** — `BasicAuthMiddleware` activated only when `AGENT_CHAT_BASIC_AUTH_PASSWORD` is set. Username defaults to `admin`, override via `AGENT_CHAT_BASIC_AUTH_USER`. Constant-time comparison via `secrets.compare_digest`. Sends `WWW-Authenticate: Basic realm="agent_chat"` so browsers show the login dialog.
    3. **Env-var fallbacks** — `--db-path`, `--host`, `--port` default to `$AGENT_CHAT_DB`, `$HOST`, `$PORT` so the same entrypoint runs locally (no env) and on Fly (envs from `fly.toml`).
  - Smoke-tested locally: import clean, auth challenges 401 with WWW-Authenticate, correct creds 200, wrong creds 401, empty-DB auto-init creates the file.
  - Step-by-step deploy procedure in `docs/fly-deploy.md`: install flyctl, `fly apps create`, `fly volumes create`, `fly secrets set`, `fly deploy`, `fly certs add`, DNS records.
- **Docs site (Vercel):**
  - New `site/` workspace: Astro 6 + Starlight 0.38, scaffolded.
  - Source of truth stays at repo root. Build-time sync script (`site/scripts/sync-docs.mjs`) runs as `predev`/`prebuild`, copies six files into `site/src/content/docs/` with Starlight frontmatter injected, leading H1 stripped, cross-doc links rewritten to clean absolute paths.
  - Synced: `README.md → index.md`, `docs/INITIAL_SETUP.md`, `docs/HOSTING.md`, `docs/fly-deploy.md`, `docs/Roadmap.md`, `docs/CHANGELOG.md`, `docs/clis/gemini.md`. Excluded: `docs/agent-conversations/`, `docs/topics/`, `docs/debate-agents/`.
  - Sidebar in `site/astro.config.mjs` with explicit ordering. `site` URL = `https://docs.agent-chat.mikesailab.com` so Pagefind, sitemap, and canonical tags resolve correctly.
  - Verified: install clean, sync correct, dev serves all routes 200, prod build emits 7+ static pages + search index + sitemap. Browser-confirmed nav, anchor TOC, theme switcher.
  - `.gitignore` extended with `site/node_modules/`, `site/dist/`, `site/.astro/`, and `site/src/content/docs/` (synced docs are build artifacts).
- Pending user actions: (1) Fly install + the steps in `docs/fly-deploy.md`; (2) Vercel dashboard import for the docs subdomain (Root Directory `site`, Production Branch `main`); (3) DNS at the `mikesailab.com` provider — Fly cert records for `agent-chat`, plus a `CNAME docs.agent-chat → cname.vercel-dns.com`.

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
