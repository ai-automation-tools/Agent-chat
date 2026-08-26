# `collaborate-mode` skill

A layered Agent Skill that teaches a CLI agent how to behave in an `agent_chat` **collaboration** — composing on top of the base [`agent-chat`](../agent-chat/) skill, which handles the participation loop.

A collaboration is the third conversation type (see `conv_type` in [`src/orchestrator/conv_types.py`](../../src/orchestrator/conv_types.py)): two to five **collaborators**, where whichever one speaks first also holds the **facilitator** role. The facilitator is not a separate seat — unlike a podcast host, it contributes like everyone else. It's the counterpart to [`debate-mode`](../debate-mode/) and wants nearly the opposite instincts.

The one thing it teaches:

1. **The room is judged by what it produces, not by how it read.** A debate is worth reading; a collaboration is worth *using*.
2. **Build on other people's material.** The failure mode isn't conflict — it's parallel monologues, three complete answers with nobody reading anyone else's.
3. **The facilitator lands it.** Unlike a debate's moderator it *does* take positions, and on its last turn it writes the artifact and sends it with `signal='result'`.

Your seat isn't guesswork — `get_kickoff()` and every turn response return `conversation_type`, `your_role` (`facilitator` / `collaborator`), the full `roles` map, and a one-paragraph `role_brief`. Those fields are recorded on the conversation, so they're right even when the operator seeded it by hand and no launch prompt mentioned a role.

See [`SKILL.md`](SKILL.md) for the full guidance.

## Sub-types live on the preset

`collaborate` is one *structure*; what the room actually makes comes from the **preset**, which is the sub-type axis (see [`src/presets.py`](../../src/presets.py)):

| Preset | The artifact |
|:---|:---|
| `collaborate` | Whatever was asked for, written out in full |
| `brainstorm` | A ranked shortlist — diverge first, rank late |
| `plan` | Numbered steps with owners and a definition of done |
| `decide` | The decision, plus every option that lost and why |
| `solve` | Root cause, the evidence for it, and the fix |
| `code-review` | A verdict plus blocking issues, separated from suggestions |
| `design` | Components, interfaces, failure modes, tradeoffs taken |
| `validate` | Go / no-go, with the assumption most likely to kill it |

The shape reaches the agents through the rendered kickoff body, which `orchestrator.seeding` composes at seed time — so it's in `get_kickoff()`'s `instructions` on any CLI, skills installed or not.

## Install

`collaborate-mode` lives alongside `agent-chat` under the repo-root `skills/` folder, so the recommended install wires them all at once.

### Recommended: run the setup-link script once per clone

```powershell
# Windows — junctions every CLI's skills dir to repo-root skills/
.\scripts\setup\setup-skill-links.ps1
```

```bash
# macOS/Linux
./scripts/setup/setup-skill-links.sh
```

This links the repo-root `skills/` into each CLI's per-clone, gitignored config dir — `.claude/skills` (Claude Code), `.codex/skills` (Codex), `.agents/skills` (Antigravity), `.gemini/skills` (Gemini, deprecated fallback). Edits to `skills/collaborate-mode/SKILL.md` then propagate to every CLI. Re-run once per clone.

### Manual install (per-CLI reference)

Same per-CLI discovery paths as the base `agent-chat` skill — see [`../agent-chat/README.md`](../agent-chat/README.md). Substitute `collaborate-mode` wherever `agent-chat` appears:

```powershell
# Claude Code (project-local)
New-Item -ItemType Directory -Force "$PWD/.claude/skills/collaborate-mode" | Out-Null
Copy-Item "$PWD/skills/collaborate-mode/SKILL.md" "$PWD/.claude/skills/collaborate-mode/SKILL.md"

# Codex / Antigravity (project-local — .agents/skills/)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/collaborate-mode" | Out-Null
Copy-Item "$PWD/skills/collaborate-mode/SKILL.md" "$PWD/.agents/skills/collaborate-mode/SKILL.md"
```

Verify with `/skills` — `agent-chat` and `collaborate-mode` should both appear.

> [!NOTE]
> **OpenCode has no documented skills path**, so the link script doesn't cover it. It still behaves correctly in a collaboration: the facilitator/collaborator brief ships **in-band** on every `get_kickoff` and turn response (`role_brief`), and the deliverable's shape rides the kickoff body. The skill adds depth, not the basics.

## Verify end-to-end

Seed a collaboration — one facilitator, two collaborators, producing a plan:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --type collaborate `
  --participants claude-code,codex,antigravity `
  --host claude-code `
  --topic "How should we cut our cloud bill by 30%?" `
  --preset plan `
  --max-turns 4
```

In each CLI, give a one-line prompt: `join the agent_chat conversation`. Then check:

- The **facilitator** opens by restating the goal and putting down real material — not "let's hear everyone's thoughts."
- The **collaborators** build on each other by name, rather than each posting a complete separate answer.
- On the facilitator's **last** turn it posts the plan itself with `signal='result'`, and the conversation keeps running afterwards (a result is not a stop signal).

Watch it live at `http://127.0.0.1:8765/conversations/<id>` — the deliverable renders with an amber rule and a `RESULT` badge, and `/export.md` tags its heading with `` `signal=result` ``.

## Where the guidance is duplicated (keep in sync)

Two places, because not every CLI reads skills:

| Where | Why it exists |
|:---|:---|
| `skills/collaborate-mode/SKILL.md` (this) | The deep version, for CLIs that load skills |
| `_ROLE_BRIEFS` in [`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py) | Ships in-band with every turn payload and with `get_kickoff()` — works on any CLI, including a hand-seeded run |

The launch prompt in [`scripts/lib/spawn-agents.ps1`](../../scripts/lib/spawn-agents.ps1) used to be a third copy, one here-string per role. It no longer is: `New-AgentPrompt` is role-agnostic and points every agent at `role_brief`. Adding a seat means editing `_ROLE_BRIEFS` and this file — nothing in PowerShell.

The artifact's *shape* is a third thing and lives in [`src/presets.py`](../../src/presets.py) (`deliverable`), reaching agents through the kickoff body rather than either of the above.

---

<p align="center">
  <sub>← <a href="../README.md">Skills</a> · <a href="../../README.md">Agent-Chat</a> · <a href="../../docs/Guides/collaborate.md">Collaboration guide</a></sub>
</p>
