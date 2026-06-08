# Gemini CLI — agent_chat integration

How to register the `agent_chat` MCP server with Gemini CLI and bring it into a conversation alongside Claude Code and Codex.

## Where Gemini reads MCP config

Gemini CLI loads MCP servers from a JSON file at `.gemini/settings.json`. Like Claude Code's `.mcp.json`, it's resolved **relative to the working directory the CLI is launched from**, so different folders can register different servers.

For this project, the per-folder config lives at:

```
agents/CLIs/gemini_agent1/.gemini/settings.json
```

Launching Gemini CLI from `agents/CLIs/gemini_agent1/` is what makes the registration take effect. `.gemini/` is gitignored — settings.json (which may contain API keys for other servers like Serper or GitHub) stays on your machine and never enters the public repo.

## Registration block

Open `agents/CLIs/gemini_agent1/.gemini/settings.json` and add an `agent_chat` entry inside the existing `mcpServers` object. Preserve any other servers you already have registered.

```json
"agent_chat": {
  "command": "pwsh",
  "args": [
    "-NoProfile",
    "-File",
    "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
    "gemini"
  ]
}
```

> [!NOTE]
> The launcher (`scripts/run-mcp-server.ps1`) resolves the venv interpreter and the MCP server script relative to its own location, so the only hardcoded path in this config is the launcher path itself. Cloning to a different drive/folder = edit one string.
>
> Requires `pwsh` (PowerShell 7+) on PATH. Install with `winget install Microsoft.PowerShell` if missing.
>
> `--db-path` is no longer needed in the config — the server defaults to `<repo>/db/chat.db` resolved from `src/agent_chat_mcp.py`'s location, and `$AGENT_CHAT_DB` overrides. To pass an explicit `--db-path` anyway, append it after `"gemini"` in the args array; the launcher forwards extra args verbatim to the Python child.

> [!NOTE]
> macOS/Linux equivalent: swap to the `.sh` launcher and skip the pwsh host —
>
> ```json
> "agent_chat": {
>   "command": "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh",
>   "args": ["gemini"]
> }
> ```
>
> The `.sh` ships with the +x bit set in the git index.

## Verify the server registered

After saving `settings.json`, launch Gemini CLI from `agents/CLIs/gemini_agent1/` and ask it:

```
Do you see an MCP server called agent_chat? List the tools it exposes.
```

You should get back four tools: `wait_for_turn`, `get_my_turn`, `send_message`, `get_conversation_status`. If you don't, double-check:

1. The JSON parses (`python -m json.tool agents/CLIs/gemini_agent1/.gemini/settings.json`).
2. The Python interpreter path actually exists.
3. `db/chat.db` exists or can be auto-created (the server will create it on first run if the parent directory exists).

## Run a 3-agent conversation

Once Claude Code, Codex, and Gemini all have `agent_chat` registered:

1. Seed a 3-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --topic "<your topic>" `
     --participants claude-code,codex,gemini `
     --first claude-code --mode turns --max-turns 5
   ```
   (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

   The `--participants` order defines the turn-rotation order. With `claude-code,codex,gemini` and `--first claude-code`, the cycle is `claude-code → codex → gemini → claude-code → …` and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all three CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder).
3. Paste the canonical kickoff prompt from `prompts/kickoff.md` into each, replacing `{{TOPIC}}` and `{{TONE_INSTRUCTION}}`.
4. Send the prompt to the `--first` agent first so it has its opening message ready before the others start waiting.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

## Known quirks

_None confirmed yet — fill this section in as we exercise three-agent runs._

Likely things to watch for:

- **Tool-call cadence.** Gemini may call `wait_for_turn` more aggressively than Claude/Codex if its loop logic differs. The server's 1s polling interval is shared, so this shouldn't matter for cost — but it's worth confirming.
- **History rendering.** Gemini may format the history differently when reading it back; confirm it correctly identifies the most recent message and references it.
- **Three-way turn skipping.** With three participants the rotation must wrap correctly. Watch for `current_turn` ever landing on the wrong agent after a `send_message`.
