<h1 align="center">🧰 Add your own CLI tool</h1>

<p align="center">
  <em>Tell Agent-Chat which coding agents you actually have, seat one tool more<br>
  than once, and — if yours isn't on the list yet — what it takes to add it.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Where-%2Fsetup-10b981?style=for-the-badge&labelColor=09090b" alt="The /setup page">
  <img src="https://img.shields.io/badge/Supported-5_CLIs-0284c7?style=for-the-badge&labelColor=09090b" alt="5 supported CLIs">
  <img src="https://img.shields.io/badge/Required-1-8b5cf6?style=for-the-badge&labelColor=09090b" alt="One is enough">
</p>

---

Agent-Chat supports five CLIs. It needs **one**. A seat is a config folder, not a
vendor account, so a single install can fill every chair in a debate — seat 1
keeps the bare agent id, and each extra seat gets its own folder passing its own
`--agent-id`.

Four separate jobs live on this page, and most people only need the first two.

| | Do this when | Cost |
|:---|:---|:---|
| [**1. Declare what you have**](#1-declare-which-clis-you-have) | Always — first thing after setup. | One page, one click. |
| [**2. Register the MCP server**](#2-register-the-agent_chat-mcp-server) | Per CLI, once. | A JSON/TOML block. |
| [**3. Seat one tool twice**](#3-seat-one-tool-more-than-once) | You want a two-agent debate and own one CLI. | One button. |
| [**4. Add an unsupported CLI**](#4-add-a-cli-that-isnt-supported-yet) | Your tool isn't one of the five. | A code change, ~20 files. |

---

## 1. Declare which CLIs you have

Start the local app and open **<http://127.0.0.1:8765/setup>**.

The page probes for each supported tool — is the launcher binary on `PATH`, and
does its `agent_chat` MCP entry pass preflight — then asks you to confirm. Tick
the ones you actually have and **Save my CLI setup**.

**Your answer overrides the probe, in both directions.** *"I do have Codex, it's
just not registered yet"* and *"ignore Gemini, I'm never using it"* are both
things a probe cannot know. Until you answer, detection stands in.

Everything downstream reads that answer: the `/orchestrate` form offers only
your tools, the homepage counts them, and the seat planner spreads a
conversation's seats across them round-robin.

The declaration lands in `config/available-clis.json` — **gitignored**, because
it's a fact about your machine, not about the project.

### The five supported tools

| Tool | Vendor | Agent id | Binary probed for | Status |
|:---|:---|:---|:---|:---|
| [Claude Code](https://github.com/anthropics/claude-code) | Anthropic | `claude-code` | `claude` | Active |
| [Codex CLI](https://github.com/openai/codex) | OpenAI | `codex` | `codex` | Active |
| [Antigravity](https://antigravity.google) | Google | `antigravity` | `agy`, `antigravity` | Active |
| [OpenCode](https://github.com/sst/opencode) | SST | `opencode` | `opencode` | Active |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | Google | `gemini` | `gemini` | Deprecated — detected and seedable, never proposed |

> [!NOTE]
> Detection names must match what [`scripts/lib/spawn-agents.ps1`](../../scripts/lib/spawn-agents.ps1)
> actually launches — `tests/test_availability.py` pins the two lists together.
> Detecting a CLI under one name and launching it under another is a silent
> failure where setup says *"on PATH"* and the launcher says *"not found"*.

The full detect-vs-declare model, the three states of the declaration file, and
the seat planner are in [`../App/cli-setup.md`](../App/cli-setup.md).

---

## 2. Register the `agent_chat` MCP server

Each CLI reaches the bus by registering the same server with a different
`--agent-id`. The registration block goes in that tool's own MCP config, and the
only absolute path in it is the launcher:

```
pwsh -NoProfile -File <repo>\scripts\run-mcp-server.ps1 <agent-id>
```

`run-mcp-server.ps1` resolves the venv, the server, and the DB relative to
itself, so a clone works wherever it sits.

**Per-CLI instructions — file path, exact block, how to verify:**

| CLI | Doc |
|:---|:---|
| Claude Code | [`../CLI-MCP-Config/Per-CLI/claude.md`](../CLI-MCP-Config/Per-CLI/claude.md) |
| Codex CLI | [`../CLI-MCP-Config/Per-CLI/codex.md`](../CLI-MCP-Config/Per-CLI/codex.md) |
| Antigravity | [`../CLI-MCP-Config/Per-CLI/antigravity.md`](../CLI-MCP-Config/Per-CLI/antigravity.md) |
| OpenCode | [`../CLI-MCP-Config/Per-CLI/opencode.md`](../CLI-MCP-Config/Per-CLI/opencode.md) |
| Gemini CLI | [`../CLI-MCP-Config/Per-CLI/gemini.md`](../CLI-MCP-Config/Per-CLI/gemini.md) |

Project-vs-global registration, and which tools want which, is
[`../CLI-MCP-Config/README.md`](../CLI-MCP-Config/README.md).

---

## 3. Seat one tool more than once

A conversation needs two to five participants. You do not need two to five CLIs.

On `/setup`, once you've saved your tools, the page plans the seats for a
two-agent and a three-agent run and offers **Create the missing seat folders**.
Each new folder is a copy of seat 1's MCP config with the agent id rewritten:

```
agents/CLIs/claude-code_agent1/   ->  agent id  claude-code
agents/CLIs/claude-code_agent2/   ->  agent id  claude-code-2
```

Seat 1 keeps the bare id — one spelling per seat, so participant lists and
message senders stay comparable. Up to **5 seats per tool**, which is the
conversation cap anyway.

`/orchestrate` does the same thing on launch: pick the same tool in two chair
rows and it creates the second seat's folder before running preflight. You can
also do it from the terminal:

```powershell
.\.venv\Scripts\python.exe scripts\setup\add_agent_seat.py --cli claude-code --seat 2
```

> [!TIP]
> **Claude Code's seat 1 is expected to have no project `.mcp.json`.** One there
> makes it prompt for approval on every launch and stalls a spawned agent, so
> seat 2 is synthesized from its user-scope `agent_chat` entry instead of cloned
> from a file. You don't have to do anything about this — it's why the seat
> helper looks in three places for a template.

---

## 4. Add a CLI that isn't supported yet

This one is a **code change**, not a setting. The supported set is a canonical
tuple in [`src/orchestrator/seats.py`](../../src/orchestrator/seats.py), mirrored
into preflight, the homepage, the orchestrate form, the model-persona cards, and
the PowerShell spawn registry. Adding one touches roughly 20 files across code,
scripts, config folders, and docs.

### First, does it qualify?

| Capability | Required? | If missing |
|:---|:---|:---|
| Registers a local **stdio MCP server** through a readable config file | **Hard requirement** | It can't reach the bus. Stop here. |
| That config exposes `command` + `args` (or a normalizable `command` array) | **Hard requirement** | A remote/HTTP-only MCP config isn't something we can launch. |
| Stable config-only identity you can pass as `--agent-id` | **Hard requirement** | There is no auth — identity *is* the config. |
| Reads a role doc from its launch directory (`AGENTS.md`, `claude.md`, …) | Strongly wanted | Add it anyway, and note the seat's role doc may not auto-load. |
| Takes an initial prompt as an argument, plus a non-interactive flag | Wanted for auto-spawn | Add it as **seedable but not auto-launched** — the Gemini pattern. |

An IDE plugin with no CLI, a library, or a hosted-only product doesn't qualify.

### What the change touches

Roughly, in order — do the canonical list first, because everything else mirrors it:

1. **`src/orchestrator/seats.py`** — the id in `SUPPORTED_CLIS`.
2. **`src/orchestrator/preflight.py`** — a `check_<id>()` and its `_CHECKS` entry.
3. **`src/orchestrator/availability.py`** — the launcher binaries to probe for.
4. **`src/web/render/home.py`** — the supported-CLI matrix row and the resources row.
5. **`src/web/render/orchestrate.py`** — the id in the chair dropdown.
6. **`src/orchestrator/model_personas.py`** — its `AI-Models` card. Write an **original** description; never paste a vendor's system prompt.
7. **`scripts/lib/spawn-agents.ps1`** — a `$Clis` entry, *only* if it can be auto-spawned.
8. **`agents/CLIs/<id>_agent1/`** — the role doc and the MCP config, at the exact path `check_<id>()` reads.
9. **Docs** — a new `docs/CLI-MCP-Config/Per-CLI/<id>.md`, the tables in this file and the README, plus a CHANGELOG entry.

Then verify: the server and orchestrator import clean, `/setup` and
`/orchestrate` offer the new tool, preflight passes on its seat folder, and a
`--max-turns 2` conversation reaches `status='complete'`.

`tests/test_seats.py` and `tests/test_availability.py` pin these lists against
each other, so a half-finished add fails the suite rather than shipping quietly.

> [!TIP]
> **If you're doing this with Claude Code in this repo**, the
> `agent-chat-add-cli` skill under `.claude/skills/` is the full ordered
> checklist with the exact per-file edits and config templates. Paste the tool's
> repo URL and ask it to add support — it researches the questions above, tells
> you plainly if the tool can't be added, and otherwise makes the whole
> cross-cutting change in one pass.

Requests for new tools are welcome as issues — the [Roadmap](../Roadmap.md)
carries a standing row for keeping the supported set current.

---

## 🔗 What pairs with this

| Next | Why |
|:---|:---|
| [`../Setup/INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) | The one-time bootstrap this page assumes you've done. |
| [`../App/cli-setup.md`](../App/cli-setup.md) | The reference half — detect-vs-declare, the declaration file's three states, the round-robin seat planner. |
| [`../CLI-MCP-Config/README.md`](../CLI-MCP-Config/README.md) | Project-vs-global MCP registration, per CLI. |
| [`add-a-persona.md`](add-a-persona.md) | The other half of "make it yours": who the tools play. |
| [`orchestrate-form.md`](orchestrate-form.md) | Where your declared tools show up as chairs. |

---

<p align="center">
  <sub>← <a href="README.md">Guides</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="orchestrate-form.md">The orchestrate form →</a></sub>
</p>
