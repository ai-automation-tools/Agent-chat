# Gemini CLI — `agent_chat` integration

> **Nav:** [Registration hub ↑](../README.md) · **Gemini** deep dive · siblings: [Claude Code](claude.md) · [Codex](codex.md) · [Antigravity](antigravity.md)

> [!WARNING]
> **Deprecated — kept as a fallback.** Google deprecated the Gemini CLI; its successor is the **Antigravity** CLI. For new setups use [`antigravity.md`](antigravity.md) (agent-id `antigravity`, workspace `agents/CLIs/antigravity_agent1/`) — that's what the auto-debate launcher (`scripts/debate.ps1`) spawns. This page is retained for anyone still running the Gemini seat directly.

Register the `agent_chat` MCP server with Gemini CLI and bring it into a conversation alongside Claude Code and Codex.

---

## 📂 Where Gemini reads MCP config

| Scope | File | Notes |
|:--|:--|:--|
| **project** (default) | `.gemini/settings.json` (relative to launch dir) | per-folder; in this repo at `agents/CLIs/gemini_agent1/.gemini/settings.json` |
| **user** (global) | `~/.gemini/settings.json` | every Gemini session on the machine |

Both use a top-level `mcpServers` object, and Gemini CLI has a real `gemini mcp add` command with a `-s` / `--scope` flag (`project` is the default). In this repo `.gemini/` is gitignored — `settings.json` (which may hold other API keys) stays on your machine.

---

## Project-level registration

Add `agent_chat` inside the `mcpServers` object of `agents/CLIs/gemini_agent1/.gemini/settings.json` (preserve any other servers):

```json
"agent_chat": {
  "command": "pwsh",
  "args": [
    "-NoProfile",
    "-File",
    "<repo>/scripts/run-mcp-server.ps1",
    "gemini"
  ]
}
```

…or let the CLI write it (project is the default scope):

```powershell
gemini mcp add agent_chat pwsh -NoProfile -File "<repo>/scripts/run-mcp-server.ps1" gemini
```

> [!NOTE]
> The launcher resolves the venv interpreter and server script relative to its own location, so the launcher path is the only hardcoded string. `--db-path` is optional (defaults to `<repo>/db/chat.db`; `$env:AGENT_CHAT_DB` overrides); append it after `"gemini"` in `args` to set one explicitly. If the parser mis-claims a leading-`-` arg, separate the command from its args with `--`: `gemini mcp add agent_chat -- pwsh -NoProfile -File "<LAUNCHER>" gemini`.

<details>
<summary><b>macOS/Linux variant</b> — use the <code>.sh</code> launcher, no <code>pwsh</code> needed</summary>

```json
"agent_chat": {
  "command": "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh",
  "args": ["gemini"]
}
```

The `.sh` ships with the +x bit set in the git index.

</details>

---

## Global-level registration

To register `agent_chat` for **every** Gemini session, use user scope — either via the CLI:

```powershell
gemini mcp add -s user agent_chat pwsh -NoProfile -File "<repo>/scripts/run-mcp-server.ps1" gemini
```

…or by hand-editing the global settings file (same `mcpServers` shape as the per-folder file):

```
~/.gemini/settings.json
C:\Users\<you>\.gemini\settings.json     # Windows
```

---

## ✅ Verify

Launch Gemini CLI from `agents/CLIs/gemini_agent1/` and ask it:

> Do you see an MCP server called agent_chat? List the tools it exposes.

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status`. If not, check:

1. The JSON parses — `python -m json.tool agents/CLIs/gemini_agent1/.gemini/settings.json`.
2. The launcher path exists and `pwsh` is on PATH.
3. `db/chat.db` exists or can be auto-created.

`/mcp refresh` re-discovers tools from *already-configured* servers, but adding a new server in `settings.json` does **not** take effect without restarting the CLI ([#3528](https://github.com/google-gemini/gemini-cli/issues/3528), [#4786](https://github.com/google-gemini/gemini-cli/issues/4786)).

---

## ▶️ Run a 3-agent conversation

<details>
<summary>Seed + drive a claude-code · codex · gemini run</summary>

Once all three CLIs have `agent_chat` registered:

1. Seed a 3-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --topic "<your topic>" `
     --participants claude-code,codex,gemini `
     --first claude-code --mode turns --max-turns 5
   ```
   (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

   The `--participants` order defines turn rotation. With `--first claude-code` the cycle is `claude-code → codex → gemini → …`, and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all three CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder).
3. Paste the canonical kickoff prompt from `prompts/Kickoff/kickoff.md` into each, replacing `{{TOPIC}}` and `{{TONE_INSTRUCTION}}`.
4. Send the prompt to the `--first` agent first.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

</details>

---

## ⚠️ Known quirks

- **Adding a server needs a restart.** `/mcp refresh` reloads tools from existing servers, but a newly added server in `settings.json` requires a CLI restart.
- **Tool-call cadence.** Gemini may call `wait_for_turn` more aggressively than Claude/Codex; the server's 1s polling interval is shared, so cost is unaffected.
- **History rendering.** Gemini may format read-back history differently; confirm it identifies the most recent message correctly.
- **Three-way turn skipping.** With three participants, watch for `current_turn` landing on the wrong agent after a `send_message`.

---

## 📚 Vendor documentation

The Gemini CLI is deprecated but still documented; if this page stops matching, check the source:

- MCP servers with Gemini CLI — <https://geminicli.com/docs/tools/mcp-server/>
- MCP setup tutorial — <https://geminicli.com/docs/cli/tutorials/mcp-setup/>
