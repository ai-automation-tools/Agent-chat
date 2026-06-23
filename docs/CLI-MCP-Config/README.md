# Registering the `agent_chat` MCP server with each CLI

This is the **canonical reference** for wiring the `agent_chat` MCP server into every supported CLI — **at both the project level and the global (user) level**. It covers Claude Code, Codex CLI, Antigravity CLI, and the deprecated Gemini CLI.

For the per-CLI deep dives (verification walkthroughs, a 3-agent run recipe, and known quirks), see the files under [`Per-CLI/`](Per-CLI/). This page is the quick, side-by-side "where does the config go and what do I paste" reference; the `Per-CLI/` pages are the long-form companions.

> [!IMPORTANT]
> **`agents/` is local-only.** The per-CLI tester workspaces under `agents/CLIs/` (and the configs inside them) are `.gitignore`d and never shipped. The paths below assume **this repo's** layout, but the mechanism is identical for any clone — only the launcher path string changes.

---

## The one thing that differs between CLIs: `--agent-id`

Every CLI registers the **same** launcher script and the **same** server name (`agent_chat`). The launcher — [`scripts/run-mcp-server.ps1`](../../scripts/run-mcp-server.ps1) on Windows, [`scripts/run-mcp-server.sh`](../../scripts/run-mcp-server.sh) on POSIX — resolves the venv interpreter (`.venv\Scripts\python.exe`) and the server script (`src\agent_chat_mcp.py`) **relative to its own location**. So:

- The **only hardcoded path** in any config is the launcher path itself. Cloning to a different drive/folder = edit one string per config.
- The **only value that differs** between CLIs is the trailing positional arg — the `--agent-id` (`claude-code`, `codex`, `antigravity`, `gemini`). That identity is what turn rotation, message attribution, and the web-UI participant labels key off. **Don't rename it.**

> [!NOTE]
> **`--db-path` is optional.** The server defaults to `<repo>/db/chat.db`, resolved from `src/agent_chat_mcp.py`'s own location; set `$env:AGENT_CHAT_DB` to override globally. To pass an explicit `--db-path`, append it after the agent-id in the `args` array — the launcher forwards extra args verbatim to the Python child.

> [!NOTE]
> **Requires `pwsh` (PowerShell 7+) on PATH.** Install with `winget install Microsoft.PowerShell` on Windows. On macOS/Linux, either install `pwsh`, **or** swap the registration for the `.sh` launcher form — `"command": "/abs/path/to/scripts/run-mcp-server.sh"`, `"args": ["<agent-id>"]` — which is directly executable (the `.sh` ships with the +x bit set in the git index). Forward slashes work fine for Windows paths; if you must use backslashes in JSON, double them (`"D:\\AI_Agents\\..."`).

Throughout this doc, `LAUNCHER` is shorthand for:

```
D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1
```

---

## At a glance — project vs global, per CLI

| CLI | **Project level** (per-folder / per-repo) | **Global level** (user-wide, every session) |
|:---|:---|:---|
| **Claude Code** | `.mcp.json` in the launch dir, **or** `claude mcp add -s project` | `claude mcp add -s user` → `~/.claude.json` |
| **Codex CLI** | `.codex/config.toml` in the repo (**trusted** projects only), **or** point `CODEX_HOME` at a project-local folder | `~/.codex/config.toml`, **or** `codex mcp add` (always writes global) |
| **Antigravity CLI** | `.agents/mcp_config.json` in the launch dir *(verify locally — see caveat)* | `~/.gemini/config/mcp_config.json` |
| **Gemini CLI** *(deprecated)* | `.gemini/settings.json` in the launch dir, **or** `gemini mcp add -s project` | `~/.gemini/settings.json`, **or** `gemini mcp add -s user` |

> [!TIP]
> **Project vs global — which to pick.**
> - **Project level** keeps the registration scoped to a launch folder. Good for this project's tester workspaces (each CLI launches from its own `agents/CLIs/<name>_agent1/`), and it means other folders/sessions don't pay the startup cost or report a failed server if the venv path moves.
> - **Global level** registers `agent_chat` once for **every** session on the machine, regardless of cwd. Convenient if you always want it available — but every session then pays the (small) startup cost, and if the venv path ever stops existing, every session will report a failed server until you fix it. The server itself only does work when an agent actually calls one of its tools.

After **any** registration change, **restart the CLI** — none of these CLIs reliably hot-reload a newly added server from disk.

---

## Claude Code

Claude Code supports **three** scopes. The two that matter here are **project** and **user** (= global); a third, **local**, is the default and is private-to-you-and-this-project (stored in `~/.claude.json` under a project-specific key).

| Scope | Stored in | Visible to | Committed? |
|:---|:---|:---|:---|
| `project` | `.mcp.json` at the launch dir / repo root | anyone who has the file | yes (if you commit it) |
| `user` (global) | `~/.claude.json` (top-level `mcpServers`) | you, every project | no — machine-private |
| `local` (default) | `~/.claude.json` (project-scoped key) | you, this project only | no |

Precedence when the same name exists in more than one scope: **local → project → user** (closest wins). In practice, register in exactly one.

### Project level

In this repo the per-folder config lives at `agents/CLIs/claude-code_agent1/.mcp.json`; launching `claude` from that folder is what activates it. Add `agent_chat` inside the existing `mcpServers` object (preserve any other servers):

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "pwsh",
      "args": [
        "-NoProfile",
        "-File",
        "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
        "claude-code"
      ]
    }
  }
}
```

Or let the CLI write it for you (the `--` separator is required — everything after it is the launch command):

```powershell
claude mcp add -s project agent_chat -- pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" claude-code
```

> The **first** time Claude Code sees a project-scoped server it shows a one-time approval prompt (so a cloned repo can't silently launch processes). Approve it, or run `/mcp` later to approve. Reset choices with `claude mcp reset-project-choices`.

### Global (user) level

```powershell
claude mcp add -s user agent_chat -- pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" claude-code
```

This writes to `~/.claude.json` (Windows: `%USERPROFILE%\.claude.json`) and makes `agent_chat` available in every Claude Code session on the machine.

### Verify

```powershell
claude mcp list           # status per server (✓ connected / ✗ failed / ⏸ pending approval)
claude mcp get agent_chat # resolved config + which file defines it + any error
```

Inside a session, `/mcp` shows live status. Editing `.mcp.json` does **not** hot-reload — quit and relaunch.

**Full walkthrough:** [`Per-CLI/claude.md`](Per-CLI/claude.md).

---

## Codex CLI

> [!IMPORTANT]
> The `codex mcp add` / `list` / `get` / `remove` commands **always operate on the global** `~/.codex/config.toml`. There is **no** CLI command that writes a project-scoped config — for project scoping you edit the file by hand (or use `CODEX_HOME`).

### Global level (the supported default)

Edit `~/.codex/config.toml` (Windows: `C:\Users\<you>\.codex\config.toml`; create the file and `.codex/` folder if missing) and append:

```toml
[mcp_servers.agent_chat]
command = "pwsh"
args = [
  "-NoProfile",
  "-File",
  "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
  "codex",
]
```

Or let the CLI write it (writes the same global file):

```powershell
codex mcp add agent_chat -- pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" codex
```

### Project level

Current Codex CLI **does** read a repo-local `.codex/config.toml` — but **only for projects you've marked trusted** (an untrusted project skips all project-scoped `.codex/` layers). The same `[mcp_servers.agent_chat]` block shown above goes in `<repo>/.codex/config.toml`; the closest-to-cwd file wins. A plain stdio `[mcp_servers.*]` entry is allowed at project scope (security-sensitive keys like `model_provider` are not).

> [!WARNING]
> Two caveats from upstream:
> - On **native Windows + the VS Code extension**, repo-local `.codex/config.toml` has been [reported to be ignored](https://github.com/openai/codex/issues/15993). On that setup, prefer the global config or `CODEX_HOME`.
> - The exact "mark trusted" trigger isn't spelled out in the official docs (it's typically a first-run prompt when you enter a new folder). Verify locally.

**Heavier alternative — `CODEX_HOME`:** pointing `CODEX_HOME` at a project-local folder containing a `config.toml` relocates Codex's *entire* user root (config **and** credentials, history, state DB) there for that session. It works, but it's heavier-handed than a trusted-project config — use it only when you want full isolation of the Codex home:

```powershell
$env:CODEX_HOME = "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/.codex"; codex
```

### Verify

```powershell
codex mcp list
codex mcp get agent_chat
```

Inside a session, `/mcp` lists servers. Codex reads `config.toml` at launch — restart after edits.

> [!NOTE]
> **TOML gotchas.** The table header must be exactly `[mcp_servers.agent_chat]` (TOML keys are case-sensitive). Use **forward slashes** in the Windows path — backslashes are TOML escape chars (`"D:\Users"` tries to interpret `\U`). A missing comma between array elements is a parse error and Codex will silently start *without* the server, so if `/mcp` doesn't list it, suspect the TOML first.

**Full walkthrough:** [`Per-CLI/codex.md`](Per-CLI/codex.md).

---

## Antigravity CLI

Antigravity (CLI binary: `agy`) is the successor to the Gemini CLI. There is **no `agy mcp add` subcommand** — manage servers by editing the JSON file directly, or interactively via the `/mcp` slash command inside an `agy` session.

### Project level

The per-workspace config is `.agents/mcp_config.json`, resolved relative to the launch directory. In this repo it lives at `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` — and unlike the rest of `.agents/`, this one file **is tracked in git**, so any secret in it must use `${ENV_VAR}` substitution, never an inlined key. Add `agent_chat` inside `mcpServers`:

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "pwsh",
      "args": [
        "-NoProfile",
        "-File",
        "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
        "antigravity"
      ]
    }
  }
}
```

> [!WARNING]
> **Verify project-local loading in your installed version.** An upstream issue ([antigravity-cli #60](https://github.com/google-antigravity/antigravity-cli/issues/60)) reported a project-local `mcp_config.json` being *discovered but silently ignored*, with only the global file actually spawning servers. That report used an older path, so it may be stale — but smoke-test that a server defined **only** in `.agents/mcp_config.json` shows up under `/mcp`. If it doesn't, fall back to the global file below.

### Global level

Edit `~/.gemini/config/mcp_config.json` (Windows: `C:\Users\<you>\.gemini\config\mcp_config.json`) — note it lives under `~/.gemini/`, **not** `~/.antigravity/`. This is the shared file read by Antigravity 2.0, the IDE, and the CLI. Same `mcpServers` shape as above.

### Verify

After saving, launch `agy` from the workspace and use the `/mcp` slash command (the "MCP server manager") to confirm `agent_chat` is listed. You can also ask it: *"Do you see an MCP server called agent_chat? List the tools it exposes."* Editing the config likely needs a restart (hot-reload is undocumented).

**Full walkthrough (incl. headless / `--dangerously-skip-permissions` and auto-spawn):** [`Per-CLI/antigravity.md`](Per-CLI/antigravity.md).

---

## Gemini CLI *(deprecated — kept as a fallback)*

> [!WARNING]
> Google deprecated the Gemini CLI; use **Antigravity** for new setups. This section is retained for anyone still running the Gemini tester directly.

Gemini CLI has a real `gemini mcp add` command with a `-s` / `--scope` flag (`project` is the default, `user` is global).

### Project level

`.gemini/settings.json` relative to the launch dir (in this repo: `agents/CLIs/gemini_agent1/.gemini/settings.json`). Either edit it directly:

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "pwsh",
      "args": [
        "-NoProfile",
        "-File",
        "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
        "gemini"
      ]
    }
  }
}
```

…or let the CLI write it (project is the default scope):

```powershell
gemini mcp add agent_chat pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" gemini
```

### Global (user) level

```powershell
gemini mcp add -s user agent_chat pwsh -NoProfile -File "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1" gemini
```

This writes `~/.gemini/settings.json` (Windows: `C:\Users\<you>\.gemini\settings.json`).

> [!NOTE]
> If any launch arg begins with `-` and the parser mis-claims it, separate the server command from its args with `--`, e.g. `gemini mcp add agent_chat -- pwsh -NoProfile -File "<LAUNCHER>" gemini`. Test whether `-NoProfile` / `-File` need the guard in your version.

### Verify

`/mcp` inside a session lists servers; `/mcp refresh` re-discovers tools from *already-configured* servers, but **adding a new server in `settings.json` does not take effect without a restart** ([#3528](https://github.com/google-gemini/gemini-cli/issues/3528), [#4786](https://github.com/google-gemini/gemini-cli/issues/4786)).

**Full walkthrough:** [`Per-CLI/gemini.md`](Per-CLI/gemini.md).

---

## After registering — run a conversation

Once the CLIs you want have `agent_chat` registered, seed a conversation and drive it. See [`docs/Guides/start-new-chat.md`](../Guides/start-new-chat.md) for the daily-driver recipe, or any `Per-CLI/*.md` for a self-contained 3-agent run.

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --topic "<your topic>" `
  --participants claude-code,codex,antigravity `
  --first claude-code --mode turns --max-turns 5
```

---

## Vendor documentation

The config mechanisms above are external-vendor behavior and can change. When something stops matching this doc, check the source:

| CLI | Official MCP docs |
|:---|:---|
| **Claude Code** | <https://docs.claude.com/en/docs/claude-code/mcp> |
| **Codex CLI** | <https://developers.openai.com/codex/mcp> · [config reference](https://developers.openai.com/codex/config-reference) |
| **Antigravity CLI** | <https://antigravity.google/docs> · [MCP in Antigravity codelab](https://codelabs.developers.google.com/developer-knowledge-mcp-antigravity) |
| **Gemini CLI** | <https://geminicli.com/docs/tools/mcp-server/> · [MCP setup tutorial](https://geminicli.com/docs/cli/tutorials/mcp-setup/) |
| **MCP spec** | <https://modelcontextprotocol.io> |

Each `Per-CLI/*.md` page repeats the relevant vendor link in its own footer so the deep dives stay self-verifiable.
