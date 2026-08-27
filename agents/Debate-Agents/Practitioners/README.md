# Practitioners — work-role personas for collaborations

Seed cards for the `Practitioners` persona group: roles you'd want **around a
table**, as opposed to the entertainment cards the debate roster is built from.
A debate wants Gordon Ramsay; a collaboration wants someone who has shipped a
migration.

Like every folder here, these are a **one-time import seed**, not the runtime
source. The `personas` table in `db/chat.db` is the source of truth — edit these
cards on the [`/personas`](http://127.0.0.1:8765/personas) page, not in git.
See [`docs/App/personas.md`](../../../docs/App/personas.md).

## The cards

Each is written to pair with a `collaborate` sub-type (`src/presets.py`), because
the sub-type decides what the room hands back and these decide who is arguing
about it.

| Card | Pairs with | Argues for |
|:---|:---|:---|
| Full-Stack Developer | `solve`, `plan`, `audit` | cohesion end to end; naming what a choice costs |
| Systems Architect | `design` | committing to one shape, and recording the rejected one |
| Product Designer | `design`, `brainstorm` | the empty, error and slow states; a named user |
| Product Strategist | `validate`, `decide` | sequence, and the cheapest test that changes the answer |
| Idea Generator | `brainstorm` | staying open one turn longer, then ranking honestly |
| Code Reviewer | `code-review`, `audit` | a verdict, with blocking kept apart from preference |
| Critical Thinker | `decide`, `validate` | reasoning that survives being examined |
| Researcher | `validate`, `decide`, `brainstorm` | evidence graded, and "nobody knows this yet" said out loud |
| Security Researcher | `audit`, `design`, `validate` | the attacker's goal, not a control checklist |
| Business Analyst | `plan`, `validate`, `collaborate` | requirements with owners, models with visible assumptions |
| Creative Writer | `brainstorm`, `collaborate` | the words as the product; cutting until it lands |

## Why they are shaped this way

Every card carries five sections beyond `## Purpose`: **what I bring** (the
domain substance), **what I argue for**, **what I won't let slide**, **where I
clash**, and **how I work in this room**.

The last two are the ones that don't come from any source agent, and they are the
reason these work at all:

- **Where I clash** names the other cards this one predictably disagrees with.
  A collaboration's two failure modes are parallel monologues and agreement with
  no addition (see [`skills/collaborate-mode`](../../../skills/collaborate-mode/SKILL.md));
  friction written into the cards is the cheapest defence against the second.
- **How I work in this room** converts a *worker* into a *participant*. It says
  the card contributes rather than chairs, brings file paths rather than
  impressions, and — for the two cards whose sources are pure interrogators —
  that a turn spent only asking questions added nothing.

## Provenance

The domain substance is adapted from
[`davila7/claude-code-templates`](https://github.com/davila7/claude-code-templates)
(MIT, © 2025 Daniel Ávila) — the repository behind [aitmpl.com](https://www.aitmpl.com/agents/).
Each card's frontmatter names the file it came from in `adapted_from`.

They are adaptations, not copies. The sources are Claude Code **subagent
definitions**: tool lists, `Query context manager` preambles, communication
protocols, implementation workflows, and "Integration with Other Agents"
sections pointing at agents that don't exist here. All of that is wrong for a
turn-based conversation and was removed. What was kept is the expertise — the
checklists, the anti-patterns, the things a good practitioner refuses to accept.

One of the eleven has no source at all: **Creative Writer** is written from
scratch, because a catalogue of coding agents has no creative-writing agent and
dressing a copywriter up as one would have been the wrong card.

Three of the sources needed more than trimming:

- **`critical-thinking`** instructs the agent to *never* propose a solution.
  In a room that owes a deliverable, that makes it a passenger — so the card
  probes and then commits to a position.
- **`simple-app-idea-generator`** interviews a human with a list of questions.
  There is no human in the room, so the card generates and builds on other
  agents' material instead.
- **`business-analyst`** and **`market-researcher`** open with *"ask the user
  for…"* and carry human-in-the-loop pause criteria. Nobody is there to answer
  between turns, so those cards draft first and put the draft up to be argued
  with — a proposed requirement someone can reject beats a question inviting
  them to write one.

---

<div align="center">

[⬆ Debate-Agents](../) · [🏠 Repo root](../../../README.md)

</div>
