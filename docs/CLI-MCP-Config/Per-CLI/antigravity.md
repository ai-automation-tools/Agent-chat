# Antigravity CLI — `agent_chat` integration

> **Nav:** [Registration hub ↑](../README.md) · **Antigravity** deep dive · siblings: [Claude Code](claude.md) · [Codex](codex.md) · [Gemini](gemini.md)

Register the `agent_chat` MCP server with the **Antigravity** CLI (binary: `agy`) and bring it into a conversation alongside Claude Code and Codex.

> [!NOTE]
> **Antigravity replaced the Gemini CLI.** Google deprecated the Gemini CLI; Antigravity is its successor. This workspace (`agents/CLIs/antigravity_agent1/`, agent-id `antigravity`) supersedes `agents/CLIs/gemini_agent1/`. The Gemini tester is kept as a fallback — see [`gemini.md`](gemini.md) — but new runs use `antigravity`.

---

## 📂 Where Antigravity reads MCP config

| Scope | File | Notes |
|:--|:--|:--|
| **project** | `.agents/mcp_config.json` (relative to launch dir) | per-folder; in this repo at `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` |
| **global** | `~/.gemini/config/mcp_config.json` | shared by Antigravity 2.0, the IDE, and the CLI |

Both use a top-level `mcpServers` object. There is **no `agy mcp add` subcommand** — manage servers by editing the JSON directly, or interactively via the `/mcp` slash command (the "MCP server manager") inside an `agy` session.

In this repo, `.agents/mcp_config.json` is the one file in `.agents/` that's **tracked in git** (it holds the `agent_chat` config) — so any secret in it (e.g. GitHub) **must** use `${ENV_VAR}` substitution, never an inlined key. The rest of `.agents/` is gitignored.

> [!IMPORTANT]
> Any other server in this `mcp_config.json` that needs a token reads it via `${ENV_VAR}` — e.g. `github` uses `${GITHUB_TOKEN}`. Set those env vars (e.g. `$env:GITHUB_TOKEN = "..."`) or remove the servers you don't use — an unset variable makes that server fail to start.

---

## Project-level registration

Add `agent_chat` inside the `mcpServers` object of `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` (preserve any other servers):

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

Launching `agy` from `agents/CLIs/antigravity_agent1/` is what activates it.

> [!NOTE]
> The launcher resolves the venv interpreter and server script relative to its own location, so the launcher path is the only hardcoded string. `--db-path` is optional (defaults to `<repo>/db/chat.db`; `$env:AGENT_CHAT_DB` overrides); append it after `"antigravity"` in `args` to set one explicitly.

> [!WARNING]
> **Verify project-local loading in your installed version.** An upstream issue ([antigravity-cli #60](https://github.com/google-antigravity/antigravity-cli/issues/60)) reported a project-local `mcp_config.json` being *discovered but silently ignored*, with only the global file spawning servers. That report referenced an older path, so it may be stale — but smoke-test that a server defined **only** in `.agents/mcp_config.json` shows up under `/mcp`. If it doesn't, register globally instead.

<details>
<summary><b>macOS/Linux variant</b> — use the <code>.sh</code> launcher, no <code>pwsh</code> needed</summary>

```json
"agent_chat": {
  "command": "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh",
  "args": ["antigravity"]
}
```

The `.sh` ships with the +x bit set in the git index.

</details>

---

## Global-level registration

To make `agent_chat` available to **every** Antigravity session, put the same `agent_chat` block inside the `mcpServers` object of the global config:

```
~/.gemini/config/mcp_config.json
C:\Users\<you>\.gemini\config\mcp_config.json     # Windows
```

> [!NOTE]
> The global file lives under `~/.gemini/`, **not** `~/.antigravity/` — Antigravity inherited Gemini's config root. (A legacy pre-migration path `~/.gemini/antigravity-cli/mcp_config.json` still appears in older guides; newer official codelabs use `~/.gemini/config/mcp_config.json`.)

---

## ✅ Verify

Launch `agy` from the workspace and use the `/mcp` slash command (the "MCP server manager") to confirm `agent_chat` is listed, or ask the agent directly:

> Do you see an MCP server called agent_chat? List the tools it exposes.

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status`. If not, check:

1. The JSON parses — `python -m json.tool agents/CLIs/antigravity_agent1/.agents/mcp_config.json`.
2. `pwsh` resolves on PATH and the launcher path exists.
3. `db/chat.db` exists or can be auto-created.
4. You launched from `agents/CLIs/antigravity_agent1/` — not the repo root.

Editing the config likely needs a restart (hot-reload is undocumented).

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
3. Ask each agent to call `get_kickoff()` once, then drive itself through the `wait_for_turn` → `send_message` loop (see `prompts/Kickoff/kickoff.md` / the `agent-chat` skill).
4. Start the `--first` agent first.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

</details>

---

## 🤖 Headless / auto-spawn

The `scripts/debate.ps1` launcher registers `antigravity` (via `agy`) in its `$Clis` launch table. Tool-approval prompts can be bypassed two ways:

- The `--dangerously-skip-permissions` flag (passed automatically by `debate.ps1 -SkipPermissions`):
  ```powershell
  agy --dangerously-skip-permissions -i "Read the file at '...' and follow it."
  ```
- Persistently, via `.agents/settings.json` in the workspace (`agents/CLIs/antigravity_agent1/.agents/settings.json`):
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

---

## ⚠️ Known quirks

- **Config reload.** Editing `mcp_config.json` while Antigravity is running may not hot-reload the server list — relaunch after any change.
- **Three-way turn skipping.** With three participants the rotation must wrap correctly. Watch for `current_turn` landing on the wrong agent after a `send_message`.

---

## 📚 Vendor documentation

Antigravity is newer and its docs move; if this page stops matching, check the source:

- Antigravity docs — <https://antigravity.google/docs>
- MCP in Antigravity (codelab) — <https://codelabs.developers.google.com/developer-knowledge-mcp-antigravity>
- `antigravity-cli` issues (project-local config behavior) — <https://github.com/google-antigravity/antigravity-cli/issues>
