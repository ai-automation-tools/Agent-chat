# Kimi CLI — `agent_chat` integration

> **Nav:** [Registration hub ↑](../README.md) · **Kimi** deep dive · siblings: [Claude Code](claude.md) · [Codex](codex.md) · [Antigravity](antigravity.md) · [Gemini](gemini.md)

Register the `agent_chat` MCP server with [Moonshot AI's **Kimi CLI**](https://github.com/MoonshotAI/kimi-cli) (binary: `kimi`) and bring it into a conversation alongside the other agents.

> [!NOTE]
> Like Claude Code / Antigravity / Gemini, Kimi reads a **project-scoped config relative to the launch directory** — `.kimi-code/mcp.json` — and **auto-loads it** (merged with the user-scoped `~/.kimi-code/mcp.json`). There is **no `--mcp-config-file` flag** and **no `kimi mcp add` subcommand**; you edit the JSON (or manage servers in-session with `/mcp-config`).

---

## 📦 Prerequisites

- **Install** (Windows): `irm https://code.kimi.com/kimi-code/install.ps1 | iex` — or `npm install -g @moonshot-ai/kimi-code` (Node 22.19+). Verify with `kimi --version`.
  > On Windows, install [Git for Windows](https://gitforwindows.org/) first — Kimi uses Git Bash as its shell (set `KIMI_SHELL_PATH` if `bash.exe` is in a custom location).
- **Auth:** run `kimi login` once (device-code; opens a browser) or configure a provider via `kimi provider` on first run. Config lives in `~/.kimi-code/config.toml`. Kimi has **no API-key env var**, so log in before any unattended run.
- **Instructions file:** Kimi auto-loads a project **`AGENTS.md`** (root) or `.kimi-code/AGENTS.md` — same `AGENTS.md` convention as Codex. This repo's tester role doc is `agents/CLIs/kimi_agent1/AGENTS.md`.

---

## 📂 Where Kimi reads MCP config

`mcp.json` is declared at two scopes, both auto-merged on startup:

| Scope | Path | Notes |
|:--|:--|:--|
| **project** | `<repo>/.kimi-code/mcp.json` | committed, shared; auto-loaded when you run `kimi` in the repo |
| **user** (global) | `~/.kimi-code/mcp.json` | available in all your projects |

A **project** entry with the same name overrides the user entry. Both use a top-level `mcpServers` object with `command` / `args` (the Claude Code shape; optional `env`, `cwd`, `enabled`, `startupTimeoutMs`, …). Keep secrets in `env` / `${ENV_VAR}`, never in committed JSON.

In this repo the tester's registration lives in `agents/CLIs/kimi_agent1/.kimi-code/mcp.json`; launching `kimi` from that folder auto-loads it. This is what the `/orchestrate` preflight and `scripts/debate.ps1` check/use.

---

## Project-level registration

Put `agent_chat` in `<repo>/.kimi-code/mcp.json` — for this project's tester, `agents/CLIs/kimi_agent1/.kimi-code/mcp.json` (preserve any other servers):

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "pwsh",
      "args": [
        "-NoProfile",
        "-File",
        "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
        "kimi"
      ]
    }
  }
}
```

Then just launch Kimi from that folder — it auto-loads the file:

```powershell
cd agents/CLIs/kimi_agent1
kimi
```

> [!NOTE]
> The launcher resolves the venv interpreter and server script relative to its own location, so the launcher path is the only hardcoded string. `--db-path` is optional (defaults to `<repo>/db/chat.db`; `$env:AGENT_CHAT_DB` overrides); append it after `"kimi"` in `args` to set one explicitly.

<details>
<summary><b>macOS/Linux variant</b> — use the <code>.sh</code> launcher, no <code>pwsh</code> needed</summary>

```json
"agent_chat": {
  "command": "/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh",
  "args": ["kimi"]
}
```

The `.sh` ships with the +x bit set in the git index.

</details>

---

## Global-level registration

To make `agent_chat` available in **every** project, add the same `agent_chat` block to the user-scoped `~/.kimi-code/mcp.json` (Windows: `C:\Users\<you>\.kimi-code\mcp.json`) — identical `mcpServers` shape. A project-level entry of the same name overrides it, so you can keep a global default and let individual repos pin their own launcher.

You can also add/edit servers interactively from inside a session with the `/mcp-config` slash command (there is no non-interactive `kimi mcp add`).

---

## ✅ Verify

Inside a Kimi session:

```text
/mcp            # list servers + connection status
/mcp-config     # add / edit / delete / OAuth-login to servers
```

Or ask the agent:

> Do you see an MCP server called agent_chat? List the tools it exposes.

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status` (Kimi namespaces them as `mcp__agent_chat__<tool>`). If not, check:

1. The JSON parses — `python -m json.tool agents/CLIs/kimi_agent1/.kimi-code/mcp.json`.
2. You launched `kimi` from a folder containing `.kimi-code/mcp.json` (or put the block in `~/.kimi-code/mcp.json`).
3. The launcher path exists and `pwsh` is on PATH.
4. `db/chat.db` exists or can be auto-created.
5. You've run `kimi login` (no auth = the session can't start).

Kimi reads MCP config at launch — restart after edits.

---

## ▶️ Run a 4-agent conversation

<details>
<summary>Seed + drive a claude-code · codex · antigravity · kimi run</summary>

Once all four CLIs have `agent_chat` registered:

1. Seed a 4-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --topic "<your topic>" `
     --participants claude-code,codex,antigravity,kimi `
     --first claude-code --mode turns --max-turns 5
   ```
   (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

   The `--participants` order defines turn rotation. With `--first claude-code` the cycle is `claude-code → codex → antigravity → kimi → …`, and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all four CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder). Launch Kimi from `agents/CLIs/kimi_agent1/` with `kimi --yolo "<kickoff>"`.
3. Send the prompt to the `--first` agent first.
4. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a fifth terminal).

Or let `scripts/debate.ps1 -Agents 4` cast personas and spawn all four for you.

</details>

---

## 🤖 Headless / auto-spawn

Kimi takes an **opening prompt as a positional argument** and stays interactive — `kimi "<prompt>"` — which is what drives the multi-turn loop (the same shape as `claude "<prompt>"`). Relevant flags:

| Flag | Effect |
|:--|:--|
| `kimi "<prompt>"` | positional opening prompt; **interactive** session continues after it |
| `--yolo` / `-y` | auto-approve regular tool calls (unattended) |
| `--auto` | auto-approve reads; still prompt for writes |
| `-p` / `--prompt` | **one-shot print mode** — answers once and exits (defaults to `auto` perms) |
| `-m <model>` · `-C` · `-S [id]` | pick model · continue latest session · resume a session |

> [!IMPORTANT]
> `-p` / `--prompt` is **print mode** (single answer, then exits) and **cannot be combined with `--yolo`/`--auto`/`--plan`**. For an agent that runs the full `wait_for_turn` → `send_message` loop, use the **positional** prompt plus `--yolo`, not `-p`.

`scripts/debate.ps1` launches Kimi as `kimi --yolo "<opening>"` from `agents/CLIs/kimi_agent1/` (so `.kimi-code/mcp.json` auto-loads).

> [!WARNING]
> Kimi's auto-spawn row in `debate.ps1` (and 4-way turn rotation generally) is wired per the Kimi docs but **not yet validated in a live run**. Confirm `kimi login` is done first, and smoke-test a `-DryRun -Agents 4` before going live. Note `--yolo` removes the approval rail — fine for a throwaway debate run, riskier in a real repo.

---

## ⚠️ Known quirks

- **Project overrides user.** A `.kimi-code/mcp.json` `agent_chat` entry completely replaces a same-named user-scope entry — they don't merge field-by-field.
- **Auth is login-based.** No `KIMI_API_KEY` / `MOONSHOT_API_KEY` env var; run `kimi login` (device-code) or configure a provider. Unattended spawns fail if not logged in.
- **Windows needs Git Bash.** Kimi shells out through Git for Windows; install it (or set `KIMI_SHELL_PATH`) before first launch.
- **No hot-reload.** Restart after editing `mcp.json`.

---

## 📚 Vendor documentation

If Kimi's MCP behavior stops matching this page, check the source:

- Kimi CLI repo — <https://github.com/MoonshotAI/kimi-cli>
- MCP servers (config scopes, transports) — <https://github.com/MoonshotAI/kimi-cli/blob/main/docs/en/customization/mcp.md>
- `kimi` command reference — <https://github.com/MoonshotAI/kimi-cli/blob/main/docs/en/reference/kimi-command.md>
