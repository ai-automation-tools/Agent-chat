# Backlog

Short-term enhancements, bug fixes, and tech debt for Agent-chat. Items are listed roughly in priority order within each section. Mark with `[x]` when done, or move to a **Done** section at the bottom.

For longer-term roadmap items (multi-conversation support, three+ agents, `wait_for_turn`, etc.) see the **Possible next steps** section in the root [`README.md`](../README.md).

---

## Enhancements

- [ ] **Make the venv interpreter path portable** *(added 2026-05-01)*
  Both `agents/claude-code_agent1/.mcp.json` and the global Codex `~/.codex/config.toml` hardcode the absolute Windows path `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe`. Anyone cloning this repo to a different drive, machine, or OS has to hand-edit both files. Options to evaluate: (a) a tiny launcher script (`scripts/run-mcp-server.ps1` / `.sh`) that resolves the venv relative to its own location and execs into it, then point `command` at the launcher; (b) env-var substitution (`${REPO_ROOT}` / `${MCP_AGENT_CHAT_PYTHON}`) if both Claude Code and Codex MCP loaders support it; (c) accept the friction and document a one-liner that rewrites the configs after clone.

- [ ] **Lightweight CI workflow** *(added 2026-05-01)*
  GitHub Actions job that on push: creates the venv, runs `pip install -r requirements.txt`, validates `agents/claude-code_agent1/.mcp.json` parses as JSON, validates `agents/codex_agent1/.codex/config.toml` parses as TOML, runs `python -c "import sys; sys.path.insert(0, 'src'); import agent_chat_mcp"`. Cheap, catches the obvious regressions.

- [ ] **Helper scripts under `scripts/`** *(added 2026-05-01)*
  Small PowerShell wrappers so the common DB-path-everywhere invocations stop being copy-paste from the README:
  - `scripts/seed-conversation.ps1` → wraps `start_conversation.py` with the canonical `--db-path` baked in.
  - `scripts/tail-conversation.ps1` → wraps `inspect_conversations.py tail`.
  - `scripts/list-conversations.ps1` → wraps `inspect_conversations.py list`.
  Cross-platform `.sh` siblings if/when that matters.

- [ ] **Convert absolute `--db-path` arg to default-from-env** *(added 2026-05-01)*
  Today every config has to repeat `D:/.../db/chat.db`. If `agent_chat_mcp.py` defaulted `DB_PATH` to `${AGENT_CHAT_DB:-./db/chat.db}` when no `--db-path` is passed, the configs could drop one source of duplication. Trade-off: implicit defaults are easier to misconfigure silently.

---

## Bug fixes / cleanup

- [ ] **`canvas-design` skill is non-functional after font removal** *(added 2026-05-01)*
  In commit `f74b925` we git-rm'd `agents/claude-code_agent1/.claude/skills/canvas-design/canvas-fonts/`, but `SKILL.md` and `LICENSE.txt` are still tracked. The skill references the now-missing fonts and won't render correctly. Decide: delete the rest of `canvas-design/` (cleanest — it's not relevant to a tester repo), or restore the fonts via a one-shot download script that runs post-clone.

- [ ] **`.mcp.json` indentation is inconsistent** *(added 2026-05-01)*
  In `agents/claude-code_agent1/.mcp.json` different server entries are indented at different depths (2 vs 4 vs 6 spaces). Parses fine, but reads as if it was assembled from multiple sources. One pass with a JSON formatter (Prettier or `python -m json.tool`) would normalize it.

- [ ] **`inspect_conversations.py tail` prints "(conversation complete)" before the conversation is actually complete** *(added 2026-05-01)*
  Observed during the smoke test: `tail 1` exited and printed `(conversation complete)` while conversation #1's status was still `active` (`show 1` confirmed `current_turn: claude-code` and a manual `stop 1` was needed afterwards). `tail` appears to be using "no new messages within poll window" as its exit condition rather than checking `conversations.status == 'complete'`. Cosmetic — the conversation itself was fine — but the messaging is misleading. Fix: have `tail` query the conversation status before exiting, and only print `(conversation complete)` when `status='complete'`; otherwise stay polling or print something like `(no activity — Ctrl-C to exit)`.

---

## Tech debt

- [ ] **Repo-path duplication across configs and docs** *(added 2026-05-01)*
  The string `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat` and its `.venv/Scripts/python.exe` / `db/chat.db` / `src/agent_chat_mcp.py` derivatives still appear in: README install section, README MCP-config examples, `agents/claude-code_agent1/.mcp.json`, **`C:\Users\mikes\.codex\config.toml`** (global Codex config — outside the repo), `docs/INITIAL_SETUP.md`, `docs/CHANGELOG.md`. A path change today is a 6-file edit. Related to the "portable venv" item above — solving that probably solves most of this too.
  *(Updated: `agents/codex_agent1/.codex/config.toml` was deleted in favor of the global Codex config; net duplication count unchanged but one file is now outside the repo.)*

---

## Done

- [x] **End-to-end smoke test** *(added 2026-05-01, closed 2026-05-01)*
  Conversation #1 ran cleanly: `claude-code` opened with a turn-rotation validation prompt at 21:11 UTC, `codex` replied with confirmation of `status=your_turn`, `turns_remaining=5`, history length=1, and `current_turn` flipped back to `claude-code` afterwards. Manually stopped via `inspect_conversations.py stop 1` before either agent hit max-turns or sent `signal="done"` — those code paths therefore remain unexercised but the core happy path (turn rotation, persistence across processes, both CLIs loading the MCP server) is proven.

- [x] **Confirm Codex CLI config loader behavior** *(added 2026-05-01, closed 2026-05-01)*
  Resolved empirically: Codex's default loader only reads the user-level `~/.codex/config.toml` and ignores per-folder `.codex/config.toml`. Acted on this by registering `[mcp_servers.agent_chat]` in `C:\Users\mikes\.codex\config.toml` and deleting the redundant in-repo `agents/codex_agent1/.codex/config.toml` (commit `29ee1bc`).

- [x] **Local web UI for live chat viewing — v1** *(added 2026-05-01, closed 2026-05-01)*
  Built `src/web_ui.py` as a single-file Starlette app using existing transitive deps (`starlette`, `uvicorn`, `sse-starlette` come in via `mcp`). Routes: `/` (conversations table), `/conversations/<id>` (transcript + live SSE auto-update for active conversations), `/api/conversations[/<id>]` (JSON), `/api/conversations/<id>/stream` (SSE). Binds to `127.0.0.1:8765` by default. Smoke-tested against `db/chat.db` containing conversation #1: list view, detail view, JSON API, and SSE stream all return expected output. Out of v1 (potential follow-ups, file separately if wanted): human-in-the-loop posting, seed-new-conversation form, force-stop button, auth, multi-user.
