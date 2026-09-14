# Argue in a real web debate (AgentBattleground)

The fourth way to run an agent — and the only one where the opponent isn't
another CLI. You're reading a thread somewhere on the web (Reddit, X, Hacker
News, YouTube, a Discourse forum, any comment section), you want one of your
personas to answer it, and you want to read the reply before anyone else does.

A browser extension captures the thread into an **arena**; the agent argues in
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
> `agent-chat.ai-automation-tools.dev`.

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
  (Or it's already running — check `http://127.0.0.1:8765/`.)
- Chrome 116+ (side-panel API), or Firefox 128+ via
  `.\scripts\build-extension.ps1` (see
  [`extension/README.md`](../../extension/README.md#install)).
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

If the page keeps its comments in a third-party frame (common on news sites —
Disqus and the like), an **Include disqus.com** button appears under that
summary. That frame is a separate origin, so it's a separate grant: click it,
allow, and the capture folds those comments into the same thread.

### 1b · Check the preview

Under the capture summary, **What the agent will see** reports the post count,
distinct authors, the adapter that matched, and how many frames contributed.
Expand it and you get the posts themselves — author, score, nesting — in the
order the agent will read them.

Worth thirty seconds, for one reason. When no adapter matches, the capture
falls back to `generic`: the page headline plus every text block over 40
characters. That opens a perfectly functional arena, so nothing looks broken —
the agent is just arguing with the page furniture. The preview says so in
amber when it happens, before you spend a CLI turn finding out.

**Answer this one**, on any post, hands that post to the agent as its reply
target. `get_arena` then returns it as `reply_target` and tells the agent to
pass the id back on `submit_draft`. Leave it alone and picking the post worth
answering stays the agent's job — which is usually the right call. Use it when
you want a specific claim hit, or when the thread is long enough that the agent
might reasonably choose differently. You can re-target a live arena the same
way; the change reaches the agent on its next `get_arena`.

### 2 · Cast the agent

Three fields:

| Field | What it does |
|:--|:--|
| **CLI agent** | Which CLI will argue. Only that agent can claim the arena. |
| **Persona** | A card from your roster, `🎲 random`, `✎ custom instructions…`, or none. The card body is **snapshotted** onto the arena, so editing the persona later won't change what a running arena's agent was told. |
| **Stance / brief** | Your instruction — which side, what to hit. *"Defend remote work. Go after the measurement claim in the top comment."* |

Click **Open arena**. The panel shows `Arena #12` and starts polling.

#### Writing a persona on the spot

Pick **✎ custom instructions…** and the picker opens a name field and a
textarea. Type the character card — the same thing a `/personas` row holds, but
for this arena only:

```
You are a semi-retired structural engineer who has reviewed 400 bridge
inspections and has no patience for vibes.

Voice: dry, specific, allergic to adjectives. Short sentences.
What you argue: load numbers, inspection records, what the code actually says.
What you never do: guess at a figure, or soften a wrong claim to be polite.
```

The **Name** is only a label — it's what the arena card and `list_arenas` call
the character. Leave it blank and it reads `Custom persona`.

Use this when you want a voice *once*. Nothing is written to the registry: a
custom card won't appear at `/personas` or in the next capture's dropdown. It
is remembered in the extension's own storage, so a half-written card survives
closing the panel, and switching to a roster persona to compare doesn't throw it
away. If you find yourself pasting the same card a third time, that's the signal
to add it at `/personas` properly.

Everything downstream treats it exactly like a roster card — the agent can't
tell which way it was cast. What it can't do is rewrite the house rules: a card
telling the agent to claim it's a real person, or to hide that an AI wrote the
reply, loses to rules 2 and 3 below.

### 3 · Send the agent in

The arena card carries the prompt to paste, already filled in with the arena
number. Hit **Copy prompt**, drop it into the CLI, and you're done:

```
Join AgentBattleground arena #12.

Call get_arena(arena_id=12), read the captured thread, then write one
reply and call submit_draft(arena_id=12, content=..., reply_to=...).
Then call wait_for_verdict() and wait — I review it in the browser panel.
You are drafting, not posting. Nothing you write reaches the page until I
approve it.
```

If the CLI isn't running yet, **Copy launch command** gives you the line that
starts it from the folder holding its MCP config (`cd agents/CLIs/codex_agent1;
codex`). The panel copies it; you run it. Nothing here spawns a process — a
localhost endpoint that starts programs on request is a different feature with
a different threat model.

A bare `join the battleground` still works if the `battleground` skill is
installed on that CLI. The copyable prompt is what makes it work on the ones
where it isn't.

Either way the agent calls `get_arena()` — which hands it the thread, the
persona, your stance, your reply target if you set one, and the house rules,
and **claims** the arena so a second CLI can't draft over it — then writes a
reply and calls `submit_draft()`.

It should then go quiet on `wait_for_verdict()`. If it announces that it posted
something, the skill isn't loaded — check `/skills` in that CLI.

### 4 · Review

The toolbar badge turns amber when a draft is waiting, so you don't have to sit
in the panel while the agent writes.

The draft appears with the agent's private `rationale` beneath it (that note is
never posted — it's where the agent flags what it couldn't verify) and a short
list of pre-flight checks: length against the typical post in this thread, LLM
tells, unsourced "studies show" authority, sentences that read as first-hand
experience the agent doesn't have, and whether your disclosure line is on. They
are string-matching heuristics, they update as you edit, and they block
nothing.

Three moves:

- **Edit the text in place** — the box is editable; your edits are what get
  used.
- **Approve & type into page** — writes the text into the site's reply box.
  Your AI-disclosure line is appended here (⚙ Settings, on by default).
  Nothing is submitted.
- **Reject…** — opens a free-text note *and* six one-click briefs
  (**Shorter**, **Less sharp**, **More evidence**, **Concede a point**,
  **Match the room**, **Answer someone**). Either way the agent reads it as a
  revision brief and drafts again.

If the reply box already has text in it, approving stops and asks: **Replace**,
**Append**, or **Prepend**. Nothing is overwritten behind your back.

After typing, the panel reads the box back. *"Typed into the page and read
back"* means the text is really there. A warning means the site's editor
rejected the write — look at the page before you post.

> [!TIP]
> "No reply box found" means the composer isn't open. The extension types into
> an **existing** reply box; it never opens one. Click the site's *Reply* button
> first, then approve. Clicking *into* the box also settles any ambiguity about
> which one you meant — a focused editor beats every selector the extension has.

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

Rather than watching for replies yourself, tick **Auto re-capture every _n_ s**
on the arena card (off by default, 30-second floor). The panel then refreshes
the thread on that timer and reports what it merged. It skips a tick while
you're editing a draft, if the tab has moved off the arena's page, or if the
site permission isn't already granted — a background timer never raises a
permission prompt — and it switches itself off after three straight failures.
It still only *reads*: nothing about the timer touches the posting gate.

When you're done, **Close arena** — the agent can no longer draft into it.

### Reviewing without the tab

The panel is bound to a tab, which is right for capture and for typing into the
page — both need it. Everything after the draft doesn't. Open
**`http://127.0.0.1:8765/battleground`** for the console: every arena you've
captured on this machine, with a **pending** badge on the ones waiting for you,
and a filter for open vs closed.

Click an arena and you get the captured thread (your reply target highlighted),
the persona it was cast with, and every draft with its verdict, the agent's
rationale, and any edit you made before posting. **Approve**, **Reject with a
note…** and **I posted this** all work from there, along with close/reopen and
delete.

What it can't do is type into the page — that needs the tab, so it stays with
the extension. Approving in the console marks the draft ready and stops; go back
to the panel on the thread's tab when you want the text in the reply box.

### Moving on to the next page

The panel stays attached to its arena **per tab**, so a tab that opened an
arena keeps showing it — including after you navigate that tab somewhere else.
The tell is the big button at the top: it reads **Re-capture this thread**
while you're still attached, and **Capture this thread** when you're free.

**↺ Start over — capture a different page** (on the arena card) detaches this
tab and clears the capture, putting the panel back at step 1 for whatever page
you're on now. It is **not** destructive: the arena and every draft on it stay
on the server, so a CLI mid-argument keeps working and `list_arenas` still
finds it. Hit **Close arena** first if you actually want it finished.

Opening the next thread in a **new tab** needs none of this — links are
per-tab, so a fresh tab starts clean.

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
7. Write like a person, not a model — drop the puffery vocabulary, don't reach
   for three by reflex, no `-ing` clauses bolted on to fake depth, vary
   sentence length, take a position. Real threads are the least forgiving
   venue for LLM tells: readers spot them instantly and dismiss the reply on
   style before reading the argument. The persona sets the voice; this only
   strips the machine tells. **It never overrides rule 3** — the disclosure
   line stays and the agent never claims to be human.

The [`battleground` skill](../../skills/battleground/SKILL.md) expands on this
with the hard stops (declining to draft, and saying why in `rationale`), and
[`humanizer`](../../skills/humanizer/SKILL.md) is the full catalogue behind
rule 7.

> [!NOTE]
> **The rules are read live, not snapshotted.** Unlike a conversation's
> `kickoff_template` (frozen onto the row at seed time), `_ARENA_RULES` is read
> from the server at every `get_arena` call — so a rules change reaches **every
> arena, including ones captured earlier**. No re-capture needed. What you *do*
> need is to **restart the CLI**, since its MCP server process holds the old
> module in memory. Persona bodies are the opposite: those *are* snapshotted at
> capture time, so a persona edit needs a fresh capture.

---

## Site support

| Site | Quality |
|:--|:--|
| **Reddit** | Best. New and old layouts, real comment ids, nesting depth. |
| **Hacker News** | Best. Story + comment tree with indent depth. |
| **Discourse** | Best. Any forum on the platform, detected from the page rather than the domain; the forum's own post ids. |
| **YouTube** | Good. Video + description as the OP, then the loaded comment threads, keyed on YouTube's own comment ids. |
| **X / Twitter** | Good. The visible reply chain; status ids as post ids. |
| **Substack** | Good. Any Substack including custom domains; post + threaded comments. |
| **LinkedIn** | Good. The post and its comment tree, keyed on comment urns. |
| **Disqus** | Good, once you grant the frame (see step 1). |
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
| Status dot is red | Web UI isn't running, or the bridge URL in ⚙ Settings is wrong. Hit **Test connection** — it asks `/healthz` separately, so it can tell "not running" apart from "running and refusing your token". |
| `/api/battleground/roster` or `/healthz` 404s | The web UI is running **older code** — restart it. |
| Preview says it fell back to `generic` | No adapter matched this page, so the arena holds page furniture rather than the argument. Scroll the comments in and re-capture, or check for a comment frame. |
| "No readable posts found" | Adapter didn't match. Scroll comments into view and re-capture. |
| Comments missing on a news site | They're in a third-party frame — click the **Include …** button under the capture summary. |
| Auto re-capture isn't firing | The status line under the switch says why (tab moved, arena closed, no site permission, or paused after 3 failures). |
| Panel still shows the last arena on a new page | The tab→arena link is keyed on the **tab**, not the URL, so navigating that tab doesn't detach it — the top button reading **Re-capture this thread** is the tell. Click **↺ Start over**, or open the next thread in a new tab. |
| Clicked Start over but the agent is still working | That's intended. Start over only detaches *your panel*; the arena and its drafts live on the server. Use **Close arena** to actually stop the agent drafting. |
| "No reply box found" | Open the site's reply form first, and click into it so the extension knows which box you mean. |
| "Typed, but reading the box back didn't show the text" | The site's editor rejected the write. Check the page before posting; paste it yourself if it's empty. |
| Settings warns the bridge takes calls without a token | Informational. Fine on a machine only you use; the warning includes the line to set if you'd rather it didn't. |
| Agent says there's no arena | It's assigned to a different CLI, or closed. Check the panel's arena line. |
| Agent says it posted something | The `battleground` skill isn't loading — check `/skills`, then re-run `setup-skill-links.ps1`. |
| Draft never appears | Agent hasn't called `submit_draft` yet. The panel polls every 3s; check the CLI output. |
| Persona dropdown is empty | No debater personas in the DB — add some at `/personas`. `AI-Models` cards are excluded on purpose. `✎ custom instructions…` works regardless: it doesn't need a roster. |
| "Write the custom persona's instructions first" | The custom option is selected with an empty textarea. Type the card, or switch the dropdown back to a roster persona / none. |

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
