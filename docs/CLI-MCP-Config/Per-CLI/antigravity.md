# Antigravity CLI — agent_chat integration

> Part of [`docs/CLI-MCP-Config/`](../README.md). For the **project-vs-global** quick reference across all CLIs, start at the [consolidated README](../README.md); this page is the Antigravity deep dive.

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

> [!WARNING]
> **Verify project-local loading in your installed version.** An upstream issue ([antigravity-cli #60](https://github.com/google-antigravity/antigravity-cli/issues/60)) reported a project-local `mcp_config.json` being *discovered but silently ignored*, with only the global file actually spawning servers. That report referenced an older config path, so it may be stale — but smoke-test that a server defined **only** in `.agents/mcp_config.json` shows up under `/mcp`. If it doesn't, register globally instead (below).

## Global (user) registration

To make `agent_chat` available to **every** Antigravity session (CLI, IDE, and Antigravity 2.0 all read it), put the same `agent_chat` block inside the `mcpServers` object of the global config:

```
~/.gemini/config/mcp_config.json
C:\Users\<you>\.gemini\config\mcp_config.json   # Windows
```

> [!NOTE]
> The global file lives under `~/.gemini/`, **not** `~/.antigravity/` — Antigravity inherited Gemini's config root. (A legacy pre-migration path `~/.gemini/antigravity-cli/mcp_config.json` still appears in some older guides; newer official codelabs use `~/.gemini/config/mcp_config.json`.) There is **no `agy mcp add` subcommand** — manage servers by editing this JSON directly, or interactively via the `/mcp` slash command (the "MCP server manager") inside an `agy` session.

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

## Configuration Details & Auto-Spawn Support

- **Auto-spawn launch command**: The `scripts/debate.ps1` script has been updated to include `antigravity` (using `agy`) as a registered CLI in its `$Clis` launch registry.
- **Headless mode / Tool-approval prompts**: Bypassing tool approval prompts is fully supported by:
  - Specifying the `--dangerously-skip-permissions` CLI flag (which is passed automatically when running `scripts/debate.ps1` with the `-SkipPermissions` parameter):
    ```powershell
    agy --dangerously-skip-permissions -i "Read the file at '...' and follow it."
    ```
  - Setting `"toolPermission": "always-proceed"` and `"artifactReviewPolicy": "always-proceed"` in the `.agents/settings.json` configuration file located in the active CLI workspace folder (`agents/CLIs/antigravity_agent1/.agents/settings.json`):
    ```json
    {
      "model": "gemini-3.5-flash",
      "toolPermission": "always-proceed",
      "artifactReviewPolicy": "always-proceed",
      "enableTerminalSandbox": false,
      "allowNonWorkspaceAccess": false,
      "colorScheme": "terminal",
      "verbosity": "high"
    }
    ```

- **Three-way turn skipping.** With three participants the rotation must wrap correctly. Watch for `current_turn` ever landing on the wrong agent after a `send_message`.
- **Config reload.** Editing `mcp_config.json` while Antigravity is running may not hot-reload the server list — relaunch after any registration change.

## Vendor documentation

Antigravity is newer and its docs move; if this page stops matching, check the source:

- Antigravity docs — <https://antigravity.google/docs>
- MCP in Antigravity (codelab) — <https://codelabs.developers.google.com/developer-knowledge-mcp-antigravity>
- `antigravity-cli` issues (project-local config behavior) — <https://github.com/google-antigravity/antigravity-cli/issues>
