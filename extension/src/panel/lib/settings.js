/**
 * AgentBattleground — panel settings, persisted in `chrome.storage.local`.
 *
 * Nothing here is a secret except `bridgeToken`, which is the operator's own
 * loopback token; it never leaves the machine.
 */

import { CUSTOM_PERSONA, $, DEFAULTS, MIN_AUTO_SECONDS, state } from './state.js';

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

// ---------------------------------------------------------------------------
// The custom persona card
//
// The picker's "✎ custom instructions…" option is a whole persona typed into
// the panel rather than chosen from the registry. It's stored here rather than
// in the registry on purpose: the operator is casting *this* arena, not adding
// a character to the roster, and the arena row snapshots the body anyway.
// ---------------------------------------------------------------------------

/** True when the picker is on the custom option. */
export function isCustomPersona() {
  return $('persona').value === CUSTOM_PERSONA;
}

/** Show or hide the card editor, and fill it from the last saved draft. */
export function syncCustomPersona() {
  const on = isCustomPersona();
  $('custom-persona').classList.toggle('hidden', !on);
  if (!on) return;
  $('persona-name').value = state.settings.personaName || '';
  $('persona-instructions').value = state.settings.personaInstructions || '';
}

/** Pull the card editor into `state.settings` and persist it.
 *
 * Kept even when the picker moves off custom, so switching to a registry
 * persona to compare and switching back doesn't throw the card away. */
export async function saveCustomPersona() {
  state.settings.personaName = $('persona-name').value.trim();
  state.settings.personaInstructions = $('persona-instructions').value.trim();
  await persistSettings();
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
