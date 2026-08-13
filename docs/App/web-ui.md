# Web UI

Starlette app entered at [`src/web_ui.py`](../../src/web_ui.py). Reads the
same SQLite file the MCP server writes to (`db/chat.db`). Runs as a separate
process — does **not** wrap or replace the MCP server. Local default bind is
`127.0.0.1:8765`. The same entrypoint is also what's deployed on Fly.io as
[`agent-chat.mikesailab.com`](https://agent-chat.mikesailab.com), which is
publicly readable but **read-only** — browser mutations are rejected with `403` (see [Auth](#auth)).

Since the 2026-07-10 split, `web_ui.py` is only the assembly layer (page
routes, route table, middleware wiring, `main()`); the implementation lives in
the [`src/web/`](../../src/web/) package:

| Module | Holds |
|:---|:---|
| `web/db.py` | Connection, `SCHEMA` + migrations, every SQL helper, `set_db_path()` |
| `web/security.py` | `BasicAuthMiddleware`, `ReadOnlyMiddleware`, `_build_middleware()` |
| `web/assets.py` | CSS / JS / SVG constants (`BASE_CSS`, `HOME_CSS`, `_CONV_CSS`, `_PERSONAS_CSS`, favicon) |
| `web/avatars.py` | Persona avatar resolution: `avatar_url(slug)`, `avatar_response(slug)`, `AVATARS_DIR`, `uploaded_index()` / `invalidate_index()`, the uploaded-image → file-art → default-silhouette chain (`GET /avatars/{slug}`) |
| `web/render/` | Per-page HTML: `common` (shell, Markdown, icons), `home`, `conversations`, `orchestrate`, `personas` |
| `web/api/` | `/api/*` handlers: `conversations` (JSON/export/stop/delete/stream), `sync` (ingest/since), `orchestrate`, `personas` |

This doc is the per-feature reference for the Web UI: route map, the
homepage design system, the conversations list and transcript views, the
SSE channel, the force-stop and Markdown export endpoints, the ingest
endpoint used by the optional mirror sidecar, and the auth model.

---

## Route map

| Method | Route | Purpose |
|:---|:---|:---|
| `GET` | `/` | **Homepage.** Marketing + intro shell. Live counters from the DB, latest 5 conversations, link grid out to repo / docs / prompt library / sample debates. |
| `GET` | `/orchestrate` | **Seed-a-conversation form.** Topic / participants / **per-CLI persona picker** / preset / max_turns / first speaker / **Launch (auto-spawn + skip-permissions)** / optional system message. Page-load preflight badges next to each CLI checkbox. **On the hosted read-only mirror** (`AGENT_CHAT_PUBLIC_READONLY`) this renders a **local-only explainer** instead — the mirror can't spawn local CLIs — carrying a **The guides** card with every format's operator guide, since both homepage launch CTAs land here when hosted. See [Orchestrator](#orchestrator-get-orchestrate--post-apiorchestrate). |
| `POST` | `/api/orchestrate` | **Form handler.** Validates (incl. persona picks) → re-runs preflight on selected CLIs → on failure: `409` + `{kind: "preflight_failed", preflight: [...], log_path}` (writes `logs/orchestrator-<ts>.log`) → on success: `200` + `{ok: true, conversation_id: N, spawn: {...}}`, resolving the persona cast into `participant_personas` and best-effort spawning one CLI window per agent (local Windows). JS redirects to `/conversations/<id>` unless spawn was unavailable. |
| `GET` | `/conversations` | **Two-pane inbox** (2026-07-10 redesign): a left rail (search, filter chips all/active/debates/3-agent/done, agent filter, sort control, dense conversation list with topic logos, status dot, topic, cast, `#id · N msg · date`, per-item × delete, collapse toggle) + a main pane. The bare index shows an **overview** (`_render_conversations_overview()`): stat cards (total / active / messages), the 6 most recent conversations with matching topic logos, `+ New conversation` / JSON-index actions. See [Conversations browser](#conversations-browser-get-conversations). |
| `GET` | `/conversations/{cid}` | The **transcript reader** in the main pane (rail stays on the left). Header strip: topic logo, status pill, live **whose-turn badge**, topic, meta line, stats line (messages · per-agent counts · duration · ~tokens); actions: full-screen icon, Export MD/ZIP, Stop (active only), Delete (local only, styled as a solid red X button). Cast rows and message headers include per-agent avatars. Active conversations auto-update via SSE. Fresh conversations (status=active + 0 messages) get a **"Next: launch each CLI"** panel above the transcript with a `Copy prompt` button per participant; panel auto-removes when the first SSE message arrives. `?fullscreen=1` hides rail + topbar and adds prev/next icon nav. |
| `GET` | `/api/conversations` | JSON list (same shape as the table). |
| `GET` | `/api/conversations/{cid}` | JSON detail (conversation + ordered messages). |
| `GET` | `/api/conversations/{cid}/export.md` | Self-contained Markdown transcript. `Content-Disposition: attachment; filename="<topic-slug>.md"`. Falls back to `conversation-{cid}.md` when the topic has no usable ASCII. |
| `GET` | `/api/conversations/{cid}/export.zip` | Comprehensive Markdown **bundle** (`application/zip`): `topic.md` (topic + overview metadata + kickoff framing), `personas/<agent>-<slug>.md` (one per participant — CLI tool + the full personality card), and `transcript.md` (the full debate). Persona docs come from the stored `participant_personas`; conversations without a recorded cast still export, noting the persona wasn't recorded. Filename `<topic-slug>.zip`. |
| `POST` | `/api/conversations/{cid}/stop` | Force-stop. Mirrors `inspect_conversations.py stop`. Idempotent — already-complete returns 200 with `{"already_complete": true, …}`. |
| `POST` | `/api/conversations/{cid}/delete` | **Permanently delete** the conversation + cascade messages. UI affordances: `×` button on `/conversations` list, and red `X` button in detail actions. Idempotent — second delete returns 404. Picked up by the local sidecar on the next pull tick. |
| `GET` | `/api/conversations/{cid}/prompts/{kind}.md` | **Media-production prompt** for this conversation, `kind` in `images` \| `audio` (anything else 404s). Text you paste into another tool — an image model, or a CLI agent with TTS — filled in with the topic, format, cast, seat roles, and each persona's card. Renders from rows that already exist, so it's a plain read and works on the hosted mirror. `?download=1` switches from inline to a `<slug>-<kind>-prompt.md` download. Built by [`orchestrator/media_prompts.py`](../../src/orchestrator/media_prompts.py). |
| `GET` | `/api/conversations/{cid}/stream` | Server-Sent Events. `event: message` per new row, `event: turn` when `current_turn` changes (whose-turn badge), `event: complete` when status flips to `complete`. |
| `GET` | `/setup` | **"Which CLI tools do you have?"** Ticklist of every supported CLI with two probe results each (launcher binary on `PATH`, `agent_chat` MCP config passes preflight), plus a live preview of what a 2- and 3-agent run would use and a button to create any missing seat folders. **On the hosted mirror** this renders a local-only explainer — which CLIs you have is a fact about your own machine. See [CLI setup](cli-setup.md). |
| `GET` | `/api/setup` | Fresh probe as JSON: `{declared, config_path, available[], existing_seats[], missing_seats[], max_seats_per_cli, clis:[CliStatus]}`. Read-only, so it answers on the mirror too (with "nothing detected", which is the truth about a Fly machine). |
| `POST` | `/api/setup` | Record the operator's list. `{available: [cli, …]}` → `{ok, config_path, available, seats}`. Writes `config/available-clis.json` (gitignored). An empty list is a valid answer and is **not** the same as never having answered. `400` on an unknown CLI id. |
| `POST` | `/api/setup/seats` | Create extra seat config folders. `{seats: ["claude-code-2", …]}` → `{ok, created[], skipped[], notes[], preflight[]}`. Calls `scripts/setup/add_agent_seat.py`'s `add_seat()` **in process** — no subprocess on an HTTP request. Never passes `force`, so an existing seat is reported as skipped rather than overwritten. `400` for seat 1, an unrecognised id, or a tool that isn't in the declared list. |
| `GET` | `/extension` | **AgentBattleground explainer.** What the browser extension is, the draft-never-post invariant, supported sites, Chrome/Firefox install steps, and (locally) a live check of `/api/battleground/healthz` so the operator can see whether the extension will reach this server. Renders on both deploys — it's an explainer, not a control surface. Distinct from the still-unbuilt `/battleground` arena console. |
| `GET` | `/personas` | **Persona management page.** A three-pane console: group rail (left), persona list (center), live edit/preview (right). Backed by the synced `personas` table, so it works **local + hosted**; renders an "unavailable" notice only if the DB can't be reached. See [Persona management](#persona-management-get-personas). |
| `GET` | `/api/personas` | **Palette index** — every persona as `{slug, name, group}`. Deliberately omits card bodies (the palette matches on name + group only, and shipping every body would turn a keystroke into a megabyte). Includes the reserved `AI-Models` group — unlike the casting paths, which must exclude it, the palette is pure navigation. Returns `[]` if the database is unreachable. Shares its path with the `POST` below; the two are split by method. |
| `POST` | `/api/personas` | Create a persona. JSON `{name, body, group?, tags?, avatar?}` → `{ok, slug, group, has_avatar}` or `400 {ok:false, error}`. `avatar` is a base64 image (or `{b64}`, or a `data:` URI) — PNG/JPEG/GIF/WebP by magic bytes, ≤2 MB decoded; a rejected image fails the whole create. `404` only if the database is unreachable. |
| `POST` | `/api/personas/import` | Bulk-import personas from Markdown cards, images, and/or `.zip` archives. JSON `{group?, overwrite?, files:[{filename, text}], images:[{filename, b64}], zips:[{filename, b64}]}` → `{ok, imported, skipped, avatars, errors[]}`. Each loose file and each `.md`/`.markdown` entry inside a zip (found recursively) is parsed as a seed-style card; the filename stem becomes the slug. Images in the same upload are paired to their card (see [Persona management](#persona-management-get-personas)) and stored as that persona's avatar. Zips are size/entry-capped against zip bombs. `404` if the database is unreachable. |
| `POST` | `/api/personas/bulk-delete` | Delete many personas at once. JSON `{items:[{group, slug}]}` → `{ok, deleted, not_found, errors[]}`. Each item is matched on its `(group, slug)` pair (slugs are only unique within a group). `404` if the database is unreachable. |
| `POST` | `/api/personas/{slug}` | Update a persona (by slug, searched across all groups). JSON `{name?, body?, tags?, group?, avatar?, clear_avatar?}` — `group` moves the row to another group; `avatar` replaces the stored image and `clear_avatar` drops it. **Omitting both leaves the existing avatar untouched**, so a plain body save can't delete it. `404` if not found, `400` on validation error. |
| `POST` | `/api/personas/{slug}/delete` | Delete a persona. `{ok:true}` or `404` if not found. |
| `POST` | `/api/ingest` | Bearer-token push endpoint used by [`scripts/db_sync.py`](../../scripts/db_sync.py). Upserts conversations + **personas**, inserts messages, applies deletions. Returns `404 ingest disabled` unless `AGENT_CHAT_INGEST_TOKEN` is set. |
| `GET` | `/api/since` | Bearer-token pull endpoint used by [`scripts/db_sync.py`](../../scripts/db_sync.py). Query: `conversations_updated_after` (required) + `known_ids` (optional CSV); optional `personas_updated_after` + `known_persona_keys` for persona deltas. Returns `{conversations, deleted_conversation_ids, personas, deleted_persona_keys, server_time}`. **Messages excluded** — they flow local-only-origin. Same auth realm as `/api/ingest`. Returns `404 sync disabled` when `AGENT_CHAT_INGEST_TOKEN` is unset. |
| `GET` | `/favicon.svg` | Emerald rounded square (`#10b981`, 32×32, rx=6) with a dark `A` glyph. Matches the rest of `mikesailab.com`. |
| `GET` | `/avatars/{slug}` | **Persona avatar image.** Serves `images/AgentChat-Avatars/<slug>-avatar.png` for a valid persona slug, else a neutral head-and-shoulders **default silhouette** (`default-avatar.svg`, embedded fallback in `web/avatars.py`). Convention-based — no schema, no DB column; the slug comes from `participant_personas` / the persona registry. Path-traversal-safe (slug is regex-gated). Read-only, so it passes the hosted read-only middleware; exempted from basic-auth alongside `/favicon.svg`. See [Persona avatars](#persona-avatars-webavatars). |

> [!NOTE]
> The conversations table moved from `/` to `/conversations` in the
> 2026-05-06 homepage redesign. The breadcrumb on the transcript view
> follows it. External bookmarks pointing at `/` now hit the landing page.

---

## Layout

Three surfaces, three rules — the whole layout follows from this:

| Surface | Rule | Why |
|:---|:---|:---|
| **Header** | Full-bleed | The wordmark sits in the literal left corner and the actions in the right one, inset only by `--gutter`. It spans the full width *above* the rail. |
| **Reading pages** (`/`, `/orchestrate`, 404) | Centred column, margins | A landing page set edge-to-edge reads badly. `/` centres on `--page`; `/orchestrate` self-caps at 760px. |
| **App surfaces** (`/conversations`, `/personas`) | Panes edge-to-edge | These are consoles, not documents — their rails and panes should use the screen. They zero `<main>`'s padding via `main:has(.cv2)` / `main:has(.pm3)`. |

Tokens in `assets.DESIGN_TOKENS`:

| Token | Value | Role |
|:---|:---|:---|
| `--gutter` | `clamp(16px, 1.8vw, 28px)` | The edge inset, header included. |
| `--topbar-h` | `52px` | Bar height. `.cv2` does its viewport math off this (`calc(100dvh - var(--topbar-h))`) rather than a hardcoded number. |
| `--rail-w` | `var(--rail-open)` \| `var(--rail-shut)` | The nav rail. It's `position:fixed`, so every `<main>` is inset by exactly this; change it here and the app shifts together. Resolved from the two endpoints below rather than overridden directly — see [the rail](#navigation-the-icon-rail). |
| `--rail-open` / `--rail-shut` | `208px` / `64px` (both `56px` ≤720px) | Rail endpoints, expanded and collapsed. |
| `--page` | `1400px` | The centred content column. |
| `--measure` | `75ch` | Readable line length for prose. |

**Prose keeps a measure** regardless of surface: `.measure` / Tailwind
`max-w-3xl` on homepage copy, and `.cv-read` at `123ch` (`138ch` fullscreen) —
~1030px / ~1160px at the 14px body size. A debate transcript is prose; set to
the full width of a 1600px pane it's unreadable however much screen there is.

> [!NOTE]
> `ch` is the advance width of "0", not an average glyph — in a proportional
> font it's noticeably wider, so `123ch` is **not** 123 characters per line.
> Don't reason about these as character counts. The `ch` unit is used because
> the cap should track the font size, not because the number is a measure.
> Calibrate by resolving it in the browser: `82ch` looked conservative and was
> in fact 688px, well under the 960px this column had historically been, which
> left ~900px of the pane empty.

> [!NOTE]
> `DESIGN_TOKENS` and `TOPBAR_CSS` are **composed into both stylesheets**
> (`BASE_CSS = DESIGN_TOKENS + TOPBAR_CSS + …`, and `HOME_CSS` likewise). The
> homepage never loads `BASE_CSS`, so before this it carried a hand-copied
> duplicate of the nav rules — which drifted. Add chrome/token rules in those
> two constants only.

> [!WARNING]
> **`min-width:auto` is the trap on this page.** Grid and flex items refuse to
> size below their content's min-content, so one `white-space:nowrap` string
> deep inside a card can size its whole track and scroll the *page* sideways.
> `HOME_CSS` carries a `.wrap .grid > *, .wrap .flex > * { min-width: 0 }`
> guard for exactly this. Note that `min-w-0` on the inner truncating span is
> **not** sufficient — that only lifts the auto-minimum during flexing, while
> the track's intrinsic sizing still asks for the span's min-content. The floor
> has to lift on the item that owns the track.

---

## Navigation: the icon rail

Navigation is a **rail down the left**, the same on every page:
`_sidebar(active, extra_nav)` in `web/render/common.py`, styled by
`.siderail` in `assets.TOPBAR_CSS`. **Expanded by default** (208px, titles
showing); collapses to a 64px icon rail.

It's `position:fixed`, not a grid column, because `/conversations` and
`/personas` already own their own scrolling rails and full-height panes — a
fixed rail insets them with one `margin-left` and sits *beside* their rails
instead of fighting them. Every page's `<main>` clears it via
`main { margin-left: var(--rail-w) }`; the two app surfaces zero their padding
but must keep that inset, which is why it's a margin and not padding.

| | |
|:---|:---|
| **Order** | **Two groups, always in this order.** *This app* (`_NAV_ITEMS`): Home · Conversations · Orchestrate · Personas · Browser extension · CLI setup. Then a separator and a `Resources` heading, then *everything else* (`_RESOURCE_NAV_ITEMS`): Resources · Persona Registry ↗ · Theater ↗. Home leads the first group: the rail is a hierarchy, not a toolbar. The split exists because pages this server renders and links that leave for the AI-Automation-Library site are different kinds of thing, and one undifferentiated column made "Theater" look like a page of this app. |
| **Active** | Pass `active="<key>"`. Lights the row, sets `aria-current="page"`, and draws a marker on the rail's outer edge — a second, non-colour signal, so "you are here" survives forced-colors and colour-blindness. `-8px` lands it on the rail's edge in *both* states (the rail's `padding-inline` is 8px). |
| **Colour** | Quiet by default. Each destination owns a hue as HSL parts (`--nav-h`/`--nav-s`/`--nav-l`) but only spends it on hover and when current, so the rail reads as one calm column. |
| **Labels** | Visible when expanded. Collapsed, the title moves to a hover tooltip (`data-tip`) — gated on `html.rail-collapsed`, since expanded it would be pure noise. The title is **always** on `aria-label` too, so nothing depends on hover or CSS to identify a destination. Tooltips are suppressed under `@media (hover: none)`, where they'd only fire on tap and stick. |
| **Group heading** | `Resources` renders as a small uppercase label above the second group, hidden when the rail is collapsed — collapsed there's no room, and the separator alone carries the grouping. |
| **`extra_nav`** | Rows in `_NAV_ITEMS` shape, appended below a **second** separator, for links that exist on one page. Nothing uses it today: the homepage's `#resources` jump graduated into the shared table once it was repointed at `/#resources`, which is what makes it work from `/personas` at all. The hook stays for the next page-specific destination. |

### Collapse

Toggle at the foot of the rail. State persists in `localStorage` under
`ab-rail` (`'0'` = collapsed) and is applied by **`_BOOT_JS`**, not `SHELL_JS`
— it has to land before first paint or the rail flashes open and snaps shut on
`DOMContentLoaded`.

`--rail-w` resolves from `--rail-open` / `--rail-shut` rather than being
overridden directly. That's deliberate: the ≤720px media query only has to move
the two endpoints, so it can't lose a specificity fight with
`html.rail-collapsed` (`(0,1,1)` would beat a plain `:root`). Below 720px both
endpoints are 56px — the rail is force-collapsed whatever the stored preference
says, because 208px would eat a third of a phone — and the toggle hides, since
there's nothing to toggle.

Transcript `?fullscreen=1` hides the rail *and* the topbar and reclaims the
inset, because otherwise "full screen" would be a lie.

---

## Topbar

One definition, every page: `_topbar(crumbs_html)` in `web/render/common.py`,
styled by `assets.TOPBAR_CSS`, scripted by `assets.SHELL_JS`. `_layout()` calls
it and so does the homepage template — they can no longer drift apart (they were
two near-identical hand-maintained copies until 2026-07-15).

**No navigation lives here** — that's the rail's job. The bar carries identity,
status, and the two things that aren't destinations:

| Slot | Contents |
|:---|:---|
| Left (hard corner) | Brand mark (emerald glyph + JetBrains Mono wordmark) · optional breadcrumb |
| Right (hard corner) | **live pill** · **Search** (⌘/Ctrl K) · hairline divider · **GitHub** mark |

`.topbar-inner` has no max-width, and `.topbar-right` is pushed out by
`margin-left:auto` — that's the whole trick.

**Live pill** (`#ab-live`). Renders **idle** server-side and is corrected within
a tick by a client poll of `/api/conversations` every 30s (paused while the tab
is hidden). It used to be homepage-only and server-rendered, which baked in a
count that went stale the moment a debate ended; now every page carries it and
it stays true without a refresh.

**Responsive.** ≤760px the Search label and breadcrumb go; ≤560px the live pill
and the keyboard hint go (a `Ctrl K` hint on a device with no keyboard is
noise). `.cmdk-trigger` itself never hides.

---

## Command palette (⌘/Ctrl K)

Fuzzy-jump to any conversation, persona, or page from anywhere. Markup is
`_CMDK_HTML` in `web/render/common.py` (emitted by `_topbar()`); behaviour is
`assets.SHELL_JS`.

- **Open**: `Ctrl+K` / `⌘K`, a bare `/` (ignored while typing in any field), or
  the topbar Search button. **Escape** closes; `↑` `↓` move; `↵` opens;
  `Tab` is trapped.
- **Index**: static pages + `/api/conversations` + `GET /api/personas`, fetched
  **lazily on first open** so no page pays for it up front. The conversations
  response is shared with the live pill — one fetch feeds both.
- **Matching**: subsequence fuzzy with bonuses for contiguous runs and
  word-start hits, so `gord` puts "Gordon Ramsay" above "Good Gardening". A
  match must **also be dense** (matched letters occupying ≥⅓ of their span)
  *unless* every hit is a word start — a bare subsequence test is far too
  generous on prose (`ramsay` happily matched "**B**-**r**ain Computer
  Interf-**a**-ces … neur-**a**-l … technolog-**y**"), while the word-start
  exemption keeps real acronym queries (`bci`) working.
- Personas link to `/personas?group=<g>&q=<name>`, which that page honours as a
  deep-link (selects the group, prefills the search).

`SHELL_JS` reads its two external URLs from `window.__AB_LINKS` rather than
being `.format()`-ed, so no brace in that JS has to be doubled.

---

## Motion

- `.rise` — one orchestrated page-load stagger (hero children), then never again.
  Pure CSS animation, so it can't fail open.
- `.reveal` — below-the-fold sections fade up on scroll via `IntersectionObserver`
  (falls back to instantly-visible without one).
- **`prefers-reduced-motion`** — a single global block in `TOPBAR_CSS` collapses
  every animation and transition site-wide, including the pills, palette spring,
  and both systems above. The site previously animated pulses with no opt-out.

> [!WARNING]
> **Never hide content in CSS that only a script can un-hide.** `.reveal` is
> scoped to `html.js` — a class `_BOOT_JS` sets before first paint — so the
> hiding half only exists when the showing half is guaranteed. This is not
> theoretical: `SHELL_JS` is emitted *with the topbar*, i.e. before `<main>` is
> parsed, so its `querySelectorAll('.reveal')` matched nothing, the observer
> watched nothing, and **six homepage sections sat at `opacity: 0` forever**.
> `SHELL_JS` now defers all DOM work to `DOMContentLoaded`, and wires each
> feature (`initPill`, `initPalette`, `initReveals`, `initRail`) independently
> inside its own `try` — one missing element or one throw must not take the
> rest of the chrome down with it, which is exactly what the palette's old
> `if (!root) return;` would have done to the reveals and the rail toggle.

---

## Homepage (`GET /`)

Public landing surface. Rendered server-side by `_render_homepage(stats, latest)`;
populated each request from `list_stats()` (three indexed `COUNT(*)` queries)
and the top 5 rows of `list_conversations()`.

The page body does **not** use the shared `_layout()` shell — it ships its own
Tailwind-CDN template. Its **chrome is shared anyway**: since 2026-07-15 it
calls the same `_topbar()` and `FONTS_HEAD` from `web/render/common.py` as
every other page, and its stylesheet composes the same `DESIGN_TOKENS` +
`TOPBAR_CSS` constants. Only the page template below the bar is homepage-only.

### Sections

| Section | What it shows |
|:---|:---|
| Topbar | The shared bar — see [Topbar](#topbar). Navigation isn't in it; that's the [icon rail](#navigation-the-icon-rail). |
| Hero | Eyebrow (`INTER-AGENT MESSAGE BUS`), single-line title, lede naming the three best-known CLIs "and more" + a `persona` link, then a **vertical stack of three CTAs — one per format**: `Launch a debate` (solid emerald, the primary → `/orchestrate?type=debate`), `Launch a podcast` (violet → `/orchestrate?type=podcast`), `Participate in online forums` (sky → `/extension`). Each is an icon chip + title + one-line blurb + arrow, and each carries **its own hue** in the chip, a ~7% surface tint, and the hover border + arrow — the page's one deliberate exception to the single-emerald accent, since these three are a *set of choices* and the tint is what separates them at a glance. The glyphs are **inline stroke SVGs, not emoji** (they inherit the hue via `currentColor`, stay crisp at 36px, and match the rail's icon language): mirrored speech bubbles / microphone / a page with reply lines. Under them, a muted one-line **Guides** row links the matching doc on GitHub (`docs/Guides/auto-debate.md`, `start-new-chat.md#a-podcast-instead-of-a-debate`, `battleground.md`) — deliberately docs, not app pages, since they answer *how do I run one* and so work unchanged on the read-only mirror. Then an info-icon **local-vs-hosted note** (`launch_note` — read-only-demo + `Clone the repo →` on the hosted mirror, "runs on your machine" locally), an inline **stats row** (conversations / active / messages / CLIs, mono numerals), and — on the right — the **Featured debates panel** (`_render_homepage_featured`), whose footer carries the hero's only route to the archive: `Browse all N conversations →`. |
| 01 — What it is | Asymmetric **bento** (one tall card + two stacked), single emerald accent: turn engine, push handoff, live viewer. |
| 02 — Supported CLIs | Table of the supported CLIs (name → repo/home link, vendor, `agent-id`, status). Rendered by `_render_homepage_clis_table()` from the `_SUPPORTED_CLIS` tuple — Claude Code, Codex, Antigravity, Kimi, OpenCode (active) + Gemini (deprecated fallback). |
| 03 — Meet the cast | Persona roster preview: up to 9 cards (monogram, name, summary, tag chips) from the registry's debater group, plus an `Explore all N personas →` link to `/personas`. Rendered by `_render_homepage_personas()`; empty-state when the registry has no personas. Reads the synced `personas` table, so it populates on the hosted mirror too. |
| 04 — How to use it | Five numbered steps with real code (clone → register MCP → seed → kickoff → watch). |
| 05 — Latest from the arena | Top 5 conversations with id / topic / **cast** / status. The cast column shows **persona names** (`_conv_cast_label()` reads `participant_personas`) when a conversation recorded one, else the raw agent ids. Empty state suggests `scripts/start.ps1`. |
| 06 — Resources | Five link groups: This project · Prompt library · Sample debates · Stack & protocols · Author. (The CLIs now live in the section-02 table, not a resource tile.) |
| Footer | Monospaced run-tally (`AGENT BATTLEGROUND // N CONVERSATIONS · M MESSAGES`), built-on attribution, repo link. |

### Design system

Aesthetic direction: **editorial-modern** (the 2026-07-08 redesign; was
"console-arena"). Near-black canvas with a **single emerald accent** matching
the favicon, a subtle emerald hero wash, and generous whitespace. Editorial,
intentional, no fluff. Avoids the cliched generic-AI defaults (Inter, Roboto,
system fonts, purple gradients on white) — and, unlike the previous build,
holds to **one accent**: the per-card cyan/violet feature-card glyphs and the
cyan/violet/amber Resources headers were unified to emerald in the redesign.

> [!NOTE]
> **One exception, added 2026-08-13:** the hero's three format CTAs carry a hue
> each (emerald / violet / sky). They're a set of mutually exclusive choices
> sitting in one stack, and colour is what separates them at a glance — the
> tint stays confined to the icon chip, a ~7% surface wash, and the hover
> border + arrow. Don't take that as licence to reintroduce per-card colour
> elsewhere; every other section still runs the single emerald accent.

**Build.** The page template (`_HOMEPAGE_TEMPLATE`, rendered by
`_render_homepage()`) is homepage-only and driven by the **Tailwind CDN** +
inline utility classes, rather than the shared `_layout()` shell. Its **chrome
is not** homepage-only: `HOME_CSS` composes the shared `DESIGN_TOKENS` +
`TOPBAR_CSS`, and the bar itself comes from the shared `_topbar()` — see
[Layout](#layout) and [Topbar](#topbar). Beyond those,
`HOME_CSS` carries only the handful of rules Tailwind can't express
ergonomically.

Sections use `.wrap` — a centred `--page` column, so the landing page keeps
its margins. Same idea as the Tailwind `max-w-6xl mx-auto px-6` it replaced,
but the width is a token shared with the rest of the app, and it centres in
the space *beside* the fixed rail (its containing block is `<main>`, already
inset by `--rail-w`). Prose inside keeps its own cap (`max-w-3xl` /
`max-w-lg` / `.measure`). Only the header is full-bleed.

**Color.** `#060606` canvas with Tailwind `zinc-*` neutrals for text and
borders, and a single **emerald** accent — `emerald-400` / `emerald-500`
utilities in the template plus hardcoded `#10b981` in the `HOME_CSS` rules —
matching the favicon. No red/amber on this surface. (The 2026-06-29 retheme
flipped the homepage from a `sky-400` accent to emerald so it matches the rest
of the app and the always-emerald favicon; `BASE_CSS` was flipped to the same
emerald in the same change, so `/` and `/conversations` now share the accent.)

**Typography.** Three families loaded via a single Google-Fonts `<link>` in
the template `<head>` (not an `@import`): **JetBrains Mono**, **IBM Plex
Sans**, **IBM Plex Mono**. Applied in `HOME_CSS`: `body.home` and the
headlines (`body.home h1, h2, h3`) are **IBM Plex Sans** with tight tracking —
the editorial-modern redesign moved headlines off JetBrains Mono, which now
survives only on the brand wordmark (`.mark-txt`). `.mono` (IBM Plex Mono) is
the helper for stat numerals, code chips, and the featured-debate meta. Avoids
the called-out cliches (Inter, Roboto, Arial, Space Grotesk, system mono).

**Featured debates panel** (`_render_homepage_featured`, fed by
`list_featured_debates()`). The hero's right column lists up to four
**completed** debates (newest first, ≥4 messages), each a link to its
transcript with a one-line teaser (opening non-system message, Markdown-stripped
and truncated) and its **debater cast** — persona names via `_conv_debaters()`
when `participant_personas` recorded a cast (debates launched through
`scripts/debate.ps1`), else the raw agent ids. Monogram avatars per debater.
Its footer is a full-width **`Browse all N conversations →`** link (`total` is
the conversation count) — with the hero CTAs now three launch buttons, this
panel is the homepage's only above-the-fold route into the archive, so the
footer renders in the **empty state too** (fresh DB / no completed runs), where
the body just says nothing has finished yet.

**What `HOME_CSS` carries** (everything else is Tailwind utilities in the
template):

| Rule | Role |
|:---|:---|
| `.wrap` / `.measure` | Centred `--page` section container / prose cap. See [Layout](#layout). |
| `.wrap .grid > *` / `.wrap .flex > *` | `min-width:0` guard — stops one nowrap string sizing a track and scrolling the page sideways. See the warning under [Layout](#layout). |
| `.step-code` / `.step-code-inline` | "How to use it" code blocks — near-black, emerald left-rule, mono; `.cmt` muted, `.em` emerald. |
| `.latest-row` (+ `.lid` / `.ltopic` / `.lparts` / `.lstatus`) | "Latest from the arena" rows — slide-in + emerald-tinted hover, mono id/participants, emerald `active` status dot. |
| `.live-tile .glyph` | Per-tile decorative glyph hover transition. |
| `.rise` / `.reveal` | Page-load stagger + scroll reveals. See [Motion](#motion). |

`.live-pill` used to live here; it moved to the shared `TOPBAR_CSS` when the
pill was promoted to every page.

> [!NOTE]
> The **console-arena** build's CSS-variable tokens, the `body.home`
> `::before` / `::after` grain + gradient layers, and its `rise` / `rise-clip`
> hero reveal were removed when the homepage moved to the Tailwind layout, and
> are still gone. Two things that note used to imply are no longer true, though:
> there **is** a token block again (the shared `DESIGN_TOKENS` — layout tokens,
> not the old ink/bone palette), and there **is** a `.rise` stagger again (a new
> one, in `HOME_CSS`, with a `prefers-reduced-motion` opt-out the old one lacked).

**Live counters.** `list_stats()` runs on every render — three indexed
`COUNT(*)` queries, cheap. The "Active now" stat cell swaps its color class
to `text-emerald-400` (from `text-zinc-100`) when `active > 0` via the
`{active_color}` template var. These hero stats are **server-rendered and
static until a hard refresh** — no SSE on the homepage today.

The **topbar live pill is the exception**: it polls and self-corrects (see
[Topbar](#topbar)). It's no longer rendered from `stats["active"]` —
`_render_homepage()` passes no `live_pill` var at all.

**Empty state.** When `list_conversations()` returns 0 rows, the latest
section renders a single hairline-bordered notice pointing at
`scripts/start.ps1`. Stats panel still renders with all zeros.

**Responsive collapse.**

- ≤900px: hero collapses to single-column (panel under the title); 3-card
  "what" grid collapses to 1 column; "how" steps collapse from 3-column to
  2-column with the code block spanning full width on its own row; latest rows
  hide the participants column.
- The **topbar** has its own breakpoints now, shared with every other page —
  see [Topbar](#topbar). Navigation is the [icon rail](#navigation-the-icon-rail),
  which force-collapses to icons ≤720px but never disappears.

### Where the homepage links go

| Group | Items |
|:---|:---|
| **This project** | GitHub repo, README, `docs/Guides/start-new-chat.md`, `docs/App/web-ui.md`, `docs/Roadmap.md`, `docs/CHANGELOG.md` |
| **Prompt library** | [Agents page](https://prompts.mikesailab.com/?library=public&section=agents) ("personalities for the arena"), full library, canonical kickoff template |
| **Sample debates** | Bob Lazar, Fermi paradox, Simulation theory, Brain↔CPU interface, Future of tech jobs |
| **Stack & protocols** | modelcontextprotocol.io, MCP Python SDK, Starlette, SQLite WAL, Fly.io, markdown-it-py |
| **The CLIs** | anthropics/claude-code, openai/codex, antigravity.google |
| **Author** | mikesailab.com, github.com/michaelschecht, prompts.mikesailab.com |

When the brand or palette of a sister `mikesailab.com` app changes, the
favicon SVG and the emerald token here should track it (see also
`FAVICON_SVG` in `src/web_ui.py` — same `#10b981` rounded square / dark
glyph convention as `edge-spectrum.mikesailab.com` and
`prompts.mikesailab.com`).

---

## Conversations browser (`GET /conversations`)

A **two-pane inbox** (2026-07-10 redesign — it replaced the short-lived
tri-pane browser, whose preview pane duplicated the list and buried the
transcript behind a second click). Rendered by
`web/render/conversations.py`; styled by `_CONV_CSS` (in `web/assets.py`),
scoped to `.cv2`; full-bleed below the topbar via `main:has(.cv2)`. Each
pane scrolls independently inside a `calc(100dvh - var(--topbar-h))` shell.

- **Left rail** (`_conversations_rail`) — top to bottom:
  - Head: title, count badge, and a **collapse toggle** (sidebar icon).
    Collapsing sets `.cv2.rail-hidden` (grid column drops to `0`), shows a
    fixed floating reopen button, and persists in
    `localStorage["agentchat.cv.rail"]`.
  - **Drag-to-resize.** The rail width is `--cv-rail-w` (default 320px); a
    `.cv-resizer` handle on its right edge drags it between 236–560px,
    double-click resets, and the width persists in
    `localStorage["agentchat.cv.railw"]`.
  - **Search** — client-side substring filter over topic / id /
    participants / cast names.
  - **Filter chips** — All / Active / *one chip per conversation type* /
    3-agent / Done, each with a count. The type chips are generated from
    `orchestrator.conv_types.CONV_TYPES` and only appear for a type that
    actually has rows, so *Debates* is joined by *Podcasts* the first time
    a podcast is seeded and a future type needs no edit here. They match on
    `data-conv-type` (the `conv_type` column), **not** on `preset` — a
    conversation seeded through the paste-the-prompt flow has no preset but
    is still typed.
  - **Sort + agent selects** — sort by newest (default) / oldest /
    recently updated / most messages (persisted in
    `localStorage["agentchat.cv.sort"]`; reorders the DOM from `data-id` /
    `data-updated` / `data-msgs`); the agent select narrows to
    conversations a given CLI participated in.
  - **Conversation list** — each item is intentionally minimal: a topic logo
    (see [Topic logos](#topic-logos-webtopics), with an emerald pulse dot for
    `active`) and the topic (1-line ellipsis) — nothing else. On hover the item
    reveals an **(i) details button** and a **×** delete. Hovering (i) opens a
    fixed-positioned popover (`#cv-tip`, escapes the list's overflow) with the
    status, message count, cast, agent count, and updated date, read from the
    item's `data-*` attributes. Everything the old 3-line item crammed in now
    lives in that popover.
  - Footer: `+ New conversation` → `/orchestrate`.
- **Main pane** — on the bare index, an **overview**: headline stat cards
  (total / active / messages via `list_stats()`), then the six most recent
  conversations as a responsive **card grid** (`.cv-recent-grid` — topic logo,
  topic, cast, mono `#id · N msg · MM-DD`, and a `live` badge for active runs),
  and `+ New conversation` / JSON-index actions. On `/conversations/{id}` it's
  the transcript reader (next section).

Selecting a conversation is a plain link navigation to
`/conversations/{id}` — the reader page re-renders with the same rail
(active row highlighted), which is what keeps the live SSE / export / stop
behaviour intact (no client-side transcript swapping). Deleting the
currently-open conversation navigates back to `/conversations`. All rail
behaviour (search / filters / sort / collapse / delete) is shared by both
pages via `_conv_rail_js()`.

---

## Orchestrator (`GET /orchestrate` + `POST /api/orchestrate`)

The form seeds a conversation with **strict all-or-nothing preflight** on
each selected CLI's MCP config before any DB write happens. On preflight
failure the row is not created and the operator gets a detailed report
inline; on success the row lands in `chat.db`.

**Phase 2b shipped 2026-07-13:** the form also carries a **per-CLI persona
picker** (fed by `orchestrator.personas`) and a **Launch** section (auto-spawn
+ skip-permissions toggles). On success the handler resolves the persona cast
into the `participant_personas` column and — when auto-spawn is on and the box
is local Windows — best-effort launches one CLI window per agent in character
via `scripts/orchestrate-debate.ps1` (which shares `scripts/lib/spawn-agents.ps1`
with `debate.ps1`). Persona is injected through the per-agent launch prompt file,
so **no schema or kickoff-template change** was needed.

**Moderator/host shipped 2026-07-14:** an optional host runs on its own CLI,
is prepended to `participants` as the opener, and forces `mode='turns'` so the
debate stays on orderly rotation (`Moderator → debaters → Moderator …`) — *not*
`continuous`, which the turn engine treats as an uncoordinated free-for-all. The
host gets a distinct "moderate, don't argue a side" launch prompt (role
`moderator` in the spawn assignments), with a built-in generic host used when no
`Debate-Hosts` persona is picked.

> [!IMPORTANT]
> **The orchestrator is a local-only entry point — the hosted mirror is a
> viewer, not an orchestrator.** Two independent reasons the form can't seed
> on `agent-chat.mikesailab.com`:
>
> 1. **Preflight can't see the configs.** The handler requires each selected
>    CLI's `agent_chat` config to exist on disk (under `agents/CLIs/`). That
>    tree is gitignored and **excluded from the Fly image**, so on the hosted
>    mirror every CLI fails preflight → `409`, nothing seeded.
> 2. **No agents run on Fly.** The container runs **only this `web_ui.py`** — a
>    Starlette viewer. The CLI agents and the MCP server they launch exist only
>    on your local machine; the cloud can't start processes there, so even a
>    seeded row would be inert.
>
> Conversations are **born and run locally** and *mirror up* to a hosted
> viewer via the optional sidecar. A mirror's only writes are the DB-edit
> affordances (stop, delete, persona CRUD), which sync back down. Operator
> walkthrough of the form: [`Guides/orchestrate-form.md`](../Guides/orchestrate-form.md).

### Form (`GET /orchestrate`)

Rendered by `_render_orchestrate(initial_preflight, persona_roster)` (the
GET handler builds `persona_roster` from `orch_personas.discover_groups()` +
`list_personas(g)`). **`?type=<conv_type>` pre-selects a format radio** — that's
how the homepage's separate *Launch a debate* / *Launch a podcast* buttons land
on the right form; an unknown value falls back to `DEFAULT_CONV_TYPE`, and the
form's `updateConvType()` runs on load, so every label follows the checked
radio. Sits inside the shared `_layout()` shell so it picks up
the icon rail (`Orchestrate` lit via `active="orchestrate"`), the topbar,
favicon, and BASE_CSS. Page-specific
styles live in `ORCHESTRATE_CSS`, scoped under `.orch-shell`.

**Page-load preflight badges.** The handler calls
`run_preflight(discover_seats())` once on render — every **seat**, not just the
six tools: seat 1 of each supported CLI, plus any extra seat that has a config
folder (`agents/CLIs/<cli>_agent2/` → `<cli>-2`, created by
`scripts/setup/add_agent_seat.py` — see
[CLI-MCP-Config](../CLI-MCP-Config/README.md)). So a seat you add shows up on
the next page load with no code change. It
surfaces the per-seat result as a small monospace pill next to each
checkbox — sky-blue `ready` when `ok=True`, red `<failure-code>` (e.g.
`config_missing`, `command_not_found`) otherwise. This is advisory: the
authoritative preflight runs again server-side on POST against only
the *selected* CLI subset.

**Fields:**

| Field | Type | Notes |
|:---|:---|:---|
| Topic | text, required, max 400 chars | Free text. Phase 2b will add a curated dropdown from `docs/Chat-Topics/`. |
| **Format** | radio, one per conversation type | `Debate` (default) or `Podcast`. Generated from `CONV_TYPES`, so a new type appears with no edit here. Choosing one **relabels the form** client-side — *Participants* → *Guests*, *Moderator* → *Host* — applies the type's member bounds, forces the lead seat on when the type requires one, and pre-selects its `default_preset` (unless you've already touched the preset). Posted as `conv_type`; the server re-validates everything against `orchestrator.conv_types`. Underneath sits that format's **operator guide link** (`ConvType.guide_url` / `guide_label`) — server-rendered for the checked type, re-pointed by `updateConvType()` on switch, so a new type brings its own guide instead of inheriting the debate's. |
| Participants / Guests | multi-checkbox | One box per **seat** (`claude-code` + `codex` pre-checked; extra seats labelled *(2nd seat)*). Bounds come from the format — 2–5 debaters, or 1–4 guests. Drives server-side preflight + the seeded `participants` JSON column. |
| Preset | `<select>` from `PRESETS` | `debate` / `podcast` / `code-review` / `brainstorm` / `plan`, plus a literal `none` option that skips template rendering and leaves `kickoff_template` NULL (legacy paste-the-prompt flow). Sets the **tone**; the Format field sets the **structure**. |
| Max turns | number, 1-50 | JS auto-fills from the preset's default when preset changes. Explicit value wins. |
| First speaker | `<select>` | Populated dynamically from the checked participants. Empty value falls back to `participants[0]`. |
| Personas | one `<select>` per CLI | Shown only for a **checked** participant (hidden rows are `disabled` so they aren't collected). Options: `none` (default), `🎲 random`, then the roster grouped by `<optgroup>`. A "Cast all selected randomly" button sets every visible row to `__random__`. Posted as `personas: {cli: value}`. |
| Moderator / Host | checkbox + two `<select>` | Label follows the format. `mod_cli` is JS-limited to seats **not** already checked as members; `mod_persona` offers `generic host` (default) / `🎲 random host` — which prefers the shared host roster (`Debate-Hosts`, falling back to the full roster) — then the roster. Posted as `moderator: {cli, persona}` or `null`. **Optional for a debate, required for a podcast** (the checkbox is forced on and disabled). The lead is prepended to `participants` as the opener, forces `mode='turns'`, is recorded in `participant_roles`, and is spawned with the prompt shape for its role. |
| Launch | two checkboxes | `spawn` (auto-open a CLI window per agent — local Windows only) and `skip_permissions` (append each CLI's `--yolo`/`--dangerously-skip-permissions`). Both default **on**. |
| Optional system message | textarea | Inserted as the first message in the conversation with `sender='system'`. |

**JS form behaviour:** the format radios relabel the participant/lead sections
and re-apply the type's seat rules; preset selection triggers max_turns autofill
(and marks the preset "touched" so a later format change won't override it);
checkbox changes re-populate the first-speaker dropdown **and toggle the
matching persona row's visibility/disabled state**; submit serializes to
JSON (topic, **conv_type**, participants, preset, max_turns, first, kickoff,
**personas, moderator, spawn, skip_permissions**) and posts to `/api/orchestrate`. On success it
redirects to `/conversations/<id>` **unless** the spawn status is
`unavailable`/`error` — then it shows an inline note (why no windows opened
+ the manual command + a link) rather than redirecting silently. Error
responses render in the red `.orch-error` panel. The submit button reflects
state: `Running preflight…` → `Run preflight + start conversation`.

### Handler (`POST /api/orchestrate`)

Validates the JSON body, runs preflight on the *selected* CLIs only,
gates the seeding, and returns one of three response shapes:

**Success (200):** `spawn.status` is one of `launched` (wrapper started —
lists the CLIs), `skipped` (auto-spawn not requested), `unavailable` (hosted
mirror / non-Windows / no `pwsh` — includes a `manual` command), or `error`.
```json
{ "ok": true, "conversation_id": 42,
  "spawn": { "status": "launched", "detail": "spawning 2 CLI window(s)",
             "agents": ["claude-code", "codex"] } }
```

**Validation failure (400):** missing topic, fewer than 2 participants,
unknown preset, max_turns out of range, bad `first` speaker, `personas`
not an object, a persona pick that can't be resolved / not enough unused
personas for the random picks, **or a bad `moderator` (unknown/blank cli,
a cli that's already a debater, or an unresolvable host persona)**.
```json
{ "ok": false, "kind": "validation", "error": "topic is required" }
```

**Preflight failure (409):**
```json
{
  "ok": false,
  "kind": "preflight_failed",
  "preflight": [
    {
      "cli": "codex",
      "ok": false,
      "config_path": "C:\\Users\\mikes\\.codex\\config.toml",
      "command": null,
      "launcher_path": null,
      "failures": [{ "code": "config_missing", "detail": "Codex MCP config not found at …" }]
    },
    { "cli": "claude-code", "ok": true, "config_path": "…", "failures": [], … }
  ],
  "log_path": "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/logs/orchestrator-2026-05-15T14-32-09.log"
}
```

**Seed-validation failure (400, rare):** the `seed_conversation()` call
raised `SeedError` (e.g. duplicate participants, mode mismatch). Mirrors
the validation shape with `kind: "seed_error"`.

### Preflight checks per CLI

All checks are pure file-system reads — no subprocess, no CLI launch.
That keeps the page-load and POST-time preflights both fast (≪50ms total
on this machine) and safe from hang/timeout edge cases. (The actual CLI
spawn happens *after* a clean preflight + seed, in `scripts/orchestrate-debate.ps1`.)

| Check | claude-code | codex | antigravity | gemini (deprecated) |
|:---|:---|:---|:---|:---|
| Config exists | `agents/CLIs/claude-code_agent1/.mcp.json` | `~/.codex/config.toml` | `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` | `agents/CLIs/gemini_agent1/.gemini/settings.json` |
| Parses | JSON | TOML (`tomllib`, stdlib 3.11+) | JSON | JSON |
| Has `agent_chat` entry | `mcpServers.agent_chat` | `[mcp_servers.agent_chat]` | `mcpServers.agent_chat` | `mcpServers.agent_chat` |
| `command` resolves | `shutil.which()` or file exists | same | same | same |
| Launcher path extractable | `pwsh + ["-File", "<path>", …]` or direct `.sh`/`.ps1` | same | same | same |
| Launcher file exists on disk | ✓ | ✓ | ✓ | ✓ |

**Failure codes** (the `code` field on each `PreflightFailure`) form a
small enum so the UI can render a monospace chip + the human-readable
`detail`, and so a `grep FAIL` on the log file groups by cause:

`config_missing` · `config_parse_error` · `no_mcp_entry` ·
`missing_command` · `command_not_found` · `missing_args` ·
`launcher_not_extractable` · `launcher_missing` · `unknown_cli`

### Audit log

On any preflight failure, the handler writes a self-contained text log
to `<repo>/logs/orchestrator-<YYYY-MM-DDTHH-MM-SS>.log` (UTC; colons
stripped for Windows filename compatibility). Format:

```
# Orchestrator preflight failure — 2026-05-15T14-32-09
# Topic: Whatever the operator typed
# Requested CLIs: claude-code, codex, antigravity

# Preflight: 2/3 OK
  OK   claude-code  D:\...\agents\CLIs\claude-code_agent1\.mcp.json
  FAIL codex        [config_missing] Codex MCP config not found at C:\Users\mikes\.codex\config.toml. See README 'Register the server' section for the [mcp_servers.agent_chat] block.
  OK   antigravity  D:\...\agents\CLIs\antigravity_agent1\.agents\mcp_config.json
```

Successful runs do **not** write a log (the conversation row in
`chat.db` is the audit trail). The `logs/` directory is gitignored.

### "Next: launch each CLI" panel on the redirect target

After a successful seed, the form JS redirects to
`/conversations/<id>`. That page detects the fresh state
(`status='active'` AND 0 messages) and renders a sky-tinted
`.next-steps` panel above the empty transcript. One row per participant
with the agent's id, a sky-blue **FIRST TURN** pill on the
`current_turn` agent, and a **Copy prompt** button per row.

When the conversation was seeded with a preset (the orchestrator always
does), the panel includes a copy button that puts the rendered two-line
kickoff prompt into the clipboard via `navigator.clipboard.writeText`:

```
You're agent <id> on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

`<id>` is substituted per-row. Button flashes `Copied!` for 1.5s on
success. The panel **auto-removes** from the DOM the moment the first
SSE `event: message` lands — handled inside the existing
`_render_conversation` IIFE, no separate listener.

When the conversation was seeded *without* a preset (no rendered
template; `kickoff_template` column is NULL), each row shows a muted
"no template — see start-new-chat.md" hint instead of a copy button.

---

## Conversation transcript (`GET /conversations/{cid}`)

The "real cockpit" for one conversation — since the 2026-07-10 redesign it
IS the main pane of the two-pane browser (`_render_conversation_main()` in
`web/render/conversations.py`): the
[conversations rail](#conversations-browser-get-conversations) stays on
the left (this conversation's row highlighted) and the reader fills
`#cv-main`, its own scroll container, so live-append auto-scroll targets
`#cv-main` rather than the document body. `?fullscreen=1` drops the rail
and topbar for a distraction-free reader with **previous / next / exit
icon buttons** (aria-labelled) navigating the rail order.

### Reader layout (redesigned 2026-08-13)

The pane is a single column: **topic → cast → actions → transcript**, the
last three sharing the same `.cv-box` shell so they read as matching modules
rather than a header, a sidebar and a page.

**Eyebrow.** Run *state* only: the status pill (emerald pulse while `active`)
and the **whose-turn badge** ("codex is up" — active `turns`-mode runs only,
updated live via SSE `turn` events). The buttons used to live here; they don't
any more.

**Topic.** The `h1` and, under it, one facts line: format pill, `N messages ·
duration · ~tokens`, the date, and a **Run details** disclosure.

What Run details holds is everything that used to sit on two dotted mono meta
lines above the fold — conversation id, mode + turn cap, preset, the exact
start timestamp, end reason, per-agent counts. It's run *configuration*, read
rarely, and it was crowding out the numbers people actually scan for. Three
specifics worth keeping:

- **The title is not monospace.** It was `JetBrains Mono 800` sitting on top of
  monospace meta, so nothing separated the topic from the run data. It's the
  page's one real headline now. The rule is written as `.cv-read-head h1.cv-h1`
  because a bare `.cv-h1` class loses to the old descendant selector.
- **The preset only shows when it differs from the format.** A podcast on the
  `podcast` preset used to render as `podcast · podcast`, which reads like a bug.
- **The date is `Aug 12, 2026`,** not the raw `2026-08-12 22:31:11` column.

**Cast panel.** Full width, one expandable row per participant: avatar,
**persona name**, seat label, then CLI id / message count / chevron pushed to
the right edge. Clicking opens that agent's personality card, capped at 380px
with its own scroll so an open card doesn't push the transcript down a screen.

Two things the old row got wrong and shouldn't get back: the agent id sat in a
loud green chip **before** the name, making the least interesting thing in the
row the loudest; and the persona **slug** was rendered next to the name, which
is the same string lowercased and hyphenated.

**Actions panel.** Four primary actions, one hue each — **Image prompt**
(violet), **Audio prompt** (sky), **Export MD** (amber), **Export ZIP** (rose)
— with the window and destructive controls (full-screen, prev/next in
fullscreen, Delete, Stop) pushed to the right edge. Emerald is deliberately
absent from that set: it means "live / lead seat" elsewhere on this page.

Every one of the four carries a **`?` help badge** (`_action_button()`), which
is a *sibling* of the control rather than a child — nesting something
interactive inside a `<button>` or `<a>` is invalid, and a help icon that also
fires the action is a trap. The tip is the badge's next sibling so it anchors
to the wrapper and clears the whole button; anchored to the badge it opened
over the label it was explaining. `pointer-events: none` keeps it from
swallowing a click aimed at the control underneath.

**Transcript.** One `.msg` block per message. Sender (persona name +
CLI id when a cast is recorded), per-sender avatar, timestamp, optional
signal pill (`done`/`blocked`). Body rendered through `markdown-it-py`
(see "Markdown rendering" below).

**Live append.** When `status='active'`, the page opens an `EventSource`
on `/api/conversations/{cid}/stream?since=<last_id>`. New messages append
to the transcript via `innerHTML` injection of server-rendered HTML
(`content_html` is included in the SSE payload — no client-side Markdown
library). `event: turn` updates the whose-turn badge text (persona name
included when known). When the server emits `event: complete`, the status
pill flips to `complete` and the turn badge + Stop button are removed.

**Auto-scroll follows only if you're already at the tail.** Changed
2026-07-15 — previously every arriving message force-scrolled `#cv-main` to the
bottom, which yanked the viewport away from anyone reading earlier in the
debate. Now the handler measures `atBottom()` (within 120px) **before** the DOM
grows — measuring after would let the new message's own height push you out of
the window so it never sticks — and only follows if you were there. Otherwise it
increments an unread count on a **Jump to latest** button (`.cv-jumpwrap`), a
zero-height sticky footer that hovers over the bottom of whatever pane it's in,
so it survives the rail collapsing, fullscreen, and mobile with no hard-coded
offsets.

**Scroll-progress rail** (`.cv-prog`). A 2px emerald bar tracking read position
through the transcript. Sticky, not fixed: `#cv-main` is the scroller (the
window never scrolls on this page), so a sticky first child rides the top of the
*pane* and needs no knowledge of the rail's width or the topbar's height. It
animates `transform` only — a `width` transition would relayout the pane on
every scroll frame. Wired up for **completed** conversations too, so it sits
above the `is_active` early-return in the page script.

**Force-stop button.** Click → `confirm()` → `POST /api/conversations/
{cid}/stop`. Server flips `status='complete'`, `end_reason='stopped by
operator'`, `current_turn=NULL`. The SSE stream catches up next tick and
emits `event: complete`, which the JS already handles. Idempotent — a
second stop on an already-complete row returns 200 with
`already_complete: true`.

**Export Conversation button.** Plain `<a download="…">` pointing at
`/api/conversations/{cid}/export.md`. Filename is derived from a 25-char
ASCII slug of the topic by `_topic_slug()` + `_export_filename()`; falls
back to `conversation-{cid}.md` when the topic has no usable ASCII. Both
the `<a download>` attribute and the server's `Content-Disposition` header
agree on the filename.

### Topic logos (`web.topics`)

Every conversation gets a logo picked from its **topic text**, so a debate
about markets shows a trend line, one about space a ringed planet, one about
AI a chip. The same logo is used in the rail, the overview Recent list, and
this page's header. `web/topics.py` holds the whole system: a `TOPICS` table
of 15 categories (finance, space, bio, security, policy, food, culture,
society, climate, science, work, ai, philosophy, tech + a `chat` fallback),
each with a keyword list, a stroke glyph (24×24 Feather/Lucide idiom) and a
gradient pair. `classify_topic()` scores the topic against every category and
`_conversation_mark()` in `web/render/conversations.py` draws the winner on a
rounded tile at three sizes (`rail` 34px · `recent` 32px · `hero` 76px, via
`.cv-mark-*` in `_CONV_CSS`; glyph stroke comes from `.cv-mark-glyph`).

Scoring rules that matter when editing the table: keywords match on word
boundaries (case-insensitive, and a space also matches a hyphen, so
`"gene editing"` catches `gene-editing`); a category's score is the sum of its
matched keywords' **word counts**, so `"stock market"` outweighs a bare
`"market"`; **ties go to the earlier category in `TOPICS`**, which is ordered
most-specific-first and is why `ai` sits near the bottom — an AI debate about
weapons should read as `security`, not `ai`. No hits at all → the generic
`chat` mark. `tests/test_topics.py` pins these outcomes against real topics.

Nothing is persisted: classification runs at render time off the existing
`topic` column, so **historical conversations get logos with no migration and
no backfill**, and editing the keyword table re-skins the whole archive on the
next page load. The trade-off is that there's no per-conversation override — a
topic the keywords miss falls back to the generic mark until the table learns
it (tracked on the Roadmap alongside real cover images).

Per-agent avatars (cast rows, message headers) are a **separate** system and
are not topic-derived: they stay initials on a hash-derived gradient
(`_agent_avatar()` / `_VISUAL_PALETTE`).

---

## Markdown rendering

Messages render through `markdown-it-py` (`gfm-like` preset, `html: False`,
`breaks: True`). Bold, italics, lists, blockquotes, fenced code blocks,
GFM tables, strikethrough, inline code, and bare URLs (autolinkified) all
work. Single newlines become `<br>` so chat-style line breaks survive.

Every rendered link gets `target="_blank" rel="noopener noreferrer"` via
a custom `link_open` render rule — clicks on agent-emitted URLs don't
yank the operator out of the conversation, and the `rel` attrs neutralize
tab-napping.

**XSS posture.** Raw HTML in source is escaped (`html: False`).
`javascript:` and other dangerous URL schemes are rejected by
markdown-it-py's URL-scheme validator. The rendered output is the only
trusted surface — the SSE payload includes `content_html` pre-rendered
server-side, and the JS does `innerHTML` injection without further
processing.

The same renderer is used for the initial page load (`_render_message`)
and the SSE stream (`api_stream` adds `content_html` to each message
payload).

### Syntax highlighting

Fenced code blocks (`` ```python ``, `` ```javascript ``, etc.) are
highlighted client-side by [highlight.js v11.10.0](https://highlightjs.org/),
loaded from cdnjs in `<head>` via the `HIGHLIGHT_JS_HEAD` constant
passed through `_layout()`'s optional `head_extras=` parameter. Scoped
to the conversation detail page only — the homepage and the
conversations list don't load the library.

- **Theme:** `github-dark` from highlight.js's bundled stylesheets.
  One small CSS override
  (`.msg-body pre code.hljs { background: transparent; padding: 0 }`)
  keeps the surrounding `<pre>` box styling intact so highlight.js
  doesn't fight the existing message-body chrome.
- **Language hints:** markdown-it-py's default behavior emits
  `<code class="language-X">` for `` ```X `` fences; highlight.js reads
  that class and skips its auto-detector. Unhinted fences (just ` ``` `)
  fall through to highlight.js's auto-detection.
- **Live append:** the SSE handler in `_render_conversation()`'s
  inline JS calls `hljs.highlightElement()` on each newly-inserted
  message node, so mid-conversation arrivals look the same as the
  initial server-rendered batch.

There's a brief "unstyled code flash" between initial paint and
highlight.js's first pass — acceptable trade-off for keeping Pygments
(+ a Python dep + per-render CPU) out of the stack. If that flash ever
becomes annoying, the natural move is server-side via Pygments piped
through `markdown-it-py`'s `highlight=` callback.

---

## Markdown export (`GET /api/conversations/{cid}/export.md`)

> **The renderers live in `src/orchestrator/export.py`** (since 2026-07-10),
> imported into `web_ui.py` under their old underscore names — the same
> functions also power `scripts/publish_debate.py`, which writes these files
> straight into the AI-Automation-Library archive. The output format is a
> **contract** with downstream parsers — see
> [`export-format.md`](export-format.md) before changing any shape below.

`render_export_markdown(data)` builds a self-contained Markdown document
from the conversation row plus its messages:

```
# Conversation #{id}: {topic}

| Field | Value |
|:---|:---|
| Status | … |
| Mode | … (max N turns/agent) |
| Participants | … |
| Created | … |
| Updated | … |
| End reason | …  ← only when set

---

## {sender} — {timestamp} — `signal=done`  ← signal segment only when set

{message body, verbatim — no double-rendering through HTML}

---

## {next sender} — {timestamp}

…

_Exported from Agent Battleground. Source: Conversation #{id}._
```

Headers: `Content-Type: text/markdown; charset=utf-8`,
`Content-Disposition: attachment; filename="<slug-or-fallback>.md"`,
`Cache-Control: no-store` (because the conversation can change while
live). 404 for unknown ids.

### Bundle export (`GET /api/conversations/{cid}/export.zip`)

`render_export_zip(data)` builds a `.zip` of Markdown files (stdlib `zipfile`
into a `BytesIO`, served as `application/zip`; the file set comes from the
shared `bundle_files()`):

- **`topic.md`** — `render_export_overview()`: the topic + an overview metadata
  table (status, mode, max-turns, participants, dates, end reason, preset, the
  conversation **type**, and the lead seat when one was recorded), a
  **Cast** list when personas are recorded, and the rendered kickoff/framing
  (`kickoff_template`) when present. No invented subtopics.
- **`personas/<agent>-<slug>.md`** — `persona_doc()`, one per participant: the
  CLI tool (`agent_id`), the seat it held (`Role`, omitted for conversations
  seeded before roles existed), the persona name/slug, and the full card body.
  Source is the conversation's `participant_personas` JSON (recorded by
  `scripts/debate.ps1` at launch). Participants without a recorded persona get a
  doc noting so.
- **`transcript.md`** — the same body as the single-file `export.md`.

`participant_personas` stores the **full card body**, not just a slug, so the
bundle is complete even on the hosted mirror (where `agents/` cards aren't shipped).

---

## Media prompts (`orchestrator/media_prompts.py`)

Two of the four buttons in the conversation page's **Actions** panel —
**Image prompt** and **Audio prompt**, beside the two exports. Each opens a
modal holding a prompt built from that conversation, with **Copy prompt** and
**Download .md**.

The labels carry the word *prompt* deliberately. Called just "Images" and
"Audio" they read as a generate button, which is the one thing this path never
does — the modal title, the blurb, and a footer note (**This page generates
nothing**) all repeat it. Don't shorten them back.

A **`?` badge** sits on each button's top-right corner (`_media_button()`),
explaining on hover that this is *a prompt, not a generator* — the image one
names the conversation's own format ("for this podcast"). Three things about it
are load-bearing:

- **The badge is a sibling of the `<button>`, not a child.** Nesting anything
  interactive inside a button is invalid HTML, and a help affordance that also
  fires the button is a trap.
- **The tip is the badge's next sibling**, so it anchors to the `.cv-pbtn`
  wrapper and clears the whole button. Anchored to the badge it opened halfway
  up the button and covered the label it was explaining.
- **The tip is `pointer-events: none`** so it can never swallow a click meant
  for the button underneath, and the badge is `tabindex="0"` +
  `aria-describedby` so the explanation is reachable without a mouse.

The badge's fill is a literal hex rather than a token: it straddles the button's
edge, and the translucent `--panel` let the border show through so it stopped
reading as a distinct chip.

> [!IMPORTANT]
> **They produce text, never media.** Nothing in this path calls an image or
> audio API, spends a credit, or writes a file. The output is a prompt you paste
> into whatever tool you use — the same posture as the battleground panel's
> copyable launch command, and for the same reason. Don't "finish" this by
> wiring a generation API into the web server.

| Kind | Asks the receiving tool for |
|:---|:---|
| `images` | `cover-image.png`, `<conv_type>-team.png` (so a debate gets `debate-team.png` and a podcast `podcast-team.png`), and one portrait per seat named `<persona-slug>.png`. |
| `audio` | One `<slug>.mp3`, rendered per-turn and stitched, plus the transcript and a README. |

Both are filled in from the conversation row: topic, format, seat roles, the
cast, and each persona's card. Details worth knowing before changing them:

- **Filenames use `export.topic_slug()`** — the same 25-char slug that joins the
  DB, the library archive, and the theater app. Do not add a second slug rule.
  The folder shape matches the library's podcast episodes, so a finished bundle
  drops in without translation.
- **The audio prompt links the transcript rather than embedding it.** It tells
  the reader to `curl` this app's own `export.md`, so the prompt stays paste-
  sized and can't go stale while a conversation is still running. The URL is
  built from the **request origin**, so a hosted visitor gets a hosted URL —
  don't hardcode localhost back in.
- **Persona cards are capped** at `_MAX_CARD_CHARS` (2000) per seat, cut on a
  line boundary with a visible marker. Cards run ~5KB and are mostly behavioural
  instruction that an image or voice tool has no use for; uncapped, a five-seat
  prompt approached 30KB. Capped, the largest prompt in the current DB is ~9KB.
- **The prompt is fetched on click, not embedded.** Two ~9KB strings in the HTML
  of every conversation page, for a button most visits never press, is the
  version of this that got rejected.
- **Both prompts carry a likeness/disclosure clause.** Personas are frequently
  written after real public figures, so the image prompt asks for stylized
  caricature rather than photoreal impersonation, and the audio prompt rules out
  cloning a real person's voice. Keep them.

Covered by `tests/test_media_prompts.py`.

---

## Cast panel (conversation page)

When a conversation has a recorded persona cast (`conversations.participant_personas`,
set by `scripts/debate.ps1` at launch), the detail page renders a **Cast** panel
above the transcript — one expandable entry per participant showing the CLI tool
(`agent_id`), the persona name, and the **seat** it held (Host / Guest /
Moderator / Debater, read from `participant_roles`; the lead gets the accent
treatment, and the label is absent for conversations seeded before roles were
recorded), expanding to the full personality card. Cast rows
and each message header carry a **persona avatar** (see [Persona avatars](#persona-avatars-webavatars)),
and each message header is also labelled with the persona name (e.g.
*Flat-Earth Fred* `claude-code`), for both the server-rendered initial messages
and the live SSE-appended ones (a `PERSONAS` JS map carries `agent_id →
persona_name` to the client, while `AGENT_VISUALS` carries each agent's avatar
**initials, gradient style, and persona slug** so live messages render the same
image the server did). Styling is in `_CAST_CSS`.

**Fallback for conversations with no recorded cast.** Plenty of rows predate the
persona system (any plain non-debate run, plus most conversations below #23), and
they used to render no panel at all. `_effective_cast()` now backfills each
participant that has no recorded persona with the built-in **AI-Models** card for
its CLI — see [`personas.md`](personas.md#ai-models--the-default-cast) — so
conversation #16 (`gemini` + `codex`) reads as *Gemini vs Codex*. Those rows carry
an `AI model` chip (`.cast-model`) to mark them as the CLI's default card rather
than a cast persona; a recorded persona always wins. The cards are created on boot
by `ensure_model_personas()` (create-if-missing). If the DB holds no AI-Models
rows, the panel degrades to the old behaviour — no panel, bare `agent_id` labels.
Message-header **names** are still not backfilled (they keep showing the raw
`agent_id`, to avoid a redundant *Claude Code* `claude-code`), but the header
**avatar** now resolves from the agent id, so a CLI participant shows its brand
mark rather than initials — see [Persona avatars](#persona-avatars-webavatars).

## Persona avatars (`web.avatars`)

Every place the UI names a specific persona shows its **avatar image**: the
persona rows on `/personas`, the Cast panel and message headers on the
transcript page, and the roster + featured-debate chips on the homepage.

**Three sources, in order** — an uploaded image on the persona's row, then
shipped file art, then the default silhouette — all behind `GET /avatars/{slug}`
(`web/avatars.py`).

- **Uploaded avatars live in the DB.** The `/personas` editor and the importer
  write the image onto the persona row (`avatar_mime` + base64 `avatar_data`),
  and it **wins over file art** — replacing a shipped avatar from the browser is
  an explicit operator action and should stick. The DB is the only placement that
  works on a hosted mirror: the `personas` table is carried by the sidecar, so an
  upload crosses over on the next sync tick **with no redeploy**, and one made on
  the mirror survives the next one. A file written into the image's tree would do
  neither. See [`personas.md` → Avatars](personas.md#avatars).
- **Shipped art is convention, not schema.** The image for persona `<slug>` is
  `images/AgentChat-Avatars/<slug>-avatar.png` (persona photos) **or**
  `<slug>-avatar.svg` (the CLI agents' brand marks — `.png` wins if both exist).
  Like [topic logos](#topic-logos-webtopics) this is resolved at render time from
  the slug already present in `participant_personas` / the persona registry — no
  migration, no backfill. Drop a `<slug>-avatar.png` in and it appears.
- **CLI agents (the `AI-Models` cards).** `claude-code`, `codex`, `antigravity`,
  `gemini`, `kimi`, `opencode` ship an **original brand-glyph SVG** each
  (`<id>-avatar.svg`) — the tool's signature colour + a simple non-infringing
  mark, deliberately *not* a copy of the vendor's trademarked logo (same spirit
  as the AI-Models card bodies). Drop an official `<id>-avatar.png` in to override.
- **Agent-id fallback = brand marks with no cast.** When a conversation has **no
  linked personas**, each message header and Cast row resolves its avatar from
  the raw agent id — which for a CLI participant *is* its brand-avatar slug — so
  those runs show the tool marks instead of bare initials. This holds for the
  live SSE path too (`AGENT_VISUALS.slug` falls back to the sender id).
- **Default fallback.** Any slug that still has no file — a persona with no art,
  an unknown agent id — gets a neutral head-and-shoulders **silhouette**
  (`default-avatar.svg`, with an embedded copy in `web/avatars.py` as a last
  resort). So an avatar slot is never empty. `DEFAULT_AVATAR_URL`
  (`/avatars/_default`) is the URL that always resolves to it: `_default` can't be
  a persona slug, so the handler falls straight through. The editor's preview
  points there after **Remove**.
- **Uploads are raster-only, typed by their bytes.** `normalize_avatar()` sniffs
  the magic bytes and stores PNG / JPEG / GIF / WebP — whatever the uploader
  *claimed* is ignored, and SVG is refused outright, because it is script-capable
  markup and these bytes are served back from the app's own origin. Stored images
  are served with `X-Content-Type-Options: nosniff` and
  `Content-Security-Policy: default-src 'none'; sandbox`. Ceiling is
  `AVATAR_MAX_BYTES` (2 MB decoded); the browser downscales to 512px on the long
  edge before upload (PNG, falling back to JPEG when the PNG is still large), and
  ships images under 400 KB byte-for-byte so animated GIFs keep animating.
- **Layered rendering.** The `<img class="avatar-img">` overlays the existing
  initials-on-gradient chip (`.avatar-has-img` + `.avatar-img` in `assets.py`,
  `object-fit:cover`, `border-radius:inherit`). If the image fails to load,
  `onerror` hides it and the monogram underneath shows through. The plain
  (non-`-rounded`) PNGs are used everywhere; each chip's own border-radius does
  the circle/rounded-square crop.
- **Live messages.** `AGENT_VISUALS` carries each agent's `persona_slug` to the
  client so SSE-appended messages build the same `<img>` the server rendered.
- **Cache-busting.** `avatar_url()` appends `?v=…` — a digest of the row's
  `updated_at` for an uploaded avatar, else the file mtime — so swapping a
  persona's art (or the CLI glyphs) changes the URL and browsers holding a long
  `Cache-Control` copy — including the default silhouette served before a file
  existed — refetch without a manual reload. The live-append JS uses the same
  versioned URL (carried in `AGENT_VISUALS.avatar`).
  Building a page of *N* avatar URLs is **one** query, not *N*: `uploaded_index()`
  memoizes `{slug: updated_at}` for 30s, and every write path (the persona
  endpoints, `/api/ingest`) calls `invalidate_index()` so a fresh upload is
  versioned immediately. The **serve** path is deliberately not gated on that
  cache — it reads the DB per request, so a stale entry can never withhold a
  just-uploaded image.
- **SVG marks must be pure shapes.** The CLI brand SVGs are built from `<rect>` /
  `<path>` / `<circle>` / gradients only — **no `<text>` and no `<mask>`**, which
  don't render when an SVG is loaded via an `<img>` tag (they work on direct
  navigation, which makes the bug easy to miss). Glyphs are drawn as vector
  paths. Keep this constraint for any new SVG avatar.
- **Serving + shipping.** Read-only GET (passes the hosted read-only middleware),
  exempted from basic-auth next to `/favicon.svg` (`web/security.py`), long
  `Cache-Control`. The slug is regex-gated (`[a-z0-9-]`) so a path component
  can't traverse out of `AVATARS_DIR`. `images/AgentChat-Avatars/` is COPYed into
  the Fly image (`Dockerfile` + a scoped `.dockerignore` un-ignore) — the rest of
  `images/` stays out of the runtime image.

To add or replace an avatar: drop `<slug>-avatar.png` into
`images/AgentChat-Avatars/`, commit it, and (for the hosted mirror) redeploy to
Fly so the new file ships.

## Persona management (`GET /personas`)

A **three-pane management console** for the debate personality roster (the
2026-06-29 redesign replaced the single-column accordion). Emerald-accented to
match the homepage brand and the favicon, scoped to a `.pm3` wrapper so it
doesn't disturb the `BASE_CSS` the other app pages use. Fills the viewport
below the topbar via `main:has(.pm3)`, which zeroes `<main>`'s padding. (That
override is still needed — `main` carries `--gutter` padding this page zeroes,
and a `--rail-w` margin it must keep so the panes clear the
[icon rail](#navigation-the-icon-rail).) Styled by `_PERSONAS_CSS`; rendered by
`_render_personas_page`.

**Deep-links.** Accepts `?group=<group>&q=<text>` — selects the group, then
prefills the rail search. The command palette links personas this way, so
picking "Gordon Ramsay" from `⌘K` lands on the Celebrities group filtered to
that one row.

- **Left rail — group navigator.** A search box, one button per group (folder
  icon, name, count chip) with the active group emerald-highlighted, and a
  `+ New group` action. Clicking a group switches the center list client-side;
  non-active groups carry the `hidden` attribute (`.pm-rows[hidden]` =
  `display:none`).
- **Center pane — persona list.** Header with the group title, a sort `<select>`
  (Name A–Z / Z–A), and `+ New` / `Import` / `Select` actions; a column header;
  then one row per persona (monogram avatar, name, mono slug, emerald tag chips,
  and hover quick-actions: edit / duplicate / delete). The left-rail search
  filters the active group's rows by name/slug/tags. Empty/filtered states show
  an inline notice.
- **Right pane — detail / edit.** One shared form, populated client-side on row
  select (no full re-render). Display name, a group `<select>` (with the
  *＋ Create new group…* escape hatch), a tag chip input, and the Markdown body
  under **Edit / Preview** tabs. Preview is a small inline, escape-first Markdown
  renderer (headings/bold/italic/code/lists) — no CDN dependency, so the page
  works offline. **Save** / **Delete** in the footer. On a narrow viewport
  (≤900px) the rail + list stack and this pane becomes a right slide-over drawer
  (opened on select, closed via its ✕).
- **Avatar picker** (in the detail pane, above Tags). A round preview of the
  persona's current image plus **Choose image…** and **Remove**; **Remove** only
  appears when there's an *uploaded* avatar to remove — shipped file art and the
  silhouette aren't the editor's to delete. The image is read and downscaled in
  the browser (`fileToAvatarB64`, canvas, 512px long edge; files under 400 KB go
  byte-for-byte so animated GIFs survive), previewed as a `data:` URI, and applied
  **on save** — nothing is written until the form is submitted. The save payload
  carries `avatar:{b64}` or `clear_avatar:true` **only when the operator touched
  it**, so an ordinary body edit can't drop the art. See
  [Persona avatars](#persona-avatars-webavatars).
- **Duplicate** opens the form in create mode prefilled from the row (name +
  " copy", tags, body) and saves through `POST /api/personas` — there is no
  dedicated duplicate endpoint. The copy starts on the default silhouette: it's a
  new slug, and the original's image bytes only exist server-side.
- Persona bodies ride in a `<script type="application/json">` island the detail
  pane reads on selection (lighter than a textarea per row); `<` is escaped to
  `<` so a body containing `</script>` can't break out of the island.
- **Group folder** is a `<select>` of existing groups with a trailing
  *＋ Create new group…* option that reveals an inline text input — picking it
  and typing a name creates the group when the persona is saved (groups are just
  distinct `"group"` values, so a group materializes with its first persona).
- **Tags** use a chip input: type a tag and press comma or Enter (or paste a
  `a, b, c` list) to resolve each into a removable chip; Backspace on the empty
  field deletes the last chip.
- **Import** (a modal opened by the **Import** button) accepts one or more
  `.md` cards (read client-side via `File.text()`), **images**, and/or `.zip`
  archives (base64-encoded client-side and unzipped server-side with stdlib
  `zipfile`). All inputs POST to `/api/personas/import` as JSON
  (`files:[{filename, text}]`, `images:[{filename, b64}]`, `zips:[{filename,
  b64}]`). Each loose card and each `.md`/`.markdown` entry inside a zip is parsed
  as a seed-style frontmatter+body card; the filename stem becomes the slug. Zip
  entries are found recursively — directories, `__MACOSX` metadata, dotfiles, and
  any other file type are ignored. Zips are bounded by `_ZIP_MAX_ENTRIES` (1000)
  and `_ZIP_MAX_TOTAL_BYTES` (50 MiB uncompressed) to refuse zip bombs; entries
  are read into memory and parsed (never extracted to disk), so path traversal is
  a non-issue. A target group (existing or new) and an *overwrite* toggle apply to
  the whole batch; the response reports `imported` / `skipped` / `avatars` counts
  and the first error. The client **auto-batches** the selection into ~3 MB-of-
  content chunks and POSTs them sequentially (aggregating the counts), so a large
  selection doesn't put one oversized request on the small hosted VM — pick
  everything at once and it chunks itself. Batching groups by pairing key first,
  because **a card and its image must reach the server in the same request**.
- **Cards and images import together.** `_pair_avatars()` attaches each image in
  an upload to the card it belongs to, first match wins:

  | # | Shape | Example |
  |:--|:---|:---|
  | 1 | Same folder, matching name (a trailing `-avatar` is ignored) | `crypto-chad.md` + `crypto-chad.png` |
  | 2 | Same folder, exactly one card and one image | `crypto-chad/card.md` + `crypto-chad/avatar.png` |
  | 3 | The whole upload is one card and one image | any two files picked together |

  So one zip of `<persona>.md` + `<persona>.png` — flat, or a folder per persona —
  lands a persona with both its instructions and its picture. An image that pairs
  with nothing is **reported and skipped, never guessed onto an arbitrary card**;
  an unreadable or non-raster one costs that persona its picture, not its
  existence. An overwrite that carries no image **keeps the row's current
  avatar** — re-importing an edited card must not delete art uploaded separately.
- **Bulk delete** — the **Select** toggle (becomes **Done**) reveals a checkbox
  on every persona row and a floating action bar (**Select all** / **Clear** /
  **Delete selected** / **Cancel**) with a live selection count; **Select all**
  only ticks the rows currently visible (active group, matching the search).
  Confirming POSTs the chosen `(group, slug)` pairs to
  `/api/personas/bulk-delete`. Off by default, so the page is unchanged until you
  opt in. The per-persona **Delete** in the right pane (and the row's trash
  quick-action) still handles one-off removals.

Writes go through the registry write layer in `src/orchestrator/personas.py`
(`create_persona` / `update_persona` / `delete_persona` / `import_persona_card`,
which write the `personas` table and locate rows across **all** groups via
`_find_persona_any_group`). Personas live in the shared DB (`db/chat.db`), so —
unlike before — this **works on both local and the hosted mirror**: the
optional db-sync sidecar mirrors the `personas` table bidirectionally.
The page and its `POST /api/personas*` endpoints stay gated on
`personas.root_exists()`, which now just confirms the DB is reachable (it returns
`404` / an "unavailable" notice only if the database can't be opened at all).
Changes are picked up immediately by the next debate and by `list_personas` (no
caching), and propagate to the other side on the next sync tick (~5s).

## SSE stream (`GET /api/conversations/{cid}/stream`)

Long-lived `text/event-stream` connection. Query string: `?since=<last_id>`
to skip messages the client has already rendered.

**Tick loop** (`POLL_INTERVAL_SECONDS = 1.0`, in `web/api/conversations.py`):

1. `request.is_disconnected()` → break (client closed tab).
2. `messages_since(cid, last_id)` → emit `event: message` per row with
   payload `{...message_row, "content_html": render_markdown(content)}`.
3. `conversation_turn_state(cid)` → if `complete`, emit `event: complete`
   and break; if the row is gone (deleted), break silently; else if
   `current_turn` changed since the last tick (including the first tick),
   emit `event: turn` with `{"current_turn": "<agent-id-or-null>"}` — the
   reader's whose-turn badge listens for this.
4. `await asyncio.sleep(1.0)`, continue.

**Why 1 second.** Same cadence as `wait_for_turn` server-side polling.
Cheap (each tick is one indexed query). New rows surface within
`interval + RTT` ≈ 1–2s locally, ~5–7s through the Fly mirror (extra
hop = the local sidecar's `--interval` window).

---

## Ingest (`POST /api/ingest`)

Bearer-token write endpoint. Used by [`scripts/db_sync.py`](../../scripts/db_sync.py)
to push local DB deltas at a hosted mirror. Two features unique to this
endpoint:

- **Independent auth realm.** `/api/ingest` is exempt from both the
  optional basic-auth gate (`BasicAuthMiddleware` short-circuits on
  `request.url.path == "/api/ingest"`) and the read-only gate
  (`ReadOnlyMiddleware` exempts it), so the machine-to-machine sidecar only
  needs its bearer token — not the human basic-auth password, and it keeps
  pushing even when the public mirror is read-only (see [Auth](#auth)). The
  bearer-token check is enforced inside the route handler regardless.
- **Opt-in per deployment.** When `AGENT_CHAT_INGEST_TOKEN` is unset, the
  endpoint short-circuits to `404 ingest disabled` — local dev never has
  to think about it.

---

## Auth

> [!IMPORTANT]
> **The hosted Fly deploy is read-only.** Reads (browser pages + JSON GETs)
> are public; every browser **mutation** (stop / delete / orchestrate /
> persona writes) is rejected with `403` because the deploy sets
> `AGENT_CHAT_PUBLIC_READONLY=1` (see `[env]` in [`fly.toml`](../../fly.toml)).
> The bearer-gated `/api/ingest` sync realm is exempt, so the local→Fly
> sidecar keeps pushing. Local dev runs with the flag **off** — fully
> writable and unauthenticated.

`_build_middleware()` in [`src/web_ui.py`](../../src/web_ui.py) assembles the
stack from two independent, default-off env flags:

| Surface | Trigger env var | Status | Mechanism | Realm |
|:---|:---|:---|:---|:---|
| Browser **mutations** (any non-GET/HEAD/OPTIONS, except `/api/ingest`) | `AGENT_CHAT_PUBLIC_READONLY` | **on** for the Fly deploy (`fly.toml`); off locally | `ReadOnlyMiddleware` → `403 read-only deployment`. Keys off the HTTP method, so new mutation routes are covered automatically. | — |
| Browser pages + JSON API | `AGENT_CHAT_BASIC_AUTH_PASSWORD` | off (unset) | HTTP Basic via `BasicAuthMiddleware`, attached when the password is set. Username defaults to `admin`, override with `AGENT_CHAT_BASIC_AUTH_USER`. Listed first so it forms the outermost layer. | `agent_chat` |
| `/api/ingest` | `AGENT_CHAT_INGEST_TOKEN` | active when env var set | `Authorization: Bearer <token>`, constant-time compared. | `agent_chat_ingest` |

Read-only mode is the public-safety baseline (it stops data loss without a
login); basic auth is the heavier gate when you want to lock reads too. They
compose — basic auth challenges first, then the read-only check runs. Both
credential checks use `secrets.compare_digest`. Neither is meant for serious
multi-user auth — for that, front the deploy with whatever your platform
gives you (Cloudflare Access, Tailscale Funnel, …).

`/favicon.svg` is exempt from basic auth (so browsers can fetch the icon for
the auth-challenge tab); `GET` requests are never blocked by read-only mode.

### The demo strip

Enforcement without communication is a trap: someone landing on a shared
`/conversations/<id>` link has no cue that the Stop, Delete and persona-editor
buttons in front of them are going to `403`. So `demo_banner()` in
`web/render/common.py` renders a slim amber strip under the topbar on **every**
page, and the homepage template renders the same call.

It keys off `_is_public_readonly()` — the *same* env flag `ReadOnlyMiddleware`
enforces on — so the promise and the enforcement cannot drift: if the strip is
showing, mutations 403, and if mutations 403, the strip is showing.

**Not dismissible**, on purpose. A notice you can hide is a notice that isn't
there for the next person on the same link.

Layout-wise it's `position: sticky` under the topbar, and
`body:has(.demo-strip) .siderail { top: calc(var(--topbar-h) + var(--demo-h)) }`
pushes the fixed rail down by exactly its height, so the two never overlap.
Presence-gated with `:has()` rather than a `body` class because the homepage
builds its own `<body>` tag. The `?fullscreen=1` reader hides it along with the
rail.

---

## Configuration

| Setting | Where | Default |
|:---|:---|:---|
| DB path | `--db-path` arg or `$AGENT_CHAT_DB` | `<repo>/db/chat.db` (resolved from `src/web_ui.py`'s location) |
| Bind address | `--host` or `$HOST` | `127.0.0.1` |
| Port | `--port` or `$PORT` | `8765` |
| Public read-only mode | `$AGENT_CHAT_PUBLIC_READONLY` | unset → off (writable) locally; `"1"` on the Fly deploy → browser mutations return `403` |
| Basic auth password | `$AGENT_CHAT_BASIC_AUTH_PASSWORD` | unset → gate off; set → HTTP Basic attached |
| Basic auth user | `$AGENT_CHAT_BASIC_AUTH_USER` | `admin` |
| Ingest token | `$AGENT_CHAT_INGEST_TOKEN` | unset → ingest off (404) |

Local dev (no env vars set):

```powershell
.\.venv\Scripts\python.exe src\web_ui.py
# → http://127.0.0.1:8765/
# (DB defaults to <repo>/db/chat.db; override with --db-path or $env:AGENT_CHAT_DB.)
```

A public read-only mirror runs with `AGENT_CHAT_INGEST_TOKEN` set (ingest on),
`AGENT_CHAT_PUBLIC_READONLY=1`, and browser basic-auth off.

---

## Schema sync

`SCHEMA` is duplicated from `src/agent_chat_mcp.py` rather than imported —
the web UI's copy lives in `src/web/db.py` (moved there by the 2026-07-10
split). Reason: keeping the web UI lightweight (no FastMCP/Pydantic on
startup) and letting it boot against an empty Fly volume on first request
via `db_init()`. **When the schema changes, both files must be updated in
the same PR**, plus a CHANGELOG entry. The duplication is annotated with a
`sync-required` note on each side.

---

## Where to look for what

| Concern | File / function |
|:---|:---|
| Add or rename a route | `routes` list in `web_ui.py`, plus an entry in this table. |
| Tweak the homepage layout | `web/render/home.py` (`_render_homepage()` + `_HOMEPAGE_TEMPLATE`), styled by `HOME_CSS` in `web/assets.py`. |
| Tweak the conversations browser or reader | `web/render/conversations.py` (`_conversations_rail()` / `_render_conversations_overview()` / `_render_conversation_main()`), styled by `_CONV_CSS` in `web/assets.py` (+ `BASE_CSS` for `.msg` cards). |
| Adjust Markdown rendering | `_md` instance + the `_link_open_renderer` rule in `web/render/common.py`. |
| Swap syntax-highlighting theme or version | `HIGHLIGHT_JS_HEAD` in `web/assets.py` (CDN URLs + `.hljs` background override). Restart `web_ui.py` (or redeploy) — clients pick up the new CDN on next page load. |
| Change the export format | `render_export_markdown()` in `src/orchestrator/export.py` — but read [`export-format.md`](export-format.md) first; the format is a contract with the library archive + theater app. |
| Touch SSE behavior | `api_stream()` in `web/api/conversations.py` + the inline JS in `_render_conversation_main()`. |
| Force-stop semantics | `stop_conversation()` in `web/db.py` + `api_stop()` in `web/api/conversations.py`. Mirror in `inspect_conversations.cmd_stop`. |
| Auth | `web/security.py` (`BasicAuthMiddleware` + `_build_middleware()`). |
| Ingest | `ingest_payload()` in `web/db.py` + `api_ingest()` in `web/api/sync.py`. Client: `scripts/db_sync.py`. |
| Favicon / brand | `FAVICON_SVG` in `web/assets.py` + the `favicon()` route handler in `web_ui.py`. |
| Add a conversation topic logo / re-tune which one a topic gets | The `TOPICS` table in `web/topics.py` (keywords + glyph + gradient; order = tie-break priority). Add a case to `tests/test_topics.py`. No migration — existing rows re-classify on next page load. |
| Theater link | `THEATER_URL` in `web/render/common.py` (icon rail via `_NAV_ITEMS`, homepage Featured-debates panel, command palette). |
| Persona Registry link | `REGISTRY_URL` in `web/render/common.py` (icon rail via `_NAV_ITEMS`, command palette). Both reach it through `window.__AB_LINKS`, set in `_CMDK_HTML`. |
