/**
 * AgentBattleground — the only code that ever touches the page's reply box.
 *
 * **It types. It never submits.** Nothing in this file clicks a button, opens
 * a composer, or dispatches a form submit; the operator presses the site's own
 * post button. That is the line between this and astroturfing, and it is not a
 * setting.
 *
 * Everything below `composerOp` is injected, so it has to be self-contained —
 * `chrome.scripting.executeScript({func})` serialises the function and the
 * page has none of this module's scope.
 *
 * Two frames' worth of care:
 *
 * * The probe runs in **every** allowed frame and the insert targets exactly
 *   one. A third-party comment platform (Disqus and friends) keeps its
 *   composer inside its own iframe, so a top-frame-only insert types into
 *   whatever unrelated search box the host page happened to have.
 * * The insert is **read back**. "Approved but nothing happened" is the worst
 *   failure this feature has, because the operator's next move is to hit post.
 */

import { state } from './state.js';
import { hasPageAccess } from './permissions.js';

/**
 * Injected. `op` is 'read' or 'insert'.
 *
 * Returns `{found, adapter, tag, text, top}` for a read, plus `{ok, reason,
 * verified}` for an insert.
 */
function composerOp(op, text, mode) {
  // Per-site composers, most specific first. A site that isn't listed still
  // works through the generic list — these only stop the picker landing on a
  // search box that happens to sit above the reply form.
  const BY_HOST = [
    ['reddit.com', [
      'shreddit-composer [contenteditable="true"]',
      'faceplate-textarea-input textarea',
      'textarea[name="text"]',
    ]],
    ['x.com', ['div[data-testid="tweetTextarea_0"]']],
    ['twitter.com', ['div[data-testid="tweetTextarea_0"]']],
    ['news.ycombinator.com', ['textarea[name="text"]']],
    ['youtube.com', [
      '#placeholder-area #contenteditable-root',
      'ytd-commentbox #contenteditable-root',
      '#contenteditable-root',
    ]],
    ['linkedin.com', [
      '.comments-comment-box [contenteditable="true"]',
      '.ql-editor[contenteditable="true"]',
    ]],
    ['substack.com', [
      '.comment-input [contenteditable="true"]',
      'form [contenteditable="true"]',
    ]],
    ['disqus.com', ['textarea.textarea', 'textarea[placeholder]']],
  ];
  const GENERIC = [
    'textarea[name="text"]',
    'textarea[placeholder]',
    'textarea',
    '[role="textbox"][contenteditable="true"]',
    '[contenteditable="true"]',
  ];

  const isVisible = (node) => {
    const r = node.getBoundingClientRect();
    return r.width > 40 && r.height > 15;
  };

  const selectorsForPage = () => {
    const host = location.hostname;
    for (const [suffix, list] of BY_HOST) {
      if (host === suffix || host.endsWith(`.${suffix}`)) {
        return { adapter: suffix, selectors: list };
      }
    }
    // Discourse installs each have their own domain, so sniff the page.
    const generator = document.querySelector('meta[name="generator"]');
    if ((generator?.content || '').startsWith('Discourse')) {
      return { adapter: 'discourse', selectors: ['textarea.d-editor-input'] };
    }
    return { adapter: 'generic', selectors: [] };
  };

  const { adapter, selectors } = selectorsForPage();

  const pick = () => {
    // A focused editor beats every guess: the operator just clicked into the
    // box they mean.
    const active = document.activeElement;
    if (active && (active.tagName === 'TEXTAREA' || active.isContentEditable)) {
      return active;
    }
    for (const sel of [...selectors, ...GENERIC]) {
      for (const node of document.querySelectorAll(sel)) {
        if (isVisible(node)) return node;
      }
    }
    return null;
  };

  const valueOf = (node) => (node.isContentEditable ? node.innerText : node.value) || '';

  const target = pick();
  const base = { adapter, top: window === window.top, href: location.href };

  if (!target) {
    return op === 'read'
      ? { ...base, found: false, text: '' }
      : {
          ...base,
          ok: false,
          reason:
            'no reply box found — open the site’s reply form first, or click ' +
            'into it so the extension knows which box you mean',
        };
  }

  if (op === 'read') {
    return {
      ...base,
      found: true,
      tag: target.tagName.toLowerCase(),
      text: valueOf(target),
    };
  }

  const existing = valueOf(target);
  let final = text;
  if (mode === 'append') final = existing ? `${existing.replace(/\s+$/, '')}\n\n${text}` : text;
  else if (mode === 'prepend') final = existing ? `${text}\n\n${existing.replace(/^\s+/, '')}` : text;

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
    if (!document.execCommand('insertText', false, final)) {
      target.textContent = final;
      target.dispatchEvent(new InputEvent('input', { bubbles: true }));
    }
  } else {
    const proto =
      target instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(target, final);
    else target.value = final;
    target.dispatchEvent(new Event('input', { bubbles: true }));
    target.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // Read back rather than trusting the write. Some editors re-render from
  // their own state and quietly drop what we set.
  const after = valueOf(target);
  const squash = (s) => s.replace(/\s+/g, ' ').trim();
  return {
    ...base,
    ok: true,
    where: target.tagName.toLowerCase(),
    mode,
    verified: squash(after).includes(squash(text).slice(0, 120)),
    length: after.length,
  };
}

/** Frames worth typing into, best first: a site adapter beats the generic
 *  picker, and a real find beats a miss. */
function rankFrames(results) {
  return results
    .filter((r) => r?.result)
    .map((r) => ({ frameId: r.frameId ?? 0, ...r.result }))
    .sort((a, b) => {
      if (a.found !== b.found) return a.found ? -1 : 1;
      const specific = (f) => (f.adapter && f.adapter !== 'generic' ? 1 : 0);
      if (specific(a) !== specific(b)) return specific(b) - specific(a);
      return (b.top ? 1 : 0) - (a.top ? 1 : 0);
    });
}

/**
 * Look for a composer across every frame we can reach, without writing
 * anything. Returns `{ok, frameId, found, text, adapter}` — `text` is what is
 * already sitting in the box, which is what decides replace/append/prepend.
 */
export async function probeComposer(access) {
  const granted = access ? await access : await hasPageAccess();
  if (!granted) return { ok: false, reason: 'permission denied for this site' };
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId: state.tab.id, allFrames: true },
      func: composerOp,
      args: ['read', '', 'replace'],
    });
  } catch (err) {
    return { ok: false, reason: String(err.message || err) };
  }
  const ranked = rankFrames(results);
  const best = ranked[0];
  if (!best) return { ok: false, reason: 'the page returned nothing' };
  return {
    ok: true,
    frameId: best.frameId,
    found: Boolean(best.found),
    text: best.text || '',
    adapter: best.adapter,
  };
}

/**
 * Type `text` into one frame's composer. `mode` is 'replace' | 'append' |
 * 'prepend'. Never submits.
 */
export async function insertIntoComposer(text, { mode = 'replace', frameId = null, access = null } = {}) {
  const granted = access ? await access : await hasPageAccess();
  if (!granted) return { ok: false, reason: 'permission denied for this site' };

  let target = { tabId: state.tab.id };
  if (frameId !== null && frameId !== undefined) {
    target = { tabId: state.tab.id, frameIds: [frameId] };
  }
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target,
      func: composerOp,
      args: ['insert', text, mode],
    });
  } catch (err) {
    return { ok: false, reason: String(err.message || err) };
  }
  return results?.[0]?.result || { ok: false, reason: 'injection returned nothing' };
}

/**
 * Read back whatever is in the reply box right now, across frames.
 *
 * Used when the operator says "I posted it": the agent should learn the voice
 * that actually shipped, not the copy we handed over.
 */
export async function readComposerText() {
  const probe = await probeComposer(null);
  return probe.ok && probe.found ? probe.text : '';
}
