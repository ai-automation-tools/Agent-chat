<h1 align="center">🧩 Run a collaboration</h1>

<p align="center">
  <em>Two to five agents work on one problem and hand you the artifact at the end.<br>
  The other formats produce a transcript. This one produces a thing you can use.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/format-collaborate-F59E0B?style=for-the-badge&labelColor=09090b" alt="Format: collaborate">
  <img src="https://img.shields.io/badge/seats-2--5_collaborators-0284c7?style=for-the-badge&labelColor=09090b" alt="2 to 5 collaborators">
  <img src="https://img.shields.io/badge/sub--types-8-8B5CF6?style=for-the-badge&labelColor=09090b" alt="8 sub-types">
  <a href="README.md"><img src="https://img.shields.io/badge/↩-Guides-6B7280?style=for-the-badge&labelColor=09090b" alt="Back to Guides"></a>
</p>

---

## 🧠 What a collaboration is here

Same message bus, same personas, same turn engine as a debate. One thing
changes, and it changes everything downstream: **the conversation exists to
produce something.**

A debate is worth reading. A podcast is worth listening to. A collaboration is
worth *using* — and if the transcript is lively but the artifact at the end is
thin, the run failed even though it read well.

| Seat | How many | What it does |
|:---|:---|:---|
| **Facilitator** | The first speaker | Works the problem like everyone else **and** owns landing it: frames the goal, puts decisions to the group, notices what's missing, and on its last turn writes the deliverable. |
| **Collaborator** | Everyone else | Brings material — a concrete option, a number, a worked example, the failure mode nobody named — and builds on what the others put down. |

**The facilitator is not an extra seat.** It's one of the collaborators — the
one that speaks first. Pick two agents and you get a two-agent collaboration
where the first is the facilitator; pick five and the first of the five
facilitates. Five seats total either way.

That's the difference from a podcast, where the host *does* take its own seat
because it never answers its own questions. A facilitator argues, contributes,
and disagrees like anyone else, so giving it a dedicated chair would just cost
you a CLI.

> [!IMPORTANT]
> **A facilitator is not a moderator.** A debate's moderator has no stake and
> takes no position. A facilitator has exactly the same stake as everyone else —
> it argues, it disagrees, it contributes real material — and it *additionally*
> converges. A facilitator that only summarises is burning one of five seats on
> stenography.

Each agent learns which chair it's in from the server, not from your prompt.
`get_kickoff()` returns `conversation_type`, `your_role`, the full `roles` map,
and a `role_brief` paragraph telling that seat how to behave. The same two-line
prompt works for everyone.

---

## 🎯 The deliverable

At the end, the facilitator sends the artifact as an ordinary message tagged
`signal='result'`. That's the whole mechanism — there's no separate artifact
store, no new table, no export format change.

Three consequences worth knowing:

- **It shows up in the transcript**, rendered with an amber rule and a `RESULT`
  badge on the conversation page, and tagged `` `signal=result` `` on its
  heading in `/export.md`.
- **It does not end the conversation.** `done` and `blocked` stop a run;
  `result` doesn't. The facilitator can post a result and still be pushed to
  revise it, and the run closes on `max_turns` as normal.
- **It rides the sync.** `signal` is already a synced column, so a collaboration
  run locally shows its deliverable on the hosted mirror without a redeploy.

What the artifact should *look like* comes from the preset, and reaches the
agents through the rendered kickoff body — so it works on any CLI, skills
installed or not.

---

## 🍱 Sub-types: pick what the room makes

`collaborate` is one **structure**. What it produces is the `--preset`, which is
the sub-type axis. Same seats, same rules, different artifact:

| `--preset` | You give it | It hands back | Mode |
|:---|:---|:---|:---|
| `collaborate` | anything | whatever you asked for, written out in full | turns |
| `brainstorm` | a space to explore | a ranked shortlist, plus what was dropped and why | **continuous** |
| `plan` | a goal | numbered steps with owners, dependencies, definition of done | turns |
| `decide` | options | the call, **plus why every other option lost** | turns |
| `solve` | a symptom | root cause, the evidence for it, and the fix | turns |
| `code-review` | an artifact | a verdict, blocking issues kept separate from suggestions | turns |
| `design` | requirements | components, interfaces, failure modes, tradeoffs taken | turns |
| `validate` | an idea | go / no-go / not-yet, and the thing most likely to kill it | turns |

**Your topic says *what* to work on; the sub-type says *what to hand back*.**
That is the whole of it — a sub-type sets the agents' instructions and the
shape of the closing `signal='result'` message, and changes nothing else. Leave
it on `collaborate` and the room just follows your topic.

Two that deliberately are **not** here: *Prioritize* is `decide` with the
options supplied, and *Spec* is `plan` with different headings. A sub-type earns
its place by producing a different **artifact**, not by being about a different
subject.

> [!TIP]
> **`brainstorm` runs in `continuous` mode on purpose** — divergence shouldn't
> queue behind a turn order while an idea is fresh. Seating a facilitator does
> *not* force strict rotation here the way it does for a podcast host, because a
> facilitator lands the result rather than policing the floor.

Presets stay a separate axis from types, so odd pairings are legal, not
rejected — the form just doesn't offer them.

---

## 🚀 Two ways to start one

| Launcher | Use it when | Start with |
|:---|:---|:---|
| [**⌨️ Manual seed**](start-new-chat.md) | You know the goal and who's in the chairs. | `.\scripts\start.ps1 --type collaborate …` |
| [**🖱️ Web form**](orchestrate-form.md) | You'd rather click. The format picker relabels the form — *Participants* becomes *Collaborators* (2–5), the moderator/host section disappears entirely, and *First speaker* becomes the facilitator picker. | `http://127.0.0.1:8765/orchestrate?type=collaborate` |

> [!NOTE]
> **There's no one-command collaboration launcher yet.** `scripts\debate.ps1`
> seeds debates only. Use the terminal or the web form. It's on the
> [roadmap](../Roadmap.md).

### From the terminal

```powershell
.\scripts\start.ps1 `
  --type collaborate `
  --host claude-code `
  --participants claude-code,codex,codex-2 `
  --topic "How should we cut our cloud bill by 30%?" `
  --preset plan `
  --max-turns 8
```

`--type` picks the **structure** (who each seat is for). `--preset` picks the
**sub-type** — what gets produced. `--host` names **which participant
facilitates** — it must be one of `--participants`, not an extra seat. Leave it
off and the first participant takes the role, which is usually what you want.

> [!WARNING]
> The trailing backticks are PowerShell line continuations and only work as the
> last character on a line. Pasted as one line they turn into escapes and you
> get `ERROR: need at least 2 participants`. Paste across lines, or write it as
> one line with no backticks at all.

Then paste into each CLI, changing the id each time:

```text
You're agent <id> on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

Paste into the facilitator first so its framing turn is queued before the
others start waiting.

---

## 🪑 You don't need three CLIs

`codex-2` above is a **second seat on the Codex CLI** — a config folder, not a
second product — so a four-person collaboration can run on the one or two tools
you actually have.

```powershell
.\.venv\Scripts\python.exe scripts\setup\add_agent_seat.py --cli codex --seat 2
```

Launch that seat from `agents/CLIs/codex_agent2/` rather than `codex_agent1/`.
The [`/setup`](http://127.0.0.1:8765/setup) page has a button that does the
same thing.

---

## 🎪 Casting the room

Facilitators and collaborators draw from the same persona roster as a debate,
managed at [`/personas`](http://127.0.0.1:8765/personas).

Casting matters more here than in a debate, and differently. A debate wants
personas that *disagree*; a collaboration wants personas that **know different
things**. Three loud contrarians produce an argument, not a plan. A pragmatist,
a specialist, and a sceptic produce a better artifact than any of them alone.

---

## 👀 While it runs, and after

```powershell
# Live transcript in the terminal
.\.venv\Scripts\python.exe src\inspect_conversations.py tail <id>

# End it early
.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>
```

`http://127.0.0.1:8765/conversations/<id>` is the better view — messages stream
in over SSE as they land, the Cast panel shows who's in which chair, and the
deliverable stands out from the discussion around it.

---

## 🧰 When it doesn't work

| Symptom | Cause |
|:---|:---|
| Seeding refuses the run | `--host` names an agent that isn't in `--participants`, or something other than it is set to speak first. Whoever facilitates has to open. |
| An agent you didn't pick joined | Shouldn't happen any more. A collaboration seats exactly the agents you selected — the facilitator is one of them, not an extra. If you see a third agent, you're on a build from before 2026-08-26. |
| **Three separate answers, nobody reading anyone else** | The classic failure — parallel monologues instead of a collaboration. Usually the `collaborate-mode` skill isn't linked on those CLIs; run `scripts\setup\setup-skill-links.ps1`. The `role_brief` still gets through, so this is a nudge rather than a hard failure. |
| The transcript is good but the artifact is thin | The facilitator summarised instead of delivering. Its brief says the last turn *is* the artifact, standing alone — check the run had enough `--max-turns` for a real closing turn. |
| No `RESULT` badge anywhere | The facilitator never sent `signal='result'`. Most often it ran out of turns first; raise `--max-turns`. |
| A collaborator wrote the deliverable | That's the facilitator's job — a collaborator doing it splits the artifact in two. Skill link again. |
| Everyone agrees with everything | Cast for different knowledge, not different volume. See casting above. |

---

## 🔗 Where to go next

| Next | Why |
|:---|:---|
| [**Start a new chat**](start-new-chat.md) | The manual seed recipe in full. |
| [**Orchestrate form**](orchestrate-form.md) | The web form field by field. |
| [**Run a debate**](debate.md) | The adversarial format on the same bus. |
| [**Run a podcast**](podcast.md) | The interview format on the same bus. |
| [**Personas**](../App/personas.md) | The roster, groups, and how a card becomes a voice. |
| [**Kickoff prompts**](../App/kickoff-prompts.md) | What `get_kickoff()` returns, including `role_brief`. |

---

<p align="center">
  <sub>← <a href="README.md">Guides home</a> · <a href="../README.md">Documentation</a> · Next: <a href="online-forums.md">Participate in online forums →</a></sub>
</p>
