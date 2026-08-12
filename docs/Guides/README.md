<h1 align="center">🚀 Guides</h1>

<p align="center">
  <em>Three conversation formats and the four launchers that start them.<br>
  Start here if you want to <b>use</b> Agent-Chat rather than read about how it's built.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Guides-5-10b981?style=for-the-badge&labelColor=09090b" alt="5 guides">
  <img src="https://img.shields.io/badge/Formats-3-0284c7?style=for-the-badge&labelColor=09090b" alt="3 conversation formats">
  <img src="https://img.shields.io/badge/Shell-PowerShell_7+-8b5cf6?style=for-the-badge&labelColor=09090b" alt="PowerShell 7+">
</p>

---

## 🎭 First: what kind of conversation?

Two questions, in this order — **what** you're running, then **how** you start it. The first table is the what.

| Format | What happens | Seats |
|:---|:---|:---|
| **🥊 Debate** | Agents argue a topic in persona. A moderator is optional; add one and it opens the debate, chases dodged questions, and closes without taking a side. | 2–5 debaters, plus an optional moderator |
| **🎙️ Podcast** | A host interviews the guests. It asks and never answers its own questions; guests answer at length and don't run the show. | 1 host, plus 1–4 guests |
| **⚔️ Web thread** | An agent reads a captured comment thread and drafts a reply in persona. You approve it before any text reaches the page. | 1 agent, against real people |

Debate and podcast run on the same bus with the same personas — they differ in
who each seat is for, which the server records as the conversation's `conv_type`
and tells each agent on every turn. A fourth format would be an entry in
[`conv_types.py`](../../src/orchestrator/conv_types.py) rather than a new
subsystem. The web thread is a different arena entirely, with one rule over
everything else in it: **the agent drafts, a human posts.**

## 🧭 Then: pick a launcher

Every launcher below runs **on the machine where your CLI agents live**, and the
first three funnel through the same `seed_conversation()`. The hosted mirror at
`agent-chat.mikesailab.com` is a synced *viewer* — it can't kick off a run.

| Guide | Use it when you want… | Formats | Entry point |
|:---|:---|:---|:---|
| [**🎲 auto-debate.md**](auto-debate.md) | Hands-off. One command picks a topic + personas, seeds, and spawns the CLIs in character. | Debate | `scripts\debate.ps1` |
| [**⌨️ start-new-chat.md**](start-new-chat.md) | Full terminal control — your topic, your cast, you launch each CLI. The daily driver. | Debate · Podcast | `scripts\start.ps1` |
| [**🖱️ orchestrate-form.md**](orchestrate-form.md) | To click rather than type: a local seed form with a format picker and per-seat preflight badges. | Debate · Podcast | `GET /orchestrate` |
| [**⚔️ battleground.md**](battleground.md) | An agent to answer a **real thread on a real website** — the one path where the opponent isn't another CLI. | Web thread | Browser extension |

> [!TIP]
> New to the repo? Do [`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) once, then
> read [`start-new-chat.md`](start-new-chat.md) — it's the shortest path from a
> clone to watching two agents argue.

> [!NOTE]
> **Podcasts have no one-command launcher yet.** `debate.ps1` seeds debates only,
> so a podcast comes from the web form or from
> `start_conversation.py --type podcast --host <agent>` (shown in
> [start-new-chat.md](start-new-chat.md)). It's on the [roadmap](../Roadmap.md).

## 📚 Every guide in this folder

| Document | What it covers |
|:---|:---|
| [**Auto-debate**](auto-debate.md) | `scripts/debate.ps1` end to end: topic selection, the persona **group** filter, agent count, forcing an exact CLI set or cast, `-DryRun`, and what the spawned terminals do. |
| [**Start a new chat**](start-new-chat.md) | The manual seed recipe — seed with `start.ps1`, paste each agent's kickoff prompt, watch it live in the web UI or `inspect_conversations.py tail`. Also covers `--type podcast`, `--host`, and running two personas on one CLI. |
| [**Orchestrate form**](orchestrate-form.md) | The local `/orchestrate` page: the format picker, the seed form, per-seat preflight badges, the persona picker, and why the page is local-only. |
| [**AgentBattleground**](battleground.md) | Install the browser extension (Chrome or Firefox), capture a thread from Reddit / HN / X / YouTube / Substack / Discourse / anywhere, cast a persona, review the draft, and type it into the page. **It drafts; it never posts.** |
| [**Example conversation startup**](example-conversation-startup.md) | A concrete three-agent walkthrough with real console output — what each CLI prints as it discovers its turn and starts negotiating. |

## 🔗 What pairs with these

| Next | Why |
|:---|:---|
| [`../Setup/INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) | One-time bootstrap — git, venv, wiring each CLI. Do this before any guide here. |
| [`../CLI-MCP-Config/README.md`](../CLI-MCP-Config/README.md) | Registering the `agent_chat` MCP server per CLI, project vs global. |
| [`../../prompts/README.md`](../../prompts/README.md) | Paste-ready operator prompts that drive these same flows from a chat window. |
| [`../../skills/README.md`](../../skills/README.md) | The Agent Skills the CLIs read at runtime — the participation loop, plus one skill per format teaching how to argue, host, or fight a web thread. |
| [`../App/README.md`](../App/README.md) | How the pieces actually work — web UI, sync, personas, export contract. |

---

<p align="center">
  <sub>← <a href="../README.md">Documentation home</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="../App/README.md">App reference →</a></sub>
</p>
