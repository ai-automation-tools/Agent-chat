/**
 * AgentBattleground — per-origin page access.
 *
 * Standing access: none. The extension asks per-origin, from a click, the
 * first time you capture on a domain — and asks again, separately, for a
 * third-party comment iframe.
 */

import { ext, state } from './state.js';

export function originOf(url) {
  try {
    return `${new URL(url).origin}/*`;
  } catch {
    return null;
  }
}

/**
 * Start a permission request for the current tab's origin.
 *
 * **Call this synchronously from a click handler** — never after an `await`.
 * Firefox discards the user gesture across a microtask boundary and then
 * refuses `permissions.request`, so a handler that awaits first works in
 * Chrome and silently fails in Firefox. Returns a promise the caller awaits
 * later; already-granted origins resolve `true` without a prompt.
 */
export function requestPageAccess() {
  const origin = originOf(state.tab?.url);
  if (!origin) return Promise.resolve(false);
  try {
    return ext.permissions.request({ origins: [origin] });
  } catch {
    return Promise.resolve(false);
  }
}

export async function hasPageAccess() {
  const origin = originOf(state.tab?.url);
  if (!origin) return false;
  return ext.permissions.contains({ origins: [origin] });
}
