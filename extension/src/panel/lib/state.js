/**
 * AgentBattleground — shared panel state and small DOM helpers.
 *
 * Every other panel module imports `state` and mutates fields on it rather
 * than exporting its own `let`. That's deliberate: the modules form a couple
 * of import cycles (arena → view → drafts → arena), and a single object
 * binding is the one shape that survives them without ordering surprises.
 *
 * The same rule applies to exported functions across a cycle: declare them
 * with `function`, never `const fn = () => …`. Declarations are hoisted and
 * initialised before a module body runs, so a partially-evaluated module can
 * still be called into.
 */

/* global browser */

/**
 * The extension API namespace.
 *
 * Firefox exposes `chrome.*` as well, but only as a callback-based porting
 * aid — `browser.*` is the namespace that returns promises there. Every call
 * in this package is awaited, so a bare `chrome.` resolves to `undefined` on
 * Gecko and takes the panel down on the first `await` (`chrome.tabs.query`,
 * during init). Chrome has no `browser` global, so it falls through.
 *
 * `background.js` carries its own copy of this line rather than importing it:
 * it loads as a classic script on Firefox and must stay import-free.
 */
export const ext = typeof browser !== 'undefined' ? browser : chrome;

export const DEFAULTS = {
  bridgeUrl: 'http://127.0.0.1:8765',
  bridgeToken: '',
  disclose: true,
  disclosureText: '\n\n— drafted by an AI (Agent-Chat)',
  agent: 'claude-code',
  persona: '',
  /** The one-off card behind `persona === CUSTOM_PERSONA`. Kept even while
   *  another persona is selected, so switching away and back doesn't discard
   *  something the operator spent a while writing. */
  personaName: '',
  personaInstructions: '',
  autoRecapture: false,
  autoSeconds: 90,
};

/** Sentinel `<option>` values in the persona picker. Neither is a slug, and
 *  both must stay outside the `<optgroup>`s — the random draw picks from
 *  grouped options only, so a sentinel can never be drawn. */
export const RANDOM_PERSONA = '__random__';
export const CUSTOM_PERSONA = '__custom__';

export const POLL_MS = 3000;

/** Floor on auto re-capture. A capture is a full DOM walk plus a POST; below
 *  this it's a scraper pointed at someone else's site, not a refresh. */
export const MIN_AUTO_SECONDS = 30;
export const MAX_AUTO_FAILURES = 3;
export const MAX_POSTS = 200;

/** How much of each captured post the preview shows before eliding. */
export const PREVIEW_CHARS = 220;

export const state = {
  settings: { ...DEFAULTS },
  /** { id, url, title } for the active tab. */
  tab: null,
  /** { arena, drafts } as last read from the bridge. */
  arena: null,
  /** Last merged capture for this tab, before an arena exists. */
  capture: null,
  /** Comment-iframe origins we could still be granted. */
  pendingHints: [],
  /** Last /healthz payload — drives the token nudge. */
  health: null,
  /** Last /roster payload — personas, CLI ids, launch commands. */
  roster: null,
  /** Post id the operator picked as the reply target, pre-arena. */
  replyTo: null,
  /** Draft ids already seen, so a new one can raise the badge exactly once. */
  seenDrafts: new Set(),
  /** Expanded/collapsed memory for the capture preview. */
  previewOpen: false,

  pollTimer: null,
  autoTimer: null,
  autoFailures: 0,
  lastAutoAt: 0,
  captureBusy: false,
};

export const $ = (id) => document.getElementById(id);

/** `el('button', 'ghost', 'Copy')` — the three things every node here needs. */
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Write a `.msg` paragraph in one of its three states. */
export function say(id, text, kind = '') {
  const node = $(id);
  if (!node) return;
  node.className = `msg${kind ? ` ${kind}` : ''}`;
  node.textContent = text;
}

/** Copy to the clipboard, falling back to a hidden textarea + execCommand.
 *
 * `navigator.clipboard` needs a secure context and can still be refused in a
 * Firefox sidebar, and a copy button that silently does nothing is worse than
 * no copy button. */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* fall through */
  }
  try {
    const scratch = document.createElement('textarea');
    scratch.value = text;
    scratch.style.position = 'fixed';
    scratch.style.opacity = '0';
    document.body.append(scratch);
    scratch.select();
    const ok = document.execCommand('copy');
    scratch.remove();
    return ok;
  } catch {
    return false;
  }
}
