# Antigravity CLI — agent_chat integration

How to register the `agent_chat` MCP server with the **Antigravity** CLI and bring it into a conversation alongside Claude Code and Codex.

> **Antigravity replaced the Gemini CLI.** Google deprecated the Gemini CLI; Antigravity is its successor. This workspace (`agents/CLIs/antigravity_agent1/`, agent-id `antigravity`) is the successor to `agents/CLIs/gemini_agent1/`. The Gemini tester is kept around for now as a fallback — see [`gemini.md`](gemini.md) — but new runs should use `antigravity`.

## Where Antigravity reads MCP config

Antigravity loads MCP servers from a JSON file at `.agents/mcp_config.json`, resolved **relative to the working directory the CLI is launched from**, so different folders can register different servers. (This differs from the Gemini CLI, which used `.gemini/settings.json`.)

For this project, the per-folder config lives at:

```
agents/CLIs/antigravity_agent1/.agents/mcp_config.json
```

Launching Antigravity from `agents/CLIs/antigravity_agent1/` is what makes the registration take effect. `mcp_config.json` is the one file in `.agents/` that's tracked in git (we keep the `agent_chat` config in the repo) — any secret in it (Serper, GitHub) **must** use `${ENV_VAR}` substitution, never an inlined key, so it stays out of the public repo. The rest of `.agents/` (`settings.json`, hooks, policies, skills) is gitignored and stays on your machine.

> [!IMPORTANT]
> The other MCP servers in this `mcp_config.json` (`serper`, `github`) read their tokens from the environment via `${SERPER_API_KEY}` / `${GITHUB_TOKEN}`. Set those env vars on your machine (e.g. `$env:SERPER_API_KEY = "..."`) or remove the servers you don't use — an unset variable will make that server fail to start.

## Registration block

Open `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` and add an `agent_chat` entry inside the existing `mcpServers` object. Preserve any other servers you already have registered.

```json
"agent_chat": {
  "command": "pwsh",
  "args": [
    "-NoProfile",
    "-File",
    "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
    "antigravity"
  ]
}
```

> [!NOTE]
> The launcher (`scripts/run-mcp-server.ps1`) resolves the venv interpreter and the MCP server script relative to its own location, so the only hardcoded path in this config is the launcher path itself. Cloning to a different drive/folder = edit one string.
>
> Requires `pwsh` (PowerShell 7+) on PATH. Install with `winget install Microsoft.PowerShell` if missing.
>
> `--db-path` is no longer needed in the config — the server defaults to `<repo>/db/chat.db` resolved from `src/agent_chat_mcp.py`'s location, and `$AGENT_CHAT_DB` overrides. To pass an explicit `--db-path` anyway, append it after `"antigravity"` in the args array; the launcher forwards extra args verbatim to the Python child.

> [!NOTE]
> macOS/Linux equivalent: swap to the `.sh` launcher and skip the pwsh host —
>
> ```json
> "agent_chat": {
>   "command": "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh",
>   "args": ["antigravity"]
> }
> ```
>
> The `.sh` ships with the +x bit set in the git index.

## Verify the server registered

After saving `mcp_config.json`, launch Antigravity from `agents/CLIs/antigravity_agent1/` and ask it:

```
Do you see an MCP server called agent_chat? List the tools it exposes.
```

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status`. If you don't, double-check:

1. The JSON parses (`python -m json.tool agents/CLIs/antigravity_agent1/.agents/mcp_config.json`).
2. `pwsh` resolves on PATH and the launcher path exists.
3. `db/chat.db` exists or can be auto-created (the server will create it on first run if the parent directory exists).
4. You launched Antigravity from `agents/CLIs/antigravity_agent1/` — not from the repo root or another folder.

## Run a 3-agent conversation

Once Claude Code, Codex, and Antigravity all have `agent_chat` registered:

1. Seed a 3-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --topic "<your topic>" `
     --participants claude-code,codex,antigravity `
     --first claude-code --mode turns --max-turns 5
   ```
   (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

   The `--participants` order defines the turn-rotation order. With `claude-code,codex,antigravity` and `--first claude-code`, the cycle is `claude-code → codex → antigravity → claude-code → …` and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all three CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder).
3. Ask each agent to call `get_kickoff()` once, then drive itself through the `wait_for_turn` → `send_message` loop (see `prompts/kickoff.md` / the `agent-chat` skill).
4. Start the `--first` agent first so it has its opening message ready before the others start waiting.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

## Known quirks

_None confirmed yet — fill this section in as we exercise Antigravity runs._

Things to confirm:

- **Auto-spawn launch command (open).** `scripts/debate.ps1` does not yet have an `antigravity` row in its `$Clis` launch table — the Antigravity CLI's headless invocation (binary name on PATH, the initial-prompt flag, and the skip-approval mechanism — Gemini used `--yolo`; Antigravity's `settings.json` has `toolPermission: request-review`) is unconfirmed. Until it is, run Antigravity manually (open it yourself and paste the opener) rather than via the one-command auto-debate launcher. Tracked on the Roadmap.
- **Tool-approval prompts.** `settings.json` ships `toolPermission: request-review`, so Antigravity may prompt before each `agent_chat` tool call. Approve "always allow" for the testing session, or find the settings value that disables review.
- **Three-way turn skipping.** With three participants the rotation must wrap correctly. Watch for `current_turn` ever landing on the wrong agent after a `send_message`.
- **Config reload.** Editing `mcp_config.json` while Antigravity is running may not hot-reload the server list — relaunch after any registration change.
