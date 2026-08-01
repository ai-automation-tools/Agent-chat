/**
 * AgentBattleground — everything the operator looks at.
 *
 * Three pieces beyond the plumbing:
 *
 * * **The capture preview** — exactly the posts the agent will be handed, in
 *   order, with nesting and the adapter that found them. A capture that fell
 *   back to `generic` says so, because that is the difference between "the
 *   agent read the argument" and "the agent read the page furniture".
 * * **The handoff card** — the prompt to paste into the CLI, ready to copy,
 *   plus the command that starts that CLI in the right folder.
 * * **The review list** — delegated to `drafts.js`.
 */

import { PREVIEW_CHARS, $, el, copyText, say, state } from './state.js';
import { currentTarget, setReplyTarget } from './arena.js';
import { renderDraft } from './drafts.js';

// ---------------------------------------------------------------------------
// Capture preview
// ---------------------------------------------------------------------------

/** The thread the agent currently has: the arena's if open, else the capture. */
function previewPosts() {
  if (state.arena) return state.arena.arena.thread || [];
  return state.capture?.posts || [];
}

function previewSite() {
  if (state.arena) return state.arena.arena.site;
  return state.capture?.site || null;
}

export function renderPreview() {
  const card = $('preview-card');
  const posts = previewPosts();
  card.classList.toggle('hidden', posts.length === 0);
  if (!posts.length) return;

  const site = previewSite();
  const frames = state.capture?.frames || 1;
  const authors = new Set(posts.map((p) => p.author || 'unknown')).size;
  $('preview-meta').textContent =
    `${posts.length} post${posts.length === 1 ? '' : 's'} · ${authors} author${
      authors === 1 ? '' : 's'
    } · ${site}${frames > 1 ? ` · ${frames} frames` : ''}`;

  const warn = $('preview-warn');
  if (site === 'generic') {
    warn.classList.remove('hidden');
    warn.textContent =
      'No site adapter matched, so this is the generic reader: page headline ' +
      'plus any text block over 40 characters. Check the posts below are ' +
      'actually the argument before you open an arena.';
  } else {
    warn.classList.add('hidden');
  }

  const toggle = $('preview-toggle');
  toggle.textContent = state.previewOpen ? 'Hide posts' : `Show ${posts.length} posts`;

  const list = $('preview-posts');
  list.classList.toggle('hidden', !state.previewOpen);
  list.innerHTML = '';
  if (!state.previewOpen) return;

  const target = currentTarget();
  for (const post of posts) {
    const row = el('li', 'post');
    const depth = Math.min(Number(post.depth) || 0, 8);
    row.style.marginLeft = `${depth * 10}px`;
    if (post.id === target) row.classList.add('targeted');

    const head = el('div', 'post-head');
    head.append(el('span', 'post-author', post.author || 'unknown'));
    const bits = [];
    if (post.score) bits.push(post.score);
    if (post.timestamp) bits.push(post.timestamp);
    if (bits.length) head.append(el('span', 'post-meta', bits.join(' · ')));
    row.append(head);

    const body = (post.text || '').replace(/\s+/g, ' ').trim();
    row.append(
      el(
        'p',
        'post-body',
        body.length > PREVIEW_CHARS ? `${body.slice(0, PREVIEW_CHARS)}…` : body
      )
    );

    const aim = el(
      'button',
      'link',
      post.id === target ? '✓ agent answers this' : 'Answer this one'
    );
    aim.title =
      'Hand this post to the agent as its reply target (get_arena returns it ' +
      'as reply_target).';
    aim.onclick = () => setReplyTarget(post.id);
    row.append(aim);
    list.append(row);
  }
}

/** The one-line "who is being answered" note shown on the cast/arena cards. */
function renderTargetLine(id) {
  const node = $(id);
  if (!node) return;
  const target = currentTarget();
  if (!target) {
    node.className = 'msg';
    node.textContent =
      'No reply target picked — the agent chooses which post to answer.';
    return;
  }
  const post = previewPosts().find((p) => p.id === target);
  node.className = 'msg ok';
  node.textContent = `Answering ${post ? post.author : target}${
    post ? `: “${(post.text || '').replace(/\s+/g, ' ').slice(0, 60)}…”` : ''
  }`;
}

// ---------------------------------------------------------------------------
// CLI handoff
// ---------------------------------------------------------------------------

/** The prompt the operator pastes into the CLI to start the agent's loop. */
export function handoffPrompt() {
  if (!state.arena) return '';
  const a = state.arena.arena;
  const lines = [
    `Join AgentBattleground arena #${a.id}.`,
    '',
    `Call get_arena(arena_id=${a.id}), read the captured thread, then write one`,
    `reply and call submit_draft(arena_id=${a.id}, content=..., reply_to=...).`,
    'Then call wait_for_verdict() and wait — I review it in the browser panel.',
    'You are drafting, not posting. Nothing you write reaches the page until I',
    'approve it.',
  ];
  return lines.join('\n');
}

/** How to start the cast CLI, from the folder that carries its MCP config. */
function launchCommand() {
  const agent = state.arena?.arena?.agent_id || state.settings.agent;
  const entry = state.roster?.launch?.[agent];
  if (!entry) return '';
  return `cd ${entry.dir}; ${entry.exe}`;
}

function renderHandoff() {
  if (!state.arena) return;
  const agent = state.arena.arena.agent_id || 'whichever CLI picks it up';
  $('handoff-cli').textContent = agent;
  $('handoff-prompt').value = handoffPrompt();
  const launch = launchCommand();
  $('copy-launch').classList.toggle('hidden', !launch);
  $('copy-launch').title = launch
    ? `Copies: ${launch}\n\nRun it in your own terminal — the extension never spawns anything.`
    : '';
}

export function wireHandoff() {
  $('copy-prompt').onclick = async () => {
    const ok = await copyText(handoffPrompt());
    say(
      'handoff-msg',
      ok ? 'Copied — paste it into the CLI.' : 'Couldn’t reach the clipboard; select the text and copy it.',
      ok ? 'ok' : 'err'
    );
  };
  $('copy-launch').onclick = async () => {
    const cmd = launchCommand();
    if (!cmd) return;
    const ok = await copyText(cmd);
    say(
      'handoff-msg',
      ok ? `Copied: ${cmd}` : 'Couldn’t reach the clipboard.',
      ok ? 'ok' : 'err'
    );
  };
  $('preview-toggle').onclick = () => {
    state.previewOpen = !state.previewOpen;
    renderPreview();
  };
}

// ---------------------------------------------------------------------------
// The whole panel
// ---------------------------------------------------------------------------

export function render() {
  const hasCapture = Boolean(state.capture);
  const hasArena = Boolean(state.arena);

  $('cast-card').classList.toggle('hidden', !hasCapture || hasArena);
  $('arena-card').classList.toggle('hidden', !hasArena);
  $('drafts-card').classList.toggle('hidden', !hasArena);
  $('capture').textContent = hasArena ? 'Re-capture this thread' : 'Capture this thread';

  renderPreview();
  if (!hasArena) {
    renderTargetLine('cast-target');
    return;
  }

  const a = state.arena.arena;
  $('arena-id').textContent = `#${a.id}`;
  const cast = a.persona_name
    ? `${a.agent_id || 'unassigned'} as ${a.persona_name}`
    : a.agent_id || 'unassigned';
  $('arena-meta').textContent =
    `${a.status} · ${a.site} · ${a.thread.length} posts · ${cast}`;
  renderTargetLine('arena-target');
  renderHandoff();
  $('handoff').classList.toggle('hidden', state.arena.drafts.length > 0);
  $('close-arena').disabled = a.status !== 'open';
  renderAutoStatus();

  const list = $('drafts');
  list.innerHTML = '';
  if (!state.arena.drafts.length) {
    list.append(el('p', 'msg', 'No drafts yet — waiting on the agent.'));
  }
  for (const draft of [...state.arena.drafts].reverse()) list.append(renderDraft(draft));
}

export function renderAutoStatus(note) {
  const node = $('auto-status');
  if (!node) return;
  if (!state.settings.autoRecapture) {
    node.textContent = 'off — re-capture by hand';
    return;
  }
  const since = state.lastAutoAt
    ? `${Math.round((Date.now() - state.lastAutoAt) / 1000)}s ago`
    : 'not yet';
  node.textContent = `every ${state.settings.autoSeconds}s · last ${since}${
    note ? ` · ${note}` : ''
  }`;
}
