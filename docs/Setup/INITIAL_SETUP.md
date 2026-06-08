# Initial Setup

This document records the exact steps taken to bootstrap this repository on **2026-05-01**, so the layout and agent wiring can be reproduced or audited.

The end state is:

```
Agent-chat/
├── README.md                     # Project overview, install, usage
├── .gitignore                    # Python + SQLite + env + OS
├── src/                          # MCP server + helper CLIs
│   ├── agent_chat_mcp.py
│   ├── start_conversation.py
│   └── inspect_conversations.py
├── docs/                         # Documentation (this folder)
│   ├── CHANGELOG.md
│   ├── INITIAL_SETUP.md
│   └── .gitkeep
├── db/                           # SQLite DB lives here at runtime
│   └── .gitkeep                  # *.db itself is gitignored
└── agents/                       # One folder per CLI participant
    ├── claude-code_agent1/
    │   ├── claude.md             # Role/instructions for Claude Code
    │   ├── .mcp.json             # Includes agent_chat with --agent-id claude-code
    │   └── .claude/              # Claude Code workspace settings
    └── codex_agent1/
        ├── AGENTS.md             # Role/instructions for Codex CLI
        └── .codex/
            ├── config.toml       # [mcp_servers.agent_chat] with --agent-id codex
            └── skills/
```

## 1. Remote and local git

1. Created a private GitHub repo at `https://github.com/michaelschecht/Agent-chat` (no auto-init — repo was empty so the local could push first).
2. `git init -b main` inside `D:\AI_Agents\Projects\Mikes_AI_Lab\Repos\Live_Apps\Agent-Chat`.
3. Wrote `.gitignore` with Python build artifacts, `.venv/`, `*.db*`, `.env*` (with `.env.example` allow-listed), `.vscode/`, `.idea/`, `.DS_Store`, `Thumbs.db`.
4. Staged files, made initial commit, added `origin`, pushed.

## 2. Repo restructure

Originally everything (the three `.py` files **and** the README) lived in a single mixed-purpose `Docs/` folder. That was cleaned up:

1. Pre-created `src/` (git mv on Windows requires the destination directory to exist).
2. `git mv Docs/agent_chat_mcp.py src/agent_chat_mcp.py` — and the same for the other two scripts.
3. `git mv Docs/README.md README.md` — moved README to repo root.
4. `rmdir Docs` — old folder now empty.
5. `mkdir docs` and `touch docs/.gitkeep` — fresh lowercase folder for actual documentation.
6. Updated README: added a "Repository layout" tree section and prefixed file references in the Files table with `src/`. The MCP config examples and PowerShell commands inside the README were intentionally **not** changed because they describe the user-side install location, not paths inside this repo.
7. Commit `3ea7df1` — "Restructure: src/ for source, docs/ for documentation, README at root".

## 3. Agent wiring

Both agent folders already existed (`agents/CLIs/claude-code_agent1/` and `agents/CLIs/codex_agent1/`) with starter content. They were configured to talk to the same `agent_chat` MCP server backed by the same SQLite database.

### Shared paths

- Server script: `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/src/agent_chat_mcp.py`
- Shared DB: `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/db/chat.db` (auto-created on first run; `db/` exists, `*.db` is gitignored)

### Claude Code agent (`agents/CLIs/claude-code_agent1/`)

Appended a new server entry to the existing `.mcp.json` (which already had 9 unrelated servers — preserved as-is):

```json
"agent_chat": {
  "command": "pwsh",
  "args": [
    "-NoProfile",
    "-File",
    "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
    "claude-code"
  ]
}
```

> [!NOTE]
> This registration shape — pwsh + launcher script — is the current form.
> Earlier in this project the config invoked the venv Python directly and
> passed both the server script and `--db-path` as args. Since 2026-05-12:
> (a) the MCP server defaults `DB_PATH` to `<repo>/db/chat.db` (resolved
> from `src/agent_chat_mcp.py`'s location) and honours `$AGENT_CHAT_DB`,
> and (b) `scripts/run-mcp-server.ps1` resolves the venv interpreter and
> server-script path from `$PSScriptRoot` — so the only hardcoded path in
> the config is the launcher itself.

Replaced the previous `claude.md` (a full-stack developer brief) with a tester role focused on participating in `agent_chat` conversations.

### Codex CLI agent (`agents/CLIs/codex_agent1/`)

The MCP server is registered in the **user-level** Codex config at `C:\Users\mikes\.codex\config.toml` (later in the day — initially we tried a per-folder `.codex/config.toml` here, but Codex's loader doesn't read that location by default, so the in-repo file was removed). The block appended to the global config:

```toml
[mcp_servers.agent_chat]
command = "pwsh"
args = [
  "-NoProfile",
  "-File",
  "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
  "codex",
]
```

> [!NOTE]
> Same launcher + defaulting story as the Claude Code block above — the
> only hardcoded path is `scripts/run-mcp-server.ps1`, and `--db-path`
> is optional (server defaults + `$AGENT_CHAT_DB`).

Side effect: `agent_chat` is now visible to **every** Codex session on this machine, regardless of cwd. That's fine — the server only does work when an agent calls its tools — but it means the venv at `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/.venv/` must keep existing or every Codex session will fail to start that server until the path is fixed.

`agents/CLIs/codex_agent1/.codex/skills/` (skill-creator, skill-installer) is unrelated to MCP wiring and stays.

Replaced `AGENTS.md` (was a generic IT/developer agent brief) with a tester role mirroring the Claude side.

## 4. Verification performed

- `python --version` → `Python 3.12.10`.
- `python -c "import mcp, pydantic"` → both import on the system interpreter; pydantic `2.12.5` (system).
- Imported `agent_chat_mcp.py` directly to confirm it loads without runtime errors.
- Ran `python src/start_conversation.py --help` to confirm the seed script is invokable and reports the expected CLI flags.

The MCP server itself was not invoked end-to-end here — that happens when each CLI launches it as a subprocess. Run a real conversation as the next step.

## 4a. Switched off the system Python (later, same day)

Relying on the system interpreter is fragile — anything else on the machine can change `mcp` or `pydantic` versions out from under us. Replaced with an in-repo venv:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install mcp pydantic
.\.venv\Scripts\python.exe -m pip freeze > requirements.txt
```

Resolved versions captured in `requirements.txt` (committed): `mcp==1.27.0`, `pydantic==2.13.3`, plus their transitive deps. `.venv/` itself is gitignored.

Both agent MCP configs were repointed from `"command": "python"` to the venv interpreter:

```
D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/.venv/Scripts/python.exe
```

Verification: `& .venv\Scripts\python.exe -c "import mcp, pydantic; print(pydantic.VERSION)"` → `2.13.3`.

To rehydrate the venv on a fresh clone:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. Running a conversation (smoke test)

From the repo root:

```powershell
python src/start_conversation.py `
  --topic "Smoke test: confirm the agent_chat MCP server works end to end" `
  --participants claude-code,codex `
  --first claude-code `
  --mode turns `
  --max-turns 5
```
(DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

Then:
- Open Claude Code in `agents/CLIs/claude-code_agent1/` so it picks up the local `.mcp.json`.
- Open Codex CLI in `agents/CLIs/codex_agent1/` (with the config caveat above honoured).
- Ask each agent to call `get_kickoff` once, then drive itself through the `wait_for_turn` → `send_message` loop until the conversation ends. (Pre-`get_kickoff` flow — paste the rendered `prompts/kickoff.md` into each CLI — still works for rows seeded without `--preset`.)
- Optionally tail the conversation in a third terminal:
  ```powershell
  python src/inspect_conversations.py tail 1
  ```
