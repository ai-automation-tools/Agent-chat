---
name: agent-chat-add-cli
description: Add support for a new CLI agent (Claude Code / Codex / OpenCode style) to Agent-Chat from a pasted repo URL. Use when the operator says "add support for this CLI", "add a new CLI", "onboard <tool> as an agent", or pastes a coding-agent repo/docs URL and asks whether it can join the arena. Researches the candidate for MCP support, then either reports it CANNOT be added (with the specific reason) or performs the full cross-cutting change — canonical list, the code mirrors, spawn registry, per-CLI config folder, and every doc/site surface — as an ordered checklist so nothing is half-updated.
---

# Agent-Chat — Add support for a new CLI

Onboarding a CLI touches ~20 files across code, PowerShell, per-CLI config folders, docs, and the homepage. This skill is the authoritative checklist so no surface is missed. **Read [reference.md](reference.md) for the exact per-file edits and the config-file templates** — this file is the decision flow and the ordered task list.

## The two possible outcomes

The operator pastes a repo URL (e.g. `https://github.com/openai/codex`) and asks to add it. You end at exactly one of:

- **A — Cannot be added.** Report the specific blocking reason (see the disqualifiers in Step 2) and stop. Do not edit anything.
- **B — Added.** Make the full change below, verify it, then tell the operator the site is updated locally and ask whether to deploy the hosted mirror.

Never do a partial, silent add. If the CLI qualifies but can't be auto-spawned, that's still outcome B — you add it as *seedable but not auto-launched* (the Gemini pattern) and say so explicitly.

## Step 1 — Research the candidate

From the pasted URL, find out how the tool works. Use WebFetch on its README + docs pages, WebSearch for "<tool> MCP server config", and the `context7` MCP for its docs if available. You are answering four questions:

1. **MCP support (load-bearing).** Does the CLI let you register a **local stdio MCP server** via a config file? What is the config **file path** (repo-local dotfile? a global config in `~`?) and the **JSON/TOML shape** — which key holds servers (`mcpServers`? top-level `mcp`? `[mcp_servers]` TOML?), and does an entry take `command` + `args`, or a single `command` array (OpenCode style)?
2. **Role-doc / system prompt.** Does it auto-read an instructions file from its launch directory (`AGENTS.md` is the emerging standard; Claude Code reads `claude.md`, Gemini `GEMINI.md`)? That file is how the tester role loads.
3. **Launch as an unattended agent (needed for auto-spawn/debates).** Does the binary accept an **initial prompt as a CLI argument**, and is there a **skip-permissions / non-interactive** flag? What is the **binary name on PATH**?
4. **Identity.** Confirm you can pass a stable id/label — Agent-Chat's identity is config-only (`--agent-id`), there's no auth.

Summarise these four findings back to the operator before editing.

## Step 2 — Qualify or disqualify (the decision gate)

| Capability | Required? | If missing |
|:---|:---|:---|
| Registers a local **stdio MCP server** via a readable config file | **Hard requirement** | **Outcome A** — report "cannot be added: <tool> has no MCP-server support, so it can't reach the agent_chat bus." |
| Config exposes `command`+`args` (or a normalizable `command` array) | **Hard requirement** | Outcome A — "MCP config shape isn't a local command we can launch (e.g. remote/HTTP-only)." |
| Stable config-only identity | **Hard requirement** | Outcome A (rare) |
| Reads a role-doc from cwd | Strongly wanted | Add anyway; note the tester role may not auto-load |
| Takes an initial-prompt arg + unattended flag | Wanted for **auto-spawn** | Add as **seedable-only** (skip the `$Clis` spawn-registry entry, like Gemini) |

If any hard requirement fails → **Outcome A**: give the reason plainly and stop.
Otherwise → **Outcome B**: continue.

Also disqualify (Outcome A) if the URL isn't a CLI coding agent at all (a library, an IDE plugin with no CLI, a hosted-only product).

## Step 3 — Choose the identity

Pick the canonical **agent-id** (lowercase-hyphen slug, unique, e.g. `codex`, `opencode`), the **display name** ("Codex CLI"), and the **vendor** ("OpenAI"). This id must be identical everywhere in Step 4 and must match the `--agent-id` arg in the MCP config. Decide **active** vs **deprecated/fallback** (almost always active).

## Step 4 — Make the change (ordered checklist)

Do these in order. **Reference every list by its symbol name, not by line number** (lines drift). Full detail + exact snippets are in [reference.md](reference.md).

**Canonical (do first):**
1. `src/orchestrator/preflight.py` → add the id to `SUPPORTED_CLIS`; add a `check_<id>()` function (copy the closest-shaped existing checker); add a `_CHECKS` dispatch entry.

**Code mirrors:**
2. `src/web/render/home.py` → add a row to `_SUPPORTED_CLIS` (with active/status) **and** to `_CLI_RESOURCES` (repo + docs URLs); update the CLI-count stat and prose that say "Six"/"6".
3. `src/web/render/orchestrate.py` → add the id to `_ORCH_CLI_IDS` **and** add a hardcoded checkbox `<label>` block (they are not generated).
4. `src/orchestrator/model_personas.py` → add a `MODEL_CARDS` entry (display name, tags, an **original** description body — never paste a vendor system prompt). It becomes the AI-Models reference card.
   - `personas.py` and `web/api/orchestrate.py` consume the canonical tuple — **no change**.

**Scripts:**
5. `scripts/lib/spawn-agents.ps1` → add a `$Clis` entry (`Dir`/`Exe`/`PromptArg`/`SkipPerm`) — **only if auto-spawnable**. Skip for seedable-only CLIs.
6. `scripts/debate.ps1` → if you added a spawnable CLI, bump the `[ValidateSet(...)]` cap on `-Agents` and sync the help text.
7. `scripts/setup/setup-skill-links.ps1` (+ `.sh`) → add the workspace `.<id>/skills` junction target if you want runtime-skills parity.
8. `skills/start-debate/SKILL.md` → update the CLI-order / agent-count lines if the spawn registry changed. (This is a *runtime* skill read by live agents — keep it in sync.)

**Per-CLI config folder:**
9. Create `agents/CLIs/<id>_agent1/` with a **role doc** (`AGENTS.md` unless the CLI needs its own) and the **MCP config file** at the exact path `check_<id>()` reads, registering `agent_chat` → `pwsh -NoProfile -File scripts/run-mcp-server.ps1 <id>`. Use the matching template in reference.md.
10. `.gitignore` → add a `!`-unignore exception if the config lives in an otherwise-ignored dotfolder (follow the existing antigravity/opencode pattern).

**Docs:**
11. `README.md` (the CLI-registration table + the supported-CLIs badge), `docs/CLI-MCP-Config/README.md` (the three CLI tables), a **new** `docs/CLI-MCP-Config/Per-CLI/<id>.md`, `CLAUDE.md` (intro paragraph + the repo-tree `agents/CLIs/` annotation + this skill list if relevant), `docs/Guides/start-new-chat.md` (per-CLI config bullet), `docs/CHANGELOG.md` (new entry — copy the OpenCode entry as a template), `docs/Roadmap.md` (close any matching item Open→Done with today's date).

## Step 5 — Verify

Run these (PowerShell, venv interpreter):

```powershell
# server + orchestrator import clean
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import agent_chat_mcp, orchestrator.preflight, orchestrator.model_personas"
# new id is in the canonical tuple
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from orchestrator.preflight import SUPPORTED_CLIS; print('<id>' in SUPPORTED_CLIS)"
# homepage tiles + table render without error
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from web.render.home import _render_homepage_res_groups, _render_homepage_clis_table; assert '<id>' in _render_homepage_clis_table()"
# any .mcp.json/opencode.json you wrote is valid
.\.venv\Scripts\python.exe -m json.tool agents\CLIs\<id>_agent1\<config>.json
```

Then run `/smoke-test`. If the CLI is a real installed tool, optionally run the actual preflight (`run_preflight`) to confirm the config passes.

## Step 6 — Site + deploy

`src/web/render/home.py` runs on the **hosted Fly mirror** (`agent-chat-mikesailab`). Your homepage edits are live locally immediately but the public site needs a deploy. **Deploying is outward-facing — ask the operator before running it** (`/deploy-fly` or `fly deploy --app agent-chat-mikesailab`). Restart the local web UI if it needs to pick up the render change.

## Golden rules

- **`preflight.SUPPORTED_CLIS` is the single source of truth.** Every other list is a mirror that must match it exactly — a missed mirror is a silent bug (a CLI that preflights but never appears in the form, or has no persona card).
- **Never paste a vendor's system prompt** into the AI-Models card — write an original description.
- **One id, spelled identically** across code, scripts, config folder name, and the `--agent-id` arg.
- If unsure whether the CLI is auto-spawnable, add it **seedable-only** and say so — don't guess a spawn command that will hang a debate window.
