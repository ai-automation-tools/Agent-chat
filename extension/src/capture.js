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
 * Output shape (matches what POST /api/battleground/arenas expects, plus the
 * frame bookkeeping the panel needs to merge a comment iframe into the page):
 *
 *   { site, url, title, posts: [{ id, author, text, permalink?, score?,
 *                                 timestamp?, depth? }],
 *     top, frameUrl, frameHints: ["https://disqus.com/*", …], error }
 *
 * Each adapter's job is only to find posts and give each a *stable* id — the
 * bridge merges re-captures on that id, so a good one (the site's own comment
 * id) means an operator can re-capture a thread mid-argument and the agent
 * sees exactly the new replies rather than a shuffled pile of duplicates.
 *
 * The file is injected into **every frame** the extension has access to, not
 * just the top one, because half the comment sections on the web live in a
 * third-party iframe (Disqus and friends). A subframe therefore never emits a
 * page-lead post — only real comments — so an ad iframe that happens to be in
 * scope contributes nothing.
 */

(() => {
  const MAX_POSTS = 200;
  const MAX_CHARS = 8000;

  const TOP = window === window.top;

  /** Third-party comment platforms that render into an iframe. */
  const COMMENT_FRAME_HOSTS =
    /(^|\.)(disqus\.com|spot\.im|openweb\.com|hyvor\.com|commento\.io|viafoura\.co|fastcomments\.com|coral\.coralproject\.net)$/;

  const clean = (s) =>
    (s || '')
      .replace(/ /g, ' ')
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

  const attr = (el, name) => el?.getAttribute(name) || '';

  /**
   * First element matching the *first selector that matches anything*.
   *
   * Not the same as `querySelector('a, b, c')`, which returns whichever match
   * comes first in the document regardless of which selector found it — so a
   * broad last resort like `h1` wins over a precise `h1.post-title` that sits
   * further down the page. Use this wherever the list is a preference order.
   */
  const pick = (...selectors) => {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  };

  const meta = (name) =>
    clean(
      attr(document.querySelector(`meta[property="${name}"], meta[name="${name}"]`), 'content')
    );

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

  /**
   * First descendant matching `sel` that belongs to `root` itself rather than
   * to a nested comment inside it. Threaded layouts (Substack, Discourse,
   * Disqus, LinkedIn) nest replies inside their parent's DOM node, so a naive
   * querySelector swallows the whole subtree into one post.
   */
  const firstOwn = (root, sel, boundary) => {
    for (const el of root.querySelectorAll(sel)) {
      if (el.closest(boundary) === root) return el;
    }
    return null;
  };

  /** Nesting depth of a comment node inside its own kind. */
  const nestDepth = (el, boundary, base = 0) => {
    let d = base;
    for (let p = el.parentElement; p && d < 50; p = p.parentElement) {
      if (p.matches(boundary)) d += 1;
    }
    return d;
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
        attr(shredditPost, 'id') || 'op',
        attr(shredditPost, 'author'),
        `${attr(shredditPost, 'post-title')}\n\n${body}`.trim(),
        { score: attr(shredditPost, 'score') || undefined, depth: 0 }
      );
      if (p) posts.push(p);
    } else {
      // Old reddit / partial renders: title + selftext.
      const title = text(pick('.thing .title a', 'h1'));
      const body = text(pick('.thing .usertext-body .md', '[data-test-id="post-content"]'));
      const author = text(document.querySelector('.thing .author'));
      const p = post('op', author, `${title}\n\n${body}`.trim(), { depth: 0 });
      if (p) posts.push(p);
    }

    document.querySelectorAll('shreddit-comment').forEach((c) => {
      const depth = Number(attr(c, 'depth') || 0);
      const p = post(
        attr(c, 'thingid') || attr(c, 'id'),
        attr(c, 'author'),
        text(c.querySelector('[slot="comment"]')),
        { depth: Number.isFinite(depth) ? depth : 0, score: attr(c, 'score') || undefined }
      );
      if (p) posts.push(p);
    });

    if (posts.length <= 1) {
      // Old reddit comment tree.
      document.querySelectorAll('.thing.comment').forEach((c) => {
        const p = post(
          attr(c, 'data-fullname'),
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
        { permalink: href || undefined, timestamp: attr(a.querySelector('time'), 'datetime') || undefined }
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
    const title = text(pick('.titleline a', '.title a'));
    const story = text(pick('.toptext', '.fatitem .commtext'));
    const op = post('story', text(document.querySelector('.hnuser')), `${title}\n\n${story}`.trim(), { depth: 0 });
    if (op) posts.push(op);

    document.querySelectorAll('tr.athing.comtr').forEach((row) => {
      const indentPx = Number(attr(row.querySelector('.ind'), 'indent') || 0);
      const p = post(
        row.id,
        text(row.querySelector('.hnuser')),
        text(row.querySelector('.commtext')),
        {
          depth: Number.isFinite(indentPx) ? indentPx : 0,
          permalink: row.querySelector('.age a')?.href,
          timestamp: attr(row.querySelector('.age'), 'title') || undefined,
        }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // YouTube — video + the loaded comment threads
  //
  // Stable id: the `lc=` parameter on a comment's timestamp link is YouTube's
  // own comment id. It survives sort changes and re-renders, which the DOM
  // element ids do not.
  // -------------------------------------------------------------------------
  const youtube = () => {
    const posts = [];
    const videoId = new URLSearchParams(location.search).get('v') || location.pathname.split('/').pop();

    const title = text(
      pick('#above-the-fold #title h1', 'ytd-watch-metadata h1', 'h1.ytd-video-primary-info-renderer')
    ) || meta('og:title');
    const channel = text(pick('#owner #channel-name a', 'ytd-channel-name a', '#upload-info #channel-name'));
    const description = text(pick('#description-inline-expander', '#description-inner', '#meta #description'));
    const op = post(`video-${videoId || 'op'}`, channel || 'uploader', `${title}\n\n${description}`.trim(), {
      depth: 0,
      permalink: location.href.split('&')[0],
    });
    if (op) posts.push(op);

    const commentNodes = document.querySelectorAll('ytd-comment-view-model, ytd-comment-renderer');
    commentNodes.forEach((c, i) => {
      // The older `ytd-comment-renderer` sometimes wraps the newer node; take
      // the leaf so a comment isn't captured twice.
      if (c.querySelector('ytd-comment-view-model')) return;
      const timeLink = c.querySelector('#published-time-text a, a.yt-simple-endpoint[href*="lc="]');
      const lc = attr(timeLink, 'href').match(/[?&]lc=([^&]+)/)?.[1];
      const p = post(
        lc ? decodeURIComponent(lc) : c.id || `yt-comment-${i}`,
        text(c.querySelector('#author-text, #header-author #author-text')),
        text(c.querySelector('#content-text')),
        {
          depth: c.closest('ytd-comment-replies-renderer') ? 2 : 1,
          score: text(c.querySelector('#vote-count-middle')) || undefined,
          timestamp: text(timeLink) || undefined,
          permalink: timeLink?.href || undefined,
        }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // LinkedIn — a feed post and its comment tree
  // -------------------------------------------------------------------------
  const linkedin = () => {
    const posts = [];
    const root =
      pick('.feed-shared-update-v2', '[data-urn*="activity"]', '.full-height main') || document.body;

    const urn = attr(root, 'data-urn') || attr(root, 'data-id') || 'post';
    const op = post(
      urn,
      text(root.querySelector('.update-components-actor__title, .update-components-actor__name')).split('\n')[0],
      text(
        root.querySelector(
          '.update-components-text, .feed-shared-inline-show-more-text, .update-components-update-v2__commentary'
        )
      ),
      { depth: 0, permalink: location.href.split('?')[0] }
    );
    if (op) posts.push(op);

    const BOUNDARY = 'article.comments-comment-entity, .comments-comment-item, .comments-comment-entity';
    document.querySelectorAll(BOUNDARY).forEach((c, i) => {
      const id = attr(c, 'data-id') || attr(c, 'data-urn') || c.id || `li-comment-${i}`;
      const p = post(
        id,
        text(
          firstOwn(c, '.comments-comment-meta__description-title, .comments-post-meta__name-text', BOUNDARY)
        ).split('\n')[0],
        text(firstOwn(c, '.comments-comment-item__main-content, .update-components-text', BOUNDARY)),
        { depth: nestDepth(c, BOUNDARY, 1) }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // Substack — the post plus its (threaded) comments
  // -------------------------------------------------------------------------
  const substack = () => {
    const posts = [];
    // og:title and meta author are what Substack's own share cards use, and
    // they're right on every theme — the visible h1 is often the masthead.
    const title = meta('og:title') || text(pick('h1.post-title', 'h1[class*="post-title"]', 'article h1'));
    const author =
      meta('author') || text(pick('.byline-names', '.post-header .profile-hover-card-target a'));
    const body = text(pick('.available-content', '.body.markup', 'article .markup'));
    const op = post(
      `post-${location.pathname.split('/').filter(Boolean).pop() || 'op'}`,
      author || location.hostname,
      `${title}\n\n${body}`.trim(),
      { depth: 0, permalink: location.href.split('?')[0] }
    );
    if (op) posts.push(op);

    const BOUNDARY = '.comment, [class*="comment_"][id^="comment-"]';
    document.querySelectorAll(BOUNDARY).forEach((c, i) => {
      const anchored = c.id || attr(c, 'data-comment-id') || firstOwn(c, '[id^="comment-"]', BOUNDARY)?.id;
      const p = post(
        anchored || `sub-comment-${i}`,
        text(firstOwn(c, '.comment-meta a, .commenter-name, [class*="name"] a', BOUNDARY)).split('\n')[0],
        text(firstOwn(c, '.comment-body, .comment-content .body, [class*="comment-body"]', BOUNDARY)),
        { depth: nestDepth(c, BOUNDARY, 1) }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // Discourse — runs on the forum's own domain, so it's sniffed from the DOM
  // rather than the hostname. `data-post-id` is the forum's own id.
  // -------------------------------------------------------------------------
  const discourse = () => {
    const posts = [];
    const title = text(pick('#topic-title .fancy-title', 'h1 .fancy-title', '#topic-title h1'));

    document.querySelectorAll('article[data-post-id], .topic-post article').forEach((a, i) => {
      const id = attr(a, 'data-post-id') || attr(a, 'id').replace(/^post_/, '') || `post-${i}`;
      const body = text(a.querySelector('.cooked'));
      // The username link can still be an empty shell while the post header
      // hydrates; `data-user-card` carries the name as an attribute either way.
      const nameEl = a.querySelector('.names .username a, .names .username, [data-user-card]');
      const p = post(
        id,
        text(nameEl).split('\n')[0] || attr(a.querySelector('[data-user-card]'), 'data-user-card'),
        i === 0 && title ? `${title}\n\n${body}`.trim() : body,
        {
          // Discourse is flat by default; only quoted/embedded replies nest.
          depth: a.closest('.embedded-posts, .reply-to-tab') ? 1 : 0,
          permalink: a.querySelector('.post-info.post-date a')?.href,
          timestamp: attr(a.querySelector('.post-date .relative-date'), 'title') || undefined,
          score: text(a.querySelector('.post-likes')) || undefined,
        }
      );
      if (p) posts.push(p);
    });
    return posts;
  };

  // -------------------------------------------------------------------------
  // Disqus — only ever reached inside the disqus.com iframe
  // -------------------------------------------------------------------------
  const disqus = () => {
    const posts = [];
    const BOUNDARY = 'li.post, .post[id^="post-"]';
    document.querySelectorAll(BOUNDARY).forEach((el, i) => {
      const id = (el.id || attr(el, 'data-id') || `disqus-${i}`).replace(/^post-/, '');
      const p = post(
        id,
        text(firstOwn(el, '.author a, .author, [data-role="username"]', BOUNDARY)).split('\n')[0],
        text(firstOwn(el, '.post-message, .post-body .post-message', BOUNDARY)),
        {
          depth: nestDepth(el, BOUNDARY, 0),
          timestamp: attr(el.querySelector('.time-ago'), 'title') || undefined,
          score: text(el.querySelector('.vote-up .updatable')) || undefined,
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

    // Only the top frame contributes a page lead. A subframe emitting one
    // would drag every ad iframe's boilerplate into the arena.
    if (TOP) {
      const headline = text(document.querySelector('h1')) || document.title;
      const article = document.querySelector('article, main, [role="main"]');
      const lead = text(article).slice(0, 4000);
      const op = post('page', location.hostname, `${headline}\n\n${lead}`.trim(), { depth: 0 });
      if (op) posts.push(op);
    }

    // Anything that smells like a comment node and carries real prose. The
    // 40-char floor drops "Reply" / "Report" chrome that shares the class.
    const seen = new Set();
    const candidates = document.querySelectorAll(
      '[class*="comment" i], [id*="comment" i], [data-testid*="comment" i], [itemtype$="Comment"], .message, .post-body'
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
  // Site detection
  //
  // Hostname first for the single-domain sites, then a DOM sniff for the
  // platforms that live on their customers' own domains (Substack, Discourse).
  // -------------------------------------------------------------------------

  const detect = () => {
    const host = location.hostname.replace(/^www\./, '');
    if (/(^|\.)reddit\.com$/.test(host)) return ['reddit', reddit];
    if (/(^|\.)(x|twitter)\.com$/.test(host)) return ['x', x];
    if (/(^|\.)ycombinator\.com$/.test(host)) return ['hackernews', hackernews];
    if (/(^|\.)(youtube\.com|youtu\.be)$/.test(host)) return ['youtube', youtube];
    if (/(^|\.)linkedin\.com$/.test(host)) return ['linkedin', linkedin];
    if (/(^|\.)disqus\.com$/.test(host)) return ['disqus', disqus];

    if (
      /(^|\.)substack\.com$/.test(host) ||
      document.querySelector('script[src*="substackcdn"], link[href*="substackcdn"], meta[name="parsely-type"][content="post"] ~ link[href*="substack"]')
    ) {
      return ['substack', substack];
    }

    const generator = attr(document.querySelector('meta[name="generator"]'), 'content');
    if (
      /discourse/i.test(generator) ||
      document.querySelector('meta[name="discourse_theme_id"], #main-outlet .topic-post, body.discourse-page')
    ) {
      return ['discourse', discourse];
    }

    return ['generic', generic];
  };

  /** Origins of third-party comment iframes the operator could opt into. */
  const frameHints = () => {
    if (!TOP) return [];
    const origins = new Set();
    document.querySelectorAll('iframe[src]').forEach((f) => {
      let url;
      try {
        url = new URL(f.src, location.href);
      } catch {
        return;
      }
      if (url.origin === location.origin) return;
      const host = url.hostname.replace(/^www\./, '');
      if (COMMENT_FRAME_HOSTS.test(host)) origins.add(`${url.origin}/*`);
    });
    return [...origins];
  };

  // -------------------------------------------------------------------------

  let [site, adapter] = detect();
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
    url: TOP ? location.href : (document.referrer || location.href),
    title: clean(document.title) || location.href,
    posts,
    top: TOP,
    frameUrl: location.href,
    frameHints: frameHints(),
    error,
  };
})();
