# `podcast-mode` skill

A layered Agent Skill that teaches a CLI agent how to behave in an `agent_chat` **podcast** — composing on top of the base [`agent-chat`](../agent-chat/) skill, which handles the participation loop.

A podcast is the second conversation type (see `conv_type` in [`src/orchestrator/conv_types.py`](../../src/orchestrator/conv_types.py)): one **host** plus one to four **guests**, five seats total. It's the counterpart to [`debate-mode`](../debate-mode/) and wants the opposite instincts.

The one thing it teaches:

1. **The host asks; it never argues a side, and never answers its own question.** Short turns, one real follow-up each, chase the specific claim.
2. **The guests answer, at length, with something concrete.** Stories and numbers, not positions.
3. **Nobody manufactures conflict.** Disagree where you genuinely do; this isn't a contest.

Your seat isn't guesswork — `get_kickoff()` and every turn response return `conversation_type`, `your_role` (`host` / `guest`), the full `roles` map, and a one-paragraph `role_brief`. Those fields are recorded on the conversation, so they're right even when the operator seeded it by hand and no launch prompt mentioned a role.

See [`SKILL.md`](SKILL.md) for the full guidance.

## Install

`podcast-mode` lives alongside `agent-chat` under the repo-root `skills/` folder, so the recommended install wires them all at once.

### Recommended: run the setup-link script once per clone

```powershell
# Windows — junctions every CLI's skills dir to repo-root skills/
.\scripts\setup\setup-skill-links.ps1
```

```bash
# macOS/Linux
./scripts/setup/setup-skill-links.sh
```

This links the repo-root `skills/` into each CLI's per-clone, gitignored config dir — `.claude/skills` (Claude Code), `.codex/skills` (Codex), `.agents/skills` (Antigravity), `.gemini/skills` (Gemini, deprecated fallback). Edits to `skills/podcast-mode/SKILL.md` then propagate to every CLI. Re-run once per clone.

### Manual install (per-CLI reference)

Same per-CLI discovery paths as the base `agent-chat` skill — see [`../agent-chat/README.md`](../agent-chat/README.md). Substitute `podcast-mode` wherever `agent-chat` appears:

```powershell
# Claude Code (project-local)
New-Item -ItemType Directory -Force "$PWD/.claude/skills/podcast-mode" | Out-Null
Copy-Item "$PWD/skills/podcast-mode/SKILL.md" "$PWD/.claude/skills/podcast-mode/SKILL.md"

# Codex / Antigravity (project-local — .agents/skills/)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/podcast-mode" | Out-Null
Copy-Item "$PWD/skills/podcast-mode/SKILL.md" "$PWD/.agents/skills/podcast-mode/SKILL.md"
```

Verify with `/skills` — `agent-chat` and `podcast-mode` should both appear.

> [!NOTE]
> **OpenCode has no documented skills path**, so the link script doesn't cover it. It still behaves correctly in a podcast: the host/guest brief ships **in-band** on every `get_kickoff` and turn response (`role_brief`), and the spawn launcher writes a role-specific opening prompt. The skill adds depth, not the basics.

## Verify end-to-end

Seed a podcast — one host, two guests:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --type podcast `
  --participants claude-code,codex,antigravity `
  --host claude-code `
  --topic "Has remote work actually settled anywhere?" `
  --preset podcast `
  --max-turns 4
```

In each CLI, give a one-line prompt: `join the agent_chat conversation`. Then check:

- The **host** opens by introducing the topic and both guests, and its later turns are short and end in a question.
- The **guests** answer the question that was asked and bring something concrete.
- Nobody argues a side from the host's chair, and no guest delivers a closing summary.

Watch it live at `http://127.0.0.1:8765/conversations/<id>` — the Cast panel labels each seat, with the host accented.

## Where the guidance is duplicated (keep in sync)

The same host/guest rules exist in two places, because not every CLI reads skills and not every conversation has a launch prompt:

| Where | Why it exists |
|:---|:---|
| `skills/podcast-mode/SKILL.md` (this) | The deep version, for CLIs that load skills |
| `_ROLE_BRIEFS` in [`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py) | Ships in-band with every turn payload and with `get_kickoff()` — works on any CLI, including a hand-seeded run |

Change one, change the other.

> [!NOTE]
> There used to be a **third** copy: `New-AgentPrompt` in
> [`scripts/lib/spawn-agents.ps1`](../../scripts/lib/spawn-agents.ps1) carried one
> here-string per role. It doesn't any more — the launch prompt is role-agnostic
> and points every agent at `get_kickoff()`'s `role_brief`. Adding or changing a
> seat no longer touches PowerShell.
