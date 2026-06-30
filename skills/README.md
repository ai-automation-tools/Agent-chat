# Agent Skills

This folder holds the **Agent Skills** that teach CLI agents how to behave in an
`agent_chat` conversation. Each skill is a small Markdown file in the open
[Agent Skills standard](https://developers.openai.com/codex/skills) — a
`SKILL.md` with YAML frontmatter (`name`, `description`) — loaded lazily by the
CLI when its `description` matches what the operator asked for.

The same `SKILL.md` works across **Claude Code, Codex, and Antigravity** (Gemini
CLI is a deprecated fallback). They're wired into each CLI's own (gitignored)
config dir by [`scripts/setup/setup-skill-links.ps1`](../scripts/setup/setup-skill-links.ps1)
/ [`.sh`](../scripts/setup/setup-skill-links.sh), run once per clone.

> Kimi and OpenCode were added later and aren't covered by the link script yet —
> see the "Wire the Agent Skills into Kimi + OpenCode" row in
> [`docs/Roadmap.md`](../docs/Roadmap.md).

---

## The skills

| Skill | What it does | Triggers on | Docs |
|:---|:---|:---|:---|
| **[`agent-chat`](agent-chat/SKILL.md)** | The base **participation loop** (role-agnostic). Drives an agent through `get_kickoff` → `wait_for_turn` → `send_message` on its own — including `signal='done'` / `'blocked'` semantics, turn-taking, and the "don't ask the operator between turns" rule. | "join the agent_chat conversation", "participate in the conversation", "call `get_kickoff`", or being spawned by the debate launcher. | [SKILL](agent-chat/SKILL.md) · [install](agent-chat/README.md) |
| **[`debate-mode`](debate-mode/SKILL.md)** | Layers on top of `agent-chat` to teach an agent how to **argue well** — take a falsifiable position, cite the other side specifically, concede where warranted, and avoid hedging filler. | "argue for X", "defend the position", "debate this topic", "take the side that…", or a conversation seeded with `--preset debate`. | [SKILL](debate-mode/SKILL.md) · [install](debate-mode/README.md) |
| **[`start-debate`](start-debate/SKILL.md)** | The operator-side counterpart: how to **launch** a multi-agent debate — seed a conversation and spawn the CLIs — primarily via [`scripts/debate.ps1`](../scripts/debate.ps1) (topic, persona group, agent count, CLI set, forced personas), plus the manual and web-form alternatives. | "start a debate on <topic>", "kick off a debate", "run an auto-debate", "spin up a debate between <CLIs>". | [SKILL](start-debate/SKILL.md) · [install](start-debate/README.md) |

---

## How they fit together

Two jobs, two sets of skills:

- **Participating in a conversation** — `agent-chat` is always in play; `debate-mode`
  layers on when the conversation is a debate. Both can fire at once; they don't
  conflict (`agent-chat` governs the *loop*, `debate-mode` shapes the *content*).
- **Launching a conversation** — `start-debate` runs on the operator's machine
  (where the CLIs and their MCP configs live) to seed + spawn a run. The hosted
  site can't launch agents; see the local-only `/orchestrate` page.

```
launch ──────────────►  participate ──────────────►
start-debate            agent-chat   (+ debate-mode when it's a debate)
(operator seeds +       (each spawned agent runs the
 spawns the CLIs)        get_kickoff → wait_for_turn → send_message loop)
```

---

## Install

Each skill folder contains:

- **`SKILL.md`** — the canonical behaviour, identical across every CLI.
- **`README.md`** — per-CLI discovery paths + a verification recipe.

The recommended install links the whole `skills/` tree into each CLI's config
dir in one step (edits to a `SKILL.md` then propagate everywhere):

```powershell
# Windows — directory junctions
.\scripts\setup\setup-skill-links.ps1
```

```bash
# macOS / Linux — symlinks
./scripts/setup/setup-skill-links.sh
```

The link dirs are gitignored, so re-run this once per clone / new machine. For
manual per-CLI paths and end-to-end verification, see each skill's `README.md`
(linked in the table above).

---

## Adding a new skill

Create `skills/<name>/SKILL.md` (plus a `README.md`) in the same format. The
setup-link script links **every** subfolder of `skills/`, so a new skill is
picked up automatically — no script edit needed. Then add a row to the table
above, and keep the `SKILL.md` in sync whenever the behaviour it documents
changes (stale guidance silently misleads the agents that read it at runtime).
