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
3. **Cast:** pick the CLI agent, a persona (or 🎲 random, or none), and write a one-line stance brief — *"Defend Go; go after the compile-time claim."*
4. **Open arena.**
5. In that CLI, say: **`join the battleground`**. The agent calls `get_arena`, reads the thread, and submits a draft.
6. The draft appears in the panel. **Approve & type into page**, or **Reject…** with a note (the agent reads it as a revision brief and tries again).
7. After you post it yourself, hit **I posted it** so the agent knows its reply is live.
8. New replies came in? **Re-capture page** merges them into the same arena — the agent sees only what's new. Or tick **Auto re-capture** on the arena card and let it do that on a timer.

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
        └── panel.js
```

The Firefox build is staged by [`scripts/build-extension.ps1`](../scripts/build-extension.ps1) into `extension/dist/firefox/` (gitignored) — it's the same `src/` and `icons/` with the Gecko manifest dropped in as `manifest.json`.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Status dot is red | The web UI isn't running, or the bridge URL/port in Settings is wrong. **Test connection** in Settings reports which. |
| "No readable posts found" | The adapter didn't match. Scroll the comments into view (some sites lazy-load) and re-capture. |
| Comments are missing on a news site | They're probably in a third-party frame — look for the **Include …** button under the capture summary. |
| Auto re-capture says "paused after 3 failures" | The bridge went away mid-run. Fix it, then tick the switch back on. |
| Auto re-capture never ticks | The status line says why: the tab drifted off the arena's page, the arena is closed, or the site permission was revoked. |
| "No reply box found" | Open the site's reply form *first* — the extension types into an existing composer, it never opens one. |
| Agent says there's no arena | It's assigned to a different CLI, or the arena is closed. Check the panel's arena line. |
| Draft never appears | The agent hasn't called `submit_draft` yet. The panel polls every 3s; check the CLI's output. |

## Reference

- [`docs/Guides/battleground.md`](../docs/Guides/battleground.md) — **the full step-by-step operator guide** (start here).
- [`docs/App/battleground.md`](../docs/App/battleground.md) — architecture, API, schema, security posture.
- [`skills/battleground/SKILL.md`](../skills/battleground/SKILL.md) — what the agent is told.
- [`prompts/Battleground/`](../prompts/Battleground/README.md) — paste-ready operator prompts.

## Enhancements / updates

The next improvements should preserve the core invariant: **the extension drafts, it never posts**. Approving may type text into a composer, but the final submit remains the operator's click.

### Highest priority

- **Real browser shakedown.** Load the unpacked Chrome extension and the staged Firefox build, then run the full loop: capture -> cast -> draft -> approve -> text lands in the composer without submitting. Also verify first-capture permissions, `sidebarAction.open()` on Firefox, auto re-capture, and the comment-frame **Include ...** path.
- **Local `/battleground` page.** Add a web UI page for arena history: arena list, pending draft counts, captured thread, cast, status, every draft, and verdict history. Keep page insertion in the extension, but make review and auditing possible without the original tab open.
- **Easier CLI handoff.** After **Open arena**, show a copyable prompt like `join battleground arena #12; call get_arena(arena_id=12), submit_draft, then wait_for_verdict`. If the local spawn helpers are available, add a **Launch selected CLI** action.
- **Capture preview.** Before opening an arena, show the exact posts the agent will see: authors, nesting, source adapter, post count, and a warning when capture fell back to `generic`.
- **Composer insertion hardening.** Detect whether the composer already has text and offer replace / append / prepend. Add a read-back confirmation after insertion and consider per-site composer adapters for X, Reddit, YouTube, LinkedIn, and Discourse.
- **Token setup UX.** When the bridge is running without `AGENT_CHAT_BATTLEGROUND_TOKEN`, show a gentle warning and a short setup recipe. Longer term: provide a token generator/helper and, if practical, restrict CORS to the installed extension id.

### Feature ideas

- **Competing drafts mode.** Let multiple agents or personas draft for the same arena, then let the operator pick, edit, or blend the best reply.
- **Targeted reply selection.** Let the operator choose which captured post the agent should answer, passing that id as `reply_to`.
- **Revision quick actions.** Add buttons such as **Shorter**, **Less sharp**, **More evidence**, **Concede this point**, and **Match thread tone** that send structured rejection notes.
- **Draft scoring.** Show lightweight checks before approval: disclosure present, factual support, tone fit, site-risk, length fit, and whether the reply overclaims.
- **Arena export.** Export a local-only Markdown or ZIP bundle containing the captured thread, stance, persona snapshot, drafts, verdicts, and posted text.
- **Notifications.** Badge or notify when a draft arrives, auto re-capture finds new posts, or the bridge goes down.
- **Adapter expansion.** Add stable-id adapters for more comment systems and networks, especially Mastodon, Lemmy, Guardian/Coral, OpenWeb, and large news-site comment stacks.

### Engineering cleanup

- **Split `panel.js`.** It currently owns settings, bridge calls, tab state, permissions, capture, insertion, arena lifecycle, polling, auto re-capture, and rendering. Break it into focused modules before the next large feature.
- **Add browser E2E coverage.** Unit tests cover the bridge well; the riskiest pieces are browser APIs: permissions, side panel/sidebar behavior, `chrome.scripting`, and composer insertion.
- **Add adapter fixtures.** Keep sanitized HTML fixtures for supported sites and run `capture.js` against them so selector drift is caught before manual testing.
- **Centralize schema/migrations.** The battleground tables are mirrored across the MCP server, web DB, and seeding code. Tests catch drift, but a shared schema module would remove a repeated footgun.
- **Add `/healthz`.** Expose bridge readiness for the panel: DB reachable, schema present, battleground routes available, read-only mode, and token requirement status.

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../docs/Guides/battleground.md">Operator guide</a></sub>
</p>
