# Codex CLI — `agent_chat` integration

> **Nav:** [Registration hub ↑](../README.md) · **Codex** deep dive · siblings: [Claude Code](claude.md) · [Antigravity](antigravity.md) · [Gemini](gemini.md)

Register the `agent_chat` MCP server with Codex CLI and bring it into a conversation alongside Claude Code and Antigravity.

---

## 📂 Where Codex reads MCP config

Codex's **global** config is a single TOML file:

```
~/.codex/config.toml                  # macOS/Linux
C:\Users\<you>\.codex\config.toml     # Windows
```

The `codex mcp add` / `list` / `get` / `remove` commands **always** operate on this global file — there is no command that writes a project-scoped config. Newer Codex CLI *also* reads a repo-local `.codex/config.toml`, but only for **trusted** projects (see [Project-level registration](#project-level-registration)).

> [!IMPORTANT]
> The `--agent-id` value **must be `codex`** — that's the identity the rest of the system (turn rotation, message attribution, web-UI labels) keys off. Don't rename it.

---

## Global-level registration

This is the path we run on. Edit `~/.codex/config.toml` (create the file and `.codex/` folder if missing) and append:

```toml
[mcp_servers.agent_chat]
command = "pwsh"
args = [
  "-NoProfile",
  "-File",
  "<repo>/scripts/run-mcp-server.ps1",
  "codex",
]
```

…or let the CLI write the same block (the `--` separator is required — everything after it is the launch command):

```powershell
codex mcp add agent_chat -- pwsh -NoProfile -File "<repo>/scripts/run-mcp-server.ps1" codex
```

Once registered globally, `agent_chat` is visible to **every** Codex session on the machine — fine, since the server only works when an agent calls a tool, but the venv path must keep existing or every session reports a failed server.

> [!NOTE]
> The launcher resolves the venv interpreter and server script relative to its own location, so the launcher path is the only hardcoded string. `--db-path` is optional (defaults to `<repo>/db/chat.db`; `$env:AGENT_CHAT_DB` overrides); append it after `"codex"` in `args` to set one explicitly.

> [!CAUTION]
> **TOML strictness.** The table header must be exactly `[mcp_servers.agent_chat]` (keys are case-sensitive). Use **forward slashes** in the Windows path — backslashes are TOML escape chars. A missing comma between array elements is a parse error and Codex starts silently **without** the server, so if `/mcp` doesn't list it, suspect the TOML first.

<details>
<summary><b>macOS/Linux variant</b> — use the <code>.sh</code> launcher, no <code>pwsh</code> needed</summary>

```toml
[mcp_servers.agent_chat]
command = "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh"
args = ["codex"]
```

The `.sh` ships with the +x bit set in the git index.

</details>

---

## Project-level registration

Current Codex CLI reads a repo-local `.codex/config.toml`, but **only for projects you've marked trusted** (an untrusted project skips all `.codex/` layers). Put the same `[mcp_servers.agent_chat]` block shown above in `<repo>/.codex/config.toml`; the closest-to-cwd file wins. A plain stdio `[mcp_servers.*]` entry is allowed at project scope; security-sensitive keys (`model_provider`, auth, etc.) are not.

> [!WARNING]
> - On **native Windows + the VS Code extension**, repo-local config has been [reported ignored](https://github.com/openai/codex/issues/15993) — prefer the global config or `CODEX_HOME` there.
> - The exact "mark trusted" trigger isn't documented (typically a first-run prompt on entering a new folder). Verify locally.

**Heavier alternative — `CODEX_HOME`.** Pointing `CODEX_HOME` at a project-local folder relocates Codex's *entire* user root (config **and** credentials, history, state DB) there for that session. It works, but only reach for it when you want full isolation:

```powershell
$env:CODEX_HOME = "<repo>/.codex"; codex
```

---

## ✅ Verify

```powershell
codex mcp list
codex mcp get agent_chat
```

Inside a session, `/mcp` lists servers, or ask the agent directly:

> Do you see an MCP server called agent_chat? List the tools it exposes.

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status`. If not, check:

1. The TOML parses — `python -c "import tomllib; tomllib.load(open(r'C:\Users\<you>\.codex\config.toml','rb'))"` (silent = valid).
2. The launcher path exists and `pwsh` is on PATH.
3. `db/chat.db` exists or can be auto-created.
4. The header is exactly `[mcp_servers.agent_chat]`.

Codex reads `config.toml` once at launch — restart after edits.

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
4. Send the prompt to the `--first` agent first.
5. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fourth terminal).

</details>

---

## ⚠️ Known quirks

- **No per-folder override (global registration).** You can't run two Codex sessions with different `--agent-id` values in the same shell without rewriting `config.toml` between launches. This is why a second Codex **seat** (`codex-2`) relocates `CODEX_HOME` rather than shipping a project config like the other CLIs:

  ```powershell
  .\.venv\Scripts\python.exe scripts\setup\add_agent_seat.py --cli codex --seat 2
  ```

  That seeds `agents/CLIs/codex_agent2/.codex/config.toml` from your global config with the agent id rewritten, and `scripts/lib/spawn-agents.ps1` exports `CODEX_HOME` for seat 2+ at launch. **`CODEX_HOME` relocates the whole user root — credentials included — so run `codex login` once against the new home** (or copy `auth.json` into it) before that seat can do anything. A second OS user works too, and is the only option if you'd rather not duplicate credentials.
- **Server stderr is swallowed.** Codex doesn't surface MCP stderr. To debug a startup failure, run the launch command directly and watch the output:
  ```powershell
  pwsh -NoProfile -File "<repo>/scripts/run-mcp-server.ps1" codex
  ```
  The server prints to stderr and waits for stdio JSON-RPC; Ctrl-C to exit. Append `--db-path <path>` after `codex` to point at a non-default DB.
- **Tool-call cadence.** Codex tends to call `wait_for_turn` immediately after each `send_message` without intermediate prose — that's the desired loop shape, don't "fix" it with delays.

---

## 📚 Vendor documentation

If Codex's MCP behavior stops matching this page, check the source:

- MCP in Codex — <https://developers.openai.com/codex/mcp>
- Config reference — <https://developers.openai.com/codex/config-reference>
- CLI reference — <https://developers.openai.com/codex/cli/reference>
