"""CSS / JS / static-asset constants for the web UI pages.

Pure data — no imports, no logic. Page templates live with their renderers
under ``web.render``; only reusable style/script constants live here.
"""


# ---------------------------------------------------------------------------
# HTML rendering (inline — fine for a small local app)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Design tokens — the single :root block, shared by BOTH stylesheets.
# ---------------------------------------------------------------------------
# BASE_CSS (the _layout() shell) and HOME_CSS (the Tailwind-CDN homepage) are
# served to different pages and never appear together, so each one composes
# these tokens in itself. Edit here once; both pages move.

DESIGN_TOKENS = """
/* Apex-aligned design tokens — mirror mikesailab.com.
   Canvas #060606, zinc text, emerald-400 links, emerald-500 actions, red-500
   destructive, amber-500 warning. Class names match the names the existing
   renderers and SSE-append JS write to the DOM — do not rename without
   updating _render_message + the inline script in _render_conversation. */
:root {
  --bg: #060606;
  --panel: rgba(24, 24, 27, 0.4);          /* zinc-900/40 */
  --panel-solid: #18181b;                   /* zinc-900 */
  --panel-2: #27272a;                       /* zinc-800 */
  --text: #f4f4f5;                          /* zinc-100 */
  --muted: #a1a1aa;                         /* zinc-400 */
  --muted-2: #71717a;                       /* zinc-500 */
  --accent: #10b981;                        /* emerald-400 — links */
  --accent-strong: #059669;                 /* emerald-500 */
  --accent-2: #10b981;                      /* emerald-500 — actions/done */
  --border: rgba(39, 39, 42, 0.6);          /* zinc-800/60 */
  --border-strong: #3f3f46;                 /* zinc-700 */
  --good: #10b981;                          /* emerald-500 */
  --warn: #f59e0b;                          /* amber-500 */
  --bad: #ef4444;                           /* red-500 */

  /* --- Layout -------------------------------------------------------------
     The *header* is full-bleed: the wordmark sits in the literal left corner,
     the actions in the right one, inset only by --gutter. Content is not —
     reading pages centre on --page (margins), and only the app surfaces
     (/conversations, /personas) run their panes edge-to-edge.

     --rail-w is the universal icon sidebar. It's `position:fixed`, so every
     page's <main> is inset by exactly this much; change it here and the whole
     app shifts together. */
  --gutter: clamp(16px, 1.8vw, 28px);
  --topbar-h: 52px;
  /* Height reserved for the hosted mirror's read-only demo strip. Only ever
     spent when that strip renders (see .demo-strip in TOPBAR_CSS), which is
     also what pushes the fixed rail down by the same amount. */
  --demo-h: 34px;
  --page: 1400px;                           /* centred content column */
  --measure: 75ch;                          /* readable line length for prose */

  /* The rail is expanded (titles showing) by default and collapses to icons.
     Resolve --rail-w from these two rather than overriding it directly: the
     mobile media query below only has to move the endpoints, so it can't lose
     a specificity fight with html.rail-collapsed. */
  --rail-open: 208px;
  --rail-shut: 64px;
  --rail-w: var(--rail-open);
}
html.rail-collapsed { --rail-w: var(--rail-shut); }
"""


# ---------------------------------------------------------------------------
# Topbar + command palette — ONE definition, used by both stylesheets.
# ---------------------------------------------------------------------------
# The homepage renders its own <header> markup historically; both it and the
# _layout() shell now emit render.common._topbar(), so this block is the only
# place topbar/nav styling lives. Rules are deliberately NOT scoped under
# `.topbar` — the palette and live pill are siblings of it.

TOPBAR_CSS = """
/* ---- topbar: full-bleed, mark hard-left, actions hard-right ---- */
.topbar {
  position: sticky; top: 0; z-index: 40;
  height: var(--topbar-h);
  background: rgba(6, 6, 6, 0.82);
  backdrop-filter: blur(14px) saturate(150%);
  -webkit-backdrop-filter: blur(14px) saturate(150%);
  border-bottom: 1px solid #18181b;
}
.topbar-inner {
  height: 100%;
  display: flex; align-items: center; gap: 14px;
  padding: 0 var(--gutter);
  /* No max-width and no auto margins: the mark sits in the literal left
     corner (inset only by --gutter) and .topbar-right in the right one. */
}
.topbar .mark {
  display: inline-flex; align-items: center; gap: 10px;
  text-decoration: none; color: var(--text);
  font-weight: 600; font-size: 14px;
  letter-spacing: -0.005em;
  flex: none;
}
.topbar .mark:hover { text-decoration: none; }
/* The mark is the favicon artwork itself (assets.MARK_SVG), not a letterform:
   the corner of the page and the browser tab show the same thing. It carries
   its own plate, its own emerald ring and its own rounding, so this box only
   sizes it — no background, no border-radius of its own. */
.topbar .mark .glyph {
  width: 26px; height: 26px;
  display: block; flex: none;
  transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.18s ease;
  border-radius: 7px;
}
.topbar .mark .glyph svg { display: block; width: 100%; height: 100%; }
.topbar .mark:hover .glyph {
  transform: rotate(-6deg) scale(1.06);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.16);
}
.topbar .mark-txt { white-space: nowrap; }
.topbar .crumb {
  color: var(--muted-2);
  font-size: 13px;
  min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.topbar .crumb a { color: var(--muted); text-decoration: none; }
.topbar .crumb a:hover { color: var(--text); }
.topbar .crumb strong { color: var(--text); font-weight: 500; }

/* The right cluster is pushed to the far edge by margin-left:auto. */
.topbar-right {
  margin-left: auto;
  display: flex; align-items: center; gap: 8px;
  flex: none;
}

/* ---- universal icon sidebar -------------------------------------------
   Navigation lives here, not in the header. `position:fixed` rather than a
   grid column: /conversations and /personas already own their own scrolling
   rails and full-height panes, and a fixed rail insets them with one
   `margin-left` instead of rewriting their layout. */
.siderail {
  position: fixed;
  top: var(--topbar-h); left: 0; bottom: 0;
  width: var(--rail-w);
  z-index: 35;
  display: flex; flex-direction: column; align-items: stretch;
  gap: 2px;
  padding: 10px 8px;
  background: #08080a;
  border-right: 1px solid #18181b;
  overflow: hidden;
  transition: width 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}
main { transition: margin-left 0.18s cubic-bezier(0.16, 1, 0.3, 1); }
.siderail .rail-sep {
  height: 1px; flex: none;
  background: var(--border-strong); opacity: 0.55;
  margin: 8px 4px;
}
.siderail .rail-spacer { flex: 1; }
/* Section heading for the rail's second group (reference + third-party links).
   Collapsed there's no room for it and the separator alone does the grouping. */
.siderail .rail-glabel {
  flex: none;
  padding: 2px 11px 6px;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.14em;
  color: var(--muted-2);
  white-space: nowrap; overflow: hidden;
}
html.rail-collapsed .rail-glabel { display: none; }

/* ---- read-only demo strip (hosted mirror only) ------------------------
   Sticks directly under the topbar and pushes the fixed rail down by its own
   height, so the two never overlap. Presence-gated with :has() rather than a
   body class, because the homepage builds its own <body> tag. */
.demo-strip {
  position: sticky; top: var(--topbar-h); z-index: 34;
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  padding: 8px var(--gutter);
  min-height: var(--demo-h);
  background: rgba(245, 158, 11, 0.10);
  border-bottom: 1px solid rgba(245, 158, 11, 0.30);
  font-size: 12.5px; line-height: 1.45; color: #fcd9a1;
}
.demo-strip .demo-tag {
  flex: none;
  padding: 2px 7px; border-radius: 5px;
  background: rgba(245, 158, 11, 0.22);
  color: #fbbf24;
  font-size: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.12em;
}
.demo-strip .demo-txt { min-width: 0; }
.demo-strip a { color: #fbbf24; text-decoration: underline; text-underline-offset: 2px; }
.demo-strip a:hover { color: #fde68a; }
body:has(.demo-strip) .siderail { top: calc(var(--topbar-h) + var(--demo-h)); }
/* Fullscreen reader hides the rail; the strip goes with it. */
body:has(.cv2.cv-fullscreen) .demo-strip { display: none; }

/* Colourful, but not loud. Each destination owns a hue (--nav-h / --nav-s /
   --nav-l as HSL parts): the icon always carries the full hue, and the label
   a soft tint of it — so the rail reads as a set of distinct destinations at a
   glance. Hover and the current page brighten both, and the lit one still
   tells you where you are. */
.rail-btn {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  width: 100%; height: 40px; flex: none;
  padding: 0 11px;
  border: 0; border-radius: 9px;
  text-decoration: none;
  color: hsl(var(--nav-h) calc(var(--nav-s) * 0.7) 72%);
  background: transparent;
  font: inherit; font-size: 13px; font-weight: 500;
  text-align: left; cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.rail-btn:hover { text-decoration: none; }
/* The icon spends the hue in full — `currentColor` on the stroke resolves to
   the svg's own colour, so this tints only the glyph, not the label. */
.rail-btn svg {
  width: 18px; height: 18px; flex: none; stroke-width: 2;
  color: hsl(var(--nav-h) var(--nav-s) var(--nav-l));
}
.rail-lbl {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rail-ext { opacity: 0.5; font-size: 11px; }

/* Collapsed: icons only, titles move to the tooltip. */
html.rail-collapsed .rail-btn { justify-content: center; padding: 0; }
html.rail-collapsed .rail-lbl { display: none; }
html.rail-collapsed .rail-toggle svg { transform: rotate(180deg); }
.rail-toggle svg { transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1); }
.rail-toggle { color: var(--muted-2); opacity: 0.75; }
.rail-toggle:hover { opacity: 1; background: rgba(255, 255, 255, 0.05); color: var(--text); }
.rail-btn:hover {
  color: hsl(var(--nav-h) var(--nav-s) 82%);
  background: hsl(var(--nav-h) var(--nav-s) var(--nav-l) / 0.12);
}
.rail-btn.is-active {
  color: hsl(var(--nav-h) var(--nav-s) 84%);
  background: hsl(var(--nav-h) var(--nav-s) var(--nav-l) / 0.15);
}
/* Active marker on the rail's outer edge — a second, non-colour signal, so
   "you are here" survives forced-colors and colour-blindness. -8px lands it on
   the rail's own edge in BOTH states (the rail's padding-inline is 8px). */
.rail-btn.is-active::before {
  content: ''; position: absolute; left: -8px; top: 50%;
  transform: translateY(-50%);
  width: 3px; height: 20px; border-radius: 0 3px 3px 0;
  background: hsl(var(--nav-h) var(--nav-s) var(--nav-l));
}
.rail-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* Tooltip — the title, for when the rail is collapsed and can't show it.
   Expanded, the label is right there, so this would be pure noise: hence the
   `html.rail-collapsed` gate. The same string is always on aria-label, so
   nothing depends on hover to identify a destination. */
.rail-btn::after {
  content: attr(data-tip);
  position: absolute; left: calc(100% + 14px); top: 50%;
  transform: translateY(-50%) translateX(-4px);
  padding: 5px 9px; border-radius: 6px;
  background: #17171b; color: var(--text);
  border: 1px solid var(--border-strong);
  font-size: 12px; font-weight: 500; line-height: 1;
  white-space: nowrap; pointer-events: none;
  opacity: 0; visibility: hidden;
  transition: opacity 0.13s ease, transform 0.13s ease, visibility 0.13s;
  box-shadow: 0 6px 18px -4px rgba(0, 0, 0, 0.7);
  z-index: 2;
}
html.rail-collapsed .rail-btn:hover::after,
html.rail-collapsed .rail-btn:focus-visible::after {
  opacity: 1; visibility: visible; transform: translateY(-50%) translateX(0);
}
/* The rail clips its own overflow to keep labels from spilling mid-collapse,
   which would also clip the tooltip — so let it escape when collapsed. */
html.rail-collapsed .siderail { overflow: visible; }
.btn-home { --nav-h: 152; --nav-s: 60%; --nav-l: 50%; }   /* emerald-500 */
.btn-conv { --nav-h: 217; --nav-s: 91%; --nav-l: 60%; }   /* blue-500   */
.btn-orch { --nav-h: 258; --nav-s: 90%; --nav-l: 66%; }   /* violet-500 */
.btn-pers { --nav-h: 173; --nav-s: 80%; --nav-l: 45%; }   /* teal-500   */
.btn-reg  { --nav-h: 292; --nav-s: 84%; --nav-l: 61%; }   /* fuchsia-500*/
.btn-thea { --nav-h: 38;  --nav-s: 92%; --nav-l: 55%; }   /* amber-500  */
.btn-res  { --nav-h: 340; --nav-s: 82%; --nav-l: 62%; }   /* rose-500   */
.btn-extn { --nav-h: 24;  --nav-s: 90%; --nav-l: 58%; }   /* orange-500 */
.btn-setup{ --nav-h: 199; --nav-s: 89%; --nav-l: 55%; }   /* sky-500    */
.btn-arena{ --nav-h: 0;  --nav-s: 84%; --nav-l: 60%; }   /* red-500    */

/* Every page's <main> clears the fixed rail. The two app surfaces zero their
   padding but must keep this inset — hence `margin-left`, not padding. */
main { margin-left: var(--rail-w); }

/* ---- GitHub, hard right, behind a hairline divider ---- */
.topbar-div {
  width: 1px; height: 18px; flex: none;
  background: var(--border-strong); opacity: 0.6;
  margin: 0 2px;
}
.gh-link {
  display: inline-grid; place-items: center;
  width: 30px; height: 30px; border-radius: 7px;
  color: var(--muted); flex: none;
  transition: color 0.15s ease, background 0.15s ease;
}
.gh-link:hover { color: var(--text); background: rgba(255, 255, 255, 0.06); }
.gh-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* ---- live pill — polled by the shared topbar script ---- */
.live-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.12em; color: var(--good);
  font-weight: 500; flex: none;
  text-decoration: none;
  white-space: nowrap;
}
a.live-pill:hover { text-decoration: none; color: #6ee7b7; }
.live-pill .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--good); box-shadow: 0 0 6px var(--good);
  animation: pulse-live 1.6s ease-in-out infinite;
}
.live-pill.idle { color: var(--muted-2); }
.live-pill.idle .dot { background: var(--muted-2); box-shadow: none; animation: none; }
@keyframes pulse-live { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

/* ---- palette trigger — the ⌘K affordance ---- */
.cmdk-trigger {
  display: inline-flex; align-items: center; gap: 8px;
  height: 30px; padding: 0 9px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--muted-2);
  font: inherit; font-size: 12.5px;
  cursor: pointer; flex: none;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.cmdk-trigger:hover {
  border-color: var(--muted-2); color: var(--text);
  background: rgba(255, 255, 255, 0.05);
}
.cmdk-trigger:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.cmdk-trigger svg { width: 14px; height: 14px; flex: none; }
.cmdk-trigger .cmdk-trigger-txt { padding-right: 22px; }
kbd, .kbd {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 10px; line-height: 1;
  padding: 3px 5px;
  border: 1px solid var(--border-strong);
  border-bottom-width: 2px;
  border-radius: 4px;
  background: #131316;
  color: var(--muted);
}

/* ---- command palette ---------------------------------------------------
   Fuzzy-jump to any conversation, persona, or page. The index is fetched
   lazily on first open (see PALETTE_JS) so no page pays for it up front. */
.cmdk[hidden] { display: none; }
.cmdk {
  position: fixed; inset: 0; z-index: 90;
  display: grid; place-items: start center;
  padding: clamp(48px, 12vh, 140px) 16px 16px;
}
.cmdk-scrim {
  position: fixed; inset: 0;
  background: rgba(3, 3, 4, 0.66);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  animation: cmdk-fade 0.14s ease-out;
}
.cmdk-panel {
  position: relative;
  width: 100%; max-width: 620px;
  background: #0c0c0f;
  border: 1px solid var(--border-strong);
  border-radius: 14px;
  box-shadow: 0 24px 70px -12px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(255, 255, 255, 0.04);
  overflow: hidden;
  animation: cmdk-in 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes cmdk-fade { from { opacity: 0; } }
@keyframes cmdk-in {
  from { opacity: 0; transform: translateY(-8px) scale(0.98); }
}
.cmdk-field {
  display: flex; align-items: center; gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border);
}
.cmdk-field > svg { width: 16px; height: 16px; color: var(--muted-2); flex: none; }
.cmdk-field input {
  flex: 1; min-width: 0;
  background: transparent; border: 0; outline: none;
  color: var(--text);
  font: inherit; font-size: 15px;
  padding: 15px 0;
}
.cmdk-field input::placeholder { color: var(--muted-2); }
.cmdk-list {
  list-style: none; margin: 0; padding: 6px;
  max-height: min(52vh, 420px); overflow-y: auto; overflow-x: hidden;
  scrollbar-width: thin; scrollbar-color: var(--border-strong) transparent;
}
.cmdk-group {
  padding: 9px 10px 5px;
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.14em;
  color: var(--muted-2);
}
.cmdk-item {
  display: flex; align-items: center; gap: 11px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--muted);
  scroll-margin: 8px;
  min-width: 0;   /* let the long-topic children actually ellipsize */
}
.cmdk-item[aria-selected="true"] { background: rgba(16, 185, 129, 0.12); color: var(--text); }
.cmdk-item[aria-selected="true"] .cmdk-go { opacity: 1; }
.cmdk-ico {
  display: inline-grid; place-items: center;
  width: 26px; height: 26px; flex: none;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  color: var(--muted);
  font: 700 10px/1 'IBM Plex Mono', ui-monospace, monospace;
}
.cmdk-item[aria-selected="true"] .cmdk-ico {
  background: rgba(16, 185, 129, 0.16);
  border-color: rgba(16, 185, 129, 0.34);
  color: var(--accent);
}
.cmdk-ico svg { width: 13px; height: 13px; }
/* Column, not inline: title and sub are <span>s, and as inline boxes they ran
   together on one line ("Gordon RamsayCelebrities") and ignored text-overflow. */
.cmdk-body { min-width: 0; flex: 1; display: flex; flex-direction: column; }
.cmdk-title {
  display: block;
  font-size: 13.5px; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cmdk-title mark { background: transparent; color: var(--accent); font-weight: 600; }
.cmdk-sub {
  display: block;
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 10.5px; color: var(--muted-2);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-top: 2px;
}
.cmdk-go { margin-left: auto; flex: none; opacity: 0; color: var(--accent); font-size: 12px; }
.cmdk-empty {
  padding: 34px 16px; text-align: center;
  color: var(--muted-2); font-size: 13px;
}
.cmdk-foot {
  display: flex; align-items: center; gap: 16px;
  padding: 9px 14px;
  border-top: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.015);
  font-size: 11px; color: var(--muted-2);
}
.cmdk-foot span { display: inline-flex; align-items: center; gap: 5px; }
.cmdk-foot .cmdk-count { margin-left: auto; font-family: 'IBM Plex Mono', ui-monospace, monospace; }

/* ---- responsive: shed the bar's non-essentials before it can wrap ----
   The bar carries far less than it used to (nav moved to the rail), so it
   only needs the two steps. The rail itself never collapses — it IS the
   navigation, and 56px of a phone screen is a fair price for always-there
   nav that doesn't need a hamburger. */
@media (max-width: 760px) {
  .cmdk-trigger .cmdk-trigger-txt { display: none; }
  .cmdk-trigger { padding: 0 8px; }
  .topbar .crumb { display: none; }
}
/* A 208px rail would eat a third of a phone, so below this it is always
   collapsed regardless of the stored preference — moving BOTH endpoints
   rather than --rail-w itself, so html.rail-collapsed resolves here too and
   there's no specificity fight. The toggle goes with it: nothing to toggle. */
@media (max-width: 720px) {
  :root { --rail-open: 56px; --rail-shut: 56px; }
  .rail-lbl { display: none; }
  .rail-toggle { display: none; }
  .rail-btn { justify-content: center; padding: 0; }
  .rail-btn:hover::after, .rail-btn:focus-visible::after {
    opacity: 1; visibility: visible; transform: translateY(-50%) translateX(0);
  }
  .siderail { overflow: visible; }
}
@media (max-width: 560px) {
  .topbar .live-pill { display: none; }
  /* A keyboard hint on a device with no keyboard is just noise. */
  .cmdk-trigger kbd { display: none; }
  .topbar-div { display: none; }
}
/* Coarse pointers get no hover, so the tooltip would only ever fire on tap
   and then stick. Suppress it — aria-label still carries the name. */
@media (hover: none) {
  .rail-btn::after { display: none; }
}

/* ---- motion: one global opt-out ---------------------------------------
   Everything above (and the page-load reveals, pulses, and palette spring)
   collapses to instant here. Honour the OS switch rather than animating at
   people who asked us not to. */
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}
"""


# ---------------------------------------------------------------------------
# Shell JS — the command palette, the polled live pill, scroll reveals.
# ---------------------------------------------------------------------------
# Emitted by render.common._topbar() on every page, homepage included. Raw
# string (r-prefix): the regex escapes below must reach the browser intact.
# Reads its two external URLs from window.__AB_LINKS rather than being
# .format()-ed, so no brace in this JS ever has to be doubled.

SHELL_JS = r"""
<script>
(function () {
  'use strict';
  var d = document;
  var LINKS = window.__AB_LINKS || {};

  // Everything below queries the whole document, but this script is emitted
  // with the topbar — i.e. BEFORE <main> is parsed. Running inline meant
  // querySelectorAll('.reveal') matched nothing and the observer watched
  // nothing, leaving six homepage sections invisible. Wait for the DOM.
  function ready(fn) {
    if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  // Each feature is wired independently: one missing element (or one throw)
  // must not take the rest of the chrome down with it. The palette used to
  // `return` early on no #cmdk, which would now also skip the reveals and the
  // sidebar toggle below it.
  ready(function () {
    [initPill, initPalette, initReveals, initRail].forEach(function (fn) {
      try { fn(); } catch (e) { if (window.console) console.error('[agent-chat] ' + fn.name, e); }
    });
  });

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ================= shared data cache =================
     One /api/conversations response feeds BOTH the topbar live count and the
     palette's conversation index — fetching it twice on the same page would
     be pure waste. */
  var cache = { convs: null, personas: null };

  function fetchConvs(force) {
    if (!force && cache.convs) return Promise.resolve(cache.convs);
    return fetch('/api/conversations', { headers: { accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (j) { cache.convs = Array.isArray(j) ? j : []; return cache.convs; })
      .catch(function () { return cache.convs || []; });
  }
  function fetchPersonas() {
    if (cache.personas) return Promise.resolve(cache.personas);
    return fetch('/api/personas', { headers: { accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (j) { cache.personas = Array.isArray(j) ? j : []; return cache.personas; })
      .catch(function () { return []; });
  }

  /* ================= live pill =================
     The homepage used to render an `active` count server-side that went stale
     the moment a debate ended. Now every page carries the pill and polls, so
     it stays true without a refresh. Paused while the tab is hidden. */
  var pill = null;
  function paintPill(convs) {
    if (!pill) return;
    var n = 0;
    for (var i = 0; i < convs.length; i++) if (convs[i].status === 'active') n++;
    var txt = pill.querySelector('.live-txt');
    pill.className = 'live-pill' + (n ? '' : ' idle');
    if (txt) txt.textContent = n ? n + (n === 1 ? ' debate live' : ' debates live') : 'system online';
    pill.title = n ? n + ' active conversation' + (n === 1 ? '' : 's') + ' — open the inbox' : 'No debates running right now';
  }
  function initPill() {
    pill = d.getElementById('ab-live');
    if (!pill) return;
    fetchConvs(true).then(paintPill);
    setInterval(function () { if (!d.hidden) fetchConvs(true).then(paintPill); }, 30000);
  }

  /* ================= command palette ================= */
  var root = null, input = null, list = null, count = null;
  var items = [], sel = 0, built = false, lastFocus = null;

  var ICO = {
    home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    orch: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
    pers: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>',
    extn: '<path d="M10 3.5a2 2 0 1 1 4 0V5h3a1 1 0 0 1 1 1v3h1.5a2 2 0 1 1 0 4H18v3a1 1 0 0 1-1 1h-3v1.5a2 2 0 1 1-4 0V17H7a1 1 0 0 1-1-1v-3H4.5a2 2 0 1 1 0-4H6V6a1 1 0 0 1 1-1h3z"/>',
    arena: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.4"/><line x1="12" y1="1.5" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22.5"/><line x1="1.5" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22.5" y2="12"/>',
    setup: '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    reg: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    thea: '<rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/>',
    gh: '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>'
  };

  function svg(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICO[name] || ICO.chat) + '</svg>';
  }

  var PAGES = [
    { kind: 'Pages', title: 'Home', sub: 'Landing page, live counters, featured debates', url: '/', ico: 'home' },
    { kind: 'Pages', title: 'Conversations', sub: 'Browse every debate transcript', url: '/conversations', ico: 'chat' },
    { kind: 'Pages', title: 'Orchestrate', sub: 'Seed and launch a new debate', url: '/orchestrate', ico: 'orch' },
    { kind: 'Pages', title: 'Personas', sub: 'Manage debater cards and groups', url: '/personas', ico: 'pers' },
    { kind: 'Pages', title: 'Browser extension', sub: 'What AgentBattleground is and how to install it', url: '/extension', ico: 'extn' },
    { kind: 'Pages', title: 'Battleground', sub: 'Captured arenas, drafts, and verdicts', url: '/battleground', ico: 'arena' },
    { kind: 'Pages', title: 'CLI setup', sub: 'Which CLI tools this machine has', url: '/setup', ico: 'setup' },
    { kind: 'Pages', title: 'Persona Registry', sub: 'Download more persona cards', url: LINKS.registry, ico: 'reg', ext: true },
    { kind: 'Pages', title: 'Debate Chat Theater', sub: 'Watch published debates', url: LINKS.theater, ico: 'thea', ext: true },
    { kind: 'Pages', title: 'GitHub repository', sub: 'michaelschecht/Agent-chat', url: LINKS.github, ico: 'gh', ext: true }
  ];

  function initials(name) {
    var parts = String(name || '').split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  function pad(n) { return ('000' + n).slice(-3); }

  function build() {
    if (built) return Promise.resolve(items);
    built = true;
    return Promise.all([fetchConvs(false), fetchPersonas()]).then(function (res) {
      var convs = res[0] || [], personas = res[1] || [];
      items = PAGES.filter(function (p) { return !!p.url; });
      convs.forEach(function (c) {
        var who = Array.isArray(c.participants) ? c.participants.join(' · ') : '';
        items.push({
          kind: 'Conversations',
          title: c.topic || '(untitled)',
          sub: '#' + pad(c.id) + '  ' + (c.status || '') + (who ? '  ' + who : ''),
          url: '/conversations/' + c.id,
          badge: '#' + c.id,
          live: c.status === 'active'
        });
      });
      personas.forEach(function (p) {
        items.push({
          kind: 'Personas',
          title: p.name || p.slug,
          sub: p.group || '',
          url: '/personas?group=' + encodeURIComponent(p.group || '') + '&q=' + encodeURIComponent(p.name || ''),
          badge: initials(p.name || p.slug)
        });
      });
      return items;
    });
  }

  /* Subsequence fuzzy match. Scores contiguous runs and word-start hits so
     "gord" puts "Gordon Ramsay" above "Good Gardening", and shorter titles win
     ties. Returns null when q isn't a subsequence of text at all.

     A bare subsequence test is far too generous on prose: "ramsay" happily
     matched "B-r-ain Computer Interf-a-ces ... neur-a-l ... technolog-y" by
     picking letters out of a whole sentence. So a match must ALSO be dense —
     the letters have to sit close together — unless every hit lands on a word
     start, which is what makes real acronym queries ("bci") still work. */
  var WORD_START = /[\s\-_\/·#:]/;
  function fuzzy(q, text) {
    if (!q) return { score: 0, hits: [] };
    var t = String(text).toLowerCase(), ql = q.toLowerCase();
    var ti = 0, score = 0, run = 0, hits = [], starts = 0;
    for (var i = 0; i < ql.length; i++) {
      var found = -1;
      for (var j = ti; j < t.length; j++) { if (t[j] === ql[i]) { found = j; break; } }
      if (found < 0) return null;
      hits.push(found);
      if (found === ti && i > 0) { run++; score += 6 + run * 3; } else { run = 0; score += 1; }
      if (found === 0 || WORD_START.test(t[found - 1] || '')) { score += 8; starts++; }
      ti = found + 1;
    }
    var spread = hits[hits.length - 1] - hits[0] + 1;
    if (ql.length / spread < 0.3 && starts < ql.length) return null;
    return { score: score - Math.min(t.length * 0.05, 8), hits: hits };
  }

  function hl(text, hits) {
    var set = {}, out = '', i;
    for (i = 0; i < (hits || []).length; i++) set[hits[i]] = 1;
    for (i = 0; i < text.length; i++) out += set[i] ? '<mark>' + esc(text[i]) + '</mark>' : esc(text[i]);
    return out;
  }

  function score(q) {
    var out = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var m = fuzzy(q, it.title);
      var via = 'title';
      if (!m) { m = fuzzy(q, it.sub || ''); via = 'sub'; }
      if (!m) continue;
      out.push({ it: it, s: m.score + (via === 'title' ? 12 : 0), hits: via === 'title' ? m.hits : [] });
    }
    out.sort(function (a, b) { return b.s - a.s; });
    return out.slice(0, 40);
  }

  var rows = [];
  function render() {
    var q = (input.value || '').trim();
    var hits = score(q);
    rows = [];
    if (!hits.length) {
      list.innerHTML = '<li class="cmdk-empty">Nothing matches &ldquo;' + esc(q) + '&rdquo;</li>';
      count.textContent = '';
      return;
    }
    var html = '', group = null, n = 0;
    hits.forEach(function (h) {
      if (h.it.kind !== group) { group = h.it.kind; html += '<li class="cmdk-group">' + esc(group) + '</li>'; }
      var ico = h.it.ico ? svg(h.it.ico) : esc(h.it.badge || '');
      html += '<li class="cmdk-item" role="option" data-i="' + n + '" aria-selected="false">' +
        '<span class="cmdk-ico">' + ico + '</span>' +
        '<span class="cmdk-body"><span class="cmdk-title">' + hl(String(h.it.title), h.hits) +
        (h.it.live ? ' <span class="live-pill" style="margin-left:4px"><span class="dot"></span></span>' : '') +
        '</span>' + (h.it.sub ? '<span class="cmdk-sub">' + esc(h.it.sub) + '</span>' : '') + '</span>' +
        '<span class="cmdk-go">' + (h.it.ext ? '&#8599;' : '&#8629;') + '</span></li>';
      rows.push(h.it);
      n++;
    });
    list.innerHTML = html;
    count.textContent = rows.length + (rows.length === 1 ? ' result' : ' results');
    sel = 0;
    paintSel();
  }

  function paintSel() {
    var els = list.querySelectorAll('.cmdk-item');
    for (var i = 0; i < els.length; i++) {
      var on = i === sel;
      els[i].setAttribute('aria-selected', on ? 'true' : 'false');
      if (on) {
        els[i].scrollIntoView({ block: 'nearest' });
        input.setAttribute('aria-activedescendant', 'cmdk-opt-' + i);
      }
    }
  }

  function go(i) {
    var it = rows[i];
    if (!it) return;
    close();
    if (it.ext) window.open(it.url, '_blank', 'noopener');
    else window.location.href = it.url;
  }

  function open() {
    if (!root.hidden) return;
    lastFocus = d.activeElement;
    root.hidden = false;
    input.value = '';
    list.innerHTML = '<li class="cmdk-empty">Loading&hellip;</li>';
    d.documentElement.style.overflow = 'hidden';
    input.focus();
    build().then(render);
  }
  function close() {
    if (root.hidden) return;
    root.hidden = true;
    d.documentElement.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function initPalette() {
    root = d.getElementById('cmdk');
    if (!root) return;
    input = d.getElementById('cmdk-input');
    list = d.getElementById('cmdk-list');
    count = d.getElementById('cmdk-count');
    if (!input || !list || !count) return;

    // The shortcut is Cmd+K on a Mac and Ctrl+K everywhere else (the handler
    // below accepts either). Render whichever one the reader actually has.
    if (/Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || '')) {
      Array.prototype.forEach.call(d.querySelectorAll('.cmdk-trigger kbd'), function (k) {
        k.textContent = '⌘ K';
      });
      Array.prototype.forEach.call(d.querySelectorAll('[data-cmdk-open]'), function (b) {
        b.setAttribute('aria-label', 'Search (Command K)');
      });
    }

    d.addEventListener('keydown', onKey);
    input.addEventListener('input', render);
    list.addEventListener('click', function (e) {
      var li = e.target.closest && e.target.closest('.cmdk-item');
      if (li) go(parseInt(li.dataset.i, 10));
    });
    list.addEventListener('mousemove', function (e) {
      var li = e.target.closest && e.target.closest('.cmdk-item');
      if (li) { var i = parseInt(li.dataset.i, 10); if (i !== sel) { sel = i; paintSel(); } }
    });
    Array.prototype.forEach.call(d.querySelectorAll('[data-cmdk-open]'), function (b) {
      b.addEventListener('click', open);
    });
    Array.prototype.forEach.call(d.querySelectorAll('[data-cmdk-close]'), function (b) {
      b.addEventListener('click', close);
    });
  }

  function onKey(e) {
    var mod = e.metaKey || e.ctrlKey;
    if (mod && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); root.hidden ? open() : close(); return; }
    if (root.hidden) {
      // Bare "/" opens search too — but not while the operator is typing in
      // the persona search box, the rail filter, or any other field.
      var t = e.target, tag = t && t.tagName;
      if (e.key === '/' && !e.metaKey && !e.ctrlKey && !e.altKey &&
          tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT' && !(t && t.isContentEditable)) {
        e.preventDefault(); open();
      }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); if (rows.length) { sel = (sel + 1) % rows.length; paintSel(); } }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (rows.length) { sel = (sel - 1 + rows.length) % rows.length; paintSel(); } }
    else if (e.key === 'Enter') { e.preventDefault(); go(sel); }
    else if (e.key === 'Tab') { e.preventDefault(); input.focus(); }  // keep focus trapped
  }

  /* ================= scroll reveals ================= */
  function initReveals() {
    var reveals = d.querySelectorAll('.reveal');
    if (!reveals.length) return;
    if (!('IntersectionObserver' in window)) {
      Array.prototype.forEach.call(reveals, function (el) { el.classList.add('seen'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('seen'); io.unobserve(en.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
    Array.prototype.forEach.call(reveals, function (el) { io.observe(el); });
  }

  /* ================= sidebar collapse =================
     The state itself is applied by _BOOT_JS before first paint (so the rail
     can't flash open and snap shut); this only wires the toggle. */
  function initRail() {
    var railToggle = d.getElementById('rail-toggle');
    if (!railToggle) return;
    var html = d.documentElement;
    function syncRail() {
      var collapsed = html.classList.contains('rail-collapsed');
      railToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      railToggle.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
      railToggle.setAttribute('data-tip', 'Expand');
    }
    railToggle.addEventListener('click', function () {
      var collapsed = html.classList.toggle('rail-collapsed');
      try { localStorage.setItem('ab-rail', collapsed ? '0' : '1'); } catch (e) {}
      syncRail();
    });
    syncRail();
  }
})();
</script>
"""


BASE_CSS = (
    DESIGN_TOKENS
    + TOPBAR_CSS
    + """
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.6 'IBM Plex Sans', 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* Reading pages keep margins; only the header is full-bleed, and only the app
   surfaces (/conversations, /personas) run their panes edge-to-edge — they
   zero this out via `main:has(...)` in _CONV_CSS / _PERSONAS_CSS.
   The centred --page column lives on the homepage's `.wrap` (HOME_CSS); the
   shell's own pages already self-cap (.orch-shell at 760px, the 404 centres),
   so there's nothing here to centre. */
main {
  padding: 36px var(--gutter) 72px;
}
.measure { max-width: var(--measure); }
main h2.page-title {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 26px; font-weight: 800;
  letter-spacing: -0.01em;
  margin: 0 0 6px;
  color: var(--text);
}
main p.page-sub {
  color: var(--muted-2);
  margin: 0 0 32px;
  font-size: 14px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; text-decoration-color: var(--accent-strong); }
/* Conversation list table — apex aesthetic: zinc-900/40 panel surface,
   zinc-800/60 dividers, emerald-400 row link, uppercase tracking-wider eyebrow. */
.table-wrap {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--panel);
  overflow: hidden;
}
table { width: 100%; border-collapse: collapse; }
th, td {
  padding: 12px 16px; text-align: left;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
th {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-weight: 500; color: var(--muted-2); font-size: 10.5px;
  text-transform: uppercase; letter-spacing: 0.12em;
  background: rgba(9, 9, 11, 0.5);
}
tr:last-child td { border-bottom: 0; }
tbody tr { transition: background 0.15s ease; }
tbody tr:hover td { background: rgba(24, 24, 27, 0.6); }
td a { color: var(--text); text-decoration: none; font-weight: 500; }
td a:hover { color: var(--accent); }

/* Status pill — emerald for active, muted for complete (apex's 'Live' tile
   convention uses emerald-400). */
.status-active, .status-complete {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 500;
}
.status-active { color: var(--accent); }
.status-active::before {
  content: ''; width: 6px; height: 6px;
  border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 6px var(--accent);
  animation: pulse 1.8s ease-in-out infinite;
}
.status-complete { color: var(--muted-2); }
.status-complete::before {
  content: ''; width: 6px; height: 6px;
  border-radius: 50%; background: var(--muted-2);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  background: rgba(9, 9, 11, 0.6);
  color: var(--muted);
  border: 1px solid var(--border);
  font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
}
.muted { color: var(--muted-2); }
.empty {
  padding: 64px 24px;
  text-align: center;
  color: var(--muted-2);
  border: 1px dashed var(--border);
  border-radius: 4px;
  background: var(--panel);
}
.empty code {
  color: var(--good);
  background: rgba(16, 185, 129, 0.08);
  padding: 2px 8px; border-radius: 3px;
  font-size: 12.5px;
}

/* Meta-grid — definition list of conversation metadata, styled as an
   apex panel (zinc-900/40 + zinc-800/60 border). */
.meta-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 20px;
  margin: 0 0 20px;
  padding: 20px 22px;
  background: var(--panel);
  border-radius: 4px;
  border: 1px solid var(--border);
  font-size: 13px;
}
.meta-grid dt {
  color: var(--muted-2);
  text-transform: uppercase;
  font-size: 10.5px;
  letter-spacing: 0.08em;
  align-self: center;
  font-weight: 500;
}
.meta-grid dd { margin: 0; color: var(--text); }
/* Transcript — column of zinc-900/40 message cards. Sender-colored left rule
   uses emerald for an agent message and `signal=done`, red for
   `signal=blocked`, muted zinc for system messages. */
.transcript { display: flex; flex-direction: column; gap: 14px; }
.msg {
  padding: 16px 20px;
  border-radius: 4px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 2px solid var(--accent);
  transition: border-color 0.15s ease, background 0.15s ease;
}
.msg:hover {
  background: rgba(24, 24, 27, 0.55);
  border-left-color: var(--accent-strong);
}
.msg.sender-system { border-left-color: var(--muted-2); }
.msg.signal-done { border-left-color: var(--good); }
.msg.signal-blocked { border-left-color: var(--bad); }
/* `signal=result` is the conversation's DELIVERABLE — the artifact a
   collaboration was convened to produce, as opposed to the transcript around
   it. Given more weight than the other signals (amber rule, tinted card, a
   heavier left edge) because in a collaboration it is the thing the reader
   actually came for. Both render paths — the server one and the SSE one in
   render/conversations.py — already emit `signal-<value>` generically, so this
   is the whole visual treatment. */
.msg.signal-result {
  border-left-width: 3px;
  border-left-color: var(--warn, #f59e0b);
  background: rgba(245, 158, 11, 0.05);
}
.msg.signal-result:hover { border-left-color: #fbbf24; }
/* A superseded result is a draft a later result replaced. It keeps its place
   in the transcript — collapsing it is about which result the eye lands on,
   not about hiding what was written — but it gives up the amber treatment so
   exactly one message in the run reads as THE deliverable. Last-wins is
   defined once, in orchestrator.export.final_result(). */
.msg.signal-result.signal-superseded {
  border-left-width: 2px;
  border-left-color: var(--border);
  background: transparent;
  opacity: 0.72;
}
.msg.signal-result.signal-superseded:hover { opacity: 1; border-left-color: var(--muted-2); }
.msg-head .signal.superseded {
  background: rgba(9, 9, 11, 0.6);
  border-color: var(--border);
  color: var(--muted-2);
}
.msg-superseded > summary {
  cursor: pointer; color: var(--muted-2); font-size: 12.5px;
  padding: 6px 0; list-style: none; user-select: none;
}
.msg-superseded > summary::-webkit-details-marker { display: none; }
.msg-superseded > summary::before { content: 'B8  '; }
.msg-superseded[open] > summary::before { content: 'BE  '; }
.msg-superseded > summary:hover { color: var(--text); }
.msg-head {
  display: flex; gap: 14px; align-items: baseline;
  font-size: 12px; color: var(--muted-2);
  margin-bottom: 10px;
}
.msg-head .who {
  color: var(--text);
  font-weight: 600;
  font-size: 13px;
  letter-spacing: -0.005em;
}
.msg-head .time {
  font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 11px;
}
.msg-head .signal {
  text-transform: uppercase; font-size: 10px;
  padding: 2px 8px; border-radius: 3px;
  letter-spacing: 0.08em; font-weight: 600;
  background: rgba(9, 9, 11, 0.6);
  border: 1px solid var(--border);
  color: var(--muted);
}
.msg-head .signal.done {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.32);
  color: var(--good);
}
.msg-head .signal.blocked {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.32);
  color: var(--bad);
}
.msg-head .signal.result {
  background: rgba(245, 158, 11, 0.12);
  border-color: rgba(245, 158, 11, 0.32);
  color: var(--warn);
}
.msg-body { word-wrap: break-word; overflow-wrap: anywhere;
            color: #e4e4e7; font-size: 14.5px; line-height: 1.65; }
.msg-body > :first-child { margin-top: 0; }
.msg-body > :last-child { margin-bottom: 0; }
.msg-body p { margin: 0 0 12px; }
.msg-body p:last-child { margin-bottom: 0; }
.msg-body strong { color: var(--text); font-weight: 600; }
.msg-body em { font-style: italic; color: var(--text); }
.msg-body a { color: var(--accent); text-decoration: underline;
              text-decoration-color: rgba(16, 185, 129, 0.4);
              text-underline-offset: 2px; }
.msg-body a:hover { text-decoration-color: var(--accent); }
.msg-body ul, .msg-body ol { margin: 8px 0 12px; padding-left: 26px; }
.msg-body li { margin: 3px 0; }
.msg-body li > p { margin: 0; }
.msg-body blockquote {
  margin: 10px 0; padding: 6px 16px;
  border-left: 2px solid var(--border-strong);
  color: var(--muted);
  background: rgba(9, 9, 11, 0.4);
}
.msg-body code {
  font: 13px/1.5 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
  background: rgba(9, 9, 11, 0.6);
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--border);
  color: #f4f4f5;
}
.msg-body pre {
  margin: 10px 0; padding: 14px 16px;
  background: #09090b;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow-x: auto;
}
.msg-body pre code {
  background: transparent; border: 0; padding: 0;
  font-size: 12.5px;
}
.msg-body h1, .msg-body h2, .msg-body h3,
.msg-body h4, .msg-body h5, .msg-body h6 {
  margin: 16px 0 8px; font-weight: 600; color: var(--text);
  letter-spacing: -0.01em;
}
.msg-body h1 { font-size: 19px; }
.msg-body h2 { font-size: 17px; }
.msg-body h3 { font-size: 15px; }
.msg-body h4, .msg-body h5, .msg-body h6 { font-size: 14px; }
.msg-body table {
  border-collapse: collapse; margin: 10px 0;
  font-size: 13px;
  border: 1px solid var(--border);
}
.msg-body th, .msg-body td {
  border: 1px solid var(--border);
  padding: 6px 12px;
  text-align: left;
}
.msg-body th {
  background: rgba(9, 9, 11, 0.5);
  color: var(--muted);
  font-weight: 500;
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.06em;
}
.msg-body hr { border: 0; border-top: 1px solid var(--border); margin: 14px 0; }
.msg-body del { color: var(--muted-2); }

/* Live indicator — emerald-400 pulse for active, muted dot for ended.
   The 'stopped' class swap is set by the SSE 'complete' handler. */
.live-indicator {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 11.5px; color: var(--accent);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 500;
}
.live-indicator .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent);
  animation: pulse 1.8s ease-in-out infinite;
}
.live-indicator.stopped { color: var(--muted-2); }
.live-indicator.stopped .dot {
  background: var(--muted-2);
  box-shadow: none;
  animation: none;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

/* "Next: launch each CLI" panel on fresh conversations (status=active
   + 0 messages). Disappears once the first SSE message lands. Subtle
   emerald tint so it reads as a guide, not an alert. */
.next-steps {
  margin: 20px 0;
  padding: 20px 22px;
  background: rgba(16, 185, 129, 0.04);
  border: 1px solid rgba(16, 185, 129, 0.25);
  border-radius: 8px;
}
.next-steps h3 {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
}
.next-steps p { margin: 0 0 14px 0; color: var(--muted); }
.next-steps p:last-child { margin-bottom: 0; }
.next-steps .ns-hint { font-size: 12px; color: var(--muted-2); margin-top: 16px; }
.ns-list {
  list-style: none;
  margin: 0 0 4px 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ns-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(24, 24, 27, 0.5);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.ns-agent {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 13px;
  color: var(--text);
}
.ns-first {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--accent);
  background: rgba(16, 185, 129, 0.12);
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.ns-spacer { flex: 1 1 auto; }

/* Page header row — title on the left, primary CTA on the right.
   Used on /conversations and any future list view that gets a "new"
   action. Wraps gracefully on narrow viewports. */
.page-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.page-header-row > div { flex: 1 1 auto; min-width: 0; }
.page-header-row .btn { flex: 0 0 auto; }

/* Buttons — apex CTA family. Default = ghost (zinc border, paper text).
   .btn-primary = emerald solid. .btn-danger = red outline that inverts. */
.btn {
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  padding: 7px 14px;
  border-radius: 4px;
  border: 1px solid rgba(63, 63, 70, 0.7);
  background: transparent;
  color: var(--text);
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  text-decoration: none;
  transition: all 0.15s ease;
}
.btn:hover {
  background: rgba(24, 24, 27, 0.7);
  border-color: var(--border-strong);
  text-decoration: none;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary {
  background: var(--good);
  color: #09090b;
  border-color: var(--good);
  font-weight: 600;
}
.btn-primary:hover {
  background: transparent;
  color: var(--good);
  box-shadow: inset 0 0 0 1px var(--good);
}
.btn-danger {
  border-color: rgba(239, 68, 68, 0.5);
  color: var(--bad);
  background: rgba(239, 68, 68, 0.06);
}
.btn-danger:hover {
  background: var(--bad);
  color: #09090b;
  border-color: var(--bad);
}
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.detail-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; gap: 16px; flex-wrap: wrap;
}
.detail-head h2 {
  margin: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 21px;
  font-weight: 800;
  letter-spacing: -0.01em;
  color: var(--text);
}
"""
)


# ---------------------------------------------------------------------------
# Homepage CSS — apex-aligned. Mirrors mikesailab.com: #060606 canvas,
# Inter font, zinc-100 text, emerald-400 'Live' pills, emerald-500 accents on
# hover and CTAs. Tailwind utility classes drive most layout via the CDN
# <script> in <head>; this stylesheet only carries rules Tailwind can't
# express ergonomically (the code-block tints and the home-only `.live-tile`
# SVG glyph hover transitions).
#
# Composes the same DESIGN_TOKENS + TOPBAR_CSS as BASE_CSS: the homepage does
# not load BASE_CSS, and before this it carried a hand-copied duplicate of the
# nav-button rules that could (and did) drift out of sync with the shell.
# ---------------------------------------------------------------------------

HOME_CSS = (
    DESIGN_TOKENS
    + TOPBAR_CSS
    + """
body.home { font-family: 'IBM Plex Sans', 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif; }
/* Anchor targets clear the sticky topbar (and the demo strip when it's there).
   Without this, /#resources from another page parks the section heading
   underneath the bar. Pairs with the re-scroll in the homepage template: this
   fixes the offset, that one fixes the Tailwind-CDN reflow. */
body.home section[id] { scroll-margin-top: calc(var(--topbar-h) + 16px); }
body.home:has(.demo-strip) section[id] {
  scroll-margin-top: calc(var(--topbar-h) + var(--demo-h) + 16px);
}
/* Section container — a centred --page (1400px) column, so the landing page
   keeps margins. Replaces Tailwind's `max-w-6xl mx-auto px-6`: same idea,
   but the width is a token shared with the rest of the app, and `.wrap`
   centres within the space *beside* the fixed rail (its containing block is
   <main>, which is already inset by --rail-w) rather than in the viewport.
   The header is the only full-bleed surface. */
.wrap {
  width: 100%;
  max-width: var(--page);
  margin-inline: auto;
  padding-left: var(--gutter);
  padding-right: var(--gutter);
}
.measure { max-width: var(--measure); }
/* Grid and flex items default to `min-width:auto`, which means a track can
   never size below its content's min-content — so a single nowrap string deep
   inside (the turn-engine card's "claude-code → codex → antigravity" status
   line) sized the whole track to 344px and scrolled the page sideways on a
   phone. `min-w-0` on the *inner* span isn't enough: that only lifts the
   auto-minimum during flexing, while the track's intrinsic sizing still asks
   the span for its min-content, which is nowrap = the full string. The floor
   has to lift on the item that owns the track. Then .truncate does its job. */
.wrap .grid > *, .wrap .flex > * { min-width: 0; }
/* Editorial-Modern: headlines are tight sans (not mono). The brand wordmark
   keeps JetBrains Mono via .mark-txt; .mono is the IBM Plex Mono helper used
   for stat numerals, code chips, and the featured-debate meta. */
body.home h1, body.home h2, body.home h3 { font-family: 'IBM Plex Sans', system-ui, sans-serif; letter-spacing: -0.025em; }
body.home .mark-txt { font-family: 'JetBrains Mono', ui-monospace, monospace; letter-spacing: -0.01em; }
body.home .mono { font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace; }
/* Subtle emerald wash behind the hero — depth without clutter. */
.hero-wash { position: relative; }
.hero-wash::before {
  content: ''; position: absolute; inset: -25% 0 auto 0; height: 720px; z-index: 0;
  background: radial-gradient(50% 55% at 78% 4%, rgba(16,185,129,0.12), transparent 70%);
  pointer-events: none;
}
summary::-webkit-details-marker { display: none; }
summary { list-style: none; }

/* Live-tile SVG glyph — fades in from corner, brightens on hover.
   Mirrors apex's per-tile decorative line-art convention. */
.live-tile .glyph { transition: color 0.2s ease, opacity 0.2s ease; }

/* Code blocks inside the how-it-works steps — emerald accent rule on
   the left, monospace, zinc-100 text on near-black. */
.step-code {
  background: #09090b;
  border: 1px solid rgba(39, 39, 42, 0.6);
  border-left: 2px solid #10b981;
  border-radius: 4px;
  padding: 14px 16px;
  overflow-x: auto;
  font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: #e4e4e7;
  margin: 0;
}
.step-code .cmt { color: #71717a; }
.step-code .em  { color: #10b981; }
.step-code-inline {
  font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 13px;
  color: #10b981;
  background: rgba(16, 185, 129, 0.08);
  padding: 1px 6px;
  border-radius: 3px;
}

/* Latest list — apex tile-row hover (slide-in + emerald-tinted bg). */
.latest-row {
  display: grid;
  grid-template-columns: 70px minmax(0, 2.4fr) minmax(0, 1fr) 110px;
  gap: 20px;
  align-items: center;
  padding: 16px 6px;
  border-top: 1px solid rgba(39, 39, 42, 0.6);
  text-decoration: none;
  color: #f4f4f5;
  transition: padding-left 0.18s ease, background 0.18s ease;
}
.latest-row:last-child { border-bottom: 1px solid rgba(39, 39, 42, 0.6); }
.latest-row:hover {
  padding-left: 16px;
  background: linear-gradient(90deg, rgba(16,185,129,0.08), transparent 75%);
}
.latest-row .lid {
  font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 12px; color: #71717a;
}
.latest-row .ltopic {
  font-weight: 500; font-size: 15px; color: #f4f4f5;
  letter-spacing: -0.005em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.latest-row .lparts {
  font-family: 'IBM Plex Mono', ui-monospace, "Cascadia Mono", "Consolas", monospace;
  font-size: 11.5px; color: #a1a1aa;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.latest-row .lstatus {
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.1em; text-align: right;
  display: inline-flex; align-items: center; gap: 6px;
  justify-content: flex-end;
}
.latest-row .lstatus::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
}
.latest-row .lstatus.active { color: #10b981; }
.latest-row .lstatus.active::before {
  background: #10b981; box-shadow: 0 0 6px #10b981;
}
.latest-row .lstatus.complete { color: #71717a; }
.latest-row .lstatus.complete::before { background: #71717a; }

@media (max-width: 700px) {
  .latest-row {
    grid-template-columns: 50px 1fr 90px;
    gap: 14px;
  }
  .latest-row .lparts { display: none; }
}

/* ---- page-load reveal ---------------------------------------------------
   One orchestrated entrance beats a dozen scattered micro-interactions: the
   hero's children rise in sequence, then it never runs again. Sections below
   the fold reveal on scroll instead (see REVEAL_JS) so the page feels alive
   under the thumb without animating things nobody has scrolled to yet.
   Both collapse to instant via the reduced-motion block in TOPBAR_CSS. */
.rise > * { animation: rise-in 0.62s cubic-bezier(0.16, 1, 0.3, 1) backwards; }
.rise > *:nth-child(1) { animation-delay: 0.02s; }
.rise > *:nth-child(2) { animation-delay: 0.08s; }
.rise > *:nth-child(3) { animation-delay: 0.14s; }
.rise > *:nth-child(4) { animation-delay: 0.20s; }
.rise > *:nth-child(5) { animation-delay: 0.26s; }
.rise > *:nth-child(6) { animation-delay: 0.32s; }
.rise > *:nth-child(7) { animation-delay: 0.38s; }
@keyframes rise-in {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: none; }
}
/* Scoped to html.js — set by _BOOT_JS before first paint. Content must never
   depend on JS to be *visible*: hiding it up front and un-hiding it from a
   script means any script failure silently blanks the page. (It did: the
   reveal init ran before <main> was parsed, so six homepage sections sat at
   opacity:0 forever. Now the worst case is no animation.) */
html.js .reveal {
  opacity: 0; transform: translateY(18px);
  transition: opacity 0.6s ease, transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
html.js .reveal.seen { opacity: 1; transform: none; }
@media (prefers-reduced-motion: reduce) {
  html.js .reveal { opacity: 1; transform: none; }
}
"""
)


# Styles for the /orchestrate route. Lives inside the _layout shell, so
# tokens from BASE_CSS (--bg, --text, --accent, --border, --good, --bad)
# are available without redeclaration. Scoped under `.orch-shell` so the
# form rules cannot leak into the conversations index / detail pages.
ORCHESTRATE_CSS = """
.orch-shell { max-width: 780px; margin: 32px auto; padding: 0 24px 128px; }
.orch-head h2 {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 26px; font-weight: 800; letter-spacing: -0.01em;
  margin: 0 0 8px 0;
}
.orch-head p { color: var(--muted); margin: 0 0 8px 0; max-width: 68ch; }
.orch-head h2 + * { margin-top: 14px; }

/* Same mechanic as the sub-type cards' "?": a floating tooltip, not a
   disclosure. Absolutely positioned, so revealing it reflows nothing;
   visibility rather than display so it can fade; pointer-events off so it
   never eats a click meant for what is underneath. It hangs BELOW its button
   because this one lives at the top of the page. */
.orch-head-tip { position: relative; display: inline-block; vertical-align: middle; }
.orch-head-help {
  width: 21px; height: 21px; padding: 0; margin-left: 4px;
  display: inline-flex; align-items: center; justify-content: center;
  font: 600 12px/1 ui-sans-serif, system-ui, sans-serif;
  border: 1px solid var(--border-strong); border-radius: 50%;
  background: transparent; color: var(--muted); cursor: help;
  transition: color .12s, border-color .12s, background .12s;
}
.orch-head-help:hover, .orch-head-help:focus-visible {
  color: var(--accent); border-color: var(--accent);
  background: rgba(16, 185, 129, 0.12);
}
.orch-head-detail {
  position: absolute; left: -8px; top: 30px; z-index: 40;
  width: max-content; max-width: min(46ch, calc(100vw - 48px));
  padding: 12px 14px; border-radius: 8px;
  border: 1px solid var(--border-strong); background: var(--panel-solid);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.6);
  /* Every one of these resets an <h2> property, because the tooltip lives
     inside the heading. `font: ... inherit` is NOT valid shorthand — a family
     of `inherit` voids the whole declaration, and the panel rendered at 26px
     mono 800. Longhand only here. */
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 12.5px; font-weight: 400; line-height: 1.6; letter-spacing: 0;
  color: var(--muted); text-align: left; text-transform: none; white-space: normal;
  opacity: 0; visibility: hidden; pointer-events: none;
  transition: opacity .12s ease, visibility .12s;
}
.orch-head-help:hover ~ .orch-head-detail,
.orch-head-help:focus-visible ~ .orch-head-detail { opacity: 1; visibility: visible; }
.orch-head-detail strong { color: var(--text); font-weight: 600; }
.orch-head-detail code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11.5px; color: var(--muted-2);
}

/* Sections are the page's landmarks. The gap between them has to beat the gap
   inside one by enough to read as separation at a glance — 22 vs 8 did not,
   which is why the form scanned as one undifferentiated column of gray. */
.orch-form { display: flex; flex-direction: column; gap: 30px; }
.orch-form section { display: flex; flex-direction: column; gap: 10px; }

/* The section head is a ruled anchor row: label left, a marker right, a
   hairline running out to the edge. Scrolling past one is now visible. */
.orch-form .lbl {
  display: flex; align-items: center; gap: 12px;
  font-size: 12.5px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--text); font-weight: 650;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.orch-form .lbl::after {
  content: ""; flex: 1; height: 1px; min-width: 16px;
  background: linear-gradient(90deg, var(--border-strong), transparent);
}
/* The right-hand marker — "(min 2)", "(optional)", a live count. Sits after
   the rule so it pins to the right edge; one treatment for all three, where
   there used to be three inline `style=` attributes saying the same thing. */
.orch-form .lbl .mark {
  order: 3; flex: none;
  font-family: var(--font-sans, inherit);
  font-size: 11.5px; letter-spacing: 0.02em; text-transform: none;
  font-weight: 500; font-style: normal; color: var(--muted);
}
.orch-form .lbl .mark.is-live { color: var(--accent); }

/* zinc-500 on this background is ~4.0:1 — under the floor, and it was the
   colour of every explanatory paragraph on the page. zinc-400 is ~7.8:1.
   Measure capped: these ran the full 712px column at 12px, ~95ch. */
.orch-form .hint {
  color: var(--muted); font-size: 12.5px; line-height: 1.55;
  margin: 0; max-width: 68ch;
}
.orch-form .hint code { color: var(--muted-2); }

.orch-form input[type=text],
.orch-form input[type=number],
.orch-form select,
.orch-form textarea {
  background: #09090b;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  font: inherit;
  width: 100%;
}
.orch-form input[type=text]:focus,
.orch-form input[type=number]:focus,
.orch-form select:focus,
.orch-form textarea:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15);
}
.orch-form textarea { resize: vertical; min-height: 60px; }

.orch-clis { display: flex; flex-direction: column; gap: 6px; }
.orch-cli {
  display: grid;
  grid-template-columns: 24px 160px 1fr;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: rgba(24, 24, 27, 0.4);
  cursor: pointer;
}
.orch-cli:hover { border-color: var(--border-strong); }
.orch-cli input[type=checkbox] { width: 16px; height: 16px; accent-color: var(--accent); }
.orch-cli .cli-name { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 13px; }
.orch-cli .cli-status {
  font-size: 12px;
  color: var(--muted-2);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.orch-cli .cli-status.ok { color: var(--good); }
.orch-cli .cli-status.fail { color: var(--bad); }

.orch-form .row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
.orch-form .row label { display: flex; flex-direction: column; gap: 6px; }

/* The launch control used to sit at the natural end of the form — three
   viewports below the fold, with nothing on screen saying what was about to
   run. It rides along now, and carries a live readout of the decision it is
   about to commit, which is the one piece of state this form never showed. */
.orch-actions {
  position: sticky; bottom: 0; z-index: 5;
  margin: 34px -24px 0; padding: 14px 24px calc(14px + env(safe-area-inset-bottom));
  display: flex; align-items: center; gap: 16px;
  background: linear-gradient(180deg, rgba(6, 6, 6, 0.72), var(--bg) 55%);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
  border-top: 1px solid var(--border);
}
/* Narrow: the recap takes the full row and the button drops under it, rather
   than the two squeezing each other. The button never shrinks. */
@media (max-width: 560px) {
  .orch-actions { flex-wrap: wrap; gap: 10px; }
  .orch-recap { flex-basis: 100%; }
  .orch-submit { width: 100%; }
}
.orch-recap {
  flex: 1; min-width: 12ch;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; line-height: 1.4; color: var(--muted);
}
.orch-recap b { color: var(--text); font-weight: 600; }
.orch-recap .sep { color: var(--border-strong); margin: 0 7px; }

.orch-submit {
  flex: none;
  padding: 12px 22px;
  background: var(--accent);
  color: #09090b;
  border: none;
  border-radius: 8px;
  font-weight: 650;
  font-size: 14px;
  cursor: pointer;
  letter-spacing: -0.005em;
  box-shadow: 0 6px 18px -8px rgba(16, 185, 129, 0.75);
  transition: background 140ms cubic-bezier(0.22, 1, 0.36, 1),
              box-shadow 140ms cubic-bezier(0.22, 1, 0.36, 1);
}
.orch-submit:hover { background: var(--accent-strong);
  box-shadow: 0 10px 24px -8px rgba(16, 185, 129, 0.85); }
.orch-submit:disabled { opacity: 0.5; cursor: not-allowed; box-shadow: none; }

/* Everything below this line is tuning with a working default. Saying so lets
   the eye stop at the end of the required path instead of reading all nine
   sections as equally load-bearing. */
.orch-fold {
  display: flex; align-items: center; gap: 12px;
  margin: 8px 0 -6px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11.5px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--muted);
}
.orch-fold::before, .orch-fold::after {
  content: ""; height: 1px; background: var(--border); flex: 1;
}

/* Browser surfaces the page never drew but still ships: selection, caret,
   scrollbar, focus ring. Left at their defaults they belong to no design
   system at all. */
.orch-shell ::selection { background: rgba(16, 185, 129, 0.28); color: var(--text); }
.orch-form textarea, .orch-form input { caret-color: var(--accent); }
.orch-form textarea { scrollbar-width: thin; scrollbar-color: var(--border-strong) transparent; }
.orch-form textarea::-webkit-scrollbar { width: 10px; }
.orch-form textarea::-webkit-scrollbar-thumb {
  background: var(--border-strong); border-radius: 99px;
  border: 3px solid transparent; background-clip: content-box;
}
.orch-form textarea::-webkit-scrollbar-track { background: transparent; }
.orch-form :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

.orch-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.5);
  border-radius: 6px;
  padding: 14px 16px;
  color: #fca5a5;
}
.orch-error h4 { margin: 0 0 8px 0; color: #fecaca; font-size: 14px; }
.orch-error ul { margin: 0; padding-left: 18px; }
.orch-error li { margin-bottom: 4px; font-size: 13px; line-height: 1.5; }
.orch-error .code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.15);
  padding: 1px 6px;
  border-radius: 3px;
  margin-right: 6px;
}
.orch-error.hidden { display: none; }

.orch-preflight {
  background: rgba(24, 24, 27, 0.4);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px 16px;
  font-size: 13px;
  color: var(--muted);
}
.orch-preflight h4 { margin: 0 0 6px 0; color: var(--text); font-size: 13px; }
.orch-preflight code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  color: var(--muted-2);
}
"""


# "Panel" — a host flanked by two guests, the taller centre figure holding
# the question. Chosen 2026-08-13 to replace the emerald "A" letterform,
# which said the app's name rather than what the app does. Three figures
# cover both conversation types (a debate and a moderated podcast) where a
# two-agent mark would only cover one.
#
# 256x256 viewBox, rx=56. Near-black plate (#0b0b0e) so the emerald reads as
# the figures rather than the ground — the inverse of the old icon, and of
# the sister apps on mikesailab.com (edge-spectrum, prompts), which still use
# an emerald plate with a dark glyph. Emerald (#10b981) remains the in-app
# accent on every page (the 2026-06-29 retheme unified the app on emerald +
# JetBrains Mono / IBM Plex); the speech bubble uses emerald-300 (#6ee7b7) to
# separate it from the figures below it.
#
# An emerald ring runs the full edge of the plate (added 2026-08-13). The
# near-black plate is darker than most browsers' dark tab strips, so without
# it the icon dissolved into the chrome and only the figures read; the ring
# gives the mark its own silhouette on any dark ground. It is drawn as a
# stroked rect inset by half its own width, so the stroke's OUTER edge lands
# exactly on the plate edge and nothing is clipped. The figures are scaled to
# 0.86 about the centre to clear it — at 16x16 an unscaled bubble would touch
# the ring and read as one smear.
#
# The source of truth for this artwork is
# images/AgentChat-Images/icons/dark/favicon-agents-06-panel-dark.svg —
# edit both together. Built from rounded rects and circles only, so it
# survives being rasterised into a 16x16 browser tab.
#
# ``_MARK_ART`` is the artwork alone (no <svg> wrapper), so the tab icon
# (``FAVICON_SVG``, served at /favicon.svg) and the topbar mark
# (``MARK_SVG``, inlined into every page's left corner) cannot drift apart.
_MARK_ART = (
    "<rect width='256' height='256' rx='56' fill='#0b0b0e'/>"
    "<rect x='7' y='7' width='242' height='242' rx='49' fill='none'"
    " stroke='#10b981' stroke-width='14'/>"
    "<g transform='translate(128 128) scale(0.86) translate(-128 -128)'>"
    "<rect x='88' y='16' width='80' height='44' rx='18' fill='#6ee7b7'/>"
    "<path d='M118 60 L128 74 L138 60 Z' fill='#6ee7b7'/>"
    "<g fill='#0b0b0e'>"
    "<circle cx='108' cy='38' r='6'/><circle cx='128' cy='38' r='6'/>"
    "<circle cx='148' cy='38' r='6'/>"
    "</g>"
    "<rect x='16' y='110' width='66' height='80' rx='24' fill='#10b981'/>"
    "<rect x='95' y='86' width='66' height='104' rx='24' fill='#10b981'/>"
    "<rect x='174' y='110' width='66' height='80' rx='24' fill='#10b981'/>"
    "<g fill='#0b0b0e'>"
    "<circle cx='49' cy='144' r='11'/><circle cx='128' cy='126' r='11'/>"
    "<circle cx='207' cy='144' r='11'/>"
    "</g>"
    "</g>"
)

FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 256 256'>"
    f"{_MARK_ART}"
    "</svg>"
).encode("utf-8")

# The same mark, inlined into the topbar by ``render.common._topbar``. No
# xmlns (it's inline HTML, not a standalone document) and no explicit size —
# ``.topbar .mark .glyph svg`` in TOPBAR_CSS sizes it.
MARK_SVG = f'<svg viewBox="0 0 256 256" aria-hidden="true">{_MARK_ART}</svg>'

# highlight.js CDN bundle for the conversation transcript page. Code-block
# fences emitted by markdown-it-py carry `class="language-<lang>"` so
# highlight.js uses the language hint directly (auto-detects on unhinted
# fences). `github-dark` matches the BASE_CSS dark palette closely enough
# that the existing `pre` box styling stays usable; we override
# `.hljs { background: transparent }` so the surrounding pre's background
# wins. Single integrity-checked CDN load — no Python deps added.
HIGHLIGHT_JS_HEAD = """\
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/styles/github-dark.min.css" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/highlight.min.js"></script>
<style>
  /* hljs ships its own background (#0d1117). Strip it so the BASE_CSS
     <pre> wrapper (#09090b + zinc-800/60 border) shows through. */
  .msg-body pre code.hljs { background: transparent; padding: 0; }
</style>"""


# Styling for the conversation-page Cast panel + the per-message persona label.
_CAST_CSS = """\
<style>
  /* The shared reader panel: Topic, Cast and Conversation all use this box +
     its uppercase label, so the three read as one consistent stack. */
  .cv-box { margin: 0 0 1.25rem; padding: 1rem 1.15rem; border: 1px solid var(--border, #27272a);
            border-radius: 10px; background: rgba(255,255,255,0.015); }
  .cv-box-label { margin: 0 0 0.7rem; font-size: 13px; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 0.08em; color: var(--muted, #a1a1aa); }
  /* ---- Conversation header --------------------------------------------
     Topic, then its facts on one line, then the Cast full-width beneath.
     One column the whole way down — the transcript, the cast and the topic
     all share the reader's width, so nothing reads as a sidebar. */
  .cv-h1 { margin: 0; font-size: 27px; line-height: 1.22; font-weight: 650;
           letter-spacing: -0.02em; color: var(--cv-paper, #e7eaee); }
  .cv-facts { display: flex; align-items: center; flex-wrap: wrap;
              gap: 4px 9px; margin-top: 14px; }
  .cv-type { font: 600 10px/1 'IBM Plex Mono', ui-monospace, monospace;
             letter-spacing: 0.12em; text-transform: uppercase; color: #10b981;
             background: rgba(16,185,129,0.10); border: 1px solid rgba(16,185,129,0.28);
             border-radius: 999px; padding: 4px 9px; }
  .cv-factline { font: 400 12px/1.7 'IBM Plex Mono', ui-monospace, monospace;
                 color: var(--cv-ash, #71717a); }
  .cv-factsep { color: #3f4147; }
  /* Run configuration — read rarely, so it collapses. Sits at the end of the
     facts line; the panel it opens breaks to its own row (flex-basis:100%). */
  .cv-details { margin-left: 4px; }
  .cv-details[open] { flex-basis: 100%; margin-left: 0; }
  .cv-details > summary { display: inline-flex; align-items: center; gap: 5px;
      cursor: pointer; list-style: none; font-size: 12px; color: #6b7280;
      text-decoration: underline; text-underline-offset: 3px; }
  .cv-details > summary::-webkit-details-marker { display: none; }
  .cv-details > summary:hover { color: var(--cv-bone, #c8ccd1); }
  .cv-dlist { margin: 11px 0 0; padding: 11px 13px; border: 1px solid var(--cv-line, #27272a);
              border-radius: 9px; background: rgba(255,255,255,0.02);
              display: flex; flex-direction: column; gap: 7px; }
  .cv-drow { display: flex; gap: 12px; align-items: baseline;
             font: 400 11.5px/1.5 'IBM Plex Mono', ui-monospace, monospace; }
  .cv-drow dt { flex: 0 0 88px; color: #6b7280; }
  .cv-drow dd { margin: 0; color: var(--cv-bone, #c8ccd1); overflow-wrap: anywhere; }

  /* ---- Cast panel (full width, under the topic) ------------------------ */
  .cv-cast { border: 1px solid var(--cv-line, #27272a); border-radius: 12px;
             padding: 12px 14px; background: rgba(255,255,255,0.02);
             margin: 22px 0 1.25rem; }
  .cv-cast-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px;
                  padding: 0 6px; }
  .cv-cast-label { font: 600 10px/1 'IBM Plex Mono', ui-monospace, monospace;
                   letter-spacing: 0.14em; text-transform: uppercase; color: #6b7280; }
  .cv-cast-hint { font-size: 11px; color: #52555c; }
  .cast-list { list-style: none; margin: 0; padding: 0; }
  .cast-item + .cast-item { border-top: 1px solid rgba(255,255,255,0.05); }
  .cast-item summary, .cast-missing { cursor: pointer; padding: 10px 6px; display: flex;
                       align-items: center; gap: 11px; list-style: none; border-radius: 8px; }
  .cast-item summary::-webkit-details-marker { display: none; }
  .cast-item summary:hover { background: rgba(255,255,255,0.04); }
  .cast-item details[open] summary { background: rgba(255,255,255,0.03); }
  .cast-item details[open] .cast-chev { transform: rotate(90deg); }
  .cast-missing { cursor: default; }
  .cast-avatar { flex: 0 0 28px; width: 28px; height: 28px; border-radius: 8px;
                 display: inline-grid; place-items: center;
                 font: 700 10px/1 'IBM Plex Mono', ui-monospace, monospace;
                 color: #06110f;
                 background: linear-gradient(135deg, var(--cv-ink), var(--cv-ink-2));
                 box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18); }
  /* The persona is the subject of the row. Which CLI played it is a footnote,
     so it rides in the right-hand tail with the count rather than sitting in a
     loud chip before the name. min-width:0 lets a long name ellipsis instead
     of shoving the tail off the row. */
  .cast-name { font-size: 14px; font-weight: 600; color: #e9e9ec; min-width: 0;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cast-tail { margin-left: auto; display: flex; align-items: center; gap: 14px;
               flex: 0 0 auto; }
  .cast-cli { font: 400 11px/1 'IBM Plex Mono', ui-monospace, monospace; color: #5f6470;
              white-space: nowrap; }
  /* Marks a Cast row that fell back to the CLI's built-in AI-Models card
     because the conversation recorded no persona for that agent. */
  .cast-model { font: 600 9px/1 'IBM Plex Mono', ui-monospace, monospace;
                text-transform: uppercase; letter-spacing: 0.06em; color: #a1a1aa;
                border: 1px solid var(--cv-line, #27272a); border-radius: 999px;
                padding: 2px 6px; white-space: nowrap; }
  /* Seat label — which chair this agent sat in (Host / Guest / Moderator /
     Debater). The lead seat gets the accent so the person running the room
     reads at a glance. */
  .cast-role { font: 600 9px/1 'IBM Plex Mono', ui-monospace, monospace;
               text-transform: uppercase; letter-spacing: 0.08em; color: #8b8f96;
               white-space: nowrap; }
  .cast-role.is-lead { color: #10b981; }
  .cast-count { font: 400 11px/1 'IBM Plex Mono', ui-monospace, monospace;
                color: #6b7280; flex: 0 0 auto; min-width: 46px; text-align: right; }
  .cast-chev { flex: 0 0 auto; display: inline-flex; color: #3f4147;
               transition: transform .15s ease; }
  .cast-chev svg { width: 13px; height: 13px; }
  /* Persona cards run ~5KB. Full width they read fine, but an open card would
     still push the transcript most of a screen down, so cap it and let it
     scroll — the row stays where you clicked it. */
  .cast-card { padding: 6px 10px 12px; margin-top: 2px;
               border-top: 1px solid var(--cv-line, #27272a);
               font-size: 13px; line-height: 1.65; color: var(--muted, #a1a1aa);
               max-height: 380px; overflow-y: auto; overscroll-behavior: contain; }
  .cast-card h1, .cast-card h2, .cast-card h3 { font-size: 13px; margin: 12px 0 4px;
               color: #d4d4d8; }
  .cast-card p, .cast-card li { margin: 6px 0; }
  .cast-card > :first-child { margin-top: 0; }
  .who-cli { font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted, #a1a1aa);
             font-weight: 400; opacity: 0.8; }
</style>"""

# Two-pane conversations console: left rail (search + filters + sort + list)
# and a main transcript-reader pane. Emerald-accented, scoped to `.cv2` so it
# zeroes `_layout`'s <main> padding (panes run edge-to-edge below the topbar,
# beside the nav rail). Clicking a conversation loads its transcript in the main
# pane — no intermediate preview. The rail collapses (localStorage-persisted);
# `?fullscreen=1` drops the rail entirely for a distraction-free reader.
_CONV_CSS = """\
<style>
/* App surface: panes run edge-to-edge, so zero <main>'s padding — but keep
   the --rail-w inset, or the pane slides under the fixed sidebar. */
main:has(.cv2) { max-width:none; padding:0; margin:0 0 0 var(--rail-w); }
.cv2 {
  --em:#10b981; --em-soft:rgba(16,185,129,0.10); --em-line:rgba(16,185,129,0.34);
  --cv-line:rgba(255,255,255,0.07); --cv-ash:#71717a; --cv-bone:#c8ccd1; --cv-paper:#e7eaee;
  height:calc(100dvh - var(--topbar-h));
  display:grid; grid-template-columns:var(--cv-rail-w, 320px) minmax(0,1fr);
  background:#07090a;
}
/* While dragging the rail resizer: kill selection + pointer noise, freeze the
   width transition so the pane tracks the cursor 1:1. */
.cv2.cv-resizing { cursor:col-resize; }
.cv2.cv-resizing, .cv2.cv-resizing * { user-select:none !important; }
.cv2.cv-resizing .cv-main { pointer-events:none; }
.cv2 *, .cv2 *::before, .cv2 *::after { box-sizing:border-box; }
/* ---- scrollbars: blended into the dark canvas ---- */
.cv-list, .cv-main { scrollbar-width:thin; scrollbar-color:rgba(255,255,255,0.14) transparent; }
.cv2 ::-webkit-scrollbar { width:10px; height:10px; }
.cv2 ::-webkit-scrollbar-track { background:transparent; }
.cv2 ::-webkit-scrollbar-thumb { background:rgba(255,255,255,0.08); border-radius:8px; border:2px solid transparent; background-clip:content-box; }
.cv2 ::-webkit-scrollbar-thumb:hover { background:rgba(255,255,255,0.18); background-clip:content-box; }
.cv2 ::-webkit-scrollbar-corner { background:transparent; }
/* ---- shared chrome ---- */
.cv2 .icon-btn { display:inline-grid; place-items:center; width:30px; height:30px; padding:0;
  border:1px solid var(--cv-line); border-radius:7px; background:transparent; color:var(--cv-ash);
  cursor:pointer; transition:background .12s ease,color .12s ease; text-decoration:none; }
.cv2 .icon-btn:hover { background:rgba(255,255,255,0.05); color:var(--cv-paper); text-decoration:none; }
.cv2 .icon-btn svg { width:15px; height:15px; }
.cv2 .icon-btn.btn-disabled { opacity:0.3; cursor:default; pointer-events:none; }
.cv2 .icon-btn-danger { display:inline-grid; place-items:center; width:30px; height:30px; padding:0;
  border:0; border-radius:7px; background:#ef4444; color:#fff;
  cursor:pointer; transition:background .12s ease; text-decoration:none; }
.cv2 .icon-btn-danger:hover { background:#dc2626; color:#fff; text-decoration:none; }
.cv2 .icon-btn-danger svg { width:15px; height:15px; }
.cv2 .icon-btn-danger:disabled { opacity:0.4; cursor:default; }
.cv-mark { display:inline-grid; place-items:center; flex:none; }
.cv-mark svg { display:block; width:100%; height:100%; filter:drop-shadow(0 8px 24px rgba(0,0,0,0.26)); }
.cv-mark-glyph { fill:none; stroke:#06110f; stroke-width:1.9; stroke-linecap:round;
  stroke-linejoin:round; opacity:0.82; }
.cv-mark-rail { width:34px; height:34px; }
.cv-mark-recent { width:32px; height:32px; }
.msg-avatar { flex:0 0 30px; width:30px; height:30px; border-radius:9px;
  display:inline-grid; place-items:center;
  font:700 11px/1 'IBM Plex Mono',ui-monospace,monospace; letter-spacing:0;
  color:#06110f; background:linear-gradient(135deg,var(--cv-ink),var(--cv-ink-2));
  box-shadow:inset 0 0 0 1px rgba(255,255,255,0.18); }
/* Persona avatar image overlays the initials chip (msg-avatar / cast-avatar);
   the monogram underneath shows through if the image 404s or fails to load. */
.avatar-has-img { position:relative; overflow:hidden; }
.avatar-img { position:absolute; inset:0; width:100%; height:100%;
  object-fit:cover; border-radius:inherit; display:block; }
.cv2 .msg-head { align-items:center; gap:10px; }
.cv2 .msg-head .time { margin-left:auto; flex:none; }
.cv-status { width:7px; height:7px; border-radius:50%; flex:none; background:var(--cv-ash); }
.cv-status.cv-active { background:var(--em); box-shadow:0 0 6px var(--em); animation:pulse 1.8s ease-in-out infinite; }
/* ---- rail ---- */
.cv-rail { position:relative; border-right:1px solid var(--cv-line); display:flex; flex-direction:column;
  min-height:0; background:rgba(255,255,255,0.012); }
/* Drag handle on the rail's right edge — straddles the border, widens its hit
   area beyond the visible 2px line. */
.cv-resizer { position:absolute; top:0; right:-4px; width:9px; height:100%; z-index:30;
  cursor:col-resize; display:flex; justify-content:center; touch-action:none; }
.cv-resizer::after { content:""; width:2px; height:100%; background:transparent; transition:background .12s ease; }
.cv-resizer:hover::after, .cv2.cv-resizing .cv-resizer::after { background:var(--em); }
.cv2.rail-hidden .cv-resizer { display:none; }
.cv2.rail-hidden { grid-template-columns:0 minmax(0,1fr); }
.cv2.rail-hidden .cv-rail { display:none; }
/* Fixed, so it must clear the fixed nav rail — otherwise the "reopen the
   conversation list" button hides underneath the sidebar. */
#cv-rail-open { position:fixed; left:calc(var(--rail-w) + 12px); top:calc(var(--topbar-h) + 10px); z-index:45; display:none; background:#0c1013; }
.cv2.rail-hidden #cv-rail-open { display:grid; }
.cv-railhead { display:flex; align-items:center; gap:8px; padding:14px 14px 10px; }
.cv-railhead h2 { margin:0; flex:1; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px;
  font-weight:600; text-transform:uppercase; letter-spacing:0.14em; color:var(--cv-ash); }
.cv-count { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px; color:var(--cv-ash);
  background:rgba(255,255,255,0.05); border:1px solid var(--cv-line); border-radius:999px; padding:1px 8px; }
.cv-search { position:relative; padding:0 12px 10px; }
.cv-search svg { position:absolute; left:22px; top:calc(50% - 5px); transform:translateY(-50%);
  width:14px; height:14px; color:var(--cv-ash); pointer-events:none; }
.cv-search input { width:100%; background:#0c1013; color:var(--cv-paper); border:1px solid var(--cv-line);
  border-radius:8px; padding:7px 10px 7px 30px; font:inherit; font-size:13px; }
.cv-search input::placeholder { color:var(--cv-ash); }
.cv-search input:focus { outline:none; border-color:var(--em-line); }
.cv-fchips { display:flex; flex-wrap:wrap; gap:5px; padding:0 12px 8px; }
.cv-fchip { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--cv-line);
  border-radius:999px; background:transparent; color:var(--cv-bone); padding:3px 10px;
  font:inherit; font-size:11.5px; cursor:pointer; transition:all .12s ease; }
.cv-fchip:hover { border-color:rgba(255,255,255,0.18); color:var(--cv-paper); }
.cv-fchip.active { background:var(--em-soft); border-color:var(--em-line); color:var(--cv-paper); }
.cv-fchip-n { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px; color:var(--cv-ash); }
.cv-fchip.active .cv-fchip-n { color:var(--em); }
.cv-controls { display:grid; grid-template-columns:1fr 1fr; gap:6px; padding:0 12px 10px;
  border-bottom:1px solid var(--cv-line); }
.cv-controls select { width:100%; background:#0c1013; color:var(--cv-bone); border:1px solid var(--cv-line);
  border-radius:7px; padding:6px 8px; font:inherit; font-size:12px; cursor:pointer; }
.cv-controls select:focus { outline:none; border-color:var(--em-line); }
.cv-list { flex:1; overflow-y:auto; padding:8px; display:flex; flex-direction:column; gap:3px; }
/* ---- conversation button: just the topic logo + topic; everything else lives
   in the hover (i) popover. Clean filled hover/active, no left-border accent. */
.cv-item { position:relative; border-radius:10px; }
.cv-link { display:flex; gap:11px; align-items:center; padding:9px 54px 9px 11px; border-radius:10px;
  text-decoration:none; color:var(--cv-bone); min-width:0;
  transition:background .12s ease, box-shadow .12s ease; }
.cv-link:hover { text-decoration:none; background:rgba(255,255,255,0.045); }
.cv-item.active .cv-link { background:var(--em-soft); box-shadow:inset 0 0 0 1px var(--em-line); }
.cv-mark-wrap { position:relative; flex:none; display:flex; }
.cv-mark-wrap.is-active::after { content:""; position:absolute; top:-2px; right:-2px; width:8px; height:8px;
  border-radius:50%; background:var(--em); box-shadow:0 0 0 2px #0a0d0f, 0 0 6px var(--em);
  animation:pulse 1.8s ease-in-out infinite; }
.cv-topic { flex:1; min-width:0; font-size:13.5px; font-weight:500; color:var(--cv-paper); line-height:1.35;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cv-item.active .cv-topic { color:#fff; }
/* ---- hover action buttons (i / delete) — reserved gutter, no layout shift ---- */
.cv-info, .cv-del { position:absolute; top:50%; transform:translateY(-50%); width:24px; height:24px;
  border:0; border-radius:7px; background:transparent; color:var(--cv-ash); cursor:pointer;
  display:grid; place-items:center; padding:0; opacity:0;
  transition:opacity .12s ease, background .12s ease, color .12s ease; }
.cv-info { right:32px; }
.cv-del { right:7px; font-size:15px; line-height:1; }
.cv-item:hover .cv-info, .cv-item:hover .cv-del,
.cv-info:focus-visible, .cv-del:focus-visible { opacity:1; }
.cv-info svg { width:15px; height:15px; }
.cv-info:hover { background:rgba(255,255,255,0.08); color:var(--cv-paper); }
/* ---- (i) details popover — fixed-positioned by JS so the list's overflow
   can't clip it ---- */
.cv-tip { position:fixed; z-index:80; left:0; top:0; max-width:280px; min-width:180px;
  padding:11px 13px; border-radius:11px; background:#0e1317; border:1px solid var(--cv-line);
  box-shadow:0 12px 34px rgba(0,0,0,0.55); color:var(--cv-bone); font-size:12px; line-height:1.5;
  opacity:0; visibility:hidden; transform:translateY(4px); pointer-events:none;
  transition:opacity .12s ease, transform .12s ease; }
.cv-tip.show { opacity:1; visibility:visible; transform:none; }
.cv-tip-h { display:flex; align-items:center; gap:7px; margin-bottom:7px; padding-bottom:7px;
  border-bottom:1px solid var(--cv-line); font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:11px; color:var(--cv-paper); }
.cv-tip-st { text-transform:capitalize; color:var(--cv-ash); }
.cv-tip-st.active { color:var(--em); }
.cv-tip-row { display:grid; grid-template-columns:64px 1fr; gap:8px; align-items:baseline; padding:2px 0; }
.cv-tip-k { color:var(--cv-ash); font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9.5px;
  text-transform:uppercase; letter-spacing:0.09em; }
.cv-tip-v { color:var(--cv-paper); word-break:break-word; }
.cv-nomatch { display:none; padding:18px 14px; color:var(--cv-ash);
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:12px; text-align:center; }
.cv-list-empty { padding:24px 14px; color:var(--cv-ash); font-size:12.5px; text-align:center; line-height:1.6; }
.cv-del:hover { background:rgba(248,113,113,0.16); color:#f87171; opacity:1; }
.cv-del:disabled { opacity:0.4; }
.cv-railfoot { padding:12px; border-top:1px solid var(--cv-line); }
.cv-railfoot .btn { width:100%; justify-content:center; }
/* ---- main pane ----
   The reader keeps a measure while its pane runs full-bleed: a transcript is
   prose, and prose set the full width of a 1600px pane is unreadable however
   much screen there is. ch-based so the cap tracks the font, not a magic pixel
   count.

   Sizing note: `ch` is the advance width of "0", which in a proportional font
   is wider than the average glyph — so these are NOT 123/138 characters per
   line, they're ~1030px/~1160px at the 14px body size. Picked deliberately:
   82ch resolved to 688px, well under the 960px this column used to be, which
   left ~900px of the pane empty and read as a skinny ribbon. */
.cv-main { overflow-y:auto; min-width:0; position:relative; }
.cv-read { max-width:123ch; margin:0 auto; padding:40px var(--gutter) 96px; }
.cv2.cv-fullscreen .cv-read { max-width:138ch; }

/* ---- scroll progress rail ----
   Sticky, not fixed: .cv-main is the scroller (the window never scrolls on
   this page), so a sticky first child rides the top of the *pane* and needs
   no knowledge of the rail's width or the topbar's height. margin-bottom:-2px
   keeps it from displacing the transcript. Animates transform only — a width
   transition here would relayout the pane on every scroll frame. */
.cv-prog {
  position:sticky; top:0; z-index:12;
  height:2px; margin-bottom:-2px;
  background:transparent; pointer-events:none;
}
.cv-prog i {
  display:block; height:100%; width:100%;
  transform:scaleX(0); transform-origin:0 50%;
  background:linear-gradient(90deg, var(--em), #6ee7b7);
  box-shadow:0 0 10px rgba(16,185,129,0.55);
  transition:transform .08s linear;
}

/* ---- jump to latest ----
   A zero-height sticky footer inside .cv-read: it hovers over the bottom of
   whatever pane it's in, so it survives the rail collapsing, fullscreen, and
   the mobile single-column layout without a single hard-coded offset.
   Only shows when SSE lands a message you can't see — if you're already at the
   bottom the transcript just grows and the button stays out of the way. */
.cv-jumpwrap {
  position:sticky; bottom:22px; z-index:14;
  height:0; display:flex; justify-content:center;
  pointer-events:none;
}
.cv-jump {
  transform:translateY(14px);
  display:inline-flex; align-items:center; gap:8px;
  padding:8px 14px; border-radius:999px;
  border:1px solid var(--em-line); background:rgba(9,14,12,0.92);
  backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px);
  color:var(--em); cursor:pointer;
  font:inherit; font-size:12.5px; font-weight:500;
  box-shadow:0 10px 30px -8px rgba(0,0,0,0.8);
  opacity:0; visibility:hidden;
  transition:opacity .18s ease, transform .18s cubic-bezier(0.16,1,0.3,1), visibility .18s;
}
.cv-jumpwrap.show .cv-jump {
  opacity:1; visibility:visible; transform:translateY(0); pointer-events:auto;
}
.cv-jump:hover { background:rgba(16,185,129,0.16); }
.cv-jump svg { width:13px; height:13px; }
.cv-jump .cv-jump-n {
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px;
  background:var(--em); color:#06110f; border-radius:999px; padding:1px 6px; font-weight:700;
}
.cv-read-head { margin-bottom:0; }
.cv-eyebrow { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
.cv-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
/* Actions panel beneath the Cast — same .cv-box shell as Cast and Conversation
   so the reader is three matching modules stacked. */
.cv-actionbox { padding-bottom:0.9rem; }
/* Window + destructive controls, pushed to the far edge so the four primary
   actions read as a set rather than as part of a tray of eight. */
.cv-actions-util { display:flex; align-items:center; gap:8px; margin-left:auto; }
/* The four primary actions. Each carries one hue on its icon, its border and
   its hover — the label stays light, so the row is colour-coded rather than a
   row of coloured blocks. Emerald is deliberately not in this set: it means
   "live / lead" elsewhere on this page. */
.cv-abtn { display:inline-flex; align-items:center; gap:7px; }
.cv-abtn svg { width:14px; height:14px; flex:0 0 auto; color:var(--abtn, #a1a1aa);
  transition:color .14s ease; }
.cv-abtn { border-color:color-mix(in srgb, var(--abtn, #3f3f46) 34%, transparent); }
.cv-abtn:hover { border-color:color-mix(in srgb, var(--abtn, #3f3f46) 60%, transparent);
  background:color-mix(in srgb, var(--abtn, #3f3f46) 10%, transparent); }
.cv-abtn.is-violet { --abtn:#a78bfa; }
.cv-abtn.is-sky    { --abtn:#38bdf8; }
.cv-abtn.is-amber  { --abtn:#fbbf24; }
.cv-abtn.is-rose   { --abtn:#f472b6; }
/* Media-prompt buttons (Images / Audio) — icon + label, same height as the
   export buttons beside them. The icon is a 14px stroke SVG, so it needs an
   explicit size: .btn doesn't constrain its children. */
/* ---- Actions help ----
   ONE "?" for the whole pane, sat beside the ACTIONS heading, rather than four
   badges straddling four button borders. It explains all four actions in a
   single popover, so each explanation gets a readable width instead of a 264px
   tip crammed under a button. Click to open — a hover tip can't hold four
   paragraphs still long enough to read, and it's dead on touch. */
.cv-box-head { display:flex; align-items:center; gap:8px; margin-bottom:0.7rem; }
.cv-box-head .cv-box-label { margin:0; }
/* The pane, not the "?", is the positioning context: anchored to the badge the
   popover dropped straight over the four buttons it was explaining. Anchored to
   .cv-actionbox it clears the whole row and opens beneath it. */
.cv-actionbox { position:relative; }
.cv-ahelp { display:inline-flex; }
.cv-ahelp-btn {
  width:17px; height:17px; padding:0; border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  background:#22252a; border:1px solid rgba(255,255,255,0.16);
  color:#c8cbd2; font:700 10px/1 inherit; cursor:pointer;
  transition:color .12s, border-color .12s, background .12s;
}
.cv-ahelp-btn:hover, .cv-ahelp-btn:focus-visible,
.cv-ahelp-btn[aria-expanded="true"] {
  color:var(--em); border-color:var(--em); background:var(--em-soft);
  outline:none;
}
.cv-ahelp-pop {
  /* left == .cv-box's own horizontal padding, so the popover's edge lines up
     with the first button above it rather than sitting 4px proud of it. */
  position:absolute; top:calc(100% - 5px); left:1.15rem; z-index:40;
  width:min(460px, calc(100% - 2.3rem));
  padding:13px 15px 14px; border-radius:10px;
  /* A genuinely RAISED surface. The old tip sat at #0b0d0f — a hair off the
     page background — so it read as see-through wherever it landed on the gap
     between panels. This is several stops lighter, with a visible hairline and
     a real shadow, so the text always has its own ground. Opaque literals, not
     tokens: the panel tokens are translucent by design. */
  background:#191c21; border:1px solid rgba(255,255,255,0.13);
  box-shadow:0 18px 44px -10px rgba(0,0,0,0.85), 0 0 0 1px rgba(0,0,0,0.45);
  text-align:left; letter-spacing:0; text-transform:none;
}
.cv-ahelp-pop[hidden] { display:none; }
.cv-ahelp-head {
  margin:0 0 10px; padding-bottom:9px;
  border-bottom:1px solid rgba(255,255,255,0.08);
  font:600 10.5px/1 'IBM Plex Mono',ui-monospace,monospace;
  letter-spacing:0.1em; text-transform:uppercase; color:#8b9099;
}
.cv-ahelp-list { list-style:none; margin:0; padding:0;
  display:flex; flex-direction:column; gap:11px; }
.cv-ahelp-row { display:flex; align-items:flex-start; gap:9px; }
.cv-ahelp-ico { flex:0 0 auto; display:flex; margin-top:1px; }
.cv-ahelp-ico svg { width:14px; height:14px; color:var(--abtn,#a1a1aa); }
.cv-ahelp-row.is-violet { --abtn:#a78bfa; }
.cv-ahelp-row.is-sky    { --abtn:#38bdf8; }
.cv-ahelp-row.is-amber  { --abtn:#fbbf24; }
.cv-ahelp-row.is-rose   { --abtn:#f472b6; }
.cv-ahelp-txt { display:flex; flex-direction:column; gap:2px;
  font-size:12.5px; line-height:1.55; color:#b6bac2; }
.cv-ahelp-txt b { color:#e7eaee; font-weight:600; font-size:12.5px; }
.cv-ahelp-txt span b { color:#e7eaee; }
/* Narrow screens: give it the pane's full inner width rather than a fixed one. */
@media (max-width:560px) {
  .cv-ahelp-pop { width:calc(100% - 2.3rem); }
}
/* The overlay both buttons fill in — see _media_prompt_modal(). */
.cv-pm { position:fixed; inset:0; z-index:60; display:flex; align-items:center;
  justify-content:center; padding:24px; background:rgba(3,5,8,0.72);
  backdrop-filter:blur(2px); }
.cv-pm.hidden { display:none; }
.cv-pm-card { display:flex; flex-direction:column; width:min(880px,100%);
  max-height:min(84vh,760px);
  /* Opaque literal, NOT var(--panel). The panel token is rgba(24,24,27,0.4) —
     40% opaque, which is right for the in-flow boxes that sit on the page
     background, and wrong for anything floating over content: the transcript
     read straight through the prompt text. Same raised-surface value as
     .cv-ahelp-pop, so the two overlays agree. */
  background:#191c21;
  border:1px solid rgba(255,255,255,0.13); border-radius:12px; overflow:hidden;
  box-shadow:0 24px 60px rgba(0,0,0,0.7), 0 0 0 1px rgba(0,0,0,0.45); }
.cv-pm-head { display:flex; align-items:flex-start; gap:16px; padding:16px 18px;
  border-bottom:1px solid var(--cv-line); }
.cv-pm-head h3 { margin:0; font-size:15px; color:var(--text); }
.cv-pm-sub { margin:4px 0 0; font-size:12.5px; color:var(--muted); max-width:60ch; }
.cv-pm-head .icon-btn { margin-left:auto; flex:0 0 auto; }
.cv-pm-text { flex:1 1 auto; min-height:240px; width:100%; resize:none; border:0;
  padding:16px 18px; background:transparent; color:var(--text);
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:12.5px;
  line-height:1.6; white-space:pre-wrap; }
.cv-pm-text:focus { outline:none; }
.cv-pm-foot { display:flex; align-items:center; gap:10px; padding:12px 18px;
  border-top:1px solid var(--cv-line); background:rgba(255,255,255,0.02); }
.cv-pm-note { font-size:12px; color:var(--muted,#a1a1aa); margin-right:auto; max-width:52ch; }
.cv-pm-note strong { color:var(--text); font-weight:600; }
@media (max-width:640px) {
  .cv-pm { padding:0; }
  .cv-pm-card { max-height:100vh; border-radius:0; border:0; }
  .cv-pm-note { display:none; }
}
.cv-pill { display:inline-flex; align-items:center; gap:7px; border:1px solid var(--cv-line);
  border-radius:999px; color:var(--cv-ash); padding:3px 11px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10.5px; text-transform:uppercase;
  letter-spacing:0.06em; }
.cv-pill .dot { width:6px; height:6px; border-radius:50%; background:var(--cv-ash); }
.cv-pill.is-active { color:var(--em); border-color:var(--em-line); background:var(--em-soft); }
.cv-pill.is-active .dot { background:var(--em); box-shadow:0 0 6px var(--em);
  animation:pulse 1.8s ease-in-out infinite; }
.cv-turn { display:inline-flex; align-items:center; gap:7px; border:1px solid var(--em-line);
  border-radius:999px; background:var(--em-soft); color:var(--em); padding:3px 11px;
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10.5px; letter-spacing:0.03em; }
/* "quiet for N" — elapsed since the last message on an active run. Neutral
   until it passes this conversation's own median gap x3 (see
   export.quiet_threshold_seconds), because a long turn is normal: run #54's
   facilitator spent 16.8 min writing a deliverable while every other turn took
   under 1.5 min. A hung agent looks identical from here, which is the whole
   point of surfacing the number rather than a verdict. */
.cv-quiet { display:inline-flex; align-items:center; gap:7px; border:1px solid var(--border);
            border-radius:999px; padding:3px 10px; font-size:11.5px; color:var(--muted-2);
            font-variant-numeric:tabular-nums; }
.cv-quiet .dot { width:6px; height:6px; border-radius:50%; background:var(--muted-2); }
.cv-quiet.is-stale { border-color:rgba(245,158,11,0.4); color:var(--warn,#f59e0b); }
.cv-quiet.is-stale .dot { background:var(--warn,#f59e0b); }
.cv-turn .dot { width:6px; height:6px; border-radius:50%; background:var(--em);
  box-shadow:0 0 6px var(--em); animation:pulse 1.8s ease-in-out infinite; }
/* The conversation title. Was JetBrains Mono 800 — a monospace headline sitting
   on top of monospace meta, so nothing separated the topic from the run data.
   It's the page's one real headline now, in the body face. Styling lives here
   rather than on `.cv-h1` alone because `.cv-read-head h1` would outrank a bare
   class and silently win. */
.cv-read-head h1.cv-h1 { margin:0; font-size:27px; font-weight:650;
  letter-spacing:-0.02em; line-height:1.22; color:var(--cv-paper);
  /* A topic is the run's NAME, but nothing stopped an operator pasting a whole
     brief into the field — run #57 arrived as a four-thousand-character
     headline that pushed the cast and the transcript off the screen. The seed
     path caps new ones; this clamps the ones already in the DB, retroactively
     and with no migration. The full text stays in the `title=` tooltip. */
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.cv-empty { height:100%; min-height:60vh; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:14px; color:var(--cv-ash); text-align:center; padding:24px; }
.cv-empty svg { width:30px; height:30px; opacity:0.5; }
/* ---- overview (no conversation selected) ---- */
.cv-ov { max-width:1040px; margin:0 auto; padding:40px 32px 72px; }
.cv-ov-head h1 { margin:0; font-family:'JetBrains Mono',ui-monospace,monospace; font-size:24px;
  font-weight:800; letter-spacing:-0.01em; color:var(--cv-paper); }
.cv-ov-head p { margin:6px 0 0; color:var(--cv-ash); font-size:13.5px; }
.cv-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:22px 0 28px; }
.cv-stat { border:1px solid var(--cv-line); border-radius:10px; padding:16px 18px;
  background:rgba(255,255,255,0.015); }
.cv-stat-n { display:block; font-family:'JetBrains Mono',ui-monospace,monospace; font-size:26px;
  font-weight:800; line-height:1; color:var(--cv-paper); font-variant-numeric:tabular-nums; }
.cv-stat-n.em { color:var(--em); }
.cv-stat-l { display:block; margin-top:7px; font-size:11px; text-transform:uppercase;
  letter-spacing:0.12em; color:var(--cv-ash); }
.cv-recent h2 { margin:0 0 12px; font-size:11px; text-transform:uppercase; letter-spacing:0.14em;
  color:var(--cv-ash); font-weight:600; }
/* ---- recent conversations: a responsive card grid, not a flat list ---- */
.cv-recent-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(268px, 1fr)); gap:12px; }
.cv-card { display:flex; flex-direction:column; gap:11px; padding:16px 17px; border-radius:14px;
  border:1px solid var(--cv-line); background:rgba(255,255,255,0.015); text-decoration:none;
  transition:border-color .14s ease, background .14s ease, transform .14s ease, box-shadow .14s ease; }
.cv-card:hover { text-decoration:none; border-color:var(--em-line); background:rgba(255,255,255,0.03);
  transform:translateY(-2px); box-shadow:0 10px 26px rgba(0,0,0,0.32); }
.cv-card-top { display:flex; align-items:center; gap:11px; min-width:0; }
.cv-card-topic { flex:1; min-width:0; font-size:14px; font-weight:600; color:var(--cv-paper);
  line-height:1.35; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.cv-card-live { flex:none; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:9px;
  text-transform:uppercase; letter-spacing:0.1em; color:var(--em); background:var(--em-soft);
  border:1px solid var(--em-line); border-radius:999px; padding:2px 7px; align-self:flex-start; }
.cv-card-cast { font-size:12.5px; color:var(--cv-bone); opacity:0.82; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.cv-card-meta { display:flex; align-items:center; gap:8px; font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:10.5px; color:var(--cv-ash); margin-top:auto; }
.cv-card-dot { width:2.5px; height:2.5px; border-radius:50%; background:var(--cv-ash); opacity:0.6; }
.cv-ov-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:24px; }
/* ---- full screen ----
   Distraction-free reader: the topbar AND the nav rail both go, and <main>
   reclaims the rail's inset. Leaving the rail would make "full screen" a lie. */
.cv2.cv-fullscreen { height:100dvh; grid-template-columns:minmax(0,1fr); }
body:has(.cv2.cv-fullscreen) .topbar,
body:has(.cv2.cv-fullscreen) .siderail { display:none; }
body:has(.cv2.cv-fullscreen) main { min-height:100dvh; margin-left:0; }
/* ---- mobile ---- */
@media (max-width:900px) {
  /* minmax(0,1fr), not 1fr — an auto min would let the rail's nowrap topic
     lines set the column's min-content and force horizontal page scroll. */
  .cv2 { grid-template-columns:minmax(0,1fr); grid-template-rows:auto 1fr; height:auto;
    min-height:calc(100dvh - var(--topbar-h)); }
  .cv-rail { border-right:0; border-bottom:1px solid var(--cv-line); }
  .cv-resizer { display:none; }
  .cv-list { max-height:38vh; }
  #cv-rail-open { top:auto; bottom:14px; }
  .cv-read { padding:28px 16px 56px; }
  .cv-ov { padding:28px 16px 56px; }
  .cv-stats { grid-template-columns:1fr 1fr; }
  .cv-actions-util { margin-left:0; }
  .cv-del { opacity: 0.65; }
}
</style>"""

_ORCH_READONLY_CSS = """
<style>
.orch-ro-card{border:1px solid rgba(255,255,255,0.10);border-radius:8px;padding:16px 18px;margin:16px 0;background:rgba(255,255,255,0.02);}
.orch-ro-card h3{margin:0 0 8px;font-size:14px;color:#e5e7eb;}
.orch-ro-card pre{margin:0 0 10px;padding:12px 14px;background:#0b0f0e;border:1px solid rgba(255,255,255,0.08);border-radius:6px;overflow-x:auto;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;color:#cbd5e1;}
.orch-ro-card p{margin:0;color:#9ca3af;font-size:13px;}
/* Per-format guide links. The homepage's debate + podcast CTAs both land on
   this page when hosted, so this is where a public visitor is told how to
   actually run one. */
.orch-ro-links{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
.orch-ro-links a{border:1px solid rgba(255,255,255,0.12);border-radius:6px;padding:7px 11px;font-size:12.5px;color:#d4d4d8;text-decoration:none;}
.orch-ro-links a:hover{border-color:#10b981;color:#fff;text-decoration:none;}
.orch-ro-foot{margin-top:18px;color:#9ca3af;font-size:13px;}
</style>
"""

# ---------------------------------------------------------------------------
# /setup — "which CLI tools do you have?". Rides on ORCHESTRATE_CSS for the
# shell (.orch-shell / .orch-head / .lbl / .hint / .orch-submit) and adds only
# the ticklist rows and the seat-plan preview.
# ---------------------------------------------------------------------------

SETUP_CSS = """
.su-shell { max-width: 820px; }
.su-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.su-row {
  border: 1px solid var(--border); border-radius: 8px;
  background: rgba(24, 24, 27, 0.4);
  padding: 12px 14px;
}
.su-row:has(input:checked) {
  border-color: rgba(16, 185, 129, 0.38);
  background: rgba(16, 185, 129, 0.05);
}
.su-main {
  display: grid; grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center; gap: 12px; cursor: pointer;
}
.su-main input[type=checkbox] { width: 16px; height: 16px; accent-color: var(--accent); }
.su-names { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.su-name { font-size: 14px; font-weight: 600; color: var(--text); }
.su-dep {
  font-size: 11px; font-weight: 400; font-style: normal;
  color: var(--muted-2); text-transform: uppercase; letter-spacing: 0.1em;
  margin-left: 6px;
}
.su-sub { font-size: 12px; color: var(--muted-2); }
.su-sub code, .su-detail code, .su-plan code {
  font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px;
}
.su-pills { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.su-pill {
  font-family: 'IBM Plex Mono', ui-monospace, monospace;
  font-size: 11px; line-height: 1.7; white-space: nowrap;
  border-radius: 999px; padding: 0 9px;
  border: 1px solid var(--border-strong); color: var(--muted-2);
}
.su-pill.ok { color: var(--good); border-color: rgba(16, 185, 129, 0.35);
              background: rgba(16, 185, 129, 0.08); }
.su-pill.warn { color: #fbbf24; border-color: rgba(245, 158, 11, 0.35);
                background: rgba(245, 158, 11, 0.08); }
.su-pill.off { color: var(--muted-2); }
.su-detail { margin: 10px 0 0; font-size: 12px; color: var(--muted); line-height: 1.55; }
.su-links { margin: 8px 0 0; font-size: 12px; }
.su-links a, .su-detail a { color: var(--accent); }

.su-plan {
  border: 1px solid var(--border); border-radius: 8px;
  padding: 14px 16px; background: rgba(24, 24, 27, 0.4);
  font-size: 13px; color: var(--muted);
}
.su-plan-lead { margin: 0 0 10px; color: var(--text); }
.su-plan-none { margin: 0; color: #fbbf24; }
.su-plan-list { list-style: none; margin: 0; padding: 0;
                display: flex; flex-direction: column; gap: 8px; }
.su-plan-list li { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.su-plan-k {
  flex: none; min-width: 128px;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.09em;
  color: var(--muted-2);
}
.su-seatline { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
.su-seatline code {
  background: rgba(255, 255, 255, 0.05); border-radius: 5px; padding: 2px 7px;
  color: var(--text);
}
.su-vs { color: var(--muted-2); font-size: 11px; text-transform: uppercase; }
.su-plan-note { margin: 12px 0 0; font-size: 12.5px; color: var(--muted-2); line-height: 1.6; }
.su-seats {
  margin-top: 14px; padding-top: 12px;
  border-top: 1px dashed var(--border-strong);
}
.su-seats p { margin: 0 0 10px; font-size: 12.5px; line-height: 1.6; }
.su-seats-msg { margin-left: 10px; font-size: 12px; color: var(--muted-2); }
.su-seats-msg.ok { color: var(--good); }
.su-seats-msg.fail { color: var(--bad); }
.su-foot { margin-top: 10px; }
.su-foot a { color: var(--accent); }
"""

# ---------------------------------------------------------------------------
# /extension — the AgentBattleground explainer. Prose page; borrows the
# orchestrate shell and adds cards, a site list, and the install steps.
# ---------------------------------------------------------------------------

EXTENSION_CSS = """
.xt-shell { max-width: 880px; }
/* Guide link in the page header — the counterpart to .orch-guide on the
   /orchestrate form. Both answer "how do I run one" where the homepage CTA
   drops you, rather than only at the foot of the page. */
.xt-guide { margin: 14px 0 0; font-size: 13px; }
.xt-guide a { font-weight: 500; }
.xt-guide span { color: var(--muted-2); }
.xt-invariant {
  border: 1px solid rgba(245, 158, 11, 0.32);
  background: rgba(245, 158, 11, 0.06);
  border-radius: 10px; padding: 18px 20px; margin: 4px 0 26px;
}
.xt-invariant h3 { margin: 0 0 8px; font-size: 17px; color: #fcd9a1; }
.xt-invariant p { margin: 0 0 10px; color: var(--muted); font-size: 13.5px; line-height: 1.65; }
.xt-invariant p:last-child { margin-bottom: 0; }
.xt-sec { margin: 30px 0; }
.xt-sec > h3 {
  margin: 0 0 10px; font-size: 12px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.09em; color: var(--muted-2);
}
.xt-sec > p { margin: 0 0 12px; color: var(--muted); font-size: 13.5px; line-height: 1.7; }
.xt-steps { list-style: none; counter-reset: xt; margin: 0; padding: 0;
            display: flex; flex-direction: column; gap: 14px; }
.xt-steps li { counter-increment: xt; display: grid;
               grid-template-columns: 28px minmax(0, 1fr); gap: 12px; }
.xt-steps li::before {
  content: counter(xt);
  width: 26px; height: 26px; border-radius: 7px;
  display: grid; place-items: center;
  border: 1px solid rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.1);
  color: var(--good); font-size: 12px; font-weight: 700;
}
.xt-steps h4 { margin: 3px 0 4px; font-size: 14px; color: var(--text); font-weight: 600; }
.xt-steps p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.65; }
.xt-code {
  margin: 8px 0 0; padding: 10px 12px;
  background: #0b0f0e; border: 1px solid var(--border); border-radius: 6px;
  overflow-x: auto;
  font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12.5px;
  color: #cbd5e1; white-space: pre;
}
.xt-sites { display: flex; flex-wrap: wrap; gap: 7px; }
.xt-site {
  font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px;
  border: 1px solid var(--border-strong); border-radius: 999px;
  padding: 3px 11px; color: var(--muted);
}
.xt-bridge {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  border: 1px solid var(--border); border-radius: 8px;
  background: rgba(24, 24, 27, 0.4); padding: 13px 15px;
  font-size: 13px; color: var(--muted);
}
.xt-bridge .xt-dot {
  width: 8px; height: 8px; border-radius: 50%; flex: none;
  background: var(--muted-2); align-self: center;
}
.xt-bridge.up .xt-dot { background: var(--good); box-shadow: 0 0 0 3px rgba(16,185,129,0.16); }
.xt-bridge.down .xt-dot { background: var(--bad); }
.xt-bridge code { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 12px; }
.xt-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.xt-links a {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border-strong); border-radius: 7px;
  padding: 7px 12px; font-size: 13px; color: var(--muted);
  text-decoration: none; transition: border-color .15s ease, color .15s ease;
}
.xt-links a:hover { border-color: var(--accent); color: var(--text); text-decoration: none; }
"""

# ---------------------------------------------------------------------------
# /battleground — the arena console. Second operator surface for the same
# arenas the extension's side panel drives, for reviewing drafts without the
# captured page open in a tab. Rides on ORCHESTRATE_CSS for the shell
# (.orch-shell / .orch-head) and adds the arena list, the thread, and the
# draft cards. Scoped under .bgc so nothing here can leak onto /extension,
# which shares the same shell.
# ---------------------------------------------------------------------------

BATTLEGROUND_CSS = """
.bgc { max-width: 940px; }
.bgc-note {
  display: flex; gap: 10px; align-items: baseline;
  border: 1px solid rgba(245, 158, 11, 0.32);
  background: rgba(245, 158, 11, 0.06);
  border-radius: 8px; padding: 12px 15px; margin: 0 0 24px;
  font-size: 12.5px; color: var(--muted); line-height: 1.6;
}
.bgc-note strong { color: #fcd9a1; }
.bgc-filters { display: flex; gap: 7px; flex-wrap: wrap; margin: 0 0 16px; }
.bgc-chip {
  border: 1px solid var(--border-strong); border-radius: 999px;
  padding: 4px 13px; font-size: 12.5px; color: var(--muted);
  text-decoration: none;
}
.bgc-chip:hover { border-color: var(--accent); color: var(--text); text-decoration: none; }
.bgc-chip.on { border-color: var(--accent); color: var(--text); background: rgba(16,185,129,0.10); }

.bgc-list { display: flex; flex-direction: column; gap: 10px; }
.bgc-card {
  border: 1px solid var(--border); border-radius: 9px;
  background: rgba(24, 24, 27, 0.4); padding: 14px 16px;
}
.bgc-card:hover { border-color: var(--border-strong); }
.bgc-card-top { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.bgc-card-top h3 { margin: 0; font-size: 15px; font-weight: 600; flex: 1 1 260px; min-width: 0; }
.bgc-card-top h3 a { color: var(--text); }
.bgc-card-top h3 a:hover { color: var(--accent); text-decoration: none; }
.bgc-meta {
  margin: 8px 0 0; display: flex; gap: 8px 16px; flex-wrap: wrap;
  font-size: 12px; color: var(--muted-2);
}
.bgc-meta span { display: inline-flex; gap: 5px; align-items: baseline; }
.bgc-meta b { font-weight: 500; color: var(--muted); }
.bgc-site {
  font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px;
  border: 1px solid var(--border-strong); border-radius: 999px;
  padding: 2px 9px; color: var(--muted-2); flex: none;
}
.bgc-pill {
  font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 11px;
  border-radius: 999px; padding: 2px 9px; flex: none;
  border: 1px solid var(--border-strong); color: var(--muted-2);
}
.bgc-pill.open { color: var(--good); border-color: rgba(16,185,129,0.35);
                 background: rgba(16,185,129,0.08); }
.bgc-pill.closed { color: var(--muted-2); }
.bgc-pill.pending { color: #fbbf24; border-color: rgba(245,158,11,0.38);
                    background: rgba(245,158,11,0.10); }
.bgc-pill.approved { color: var(--good); border-color: rgba(16,185,129,0.35);
                     background: rgba(16,185,129,0.08); }
.bgc-pill.rejected { color: var(--bad); border-color: rgba(239,68,68,0.35);
                     background: rgba(239,68,68,0.08); }
.bgc-pill.posted { color: #93c5fd; border-color: rgba(59,130,246,0.35);
                   background: rgba(59,130,246,0.10); }

.bgc-sec { margin: 30px 0; }
.bgc-sec > h3 {
  margin: 0 0 12px; font-size: 12px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.09em; color: var(--muted-2);
}
.bgc-sec > p { margin: 0 0 12px; color: var(--muted); font-size: 13px; line-height: 1.7; }

.bgc-head-meta {
  display: flex; gap: 8px 16px; flex-wrap: wrap; align-items: baseline;
  margin: 0 0 12px; font-size: 12.5px; color: var(--muted-2);
}
.bgc-actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 22px; }
.bgc-stance {
  border-left: 2px solid var(--accent-strong); padding: 2px 0 2px 14px;
  margin: 0 0 22px; color: var(--muted); font-size: 13.5px; line-height: 1.7;
  white-space: pre-wrap;
}

.bgc-posts { display: flex; flex-direction: column; gap: 8px; }
.bgc-post {
  border: 1px solid var(--border); border-radius: 8px;
  background: rgba(24, 24, 27, 0.4); padding: 11px 13px;
}
.bgc-post.target { border-color: rgba(16,185,129,0.45); background: rgba(16,185,129,0.05); }
.bgc-post-head {
  display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap;
  font-size: 12px; color: var(--muted-2); margin: 0 0 6px;
}
.bgc-author { font-weight: 600; color: var(--text); font-size: 12.5px; }
.bgc-target-tag {
  font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.09em;
  color: var(--good);
}
.bgc-text {
  margin: 0; color: var(--muted); font-size: 13px; line-height: 1.65;
  white-space: pre-wrap; overflow-wrap: anywhere;
}

.bgc-draft {
  border: 1px solid var(--border); border-radius: 9px;
  background: rgba(24, 24, 27, 0.4); padding: 14px 16px; margin: 0 0 12px;
}
.bgc-draft.is-pending { border-color: rgba(245,158,11,0.30); }
.bgc-draft-head {
  display: flex; gap: 9px; align-items: baseline; flex-wrap: wrap;
  margin: 0 0 10px; font-size: 12px; color: var(--muted-2);
}
.bgc-draft-head .bgc-author { font-family: 'IBM Plex Mono', ui-monospace, monospace; }
.bgc-sub {
  margin: 10px 0 0; padding: 9px 11px; border-radius: 7px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  font-size: 12.5px; color: var(--muted-2); line-height: 1.6;
  white-space: pre-wrap; overflow-wrap: anywhere;
}
.bgc-sub b {
  display: block; margin: 0 0 4px; font-weight: 600; color: var(--muted);
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
}
.bgc-verdict { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0 0; }
.bgc-msg { margin: 10px 0 0; font-size: 12.5px; color: var(--muted-2); }
.bgc-msg.fail { color: var(--bad); }
.bgc-empty {
  border: 1px dashed var(--border-strong); border-radius: 9px;
  padding: 26px 20px; text-align: center; color: var(--muted-2); font-size: 13px;
}
.bgc-empty a { color: var(--accent); }
"""

# ---------------------------------------------------------------------------
# Persona management. Personas live in the shared DB (the personas table), synced
# between local and the hosted mirror by the sidecar — so CRUD works on both. The
# root_exists() guards below now just confirm the DB is reachable (no longer a
# local-only gate). Writes go through orchestrator.personas (create/update/delete).
# ---------------------------------------------------------------------------

_PERSONAS_CSS = """\
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* --- Three-pane persona console ------------------------------------------
   Emerald-accented (matches the homepage + favicon brand), scoped to .pm3 so
   it doesn't fight the emerald-accented BASE_CSS used by the other app pages.
   The shared _layout <main> is normally a narrow 1100px column; this page is
   full-bleed and fills the viewport below the topbar (--topbar-h). */
/* App surface — same deal as .cv2: zero the padding, keep the rail inset. */
main:has(.pm3) { max-width:none; padding:0; margin:0 0 0 var(--rail-w); }

.pm3 {
  --em:#10b981; --em-2:#34d399; --em-soft:rgba(16,185,129,0.12);
  --em-line:rgba(16,185,129,0.34); --bad:#f87171;
  --pm-line:rgba(255,255,255,0.08); --pm-line-2:rgba(255,255,255,0.14);
  --pm-ash:#6b7480; --pm-bone:#c8ccd1; --pm-paper:#e7eaee;
  height:calc(100dvh - var(--topbar-h));
  display:grid; grid-template-columns:264px minmax(0,1fr) 380px;
  background:#07090a; color:var(--pm-bone);
  font-family:'IBM Plex Sans','Inter',system-ui,sans-serif;
}
.pm3 *, .pm3 *::before, .pm3 *::after { box-sizing:border-box; }
.pm3 .mono { font-family:'IBM Plex Mono',ui-monospace,monospace; }

/* Unavailable / empty-DB notice keeps the simple full-width treatment. */
.pm-unavail { margin:40px auto; max-width:60ch; border:1px solid var(--pm-line); border-radius:10px; padding:1.1rem 1.25rem; color:var(--pm-ash); }

/* ---- Left rail: group navigator ---- */
.pm-rail { border-right:1px solid var(--pm-line); display:flex; flex-direction:column; min-height:0; }
.pm-search { position:relative; padding:14px; border-bottom:1px solid var(--pm-line); }
.pm-search svg { position:absolute; left:24px; top:50%; transform:translateY(-50%); width:15px; height:15px; color:var(--pm-ash); pointer-events:none; }
.pm-search input { width:100%; background:#0c1013; color:var(--pm-paper); border:1px solid var(--pm-line); border-radius:8px; padding:8px 10px 8px 32px; font:inherit; font-size:13px; }
.pm-search input::placeholder { color:var(--pm-ash); }
.pm-search input:focus { outline:none; border-color:var(--em-line); }
.pm-grps { flex:1; overflow-y:auto; padding:10px 10px 0; display:flex; flex-direction:column; gap:2px; }
.pm-rail-h { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.16em; text-transform:uppercase; color:var(--pm-ash); padding:6px 8px 4px; }
.pm-grp { display:flex; align-items:center; gap:10px; width:100%; text-align:left; background:none; border:0; border-left:2px solid transparent; border-radius:0 6px 6px 0; padding:9px 10px; color:var(--pm-bone); cursor:pointer; font:inherit; font-size:13px; transition:background .12s ease,color .12s ease; }
.pm-grp:hover { background:rgba(255,255,255,0.03); color:var(--pm-paper); }
.pm-grp svg { width:15px; height:15px; color:var(--pm-ash); flex:none; }
.pm-grp.active { background:var(--em-soft); border-left-color:var(--em); color:var(--pm-paper); }
.pm-grp.active svg { color:var(--em); }
.pm-grp-name { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-transform:uppercase; letter-spacing:0.04em; font-size:12px; }
.pm-grp-count { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--pm-ash); background:rgba(255,255,255,0.05); border-radius:6px; padding:1px 7px; }
.pm-grp.active .pm-grp-count { color:#062019; background:var(--em); font-weight:600; }
.pm-rail-foot { padding:12px; border-top:1px solid var(--pm-line); }
.pm-rail-foot .btn { width:100%; justify-content:center; }

/* ---- Center: persona list ---- */
.pm-center { display:flex; flex-direction:column; min-width:0; min-height:0; }
.pm-chead { display:flex; align-items:center; gap:12px; padding:20px 24px 14px; flex-wrap:wrap; }
.pm-ctitle { margin:0; font-family:'JetBrains Mono',monospace; font-weight:800; font-size:24px; letter-spacing:-0.01em; color:var(--pm-paper); text-transform:uppercase; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pm-ctools { display:flex; align-items:center; gap:8px; }
.pm-sort { background:#0c1013; color:var(--pm-bone); border:1px solid var(--pm-line); border-radius:6px; padding:6px 8px; font:inherit; font-size:12px; cursor:pointer; }
.pm-sort:focus { outline:none; border-color:var(--em-line); }
.pm-colhead { display:grid; grid-template-columns:46px 1fr 220px 240px 92px; gap:12px; padding:0 24px 8px; font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.14em; text-transform:uppercase; color:var(--pm-ash); border-bottom:1px solid var(--pm-line); }
.pm-scroll { flex:1; overflow-y:auto; padding:6px 12px 80px; }
.pm-rows { display:flex; flex-direction:column; }
.pm-rows[hidden] { display:none; }
.pm-row { display:grid; grid-template-columns:46px 1fr 220px 240px 92px; gap:12px; align-items:center; padding:11px 12px; border-bottom:1px solid var(--pm-line); border-radius:8px; cursor:pointer; transition:background .12s ease,box-shadow .12s ease; }
.pm-row:hover { background:rgba(255,255,255,0.025); }
.pm-row.active { background:var(--em-soft); box-shadow:inset 0 0 0 1px var(--em-line); border-bottom-color:transparent; }
.pm-av { width:34px; height:34px; border-radius:50%; display:grid; place-items:center; font-family:'IBM Plex Mono',monospace; font-size:12px; font-weight:600; color:var(--em-2); background:rgba(16,185,129,0.10); box-shadow:inset 0 0 0 1px var(--em-line); }
/* Avatar image overlay for the persona rows (mirrors .avatar-img on the
   conversation page); initials underneath show through on load failure. */
.pm-av.avatar-has-img { position:relative; overflow:hidden; }
.pm-av .avatar-img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; border-radius:inherit; display:block; }
.pm-row-name { font-weight:600; color:var(--pm-paper); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pm-row-slug { font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--pm-ash); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pm-row-tags { display:flex; gap:5px; flex-wrap:wrap; overflow:hidden; max-height:24px; }
.pm-chip-sm { font-size:11px; line-height:1.7; color:var(--em-2); background:var(--em-soft); border:1px solid var(--em-line); border-radius:999px; padding:0 8px; white-space:nowrap; }
.pm-row-acts { display:flex; gap:2px; justify-content:flex-end; opacity:0; transition:opacity .12s ease; }
.pm-row:hover .pm-row-acts, .pm-row.active .pm-row-acts { opacity:1; }
.pm-iact { background:none; border:0; padding:6px; border-radius:6px; color:var(--pm-ash); cursor:pointer; display:grid; place-items:center; }
.pm-iact svg { width:15px; height:15px; }
.pm-iact:hover { background:rgba(255,255,255,0.06); color:var(--pm-paper); }
.pm-iact.pm-del:hover { background:rgba(248,113,113,0.12); color:var(--bad); }
.pm-center-empty { padding:48px 24px; text-align:center; color:var(--pm-ash); }
.pm-center-empty code { color:var(--em-2); background:var(--em-soft); padding:2px 8px; border-radius:4px; }

/* ---- Right: detail / edit ---- */
.pm-detail { border-left:1px solid var(--pm-line); display:flex; flex-direction:column; min-height:0; }
.pm-detail-empty { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px; padding:24px; text-align:center; color:var(--pm-ash); }
.pm-detail-empty[hidden] { display:none; }
.pm-detail-empty svg { width:30px; height:30px; opacity:0.5; }
.pm-dform { flex:1; display:flex; flex-direction:column; min-height:0; }
.pm-dform[hidden] { display:none; }
.pm-dhead { display:flex; align-items:center; gap:10px; padding:18px 22px 8px; }
.pm-dtitle { margin:0; font-family:'JetBrains Mono',monospace; font-weight:700; font-size:20px; color:var(--pm-paper); flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pm-dclose { display:none; background:none; border:0; color:var(--pm-ash); font-size:18px; cursor:pointer; padding:4px 8px; }
.pm-dbody { flex:1; overflow-y:auto; padding:6px 22px 16px; display:flex; flex-direction:column; gap:6px; }
.pm-l { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:0.14em; text-transform:uppercase; color:var(--pm-ash); margin:12px 0 5px; }
.pm-detail input[type=text], .pm-detail select { width:100%; background:#0c1013; color:var(--pm-paper); border:1px solid var(--pm-line); border-radius:8px; padding:9px 11px; font:inherit; font-size:13px; }
.pm-detail input[type=text]:focus, .pm-detail select:focus, .pm-detail textarea:focus { outline:none; border-color:var(--em-line); }
.pm-detail input[type=file] { font-size:12px; color:var(--pm-ash); }
.pm-tabs { display:flex; gap:0; border-bottom:1px solid var(--pm-line); margin-top:4px; }
.pm-tab { background:none; border:0; border-bottom:2px solid transparent; color:var(--pm-ash); padding:8px 14px; font:inherit; font-size:13px; cursor:pointer; margin-bottom:-1px; }
.pm-tab.on { color:var(--em-2); border-bottom-color:var(--em); }
.pm-detail textarea { width:100%; min-height:260px; flex:1; background:#0c1013; color:var(--pm-paper); border:1px solid var(--pm-line); border-top:0; border-radius:0 0 8px 8px; padding:12px; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:12.5px; line-height:1.55; resize:vertical; }
.pm-preview { min-height:260px; border:1px solid var(--pm-line); border-top:0; border-radius:0 0 8px 8px; padding:14px 16px; font-size:13.5px; line-height:1.6; overflow-y:auto; }
.pm-preview[hidden] { display:none; }
.pm-preview h1,.pm-preview h2,.pm-preview h3,.pm-preview h4 { font-family:'JetBrains Mono',monospace; color:var(--pm-paper); margin:0.8em 0 0.35em; line-height:1.25; }
.pm-preview h1 { font-size:18px; } .pm-preview h2 { font-size:16px; } .pm-preview h3 { font-size:14px; }
.pm-preview p { margin:0 0 0.7em; } .pm-preview ul { margin:0 0 0.7em; padding-left:1.2em; }
.pm-preview code { font-family:'IBM Plex Mono',monospace; font-size:0.92em; color:var(--em-2); background:var(--em-soft); padding:1px 5px; border-radius:4px; }
.pm-preview pre { background:#0c1013; border:1px solid var(--pm-line); border-radius:8px; padding:10px 12px; overflow-x:auto; font-family:'IBM Plex Mono',monospace; font-size:12px; }
.pm-detail-foot { display:flex; align-items:center; gap:8px; padding:14px 22px; border-top:1px solid var(--pm-line); }
.pm-detail-foot .pm-d-save { margin-left:auto; }

/* ---- Avatar picker (detail pane) ---- */
.pm-avrow { display:flex; align-items:flex-start; gap:14px; }
.pm-avprev { flex:0 0 64px; width:64px; height:64px; border-radius:50%; overflow:hidden; background:rgba(16,185,129,0.10); box-shadow:inset 0 0 0 1px var(--em-line); display:block; }
.pm-avprev img { width:100%; height:100%; object-fit:cover; display:block; }
.pm-avacts { flex:1; min-width:0; display:flex; flex-direction:column; gap:8px; }
.pm-avbtns { display:flex; gap:8px; flex-wrap:wrap; }
.pm-avacts .pm-hint { margin:0; }
.pm-avacts .pm-hint.err { color:var(--bad); }
.pm3 .btn.pm-avclear { color:var(--pm-ash); }
.pm3 .btn.pm-avclear:hover { color:var(--bad); border-color:rgba(248,113,113,0.45); }
.pm3 .btn.pm-avclear[hidden] { display:none; }

/* ---- Tag chip input ---- */
.pm-tagbox { display:flex; flex-wrap:wrap; gap:6px; align-items:center; background:#0c1013; border:1px solid var(--pm-line); border-radius:8px; padding:7px 8px; cursor:text; }
.pm-tagbox:focus-within { border-color:var(--em-line); }
.pm-chip { display:inline-flex; align-items:center; gap:5px; background:var(--em-soft); color:var(--em-2); border:1px solid var(--em-line); border-radius:999px; padding:1px 5px 1px 9px; font-size:12px; line-height:1.7; }
.pm-chip-x { background:none; border:none; color:inherit; cursor:pointer; font-size:14px; line-height:1; padding:0 2px; opacity:0.7; }
.pm-chip-x:hover { opacity:1; }
.pm-tagbox input.pm-f-tags-input { flex:1; min-width:8ch; border:none !important; background:none !important; padding:2px !important; outline:none; color:var(--pm-paper); font:inherit; font-size:13px; }

/* ---- Buttons / messages (scoped overrides on the shared .btn) ---- */
.pm3 .btn { font-size:12px; padding:7px 13px; border-radius:7px; border:1px solid var(--pm-line-2); background:transparent; color:var(--pm-bone); }
.pm3 .btn:hover { background:rgba(255,255,255,0.05); border-color:var(--pm-ash); }
/* The one .btn that's an <a>, not a <button>: out to the Persona Registry. */
.pm3 a.btn { display:inline-flex; align-items:center; text-decoration:none; line-height:1.5; }
.pm3 a.btn:hover { text-decoration:none; color:var(--pm-paper); }
.pm3 .pm-registry { color:var(--em-2); border-color:var(--em-line); }
.pm3 .pm-registry:hover { background:var(--em-soft); border-color:var(--em); }
.pm3 .pm-hint a { color:var(--em-2); }
.pm3 .btn-primary { background:var(--em); color:#062019; border-color:var(--em); font-weight:600; }
.pm3 .btn-primary:hover { background:transparent; color:var(--em-2); box-shadow:inset 0 0 0 1px var(--em); }
.pm3 .btn-danger { color:var(--bad); border-color:rgba(248,113,113,0.45); background:rgba(248,113,113,0.07); }
.pm3 .btn-danger:hover { background:var(--bad); color:#1a0808; border-color:var(--bad); }
.pm-msg { font-size:12px; }
.pm-msg.err { color:var(--bad); } .pm-msg.ok { color:var(--em-2); }
.pm-hint { font-size:12px; color:var(--pm-ash); }
.pm-check { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--pm-bone); cursor:pointer; }
.pm-check input { width:auto; accent-color:var(--em); }

/* ---- Bulk-select mode ---- */
.pm-sel { display:none; width:16px; height:16px; cursor:pointer; accent-color:var(--em); }
.pm3.pm-selecting .pm-sel { display:block; }
.pm3.pm-selecting .pm-row { grid-template-columns:auto 46px 1fr 200px 220px 92px; }
.pm-selactions { position:fixed; left:50%; transform:translateX(-50%); bottom:1.4rem; z-index:60; display:flex; gap:8px; align-items:center; background:#14191e; border:1px solid var(--pm-line-2); border-radius:12px; padding:9px 12px; box-shadow:0 12px 38px rgba(0,0,0,0.6); }
.pm-selactions[hidden] { display:none; }
.pm-sel-count { font-size:12px; color:var(--pm-ash); min-width:9ch; }

/* ---- Import modal ---- */
.pm-modal { position:fixed; inset:0; z-index:70; display:none; align-items:flex-start; justify-content:center; background:rgba(3,5,6,0.66); padding:8vh 16px; }
.pm-modal.open { display:flex; }
.pm-modal-card { width:100%; max-width:560px; background:#0c1013; border:1px solid var(--pm-line-2); border-radius:14px; padding:20px 22px; max-height:84vh; overflow-y:auto; }
.pm-modal-card h3 { margin:0 0 4px; font-family:'JetBrains Mono',monospace; font-size:17px; color:var(--pm-paper); }
/* `.pm-l` is inline elsewhere (it sits beside its field in the detail pane).
   In this modal each label owns a row, and inline let "Target group" and
   "Markdown files, images, or .zip" run together on one line with the group
   dropdown wedged between them. Scoped here so the detail pane is untouched. */
.pm-modal-card .pm-l { display:block; margin-top:14px; }

/* Drop zone around the file picker. The picker stays inside it rather than
   being replaced: dragging is a convenience, and a dashed box with no visible
   input reads as the only way in. `.over` is applied while a drag is over the
   whole modal card, not just this box, so a near-miss still lands. */
.pm-imp-drop { margin-top:6px; padding:14px; border:1px dashed var(--pm-line-2); border-radius:10px;
               display:flex; flex-direction:column; gap:8px; align-items:flex-start;
               background:rgba(255,255,255,0.015); transition:border-color .12s, background .12s; }
.pm-imp-drop.over { border-color:var(--em); background:var(--em-soft); }
.pm-imp-drop-hint { font-size:12.5px; line-height:1.5; color:var(--pm-ash); }
.pm-imp-drop-hint code { font-family:'JetBrains Mono',monospace; font-size:11.5px; }
.pm-imp-drop-or { opacity:0.7; font-style:italic; }
.pm-imp-picked { font-size:12px; color:var(--pm-paper); font-family:'JetBrains Mono',monospace; }
.pm-imp-picked:empty { display:none; }

/* ---- Mobile: collapse to drawer (rail + list stacked; detail slides over) ---- */
@media (max-width:900px) {
  .pm3 { grid-template-columns:1fr; grid-template-rows:auto 1fr; height:calc(100dvh - var(--topbar-h)); }
  .pm-rail { border-right:0; border-bottom:1px solid var(--pm-line); max-height:38vh; }
  .pm-detail { position:fixed; top:var(--topbar-h); right:0; bottom:0; width:min(440px,92vw); z-index:65; background:#07090a; transform:translateX(101%); transition:transform .22s cubic-bezier(0.16,1,0.3,1); box-shadow:-18px 0 50px rgba(0,0,0,0.5); }
  .pm-detail.open { transform:translateX(0); }
  .pm-dclose { display:block; }
}
@media (prefers-reduced-motion: reduce) { .pm-detail { transition:none; } }
</style>"""
