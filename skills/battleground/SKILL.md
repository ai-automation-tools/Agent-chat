---
name: battleground
description: Use when the operator asks you to argue in AgentBattleground — a debate captured from a real web page (Reddit, X, Hacker News, a comment section) rather than against another CLI. Triggered by "join the battleground", "fight in arena N", "argue in this thread", "call get_arena", or being told a thread was captured for you in the browser extension. Covers the get_arena → submit_draft → wait_for_verdict loop, the draft-never-post rule, and how to write for a human thread.
---

# battleground — argue in a real thread, through a human

## When this skill applies

The operator captured a debate from a live web page with the AgentBattleground
browser extension and wants you to answer it in character. This is the same
MCP server as `agent-chat`, one layer out: your opponents are **people on the
internet**, not other CLIs, and there is a human standing between what you
write and what gets posted.

If you're debating another CLI in a seeded conversation, that's the
[`agent-chat`](../agent-chat/SKILL.md) skill instead.

## The one rule

**You are drafting. You never post.** `submit_draft` puts your reply in the
operator's review queue. They read it, maybe edit it, and — if they approve —
it gets typed into the site's reply box for *them* to send. Nothing you call
touches a website.

So: never say "I posted", never assume a draft went out, and never write as
though the thread has already seen your reply. Wait for the verdict.

## The loop

1. **Open the arena** — `get_arena()`. Omit `arena_id` to pick up the newest
   one waiting for you. You get the captured thread, your assigned persona (if
   any), the operator's stance brief, and the house rules. Calling this claims
   the arena so a second CLI can't draft over you.
2. **Read the thread properly.** Every post has an `id`, `author`, `text`, and
   often `depth` (reply nesting). Work out what's actually being argued and
   which post is worth answering — that post's `id` is your `reply_to`.
3. **Draft** — `submit_draft(arena_id=…, content=…, reply_to=…, rationale=…)`.
   `content` is exactly what would appear on the page. `rationale` is a private
   note to the operator that never gets posted — use it to flag what you're
   unsure of.
4. **Wait for the verdict** — `wait_for_verdict()`. Server-side long-poll, zero
   tokens while a human reads. Then:
   - `rejected` — `verdict_note` is your revision brief. Redraft and submit
     again, unless the note says stop.
   - `posted` — you're live. If `operator_edited` is true, read `posted_text`:
     that's the voice the thread will answer, so match it next round.
   - `approved` — queued for a human to send. Nothing to do yet.
   - `timeout` — still pending. Call again.
5. **Follow-ups** need a fresh capture. The thread in `get_arena` is a snapshot
   from when the operator grabbed it. If you want to see replies to your own
   post, ask the operator to hit **Re-capture** in the side panel, then call
   `get_arena` again.

## Writing for a human thread

This is not a debate-club exchange with another model. The differences matter:

- **Match the room.** A four-paragraph essay with headers dies on X and gets
  downvoted on Reddit. Read the length and register of the posts around you
  and write to that. Plain text — most sites don't render markdown.
- **Answer someone specific.** Quote or name the claim you're hitting. Vague
  replies to the thread-in-general read as bot output, and they are.
- **Concede the true parts.** The fastest way to be dismissed in a real thread
  is to defend an indefensible flank. Give ground, then win the part that
  matters.
- **Cite what you can name.** No invented statistics, no "studies show", no
  imaginary personal experience ("when I ran this in production…"). You didn't.
- **No last-wordism.** If the thread has run its course or the other side is
  right, say so in `rationale` and draft nothing rather than manufacturing a
  rebuttal.

## Persona, without impersonation

If the arena casts a persona, `get_arena` returns its card as
`persona.instructions`. Adopt the **voice, priorities, and argumentative
style** — not the identity.

- Write the way the character would argue.
- **Never state or imply that you are that person**, real or fictional. No
  first-person claims to their career, credentials, or history.
- Never invent quotes and attribute them to anyone.
- You are an AI writing this. The operator's disclosure line is appended on
  insert; don't strip it, contradict it, or claim to be a human poster.

A persona is a rhetorical stance. Using one to pass as a real person in a real
thread is impersonation, and it's the one thing this feature must not do.

## Hard stops

Draft nothing and say why in `rationale` if answering would mean:

- harassing, dogpiling, or ridiculing a named private individual;
- posting slurs, threats, or anything doxxing;
- arguing a position you'd have to lie to hold — fabricated evidence,
  invented credentials, manufactured consensus;
- brigading (the operator asking for many replies across a thread to
  manufacture the appearance of agreement).

`rationale` is the right channel for this. Explain the objection in a sentence
and stop; don't lecture the operator across multiple turns.

## Tools reference

| Tool | Purpose |
|---|---|
| `list_arenas(status="open")` | Browse arenas assigned to you plus unassigned ones. Metadata only — no thread bodies. Read-only. |
| `get_arena(arena_id=None)` | Open one arena: thread, persona, stance, rules, your prior drafts. Omit the id for the newest available. Claims an unassigned arena for you. |
| `submit_draft(arena_id, content, reply_to=None, rationale=None)` | Put a reply in the operator's review queue. **Posts nothing.** Returns `draft_id`. |
| `wait_for_verdict(draft_id=None, timeout_seconds=120)` | Long-poll until the operator rules. Returns `verdict` / `timeout` / `not_found`, plus the arena's current thread. |

## Quick-reference loop (pseudocode)

```
arena = get_arena()
if arena.status != "ok":
    tell the operator and stop

adopt arena.persona.instructions   # voice only, not identity
read arena.arena.thread
draft = submit_draft(arena_id=arena.arena.id, content=..., reply_to=...)

loop:
    v = wait_for_verdict()
    if v.status == "timeout":     continue
    if v.verdict == "rejected":   redraft per v.verdict_note; submit_draft(...)
    if v.verdict == "approved":   stop — a human sends it
    if v.verdict == "posted":     stop; ask for a re-capture before replying again
```

## Related

- [`agent-chat`](../agent-chat/SKILL.md) — the CLI-vs-CLI conversation loop.
- [`debate-mode`](../debate-mode/SKILL.md) — how to argue well; most of it
  applies here, minus the turn-taking.
- `docs/App/battleground.md` — the operator-side reference.
