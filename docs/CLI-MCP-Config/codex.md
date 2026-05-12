# Codex CLI — agent_chat integration

How to register the `agent_chat` MCP server with Codex CLI and bring it into a conversation alongside Claude Code and Gemini.

## Where Codex reads MCP config

Unlike Claude Code and Gemini, **Codex's loader only reads a single global TOML file** at:

```
~/.codex/config.toml          # macOS/Linux
C:\Users\<you>\.codex\config.toml   # Windows
```

A per-folder `.codex/config.toml` inside the repo is **dormant by default** — Codex ignores it unless you set the environment variable `CODEX_HOME` to point at the folder containing it. We tried the per-folder approach during initial setup, found it didn't take effect, and removed the in-repo file. The global config is the supported path.

Side effect: once `agent_chat` is registered globally, it's visible to **every** Codex session on this machine, regardless of cwd. That's fine — the server only does work when an agent calls its tools — but the venv at `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/.venv/` must keep existing or every Codex session will report a failed server until the path is fixed.

## Registration block

Open `~/.codex/config.toml` (create the file and the parent `.codex/` folder if they don't exist) and append:

```toml
[mcp_servers.agent_chat]
command = "pwsh"
args = [
  "-NoProfile",
  "-File",
  "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/scripts/run-mcp-server.ps1",
  "codex",
]
```

> [!NOTE]
> The launcher (`scripts/run-mcp-server.ps1`) resolves the venv interpreter and the MCP server script relative to its own location, so the only hardcoded path in this config is the launcher path itself. Cloning to a different drive/folder = edit one string.
>
> Requires `pwsh` (PowerShell 7+) on PATH. Install with `winget install Microsoft.PowerShell` if missing.
>
> `--db-path` is no longer needed in the config — the server defaults to `<repo>/db/chat.db` resolved from `src/agent_chat_mcp.py`'s location, and `$AGENT_CHAT_DB` overrides. To pass an explicit `--db-path` anyway, append it after `"codex"` in the args array; the launcher forwards extra args verbatim to the Python child.

> [!NOTE]
> macOS/Linux equivalent: swap to the `.sh` launcher and skip the pwsh host —
>
> ```toml
> [mcp_servers.agent_chat]
> command = "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh"
> args = ["codex"]
> ```
>
> The `.sh` ships with the +x bit set in the git index.

> [!IMPORTANT]
> The `--agent-id` value **must be `codex`** — that's the identity the rest of the system (turn rotation, message attribution, web UI participant labels) keys off. Don't rename it.

## Verify the server registered

After saving `config.toml`, launch Codex CLI from `agents/CLIs/codex_agent1/` (so it picks up the local `AGENTS.md` tester role) and ask it:

```
Do you see an MCP server called agent_chat? List the tools it exposes.
```

You should get back four tools: `wait_for_turn`, `get_my_turn`, `send_message`, `get_conversation_status`. If you don't, double-check:

1. The TOML parses (`python -c "import tomllib; tomllib.load(open(r'C:\Users\<you>\.codex\config.toml','rb'))"` — silent = valid).
2. The Python interpreter path actually exists.
3. `db/chat.db` exists or can be auto-created (the server will create it on first run if the parent directory exists).
4. The block header is exactly `[mcp_servers.agent_chat]` — Codex's loader is case-sensitive and the table prefix matters.

If the server still doesn't show up, restart the Codex session — Codex reads `config.toml` once at launch and does not hot-reload.

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

- **No per-folder override.** Because the registration is global, you cannot have two Codex sessions in the same shell using different `--agent-id` values without rewriting `config.toml` between launches. For multi-codex testing, use a second OS user account or temporarily point `CODEX_HOME` at an alternate folder for that session.
- **TOML strictness.** A trailing comma after the last array element is allowed in TOML, but a missing comma between elements is a parse error and Codex will silently start without `agent_chat`. If `/mcp` doesn't list it after a launch, suspect the TOML before suspecting the server.
- **Stderr from the server is swallowed.** Codex doesn't surface MCP server stderr by default. To debug a startup failure, run the exact `command + args` from a terminal and watch the output:
  ```powershell
  pwsh -NoProfile -File "D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/scripts/run-mcp-server.ps1" codex
  ```
  The server prints to stderr and waits for stdio JSON-RPC; Ctrl-C to exit. Any import error or missing-file error will show up here. Append `--db-path <path>` after `codex` (or set `$env:AGENT_CHAT_DB`) if you need to point at a non-default DB file — the launcher forwards extra args verbatim.
- **Tool-call cadence.** Codex tends to call `wait_for_turn` immediately after each `send_message` without intermediate prose. That's the desired loop shape — don't try to "fix" it by adding delays.
