<h1 align="center">🚀 Guides</h1>

<p align="center">
  <em>Four ways to put agents in a room together, and the launchers that start them.<br>
  Start here if you want to <b>use</b> Agent-Chat rather than read about how it's built.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Formats-4-10b981?style=for-the-badge&labelColor=09090b" alt="4 conversation formats">
  <img src="https://img.shields.io/badge/Guides-11-0284c7?style=for-the-badge&labelColor=09090b" alt="11 guides">
  <img src="https://img.shields.io/badge/Shell-PowerShell_7+-8b5cf6?style=for-the-badge&labelColor=09090b" alt="PowerShell 7+">
</p>

---

## 🎭 Start with the format

One guide per format. Each is a front door: what the format is, which launcher
suits you, and the shortest command that works. They're what the web app's
launch buttons link to.

| Guide | What happens | Seats |
|:---|:---|:---|
| [**🥊 Run a debate**](debate.md) | Agents argue a topic in persona. Add a moderator and it opens the debate, chases dodged questions, and closes without taking a side. | 2–5 debaters, plus an optional moderator |
| [**🎙️ Run a podcast**](podcast.md) | A host interviews the guests. It asks and never answers its own questions; guests answer at length and don't run the show. | 1 host, plus 1–4 guests |
| [**🧩 Run a collaboration**](collaborate.md) | Agents work one problem together and the facilitator hands you the artifact at the end — a plan, a ranked shortlist, a review. The `--preset` picks which. | 1 facilitator, plus 1–4 collaborators |
| [**⚔️ Participate in online forums**](online-forums.md) | An agent reads a captured comment thread and drafts a reply in persona. You approve it before any text reaches the page. | 1 agent, against real people |

Debate, podcast, and collaboration run on the same bus with the same personas —
they differ in who each seat is for, which the server records as the
conversation's `conv_type` and tells each agent on every turn. A fifth format
would be an entry in [`conv_types.py`](../../src/orchestrator/conv_types.py)
rather than a new subsystem.

Collaboration is the odd one out in a way worth knowing before you pick: the
other two produce a **transcript**, and it produces an **artifact** — its
facilitator's closing turn is the deliverable, tagged `signal='result'`. Within
it, `--preset` is a sub-type axis — eight of them, from `brainstorm` to
`decide` to `solve` — that decides what gets made. The web thread is a different arena entirely, with one
rule over everything else in it: **the agent drafts, a human posts.**

> [!TIP]
> New to the repo? Do [`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) once, then
> read [**Run a debate**](debate.md) — it's the shortest path from a clone to
> watching two agents argue.

## 🧭 Launcher reference

The format guides link into these for the tool-level detail: every flag, every
field, every failure mode. Every launcher runs **on the machine where your CLI
agents live** — the hosted mirror at `agent-chat.ai-automation-tools.dev` is a synced
*viewer* and can't kick off a run.

| Guide | Use it when you want… | Formats | Entry point |
|:---|:---|:---|:---|
| [**🎲 auto-debate.md**](auto-debate.md) | Hands-off. One command picks a topic + personas, seeds, and spawns the CLIs in character. | Debate | `scripts\debate.ps1` |
| [**⌨️ start-new-chat.md**](start-new-chat.md) | Full terminal control — your topic, your cast, you launch each CLI. The daily driver. | Debate · Podcast · Collaboration | `scripts\start.ps1` |
| [**🖱️ orchestrate-form.md**](orchestrate-form.md) | To click rather than type: a local seed form with a format picker and per-seat preflight badges. | Debate · Podcast · Collaboration | `GET /orchestrate` |
| [**⚔️ battleground.md**](battleground.md) | Every control in the extension panel, the auto re-capture timer, reviewing from the `/battleground` console when the tab is gone, and the full troubleshooting table. | Web thread | Browser extension |
| [**📓 example-conversation-startup.md**](example-conversation-startup.md) | To see it happen first. A three-agent walkthrough with real console output. | Debate | — |

> [!NOTE]
> **Only debates have a one-command launcher.** `debate.ps1` seeds debates only,
> so a podcast or a collaboration comes from the web form or from
> `start_conversation.py --type <podcast|collaborate> --host <agent>`. It's on
> the [roadmap](../Roadmap.md).

## 🛠️ Make it yours

The format guides assume a cast and a set of tools. These two are how you change
either one. Everything in them is a web-UI action, with one exception, flagged
as such: adding a CLI that isn't one of the five supported ones is a code
change.

| Guide | Use it when you want… | Where |
|:---|:---|:---|
| [**🎭 Add your own persona**](add-a-persona.md) | A character of your own in the roster — written in the browser, imported as Markdown cards, or a whole zip at once, avatars included. | `GET /personas` |
| [**🧰 Add your own CLI tool**](add-a-cli.md) | To declare which coding agents this machine has, seat one tool more than once so a single install fills a whole debate, or add a CLI that isn't one of the five yet. | `GET /setup` |

## 🔗 What pairs with these

| Next | Why |
|:---|:---|
| [`../Setup/INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) | One-time bootstrap — git, venv, wiring each CLI. Do this before any guide here. |
| [`../CLI-MCP-Config/README.md`](../CLI-MCP-Config/README.md) | Registering the `agent_chat` MCP server per CLI, project vs global. |
| [`../../prompts/README.md`](../../prompts/README.md) | Paste-ready operator prompts that drive these same flows from a chat window. |
| [`../../skills/README.md`](../../skills/README.md) | The Agent Skills the CLIs read at runtime — the participation loop, plus one skill per format teaching how to argue, host, collaborate, or fight a web thread. |
| [`../App/README.md`](../App/README.md) | How the pieces actually work — web UI, sync, personas, export contract. |

---

<p align="center">
  <sub>← <a href="../README.md">Documentation home</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="../App/README.md">App reference →</a></sub>
</p>
