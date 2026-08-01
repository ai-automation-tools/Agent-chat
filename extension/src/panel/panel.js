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
 */

const DEFAULTS = {
  bridgeUrl: 'http://127.0.0.1:8765',
  bridgeToken: '',
  disclose: true,
  disclosureText: '\n\n— drafted by an AI (Agent-Chat)',
  agent: 'claude-code',
  persona: '',
};

const POLL_MS = 3000;

const $ = (id) => document.getElementById(id);

let settings = { ...DEFAULTS };
let tab = null; // { id, url, title }
let arena = null; // { arena, drafts } from the bridge
let capture = null; // last capture for this tab
let pollTimer = null;

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

async function loadSettings() {
  const stored = await chrome.storage.local.get('settings');
  settings = { ...DEFAULTS, ...(stored.settings || {}) };
  $('bridge-url').value = settings.bridgeUrl;
  $('bridge-token').value = settings.bridgeToken;
  $('disclose').checked = settings.disclose;
  $('disclosure-text').value = settings.disclosureText;
}

async function saveSettings() {
  settings = {
    ...settings,
    bridgeUrl: $('bridge-url').value.trim().replace(/\/$/, '') || DEFAULTS.bridgeUrl,
    bridgeToken: $('bridge-token').value.trim(),
    disclose: $('disclose').checked,
    disclosureText: $('disclosure-text').value,
  };
  await chrome.storage.local.set({ settings });
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
// Capture
// ---------------------------------------------------------------------------

/** Ask for access to this one origin the first time we capture there. */
async function ensureOriginPermission(url) {
  let origin;
  try {
    origin = `${new URL(url).origin}/*`;
  } catch {
    return false;
  }
  if (await chrome.permissions.contains({ origins: [origin] })) return true;
  return chrome.permissions.request({ origins: [origin] });
}

async function runCapture() {
  if (!tab?.id) return null;
  const msg = $('capture-summary');
  if (!/^https?:/.test(tab.url)) {
    msg.className = 'msg err';
    msg.textContent = 'This page can’t be captured (not an http(s) page).';
    return null;
  }
  const granted = await ensureOriginPermission(tab.url);
  if (!granted) {
    msg.className = 'msg err';
    msg.textContent = 'Permission denied for this site — nothing captured.';
    return null;
  }
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ['src/capture.js'],
  });
  const data = result?.result;
  if (!data || !data.posts?.length) {
    msg.className = 'msg err';
    msg.textContent = data?.error
      ? `Capture failed: ${data.error}`
      : 'No readable posts found on this page.';
    return null;
  }
  msg.className = 'msg ok';
  msg.textContent = `Captured ${data.posts.length} post${data.posts.length === 1 ? '' : 's'} (${data.site}).`;
  return data;
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

async function injectIntoPage(text) {
  const granted = await ensureOriginPermission(tab.url);
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
  } catch (err) {
    // Arena deleted out from under us (or the bridge is down) — drop the link
    // rather than poll a 404 forever.
    if (String(err).includes('no arena')) {
      await unlinkArena(tab.id);
      arena = null;
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
  await chrome.storage.local.set({ settings });

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

async function recapture() {
  const data = await runCapture();
  if (!data || !arena) return;
  try {
    const res = await api(`/arenas/${arena.arena.id}/capture`, {
      method: 'POST',
      body: { thread: data.posts },
    });
    $('capture-summary').className = 'msg ok';
    $('capture-summary').textContent = `Merged capture — ${res.posts_added} new post${
      res.posts_added === 1 ? '' : 's'
    } for the agent.`;
    await openArena(arena.arena.id);
  } catch (err) {
    $('capture-summary').className = 'msg err';
    $('capture-summary').textContent = String(err.message || err);
  }
}

async function closeArena() {
  if (!arena) return;
  await api(`/arenas/${arena.arena.id}`, { method: 'POST', body: { status: 'closed' } });
  await openArena(arena.arena.id);
}

// ---------------------------------------------------------------------------
// Draft review
// ---------------------------------------------------------------------------

function withDisclosure(text) {
  if (!settings.disclose) return text;
  const suffix = settings.disclosureText || '';
  return text.includes(suffix.trim()) ? text : text + suffix;
}

async function approveAndInsert(draft, editedText) {
  const finalText = withDisclosure(editedText);
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'approved', posted_text: finalText },
  });
  const res = await injectIntoPage(finalText);
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
    approve.onclick = () => approveAndInsert(draft, box.value);
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
    again.onclick = async () => {
      const res = await injectIntoPage(draft.posted_text || draft.content);
      const note = $(`draft-msg-${draft.id}`);
      note.className = res.ok ? 'msg ok' : 'msg err';
      note.textContent = res.ok ? 'Typed into the page.' : res.reason;
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

$('capture').onclick = async () => {
  if (arena) return recapture();
  capture = await runCapture();
  render();
};

$('recapture').onclick = recapture;
$('close-arena').onclick = closeArena;
$('unlink').onclick = async () => {
  await unlinkArena(tab.id);
  arena = null;
  stopPolling();
  render();
};

$('open-arena').onclick = createArena;

chrome.tabs.onActivated.addListener(refreshTab);
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (tabId === tab?.id && (info.status === 'complete' || info.title)) refreshTab();
});

(async function init() {
  await loadSettings();
  await loadRoster();
  await refreshTab();
})();
