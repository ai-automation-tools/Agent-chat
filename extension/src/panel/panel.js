/**
 * AgentBattleground — side panel entry point.
 *
 * The operator surface, and the only place the loop is closed:
 *
 *   capture page → preview → open arena → hand off to a CLI →
 *   (agent drafts over MCP) → review → type into the page
 *
 * This file is wiring only. The work lives in `lib/`:
 *
 *   state.js        shared state + DOM helpers
 *   settings.js     chrome.storage-backed settings
 *   bridge.js       every HTTP call to the Agent-Chat web UI
 *   permissions.js  per-origin access, requested from a gesture
 *   capture.js      injecting src/capture.js and folding frames together
 *   arena.js        arena lifecycle, review poll, auto re-capture
 *   compose.js      the page's reply box — types, never submits
 *   drafts.js       the review queue and the verdict gate
 *   view.js         rendering: preview, handoff, arena, drafts
 *
 * The one rule the whole panel enforces: **nothing is ever submitted.**
 * Approving types text into the page's own composer and stops there.
 *
 * Two things here look fussier than they need to be, on purpose:
 *
 * * `requestPageAccess()` is always called as the *first* statement of a click
 *   handler, never after an `await`. Firefox discards the user gesture across
 *   a microtask boundary and then refuses `permissions.request`, so a handler
 *   that awaits first works in Chrome and silently fails in Firefox.
 * * Auto re-capture never asks for a permission it doesn't already hold. A
 *   background timer that could raise a permission prompt is a trap.
 */

import { $, state } from './lib/state.js';
import {
  clampSeconds,
  loadSettings,
  persistSettings,
  saveCustomPersona,
  saveSettings,
  syncCustomPersona,
} from './lib/settings.js';
import { loadHealth, loadRoster } from './lib/bridge.js';
import { requestPageAccess } from './lib/permissions.js';
import { renderHints, runCapture } from './lib/capture.js';
import {
  closeArena,
  createArena,
  getLink,
  openArena,
  recapture,
  startAutoRecapture,
  stopAutoRecapture,
  stopPolling,
  unlinkArena,
} from './lib/arena.js';
import { render, wireHandoff } from './lib/view.js';

// ---------------------------------------------------------------------------
// Tab tracking
// ---------------------------------------------------------------------------

async function refreshTab() {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!active) return;
  const changed = state.tab?.id !== active.id || state.tab?.url !== active.url;
  state.tab = { id: active.id, url: active.url || '', title: active.title || '' };
  $('page-title').textContent = state.tab.title || '—';
  $('page-url').textContent = state.tab.url || '—';
  if (!changed) return;

  state.capture = null;
  state.replyTo = null;
  state.pendingHints = [];
  renderHints();
  $('capture-summary').textContent = '';
  $('capture-summary').className = 'msg';
  $('cast-card').classList.add('hidden');

  const link = await getLink(state.tab.id);
  if (link) {
    await openArena(link.arenaId);
  } else {
    state.arena = null;
    stopPolling();
    stopAutoRecapture();
    render();
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

$('toggle-settings').onclick = () => $('settings').classList.toggle('hidden');

$('save-settings').onclick = async () => {
  await saveSettings();
  await loadHealth();
  const ok = await loadRoster();
  const msg = $('settings-msg');
  msg.className = ok ? 'msg ok' : 'msg err';
  msg.textContent = ok ? 'Saved and connected.' : 'Saved, but the bridge didn’t answer.';
};

$('test-bridge').onclick = async () => {
  await saveSettings();
  const health = await loadHealth();
  const ok = await loadRoster();
  const msg = $('settings-msg');
  msg.className = ok ? 'msg ok' : 'msg err';
  if (ok) {
    msg.textContent = `Connected to ${state.settings.bridgeUrl}.`;
  } else if (health) {
    // healthz answered but roster didn't: the bridge is up and rejecting us.
    msg.textContent = health.token_required
      ? 'The bridge is up but refused the call — check the bearer token above.'
      : `The bridge is up but the call failed${health.error ? `: ${health.error}` : '.'}`;
  } else {
    msg.textContent = `No answer from ${state.settings.bridgeUrl} — is the web UI running?`;
  }
};

// Gesture-first: `requestPageAccess()` runs before the first await so Firefox
// still counts this as a user action.
$('capture').onclick = () => {
  const access = requestPageAccess();
  // The error is already on screen via `capture-summary`; swallow the reject.
  if (state.arena) return recapture(access).catch(() => {});
  return runCapture(access).then((data) => {
    state.capture = data;
    state.replyTo = null;
    state.previewOpen = Boolean(data);
    render();
  });
};

$('recapture').onclick = () => recapture(requestPageAccess()).catch(() => {});
$('close-arena').onclick = closeArena;
$('unlink').onclick = async () => {
  await unlinkArena(state.tab.id);
  state.arena = null;
  stopPolling();
  stopAutoRecapture();
  render();
};

$('open-arena').onclick = createArena;

// Picking "✎ custom instructions…" swaps the registry card for one the
// operator writes here. Both halves persist, so a half-written card survives
// switching pickers, closing the panel, or moving to another tab.
$('persona').onchange = async () => {
  state.settings.persona = $('persona').value;
  syncCustomPersona();
  await persistSettings();
};

$('persona-name').onchange = saveCustomPersona;
$('persona-instructions').onchange = saveCustomPersona;

$('auto-recapture').onchange = async () => {
  state.settings.autoRecapture = $('auto-recapture').checked;
  await persistSettings();
  if (state.settings.autoRecapture) startAutoRecapture();
  else stopAutoRecapture();
};

$('auto-seconds').onchange = async () => {
  state.settings.autoSeconds = clampSeconds($('auto-seconds').value);
  $('auto-seconds').value = state.settings.autoSeconds;
  await persistSettings();
  if (state.settings.autoRecapture) startAutoRecapture();
};

wireHandoff();

chrome.tabs.onActivated.addListener(refreshTab);
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (tabId === state.tab?.id && (info.status === 'complete' || info.title)) {
    refreshTab();
  }
});

(async function init() {
  await loadSettings();
  await loadHealth();
  await loadRoster();
  await refreshTab();
})();
