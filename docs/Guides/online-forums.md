<h1 align="center">⚔️ Participate in online forums</h1>

<p align="center">
  <em>Send an agent into a real comment thread on a real website. It writes the reply; you decide whether anyone ever sees it.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/format-web_thread-0284c7?style=for-the-badge&labelColor=09090b" alt="Format: web thread">
  <img src="https://img.shields.io/badge/it_drafts-never_posts-F59E0B?style=for-the-badge&labelColor=09090b" alt="It drafts, never posts">
  <a href="README.md"><img src="https://img.shields.io/badge/↩-Guides-6B7280?style=for-the-badge&labelColor=09090b" alt="Back to Guides"></a>
</p>

---

> [!IMPORTANT]
> **It drafts. It never posts.** Every reply lands in a review queue and waits
> for you. Approving types the text into the site's own reply box and stops —
> *you* press the site's post button. There is no auto-post switch and there
> won't be one. An agent quietly dropping persona-driven replies into live
> threads is astroturfing, and it's also the fastest way to get an account
> banned.

## 🌐 What this is

The other two formats put CLI agents in a room together. This one puts one agent
into an argument that already exists, with strangers in it.

You're reading a thread somewhere — Reddit, Hacker News, X, YouTube, LinkedIn,
Substack, a Discourse forum, any comment section — and you want one of your
personas to answer it. A browser extension captures the thread into an
**arena**. Your agent reads that arena over MCP, writes a reply, and hands it
back. You read it before anyone else does.

It's a different table and a different loop from a debate or a podcast: nothing
here seeds a conversation, and there's no turn rotation. There's a thread, an
agent, and a review gate.

| | Debate / podcast | This |
|:---|:---|:---|
| **Who's arguing** | Your CLIs, with each other | Your CLI, with real people |
| **Where it lives** | `conversations` + `messages` | `battleground_arenas` + `battleground_drafts` |
| **Reaches the hosted mirror** | Yes, via the sync sidecar | **No.** Captured page content is deliberately excluded. |
| **Who publishes** | Nobody — it's a transcript | You, by hand, on the site itself |

---

## 🧰 Before you start

- The venv installed — see [`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md).
- **The web UI running.** It's the bridge the extension talks to:
  ```powershell
  .\.venv\Scripts\python.exe src\web_ui.py
  ```
- Chrome 116+ for the side panel, or Firefox 128+ via `.\scripts\build-extension.ps1`.
- At least one CLI with the `agent_chat` MCP server registered.
- Recommended: `.\scripts\setup\setup-skill-links.ps1` once, so your CLIs read
  the battleground loop.

### Install the extension

1. Open `chrome://extensions`.
2. Turn on **Developer mode**, top right.
3. **Load unpacked**, and pick the repo's `extension/` folder.
4. Pin **AgentBattleground** to the toolbar.

That's all of it. Nothing is published to the Chrome Web Store; it's an unpacked
local extension talking to your own machine.

---

## 🔁 A round, start to finish

### 1 · Capture the thread

Open the panel on a page with an actual argument on it and click **Capture this
thread**. Chrome asks whether to grant access to that domain — the extension
ships with **no standing access to any site** and asks per domain, at the moment
you click. Scroll the comments into view first if the site lazy-loads them; the
adapter reads what's rendered.

Then read the **What the agent will see** preview. It's worth thirty seconds for
one reason: when no adapter matches, the capture falls back to `generic` and
grabs the page furniture instead of the argument. That opens a perfectly
working arena, so nothing looks broken — the preview flags it in amber before
you spend a CLI turn finding out.

### 2 · Cast the agent

Pick which CLI argues, which persona it wears, and give it a stance — *"Defend
remote work. Go after the measurement claim in the top comment."* The persona
body is **snapshotted** onto the arena, so editing that card later can't change
what a running arena's agent was told to be.

The persona can come from your roster, from `🎲 random`, or from
`✎ custom instructions…` — that last one opens a textarea and casts the arena
as a character you write on the spot, for this thread only. Nothing is added to
`/personas`. See [Writing a persona on the spot](battleground.md#writing-a-persona-on-the-spot).

### 3 · Send it in

The arena card carries a ready-made prompt with the arena number already in it.
Copy it into the CLI. The agent calls `get_arena()` (which claims the arena, so
a second CLI can't draft over it), writes a reply, calls `submit_draft()`, and
then goes quiet on `wait_for_verdict()`.

If it announces that it posted something, the skill isn't loaded on that CLI.

### 4 · Review

The toolbar badge turns amber when a draft is waiting. You get the text, the
agent's private `rationale` beneath it, and a few string-matching checks —
length against the thread's norm, LLM tells, unsourced "studies show" authority,
claims of first-hand experience the agent doesn't have. They block nothing.

Three moves: **edit in place**, **approve** (types it into the site's reply box
and stops), or **reject** with a one-click brief — *Shorter*, *Less sharp*,
*More evidence*, *Concede a point*, *Match the room*, *Answer someone* — and the
agent drafts again.

### 5 · Post it yourself

Read it once more, press the site's post button, then click **I posted it**.
The panel reads back what actually shipped, so the agent sees your edits and can
match your voice next round.

> [!TIP]
> "No reply box found" means the composer isn't open. The extension types into
> an **existing** box and never opens one. Click the site's *Reply* button
> first, and click into the box — a focused editor beats every selector the
> extension has.

---

## 📜 What the agent is told

The house rules ship inside every `get_arena` payload, so behavior doesn't
depend on a skill being installed on that particular CLI. In short: you are
drafting, not posting; write in the persona's **voice** and never claim to *be*
that person; you're an AI and the disclosure line stays; argue the substance;
no harassment or pile-ons at a private individual; match the room's length; and
write like a person rather than a model.

That last one has teeth in this venue specifically. A real thread is the least
forgiving place for LLM tells — readers spot them instantly and dismiss the
argument on style before they read it.

Full text and the hard stops are in
[`skills/battleground/SKILL.md`](../../skills/battleground/SKILL.md).

---

## 🗺️ Which sites work well

| Site | Quality |
|:---|:---|
| **Reddit · Hacker News · Discourse** | Best. Real comment ids and nesting, so re-capture merges cleanly. |
| **YouTube · X · Substack · LinkedIn** | Good. The visible thread, keyed on the site's own ids. |
| **Disqus** | Good, once you grant the comment frame — it's a separate origin and gets its own button. |
| **Anything else** | Generic fallback: headline, lead, and comment-ish blocks over 40 characters. |

Adapters live in [`extension/src/capture.js`](../../extension/src/capture.js).
Each one only has to find posts and give each a **stable id** — that's what
makes a re-capture merge new replies in rather than duplicate the thread.

---

## 🔒 Where the data goes

Nowhere. The two arena tables are left out of the local-to-hosted sync on
purpose, so third-party page content never reaches
`agent-chat.mikesailab.com`. The bridge's CORS policy answers only
`chrome-extension://` origins, and only under `/api/battleground/`.

---

## 🩺 When it doesn't work

| Symptom | Fix |
|:---|:---|
| Status dot is red | Web UI isn't running, or the bridge URL is wrong. **Test connection** tells "not running" apart from "running and refusing your token". |
| `/healthz` 404s | The web UI is running older code. Restart it. |
| Preview fell back to `generic` | No adapter matched. Scroll the comments in and re-capture, or look for a comment frame. |
| Comments missing on a news site | They're in a third-party frame — click the **Include …** button. |
| Agent says there's no arena | It's assigned to a different CLI, or it's closed. |
| Draft never appears | The agent hasn't called `submit_draft` yet. The panel polls every 3s; check the CLI output. |
| Persona dropdown is empty | No debater personas in the DB. Add some at `/personas` — `AI-Models` cards are excluded on purpose. `✎ custom instructions…` still works: it needs no roster. |
| Panel shows an old arena on a new page | The tab→arena link is per **tab**, not per URL, so navigating doesn't detach it. Click **↺ Start over** on the arena card. (The top button reading *Re-capture this thread* rather than *Capture this thread* is the tell.) |

The long-form table, including the auto-re-capture states, is in
[battleground.md](battleground.md#troubleshooting).

---

## 🔗 Where to go next

| Next | Why |
|:---|:---|
| [**AgentBattleground guide**](battleground.md) | This flow in full detail — every panel control, the auto re-capture timer, the complete troubleshooting table. |
| [**Extension README**](../../extension/README.md) | Install for Chrome and Firefox, plus the enhancement list. |
| [**Battleground reference**](../App/battleground.md) | Arenas, the bridge API, the schema, and the security posture. |
| [**Operator prompts**](../../prompts/Battleground/) | Paste-ready prompts for joining and managing arenas. |
| [**Run a debate**](debate.md) | The format where the opponent is another CLI. |

---

<p align="center">
  <sub>← <a href="README.md">Guides home</a> · <a href="../README.md">Documentation</a> · <a href="debate.md">Run a debate</a> · <a href="podcast.md">Run a podcast</a></sub>
</p>
