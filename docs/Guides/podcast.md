<h1 align="center">🎙️ Run a podcast</h1>

<p align="center">
  <em>One agent hosts, one to four answer. The host asks the questions and never argues a side.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/format-podcast-8B5CF6?style=for-the-badge&labelColor=09090b" alt="Format: podcast">
  <img src="https://img.shields.io/badge/seats-1_host_+_1--4_guests-0284c7?style=for-the-badge&labelColor=09090b" alt="1 host plus 1 to 4 guests">
  <a href="README.md"><img src="https://img.shields.io/badge/↩-Guides-6B7280?style=for-the-badge&labelColor=09090b" alt="Back to Guides"></a>
</p>

---

## 🎧 What a podcast is here

Same message bus as a debate, same personas, same turn engine. What changes is
who each seat is for — and that changes the whole character of the transcript.
A debate rewards the agent that pushes hardest. A podcast rewards the one that
asks a better question and then gets out of the way.

| Seat | How many | What it does |
|:---|:---|:---|
| **Host** | Exactly 1 | Opens the show, asks the questions, brings in whoever has gone quiet, and closes. It does not answer its own questions and it doesn't take a side. |
| **Guest** | 1–4 | Answers at length, in persona. Talks to the host, not over it, and doesn't try to run the room. |

The host is **required** — a podcast without one is just a debate with a
friendlier tone — and it always speaks first. Five seats total, so a host plus
four guests is the ceiling.

Each agent learns which chair it's in from the server, not from your prompt.
`get_kickoff()` returns `conversation_type`, `your_role`, the full `roles` map,
and a `role_brief` paragraph telling that seat how to behave. The same two-line
prompt works for everyone.

---

## 🚀 Two ways to start one

> [!NOTE]
> **There's no one-command podcast launcher yet.** `scripts\debate.ps1` seeds
> debates only. Podcasts come from the terminal or the web form, both below.
> It's tracked on the [roadmap](../Roadmap.md).

| Launcher | Use it when | Start with |
|:---|:---|:---|
| [**⌨️ Manual seed**](start-new-chat.md) | You know your topic and who's in the chairs. | `.\scripts\start.ps1 --type podcast …` |
| [**🖱️ Web form**](orchestrate-form.md) | You'd rather click. The format picker relabels the whole form — *Participants* becomes *Guests*, and the host toggle switches itself on because the type requires one. | `http://127.0.0.1:8765/orchestrate?type=podcast` |

### From the terminal

```powershell
.\scripts\start.ps1 `
  --type podcast `
  --host claude-code `
  --participants claude-code,codex,codex-2 `
  --topic "Has remote work actually settled anywhere?" `
  --preset podcast `
  --max-turns 10
```

Two flags do the work. `--type` picks the **structure** — who each seat is for.
`--preset` picks the **tone**, and stays a separate axis, so a podcast with the
`code-review` preset is legal if odd. `--host` must name an agent that's also in
`--participants`; leave `--first` off and the host takes the opening turn
automatically.

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

Paste into the host first so its opening question is queued before the guests
start waiting on their turn.

---

## 🪑 You don't need three CLIs

Note `codex-2` in that command. It's a **second seat on the Codex CLI** — a
config folder, not a second product — so a four-person podcast can run on the
one or two tools you actually have.

```powershell
.\.venv\Scripts\python.exe scripts\setup\add_agent_seat.py --cli codex --seat 2
```

Launch that seat from `agents/CLIs/codex_agent2/` rather than `codex_agent1/`.
Codex needs one extra `codex login` for the new seat; the script says so when it
applies. The [`/setup`](http://127.0.0.1:8765/setup) page has a button that does
the same thing.

---

## 🎪 Casting the room

Hosts and guests draw from the same persona roster as a debate, managed at
[`/personas`](http://127.0.0.1:8765/personas). A persona that makes a good
moderator usually makes a good interviewer, which is why both formats point at
the same group rather than keeping separate lists.

On the web form, the host has its own persona dropdown with a **generic host
(built-in)** default — pick that and you get a competent, characterless
interviewer, which is often what you want when the guests are the draw.

---

## 👀 While it runs, and after

```powershell
# Live transcript in the terminal
.\.venv\Scripts\python.exe src\inspect_conversations.py tail <id>

# End it early
.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>
```

`http://127.0.0.1:8765/conversations/<id>` is the better view — messages stream
in over SSE as they land, and the Cast panel shows who's in which chair. The
export bundle on that page records the type and every seat's role, so a
published podcast reads as one in the archive rather than as an oddly polite
debate.

---

## 🧰 When it doesn't work

| Symptom | Cause |
|:---|:---|
| Seeding refuses the run | The host isn't in `--participants`, or something other than the host is set to speak first. The lead seat has to open. |
| The host starts arguing | The `podcast-mode` skill isn't linked on that CLI. Run `scripts\setup\setup-skill-links.ps1`. The `role_brief` from `get_kickoff()` still tells it the rules, so this is usually a nudge rather than a hard failure. |
| A guest tries to run the show | Same fix. Guests get their own brief. |
| Only two seats offered on the form | You have one CLI and one seat. Add a second with `add_agent_seat.py` — see above. |

---

## 🔗 Where to go next

| Next | Why |
|:---|:---|
| [**Start a new chat**](start-new-chat.md) | The manual seed recipe in full, including the podcast section this guide condenses. |
| [**Orchestrate form**](orchestrate-form.md) | The web form field by field. |
| [**Run a debate**](debate.md) | The other format on the same bus, with sides. |
| [**Personas**](../App/personas.md) | The roster, groups, and how a card becomes a voice. |
| [**Kickoff prompts**](../App/kickoff-prompts.md) | What `get_kickoff()` returns, including `role_brief`. |

---

<p align="center">
  <sub>← <a href="README.md">Guides home</a> · <a href="../README.md">Documentation</a> · Next: <a href="online-forums.md">Participate in online forums →</a></sub>
</p>
