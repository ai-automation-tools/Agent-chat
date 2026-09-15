---
name: agent-chat-conv-types
description: >-
  Add or change a conversation format in the Agent-Chat repo — a new conv_type (debate / podcast /
  collaborate / yours), a sub-type preset, a seat role, an extra role like the skeptic, or a type
  that produces a deliverable. Decides first whether the thing asked for is a TYPE or merely a
  PRESET, then walks the full multi-file ritual: CONV_TYPES, _ROLE_BRIEFS, the runtime skill, the
  guide, the tests. Use for "add a new conversation type", "add an interview/standup/retro mode",
  "add a preset", "add a role to a conversation", "make this type produce an artifact", "the lead
  is getting its own seat and shouldn't", "change who speaks first", "seat counts are wrong",
  "signal='result' never lands", or any edit to src/orchestrator/conv_types.py or src/presets.py.
---

# Conversation types and sub-types

Two axes, and keeping them apart is the whole design.

| | `conv_type` | `preset` |
|:---|:---|:---|
| **Is** | The room's **structure** — who is in it, what each chair is for | The **sub-type** — tone, and for a type that makes something, the artifact's shape |
| **Lives in** | `src/orchestrator/conv_types.py` → `CONV_TYPES` | `src/presets.py` → `PRESETS` |
| **Costs** | Seats, role briefs, a runtime skill, a guide, tests | One dict entry |

**Everything generates from those two registries** — the `/orchestrate` radios, the
`/conversations` filter chips, export's Type/Role rows, the media prompts, the launch prompt.
So the work is almost never "wire up the UI"; it is "add the row and update its satellites".

---

## 1. First decide: type or preset?

> **Only add a `conv_type` when the SEATS genuinely differ.**

Brainstorm, plan and review are **presets of `collaborate`**, not types — same room, same
facilitator + collaborators, pointed at different work. A retro is a preset. An interview with a
host who does not answer is a *type*, because the host chair is structurally not a guest chair.

Ask: *does this need a chair that no existing type has?*

- **No** → add a `PRESETS` entry with `for_types` naming the host type. Done in one file. Stop here.
- **Yes** → the full ritual in [`references/add-a-type.md`](references/add-a-type.md).

If the answer is "a seat needs a different **brief**, not a different **shape**", that is a third
option: an **extra role** (§3), which re-brands a member seat rather than adding one.

## 2. The four flags that decide the room's behaviour

Every type-level bug in this repo's history traces to one of these being wrong.

| Flag | True means | Get it wrong and |
|:---|:---|:---|
| `lead_required` | the room refuses to seed without a lead | a collaboration ends at `max_turns` with no artifact |
| `lead_needs_own_seat` | the lead is an **observer** — its own chair, prepended by `/orchestrate`, which asks for its tool separately | a two-CLI run silently deals in an unpicked third CLI |
| `lead_forces_turns` | seating a lead overrides the preset's `mode` to `turns` | `brainstorm`'s deliberate `continuous` mode is stomped |
| `produces_deliverable` | the lead closes with `signal='result'`, and a non-lead cannot `signal='done'` before one exists | the run reads `complete` having produced nothing |

The rule behind `lead_needs_own_seat`: a debate's moderator and a podcast's host **do not argue
or answer**, so they need a chair of their own. A collaboration's facilitator **is** one of the
collaborators — `default_roles()` makes whoever speaks first the lead, and the form hides the lead
section entirely. Counting seats? Use `min_participants` / `max_participants` (includes the lead),
never `min_members` / `max_members` (the plain member role only).

## 3. Extra roles re-brand a seat, they never add one

`ConvType.extra_roles` is a tuple of `ExtraRole(role, label, plural, max_count, hint)`.
`collaborate`'s `skeptic` is one of the collaborators the operator already picked. Consequences:

- **Never assigned implicitly.** `default_roles()` still only ever produces the lead and the plain
  member role, so a caller that says nothing gets exactly the room it always got.
- `min_members` counts the **plain** member role — a facilitator plus a lone skeptic is refused.
- The lead cannot also hold one; `POST /api/orchestrate` returns an error rather than letting a
  dict update pick a winner.
- Every extra role needs its own `_ROLE_BRIEFS` entry — `tests/test_conv_types.py` pins that via
  `ALL_ROLES`.
- The `/orchestrate` *Special seats* dropdowns and its `roles: {cli: role}` payload generate from
  the registry: **no render edit, no PowerShell edit.**

## 4. Deliverables ride on `signal`, not on a column

A type with `produces_deliverable=True` has its lead post the artifact with
**`messages.signal='result'`**. `signal` already rides the sync, the SSE payload and export's
heading suffix — so a deliverable needs **no schema change and no export-contract change**. Three
rules that are easy to break:

1. `maybe_complete()` keeps stopping on `done` / `blocked` **only**. A result is not a stop signal.
2. **A run may hold several results and the LAST one wins** — leads draft then revise (run #51
   posted six). `export.final_result()` / `superseded_result_ids()` define last-wins once, for the
   reader, the export and the delivery sink.
3. Which one is current is published as an **additive `Result` row in `topic.md`**, never as a
   transcript-heading suffix — the contract says a heading *ends* with the signal span, and a
   suffix would break an end-anchored parser. `tests/test_deliverable_flow.py` pins the headings clean.

## 5. `for_types` is advisory

`Preset.for_types` only filters the `/orchestrate` picker, exactly like CLI availability does.
Nothing rejects an odd pairing, and a preset with no `for_types` is offered everywhere. Do not add
validation that turns the hint into a rule.

---

## Checklist for a new type

Full detail in [`references/add-a-type.md`](references/add-a-type.md). The short form:

- [ ] `CONV_TYPES` entry in `src/orchestrator/conv_types.py`, with the four flags of §2 chosen deliberately
- [ ] A `_ROLE_BRIEFS` entry in `src/agent_chat_mcp.py` for **every** role the type can assign, extras included
- [ ] `skills/<type>-mode/SKILL.md` — read by the participating CLIs at runtime
- [ ] A `.gitignore` line for `.claude/skills/<type>-mode/` (the junction would otherwise commit as files full of this machine's paths)
- [ ] `docs/Guides/<type>.md` + its row in the Guides index, and `ConvType.guide_url` pointing at it
- [ ] A `PRESETS` default flavour, with `for_types` naming the new key
- [ ] `docs/CHANGELOG.md` entry; `docs/Roadmap.md` row moved Open→Done with a `YYYY-MM-DD` date if it closes one
- [ ] `.\.venv\Scripts\python.exe tests\test_conv_types.py` and `tests\test_deliverable_flow.py` pass
- [ ] Seed a real `--max-turns 2` run of the new type and confirm the row reaches `status='complete'`

---

## Anti-patterns

- **Adding a type for a tone.** If the seats are the same, it is a preset. A type costs five files
  and a guide forever.
- **Editing `scripts/lib/spawn-agents.ps1`.** `New-AgentPrompt` is **role-agnostic** — it points
  every agent at `get_kickoff()`'s `role_brief`. It used to carry a per-role copy and no longer
  does. Adding a seat touches no PowerShell; a test pins that.
- **Writing the brief in three places.** `_ROLE_BRIEFS` and the `<type>-mode` skill — **two**, not
  three. `_ROLE_BRIEFS` is the single source and reaches CLIs with no skills installed and
  hand-seeded runs with no launch prompt.
- **Re-introducing an unconditional turns mode** in `POST /api/orchestrate`. Read
  `lead_forces_turns` instead.
- **Promoting a deliverable to a column.** It is a `signal` value on purpose.
- **Making `for_types` enforcing.** It filters a picker. That is all.
- **Trusting a green test run for anything on the `/orchestrate` page.** `tests/` asserts on
  rendered HTML strings, so a selector that hides the right markup passes every suite — that is
  how the host seat picker once shipped invisible. Open the page in a browser and say that you did.
