/**
 * AgentBattleground — arena lifecycle: open, re-capture, re-target, close.
 *
 * Also owns the two timers: the 3s review poll and the optional auto
 * re-capture. Both are panel-side on purpose (see `bridge.js`), and neither
 * can post anything — auto re-capture only refreshes what the agent may
 * *read*.
 */

import {
  ext,
  MAX_AUTO_FAILURES,
  POLL_MS,
  RANDOM_PERSONA,
  $,
  say,
  state,
} from './state.js';
import { api, bridgeUp, setBridgeStatus } from './bridge.js';
import { hasPageAccess } from './permissions.js';
import { isCustomPersona, persistSettings, saveCustomPersona } from './settings.js';
import { runCapture } from './capture.js';
import { render, renderAutoStatus } from './view.js';

// ---------------------------------------------------------------------------
// Per-tab arena link + toolbar badge
// ---------------------------------------------------------------------------

const linkKey = (tabId) => `arena:${tabId}`;

function setBadge(tabId, text, color) {
  ext.runtime.sendMessage({ type: 'badge', tabId, text, color });
}

export async function linkArena(tabId, arenaId, url) {
  await ext.storage.local.set({ [linkKey(tabId)]: { arenaId, url } });
  setBadge(tabId, String(arenaId));
}

export async function unlinkArena(tabId) {
  await ext.storage.local.remove(linkKey(tabId));
  setBadge(tabId, '');
}

export async function getLink(tabId) {
  const stored = await ext.storage.local.get(linkKey(tabId));
  return stored[linkKey(tabId)] || null;
}

/** The reply target in force right now — the arena's if there is one. */
export function currentTarget() {
  return state.arena ? state.arena.arena.reply_to || null : state.replyTo;
}

/**
 * Point the agent at one captured post (or clear the target with `null`).
 *
 * Before an arena exists this is local; afterwards it patches the arena, so
 * the agent's next `get_arena` sees the new target.
 */
export async function setReplyTarget(postId) {
  if (!state.arena) {
    state.replyTo = state.replyTo === postId ? null : postId;
    render();
    return;
  }
  const next = state.arena.arena.reply_to === postId ? '' : postId;
  try {
    await api(`/arenas/${state.arena.arena.id}`, {
      method: 'POST',
      body: { reply_to: next },
    });
    await openArena(state.arena.arena.id);
  } catch (err) {
    say('arena-msg', String(err.message || err), 'err');
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

export async function openArena(arenaId) {
  try {
    state.arena = await api(`/arenas/${arenaId}`);
    bridgeUp();
    flagNewDrafts();
    startPolling();
    startAutoRecapture();
  } catch (err) {
    // Arena deleted out from under us (or the bridge is down) — drop the link
    // rather than poll a 404 forever.
    if (String(err).includes('no arena')) {
      await unlinkArena(state.tab.id);
      state.arena = null;
      stopAutoRecapture();
    } else {
      setBridgeStatus(false, String(err));
    }
  }
  render();
}

/**
 * The `persona*` half of the create body, from whichever way the operator cast.
 *
 * Three shapes, and the bridge takes exactly one of them:
 *
 * * a registry slug (including the one the 🎲 draw landed on),
 * * a one-off card typed into the panel — `persona_instructions`, with no
 *   slug, since there's no registry row to point at,
 * * nothing, and the agent argues as itself.
 *
 * Returns `null` when custom is selected but empty, having already said why.
 */
function personaBody() {
  if (isCustomPersona()) {
    const instructions = $('persona-instructions').value.trim();
    if (!instructions) {
      say('arena-msg', 'Write the custom persona’s instructions first.', 'err');
      $('persona-instructions').focus();
      return null;
    }
    return {
      persona_instructions: instructions,
      persona_name: $('persona-name').value.trim() || null,
    };
  }

  let slug = $('persona').value;
  if (slug === RANDOM_PERSONA) {
    // Grouped options only, so neither sentinel can be drawn.
    const options = [...$('persona').querySelectorAll('optgroup option')];
    slug = options.length
      ? options[Math.floor(Math.random() * options.length)].value
      : '';
  }
  return { persona: slug || null };
}

export async function createArena() {
  const cast = personaBody();
  if (!cast) return;
  say('arena-msg', 'Opening arena…');

  state.settings.agent = $('agent').value;
  state.settings.persona = $('persona').value;
  await saveCustomPersona();  // persists the card and everything above it

  try {
    const data = await api('/arenas', {
      method: 'POST',
      body: {
        url: state.capture.url,
        site: state.capture.site,
        title: state.capture.title,
        thread: state.capture.posts,
        stance: $('stance').value.trim() || null,
        reply_to: state.replyTo || null,
        agent_id: $('agent').value,
        ...cast,
      },
    });
    await linkArena(state.tab.id, data.arena.id, state.capture.url);
    say('arena-msg', `Arena ${data.arena.id} is open.`, 'ok');
    await openArena(data.arena.id);
  } catch (err) {
    say('arena-msg', String(err.message || err), 'err');
  }
}

export async function recapture(access, { silent = false } = {}) {
  const data = await runCapture(access, { silent });
  if (!data || !state.arena) return 0;
  // Keep the preview showing the same posts the bridge now holds.
  state.capture = data;
  try {
    const res = await api(`/arenas/${state.arena.arena.id}/capture`, {
      method: 'POST',
      body: { thread: data.posts },
    });
    if (!silent || res.posts_added) {
      say(
        'capture-summary',
        `Merged capture — ${res.posts_added} new post${
          res.posts_added === 1 ? '' : 's'
        } for the agent.`,
        'ok'
      );
    }
    if (res.posts_added || !silent) await openArena(state.arena.arena.id);
    else render();
    return res.posts_added;
  } catch (err) {
    if (!silent) say('capture-summary', String(err.message || err), 'err');
    throw err;
  }
}

export async function closeArena() {
  if (!state.arena) return;
  await api(`/arenas/${state.arena.arena.id}`, {
    method: 'POST',
    body: { status: 'closed' },
  });
  await openArena(state.arena.arena.id);
}

// ---------------------------------------------------------------------------
// Review polling
// ---------------------------------------------------------------------------

export function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    if (!state.arena) return stopPolling();
    // Don't yank a draft out from under an operator mid-edit.
    if (document.activeElement?.tagName === 'TEXTAREA') return;
    try {
      const fresh = await api(`/arenas/${state.arena.arena.id}`);
      const changed =
        fresh.drafts.length !== state.arena.drafts.length ||
        fresh.arena.updated_at !== state.arena.arena.updated_at;
      state.arena = fresh;
      bridgeUp();
      if (changed) {
        flagNewDrafts();
        render();
      }
    } catch (err) {
      setBridgeStatus(false, String(err));
    }
  }, POLL_MS);
}

export function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

/**
 * Raise the toolbar badge when a draft the operator hasn't seen shows up.
 *
 * The panel may well be closed while the agent is writing, and a review queue
 * nobody looks at is the slowest part of the loop.
 */
export function flagNewDrafts() {
  if (!state.arena || !state.tab?.id) return;
  const pending = state.arena.drafts.filter((d) => d.status === 'pending');
  const fresh = pending.filter((d) => !state.seenDrafts.has(d.id));
  for (const d of state.arena.drafts) state.seenDrafts.add(d.id);
  if (fresh.length) {
    setBadge(state.tab.id, pending.length > 1 ? `${pending.length}!` : '!', '#d9a13b');
  } else if (!pending.length) {
    setBadge(state.tab.id, String(state.arena.arena.id));
  }
}

// ---------------------------------------------------------------------------
// Auto re-capture
//
// So the agent sees replies to its own post without the operator clicking
// Re-capture. Deliberately conservative: it never prompts for a permission,
// never runs on a tab that has drifted off the arena's page, never fires while
// a draft is being edited, and disables itself after a run of failures rather
// than hammering a bridge that's gone.
// ---------------------------------------------------------------------------

export function startAutoRecapture() {
  stopAutoRecapture();
  if (!state.settings.autoRecapture || !state.arena) return;
  state.autoFailures = 0;
  state.autoTimer = setInterval(autoTick, state.settings.autoSeconds * 1000);
  renderAutoStatus();
}

export function stopAutoRecapture() {
  if (state.autoTimer) clearInterval(state.autoTimer);
  state.autoTimer = null;
  renderAutoStatus();
}

/** Every reason to skip a tick, in the order that's cheapest to check. */
async function autoSkipReason() {
  if (!state.settings.autoRecapture) return 'off';
  if (!state.arena || !state.tab?.id) return 'no arena';
  if (state.arena.arena.status !== 'open') return 'arena closed';
  if (state.captureBusy) return 'busy';
  const editing = document.activeElement;
  if (editing && (editing.tagName === 'TEXTAREA' || editing.tagName === 'INPUT')) {
    return 'editing';
  }
  const link = await getLink(state.tab.id);
  if (!link || link.arenaId !== state.arena.arena.id) return 'tab not linked';
  if (!(await hasPageAccess())) return 'no access to this page';
  return null;
}

async function autoTick() {
  const skip = await autoSkipReason();
  if (skip) {
    renderAutoStatus(skip);
    return;
  }
  try {
    const added = await recapture(null, { silent: true });
    state.autoFailures = 0;
    state.lastAutoAt = Date.now();
    renderAutoStatus(added ? `+${added} new` : 'no new posts');
  } catch (err) {
    state.autoFailures += 1;
    if (state.autoFailures >= MAX_AUTO_FAILURES) {
      state.settings.autoRecapture = false;
      $('auto-recapture').checked = false;
      await persistSettings();
      stopAutoRecapture();
      renderAutoStatus(
        `paused after ${MAX_AUTO_FAILURES} failures — ${err.message || err}`
      );
      return;
    }
    renderAutoStatus(`failed (${state.autoFailures}/${MAX_AUTO_FAILURES})`);
  }
}
