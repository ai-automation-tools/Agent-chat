// Build-time sync: copy README.md + selected docs/*.md into
// site/src/content/docs/ with Starlight frontmatter and rewritten links.
//
// Source of truth lives at the repo root (README.md + docs/). This script runs
// before `astro dev` and `astro build` so the published site stays in sync.

import { readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../..');
const SITE_DOCS = resolve(ROOT, 'site/src/content/docs');

const FILES = [
  {
    src: 'README.md',
    target: 'index.md',
    titleOverride: 'Agent Chat',
    descriptionOverride:
      'A local MCP server that lets two CLI agents (Claude Code, Codex CLI, etc.) hold structured conversations with each other.',
  },
  { src: 'docs/INITIAL_SETUP.md', target: 'initial-setup.md' },
  { src: 'docs/HOSTING.md', target: 'hosting.md' },
  { src: 'docs/fly-deploy.md', target: 'fly-deploy.md' },
  { src: 'docs/Roadmap.md', target: 'roadmap.md' },
  { src: 'docs/CHANGELOG.md', target: 'changelog.md' },
  { src: 'docs/clis/gemini.md', target: 'clis/gemini.md' },
];

// Cross-doc link rewrites. Order matters: longer keys first so
// "docs/INITIAL_SETUP.md" wins over "INITIAL_SETUP.md".
const LINK_MAP = [
  ['docs/INITIAL_SETUP.md', '/initial-setup/'],
  ['docs/HOSTING.md', '/hosting/'],
  ['docs/fly-deploy.md', '/fly-deploy/'],
  ['docs/Roadmap.md', '/roadmap/'],
  ['docs/CHANGELOG.md', '/changelog/'],
  ['docs/clis/gemini.md', '/clis/gemini/'],
  ['INITIAL_SETUP.md', '/initial-setup/'],
  ['HOSTING.md', '/hosting/'],
  ['fly-deploy.md', '/fly-deploy/'],
  ['Roadmap.md', '/roadmap/'],
  ['CHANGELOG.md', '/changelog/'],
  ['README.md', '/'],
];

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function extractTitle(content) {
  const md = content.match(/^#\s+(.+)$/m);
  if (md) return md[1].trim();
  const html = content.match(/<h1[^>]*>(.*?)<\/h1>/i);
  if (html) return html[1].replace(/<[^>]+>/g, '').trim();
  return null;
}

function stripFirstH1(content) {
  // Strip a markdown H1 line, or an HTML <h1>...</h1> block.
  let out = content.replace(/^#\s+.+\r?\n/, '');
  if (out === content) {
    out = content.replace(/<h1[^>]*>[\s\S]*?<\/h1>\s*/i, '');
  }
  return out;
}

function rewriteLinks(content) {
  let out = content;
  for (const [src, dst] of LINK_MAP) {
    // Match a markdown link target like (path), (./path), or (path#anchor).
    const re = new RegExp(
      '\\((?:\\.\\/)?' + escapeRegex(src) + '(#[^)]+)?\\)',
      'g',
    );
    out = out.replace(re, (_m, anchor) => '(' + dst + (anchor || '') + ')');
  }
  return out;
}

function buildFrontmatter({ title, description }) {
  const lines = ['---', `title: ${JSON.stringify(title)}`];
  if (description) lines.push(`description: ${JSON.stringify(description)}`);
  lines.push('---', '');
  return lines.join('\n');
}

async function syncOne({ src, target, titleOverride, descriptionOverride }) {
  const srcPath = resolve(ROOT, src);
  const dstPath = resolve(SITE_DOCS, target);
  if (!existsSync(srcPath)) {
    console.warn(`[sync-docs] missing source, skipping: ${src}`);
    return;
  }
  let raw = await readFile(srcPath, 'utf8');
  const title = titleOverride || extractTitle(raw) || target;
  const description = descriptionOverride;
  let body = stripFirstH1(raw);
  body = rewriteLinks(body);
  const out = buildFrontmatter({ title, description }) + body;
  await mkdir(dirname(dstPath), { recursive: true });
  await writeFile(dstPath, out, 'utf8');
  console.log(`[sync-docs] ${src} -> site/src/content/docs/${target}`);
}

async function main() {
  if (existsSync(SITE_DOCS)) {
    await rm(SITE_DOCS, { recursive: true, force: true });
  }
  await mkdir(SITE_DOCS, { recursive: true });
  for (const file of FILES) await syncOne(file);
}

main().catch((err) => {
  console.error('[sync-docs] failed:', err);
  process.exit(1);
});
