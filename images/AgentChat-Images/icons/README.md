# Agent Battleground Icon Proposals

Square Agent Battleground icon proposals for favicons, app icons, and clickable buttons.

Open [`../preview.html`](../preview.html) to compare these icons alongside the landscape logo proposals.

## Favicon Round 3 — Agent Scenes (2026-08-13)

Where round 2 is one idea per mark, these are scenes: two or more agents talking,
arguing, or wired into the same bus. They carry far more meaning at app-icon size
and several of them go soft at 16px — that tradeoff is deliberate and is shown
honestly in the [Agent Scenes board](https://claude.ai/design/p/c1c596ae-e3cf-42a7-b4bc-9e6ed0ffc232?file=Agent+Scenes.dc.html),
which renders each at 148, 48, 32 and 16 pixels.

| # | Mark | Shows | Dark | Light |
|:--|:--|:--|:--|:--|
| 01 | **Face to Face** | Two agents nose to nose, mid-exchange. | [svg](./dark/favicon-agents-01-face-to-face-dark.svg) | [svg](./light/favicon-agents-01-face-to-face-light.svg) |
| 02 | **Clash** | The same two once it stops being a conversation. | [svg](./dark/favicon-agents-02-clash-dark.svg) | [svg](./light/favicon-agents-02-clash-light.svg) |
| 03 | **Round Table** | Three agents wired into one shared bus. | [svg](./dark/favicon-agents-03-round-table-dark.svg) | [svg](./light/favicon-agents-03-round-table-light.svg) |
| 04 | **Duel Terminals** | Two shells leaned in, sparking where they meet. | [svg](./dark/favicon-agents-04-duel-terminals-dark.svg) | [svg](./light/favicon-agents-04-duel-terminals-light.svg) |
| 05 | **Crossed Prompts** | Two arguments crossing mid-flight. | [svg](./dark/favicon-agents-05-crossed-prompts-dark.svg) | [svg](./light/favicon-agents-05-crossed-prompts-light.svg) |
| 06 | **Panel** ✅ | A host between two guests — the podcast format. | [svg](./dark/favicon-agents-06-panel-dark.svg) | [svg](./light/favicon-agents-06-panel-light.svg) |

✅ **Panel (dark) is what ships**, as the browser-tab icon *and* the mark in the
top-left corner of every page. The shipped copy lives as `_MARK_ART` in
`src/web/assets.py`; the dark SVG here is its source of truth — change both
together. It has since picked up a full-edge emerald ring the board above
doesn't show: the near-black plate was vanishing into dark browser chrome, so
the ring gives the mark its own silhouette. The light variant is untouched
(its plate is already emerald, so it never had the problem).

## Favicon Round 2 (2026-08-13)

Six candidates to replace the shipping favicon (the emerald plate with a black
"A", defined as `FAVICON_SVG` in `src/web/assets.py`). Each is drawn only from
circles, rounded rectangles and thick round-capped strokes so it survives being
rasterised into a 16 x 16 browser tab — the round-1 icons below are detailed
enough that they turn to mush at that size.

Every mark ships twice: `dark` is an emerald glyph on a near-black plate, `light`
is the inverse (black glyph on an emerald plate, matching what ships today).
Compare them side by side in the [Claude Design board](https://claude.ai/design/p/c1c596ae-e3cf-42a7-b4bc-9e6ed0ffc232?file=Favicon+Concepts.dc.html),
which renders each one at 32px and 16px over both light and dark browser chrome.

| # | Mark | Reads as | Dark | Light |
|:--|:--|:--|:--|:--|
| 01 | **Duet** | Two message blocks, one solid and one hollow. | [svg](./dark/favicon-2026-08-01-duet-dark.svg) | [svg](./light/favicon-2026-08-01-duet-light.svg) |
| 02 | **Turn** | A filled dot and a hollow dot — whose turn it is. | [svg](./dark/favicon-2026-08-02-turn-dark.svg) | [svg](./light/favicon-2026-08-02-turn-light.svg) |
| 03 | **Relay** | An open loop with the baton resting in the gap. | [svg](./dark/favicon-2026-08-03-relay-dark.svg) | [svg](./light/favicon-2026-08-03-relay-light.svg) |
| 04 | **Face-Off** | Two shell prompts pointed at each other. | [svg](./dark/favicon-2026-08-04-faceoff-dark.svg) | [svg](./light/favicon-2026-08-04-faceoff-light.svg) |
| 05 | **Split A** | Today's letterform cut into two voices on a shared crossbar. | [svg](./dark/favicon-2026-08-05-split-a-dark.svg) | [svg](./light/favicon-2026-08-05-split-a-light.svg) |
| 06 | **Arena** | Facing brackets holding a single live turn. | [svg](./dark/favicon-2026-08-06-arena-dark.svg) | [svg](./light/favicon-2026-08-06-arena-light.svg) |

None of these are wired up. Promoting a winner means replacing `FAVICON_SVG` in
`src/web/assets.py` — the single source for both the local server and the hosted
mirror — and redeploying to Fly.

## Round 1 — Dark Icons

- [Turn Relay](./dark/favicon-01-turn-relay.svg) - CLI agents passing turns around an MCP hub.
- [SQLite Arena](./dark/favicon-02-sqlite-arena.svg) - two agents writing through a shared SQLite-WAL message bus.
- [Signal Loop](./dark/favicon-03-signal-loop.svg) - live turn signals and chat bubbles in a loop.

## Round 1 — Light Icons

- [Turn Relay Light](./light/favicon-01-turn-relay-light.svg) - light version of the MCP turn relay concept.
- [SQLite Arena Light](./light/favicon-02-sqlite-arena-light.svg) - light version of the shared SQLite arena concept.
- [Signal Loop Light](./light/favicon-03-signal-loop-light.svg) - light version of the live signal loop concept.

## Notes

- All links are relative to this README, so they keep working if the entire `AgentChat-Images/` folder is moved.
- Icon assets use a `256 x 256` viewBox and are safe for square favicon export.
- SVG format keeps the marks crisp for browser favicons, toolbar buttons, app tiles, and README badges.

---

<p align="center">
  <sub>← <a href="../../README.md">Images</a> · <a href="../logos/README.md">Logos</a> · <a href="../../../README.md">Agent-Chat</a></sub>
</p>
