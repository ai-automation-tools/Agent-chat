/**
 * AgentBattleground — side panel.
 *
 * The operator surface, and the only place the loop is closed:
 *
 *   capture page → open arena → (agent drafts over MCP) → review → insert
 *
 * All HTTP to the Agent-Chat bridge happens here rather than in the service
 * worker, because reviewing a draft is human-paced and a worker would be torn
 * down mid-poll. All page access happens through `chrome.scripting`, per tab,
 * after an explicit per-domain permission grant — the extension holds no
 * standing access to any site.
 *
 * The one rule this file enforces above all: **nothing is ever submitted.**
 * Approving injects text into the page's own composer and stops there.
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

const DEFAULTS = {
  bridgeUrl: 'http://127.0.0.1:8765',
  bridgeToken: '',
  disclose: true,
  disclosureText: '\n\n— drafted by an AI (Agent-Chat)',
  agent: 'claude-code',
  persona: '',
  autoRecapture: false,
  autoSeconds: 90,
};

const POLL_MS = 3000;
/** Floor on auto re-capture. A capture is a full DOM walk plus a POST; below
 *  this it's a scraper pointed at someone else's site, not a refresh. */
const MIN_AUTO_SECONDS = 30;
const MAX_AUTO_FAILURES = 3;
const MAX_POSTS = 200;

const $ = (id) => document.getElementById(id);

let settings = { ...DEFAULTS };
let tab = null; // { id, url, title }
let arena = null; // { arena, drafts } from the bridge
let capture = null; // last merged capture for this tab
let pendingHints = []; // comment-iframe origins we could still be granted
let pollTimer = null;
let autoTimer = null;
let autoFailures = 0;
let lastAutoAt = 0;
let captureBusy = false;

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

async function loadSettings() {
  const stored = await chrome.storage.local.get('settings');
  settings = { ...DEFAULTS, ...(stored.settings || {}) };
  settings.autoSeconds = clampSeconds(settings.autoSeconds);
  $('bridge-url').value = settings.bridgeUrl;
  $('bridge-token').value = settings.bridgeToken;
  $('disclose').checked = settings.disclose;
  $('disclosure-text').value = settings.disclosureText;
  $('auto-recapture').checked = settings.autoRecapture;
  $('auto-seconds').value = settings.autoSeconds;
}

function clampSeconds(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULTS.autoSeconds;
  return Math.max(MIN_AUTO_SECONDS, Math.min(3600, Math.round(n)));
}

async function persistSettings() {
  await chrome.storage.local.set({ settings });
}

async function saveSettings() {
  settings = {
    ...settings,
    bridgeUrl: $('bridge-url').value.trim().replace(/\/$/, '') || DEFAULTS.bridgeUrl,
    bridgeToken: $('bridge-token').value.trim(),
    disclose: $('disclose').checked,
    disclosureText: $('disclosure-text').value,
  };
  await persistSettings();
}

// ---------------------------------------------------------------------------
// Bridge
// ---------------------------------------------------------------------------

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers['Content-Type'] = 'application/json';
  if (settings.bridgeToken) headers.Authorization = `Bearer ${settings.bridgeToken}`;
  const res = await fetch(`${settings.bridgeUrl}/api/battleground${path}`, {
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

function setBridgeStatus(ok, title) {
  const el = $('bridge-status');
  el.className = `dot ${ok ? 'on' : 'off'}`;
  el.title = title;
}

async function loadRoster() {
  try {
    const data = await api('/roster');
    setBridgeStatus(true, `Connected to ${settings.bridgeUrl}`);

    const agentSel = $('agent');
    agentSel.innerHTML = '';
    for (const id of data.agents) {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = id;
      agentSel.append(opt);
    }
    agentSel.value = settings.agent;

    const personaSel = $('persona');
    personaSel.innerHTML = '';
    personaSel.append(new Option('— no persona (argue as yourself) —', ''));
    personaSel.append(new Option('🎲 random', '__random__'));
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
    personaSel.value = settings.persona;
    return true;
  } catch (err) {
    setBridgeStatus(false, String(err));
    return false;
  }
}

// ---------------------------------------------------------------------------
// Tab tracking + per-tab arena link
// ---------------------------------------------------------------------------

const linkKey = (tabId) => `arena:${tabId}`;

async function linkArena(tabId, arenaId, url) {
  await chrome.storage.local.set({ [linkKey(tabId)]: { arenaId, url } });
  chrome.runtime.sendMessage({ type: 'badge', tabId, text: String(arenaId) });
}

async function unlinkArena(tabId) {
  await chrome.storage.local.remove(linkKey(tabId));
  chrome.runtime.sendMessage({ type: 'badge', tabId, text: '' });
}

async function getLink(tabId) {
  const stored = await chrome.storage.local.get(linkKey(tabId));
  return stored[linkKey(tabId)] || null;
}

async function refreshTab() {
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!active) return;
  const changed = tab?.id !== active.id || tab?.url !== active.url;
  tab = { id: active.id, url: active.url || '', title: active.title || '' };
  $('page-title').textContent = tab.title || '—';
  $('page-url').textContent = tab.url || '—';
  if (!changed) return;

  capture = null;
  pendingHints = [];
  renderHints();
  $('capture-summary').textContent = '';
  $('capture-summary').className = 'msg';
  $('cast-card').classList.add('hidden');

  const link = await getLink(tab.id);
  if (link) {
    await openArena(link.arenaId);
  } else {
    arena = null;
    stopPolling();
    render();
  }
}

// ---------------------------------------------------------------------------
// Permissions
//
// Standing access: none. The extension asks per-origin, from a click, the
// first time you capture on a domain — and asks again, separately, for a
// third-party comment iframe.
// ---------------------------------------------------------------------------

function originOf(url) {
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
 * Returns a promise the caller can await later. A no-op resolve of `true`
 * when the origin is already granted (neither browser prompts twice).
 */
function requestPageAccess() {
  const origin = originOf(tab?.url);
  if (!origin) return Promise.resolve(false);
  try {
    return chrome.permissions.request({ origins: [origin] });
  } catch (err) {
    return Promise.resolve(false);
  }
}

async function hasPageAccess() {
  const origin = originOf(tab?.url);
  if (!origin) return false;
  return chrome.permissions.contains({ origins: [origin] });
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------

/**
 * Inject the capture into every frame we're allowed into and fold the results
 * into one thread.
 *
 * The top frame owns the page's identity (url, title) and always contributes.
 * A subframe only contributes when it is a recognised comment platform or an
 * origin the operator explicitly opted into via a frame hint — otherwise an ad
 * iframe that happens to be in scope would pour boilerplate into the arena.
 * Subframe post ids are namespaced by platform so they can't collide with the
 * host page's, and stay stable across re-captures (which is what makes the
 * bridge's merge-on-id work).
 */
async function captureFrames() {
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id, allFrames: true },
    files: ['src/capture.js'],
  });
  const frames = results.map((r) => r?.result).filter((r) => r && Array.isArray(r.posts));
  const top = frames.find((f) => f.top) || frames[0];
  if (!top) return null;

  const hints = top.frameHints || [];
  const hinted = new Set(hints.map((h) => h.replace(/\/\*$/, '')));

  const posts = [...top.posts];
  const seen = new Set(posts.map((p) => p.id));
  const merged = [];

  for (const frame of frames) {
    if (frame === top || !frame.posts.length) continue;
    let origin = null;
    try {
      origin = new URL(frame.frameUrl).origin;
    } catch {
      continue;
    }
    if (frame.site === 'generic' && !hinted.has(origin)) continue;
    merged.push(frame);
    for (const p of frame.posts) {
      const id = `${frame.site}:${p.id}`;
      if (seen.has(id)) continue;
      seen.add(id);
      posts.push({ ...p, id });
    }
  }

  // Label the arena with where the argument actually is: if the comment
  // platform in the iframe carried the thread, that's the site, not the
  // article shell that framed it.
  const biggest = merged.reduce((a, b) => (b.posts.length > (a?.posts.length || 0) ? b : a), null);
  const site = biggest && biggest.posts.length > top.posts.length ? biggest.site : top.site;

  return {
    site,
    url: top.url,
    title: top.title,
    posts: posts.slice(0, MAX_POSTS),
    hints,
    frames: 1 + merged.length,
    error: top.error,
  };
}

/**
 * Capture the current tab.
 *
 * `access` is the promise returned by `requestPageAccess()` at click time —
 * passing it in is what keeps the permission prompt attached to the gesture.
 * Auto re-capture passes nothing and relies on the already-granted check.
 */
async function runCapture(access, { silent = false } = {}) {
  if (!tab?.id || captureBusy) return null;
  const msg = $('capture-summary');
  const fail = (reason) => {
    if (silent) return null;
    msg.className = 'msg err';
    msg.textContent = reason;
    return null;
  };

  if (!/^https?:/.test(tab.url)) {
    return fail('This page can’t be captured (not an http(s) page).');
  }
  const granted = access ? await access : await hasPageAccess();
  if (!granted) {
    return fail('Permission denied for this site — nothing captured.');
  }

  captureBusy = true;
  let data = null;
  try {
    data = await captureFrames();
  } catch (err) {
    captureBusy = false;
    return fail(`Capture failed: ${err.message || err}`);
  }
  captureBusy = false;

  if (!data || !data.posts.length) {
    return fail(data?.error ? `Capture failed: ${data.error}` : 'No readable posts found on this page.');
  }

  pendingHints = await unheldHints(data.hints || []);
  renderHints();

  if (!silent) {
    const frameNote = data.frames > 1 ? `, ${data.frames} frames` : '';
    msg.className = 'msg ok';
    msg.textContent = `Captured ${data.posts.length} post${data.posts.length === 1 ? '' : 's'} (${data.site}${frameNote}).`;
  }
  return data;
}

/** Frame-hint origins we don't hold yet — the ones worth offering a button for. */
async function unheldHints(hints) {
  const out = [];
  for (const origin of hints) {
    try {
      if (!(await chrome.permissions.contains({ origins: [origin] }))) out.push(origin);
    } catch {
      /* malformed pattern from a page we don't control — skip it */
    }
  }
  return out;
}

function renderHints() {
  const row = $('frame-hints');
  row.innerHTML = '';
  row.classList.toggle('hidden', pendingHints.length === 0);
  for (const origin of pendingHints) {
    let host = origin;
    try {
      host = new URL(origin.replace(/\/\*$/, '')).hostname;
    } catch {
      /* show the raw pattern */
    }
    const btn = document.createElement('button');
    btn.textContent = `Include ${host}`;
    btn.title = `The comments on this page load from ${host}. Grant access and capture again.`;
    btn.onclick = () => {
      // Gesture-first: request, then do the async work.
      const req = chrome.permissions.request({ origins: [origin] });
      includeHint(origin, req);
    };
    row.append(btn);
  }
}

async function includeHint(origin, request) {
  const granted = await request;
  if (!granted) return;
  pendingHints = pendingHints.filter((o) => o !== origin);
  renderHints();
  if (arena) {
    await recapture(null).catch(() => {});
  } else {
    capture = await runCapture(null);
    render();
  }
}

// ---------------------------------------------------------------------------
// Composer injection — the only thing that ever touches the page's reply box
// ---------------------------------------------------------------------------

/** Injected. Types `text` into the page's reply box. Never submits. */
function injectText(text) {
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 40 && r.height > 15;
  };
  const pick = () => {
    const active = document.activeElement;
    if (active && (active.tagName === 'TEXTAREA' || active.isContentEditable)) return active;
    const selectors = [
      'shreddit-composer [contenteditable="true"]',
      'div[data-testid="tweetTextarea_0"]',
      '#placeholder-area #contenteditable-root',
      '.comments-comment-box [contenteditable="true"]',
      'textarea[name="text"]',
      'textarea[placeholder]',
      'textarea',
      '[role="textbox"][contenteditable="true"]',
      '[contenteditable="true"]',
    ];
    for (const sel of selectors) {
      for (const el of document.querySelectorAll(sel)) {
        if (isVisible(el)) return el;
      }
    }
    return null;
  };
  const target = pick();
  if (!target) {
    return { ok: false, reason: 'no reply box found — open the site’s reply form first' };
  }
  target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  target.focus();
  if (target.isContentEditable) {
    // execCommand is deprecated but remains the only insertion path that keeps
    // React/Draft/Lexical editors' internal state in sync with the DOM.
    const sel = window.getSelection();
    sel.removeAllRanges();
    const range = document.createRange();
    range.selectNodeContents(target);
    sel.addRange(range);
    if (!document.execCommand('insertText', false, text)) {
      target.textContent = text;
      target.dispatchEvent(new InputEvent('input', { bubbles: true }));
    }
  } else {
    const proto =
      target instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(target, text);
    else target.value = text;
    target.dispatchEvent(new Event('input', { bubbles: true }));
    target.dispatchEvent(new Event('change', { bubbles: true }));
  }
  return { ok: true, where: target.tagName.toLowerCase() };
}

/** Injected. Reads back whatever is in the reply box right now. */
function readComposer() {
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 40 && r.height > 15;
  };
  for (const sel of ['textarea', '[contenteditable="true"]', '[role="textbox"]']) {
    for (const el of document.querySelectorAll(sel)) {
      if (!isVisible(el)) continue;
      const value = el.isContentEditable ? el.innerText : el.value;
      if (value && value.trim()) return value;
    }
  }
  return '';
}

async function injectIntoPage(text, access) {
  const granted = access ? await access : await hasPageAccess();
  if (!granted) return { ok: false, reason: 'permission denied for this site' };
  const [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: injectText,
    args: [text],
  });
  return res?.result || { ok: false, reason: 'injection returned nothing' };
}

// ---------------------------------------------------------------------------
// Arena lifecycle
// ---------------------------------------------------------------------------

async function openArena(arenaId) {
  try {
    arena = await api(`/arenas/${arenaId}`);
    setBridgeStatus(true, `Connected to ${settings.bridgeUrl}`);
    startPolling();
    startAutoRecapture();
  } catch (err) {
    // Arena deleted out from under us (or the bridge is down) — drop the link
    // rather than poll a 404 forever.
    if (String(err).includes('no arena')) {
      await unlinkArena(tab.id);
      arena = null;
      stopAutoRecapture();
    } else {
      setBridgeStatus(false, String(err));
    }
  }
  render();
}

async function createArena() {
  const msg = $('arena-msg');
  msg.className = 'msg';
  msg.textContent = 'Opening arena…';
  let personaValue = $('persona').value;
  if (personaValue === '__random__') {
    const options = [...$('persona').querySelectorAll('optgroup option')];
    personaValue = options.length
      ? options[Math.floor(Math.random() * options.length)].value
      : '';
  }
  settings.agent = $('agent').value;
  settings.persona = $('persona').value;
  await persistSettings();

  try {
    const data = await api('/arenas', {
      method: 'POST',
      body: {
        url: capture.url,
        site: capture.site,
        title: capture.title,
        thread: capture.posts,
        stance: $('stance').value.trim() || null,
        agent_id: $('agent').value,
        persona: personaValue || null,
      },
    });
    await linkArena(tab.id, data.arena.id, capture.url);
    msg.className = 'msg ok';
    msg.textContent = `Arena ${data.arena.id} is open.`;
    await openArena(data.arena.id);
  } catch (err) {
    msg.className = 'msg err';
    msg.textContent = String(err.message || err);
  }
}

async function recapture(access, { silent = false } = {}) {
  const data = await runCapture(access, { silent });
  if (!data || !arena) return 0;
  try {
    const res = await api(`/arenas/${arena.arena.id}/capture`, {
      method: 'POST',
      body: { thread: data.posts },
    });
    if (!silent || res.posts_added) {
      $('capture-summary').className = 'msg ok';
      $('capture-summary').textContent = `Merged capture — ${res.posts_added} new post${
        res.posts_added === 1 ? '' : 's'
      } for the agent.`;
    }
    if (res.posts_added || !silent) await openArena(arena.arena.id);
    return res.posts_added;
  } catch (err) {
    if (!silent) {
      $('capture-summary').className = 'msg err';
      $('capture-summary').textContent = String(err.message || err);
    }
    throw err;
  }
}

async function closeArena() {
  if (!arena) return;
  await api(`/arenas/${arena.arena.id}`, { method: 'POST', body: { status: 'closed' } });
  await openArena(arena.arena.id);
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

function startAutoRecapture() {
  stopAutoRecapture();
  if (!settings.autoRecapture || !arena) return;
  autoFailures = 0;
  autoTimer = setInterval(autoTick, settings.autoSeconds * 1000);
  renderAutoStatus();
}

function stopAutoRecapture() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  renderAutoStatus();
}

/** Every reason to skip a tick, in the order that's cheapest to check. */
async function autoSkipReason() {
  if (!settings.autoRecapture) return 'off';
  if (!arena || !tab?.id) return 'no arena';
  if (arena.arena.status !== 'open') return 'arena closed';
  if (captureBusy) return 'busy';
  const editing = document.activeElement;
  if (editing && (editing.tagName === 'TEXTAREA' || editing.tagName === 'INPUT')) return 'editing';
  const link = await getLink(tab.id);
  if (!link || link.arenaId !== arena.arena.id) return 'tab not linked';
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
    autoFailures = 0;
    lastAutoAt = Date.now();
    renderAutoStatus(added ? `+${added} new` : 'no new posts');
  } catch (err) {
    autoFailures += 1;
    if (autoFailures >= MAX_AUTO_FAILURES) {
      settings.autoRecapture = false;
      $('auto-recapture').checked = false;
      await persistSettings();
      stopAutoRecapture();
      renderAutoStatus(`paused after ${MAX_AUTO_FAILURES} failures — ${err.message || err}`);
      return;
    }
    renderAutoStatus(`failed (${autoFailures}/${MAX_AUTO_FAILURES})`);
  }
}

function renderAutoStatus(note) {
  const el = $('auto-status');
  if (!el) return;
  if (!settings.autoRecapture) {
    el.textContent = 'off — re-capture by hand';
    return;
  }
  const since = lastAutoAt ? `${Math.round((Date.now() - lastAutoAt) / 1000)}s ago` : 'not yet';
  el.textContent = `every ${settings.autoSeconds}s · last ${since}${note ? ` · ${note}` : ''}`;
}

// ---------------------------------------------------------------------------
// Draft review
// ---------------------------------------------------------------------------

function withDisclosure(text) {
  if (!settings.disclose) return text;
  const suffix = settings.disclosureText || '';
  return text.includes(suffix.trim()) ? text : text + suffix;
}

async function approveAndInsert(draft, editedText, access) {
  const finalText = withDisclosure(editedText);
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'approved', posted_text: finalText },
  });
  const res = await injectIntoPage(finalText, access);
  await openArena(arena.arena.id);
  const note = $(`draft-msg-${draft.id}`);
  if (note) {
    note.className = res.ok ? 'msg ok' : 'msg err';
    note.textContent = res.ok
      ? 'Typed into the page. Read it once more, then hit the site’s own post button.'
      : `Approved, but couldn’t reach a reply box: ${res.reason}`;
  }
}

async function markPosted(draft) {
  // Read the composer rather than trusting our own copy — the operator may
  // have edited in the page after insertion, and the agent should learn the
  // voice that actually shipped.
  let posted = draft.posted_text || draft.content;
  try {
    const [res] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: readComposer,
    });
    if (res?.result?.trim()) posted = res.result;
  } catch {
    /* composer already cleared by the site after posting — keep our copy */
  }
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'posted', posted_text: posted },
  });
  await openArena(arena.arena.id);
}

async function rejectDraft(draft, note) {
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'rejected', note: note || null },
  });
  await openArena(arena.arena.id);
}

function renderDraft(draft) {
  const el = document.createElement('div');
  el.className = `draft ${draft.status}`;

  const head = document.createElement('div');
  head.className = 'draft-head';
  head.innerHTML = `<span class="draft-status">${draft.status}</span><span>#${draft.id} · ${draft.agent_id}</span>`;
  el.append(head);

  if (draft.status === 'pending') {
    const box = document.createElement('textarea');
    box.rows = Math.min(16, Math.max(4, Math.ceil(draft.content.length / 60)));
    box.value = draft.content;
    el.append(box);

    if (draft.rationale) {
      const r = document.createElement('p');
      r.className = 'rationale';
      r.textContent = `Agent’s note: ${draft.rationale}`;
      el.append(r);
    }

    const row = document.createElement('div');
    row.className = 'row';
    const approve = document.createElement('button');
    approve.className = 'primary';
    approve.textContent = 'Approve & type into page';
    approve.onclick = () => approveAndInsert(draft, box.value, requestPageAccess());
    const reject = document.createElement('button');
    reject.textContent = 'Reject…';
    row.append(approve, reject);
    el.append(row);

    const noteRow = document.createElement('div');
    noteRow.className = 'row hidden';
    const noteInput = document.createElement('input');
    noteInput.type = 'text';
    noteInput.placeholder = 'What should it do differently?';
    const send = document.createElement('button');
    send.textContent = 'Send back';
    send.onclick = () => rejectDraft(draft, noteInput.value.trim());
    noteRow.append(noteInput, send);
    el.append(noteRow);
    reject.onclick = () => {
      noteRow.classList.toggle('hidden');
      noteInput.focus();
    };
  } else {
    const body = document.createElement('p');
    body.className = 'draft-body';
    body.textContent = draft.posted_text || draft.content;
    el.append(body);
    if (draft.verdict_note) {
      const r = document.createElement('p');
      r.className = 'rationale';
      r.textContent = `Your note: ${draft.verdict_note}`;
      el.append(r);
    }
  }

  if (draft.status === 'approved') {
    const row = document.createElement('div');
    row.className = 'row';
    const again = document.createElement('button');
    again.textContent = 'Type into page again';
    again.onclick = () => {
      const access = requestPageAccess();
      injectIntoPage(draft.posted_text || draft.content, access).then((res) => {
        const note = $(`draft-msg-${draft.id}`);
        note.className = res.ok ? 'msg ok' : 'msg err';
        note.textContent = res.ok ? 'Typed into the page.' : res.reason;
      });
    };
    const posted = document.createElement('button');
    posted.className = 'primary';
    posted.textContent = 'I posted it';
    posted.onclick = () => markPosted(draft);
    row.append(again, posted);
    el.append(row);
  }

  const msg = document.createElement('p');
  msg.className = 'msg';
  msg.id = `draft-msg-${draft.id}`;
  el.append(msg);
  return el;
}

// ---------------------------------------------------------------------------
// Render + polling
// ---------------------------------------------------------------------------

function render() {
  const hasCapture = Boolean(capture);
  const hasArena = Boolean(arena);

  $('cast-card').classList.toggle('hidden', !hasCapture || hasArena);
  $('arena-card').classList.toggle('hidden', !hasArena);
  $('drafts-card').classList.toggle('hidden', !hasArena);
  $('capture').textContent = hasArena ? 'Re-capture this thread' : 'Capture this thread';

  if (!hasArena) return;

  const a = arena.arena;
  $('arena-id').textContent = `#${a.id}`;
  const cast = a.persona_name ? `${a.agent_id || 'unassigned'} as ${a.persona_name}` : a.agent_id || 'unassigned';
  $('arena-meta').textContent = `${a.status} · ${a.site} · ${a.thread.length} posts · ${cast}`;
  $('arena-waiting').classList.toggle('hidden', arena.drafts.length > 0);
  $('close-arena').disabled = a.status !== 'open';
  renderAutoStatus();

  const list = $('drafts');
  list.innerHTML = '';
  if (!arena.drafts.length) {
    const empty = document.createElement('p');
    empty.className = 'msg';
    empty.textContent = 'No drafts yet — waiting on the agent.';
    list.append(empty);
  }
  for (const draft of [...arena.drafts].reverse()) list.append(renderDraft(draft));
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    if (!arena) return stopPolling();
    // Don't yank a draft out from under an operator mid-edit.
    if (document.activeElement?.tagName === 'TEXTAREA') return;
    try {
      const fresh = await api(`/arenas/${arena.arena.id}`);
      const changed =
        fresh.drafts.length !== arena.drafts.length ||
        fresh.arena.updated_at !== arena.arena.updated_at;
      arena = fresh;
      setBridgeStatus(true, `Connected to ${settings.bridgeUrl}`);
      if (changed) render();
    } catch (err) {
      setBridgeStatus(false, String(err));
    }
  }, POLL_MS);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

$('toggle-settings').onclick = () => $('settings').classList.toggle('hidden');

$('save-settings').onclick = async () => {
  await saveSettings();
  const ok = await loadRoster();
  const msg = $('settings-msg');
  msg.className = ok ? 'msg ok' : 'msg err';
  msg.textContent = ok ? 'Saved and connected.' : 'Saved, but the bridge didn’t answer.';
};

$('test-bridge').onclick = async () => {
  await saveSettings();
  const ok = await loadRoster();
  const msg = $('settings-msg');
  msg.className = ok ? 'msg ok' : 'msg err';
  msg.textContent = ok
    ? `Connected to ${settings.bridgeUrl}.`
    : `No answer from ${settings.bridgeUrl} — is the web UI running?`;
};

// Gesture-first: `requestPageAccess()` runs before the first await so Firefox
// still counts this as a user action.
$('capture').onclick = () => {
  const access = requestPageAccess();
  // The error is already on screen via `capture-summary`; swallow the reject.
  if (arena) return recapture(access).catch(() => {});
  return runCapture(access).then((data) => {
    capture = data;
    render();
  });
};

$('recapture').onclick = () => recapture(requestPageAccess()).catch(() => {});
$('close-arena').onclick = closeArena;
$('unlink').onclick = async () => {
  await unlinkArena(tab.id);
  arena = null;
  stopPolling();
  stopAutoRecapture();
  render();
};

$('open-arena').onclick = createArena;

$('auto-recapture').onchange = async () => {
  settings.autoRecapture = $('auto-recapture').checked;
  await persistSettings();
  if (settings.autoRecapture) startAutoRecapture();
  else stopAutoRecapture();
};

$('auto-seconds').onchange = async () => {
  settings.autoSeconds = clampSeconds($('auto-seconds').value);
  $('auto-seconds').value = settings.autoSeconds;
  await persistSettings();
  if (settings.autoRecapture) startAutoRecapture();
};

chrome.tabs.onActivated.addListener(refreshTab);
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (tabId === tab?.id && (info.status === 'complete' || info.title)) refreshTab();
});

(async function init() {
  await loadSettings();
  await loadRoster();
  await refreshTab();
})();
