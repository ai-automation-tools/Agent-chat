/**
 * AgentBattleground — page capture.
 *
 * Injected on demand by the side panel (never a static content script: the
 * extension has no standing access to any site, and asks per-domain the first
 * time you capture there). Runs as one IIFE whose completion value is the
 * capture, so `chrome.scripting.executeScript({files: ['src/capture.js']})`
 * gets it back directly — and so re-injecting on the same tab can't collide
 * with declarations from a previous run.
 *
 * Output shape (matches what POST /api/battleground/arenas expects):
 *
 *   { site, url, title, posts: [{ id, author, text, permalink?, score?,
 *                                 timestamp?, depth? }] }
 *
 * Each adapter's job is only to find posts and give each a *stable* id — the
 * bridge merges re-captures on that id, so a good one (the site's own comment
 * id) means an operator can re-capture a thread mid-argument and the agent
 * sees exactly the new replies rather than a shuffled pile of duplicates.
 */

(() => {
  const MAX_POSTS = 200;
  const MAX_CHARS = 8000;

  const clean = (s) =>
    (s || '')
      .replace(/ /g, ' ')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
      .slice(0, MAX_CHARS);

  const text = (el) => (el ? clean(el.innerText || el.textContent || '') : '');

  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  /** Deterministic short hash — the fallback id when a site gives us nothing. */
  const hash = (s) => {
    let h = 5381;
    for (let i = 0; i < s.length; i += 1) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  };

  const post = (id, author, body, extra = {}) => {
    const t = clean(body);
    if (!t) return null;
    return { id: String(id || `p-${hash(t.slice(0, 120))}`), author: clean(author) || 'unknown', text: t, ...extra };
  };

  // -------------------------------------------------------------------------
  // Reddit — new (shreddit web components) and old (.thing) layouts
  // -------------------------------------------------------------------------
  const reddit = () => {
    const posts = [];

    const shredditPost = document.querySelector('shreddit-post');
    if (shredditPost) {
      const body =
        text(shredditPost.querySelector('[slot="text-body"]')) ||
        text(shredditPost.querySelector('[data-post-click-location="text-body"]'));
      const p = post(
        shredditPost.getAttribute('id') || 'op',
        shredditPost.getAttribute('author'),
        `${shredditPost.getAttribute('post-title') || ''}\n\n${body}`.trim(),
        { score: shredditPost.getAttribute('score') || undefined, depth: 0 }
      );
      if (p) posts.push(p);
    } else {
      // Old reddit / partial renders: title + selftext.
      const title = text(document.querySelector('.thing .title a, h1'));
      const body = text(document.querySelector('.thing .usertext-body .md, [data-test-id="post-content"]'));
      const author = text(document.querySelector('.thing .author'));
      const p = post('op', author, `${title}\n\n${body}`.trim(), { depth: 0 });
      if (p) posts.push(p);
    }

    document.querySelectorAll('shreddit-comment').forEach((c) => {
      const depth = Number(c.getAttribute('depth') || 0);
      const p = post(
        c.getAttribute('thingid') || c.getAttribute('id'),
        c.getAttribute('author'),
        text(c.querySelector('[slot="comment"]')),
        { depth: Number.isFinite(depth) ? depth : 0, score: c.getAttribute('score') || undefined }
      );
      if (p) posts.push(p);
    });

    if (posts.length <= 1) {
      // Old reddit comment tree.
      document.querySelectorAll('.thing.comment').forEach((c) => {
        const p = post(
          c.getAttribute('data-fullname'),
          text(c.querySelector('.author')),
          text(c.querySelector('.usertext-body .md')),
          { permalink: c.querySelector('a.bylink')?.href }
        );
        if (p) posts.push(p);
      });
    }
    return posts;
  };

  // -------------------------------------------------------------------------
  // X / Twitter — the visible reply chain
  // -------------------------------------------------------------------------
  const x = () => {
    const posts = [];
    document.querySelectorAll('article[data-testid="tweet"]').forEach((a, i) => {
      const link = a.querySelector('a[href*="/status/"]');
      const href = link?.href || '';
      const id = href.match(/status\/(\d+)/)?.[1] || `tweet-${i}`;
      const handle = Array.from(a.querySelectorAll('[data-testid="User-Name"] span'))
        .map((s) => s.textContent || '')
        .find((s) => s.startsWith('@'));
      const p = post(
        id,
        handle || text(a.querySelector('[data-testid="User-Name"]')).split('\n')[0],
        text(a.querySelector('[data-testid="tweetText"]')),
        { permalink: href || undefined, timestamp: a.querySelector('time')?.getAttribute('datetime') || undefined }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // Hacker News
  // -------------------------------------------------------------------------
  const hackernews = () => {
    const posts = [];
    const title = text(document.querySelector('.titleline a, .title a'));
    const story = text(document.querySelector('.toptext, .fatitem .commtext'));
    const op = post('story', text(document.querySelector('.hnuser')), `${title}\n\n${story}`.trim(), { depth: 0 });
    if (op) posts.push(op);

    document.querySelectorAll('tr.athing.comtr').forEach((row) => {
      const indentPx = Number(row.querySelector('.ind')?.getAttribute('indent') || 0);
      const p = post(
        row.id,
        text(row.querySelector('.hnuser')),
        text(row.querySelector('.commtext')),
        {
          depth: Number.isFinite(indentPx) ? indentPx : 0,
          permalink: row.querySelector('.age a')?.href,
          timestamp: row.querySelector('.age')?.getAttribute('title') || undefined,
        }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // Generic — anything else with a comment section
  // -------------------------------------------------------------------------
  const generic = () => {
    const posts = [];
    const headline = text(document.querySelector('h1')) || document.title;
    const article = document.querySelector('article, main, [role="main"]');
    const lead = text(article).slice(0, 4000);
    const op = post('page', location.hostname, `${headline}\n\n${lead}`.trim(), { depth: 0 });
    if (op) posts.push(op);

    // Anything that smells like a comment node and carries real prose. The
    // 40-char floor drops "Reply" / "Report" chrome that shares the class.
    const seen = new Set();
    const candidates = document.querySelectorAll(
      '[class*="comment" i], [id*="comment" i], [data-testid*="comment" i], .message, .post-body'
    );
    candidates.forEach((el, i) => {
      if (!visible(el)) return;
      // Skip containers whose children are themselves candidates — we want
      // leaves, not the wrapper holding all of them.
      if (el.querySelector('[class*="comment" i], [id*="comment" i]')) return;
      const body = text(el);
      if (body.length < 40) return;
      const key = hash(body.slice(0, 200));
      if (seen.has(key)) return;
      seen.add(key);
      const author =
        text(el.querySelector('[class*="author" i], [class*="user" i], [rel="author"]')) ||
        'commenter';
      const p = post(el.id || `c-${key}-${i}`, author.split('\n')[0], body);
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------

  const host = location.hostname.replace(/^www\./, '');
  let site = 'generic';
  let adapter = generic;
  if (/(^|\.)reddit\.com$/.test(host)) {
    site = 'reddit';
    adapter = reddit;
  } else if (/(^|\.)(x|twitter)\.com$/.test(host)) {
    site = 'x';
    adapter = x;
  } else if (/(^|\.)ycombinator\.com$/.test(host)) {
    site = 'hackernews';
    adapter = hackernews;
  }

  let posts = [];
  let error = null;
  try {
    posts = adapter().filter(Boolean).slice(0, MAX_POSTS);
    // A site adapter that finds nothing (layout changed, wrong page type) is
    // worse than the generic one, so fall back rather than return an empty
    // arena the agent can't argue in.
    if (posts.length === 0 && adapter !== generic) {
      posts = generic().filter(Boolean).slice(0, MAX_POSTS);
      site = 'generic';
    }
  } catch (e) {
    error = String(e);
  }

  return {
    site,
    url: location.href,
    title: clean(document.title) || location.href,
    posts,
    error,
  };
})();
