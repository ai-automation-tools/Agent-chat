"""CSS / JS / static-asset constants for the web UI pages.

Pure data — no imports, no logic. Page templates live with their renderers
under ``web.render``; only reusable style/script constants live here.
"""


# ---------------------------------------------------------------------------
# HTML rendering (inline — fine for a small local app)
# ---------------------------------------------------------------------------

BASE_CSS = """
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
}
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

/* Topbar — thin fixed bar mirroring the apex's `h-12 bg-[#060606]/95
   backdrop-blur border-b border-zinc-900`. */
.topbar {
  position: sticky; top: 0; z-index: 40;
  height: 48px;
  background: rgba(6, 6, 6, 0.95);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-bottom: 1px solid #18181b;
}
.topbar-inner {
  height: 100%;
  display: flex; align-items: center; gap: 16px;
  padding: 0 24px;
  max-width: 1240px; margin: 0 auto;
}
.topbar .mark {
  display: inline-flex; align-items: center; gap: 10px;
  text-decoration: none; color: var(--text);
  font-weight: 600; font-size: 14px;
  letter-spacing: -0.005em;
}
.topbar .mark .glyph {
  width: 28px; height: 28px;
  background: var(--good);
  border-radius: 6px;
  display: grid; place-items: center;
  color: #09090b;
  font-weight: 800; font-size: 14px; line-height: 1;
}
.topbar .crumb {
  color: var(--muted-2);
  font-size: 13px;
}
.topbar .crumb a { color: var(--muted); text-decoration: none; }
.topbar .crumb a:hover { color: var(--text); }
.topbar .crumb strong { color: var(--text); font-weight: 500; }
.topbar nav {
  margin-left: auto;
  display: flex; align-items: center; gap: 6px;
}
.topbar nav a {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  color: var(--muted);
  text-decoration: none;
  border: 1px solid transparent;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.topbar nav a:hover {
  color: var(--text);
  background: rgba(24, 24, 27, 0.6);
  border-color: rgba(63, 63, 70, 0.6);
}
.topbar nav a.cta {
  color: var(--good);
  border-color: rgba(16, 185, 129, 0.32);
  background: rgba(16, 185, 129, 0.08);
}
.topbar nav a.cta:hover {
  background: var(--good);
  color: #09090b;
  border-color: var(--good);
}

main {
  padding: 40px 24px 64px;
  max-width: 1100px;
  margin: 0 auto;
}
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


# ---------------------------------------------------------------------------
# Homepage CSS — apex-aligned. Mirrors mikesailab.com: #060606 canvas,
# Inter font, zinc-100 text, emerald-400 'Live' pills, emerald-500 accents on
# hover and CTAs. Tailwind utility classes drive most layout via the CDN
# <script> in <head>; this stylesheet only carries rules Tailwind can't
# express ergonomically (the live-pill pulse animation, code-block tints,
# and the home-only `.live-tile` SVG glyph hover transitions).
# ---------------------------------------------------------------------------

HOME_CSS = """
body.home { font-family: 'IBM Plex Sans', 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif; }
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
@keyframes pulse-sky { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Live pill — emerald-400 dot + uppercase label, the apex 'Live' convention. */
.live-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.12em; color: #10b981;
  font-weight: 500;
}
.live-pill .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #10b981; box-shadow: 0 0 6px #10b981;
  animation: pulse-sky 1.6s ease-in-out infinite;
}
.live-pill.idle { color: #71717a; }
.live-pill.idle .dot {
  background: #71717a; box-shadow: none; animation: none;
}

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

/* (Old console-arena CSS removed — apex match uses Tailwind CDN +
   inline utility classes for layout. See HOME_CSS rules above for the
   small handful of rules still emitted server-side.) */
"""


# Styles for the /orchestrate route. Lives inside the _layout shell, so
# tokens from BASE_CSS (--bg, --text, --accent, --border, --good, --bad)
# are available without redeclaration. Scoped under `.orch-shell` so the
# form rules cannot leak into the conversations index / detail pages.
ORCHESTRATE_CSS = """
.orch-shell { max-width: 760px; margin: 32px auto; padding: 0 24px; }
.orch-head h2 {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 26px; font-weight: 800; letter-spacing: -0.01em;
  margin: 0 0 8px 0;
}
.orch-head p { color: var(--muted); margin: 0 0 28px 0; max-width: 60ch; }

.orch-form { display: flex; flex-direction: column; gap: 22px; }
.orch-form section { display: flex; flex-direction: column; gap: 8px; }
.orch-form .lbl {
  font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted-2); font-weight: 600;
}
.orch-form .hint { color: var(--muted-2); font-size: 12px; margin: 0; }

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

.orch-submit {
  margin-top: 4px;
  padding: 12px 18px;
  background: var(--accent);
  color: #09090b;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  letter-spacing: -0.005em;
}
.orch-submit:hover { background: var(--accent-strong); }
.orch-submit:disabled { opacity: 0.5; cursor: not-allowed; }

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


# Matches the visual convention of the other apps on mikesailab.com
# (edge-spectrum, prompts): emerald rounded square with the first letter
# of the app drawn as a stroke. 32x32 viewBox, rx=6, fill #10b981, glyph
# stroke #09090b at width 3. The "A" is two diagonals plus a crossbar.
# Emerald (#10b981) is the in-app brand accent across every page (the
# 2026-06-29 retheme unified the app on emerald + JetBrains Mono / IBM Plex),
# matching this favicon and the sister apps on mikesailab.com.
FAVICON_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    b"<rect width='32' height='32' rx='6' fill='#10b981'/>"
    b"<path d='M 7 24 L 16 8 L 25 24 M 11 18 L 21 18' "
    b"stroke='#09090b' stroke-width='3' stroke-linecap='round' "
    b"stroke-linejoin='round' fill='none'/>"
    b"</svg>"
)

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
  .cast { margin: 0 0 1.25rem; padding: 1rem 1.15rem; border: 1px solid var(--border, #27272a);
          border-radius: 10px; background: rgba(255,255,255,0.015); }
  .cast > h3 { margin: 0 0 0.6rem; font-size: 13px; text-transform: uppercase;
               letter-spacing: 0.08em; color: var(--muted, #a1a1aa); }
  .cast-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.4rem; }
  .cast-item details { border: 1px solid var(--border, #27272a); border-radius: 8px; overflow: hidden; }
  .cast-item summary { cursor: pointer; padding: 0.55rem 0.7rem; display: flex; align-items: baseline;
                       gap: 0.6rem; list-style: none; }
  .cast-item summary::-webkit-details-marker { display: none; }
  .cast-item summary:hover { background: rgba(255,255,255,0.03); }
  .cast-cli { font-family: ui-monospace, monospace; font-size: 12px; color: #10b981;
              background: rgba(16,185,129,0.08); padding: 1px 7px; border-radius: 5px; }
  .cast-name { font-weight: 600; }
  .cast-slug { font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted, #a1a1aa); }
  .cast-count { margin-left: auto; font-family: ui-monospace, monospace; font-size: 11px;
                color: var(--muted, #a1a1aa); }
  .cast-card { padding: 0.4rem 0.9rem 0.9rem; border-top: 1px solid var(--border, #27272a);
               font-size: 13px; color: var(--muted, #d4d4d8); }
  .who-cli { font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted, #a1a1aa);
             font-weight: 400; opacity: 0.8; }
</style>"""

# Two-pane conversations console: left rail (search + filters + sort + list)
# and a main transcript-reader pane. Emerald-accented, scoped to `.cv2` so it
# overrides the narrow `_layout` <main> column (full-bleed below the 48px
# topbar). Clicking a conversation loads its transcript directly in the main
# pane — no intermediate preview. The rail collapses (localStorage-persisted);
# `?fullscreen=1` drops the rail entirely for a distraction-free reader.
_CONV_CSS = """\
<style>
main:has(.cv2) { max-width:none; padding:0; margin:0; }
.cv2 {
  --em:#10b981; --em-soft:rgba(16,185,129,0.10); --em-line:rgba(16,185,129,0.34);
  --cv-line:rgba(255,255,255,0.07); --cv-ash:#71717a; --cv-bone:#c8ccd1; --cv-paper:#e7eaee;
  height:calc(100dvh - 48px);
  display:grid; grid-template-columns:320px minmax(0,1fr);
  background:#07090a;
}
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
.cv-status { width:7px; height:7px; border-radius:50%; flex:none; background:var(--cv-ash); }
.cv-status.cv-active { background:var(--em); box-shadow:0 0 6px var(--em); animation:pulse 1.8s ease-in-out infinite; }
/* ---- rail ---- */
.cv-rail { border-right:1px solid var(--cv-line); display:flex; flex-direction:column; min-height:0;
  background:rgba(255,255,255,0.012); }
.cv2.rail-hidden { grid-template-columns:0 minmax(0,1fr); }
.cv2.rail-hidden .cv-rail { display:none; }
#cv-rail-open { position:fixed; left:12px; top:58px; z-index:45; display:none; background:#0c1013; }
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
.cv-list { flex:1; overflow-y:auto; padding:8px; display:flex; flex-direction:column; gap:2px; }
.cv-item { position:relative; border-radius:8px; border-left:2px solid transparent; }
.cv-item:hover { background:rgba(255,255,255,0.03); }
.cv-item.active { background:var(--em-soft); border-left-color:var(--em); }
.cv-link { display:flex; gap:9px; align-items:flex-start; padding:8px 11px; text-decoration:none;
  color:var(--cv-bone); }
.cv-link:hover { text-decoration:none; }
.cv-link .cv-status { margin-top:5px; }
.cv-item-main { min-width:0; flex:1; display:flex; flex-direction:column; gap:2px; }
.cv-topic { font-size:13px; font-weight:500; color:var(--cv-paper); line-height:1.3;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:16px; }
.cv-item.active .cv-topic { color:#fff; }
.cv-cast { font-size:11.5px; color:var(--cv-bone); opacity:0.75; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }
.cv-meta { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10px; color:var(--cv-ash);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cv-nomatch { display:none; padding:18px 14px; color:var(--cv-ash);
  font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:12px; text-align:center; }
.cv-list-empty { padding:24px 14px; color:var(--cv-ash); font-size:12.5px; text-align:center; line-height:1.6; }
.cv-del { position:absolute; top:8px; right:8px; width:22px; height:22px; border:0; border-radius:6px;
  background:rgba(20,25,30,0.85); color:var(--cv-ash); cursor:pointer; font-size:15px; line-height:1;
  opacity:0; transition:opacity .12s ease; }
.cv-item:hover .cv-del { opacity:1; }
.cv-del:hover { background:rgba(248,113,113,0.16); color:#f87171; }
.cv-del:disabled { opacity:0.4; }
.cv-railfoot { padding:12px; border-top:1px solid var(--cv-line); }
.cv-railfoot .btn { width:100%; justify-content:center; }
/* ---- main pane ---- */
.cv-main { overflow-y:auto; min-width:0; }
.cv-read { max-width:960px; margin:0 auto; padding:26px 32px 72px; }
.cv2.cv-fullscreen .cv-read { max-width:1100px; }
.cv-read-head { margin-bottom:18px; }
.cv-eyebrow { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
.cv-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-left:auto; }
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
.cv-turn .dot { width:6px; height:6px; border-radius:50%; background:var(--em);
  box-shadow:0 0 6px var(--em); animation:pulse 1.8s ease-in-out infinite; }
.cv-read-head h1 { margin:0 0 10px; font-family:'JetBrains Mono',ui-monospace,monospace; font-size:23px;
  font-weight:800; letter-spacing:-0.01em; line-height:1.3; color:var(--cv-paper); }
.cv-read-meta { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px; color:var(--cv-ash);
  line-height:1.7; overflow-wrap:anywhere; }
.cv-read-stats { color:var(--cv-bone); opacity:0.8; }
.cv-empty { height:100%; min-height:60vh; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:14px; color:var(--cv-ash); text-align:center; padding:24px; }
.cv-empty svg { width:30px; height:30px; opacity:0.5; }
/* ---- overview (no conversation selected) ---- */
.cv-ov { max-width:720px; margin:0 auto; padding:40px 32px 72px; }
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
.cv-recent h2 { margin:0 0 10px; font-size:11px; text-transform:uppercase; letter-spacing:0.14em;
  color:var(--cv-ash); font-weight:600; }
.cv-recent ul { list-style:none; margin:0; padding:0; border:1px solid var(--cv-line);
  border-radius:10px; overflow:hidden; }
.cv-recent-row { display:flex; align-items:center; gap:11px; padding:12px 16px; text-decoration:none;
  color:var(--cv-bone); border-top:1px solid var(--cv-line); transition:background .12s ease; }
.cv-recent li:first-child .cv-recent-row { border-top:0; }
.cv-recent-row:hover { background:rgba(255,255,255,0.03); text-decoration:none; }
.cv-recent-main { min-width:0; flex:1; display:flex; flex-direction:column; gap:2px; }
.cv-recent-topic { font-size:14px; font-weight:500; color:var(--cv-paper); white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.cv-recent-sub { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:11px; color:var(--cv-ash);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cv-recent-when { flex:none; font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:10.5px;
  color:var(--cv-ash); }
.cv-ov-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:24px; }
/* ---- full screen ---- */
.cv2.cv-fullscreen { height:100dvh; grid-template-columns:minmax(0,1fr); }
body:has(.cv2.cv-fullscreen) .topbar { display:none; }
body:has(.cv2.cv-fullscreen) main { min-height:100dvh; }
/* ---- mobile ---- */
@media (max-width:900px) {
  /* minmax(0,1fr), not 1fr — an auto min would let the rail's nowrap topic
     lines set the column's min-content and force horizontal page scroll. */
  .cv2 { grid-template-columns:minmax(0,1fr); grid-template-rows:auto 1fr; height:auto;
    min-height:calc(100dvh - 48px); }
  .cv-rail { border-right:0; border-bottom:1px solid var(--cv-line); }
  .cv-list { max-height:38vh; }
  #cv-rail-open { top:auto; bottom:14px; }
  .cv-read { padding:20px 16px 56px; }
  .cv-ov { padding:28px 16px 56px; }
  .cv-stats { grid-template-columns:1fr 1fr; }
  .cv-eyebrow .cv-actions { margin-left:0; width:100%; }
}
</style>"""

_ORCH_READONLY_CSS = """
<style>
.orch-ro-card{border:1px solid rgba(255,255,255,0.10);border-radius:8px;padding:16px 18px;margin:16px 0;background:rgba(255,255,255,0.02);}
.orch-ro-card h3{margin:0 0 8px;font-size:14px;color:#e5e7eb;}
.orch-ro-card pre{margin:0 0 10px;padding:12px 14px;background:#0b0f0e;border:1px solid rgba(255,255,255,0.08);border-radius:6px;overflow-x:auto;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;color:#cbd5e1;}
.orch-ro-card p{margin:0;color:#9ca3af;font-size:13px;}
.orch-ro-foot{margin-top:18px;color:#9ca3af;font-size:13px;}
</style>
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
   full-bleed and fills the viewport below the 48px topbar. */
main:has(.pm3) { max-width:none; padding:0; margin:0; }

.pm3 {
  --em:#10b981; --em-2:#34d399; --em-soft:rgba(16,185,129,0.12);
  --em-line:rgba(16,185,129,0.34); --bad:#f87171;
  --pm-line:rgba(255,255,255,0.08); --pm-line-2:rgba(255,255,255,0.14);
  --pm-ash:#6b7480; --pm-bone:#c8ccd1; --pm-paper:#e7eaee;
  height:calc(100dvh - 48px);
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
.pm-modal-card .pm-l { margin-top:14px; }

/* ---- Mobile: collapse to drawer (rail + list stacked; detail slides over) ---- */
@media (max-width:900px) {
  .pm3 { grid-template-columns:1fr; grid-template-rows:auto 1fr; height:calc(100dvh - 48px); }
  .pm-rail { border-right:0; border-bottom:1px solid var(--pm-line); max-height:38vh; }
  .pm-detail { position:fixed; top:48px; right:0; bottom:0; width:min(440px,92vw); z-index:65; background:#07090a; transform:translateX(101%); transition:transform .22s cubic-bezier(0.16,1,0.3,1); box-shadow:-18px 0 50px rgba(0,0,0,0.5); }
  .pm-detail.open { transform:translateX(0); }
  .pm-dclose { display:block; }
}
@media (prefers-reduced-motion: reduce) { .pm-detail { transition:none; } }
</style>"""
