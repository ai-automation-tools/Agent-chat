# `agent-chat` skill — participation rules for multi-CLI conversations

A role-agnostic Agent Skill that teaches a CLI agent (Claude Code, Codex, or Antigravity) how to participate in an `agent_chat` MCP conversation **autonomously** — no operator hand-holding between turns. (Gemini CLI is a deprecated fallback — Antigravity replaced it.)

Replaces the "paste a 30-line kickoff prompt into every CLI" workflow. After installing the skill once per CLI, the operator (or the future orchestrator) only has to say "join the agent_chat conversation" and each agent runs the `get_kickoff` → `wait_for_turn` → `send_message` loop on its own until the conversation completes.

## One file, every CLI

The [Agent Skills standard](https://developers.openai.com/codex/skills) is supported by the target CLIs — Claude Code, Codex CLI, and Antigravity (plus the deprecated Gemini CLI) — using the same `SKILL.md` format with YAML frontmatter (`name`, `description`). Each CLI looks for skills in a slightly different directory tree, but the file itself is identical.

This folder contains:

| File | Purpose |
|---|---|
| [`SKILL.md`](SKILL.md) | The canonical skill. Identical content across all CLIs. |
| `README.md` (this file) | Per-CLI install paths + verification. |

## Install

The canonical skills live at the repo root under `skills/` (`agent-chat`, `debate-mode`). Each CLI discovers skills in its own config dir, so the skill folder has to appear in each.

### Recommended: run the setup-link script once per clone

Rather than copying `SKILL.md` into each CLI by hand, link every CLI's skills dir to the repo-root `skills/` folder in one step. Edits to `skills/agent-chat/SKILL.md` then propagate to every CLI automatically.

```powershell
# Windows — creates directory junctions into each CLI's gitignored config dir
.\scripts\setup\setup-skill-links.ps1
```

```bash
# macOS/Linux — creates symlinks
./scripts/setup/setup-skill-links.sh
```

This wires the repo-root `skills/` into each CLI's per-clone link dir:

| CLI | Link dir |
|---|---|
| Claude Code | `.claude/skills` |
| Codex | `.codex/skills` |
| Gemini (deprecated fallback) | `.gemini/skills` |
| Antigravity | `.agents/skills` |

The link dirs are gitignored, so re-run the script once per clone / new machine.

### Manual install (per-CLI reference)

If you'd rather place `SKILL.md` by hand, the per-CLI discovery paths are below. Copy or symlink — symlinks let you edit the source in `skills/agent-chat/SKILL.md` and keep all installs in sync automatically.

#### Claude Code

Claude Code reads skills from `.claude/skills/` (project) and `~/.claude/skills/` (user).

```powershell
# Project-local (this repo only)
New-Item -ItemType Directory -Force "$PWD/.claude/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$PWD/.claude/skills/agent-chat/SKILL.md"

# Or user-global (every Claude Code session on this machine)
New-Item -ItemType Directory -Force "$HOME/.claude/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$HOME/.claude/skills/agent-chat/SKILL.md"
```

Verify with `/skills` inside Claude Code — `agent-chat` should appear in the list.

#### Codex CLI

Codex scans (in priority order): `$CWD/.agents/skills/`, walks up to the repo root, then `~/.agents/skills/`, then `/etc/codex/skills/`. **Also `.codex/skills/`** in the working directory — not listed in the [official docs](https://developers.openai.com/codex/skills) but confirmed working empirically (skill shows up in `/skills`).

```powershell
# Project-local — standard path (this repo only)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$PWD/.agents/skills/agent-chat/SKILL.md"

# Or user-global
New-Item -ItemType Directory -Force "$HOME/.agents/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$HOME/.agents/skills/agent-chat/SKILL.md"
```

Verify with `/skills` inside Codex.

#### Antigravity

Antigravity reads skills from `.agents/skills/` resolved relative to the working directory it's launched from (same directory tree Codex uses for `.agents/`).

```powershell
# Project-local (this repo only)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$PWD/.agents/skills/agent-chat/SKILL.md"
```

Launch Antigravity from `agents/CLIs/antigravity_agent1/` and verify with `/skills`.

#### Gemini CLI (deprecated fallback)

> Gemini CLI has been deprecated in favor of Antigravity. These paths are kept only for fallback runs.

Gemini reads from `.gemini/skills/`, `.agents/skills/`, and the same paths under `~/`. **`.agents/skills/` takes precedence within the same tier**, which means a single install at `~/.agents/skills/agent-chat/` covers both Codex and Gemini.

```powershell
# Project-local (this repo only)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$PWD/.agents/skills/agent-chat/SKILL.md"
# (Identical to the Codex install — one folder, both CLIs pick it up.)

# Or user-global — same trick covers Codex too:
New-Item -ItemType Directory -Force "$HOME/.agents/skills/agent-chat" | Out-Null
Copy-Item "$PWD/skills/agent-chat/SKILL.md" "$HOME/.agents/skills/agent-chat/SKILL.md"
```

Verify with `/skills` inside Gemini. Use `/skills enable agent-chat --scope workspace` if Gemini doesn't auto-activate it for a given project.

#### Project-local installs in the tester workspaces (`agents/CLIs/<cli>_agent1/`)

When you launch a CLI from its `agents/CLIs/<cli>_agent1/` folder, it also discovers skills in its **own config dir** alongside its existing settings:

| Tester workspace | Working install path |
|---|---|
| `agents/CLIs/claude-code_agent1/` | `agents/CLIs/claude-code_agent1/.claude/skills/agent-chat/SKILL.md` |
| `agents/CLIs/codex_agent1/` | `agents/CLIs/codex_agent1/.codex/skills/agent-chat/SKILL.md` |
| `agents/CLIs/antigravity_agent1/` | `agents/CLIs/antigravity_agent1/.agents/skills/agent-chat/SKILL.md` |
| `agents/CLIs/gemini_agent1/` (deprecated) | `agents/CLIs/gemini_agent1/.gemini/skills/agent-chat/SKILL.md` |

This is what the `scripts/setup/setup-skill-links.ps1` / `.sh` script (or `/skills install`, or asking the CLI to install it for you) does by default in these workspaces — the skill ends up in the CLI's own per-folder config dir next to its MCP config. Those dirs (`.claude/`, `.codex/`, `.agents/`, `.gemini/`) are gitignored, so each machine needs its own install. Re-run the setup script after cloning to a new machine.

For Codex this path isn't in the official discovery list ([developers.openai.com/codex/skills](https://developers.openai.com/codex/skills) shows only `.agents/skills/`), but it works empirically. For Gemini `.gemini/skills/` is documented.

#### Manual symlink alternative

If you'd rather not use the setup script, symlink the source folder into each discovery location so edits to `skills/agent-chat/SKILL.md` propagate everywhere with no re-copy:

```powershell
# Requires Windows Developer Mode (for non-admin symlink creation) or an elevated shell.
New-Item -ItemType SymbolicLink -Path "$HOME/.claude/skills/agent-chat" -Target "$PWD/skills/agent-chat"
New-Item -ItemType SymbolicLink -Path "$HOME/.agents/skills/agent-chat" -Target "$PWD/skills/agent-chat"
```

POSIX equivalent:
```bash
ln -s "$PWD/skills/agent-chat" "$HOME/.claude/skills/agent-chat"
ln -s "$PWD/skills/agent-chat" "$HOME/.agents/skills/agent-chat"
```

## Verify end-to-end

1. Seed a short conversation:
   ```powershell
   .\.venv\Scripts\python.exe src\start_conversation.py `
     --participants claude-code,codex `
     --topic "Skill smoke test" `
     --preset debate `
     --max-turns 2
   ```
2. In two terminals, launch each CLI with no preamble beyond a single line: `join the agent_chat conversation`.
3. Each agent should call `get_kickoff()` on its own, then enter the `wait_for_turn` → `send_message` loop without asking the operator anything until the conversation hits `complete`.

If an agent asks "should I continue?" between turns, the skill isn't loading. Re-run `/skills` inside that CLI; if `agent-chat` isn't listed, recheck the install path against the table above.

## Relationship to the existing tester role docs

`agents/CLIs/claude-code_agent1/claude.md` (and `CLAUDE.md`), `agents/CLIs/codex_agent1/AGENTS.md`, and `agents/CLIs/gemini_agent1/GEMINI.md` are **tester role docs** — they cover the same participation loop plus testing-specific sections ("What to test for", "Reporting") that are not appropriate for a general participation skill.

The `SKILL.md` here is **role-agnostic** — suitable for debate, code review, brainstorm, plan, or any other preset. The tester role docs are intentionally left alone; they remain the source of truth for tester-mode sessions. If you find yourself maintaining both for the same rule, the skill is canonical and the tester docs should just reference it.

## What's next

This skill is the building block that other pieces compose on:

- **[`debate-mode`](../debate-mode/SKILL.md)** — a second skill layered on top of this one that instructs an agent to argue a position, cite the other side specifically, and avoid hedging filler. Already shipped.
- **One-click debate orchestrator** — `scripts/debate.ps1` auto-spawns each CLI into the loop from a one-line prompt. That's only possible because of the skill.
