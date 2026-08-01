<div align="center">

# ⚔️ AgentBattleground

**A Chrome extension that puts an Agent-Chat CLI agent into a debate that's already happening on the web.**

Capture the thread → cast a persona → the agent drafts a reply over MCP → you review it → it gets typed into the page's composer.

</div>

---

## What it does

Agent-Chat normally has two CLI agents argue with each other in a local SQLite database. AgentBattleground points that same machinery outward: you're reading a Reddit thread, an X reply chain, or a Hacker News argument, and you want Claude Code (in character as one of your personas) to write the reply.

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

**2. Load the extension:** open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and select this `extension/` folder.

**3. Optional — require a token.** If you'd rather the bridge not accept unauthenticated calls, set it before starting the web UI and paste the same value into the panel's Settings:

```powershell
$env:AGENT_CHAT_BATTLEGROUND_TOKEN = "some-long-random-string"
```

Chrome 116+ (side panel API). Chromium-based browsers with `chrome.sidePanel` work too; Firefox does not yet — see the Roadmap.

## Use it

1. Open a page with an argument on it. Click the **AgentBattleground** toolbar button — the side panel opens.
2. **Capture this thread.** Chrome will ask for access to that site the first time. The panel reports how many posts it found.
3. **Cast:** pick the CLI agent, a persona (or 🎲 random, or none), and write a one-line stance brief — *"Defend Go; go after the compile-time claim."*
4. **Open arena.**
5. In that CLI, say: **`join the battleground`**. The agent calls `get_arena`, reads the thread, and submits a draft.
6. The draft appears in the panel. **Approve & type into page**, or **Reject…** with a note (the agent reads it as a revision brief and tries again).
7. After you post it yourself, hit **I posted it** so the agent knows its reply is live.
8. New replies came in? **Re-capture page** merges them into the same arena — the agent sees only what's new.

## Site support

| Site | Adapter | Notes |
|---|---|---|
| Reddit | `reddit` | New (`shreddit-*`) and old layouts; comment ids and nesting depth preserved. |
| X / Twitter | `x` | The visible reply chain; status ids as post ids. |
| Hacker News | `hackernews` | Story + comment tree with indent depth. |
| Anything else | `generic` | Page headline + article lead, plus comment-ish blocks over 40 characters. |

A site adapter that finds nothing (layout changed, wrong page type) falls back to `generic` rather than opening an empty arena. Adapters live in [`src/capture.js`](src/capture.js) — each one only has to find posts and give each a **stable id**, which is what makes re-capture merge cleanly instead of duplicating.

## Files

```
extension/
├── manifest.json          # MV3; no static content scripts, per-domain opt-in
└── src/
    ├── background.js      # service worker — panel behavior + per-tab badge
    ├── capture.js         # injected on demand; site adapters; returns the thread
    └── panel/             # the operator surface: capture, cast, review, insert
        ├── panel.html
        ├── panel.css
        └── panel.js
```

There are no icons yet, so Chrome shows its default puzzle piece — drop a 128px PNG in and add an `"icons"` block to the manifest if you want branding.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Status dot is red | The web UI isn't running, or the bridge URL/port in Settings is wrong. **Test connection** in Settings reports which. |
| "No readable posts found" | The adapter didn't match. Scroll the comments into view (some sites lazy-load) and re-capture. |
| "No reply box found" | Open the site's reply form *first* — the extension types into an existing composer, it never opens one. |
| Agent says there's no arena | It's assigned to a different CLI, or the arena is closed. Check the panel's arena line. |
| Draft never appears | The agent hasn't called `submit_draft` yet. The panel polls every 3s; check the CLI's output. |

## Reference

- [`docs/Guides/battleground.md`](../docs/Guides/battleground.md) — **the full step-by-step operator guide** (start here).
- [`docs/App/battleground.md`](../docs/App/battleground.md) — architecture, API, schema, security posture.
- [`skills/battleground/SKILL.md`](../skills/battleground/SKILL.md) — what the agent is told.
- [`prompts/Battleground/`](../prompts/Battleground/README.md) — paste-ready operator prompts.
