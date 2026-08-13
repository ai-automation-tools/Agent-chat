/**
 * AgentBattleground — every HTTP call to the Agent-Chat bridge.
 *
 * All of it lives in the panel rather than the service worker, because
 * reviewing a draft is human-paced and an MV3 worker is torn down after ~30s
 * idle, which would kill the poll mid-wait.
 */

import { CUSTOM_PERSONA, RANDOM_PERSONA, $, state } from './state.js';
import { syncCustomPersona } from './settings.js';

/** One request against `/api/battleground<path>`. Throws on a non-2xx. */
export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers['Content-Type'] = 'application/json';
  if (state.settings.bridgeToken) {
    headers.Authorization = `Bearer ${state.settings.bridgeToken}`;
  }
  const res = await fetch(`${state.settings.bridgeUrl}/api/battleground${path}`, {
    ...options,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    throw new Error(data?.error || `${res.status} ${res.statusText}`);
  }
  return data;
}

export function setBridgeStatus(ok, title) {
  const node = $('bridge-status');
  node.className = `dot ${ok ? 'on' : 'off'}`;
  node.title = title;
}

export function bridgeUp() {
  setBridgeStatus(true, `Connected to ${state.settings.bridgeUrl}`);
}

/**
 * Read `/healthz` — the one endpoint that answers without a token, so it can
 * tell us *why* everything else is failing.
 *
 * Also drives the Settings nudge: a bridge running with no token is fine on a
 * single-user machine and worth knowing about, not worth nagging over.
 */
export async function loadHealth() {
  try {
    state.health = await api('/healthz');
  } catch {
    state.health = null;
  }
  renderHealthNotice();
  return state.health;
}

function renderHealthNotice() {
  const node = $('token-warn');
  if (!node) return;
  const health = state.health;
  if (!health || health.token_required) {
    node.classList.add('hidden');
    return;
  }
  node.classList.remove('hidden');
  node.textContent =
    'This bridge accepts calls without a token. Fine for a machine only you ' +
    'use. To lock it down, stop the web UI and restart it with ' +
    '$env:AGENT_CHAT_BATTLEGROUND_TOKEN = "<a long random string>", then ' +
    'paste the same value above.';
}

/** Personas + CLI ids + launch commands, in one round trip, into the pickers. */
export async function loadRoster() {
  try {
    const data = await api('/roster');
    state.roster = data;
    bridgeUp();

    const agentSel = $('agent');
    agentSel.innerHTML = '';
    for (const id of data.agents) {
      agentSel.append(new Option(id, id));
    }
    agentSel.value = state.settings.agent;

    const personaSel = $('persona');
    personaSel.innerHTML = '';
    personaSel.append(new Option('— no persona (argue as yourself) —', ''));
    personaSel.append(new Option('🎲 random', RANDOM_PERSONA));
    personaSel.append(new Option('✎ custom instructions…', CUSTOM_PERSONA));
    const groups = new Map();
    for (const p of data.personas) {
      if (!groups.has(p.group)) groups.set(p.group, []);
      groups.get(p.group).push(p);
    }
    for (const [group, list] of [...groups].sort()) {
      const og = document.createElement('optgroup');
      og.label = group;
      for (const p of list) og.append(new Option(p.name, p.slug));
      personaSel.append(og);
    }
    // A saved slug can go missing (persona deleted since last use), which
    // leaves the select on its first option. Custom survives that: it's a
    // sentinel we just appended, not a row that has to still exist.
    personaSel.value = state.settings.persona;
    if (!personaSel.value) state.settings.persona = personaSel.value;
    syncCustomPersona();
    return true;
  } catch (err) {
    setBridgeStatus(false, String(err));
    return false;
  }
}
