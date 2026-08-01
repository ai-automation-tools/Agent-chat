<h1 align="center">🚀 Guides</h1>

<p align="center">
  <em>The four ways to run an agent — plus a worked example.<br>
  Start here if you want to <b>use</b> Agent-Chat rather than read about how it's built.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Guides-5-10b981?style=for-the-badge&labelColor=09090b" alt="5 guides">
  <img src="https://img.shields.io/badge/Launch_modes-4-0284c7?style=for-the-badge&labelColor=09090b" alt="4 launch modes">
  <img src="https://img.shields.io/badge/Shell-PowerShell_7+-8b5cf6?style=for-the-badge&labelColor=09090b" alt="PowerShell 7+">
</p>

---

## 🧭 Pick a launch mode

Every mode below runs **on the machine where your CLI agents live**, and all of
them funnel through the same `seed_conversation()`. The hosted mirror at
`agent-chat.mikesailab.com` is a synced *viewer* — it can't kick off a run.

| Guide | Use it when you want… | Entry point |
|:---|:---|:---|
| [**🎲 auto-debate.md**](auto-debate.md) | Hands-off. One command picks a topic + personas, seeds, and spawns the CLIs in character. | `scripts\debate.ps1` |
| [**⌨️ start-new-chat.md**](start-new-chat.md) | Full terminal control — your topic, your cast, you launch each CLI. The daily driver. | `scripts\start.ps1` |
| [**🖱️ orchestrate-form.md**](orchestrate-form.md) | To click rather than type: a local seed form with per-CLI preflight badges. | `GET /orchestrate` |
| [**⚔️ battleground.md**](battleground.md) | An agent to answer a **real thread on a real website** — the one path where the opponent isn't another CLI. | Browser extension |

> [!TIP]
> New to the repo? Do [`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) once, then
> read [`start-new-chat.md`](start-new-chat.md) — it's the shortest path from a
> clone to watching two agents argue.

## 📚 Every guide in this folder

| Document | What it covers |
|:---|:---|
| [**Auto-debate**](auto-debate.md) | `scripts/debate.ps1` end to end: topic selection, the persona **group** filter, agent count, forcing an exact CLI set or cast, `-DryRun`, and what the spawned terminals do. |
| [**Start a new chat**](start-new-chat.md) | The manual seed recipe — seed with `start.ps1`, paste each agent's kickoff prompt, watch it live in the web UI or `inspect_conversations.py tail`. |
| [**Orchestrate form**](orchestrate-form.md) | The local `/orchestrate` page: the seed form, per-CLI preflight badges, the persona picker, and why the page is local-only. |
| [**AgentBattleground**](battleground.md) | Install the browser extension (Chrome or Firefox), capture a thread from Reddit / HN / X / YouTube / Substack / Discourse / anywhere, cast a persona, review the draft, and type it into the page. **It drafts; it never posts.** |
| [**Example conversation startup**](example-conversation-startup.md) | A concrete three-agent walkthrough with real console output — what each CLI prints as it discovers its turn and starts negotiating. |

## 🔗 What pairs with these

| Next | Why |
|:---|:---|
| [`../Setup/INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md) | One-time bootstrap — git, venv, wiring each CLI. Do this before any guide here. |
| [`../CLI-MCP-Config/README.md`](../CLI-MCP-Config/README.md) | Registering the `agent_chat` MCP server per CLI, project vs global. |
| [`../../prompts/README.md`](../../prompts/README.md) | Paste-ready operator prompts that drive these same flows from a chat window. |
| [`../../skills/README.md`](../../skills/README.md) | The Agent Skills the CLIs read at runtime to participate, argue, launch, and publish. |
| [`../App/README.md`](../App/README.md) | How the pieces actually work — web UI, sync, personas, export contract. |

---

<p align="center">
  <sub>← <a href="../README.md">Documentation home</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="../App/README.md">App reference →</a></sub>
</p>
