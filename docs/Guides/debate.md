<h1 align="center">🥊 Run a debate</h1>

<p align="center">
  <em>Two to five CLI agents argue a topic in character, one turn at a time, until someone runs out of turns or concedes.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/format-debate-10b981?style=for-the-badge&labelColor=09090b" alt="Format: debate">
  <img src="https://img.shields.io/badge/seats-2--5_debaters-0284c7?style=for-the-badge&labelColor=09090b" alt="2 to 5 debaters">
  <a href="README.md"><img src="https://img.shields.io/badge/↩-Guides-6B7280?style=for-the-badge&labelColor=09090b" alt="Back to Guides"></a>
</p>

---

## 🎭 What a debate is here

A debate is a conversation with **sides**. Each agent gets a persona and a
position, the server hands out turns in strict rotation, and nobody can speak
twice in a row. It ends when every agent has spent its `--max-turns`, or when
one of them sends `signal='done'`.

| Seat | How many | What it does |
|:---|:---|:---|
| **Debater** | 2–5 | Argues a side in persona. Reads the thread so far on every turn, answers the last speaker, moves the argument on. |
| **Moderator** | 0 or 1 | Optional. Opens the debate, chases questions that got dodged, and closes it. Takes its own seat and never argues a side. |

Five seats total, because one CLI process occupies one seat. You do **not** need
five different tools — a second seat on a CLI you already have is a folder, and
[`add_agent_seat.py`](../../scripts/setup/add_agent_seat.py) creates it. One CLI
is genuinely enough to run a debate against itself.

---

## 🚀 Three ways to start one

All three write the same conversation row through the same
`seed_conversation()`, so pick on how much you want to decide yourself.

| Launcher | Use it when | Start with |
|:---|:---|:---|
| [**🎲 Auto-debate**](auto-debate.md) | You want a debate, not a decision. It picks the topic, casts the personas, seeds, and opens a terminal per agent already in character. | `.\scripts\debate.ps1 -SkipPermissions` |
| [**⌨️ Manual seed**](start-new-chat.md) | You have a topic and a cast in mind. Seed from the terminal, then paste a two-line prompt into each CLI. The daily driver. | `.\scripts\start.ps1 --preset debate …` |
| [**🖱️ Web form**](orchestrate-form.md) | You'd rather click. Local `/orchestrate` gives you a format picker, a persona dropdown per seat, and preflight badges that catch a broken MCP config before you seed. | `http://127.0.0.1:8765/orchestrate?type=debate` |

### The shortest one that works

```powershell
# Picks a topic from the 100-topic library, casts random personas,
# seeds, and launches every CLI hands-off.
.\scripts\debate.ps1 -SkipPermissions
```

Drop `-SkipPermissions` and Claude Code stops to ask you to approve the
`agent_chat` tools on its first turn. Add `-DryRun` to see the topic, the cast,
and the launch plan without writing anything.

### Your own topic and cast

```powershell
.\scripts\start.ps1 --preset debate `
  --topic "Should AI-generated content be labeled everywhere online?" `
  --participants claude-code,codex `
  --first claude-code
```

> [!WARNING]
> Those trailing backticks are PowerShell line continuations, and they only work
> as the **last character on a line**. Paste this as one long line and the
> backticks become escapes mid-command; you'll get `ERROR: need at least 2
> participants` and wonder why. There's a single-line form in
> [start-new-chat.md](start-new-chat.md#recommended-pick-a---preset).

Then paste this into each CLI, changing the id each time:

```text
You're agent <id> on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

`get_kickoff()` returns the topic, the tone, the seat you're in, and the loop to
run. Paste into the `--first` agent first so its opening message is queued
before the others start waiting.

---

## 🎩 Adding a moderator

A moderator makes a long debate readable. It speaks first, interjects each
round, and closes — without ever picking a side.

```powershell
.\scripts\start.ps1 --preset debate `
  --topic "Is remote work over?" `
  --participants claude-code,codex,codex-2 `
  --host codex-2
```

The flag is `--host` for both formats — it names whichever seat runs the room,
which the server records as `moderator` in a debate and `host` in a podcast.
The moderator needs its own seat and can't double as a debater, and it **speaks
first**: leave `--first` off and it's set for you, or name the same agent in
both. Seeding rejects a run where the lead doesn't open.

On the web form it's the **Add a moderator** toggle, with its own seat and
persona dropdown.

---

## 🎪 Choosing the cast

Personas live in the `personas` table and are managed at
[`/personas`](http://127.0.0.1:8765/personas). Every launcher draws from the
same roster.

| You want | Do this |
|:---|:---|
| A random cast | Nothing. That's the default in `debate.ps1` and the `🎲 random` option on the form. |
| A cast from one group | `-Group "<group name>"` on `debate.ps1`, or the grouped dropdown on the form. Groups are free-form — whatever's on the cards is what exists. |
| Exact people | `-Personalities <slug>,<slug>` — slugs or display names, both resolve through the registry. |
| Nobody in character | Leave the persona as `none`. The agents argue as themselves. |

Run `.\.venv\Scripts\python.exe src\orchestrator\personas.py list --castable` to
see what's actually in your roster before you name anything.

Random draws skip the `AI-Models` group on purpose, so you never get "Claude
Code" fielded against Gordon Ramsay. Ask for that group explicitly and you'll
get it.

---

## 👀 While it runs, and after

```powershell
# Live transcript in the terminal
.\.venv\Scripts\python.exe src\inspect_conversations.py tail <id>

# End it early
.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>
```

The web UI is the better view: `http://127.0.0.1:8765/conversations/<id>`
streams each message over SSE as it lands, renders Markdown, and has a **Stop**
button. When it finishes, `/export.md` and `/export.zip` on the same page give
you the transcript plus the persona cards in the frozen bundle format that the
library archive and the theater app both read.

---

## 🧰 When it doesn't work

| Symptom | Cause |
|:---|:---|
| `need at least 2 participants` | The backtick paste problem above, nearly every time. |
| A CLI sits there and never speaks | It's not the agent's turn, or its `--agent-id` doesn't match a participant. Check with `inspect_conversations.py list`. |
| The form won't let you seed | Preflight failed on a seat. The badge next to the CLI names the error code; the full log is under `logs/`. |
| Agents ignore the format | The `agent-chat` and `debate-mode` skills aren't linked on that CLI. Run `scripts\setup\setup-skill-links.ps1` once. |

Deeper troubleshooting lives in
[start-new-chat.md](start-new-chat.md#troubleshooting).

---

## 🔗 Where to go next

| Next | Why |
|:---|:---|
| [**Auto-debate**](auto-debate.md) | Every flag on `debate.ps1` — topic selection, group filters, forcing an exact CLI set, `-DryRun`. |
| [**Start a new chat**](start-new-chat.md) | The manual recipe in full, plus continuous mode and second seats. |
| [**Orchestrate form**](orchestrate-form.md) | The web form field by field, and why it's local-only. |
| [**Run a podcast**](podcast.md) | The other format on the same bus. A host asks; nobody argues. |
| [**Kickoff prompts**](../App/kickoff-prompts.md) | What `get_kickoff()` returns, the presets, and writing your own template. |

---

<p align="center">
  <sub>← <a href="README.md">Guides home</a> · <a href="../README.md">Documentation</a> · Next: <a href="podcast.md">Run a podcast →</a></sub>
</p>
