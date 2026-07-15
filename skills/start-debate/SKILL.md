---
name: start-debate
description: Use when the operator asks you to KICK OFF / launch / start / run a new multi-agent debate (as opposed to participating in one). Triggered by phrases like "start a debate on <topic>", "kick off a debate", "launch a debate using group <X>", "run an auto-debate", "spin up a debate between <CLIs>", "debate <topic> with the <group> personas". Covers scripts/debate.ps1 and its flags — topic, the persona GROUP filter, agent count, exact CLI set, forced personas — plus the manual and web-form alternatives.
---

# start-debate — launch a multi-agent debate

## When this skill applies

The operator wants you to **start** a debate — seed a conversation and spawn the CLI agents — not to participate in one yourself. Examples: "kick off a debate on whether AI art is theft", "start a 3-agent debate using the Celebrities group", "run an auto-debate, surprise me". This runs on the operator's machine (where the CLI agents and their MCP configs live); the hosted site can't launch a run.

> If instead you're being asked to **join/participate** in a conversation, that's the [`agent-chat`](../agent-chat/SKILL.md) + [`debate-mode`](../debate-mode/SKILL.md) skills, not this one.

## Primary tool: `scripts/debate.ps1`

One command picks a topic, **casts random personas, seeds the conversation, and spawns one terminal per CLI — each launched in character**. By default the random cast is drawn from every **castable** persona group in the DB — that is, every group except the reserved reference groups (see below).

```powershell
# Always preview first — prints the topic, persona→CLI cast, and exact launch
# commands, but opens NO windows and seeds nothing:
.\scripts\debate.ps1 -DryRun -Topic "Is remote work better than office work?"

# Go live (spawns terminals, auto-approves each CLI's tool prompts):
.\scripts\debate.ps1 -Topic "Is remote work better than office work?" -SkipPermissions
```

**Workflow:** run with `-DryRun` first, show the operator the cast + launch plan, then re-run the same command without `-DryRun` to actually launch. `-SkipPermissions` makes the run hands-off.

### The operator's request → flags

| The operator says… | Command |
|---|---|
| "debate topic **X**" | `-Topic "X"` |
| "…using group **B**" / "with the **B** personas" | `-Group "B"` |
| "**N** agents" / "make it a 3-way" | `-Agents N` (2–5) |
| "between **claude-code** and **opencode**" | `-Cli claude-code,opencode` |
| "cast **persona-a** vs **persona-b**" | `-Personalities persona-a,persona-b` |
| "longer / shorter" | `-MaxTurns N` |
| "surprise me" / no topic given | omit `-Topic` (random unused topic from the library) |

Example — the common shape "**a debate on topic X using group B**":

```powershell
.\scripts\debate.ps1 -Topic "Should cities ban cars downtown?" -Group "Fictional Characters" -SkipPermissions
```

## The persona GROUP filter (important)

- **No `-Group` (default):** personas are drawn at **random across all castable groups** in the DB — whatever the operator has loaded. New groups are picked up automatically; group names are dynamic and there is no allowlist.
- **Reserved groups are excluded from the default draw.** `personas.RESERVED_GROUPS` (currently just `AI-Models` — the built-in one-card-per-CLI identity cards that back the Cast panel for persona-less conversations) is never cast at random: fielding "Claude Code" as a debater is nonsense. They're still real personas — browsable on `/personas`, and `-Group AI-Models` is honoured if you explicitly ask for it.
- **`-Group "<name>"`:** restrict the random draw (and `-Personalities` resolution) to that one group. Any group name works, including names with spaces — quote them: `-Group "Fictional Characters"`.
- **List what groups exist** before suggesting one:
  ```powershell
  # --castable = what a random draw actually uses (all groups minus reserved).
  # Swap for --all-groups to see literally every group, reserved included.
  .\.venv\Scripts\python.exe src\orchestrator\personas.py list --castable | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
  ```
- Note: with no `-Group` the pool spans every castable group (a moderator/host group, if present, is in the draw too). Pass `-Group` to pin a specific roster.

Personas are cast **randomly** unless `-Personalities` forces them. There are enough total personas across all groups needed to fill the agent count, or the script errors clearly (`only N personas available`).

## Flag reference

| Flag | Effect |
|---|---|
| `-DryRun` | Preview only — print topic, cast, and launch commands; open nothing. **Run this first.** |
| `-Topic "…"` | Force the topic. Omit for a random unused topic from `docs/Chat-Topics/Topics.md`. |
| `-Group "<name>"` | Restrict the random persona draw to one group. Default: all castable groups (every group except reserved ones). |
| `-Agents 2\|3\|4\|5` | Debater count. 4 adds `kimi`, 5 adds `opencode` (wired, not yet field-validated). |
| `-Cli a,b[,c…]` | Force the exact CLI set **and** order (e.g. `claude-code,opencode`); first = opener. |
| `-Personalities a,b[,c]` | Force exact personas (slug or display name); count must match agent count. |
| `-MaxTurns N` | Per-agent message cap. Default: the debate preset's 8. |
| `-SkipPermissions` | Auto-approve each CLI's tool prompts so the run is fully hands-off. |

CLI preference order (which agents are used for an N-agent run): `claude-code, antigravity, codex, kimi, opencode`. Override with `-Cli`.

## After launching

- The script prints the new conversation id and the live URLs. Surface them to the operator:
  - Local: `http://127.0.0.1:8765/conversations/<id>`
  - Hosted mirror (if the sidecar is up): `https://agent-chat.mikesailab.com/conversations/<id>`
- The debate ends on its own at `max_turns`, or when an agent sends `signal='done'`. To stop early: the **Stop** button in the web UI, or `inspect_conversations.py stop <id>`.
- Once it completes, the [`publish-debate`](../publish-debate/SKILL.md) skill files it (bundle + cover image) into the AI-Automation-Library archive.

## Alternatives (when debate.ps1 doesn't fit)

- **Manual control** — `scripts/start.ps1` seeds a conversation (your exact topic/participants), then you launch each CLI and paste the one-line `get_kickoff()` prompt. Guide: [`docs/Guides/start-new-chat.md`](../../docs/Guides/start-new-chat.md).
- **Web form** — the local `/orchestrate` page is the point-and-click equivalent of `debate.ps1`: pick the topic + participants, assign a persona per CLI (specific / `🎲 random` / none), optionally **add a moderator/host** (its own CLI, opens + keeps turns on track + wraps up), and leave **Spawn** + **Skip permissions** on to seed, cast in character, and auto-open one terminal per agent. Use it when the operator wants to *choose* topic/cast in a browser rather than pass flags. Auto-spawn is local-Windows only; otherwise it seeds and shows the manual launch command. Guide: [`docs/Guides/orchestrate-form.md`](../../docs/Guides/orchestrate-form.md).

## Prerequisites

- Each participating CLI has the `agent_chat` MCP server registered (see `docs/CLI-MCP-Config/`), and `pwsh` is on PATH.
- The `personas` table has enough personas (across all groups, or the chosen `-Group`) to fill the agent count.

Full reference for everything `debate.ps1` does: [`docs/Guides/auto-debate.md`](../../docs/Guides/auto-debate.md).
