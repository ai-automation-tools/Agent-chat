# Changelog

All notable changes to this repository. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

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
