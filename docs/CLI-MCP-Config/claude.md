# Claude Code — agent_chat integration

How to register the `agent_chat` MCP server with Claude Code and bring it into a conversation alongside Codex and Gemini.

## Where Claude Code reads MCP config

Claude Code loads MCP servers from a JSON file named `.mcp.json` resolved **relative to the working directory the CLI is launched from**. Different folders can register different servers, and Claude Code merges the per-folder file with any global registrations made via `claude mcp add`.

For this project, the per-folder config lives at:

```
agents/CLIs/claude-code_agent1/.mcp.json
```

Launching `claude` from `agents/CLIs/claude-code_agent1/` is what makes the registration take effect. `.mcp.json` files at the repo root and inside `agents/` are gitignored — they may contain API keys for other servers (GitHub Copilot, ElevenLabs, etc.) and stay on your machine.

## Registration block

Open `agents/CLIs/claude-code_agent1/.mcp.json` and add an `agent_chat` entry inside the existing `mcpServers` object. Preserve any other servers you already have registered.

```json
"agent_chat": {
  "command": "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/Scripts/python.exe",
  "args": [
    "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/src/agent_chat_mcp.py",
    "--agent-id", "claude-code",
    "--db-path", "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db"
  ]
}
```

> [!NOTE]
> The two absolute paths must match what the other agents are using. If you've cloned into a different drive/folder, adjust both. (See the open Roadmap item "Make venv interpreter path portable" for the long-term fix.)

> [!NOTE]
> macOS/Linux equivalent: replace `.venv/Scripts/python.exe` with `.venv/bin/python` and use forward slashes throughout.

> [!TIP]
> Prefer registering globally? Run `claude mcp add agent_chat <command> --args ...` from any folder — the server then shows up in every Claude Code session on this machine. The trade-off is the same as Codex's global config: every session pays the startup cost, and the venv path must keep existing or every session will report a failed server on launch.

## Verify the server registered

After saving `.mcp.json`, launch Claude Code from `agents/CLIs/claude-code_agent1/` and ask it:

```
Do you see an MCP server called agent_chat? List the tools it exposes.
```

You should get back four tools: `wait_for_turn`, `get_my_turn`, `send_message`, `get_conversation_status`. If you don't, double-check:

1. The JSON parses (`python -m json.tool agents/CLIs/claude-code_agent1/.mcp.json`).
2. The Python interpreter path actually exists.
3. `db/chat.db` exists or can be auto-created (the server will create it on first run if the parent directory exists).
4. You launched Claude Code from `agents/CLIs/claude-code_agent1/` — not from the repo root or another folder.

You can also run `/mcp` inside Claude Code to see the live status of every registered server (✅ connected / ❌ failed / ⏳ starting) along with any startup error from the server's stderr.

## Run a 3-agent conversation

Once Claude Code, Codex, and Gemini all have `agent_chat` registered:

1. Seed a 3-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --db-path db\chat.db `
     --topic "<your topic>" `
     --participants claude-code,codex,gemini `
     --first claude-code --mode turns --max-turns 5
   ```

   The `--participants` order defines the turn-rotation order. With `claude-code,codex,gemini` and `--first claude-code`, the cycle is `claude-code → codex → gemini → claude-code → …` and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all three CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder).
3. Paste the canonical kickoff prompt from `prompts/kickoff.md` into each, replacing `{{TOPIC}}` and `{{TONE_INSTRUCTION}}`.
4. Send the prompt to the `--first` agent first so it has its opening message ready before the others start waiting.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

## Known quirks

- **Tool-permission prompts.** On the first call to each `agent_chat` tool, Claude Code may prompt you to approve the tool. Approve "Always allow" for the duration of testing or you'll be answering prompts every turn. The approval is per-folder — re-running from a different cwd asks again.
- **Long `wait_for_turn` blocks may look idle.** With `timeout_seconds=60` (the default), Claude Code sits silently with no streaming output. That's expected — the server is long-polling, no tokens are being burned. The CLI returns when the turn arrives or the timeout fires.
- **`.mcp.json` reload.** Editing `.mcp.json` while Claude Code is running does **not** hot-reload the server list. Quit and relaunch the CLI after any registration change.
- **Per-folder `.claude/` workspace state.** Claude Code stores per-project settings (allowed tools, history, etc.) under `.claude/` in the launch directory. That folder is gitignored — settings stay on your machine.
