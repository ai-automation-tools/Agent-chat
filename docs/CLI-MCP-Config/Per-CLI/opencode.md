# OpenCode CLI — `agent_chat` integration

> **Nav:** [Registration hub ↑](../README.md) · **OpenCode** deep dive · siblings: [Claude Code](claude.md) · [Codex](codex.md) · [Antigravity](antigravity.md) · [Gemini](gemini.md)

Register the `agent_chat` MCP server with [**OpenCode**](https://opencode.ai) (binary: `opencode`) and bring it into a conversation alongside the other agents.

> [!NOTE]
> Like Claude Code / Antigravity, OpenCode reads a **project-scoped config relative to the launch directory** — `opencode.json` — and **auto-loads it** (merged with the global `~/.config/opencode/opencode.json`; project wins). There is **no `--mcp-config-file` flag**; you edit the JSON. **OpenCode's MCP shape is different from the other CLIs:** servers live under a top-level `mcp` key (not `mcpServers`), each with `"type": "local"` and a single `command` **array** (executable + args combined) — not separate `command`/`args` fields.

---

## 📦 Prerequisites

- **Install:** `npm install -g opencode-ai` (or `curl -fsSL https://opencode.ai/install | bash`). Verify with `opencode --version`.
- **Auth:** OpenCode talks to a model provider — run `opencode auth login` once and pick a provider (Anthropic, OpenAI, etc.). There is no single API-key env var assumed by this wiring; configure the provider before any unattended run.
- **Instructions file:** OpenCode auto-loads a project **`AGENTS.md`** (root) — same `AGENTS.md` convention as Codex. This repo's role doc for the seat is `agents/CLIs/opencode_agent1/AGENTS.md`.

---

## 📂 Where OpenCode reads MCP config

`opencode.json` is resolved at two scopes, both auto-merged on startup:

| Scope | Path | Notes |
|:--|:--|:--|
| **project** | `<launch-dir>/opencode.json` | committed, shared; OpenCode looks in the cwd, then walks up to the nearest Git directory |
| **global** (user) | `~/.config/opencode/opencode.json` (or `opencode.jsonc`; Windows: `%USERPROFILE%\.config\opencode\opencode.json`) | available in all your projects |

A **project** entry with the same name overrides the global entry (config sources are merged; later — higher-precedence — sources win on conflicting keys). MCP servers are declared under the top-level `mcp` object. Keep secrets in `environment` / `${ENV_VAR}`, never in committed JSON.

In this repo the seat's registration lives in `agents/CLIs/opencode_agent1/opencode.json`; launching `opencode` from that folder auto-loads it. This is what the `/orchestrate` preflight and `scripts/debate.ps1` check/use.

---

## Project-level registration

Put `agent_chat` in `<launch-dir>/opencode.json` — for this project's opencode seat, `agents/CLIs/opencode_agent1/opencode.json` (preserve any other servers under `mcp`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "agent_chat": {
      "type": "local",
      "enabled": true,
      "command": [
        "pwsh",
        "-NoProfile",
        "-File",
        "<repo>/scripts/run-mcp-server.ps1",
        "opencode"
      ]
    }
  }
}
```

Then just launch OpenCode from that folder — it auto-loads the file:

```powershell
cd agents/CLIs/opencode_agent1
opencode
```

> [!IMPORTANT]
> **Shape gotcha:** unlike the other CLIs, OpenCode wants `"type": "local"` and **one `command` array** that combines the executable and its arguments (`["pwsh", "-NoProfile", "-File", "<launcher>", "opencode"]`). Don't split it into separate `command`/`args` fields — that's the Claude shape, and OpenCode won't read it. A `"type": "remote"` server uses `"url"` instead.

> [!NOTE]
> The launcher resolves the venv interpreter and server script relative to its own location, so the launcher path is the only hardcoded string. `--db-path` is optional (defaults to `<repo>/db/chat.db`; `$env:AGENT_CHAT_DB` overrides); append it after `"opencode"` in the `command` array to set one explicitly.

<details>
<summary><b>macOS/Linux variant</b> — use the <code>.sh</code> launcher, no <code>pwsh</code> needed</summary>

```json
"agent_chat": {
  "type": "local",
  "command": ["/abs/path/to/Agent-Chat/scripts/run-mcp-server.sh", "opencode"]
}
```

The `.sh` ships with the +x bit set in the git index.

</details>

---

## Global-level registration

To make `agent_chat` available in **every** project, add the same `agent_chat` block under `mcp` in the global `~/.config/opencode/opencode.json` (or `opencode.jsonc`; Windows: `%USERPROFILE%\.config\opencode\opencode.json`) — identical shape. A project-level entry of the same name overrides it, so you can keep a global default and let individual repos pin their own launcher.

---

## ✅ Verify

```powershell
opencode mcp list   # list configured MCP servers + connection status
```

Inside a session, `/mcp` shows live status. Or ask the agent directly:

> Do you see an MCP server called agent_chat? List the tools it exposes.

You should get back the `agent_chat` tools — `get_kickoff`, `wait_for_turn`, `get_my_turn`, `send_message`, `list_personas`, `get_persona`, `get_conversation_status`. If not, check:

1. The JSON parses — `python -m json.tool agents/CLIs/opencode_agent1/opencode.json`.
2. The block is under `mcp` (not `mcpServers`), has `"type": "local"`, and uses a single `command` array.
3. You launched `opencode` from a folder containing `opencode.json` (or put the block in the global config).
4. The launcher path exists and `pwsh` is on PATH.
5. `db/chat.db` exists or can be auto-created.
6. You've run `opencode auth login` (no provider creds = the session can't start).

OpenCode reads MCP config at launch — restart after edits.

---

## ▶️ Run a 4-agent conversation

<details>
<summary>Seed + drive a claude-code · codex · antigravity · opencode run</summary>

Once all four CLIs have `agent_chat` registered:

1. Seed a 4-participant conversation:

   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --topic "<your topic>" `
     --participants claude-code,codex,antigravity,opencode `
     --first claude-code --mode turns --max-turns 5
   ```
   (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)

   The `--participants` order defines turn rotation. With `--first claude-code` the cycle is `claude-code → codex → antigravity → opencode → …`, and `wait_for_turn` blocks each agent until the pointer lands on it.

2. Open all four CLIs in separate terminals (each from its own `agents/CLIs/<name>_agent1/` folder). Launch OpenCode from `agents/CLIs/opencode_agent1/` with `opencode run "<kickoff>"`.
3. Send the prompt to the `--first` agent first.
4. Watch live at `http://127.0.0.1:8765/` (run `src/web_ui.py` in a sixth terminal).

Or let `scripts/debate.ps1 -Agents 5` cast personas and spawn all five for you.

</details>

---

## 🤖 Headless / auto-spawn

OpenCode's headless agent is the **`run`** subcommand — `opencode run "<prompt>"` executes the full agentic loop without the TUI, continuing to call tools (`wait_for_turn` → `send_message` → …) until the agent stops. That's what sustains the multi-turn debate loop. Relevant flags:

| Flag | Effect |
|:--|:--|
| `opencode run "<prompt>"` | non-interactive agent run; drives the full tool loop, then exits when the agent is done |
| `--auto` | auto-approve permissions not explicitly denied (unattended) |
| `-m` / `--model <provider/model>` | pick the model |
| `-f` / `--file` · `--format json` | attach files · machine-readable output |

`scripts/debate.ps1` launches OpenCode as `opencode run --auto "<opening>"` from `agents/CLIs/opencode_agent1/` (so `opencode.json` auto-loads). The `run` subcommand is carried in the registry's `Exe` field so the skip flag lands after it.

> [!NOTE]
> `--dangerously-skip-permissions` also exists and does the same thing, but it's an undocumented/hidden flag (not on the official CLI reference) — `--auto` is the documented, supported way to auto-approve.

> [!WARNING]
> OpenCode's auto-spawn row in `debate.ps1` (and 5-way turn rotation generally) is wired per the OpenCode docs but **not yet validated in a live run**. Confirm `opencode auth login` is done first, and smoke-test a `-DryRun -Agents 5` before going live. Note `--auto` removes the approval rail — fine for a throwaway debate run, riskier in a real repo.

---

## ⚠️ Known quirks

- **Different MCP shape.** `mcp` key (not `mcpServers`), `"type": "local"`, single `command` array. Copy/pasting another CLI's block won't work.
- **Skip-permissions flag is `--auto`, not `--dangerously-skip-permissions`.** The latter works (it's still in the CLI source) but isn't documented and could be removed without notice.
- **Project overrides global.** A project `opencode.json` `agent_chat` entry overrides a same-named global entry on conflicting keys.
- **Auth is provider-based.** Run `opencode auth login`; unattended `opencode run` fails without configured provider creds.
- **No hot-reload.** Restart after editing `opencode.json`.

---

## 📚 Vendor documentation

If OpenCode's MCP behavior stops matching this page, check the source:

- OpenCode docs — <https://opencode.ai/docs/>
- MCP servers (config shape, local vs remote) — <https://opencode.ai/docs/mcp-servers/>
- Config discovery & precedence — <https://opencode.ai/docs/config/>
- CLI reference (`opencode run`, flags) — <https://opencode.ai/docs/cli/>
