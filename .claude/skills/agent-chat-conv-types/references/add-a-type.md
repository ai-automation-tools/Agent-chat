# Adding a `conv_type`, file by file

Only for a format whose **seats differ** from debate / podcast / collaborate. A tone or an
artifact shape is a `PRESETS` entry and touches one file.

Worked example throughout: a hypothetical `interview` type — one **Interviewer** (observer, does
not answer) and one or more **Subjects**.

---

## 1. `src/orchestrator/conv_types.py` — the registry row

```python
"interview": ConvType(
    key="interview",
    label="Interview",            # singular, title case
    plural="Interviews",          # the /conversations filter chip
    lead_role="interviewer",      # stored in participant_roles
    lead_label="Interviewer",
    lead_required=True,
    member_role="subject",
    member_label="Subject",
    members_label="Subjects",
    min_members=1,
    max_members=MAX_PARTICIPANTS - 1,   # the interviewer takes a seat
    default_preset="interview",
    lead_group="Debate-Hosts",          # persona group the /orchestrate lead picker offers
    guide_url=f"{_REPO}/docs/Guides/interview.md",
    guide_label="How to run an interview",
    # Defaults worth stating explicitly rather than inheriting by accident:
    lead_needs_own_seat=True,     # an interviewer does not answer -> own chair
    lead_forces_turns=True,       # it runs the floor
    produces_deliverable=False,   # a transcript, not an artifact
),
```

`max_members` subtracts one **iff** `lead_needs_own_seat` is True. `ALL_ROLES` and
`CONV_TYPE_KEYS` derive automatically — do not hand-maintain them.

## 2. `src/agent_chat_mcp.py` — `_ROLE_BRIEFS`

One entry per role the type can assign, **including extra roles**. This dict is the single
source: it reaches CLIs with no skills installed, and hand-seeded runs with no launch prompt.
`tests/test_conv_types.py` fails on a missing one.

Write it in the second person, and state the thing the seat must *not* do — that is the half
models get wrong:

```python
"interviewer": (
    "You are the INTERVIEWER. You do not answer your own questions and you "
    "do not argue a position. Open by introducing the subject and the topic, "
    "then ask one question per turn and follow up on what you actually heard "
    "rather than moving down a list. Close by thanking the subject."
),
```

## 3. `skills/<type>-mode/SKILL.md` — the runtime skill

Read by the **participating CLIs** at runtime, junctioned into each CLI's config dir by
`scripts/setup/setup-skill-links.ps1`. Layer it on the base `agent-chat` skill rather than
restating the participation loop. Match the shape of `skills/podcast-mode/`.

Keep it in sync with `_ROLE_BRIEFS` — **two places, never three.**

## 4. `.gitignore`

Add `.claude/skills/interview-mode/`. The `.claude/skills/` exclusions are listed **by name**;
without a line, Windows commits the junction as duplicate files full of this machine's `D:` paths.

## 5. `docs/Guides/interview.md` + the Guides index

One front door per format. Add the row to `docs/Guides/README.md` and point `ConvType.guide_url`
at it. The guide links down to the launchers (`docs/Guides/start-new-chat.md` is the daily driver).

## 6. `src/presets.py` — the default flavour

```python
"interview": {
    "label": "Interview",
    "mode": "turns",
    "max_turns": 8,
    "for_types": ("interview",),
    ...
},
```

`for_types` is **advisory** — it filters the `/orchestrate` picker and rejects nothing.

## 7. Docs

- `docs/CHANGELOG.md` — reverse-chronological, an entry for any user-visible behaviour change.
- `docs/Roadmap.md` — if this closes an item, **move** the row Open→Done with a `YYYY-MM-DD`
  `Closed` date. Never delete rows.
- `CLAUDE.md`'s conv-types section if the change alters a rule, not just adds a row.

## 8. Nothing else

Explicitly **not** touched by a new type:

| File | Why not |
|:---|:---|
| `scripts/lib/spawn-agents.ps1` | `New-AgentPrompt` is role-agnostic; it points every agent at `get_kickoff()`'s `role_brief` |
| `src/web/render/orchestrate.py` | the radios and the *Special seats* dropdowns generate from `CONV_TYPES` |
| `src/orchestrator/export.py` | the Type/Role rows read `type_label()` / `role_label()` |
| `src/web/media_prompts.py` | generated from the registry |
| Any `SCHEMA` copy | `conv_type` and `participant_roles` are existing columns |

If you find yourself editing one of these to add a type, the registry is missing something —
fix that instead.

---

## Verify

```powershell
.\.venv\Scripts\python.exe tests\test_conv_types.py
.\.venv\Scripts\python.exe tests\test_deliverable_flow.py     # if produces_deliverable
```

Then the part no test covers, because `tests/` asserts on rendered HTML strings:

1. Open `http://127.0.0.1:8765/orchestrate`, pick the new type, and confirm the Participants
   section renders the right chairs, the lead section appears (or is hidden) per
   `lead_needs_own_seat`, and the seat ids derive correctly.
2. Seed a real `--max-turns 2` run and confirm the row reaches `status='complete'`:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py --topic "smoke" --conv-type interview --max-turns 2
.\.venv\Scripts\python.exe src\inspect_conversations.py list
```

Say in your report that you checked the page in a browser. A green suite does not cover it.
