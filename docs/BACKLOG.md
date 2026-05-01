# Backlog

Short-term enhancements, bug fixes, and tech debt for Agent-chat. Items are listed roughly in priority order within each section. Mark with `[x]` when done, or move to a **Done** section at the bottom.

For longer-term roadmap items (multi-conversation support, three+ agents, `wait_for_turn`, etc.) see the **Possible next steps** section in the root [`README.md`](../README.md).

---

## Enhancements

- [ ] **Make the venv interpreter path portable** *(added 2026-05-01)*
  Both `agents/claude-code_agent1/.mcp.json` and `agents/codex_agent1/.codex/config.toml` hardcode the absolute Windows path `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe`. Anyone cloning this repo to a different drive, machine, or OS has to hand-edit both files. Options to evaluate: (a) a tiny launcher script (`scripts/run-mcp-server.ps1` / `.sh`) that resolves the venv relative to its own location and execs into it, then point `command` at the launcher; (b) env-var substitution (`${REPO_ROOT}` / `${MCP_AGENT_CHAT_PYTHON}`) if both Claude Code and Codex MCP loaders support it; (c) accept the friction and document a one-liner that rewrites the configs after clone.

- [ ] **End-to-end smoke test** *(added 2026-05-01)*
  We've configured both agents but never actually run a conversation between them. Seed a topic with `start_conversation.py`, launch Claude Code from `agents/claude-code_agent1/`, launch Codex from `agents/codex_agent1/`, watch a few turns flow, terminate via `signal="done"`. This is the whole reason the testers exist — confirm the harness works before relying on it for regression catching.

- [ ] **Confirm Codex CLI config loader behavior** *(added 2026-05-01)*
  We assumed Codex picks up `agents/codex_agent1/.codex/config.toml`, but standard behavior is to read `~/.codex/config.toml` from the user home. Verify what the installed Codex version actually does. Likely outcomes: (a) per-folder works → no change needed; (b) requires `CODEX_HOME=...` env var → bake it into a launcher / `.envrc`; (c) requires merging into the global config → document and accept that codex_agent1's local config is reference-only.

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

---

## Tech debt

- [ ] **Repo-path duplication across configs and docs** *(added 2026-05-01)*
  The string `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat` and its `.venv/Scripts/python.exe` / `db/chat.db` / `src/agent_chat_mcp.py` derivatives appear in: README install section, README MCP-config examples, `agents/claude-code_agent1/.mcp.json`, `agents/codex_agent1/.codex/config.toml`, `docs/INITIAL_SETUP.md`, `docs/CHANGELOG.md`. A path change today is a 6-file edit. Related to the "portable venv" item above — solving that probably solves most of this too.

---

## Done

*(nothing yet — move items here with their completion date and the commit hash that closed them)*
