/**
 * AgentBattleground — panel settings, persisted in `chrome.storage.local`.
 *
 * Nothing here is a secret except `bridgeToken`, which is the operator's own
 * loopback token; it never leaves the machine.
 */

import { $, DEFAULTS, MIN_AUTO_SECONDS, state } from './state.js';

export function clampSeconds(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULTS.autoSeconds;
  return Math.max(MIN_AUTO_SECONDS, Math.min(3600, Math.round(n)));
}

export async function loadSettings() {
  const stored = await chrome.storage.local.get('settings');
  state.settings = { ...DEFAULTS, ...(stored.settings || {}) };
  state.settings.autoSeconds = clampSeconds(state.settings.autoSeconds);
  $('bridge-url').value = state.settings.bridgeUrl;
  $('bridge-token').value = state.settings.bridgeToken;
  $('disclose').checked = state.settings.disclose;
  $('disclosure-text').value = state.settings.disclosureText;
  $('auto-recapture').checked = state.settings.autoRecapture;
  $('auto-seconds').value = state.settings.autoSeconds;
}

export async function persistSettings() {
  await chrome.storage.local.set({ settings: state.settings });
}

/** Pull the Settings form into `state.settings` and persist it. */
export async function saveSettings() {
  state.settings = {
    ...state.settings,
    bridgeUrl:
      $('bridge-url').value.trim().replace(/\/$/, '') || DEFAULTS.bridgeUrl,
    bridgeToken: $('bridge-token').value.trim(),
    disclose: $('disclose').checked,
    disclosureText: $('disclosure-text').value,
  };
  await persistSettings();
}
