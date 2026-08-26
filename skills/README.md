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

> OpenCode was added later and isn't covered by the link script yet — see the
> "Wire the Agent Skills into OpenCode" row in
> [`docs/Roadmap.md`](../docs/Roadmap.md).

---

## The skills

| Skill | What it does | Triggers on | Docs |
|:---|:---|:---|:---|
| **[`agent-chat`](agent-chat/SKILL.md)** | The base **participation loop** (role-agnostic). Drives an agent through `get_kickoff` → `wait_for_turn` → `send_message` on its own — including `signal='done'` / `'blocked'` semantics, turn-taking, and the "don't ask the operator between turns" rule. | "join the agent_chat conversation", "participate in the conversation", "call `get_kickoff`", or being spawned by the debate launcher. | [SKILL](agent-chat/SKILL.md) · [install](agent-chat/README.md) |
| **[`debate-mode`](debate-mode/SKILL.md)** | Layers on top of `agent-chat` to teach an agent how to **argue well** — take a falsifiable position, cite the other side specifically, concede where warranted, and avoid hedging filler. | "argue for X", "defend the position", "debate this topic", "take the side that…", or a conversation seeded with `--preset debate`. | [SKILL](debate-mode/SKILL.md) · [install](debate-mode/README.md) |
| **[`podcast-mode`](podcast-mode/SKILL.md)** | The counterpart to `debate-mode` for the other conversation type: a **podcast** — one host who interviews, plus 1–4 guests. Teaches the opposite instincts. The host asks and never argues a side; the guests answer at length with something concrete; nobody manufactures conflict. | `conversation_type: "podcast"` with a `your_role` of `host` or `guest` in the kickoff / turn payload, "you're hosting a podcast", "you're a guest on". | [SKILL](podcast-mode/SKILL.md) · [install](podcast-mode/README.md) |
| **[`collaborate-mode`](collaborate-mode/SKILL.md)** | The third conversation type: a **collaboration** — two to five collaborators working toward an artifact rather than a transcript, where whichever speaks first also facilitates. Teaches the instincts a debate punishes: build on other people's material, converge, record surviving disagreement honestly, and end with the facilitator posting the deliverable via `signal='result'`. What the room makes comes from the **preset** — eight sub-types, from `brainstorm` (ranked shortlist) through `decide` (the call plus why the others lost) to `solve` (root cause and fix). | `conversation_type: "collaborate"` with a `your_role` of `facilitator` or `collaborator`, "work together on", "brainstorm with the other agents". | [SKILL](collaborate-mode/SKILL.md) · [install](collaborate-mode/README.md) |
| **[`battleground`](battleground/SKILL.md)** | The **AgentBattleground** loop: argue in a debate captured from a real web page rather than against another CLI. Drives `get_arena` → `submit_draft` → `wait_for_verdict`, and carries the two rules the feature depends on — **you draft, a human posts**, and a persona is a *voice*, never a claimed identity. | "join the battleground", "argue in this thread", "fight in arena N", "call `get_arena`". | [SKILL](battleground/SKILL.md) · [install](battleground/README.md) |
| **[`start-debate`](start-debate/SKILL.md)** | The operator-side counterpart: how to **launch** a multi-agent debate — seed a conversation and spawn the CLIs — primarily via [`scripts/debate.ps1`](../scripts/debate.ps1) (topic, persona group, agent count, CLI set, forced personas), plus the manual and web-form alternatives. | "start a debate on <topic>", "kick off a debate", "run an auto-debate", "spin up a debate between <CLIs>". | [SKILL](start-debate/SKILL.md) · [install](start-debate/README.md) |
| **[`publish-debate`](publish-debate/SKILL.md)** | The operator-side **after** step: **publish** a finished debate into the AI-Automation-Library archive — run [`scripts/publish_debate.py`](../scripts/publish_debate.py) (bundle straight from `chat.db`, no ZIP), then generate the `cover-image.png` from the embedded master cover prompt. | "publish conversation #N to the library", "add that debate to the AI library", "generate a cover for the debate". | [SKILL](publish-debate/SKILL.md) · [install](publish-debate/README.md) |
| **[`humanizer`](humanizer/SKILL.md)** | Strips the patterns that mark text as AI-written — puffery vocabulary, the rule of three, `-ing` pseudo-analysis, negative parallelisms. Vendored from Wikipedia's *Signs of AI writing*. **Delivered in-band, not by skill match** — see below. | "humanize this", "make this sound less like AI", "why does this read as generated". | [SKILL](humanizer/SKILL.md) · [install + wiring](humanizer/README.md) |

> [!IMPORTANT]
> **`humanizer` is wired differently from the other six.** Skills load lazily by
> `description` match, and an agent mid-debate is *generating*, not *editing* —
> so a skill described as "use when editing text" would never fire on a
> `send_message` turn. The rules that matter mid-turn are therefore shipped
> **in-band**: in the [kickoff template](../prompts/Kickoff/kickoff.md), in
> `_ARENA_RULES` (rule 7), and in [`debate-mode`](debate-mode/SKILL.md). That
> also covers OpenCode, which the linker doesn't reach. The skill
> itself is the deep reference and the explicit editing pass. Full rationale:
> [`humanizer/README.md`](humanizer/README.md).
>
> **Persona voice always wins** — humanizing removes machine tells; it must not
> normalize distinct personas into one register.

---

## How they fit together

Two jobs, two sets of skills:

- **Participating in a conversation** — `agent-chat` is always in play; then
  **one** of `debate-mode` / `podcast-mode` / `collaborate-mode` layers on
  according to the conversation's type. They don't conflict with the base skill
  (`agent-chat` governs the *loop*, the other shapes the *content*) but they are
  alternatives to each other: `get_kickoff()` returns `conversation_type` and
  `your_role`, so which one applies is never a guess.
- **Participating in a *web* debate** — `battleground` replaces `agent-chat`'s loop
  (different tools, no turn order, a human review step) while `debate-mode`'s
  content guidance still applies.
- **Launching a conversation** — `start-debate` runs on the operator's machine
  (where the CLIs and their MCP configs live) to seed + spawn a run. The hosted
  site can't launch agents; see the local-only `/orchestrate` page.
- **Publishing the result** — `publish-debate` (also operator-side) files the
  finished debate + a generated cover into the AI-Automation-Library archive.

```
launch ──────────────►  participate ─────────────────►  publish ──────────────►
start-debate            agent-chat                      publish-debate
                         + ONE of debate-mode /
                           podcast-mode / collaborate-mode
(operator seeds +       (each spawned agent runs the    (bundle + cover into the
 spawns the CLIs)        get_kickoff → … loop)           AI-Automation-Library)
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

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../prompts/README.md">Prompts</a> · <a href="../docs/Guides/README.md">Guides</a></sub>
</p>
