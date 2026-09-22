# Initial Setup

Two parts: a **[Fresh-clone setup](#fresh-clone-setup)** path (what to run today, the same steps as the [README](../../README.md#-getting-started)), and the original **[historical bootstrap record](#historical-bootstrap-record-2026-05-01)** of how the repo was first created (kept for audit).

---

## Fresh-clone setup

Clone → watch a debate, in seven steps, with the reproduction detail behind each. Windows / PowerShell shown; macOS-Linux notes inline.

### 1 · Clone & install

```powershell
git clone https://github.com/ai-automation-tools/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- Deps are pinned exactly in `requirements.txt` (`mcp`, `pydantic`, `starlette`, `markdown-it-py`, …). Always invoke the venv interpreter explicitly rather than relying on activation.
- Requires `pwsh` (PowerShell 7+) on PATH for the launcher (`winget install Microsoft.PowerShell`). macOS/Linux: use `./.venv/bin/python` and the `.sh` launcher form throughout.
- **Wire the shared Agent Skills once per clone** — links repo-root `skills/` into each CLI's (gitignored) config dir so every CLI reads the same `SKILL.md`:
  ```powershell
  .\scripts\setup\setup-skill-links.ps1   # Windows junctions (POSIX: scripts/setup/setup-skill-links.sh)
  ```

### 2 · Register the MCP server with each CLI

Every CLI loads the **same** launcher (`scripts/run-mcp-server.ps1`) under a different `--agent-id` — the only value that differs. The launcher resolves the venv interpreter and server script relative to itself, so the launcher path is the only hardcoded string per config; `--db-path` is optional (defaults to `<repo>/db/chat.db`, `$AGENT_CHAT_DB` overrides). Per-CLI config location + copy-paste snippet (project **or** global scope): **[docs/CLI-MCP-Config/](../CLI-MCP-Config/README.md)**.

**Optional — a second seat on the same tool.** Two participants can run on one CLI (useful for a podcast, where a host plus four guests would otherwise use every tool you have). Each extra seat is another config folder with its own agent id:

```powershell
.\.venv\Scripts\python.exe scripts\setup\add_agent_seat.py --cli claude-code --seat 2
```

That writes `agents/CLIs/claude-code_agent2/` and the participant id becomes `claude-code-2`. Seats run to `-5`. It works whether Claude Code is registered in the seat-1 folder or at user scope with `claude mcp add --scope user` — in the second case the new seat's `.mcp.json` is built from the `agent_chat` entry in `~/.claude.json`. **Codex needs one extra step** — its seats relocate `CODEX_HOME`, so run `codex login` once against the new folder; the script prints the exact command.

> [!TIP]
> You can skip this step entirely. `/orchestrate` creates the seat when you point a second chair at a tool you already have, so the shortest path to two agents on one CLI is the launch form.

### 3 · Start the local web app

It's the live viewer **and** where the `/orchestrate` seed form lives — start it first:

```powershell
.\.venv\Scripts\python.exe src\web_ui.py   # → http://127.0.0.1:8765/
```

### 4 · Tell it which CLIs you have

Open **`http://127.0.0.1:8765/settings`** — the **CLI tools** tab. It probes each supported CLI — launcher binary on `PATH`, `agent_chat` MCP config valid — and you tick the ones you actually have. That answer is saved to `config/available-clis.json` (gitignored) and everything downstream (`/orchestrate`, `debate.ps1`, the homepage) offers only those.

**One CLI is enough.** If you have exactly one, the tab will plan a debate as `claude-code` vs `claude-code-2` and offer to create the extra seat folder for you — same result as running `add_agent_seat.py` by hand in step 2.

The other two tabs are optional and can wait: **Notifications** (be told when a run finishes or gets stuck — see [notifications](../App/notifications.md)) and **Delivery** (write each finished run out to a folder — see [delivery](../App/delivery.md)). Both are off until you set them up.

### 5 · Start a conversation

Pick one of the three ways — [auto-debate](../Guides/auto-debate.md), [manual CLI seed](../Guides/start-new-chat.md), or the [web form](../Guides/orchestrate-form.md). A manual smoke test:

```powershell
.\scripts\start.ps1 --topic "Smoke test: confirm agent_chat works end to end" --participants claude-code,codex --first claude-code --mode turns --max-turns 5
```

Then open each CLI from its `agents/CLIs/<cli>_agent1/` folder (so it loads the right `--agent-id` config) and paste the one-line `get_kickoff()` prompt — `--first` agent first.

### 6 · Watch it live

`http://127.0.0.1:8765/conversations/<id>` (local, instant) — or the hosted mirror `https://agent-chat.ai-automation-tools.dev/conversations/<id>` if the DB-sync sidecar is running.

### 7 · Review, export & debug

Transcript, **Stop**, and **Export** (Markdown / `.zip`) on the conversation page; or from the CLI:

```powershell
.\.venv\Scripts\python.exe src\inspect_conversations.py list      # all conversations
.\.venv\Scripts\python.exe src\inspect_conversations.py show 1    # full transcript
.\.venv\Scripts\python.exe src\inspect_conversations.py tail 1    # live tail
Get-Content -Wait db\db_sync.log                                  # tail the sidecar log
```

### Verify the install

```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import agent_chat_mcp; print('imports ok')"
.\.venv\Scripts\python.exe src\start_conversation.py --help
```

Current source tree: [`docs/repo-layout.md`](../repo-layout.md).

---

## Historical bootstrap record (2026-05-01)

The exact steps taken to bootstrap this repository on **2026-05-01**, so the original layout and agent wiring can be reproduced or audited. (The sections below predate the later additions — Antigravity / OpenCode, the orchestrator, the persona DB — which are covered in the [CHANGELOG](../CHANGELOG.md). For the current setup path use [Fresh-clone setup](#fresh-clone-setup) above.)

The end state at that point was:

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

1. Created a private GitHub repo at `https://github.com/ai-automation-tools/Agent-chat` (no auto-init — repo was empty so the local could push first).
2. `git init -b main` inside `D:\AI_Agents\Projects\Mikes_AI_Lab\Repos\AI-Automation-Tools\Live_Apps\Agent-Chat`.
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

- Server script: `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/AI-Automation-Tools/Live_Apps/Agent-Chat/src/agent_chat_mcp.py`
- Shared DB: `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/AI-Automation-Tools/Live_Apps/Agent-Chat/db/chat.db` (auto-created on first run; `db/` exists, `*.db` is gitignored)

### Claude Code agent (`agents/CLIs/claude-code_agent1/`)

Appended a new server entry to the existing `.mcp.json` (which already had 9 unrelated servers — preserved as-is):

```json
"agent_chat": {
  "command": "pwsh",
  "args": [
    "-NoProfile",
    "-File",
    "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/AI-Automation-Tools/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
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

The seat's role doc is `claude.md` in that folder — a **full-stack developer** brief that also covers participating in `agent_chat` conversations. (It was briefly narrowed to a testing-only role in May 2026 and widened back on 2026-08-26; all five seat docs are generated from one template.)

### Codex CLI agent (`agents/CLIs/codex_agent1/`)

The MCP server is registered in the **user-level** Codex config at `C:\Users\mikes\.codex\config.toml` (later in the day — initially we tried a per-folder `.codex/config.toml` here, but Codex's loader doesn't read that location by default, so the in-repo file was removed). The block appended to the global config:

```toml
[mcp_servers.agent_chat]
command = "pwsh"
args = [
  "-NoProfile",
  "-File",
  "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/AI-Automation-Tools/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
  "codex",
]
```

> [!NOTE]
> Same launcher + defaulting story as the Claude Code block above — the
> only hardcoded path is `scripts/run-mcp-server.ps1`, and `--db-path`
> is optional (server defaults + `$AGENT_CHAT_DB`).

Side effect: `agent_chat` is now visible to **every** Codex session on this machine, regardless of cwd. That's fine — the server only does work when an agent calls its tools — but it means the venv at `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/AI-Automation-Tools/Live_Apps/Agent-Chat/.venv/` must keep existing or every Codex session will fail to start that server until the path is fixed.

`agents/CLIs/codex_agent1/.codex/skills/` (skill-creator, skill-installer) is unrelated to MCP wiring and stays.

The seat's role doc is `AGENTS.md`, the same full-stack-developer + agent-chat brief as the Claude side with Codex's agent id and config location swapped in.

### Wire the shared Agent Skills (run once per clone)

The canonical Agent Skills (`agent-chat`, `debate-mode`) live at the repo-root
`skills/` folder and are linked into each CLI's (gitignored) config directory so
every CLI reads the same `SKILL.md`. After cloning, run the setup script once to
create the links:

```powershell
.\scripts\setup\setup-skill-links.ps1   # Windows junctions
```

> [!NOTE]
> On macOS/Linux use the POSIX equivalent, which creates symlinks instead:
> `scripts/setup/setup-skill-links.sh`.

This wires `skills/` into the per-CLI link dirs: claude-code → `.claude/skills`,
codex → `.codex/skills`, gemini → `.gemini/skills`, antigravity → `.agents/skills`.

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
D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/AI-Automation-Tools/Live_Apps/Agent-Chat/.venv/Scripts/python.exe
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
- Ask each agent to call `get_kickoff` once, then drive itself through the `wait_for_turn` → `send_message` loop until the conversation ends. (Pre-`get_kickoff` flow — paste the rendered `prompts/Kickoff/kickoff.md` into each CLI — still works for rows seeded without `--preset`.)
- Optionally tail the conversation in a third terminal:
  ```powershell
  python src/inspect_conversations.py tail 1
  ```
