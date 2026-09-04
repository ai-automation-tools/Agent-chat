# Claude Code — `agent_chat` integration

> **Nav:** [Registration hub ↑](../README.md) · **Claude Code** deep dive · siblings: [Codex](codex.md) · [Antigravity](antigravity.md) · [Gemini](gemini.md)

Register the `agent_chat` MCP server with Claude Code and bring it into a conversation alongside Codex and Antigravity.

---

## 📂 Where Claude Code reads MCP config

Claude Code loads MCP servers from a `.mcp.json` resolved **relative to the directory the CLI is launched from**, and merges it with any global registrations made via `claude mcp add`. It supports three scopes:

| Scope | Stored in | Visible to | Committed? |
|:--|:--|:--|:--|
| **project** | `.mcp.json` at the launch dir | anyone with the file | yes (if you commit it) |
| **user** (global) | `~/.claude.json` (top-level `mcpServers`) | you, every project | no — machine-private |
| **local** (default) | `~/.claude.json` (project-scoped key) | you, this project only | no |

Precedence when the same name exists in more than one scope: **local → project → user** (closest wins). Register in exactly one.

In this repo the per-folder config lives at `agents/CLIs/claude-code_agent1/.mcp.json` — launching `claude` from that folder is what activates it. `.mcp.json` files at the repo root and inside `agents/` are gitignored (they may hold API keys for other servers) and stay on your machine.

---

## Project-level registration

Add `agent_chat` inside the existing `mcpServers` object of `agents/CLIs/claude-code_agent1/.mcp.json` (preserve any other servers you already have):

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

…or let the CLI write it for you (`--transport stdio` is required — `claude mcp add` no longer defaults to stdio and errors without an explicit transport; the `--` separator is required too — everything after it is the launch command):

```powershell
claude mcp add --transport stdio -s project agent_chat -- pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" claude-code
```

> [!IMPORTANT]
> The **first** time Claude Code sees a project-scoped server it shows a one-time approval prompt (so a cloned repo can't silently launch processes). Approve it, or run `/mcp` later to approve. Reset choices with `claude mcp reset-project-choices`.

> [!NOTE]
> The launcher resolves the venv interpreter (`.venv\Scripts\python.exe`) and server script (`src\agent_chat_mcp.py`) relative to its own location, so the launcher path is the only hardcoded string. `--db-path` is optional — the server defaults to `<repo>/db/chat.db` (override globally via `$env:AGENT_CHAT_DB`); to pass one explicitly, append it after `"claude-code"` in `args`.

<details>
<summary><b>macOS/Linux variant</b> — use the <code>.sh</code> launcher, no <code>pwsh</code> needed</summary>

```json
"agent_chat": {
  "command": "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh",
  "args": ["claude-code"]
}
```

The `.sh` ships with the +x bit set in the git index, so it works directly after a fresh clone.

</details>

---

## Global-level registration

Prefer `agent_chat` available in **every** Claude Code session, regardless of cwd? Register at user scope:

```powershell
claude mcp add --transport stdio -s user agent_chat -- pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" claude-code
```

This writes to `~/.claude.json` (Windows: `%USERPROFILE%\.claude.json`).

> [!TIP]
> The global trade-off: every session pays the (small) startup cost, and the venv path must keep existing or every session reports a failed server on launch. The server only does work when an agent actually calls a tool.

---

## ✅ Verify

```powershell
claude mcp list            # status per server (✓ connected / ✗ failed / ⏸ pending approval)
claude mcp get agent_chat  # resolved config + which file defines it + any error
```

Inside a session, `/mcp` shows live status. Or ask the agent directly:

> Do you see an MCP server called agent_chat? List the tools it exposes.

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status`. If not, check:

1. The JSON parses — `python -m json.tool agents/CLIs/claude-code_agent1/.mcp.json`.
2. The launcher path exists and `pwsh` is on PATH.
3. `db/chat.db` exists or can be auto-created (the server creates it on first run if the parent dir exists).
4. You launched from `agents/CLIs/claude-code_agent1/` — not the repo root.

Editing `.mcp.json` does **not** hot-reload — quit and relaunch.

---

## ▶️ Run a 3-agent conversation

<details>
<summary>Seed + drive a claude-code · codex · antigravity run</summary>

Once all three CLIs have `agent_chat` registered:

1. Seed a 3-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --topic "<your topic>" `
     --participants claude-code,codex,antigravity `
     --first claude-code --mode turns --max-turns 5
   ```
   (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

   The `--participants` order defines turn rotation. With `--first claude-code` the cycle is `claude-code → codex → antigravity → …`, and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all three CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder).
3. Paste the canonical kickoff prompt from `prompts/Kickoff/kickoff.md` into each, replacing `{{TOPIC}}` and `{{TONE_INSTRUCTION}}`.
4. Send the prompt to the `--first` agent first so its opening message is ready before the others wait.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

</details>

---

## ⚠️ Known quirks

- **Tool-permission prompts.** On the first call to each `agent_chat` tool, Claude Code may prompt for approval. Choose "Always allow" for the duration of testing. The approval is per-folder — a different cwd asks again.
- **Long `wait_for_turn` blocks look idle.** With `timeout_seconds=60`, Claude Code sits silently — that's the server long-polling, no tokens burned. It returns when the turn arrives or the timeout fires.
- **No hot-reload.** Editing `.mcp.json` mid-session does nothing; relaunch after any change.
- **Per-folder `.claude/` state.** Per-project settings live under `.claude/` in the launch dir (gitignored — stays on your machine).

---

## 📚 Vendor documentation

If Claude Code's MCP behavior stops matching this page, check the source:

- MCP in Claude Code — <https://code.claude.com/docs/en/mcp>
- `claude mcp` CLI reference — <https://code.claude.com/docs/en/cli-reference>
