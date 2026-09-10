# `humanizer` skill

Removes the patterns that mark text as AI-written — puffery vocabulary, the rule
of three, `-ing` pseudo-analysis, negative parallelisms, em-dash overuse, vague
attribution. Based on Wikipedia's *Signs of AI writing* (WikiProject AI Cleanup).

**Provenance:** vendored 2026-08-01 from
the maintainer's local skills library (outside this repo)
at upstream **v2.3.0**, unmodified. `LICENSE` ships alongside it. Re-copy the
upstream `SKILL.md` to update; don't hand-edit the vendored copy or the next
sync silently reverts you.

---

## How this one is wired — read this first

Unlike the other four skills, **this skill is not the primary delivery
mechanism.** Skills load *lazily, by description match*, and this one's
description is "use when editing or reviewing text." An agent about to call
`send_message` mid-debate is **generating**, not editing — it will never match.

So the rules that matter mid-turn are shipped **in-band** instead, in three
places, mirroring how `_ARENA_RULES` works:

| Site | Reaches |
|:---|:---|
| [`prompts/Kickoff/kickoff.md`](../../prompts/Kickoff/kickoff.md) — inside the `` ```text `` template block | Every seeded conversation (auto-debate, manual seed, `/orchestrate`), via the rendered `kickoff_template` returned by `get_kickoff()` |
| `_ARENA_RULES` in [`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py) — rule 7 | Every AgentBattleground arena reply |
| [`skills/debate-mode/SKILL.md`](../debate-mode/SKILL.md) — *Write like a person* | Debates, on CLIs that load skills |

The in-band route also covers **OpenCode**, which the skill linker doesn't
reach (see *Install* below).

**This skill is the deep reference** — the full 24 KB pattern catalogue with
before/after examples, for when the distilled block isn't enough or when you
want to run an explicit editing pass.

> [!IMPORTANT]
> **Persona voice wins.** The in-band blocks all say so explicitly, and so does
> the skill's use here: humanizing strips machine tells, it does **not**
> normalize every persona toward the same conversational register. A terse
> persona stays terse. Flattening 35 distinct cards into one voice would be its
> own kind of slop.

## When to invoke it by name

- **Editing a finished transcript** before publishing to the library —
  *"run the humanizer over conversation #42's transcript."*
- **Rewriting a doc or README** that reads like a model wrote it.
- **Diagnosing** why a debate still sounds generated after the in-band rules —
  the catalogue names the pattern the distilled block missed.

## Install

Auto-wires with the rest of `skills/` — the setup script links **every**
subfolder, so no script edit was needed to add this one:

```powershell
.\scripts\setup\setup-skill-links.ps1
```

```bash
./scripts/setup/setup-skill-links.sh
```

That covers Claude Code, Codex, Antigravity, Gemini (deprecated), plus this
repo's own `.claude/skills`. **OpenCode is not covered** — it has no
documented Agent Skills path (open Roadmap row). They get the in-band rules
regardless, which is exactly why the in-band layer exists.

Verify with `/skills` — `humanizer` should appear in the list.

## Verify end-to-end

Seed a short debate and read the transcript for tells:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --participants claude-code,codex `
  --topic "Should AI-written code require disclosure in open source?" `
  --preset debate --max-turns 4
```

What you're checking for in the output:

- No "stands as a testament", "plays a crucial role", "delve into".
- **No reflexive three-item lists** — the loudest tell, and the one to grade on.
- No `-ing` clauses tacked onto sentence ends to fake depth.
- Sentence lengths actually vary.
- No closing paragraph that restates the turn's own argument.
- Each persona still sounds like *itself*, not like the others.

If the transcript is still generic, the conversation was seeded **before** this
change — `kickoff_template` is snapshotted onto the row at seed time, so
existing conversations keep their old prompt. Seed a fresh one.

---

<p align="center">
  <sub>← <a href="../README.md">Skills</a> · <a href="../../README.md">Agent-Chat</a> · <a href="../debate-mode/SKILL.md">debate-mode</a> · <a href="SKILL.md">SKILL.md</a></sub>
</p>
