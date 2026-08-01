<div align="center">

# ⚔️ AgentBattleground

**A browser extension that puts an Agent-Chat CLI agent into a debate that's already happening on the web.**

<sub>Chrome 116+ · Firefox 128+</sub>

Capture the thread → cast a persona → the agent drafts a reply over MCP → you review it → it gets typed into the page's composer.

</div>

---

## What it does

Agent-Chat normally has two CLI agents argue with each other in a local SQLite database. AgentBattleground points that same machinery outward: you're reading a Reddit thread, an X reply chain, a YouTube comment war or a Discourse forum argument, and you want Claude Code (in character as one of your personas) to write the reply.

```
   this extension                 src/web_ui.py                 your CLI agent
  ┌───────────────┐   HTTP     ┌────────────────┐   SQLite    ┌───────────────┐
  │ capture page  │──────────▶ │ /api/          │◀──────────▶ │  MCP tools:   │
  │ review draft  │            │  battleground  │   chat.db   │  get_arena    │
  │ type into box │◀────────── │                │             │  submit_draft │
  └───────────────┘            └────────────────┘             └───────────────┘
```

No new server and no new port — the extension talks to the web UI you're already running, and the shared `chat.db` is the bus, exactly as it is for CLI-vs-CLI conversations.

## It drafts. It does not post.

This is the design constraint the whole thing is built around, not a setting:

- The agent's reply lands as a **pending draft**. Nothing is sent anywhere.
- You read it, edit it if you want, and click **Approve**.
- Approving **types the text into the site's own reply box** and stops. You press the site's post button yourself.
- If that box already has text in it, the panel **asks** before touching it, and reads the result back afterwards so "approved" never quietly means "nothing happened".
- An **AI-disclosure line** is appended on insert (on by default, editable in Settings).
- The extension has **no standing access to any website**. It asks per-domain, the first time you capture there, and you can revoke it in Chrome at any time.

Personas are voices, not identities — the house rules the agent receives forbid claiming to *be* a real person. Undisclosed persona-driven autoposting is astroturfing; this is a writing aid with a human in the loop.

## Install

**1. Run the bridge** (the normal Agent-Chat web UI):

```powershell
.\.venv\Scripts\python.exe src\web_ui.py
```

**2. Load the extension:**

- **Chrome / Edge / Brave** (116+, for `chrome.sidePanel`): open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and select this `extension/` folder. No build step.
- **Firefox** (128+): MV3 on Gecko is a different manifest — no `chrome.sidePanel`, a background `scripts` array instead of a service worker, and a `sidebar_action`. Stage it first, then load the staged folder:

  ```powershell
  .\scripts\build-extension.ps1            # → extension\dist\firefox\
  ```

  Then `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** → pick `extension\dist\firefox\manifest.json`. The panel opens in the sidebar from the toolbar button.

**3. Optional — require a token.** If you'd rather the bridge not accept unauthenticated calls, set it before starting the web UI and paste the same value into the panel's Settings:

```powershell
$env:AGENT_CHAT_BATTLEGROUND_TOKEN = "some-long-random-string"
```

## Use it

1. Open a page with an argument on it. Click the **AgentBattleground** toolbar button — the side panel opens.
2. **Capture this thread.** Chrome will ask for access to that site the first time. The panel reports how many posts it found.
3. **Check the preview.** *What the agent will see* lists the exact posts, in order, with nesting — see [Capture preview](#capture-preview). Optionally click **Answer this one** on the post you want answered.
4. **Cast:** pick the CLI agent, a persona (or 🎲 random, or none), and write a one-line stance brief — *"Defend Go; go after the compile-time claim."*
5. **Open arena.** The arena card now shows a ready-made prompt — hit **Copy prompt**, paste it into your CLI, and that's the handoff done ([details](#cli-handoff)).
6. The agent calls `get_arena`, reads the thread, and submits a draft. The toolbar badge turns amber when one is waiting.
7. The draft appears in the panel with a few [pre-flight checks](#draft-review). **Approve & type into page**, or **Reject…** — either with your own note or one of the one-click briefs (**Shorter**, **More evidence**, **Concede a point**…).
8. After you post it yourself, hit **I posted it** so the agent knows its reply is live.
9. New replies came in? **Re-capture page** merges them into the same arena — the agent sees only what's new. Or tick **Auto re-capture** on the arena card and let it do that on a timer.

## Capture preview

Before an arena exists you can see precisely what the agent will be handed: post count, distinct authors, which adapter matched, how many frames contributed, and — expanded — every captured post with its author, score, and nesting depth.

It exists for one failure in particular. When no site adapter matches, capture falls back to `generic`: page headline plus any text block over 40 characters. That still opens a working arena, so nothing *looks* wrong — the agent is just arguing with the page furniture. The preview says so in amber when it happens, before you spend a CLI turn on it.

**Answer this one** under any post hands that post to the agent as its reply target. `get_arena` then returns it as `reply_target` and tells the agent to pass the id back as `submit_draft(reply_to=…)`. Leave it unset and choosing what's worth answering stays the agent's call. You can re-target a live arena the same way — the change reaches the agent on its next `get_arena`.

## CLI handoff

After **Open arena**, the arena card carries the exact prompt to paste:

```
Join AgentBattleground arena #12.

Call get_arena(arena_id=12), read the captured thread, then write one
reply and call submit_draft(arena_id=12, content=..., reply_to=...).
Then call wait_for_verdict() and wait — I review it in the browser panel.
You are drafting, not posting. Nothing you write reaches the page until I
approve it.
```

**Copy prompt** puts it on the clipboard. **Copy launch command** copies the line that starts the CLI you cast, from the folder holding its MCP config (`cd agents/CLIs/codex_agent1; codex`).

The panel copies that command; it never runs it. A localhost HTTP endpoint that spawns processes on request is a different feature with a different threat model, and this one is a string.

The card hides itself once the first draft arrives — by then the handoff worked.

## Draft review

Each pending draft gets a few local heuristics above the Approve button — length against the median post in the thread, the LLM tells house rule 7 tells the agent to avoid, unsourced "studies show" authority, sentences that read as first-hand experience the agent doesn't have, and whether the AI-disclosure line is switched on. They're hints, not a gate: nothing here blocks approval, and they update as you edit.

**Reject…** opens both a free-text note and six one-click briefs — **Shorter**, **Less sharp**, **More evidence**, **Concede a point**, **Match the room**, **Answer someone**. Each sends a `rejected` verdict whose note the agent reads as a revision brief.

## Composer insertion

Approving types the text into the page's **existing** reply box and stops. Three things make that less fragile than it sounds:

- **Per-site composers.** Reddit, X, Hacker News, YouTube, LinkedIn, Substack, Discourse (sniffed from the page), and Disqus have their own selectors; anything else falls back to a generic list. A box you've clicked into always wins — the extension takes focus as the answer.
- **The right frame.** The composer is looked for in every frame the extension can reach and the text is typed into exactly one. A Disqus thread keeps its reply box inside its own iframe, and a top-frame-only insert would type into whatever search box the host page had.
- **Existing text is never silently clobbered.** If the box already holds something, the panel stops and asks: **Replace**, **Append**, or **Prepend**. The verdict is recorded on the way out of that choice, so nothing is marked approved while the question is still on screen.

Afterwards the box is **read back**. "Typed into the page and read back" means it's really there; a warning means the editor rejected the write and you should look at the page before posting. Some rich-text editors re-render from their own state and quietly drop what was set — "approved but nothing happened" is the worst failure this feature has, because your next move is to hit post.

## Auto re-capture

The arena card has an **Auto re-capture every _n_ s** switch (off by default, 30s floor, 90s suggested). While it's on, the panel re-captures the page on that interval and merges what's new, so the agent sees replies to its own post without you clicking anything.

It's deliberately timid, and skips a tick entirely when:

- the arena is closed, or the tab has drifted off the arena's page;
- you're typing in a draft (it never re-renders under your cursor);
- the extension doesn't already hold access to the site — **a background timer never raises a permission prompt**.

Three consecutive failures (bridge down, say) switch it off and say so, rather than retrying forever. The status line under the switch reports the last tick.

## Site support

| Site | Adapter | Notes |
|---|---|---|
| Reddit | `reddit` | New (`shreddit-*`) and old layouts; comment ids and nesting depth preserved. |
| X / Twitter | `x` | The visible reply chain; status ids as post ids. |
| Hacker News | `hackernews` | Story + comment tree with indent depth. |
| YouTube | `youtube` | Video + description as the OP, then loaded comment threads. Ids come from the `lc=` parameter — YouTube's own comment id — so they survive a sort change. |
| LinkedIn | `linkedin` | The post plus its comment tree; `data-id` comment urns, replies one level deeper. |
| Substack | `substack` | Any Substack, custom domain included (sniffed from the page, not the hostname). Post + threaded comments. |
| Discourse | `discourse` | Any Discourse forum — also sniffed, since every install has its own domain. `data-post-id` is the forum's own id. |
| Disqus | `disqus` | The comment iframe, when you opt into it (see below). |
| Anything else | `generic` | Page headline + article lead, plus comment-ish blocks over 40 characters. |

A site adapter that finds nothing (layout changed, wrong page type) falls back to `generic` rather than opening an empty arena. Adapters live in [`src/capture.js`](src/capture.js) — each one only has to find posts and give each a **stable id**, which is what makes re-capture merge cleanly instead of duplicating.

### Comments in an iframe

Plenty of news sites host their comments in a third-party frame (Disqus and friends), which is a separate origin and therefore a separate permission. When a capture spots one, the panel offers an **Include disqus.com** button under the summary — click it, grant that origin, and the capture folds the frame's comments into the same thread. Ids from a frame are namespaced (`disqus:501`) so they can't collide with the host page's, and stay stable across re-captures.

Frames you haven't opted into are never read, and a frame that isn't a recognised comment platform is ignored even if it is readable — otherwise every ad iframe on the page would end up in the arena.

## Files

```
extension/
├── manifest.json          # MV3 (Chrome); no static content scripts, per-domain opt-in
├── manifest.firefox.json  # MV3 (Gecko): sidebar_action, background scripts, gecko id
├── icons/
│   ├── icon-{16,32,48,128}.png
│   └── make_icons.py      # regenerates them; no image library needed
└── src/
    ├── background.js      # service worker / event page — panel behavior + per-tab badge
    ├── capture.js         # injected on demand into every allowed frame; site adapters
    └── panel/             # the operator surface: capture, cast, review, insert
        ├── panel.html
        ├── panel.css
        ├── panel.js       # entry: wiring + init only
        └── lib/           # ES modules, loaded by panel.html as type="module"
            ├── state.js       # shared state object + DOM helpers
            ├── settings.js    # chrome.storage-backed settings
            ├── bridge.js      # every HTTP call to the Agent-Chat web UI
            ├── permissions.js # per-origin access, requested from a gesture
            ├── capture.js     # injecting src/capture.js, folding frames together
            ├── arena.js       # arena lifecycle, review poll, auto re-capture
            ├── compose.js     # the page's reply box — types, never submits
            ├── drafts.js      # the review queue and the verdict gate
            └── view.js        # rendering: preview, handoff, arena, drafts
```

The modules form a couple of import cycles (`arena → view → drafts → arena`), which is why they share one mutable `state` object rather than each exporting its own `let`, and why every export that crosses a cycle is a `function` declaration — declarations are hoisted, so a partially-evaluated module can still be called into.

The Firefox build is staged by [`scripts/build-extension.ps1`](../scripts/build-extension.ps1) into `extension/dist/firefox/` (gitignored) — it's the same `src/` and `icons/` with the Gecko manifest dropped in as `manifest.json`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Status dot is red | The web UI isn't running, or the bridge URL/port in Settings is wrong. **Test connection** in Settings reports which — it asks `/healthz` separately, so it can tell "not running" apart from "running and refusing your token". |
| Preview warns it fell back to `generic` | No site adapter matched this page. The arena will hold the headline plus loose text blocks, not the argument. Scroll the comments into view and re-capture, or check whether the comments live in a frame. |
| "No readable posts found" | The adapter didn't match. Scroll the comments into view (some sites lazy-load) and re-capture. |
| Comments are missing on a news site | They're probably in a third-party frame — look for the **Include …** button under the capture summary. |
| Auto re-capture says "paused after 3 failures" | The bridge went away mid-run. Fix it, then tick the switch back on. |
| Auto re-capture never ticks | The status line says why: the tab drifted off the arena's page, the arena is closed, or the site permission was revoked. |
| "No reply box found" | Open the site's reply form *first* — the extension types into an existing composer, it never opens one. Clicking into the box before you approve also tells it exactly which one you mean. |
| "Typed, but reading the box back didn't show the text" | The site's editor rejected the write and re-rendered from its own state. Look at the page before posting; if it's empty, paste it in yourself. |
| Agent says there's no arena | It's assigned to a different CLI, or the arena is closed. Check the panel's arena line. |
| Draft never appears | The agent hasn't called `submit_draft` yet. The panel polls every 3s; check the CLI's output. Did the handoff prompt actually get pasted? |

## Reference

- [`docs/Guides/battleground.md`](../docs/Guides/battleground.md) — **the full step-by-step operator guide** (start here).
- [`docs/App/battleground.md`](../docs/App/battleground.md) — architecture, API, schema, security posture.
- [`skills/battleground/SKILL.md`](../skills/battleground/SKILL.md) — what the agent is told.
- [`prompts/Battleground/`](../prompts/Battleground/README.md) — paste-ready operator prompts.

## Enhancements / updates

The next improvements should preserve the core invariant: **the extension drafts, it never posts**. Approving may type text into a composer, but the final submit remains the operator's click.

### Highest priority

- **Real browser shakedown.** Load the unpacked Chrome extension and the staged Firefox build, then run the full loop: capture -> preview -> cast -> draft -> approve -> text lands in the composer without submitting. Also verify first-capture permissions, `sidebarAction.open()` on Firefox, auto re-capture, and the comment-frame **Include ...** path. **Nothing below is trustworthy until this is done** — the panel is exercised by a Node stub and a Python test suite, neither of which can speak to `chrome.permissions` or `chrome.scripting`.
- **Local `/battleground` page.** Add a web UI page for arena history: arena list, pending draft counts, captured thread, cast, status, every draft, and verdict history. Keep page insertion in the extension, but make review and auditing possible without the original tab open.
- **Finish the token story.** The panel now warns when the bridge accepts unauthenticated calls and gives the setup line ([`/healthz`](../docs/App/battleground.md#bridge-api--apibattleground) reports `token_required`). Still open: a token generator, and restricting CORS to the installed extension id rather than any `chrome-extension://` origin.

### Feature ideas

- **Competing drafts mode.** Let multiple agents or personas draft for the same arena, then let the operator pick, edit, or blend the best reply.
- **Arena export.** Export a local-only Markdown or ZIP bundle containing the captured thread, stance, persona snapshot, drafts, verdicts, and posted text.
- **Bridge-down notification.** The toolbar badge covers a waiting draft; a bridge that dies mid-review is still only visible as a red dot in an open panel.
- **Adapter expansion.** Add stable-id adapters for more comment systems and networks, especially Mastodon, Lemmy, Guardian/Coral, OpenWeb, and large news-site comment stacks.
- **Smarter draft checks.** The pre-flight list is deliberately shallow (string matching). Tone fit and site risk would need something that actually reads the thread.

### Engineering cleanup

- **Add browser E2E coverage.** Unit tests cover the bridge well; the riskiest pieces are browser APIs: permissions, side panel/sidebar behavior, `chrome.scripting`, and composer insertion.
- **Add adapter fixtures.** Keep sanitized HTML fixtures for supported sites and run `capture.js` against them so selector drift is caught before manual testing.
- **Centralize schema/migrations.** The battleground tables are mirrored across the MCP server, web DB, and seeding code. Tests catch drift, but a shared schema module would remove a repeated footgun.

### Shipped

<details>
<summary>Enhancements from this list that are done (2026-08-01)</summary>

- **Easier CLI handoff** — copyable join prompt on the arena card, plus a copyable launch command for the cast CLI. Deliberately *not* a **Launch selected CLI** button: the panel copies the command and the operator runs it, because a localhost endpoint that spawns processes is a different threat model.
- **Capture preview** — post list with authors, nesting, adapter, frame count, and an explicit warning on a `generic` fallback.
- **Targeted reply selection** — **Answer this one** in the preview, stored as `reply_to` on the arena and handed to the agent as `reply_target`.
- **Composer insertion hardening** — per-site composers, cross-frame targeting, replace / append / prepend when the box isn't empty, and a read-back confirmation.
- **Revision quick actions** — six one-click rejection briefs.
- **Draft scoring** — local pre-flight checks above the Approve button.
- **Notifications** — amber toolbar badge when a draft is waiting.
- **Token setup UX** — a warning and the setup line when the bridge runs without a token.
- **`/healthz`** — `{ok, db, schema, readonly, token_required}`, answered without a token so it can explain why the other calls fail.
- **Split `panel.js`** — nine modules under `src/panel/lib/`.

</details>

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../docs/Guides/battleground.md">Operator guide</a></sub>
</p>
