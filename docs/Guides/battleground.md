# Argue in a real web debate (AgentBattleground)

The fourth way to run an agent — and the only one where the opponent isn't
another CLI. You're reading a thread somewhere on the web (Reddit, X, Hacker
News, a comment section), you want one of your personas to answer it, and you
want to read the reply before anyone else does.

A Chrome extension captures the thread into an **arena**; the agent argues in
it over MCP; you approve the reply and it gets typed into the page's reply box.

> [!IMPORTANT]
> **It drafts. It never posts.** Every reply the agent writes lands in a review
> queue and needs your explicit approval. Approving types the text into the
> site's own composer and stops — *you* press the site's post button. There is
> no auto-post switch, on purpose: an agent quietly posting persona-driven
> replies into live threads is astroturfing, and it's also how accounts get
> banned. See [the rules the agent is given](#what-the-agent-is-told).

> [!NOTE]
> **Local only.** The extension talks to the web UI on `127.0.0.1:8765`.
> Captured page content is stored in `chat.db` but is deliberately **excluded
> from the Fly sync** — arenas and drafts never reach
> `agent-chat.mikesailab.com`.

---

## When to use this vs. the other three paths

| You want… | Use |
|:--|:--|
| Hands-off — random topic + personas + auto-spawned CLIs | [`auto-debate.md`](auto-debate.md) (`scripts/debate.ps1`) |
| Full control from the terminal | [`start-new-chat.md`](start-new-chat.md) (`scripts/start.ps1`) |
| Click to choose topic + cast in a form | [`orchestrate-form.md`](orchestrate-form.md) (`/orchestrate`) |
| An agent to answer a **real thread on a real website** | **this guide** |

The first three seed a conversation between CLIs. This one doesn't seed a
conversation at all — it opens an *arena*, which is a different table and a
different loop.

---

## Prerequisites

- The venv is set up and deps installed (see [`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md)).
- **The web UI is running** — it's the bridge the extension talks to:
  ```powershell
  .\.venv\Scripts\python.exe src\web_ui.py
  ```
  (Or it's already up via [autostart](../App/autostart.md) — check
  `http://127.0.0.1:8765/`.)
- Chrome 116+ (the extension uses the side-panel API).
- At least one CLI with the `agent_chat` MCP server registered (see
  [CLI-MCP-Config](../CLI-MCP-Config/README.md)).
- Optional but recommended: run the skill linker once so the CLIs know the
  battleground loop —
  ```powershell
  .\scripts\setup\setup-skill-links.ps1
  ```

---

## One-time: install the extension

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the repo's `extension/` folder.
4. Pin **AgentBattleground** to the toolbar so the button is one click away.

That's the whole install — it's an unpacked local extension, nothing is
published to the Chrome Web Store.

### Optional: require a token

By default the bridge accepts unauthenticated local calls, same as the rest of
the web UI. To lock it down, set the env var **before** starting the web UI and
paste the same value into the panel's ⚙ Settings:

```powershell
$env:AGENT_CHAT_BATTLEGROUND_TOKEN = "some-long-random-string"
.\.venv\Scripts\python.exe src\web_ui.py
```

---

## The flow, step by step

### 1 · Capture the thread

Open a page with an actual argument on it and click the **AgentBattleground**
toolbar button. The side panel opens.

Click **Capture this thread**. The first time you capture on a given domain,
Chrome asks whether to grant access to that site — the extension has **no
standing access to any website** and requests it per-domain, at the moment you
ask for it. Grant it and the panel reports what it found:

```
Captured 34 posts (reddit).
```

Scroll the comments into view first if the site lazy-loads them — the adapter
reads what's rendered.

### 2 · Cast the agent

Three fields:

| Field | What it does |
|:--|:--|
| **CLI agent** | Which CLI will argue. Only that agent can claim the arena. |
| **Persona** | A card from your roster, `🎲 random`, or none. The card body is **snapshotted** onto the arena, so editing the persona later won't change what a running arena's agent was told. |
| **Stance / brief** | Your instruction — which side, what to hit. *"Defend remote work. Go after the measurement claim in the top comment."* |

Click **Open arena**. The panel shows `Arena #12` and starts polling.

### 3 · Send the agent in

In that CLI's session, say:

```
join the battleground
```

The agent calls `get_arena()` — which hands it the thread, the persona, your
stance, and the house rules, and **claims** the arena so a second CLI can't
draft over it — then writes a reply and calls `submit_draft()`.

It should then go quiet on `wait_for_verdict()`. If it announces that it posted
something, the skill isn't loaded — check `/skills` in that CLI.

### 4 · Review

The draft appears in the panel with the agent's private `rationale` beneath it
(that note is never posted — it's where the agent flags what it couldn't
verify). You have three moves:

- **Edit the text in place** — the box is editable; your edits are what get
  used.
- **Approve & type into page** — writes the text into the site's reply box.
  Your AI-disclosure line is appended here (⚙ Settings, on by default).
  Nothing is submitted.
- **Reject…** — with a note. The agent reads the note as a revision brief and
  drafts again.

> [!TIP]
> "No reply box found" means the composer isn't open. The extension types into
> an **existing** reply box; it never opens one. Click the site's *Reply* button
> first, then approve.

### 5 · Post it, and tell the panel

Read it one more time, then press the site's own post button. Come back and
click **I posted it** — the panel reads the composer's final contents so the
agent learns the text that actually shipped (it sees `operator_edited: true`
and can match your voice next round).

### 6 · Follow-ups

The thread the agent has is a snapshot from capture time. When replies land,
click **Re-capture page**: known posts are refreshed in place, new ones
appended, and the panel reports `2 new posts for the agent`. Then tell the CLI
to check the arena again.

When you're done, **Close arena** — the agent can no longer draft into it.

---

## What the agent is told

Every arena payload carries the house rules in-band, so behavior doesn't depend
on the skill being installed on that particular CLI:

1. You are drafting, not posting.
2. Write in the persona's **voice** — never claim to *be* the named person, and
   never invent quotes, credentials, or first-hand experience.
3. You are an AI writing this; don't strip or contradict the disclosure line.
4. Argue the substance — engage the strongest version of what was said, cite
   what you can name, concede what's correct.
5. No harassment, slurs, doxxing, or pile-ons at a named private individual.
6. Match the room's length and register.

The [`battleground` skill](../../skills/battleground/SKILL.md) expands on this
with the hard stops (declining to draft, and saying why in `rationale`).

---

## Site support

| Site | Quality |
|:--|:--|
| **Reddit** | Best. New and old layouts, real comment ids, nesting depth. |
| **Hacker News** | Best. Story + comment tree with indent depth. |
| **X / Twitter** | Good. The visible reply chain; status ids as post ids. |
| **Anything else** | Generic fallback — headline, article lead, and comment-ish blocks over 40 characters. |

An adapter that finds nothing falls back to generic rather than opening an
empty arena. Adapters live in
[`extension/src/capture.js`](../../extension/src/capture.js) — each one only
has to find posts and give each a **stable id**, which is what makes
re-capture merge instead of duplicate.

---

## Troubleshooting

| Symptom | Fix |
|:--|:--|
| Status dot is red | Web UI isn't running, or the bridge URL in ⚙ Settings is wrong. Hit **Test connection**. |
| `/api/battleground/roster` 404s | The web UI is running **older code** — restart it. |
| "No readable posts found" | Adapter didn't match. Scroll comments into view and re-capture. |
| "No reply box found" | Open the site's reply form first. |
| Agent says there's no arena | It's assigned to a different CLI, or closed. Check the panel's arena line. |
| Agent says it posted something | The `battleground` skill isn't loading — check `/skills`, then re-run `setup-skill-links.ps1`. |
| Draft never appears | Agent hasn't called `submit_draft` yet. The panel polls every 3s; check the CLI output. |
| Persona dropdown is empty | No debater personas in the DB — add some at `/personas`. `AI-Models` cards are excluded on purpose. |

---

## Where to go next

- [`extension/README.md`](../../extension/README.md) — the extension's own
  install + usage reference.
- [`docs/App/battleground.md`](../App/battleground.md) — architecture, the
  bridge API, schema, and the security posture.
- [`skills/battleground/SKILL.md`](../../skills/battleground/SKILL.md) — what
  the agent reads.
- [`prompts/Battleground/`](../../prompts/Battleground/) — paste-ready operator
  prompts for running an arena.
