/**
 * AgentBattleground — the review queue: one card per draft, and the verdict
 * gate that is the whole point of the feature.
 *
 * Approving does two things and stops: it records the verdict, and it types
 * the text into the page's existing composer. The site's post button is the
 * operator's to press.
 */

import { $, el, state } from './state.js';
import { api } from './bridge.js';
import { requestPageAccess } from './permissions.js';
import { insertIntoComposer, probeComposer, readComposerText } from './compose.js';
import { openArena } from './arena.js';

/**
 * One-click revision briefs. Each sends a `rejected` verdict whose note the
 * agent reads as a redraft instruction, which beats typing the same five
 * sentences into the note box every round.
 */
const QUICK_NOTES = [
  ['Shorter', 'Too long for this thread. Cut it to roughly half — keep the strongest single point and drop the rest.'],
  ['Less sharp', 'The tone is too combative for this room. Same argument, lower temperature, no jabs at the person.'],
  ['More evidence', 'The claims need support you can actually name. Cite specific, checkable sources or drop the claim.'],
  ['Concede a point', 'Give ground on the part they got right before arguing the part that matters. It reads as unbeatable-and-therefore-ignorable right now.'],
  ['Match the room', 'Read the length, formatting, and register of the surrounding posts and write to that instead.'],
  ['Answer someone', 'Too general. Answer one specific post and name the claim you are hitting — set reply_to.'],
];

/**
 * Local, cheap sanity checks shown above the Approve button.
 *
 * Heuristics, not judgements: they catch the failures that are obvious from
 * the text alone (an essay dropped into a thread of one-liners, "studies
 * show", the LLM tells house rule 7 asks the agent to avoid) and stay quiet
 * otherwise. Nothing here blocks approval.
 */
function draftChecks(text) {
  const flags = [];
  const body = text.trim();
  const lower = body.toLowerCase();

  const posts = state.arena?.arena?.thread || [];
  const lengths = posts.map((p) => (p.text || '').length).filter(Boolean).sort((a, b) => a - b);
  const median = lengths.length ? lengths[Math.floor(lengths.length / 2)] : 0;
  if (median && body.length > median * 3 && body.length > 600) {
    flags.push(['warn', `Roughly ${Math.round(body.length / median)}× the typical post here (${median} chars).`]);
  }

  const tells = [
    'stands as a testament', 'plays a crucial role', 'underscores the importance',
    'delve into', 'rich tapestry', 'it’s not just', "it's not just",
    'in today’s world', "in today's world", 'a testament to',
  ];
  const hit = tells.filter((t) => lower.includes(t));
  if (hit.length) flags.push(['warn', `LLM tell: “${hit[0]}” (house rule 7).`]);

  const overclaims = ['studies show', 'research proves', 'everyone knows', 'it is well known', 'science says'];
  const over = overclaims.filter((t) => lower.includes(t));
  if (over.length) flags.push(['warn', `Unsourced authority: “${over[0]}”. Name the source or cut it.`]);

  // The two rule-7 tells the `tells` list above structurally cannot see: both
  // are shape rather than vocabulary, so a draft that dodged every banned
  // phrase still trips them. Rule of three is the third, and is left to the
  // prompt — no string match separates it from an ordinary list of three.
  const parallel = body.match(
    /\b(?:it['’]?s|that['’]?s|this is)\s+not\s+(?:just\s+)?[^.,;!?]{1,48},\s*(?:it['’]?s|that['’]?s|it is)\b/i
  );
  if (parallel) {
    flags.push(['warn', `Negative parallelism: “${parallel[0].trim()}…” (house rule 7). Keep the second half, cut the setup.`]);
  }

  const dashes = (body.match(/—/g) || []).length;
  if (dashes >= 3) {
    flags.push(['warn', `${dashes} em dashes (house rule 7). Fine sparingly; in bulk they read as machine rhythm.`]);
  }

  if (/\b(i|we) (built|ran|shipped|worked|tested|deployed)\b/i.test(body)) {
    flags.push(['bad', 'Reads as first-hand experience. The agent has none — check this before approving.']);
  }

  if (state.settings.disclose) {
    flags.push(['ok', 'AI-disclosure line will be appended on insert.']);
  } else {
    flags.push(['bad', 'Disclosure is OFF — this will be typed in with no AI marker.']);
  }

  return flags;
}

function withDisclosure(text) {
  if (!state.settings.disclose) return text;
  const suffix = state.settings.disclosureText || '';
  return text.includes(suffix.trim()) ? text : text + suffix;
}

// ---------------------------------------------------------------------------
// Verdicts
// ---------------------------------------------------------------------------

/**
 * Approve a draft and type it in.
 *
 * If the composer already holds something we stop and ask first, rather than
 * silently overwriting whatever the operator was part-way through writing.
 * The verdict is recorded on the way *out* of that choice, so the pending card
 * — and its question — survive on screen until the operator answers.
 */
async function approveAndInsert(draft, editedText, access) {
  const finalText = withDisclosure(editedText);
  const probe = await probeComposer(access);
  if (probe.ok && probe.found && probe.text.trim()) {
    askInsertMode(draft, finalText, probe);
    return;
  }
  await commitApproval(draft, finalText, {
    mode: 'replace',
    frameId: probe.ok ? probe.frameId : null,
  });
}

async function commitApproval(draft, finalText, { mode, frameId, access = null }) {
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'approved', posted_text: finalText },
  });
  const res = await insertIntoComposer(finalText, { mode, frameId, access });
  // Re-render first: the card flips pending → approved, and every card state
  // carries a `draft-msg-<id>` line for the report to land in.
  await openArena(state.arena.arena.id);
  reportInsert(draft.id, res);
}

/** The replace / append / prepend choice, only shown when it matters. */
function askInsertMode(draft, finalText, probe) {
  const host = $(`draft-mode-${draft.id}`);
  if (!host) return;
  host.innerHTML = '';
  host.classList.remove('hidden');
  host.append(
    el(
      'p',
      'msg warn',
      `The reply box already has ${probe.text.trim().length} characters in it. ` +
        'What should happen to them?'
    )
  );
  const row = el('div', 'row');
  for (const [label, mode] of [
    ['Replace', 'replace'],
    ['Append', 'append'],
    ['Prepend', 'prepend'],
  ]) {
    const btn = el('button', mode === 'replace' ? 'primary' : null, label);
    btn.onclick = () => {
      const access = requestPageAccess();
      commitApproval(draft, finalText, { mode, frameId: probe.frameId, access });
    };
    row.append(btn);
  }
  host.append(row);
}

/** Say what actually happened to the page, including the read-back result. */
function reportInsert(draftId, res) {
  const note = $(`draft-msg-${draftId}`);
  if (!note) return;
  if (!res.ok) {
    note.className = 'msg err';
    note.textContent = `Approved, but nothing was typed: ${res.reason}`;
    return;
  }
  if (res.verified && res.flattened) {
    note.className = 'msg warn';
    note.textContent =
      'Typed and read back, but every paragraph break was lost — the text is ' +
      'in the box as one block. Fix the spacing on the page before posting.';
  } else if (res.verified) {
    note.className = 'msg ok';
    note.textContent =
      `Typed into the page (${res.where}${res.mode && res.mode !== 'replace' ? `, ${res.mode}` : ''}) ` +
      'and read back. Check it once more, then hit the site’s own post button.';
  } else {
    note.className = 'msg warn';
    note.textContent =
      'Typed, but reading the box back didn’t show the text — the editor may ' +
      'have rejected it. Look at the page before posting.';
  }
}

async function markPosted(draft) {
  // Read the composer rather than trusting our own copy — the operator may
  // have edited in the page after insertion, and the agent should learn the
  // voice that actually shipped.
  let posted = draft.posted_text || draft.content;
  try {
    const live = await readComposerText();
    if (live.trim()) posted = live;
  } catch {
    /* composer already cleared by the site after posting — keep our copy */
  }
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'posted', posted_text: posted },
  });
  await openArena(state.arena.arena.id);
}

async function rejectDraft(draft, note) {
  await api(`/drafts/${draft.id}/verdict`, {
    method: 'POST',
    body: { verdict: 'rejected', note: note || null },
  });
  await openArena(state.arena.arena.id);
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

export function renderDraft(draft) {
  const card = el('div', `draft ${draft.status}`);

  const head = el('div', 'draft-head');
  head.append(el('span', 'draft-status', draft.status));
  const meta = [`#${draft.id}`, draft.agent_id];
  if (draft.reply_to) meta.push(`↳ ${draft.reply_to}`);
  head.append(el('span', null, meta.join(' · ')));
  card.append(head);

  if (draft.status === 'pending') {
    const box = document.createElement('textarea');
    box.rows = Math.min(16, Math.max(4, Math.ceil(draft.content.length / 60)));
    box.value = draft.content;
    card.append(box);

    if (draft.rationale) {
      card.append(el('p', 'rationale', `Agent’s note: ${draft.rationale}`));
    }

    const checks = el('ul', 'checks');
    const paint = () => {
      checks.innerHTML = '';
      for (const [kind, text] of draftChecks(box.value)) {
        checks.append(el('li', kind, text));
      }
    };
    paint();
    box.addEventListener('change', paint);
    card.append(checks);

    const row = el('div', 'row');
    const approve = el('button', 'primary', 'Approve & type into page');
    approve.onclick = () => approveAndInsert(draft, box.value, requestPageAccess());
    const reject = el('button', null, 'Reject…');
    row.append(approve, reject);
    card.append(row);

    const modeHost = el('div', 'hidden');
    modeHost.id = `draft-mode-${draft.id}`;
    card.append(modeHost);

    const rejectBox = el('div', 'reject hidden');
    const quick = el('div', 'row quick');
    for (const [label, note] of QUICK_NOTES) {
      const btn = el('button', 'small', label);
      btn.title = note;
      btn.onclick = () => rejectDraft(draft, note);
      quick.append(btn);
    }
    rejectBox.append(el('p', 'msg', 'Send it back with a brief:'), quick);

    const noteRow = el('div', 'row');
    const noteInput = document.createElement('input');
    noteInput.type = 'text';
    noteInput.placeholder = 'Or write your own…';
    const send = el('button', null, 'Send back');
    send.onclick = () => rejectDraft(draft, noteInput.value.trim());
    noteRow.append(noteInput, send);
    rejectBox.append(noteRow);
    card.append(rejectBox);

    reject.onclick = () => {
      rejectBox.classList.toggle('hidden');
      if (!rejectBox.classList.contains('hidden')) noteInput.focus();
    };
  } else {
    card.append(el('p', 'draft-body', draft.posted_text || draft.content));
    if (draft.verdict_note) {
      card.append(el('p', 'rationale', `Your note: ${draft.verdict_note}`));
    }
  }

  if (draft.status === 'approved') {
    const row = el('div', 'row');
    const again = el('button', null, 'Type into page again');
    again.onclick = async () => {
      const access = requestPageAccess();
      const probe = await probeComposer(access);
      const res = await insertIntoComposer(draft.posted_text || draft.content, {
        mode: 'replace',
        frameId: probe.ok ? probe.frameId : null,
      });
      reportInsert(draft.id, res);
    };
    const posted = el('button', 'primary', 'I posted it');
    posted.onclick = () => markPosted(draft);
    row.append(again, posted);
    card.append(row);
  }

  const msg = el('p', 'msg');
  msg.id = `draft-msg-${draft.id}`;
  card.append(msg);
  return card;
}
