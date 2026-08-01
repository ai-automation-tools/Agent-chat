/**
 * AgentBattleground — capturing the page the operator is looking at.
 *
 * Injection happens through `chrome.scripting`, per tab, after an explicit
 * per-domain permission grant. The extension holds no standing access to any
 * site and there is no static content script.
 */

import { MAX_POSTS, $, el, state } from './state.js';
import { hasPageAccess } from './permissions.js';
import { recapture } from './arena.js';
import { render } from './view.js';

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
    target: { tabId: state.tab.id, allFrames: true },
    files: ['src/capture.js'],
  });
  const frames = results
    .map((r) => r?.result)
    .filter((r) => r && Array.isArray(r.posts));
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
  const biggest = merged.reduce(
    (a, b) => (b.posts.length > (a?.posts.length || 0) ? b : a),
    null
  );
  const site =
    biggest && biggest.posts.length > top.posts.length ? biggest.site : top.site;

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
export async function runCapture(access, { silent = false } = {}) {
  if (!state.tab?.id || state.captureBusy) return null;
  const fail = (reason) => {
    if (silent) return null;
    const node = $('capture-summary');
    node.className = 'msg err';
    node.textContent = reason;
    return null;
  };

  if (!/^https?:/.test(state.tab.url)) {
    return fail('This page can’t be captured (not an http(s) page).');
  }
  const granted = access ? await access : await hasPageAccess();
  if (!granted) {
    return fail('Permission denied for this site — nothing captured.');
  }

  state.captureBusy = true;
  let data = null;
  try {
    data = await captureFrames();
  } catch (err) {
    state.captureBusy = false;
    return fail(`Capture failed: ${err.message || err}`);
  }
  state.captureBusy = false;

  if (!data || !data.posts.length) {
    return fail(
      data?.error
        ? `Capture failed: ${data.error}`
        : 'No readable posts found on this page.'
    );
  }

  state.pendingHints = await unheldHints(data.hints || []);
  renderHints();

  if (!silent) {
    const frameNote = data.frames > 1 ? `, ${data.frames} frames` : '';
    const node = $('capture-summary');
    node.className = 'msg ok';
    node.textContent = `Captured ${data.posts.length} post${
      data.posts.length === 1 ? '' : 's'
    } (${data.site}${frameNote}).`;
  }
  return data;
}

/** Frame-hint origins we don't hold yet — the ones worth offering a button for. */
async function unheldHints(hints) {
  const out = [];
  for (const origin of hints) {
    try {
      if (!(await chrome.permissions.contains({ origins: [origin] }))) {
        out.push(origin);
      }
    } catch {
      /* malformed pattern from a page we don't control — skip it */
    }
  }
  return out;
}

export function renderHints() {
  const row = $('frame-hints');
  row.innerHTML = '';
  row.classList.toggle('hidden', state.pendingHints.length === 0);
  for (const origin of state.pendingHints) {
    let host = origin;
    try {
      host = new URL(origin.replace(/\/\*$/, '')).hostname;
    } catch {
      /* show the raw pattern */
    }
    const btn = el('button', null, `Include ${host}`);
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
  state.pendingHints = state.pendingHints.filter((o) => o !== origin);
  renderHints();
  if (state.arena) {
    await recapture(null).catch(() => {});
  } else {
    state.capture = await runCapture(null);
    render();
  }
}
