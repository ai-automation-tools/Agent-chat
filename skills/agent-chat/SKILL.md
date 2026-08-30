---
name: agent-chat
description: Use when joining a multi-CLI agent_chat conversation via the agent_chat MCP server. Triggered by prompts like "join the agent_chat conversation", "participate in the conversation", "call get_kickoff", or being spawned by the agent-chat debate orchestrator. Covers the get_kickoff → wait_for_turn → send_message loop, signal='done'/'blocked'/'result' semantics, turn-taking rules, and the "don't ask the operator between turns" expectation.
---

# agent-chat — participate in a multi-CLI conversation

## When this skill applies

You've been told to join an `agent_chat` conversation — typically by an opening prompt that says "call `get_kickoff()`", "start the loop", "join the conversation", or you've been spawned by the agent-chat orchestrator. The other participants are CLI agents (Codex, Antigravity, another Claude Code instance, etc.) connected to the same `agent_chat` MCP server. The operator seeded the conversation and walked away — they are not standing by for questions.

## The loop

1. **Fetch the kickoff once** — call `get_kickoff()` at the very top of your session. Three possible statuses:
   - `ok` — follow the rendered prompt body it returns. It carries the topic, your tone, and the conversation conventions the operator picked.
   - `fallback` — no template was rendered for this conversation. Default to a focused, on-topic exchange on the returned topic field.
   - `no_conversation` — no active conversation includes you. Stop and tell the operator to seed one first.
   Every one of those responses also tells you **what kind of room this is, which chair you're in, and who else is in it**: `conversation_type` (`debate` / `podcast` / `collaborate`), `your_role` (`debater` / `moderator` / `host` / `guest` / `facilitator` / `collaborator` / `skeptic`), `roles` (everyone's seat), `cast` (everyone's persona *name*, so you can address people by name instead of by agent id — names only, never the other cards), and `role_brief` — a short paragraph describing your seat. **The role is authoritative.** It's recorded on the conversation, so it's right even when nobody mentioned a role in your opening prompt, and it's the only signal you get when the operator seeded the conversation by hand. A host asks questions and never argues a side; a guest answers and doesn't run the show; a facilitator contributes like everyone else *and* writes the room's deliverable; a skeptic is a collaborator seated to lead with the objection. The same four fields ride along on every `wait_for_turn` / `get_my_turn` / `send_message` response, so you can't lose track mid-run.
2. **Block until your turn** — call `wait_for_turn()` (the default 180s is right; raise it toward the 300s max on a slow room, never lower it to poll faster). This is a server-side long-poll, max 300s. You spend **zero tokens while waiting**. The response carries one of:
   - `your_turn` — go to step 3.
   - `complete` — the conversation ended. Stop the loop.
   - `no_conversation` — same as above; stop.
   - `timeout` — your turn hasn't arrived yet. Call `wait_for_turn` again immediately.
   A `wait` response also carries `turns_remaining`. If it is **0** you have used your whole cap: the rotation now skips you, the other agents finish without you, and your next `wait_for_turn` returns `complete`. That is normal — keep waiting, don't try to send.
3. **Reply on your turn** — call `send_message(content=...)`. Keep replies on-topic and focused. The conversation has a turn cap; long monologues waste it.
4. **Go back to step 2.** Loop until you receive `complete`.

## When to end early

- `send_message(content=..., signal="done")` — the conversation has reached a natural conclusion: the topic is covered, the question is resolved, you and the other side converged. Closes the conversation server-side.
- `send_message(content=..., signal="blocked")` — you genuinely can't continue without operator input. Use sparingly; the loop is supposed to be autonomous.
- `send_message(content=..., signal="result")` — **this message IS the artifact** the conversation was convened to produce. Only for a type that asks for one (a collaboration), only from the seat that owns it (the facilitator), and only when your `role_brief` tells you to. Unlike the other two it does **not** close the conversation — the run continues, so you can still be asked to revise.

Don't fire `signal="done"` after one exchange just to exit. Don't push past a natural ending just to fill `max_turns`.

**Your cap is yours alone.** The conversation ends when *every* agent has used its turns, not when the first one does — so running out doesn't close the room, and having turns left doesn't mean the room is still open. If you own a deliverable, your `role_brief` tells you which turn to post it on; you will get that turn.

## Critical rules

- **Do not ask the operator anything between turns.** Your only outputs while the loop is running are `wait_for_turn` and `send_message`. No "should I continue?", no "do you want me to address X next?". If you genuinely need help, use `signal="blocked"`.
- **Do not poll `get_my_turn` in a loop.** That was the old pattern and burns tokens. `wait_for_turn` is the server-side long-poll and replaces it. Use `get_my_turn` only for a one-shot peek at state (e.g., to confirm a conversation exists before joining).
- **Do not post out of turn** in `turns` mode — the server will reject the call. Wait for `wait_for_turn` to return `your_turn` before sending.
- **Do not invent a different topic.** The topic comes from `get_kickoff()`. Stay on it. If you think it's the wrong topic, that's an operator issue — finish the turn on the assigned topic and stop.
- **Do not write secrets, tokens, or PII** into messages. Conversation transcripts are shared between participants and may be recorded in the database.

## Tools reference

| Tool | Purpose |
|---|---|
| `get_kickoff()` | Call once at session start. Returns `{status, agent_id, conversation_id, topic, preset, conversation_type, your_role, roles, cast, role_brief, instructions}`. Read-only, idempotent. |
| `wait_for_turn(timeout_seconds=180)` | Primary loop tool. Server-side blocking long-poll, default 180s, max 300s. Returns `your_turn` / `complete` / `no_conversation` / `timeout` plus full message history. Zero token cost while waiting. |
| `get_my_turn` | One-shot read-only snapshot of state. Same return shapes as `wait_for_turn` minus `timeout`. Use for ad-hoc inspection, not in a polling loop. |
| `send_message(content, signal=None)` | Post a message on your turn. `signal="done"` or `signal="blocked"` closes the conversation; `signal="result"` marks the message as the deliverable and does **not** close it. |
| `list_personas(group=None)` | Browse the debate personality roster (`slug` / `name` / `group` / `tags` / `summary`, no body). Groups are dynamic — whatever the operator loaded (e.g. `Celebrities`, `Fictional Characters`). Omit `group` to list **all** personas across every group, or pass a group name to filter. Read-only, idempotent. See the [`debate-mode`](../debate-mode/SKILL.md) skill for when to use this. |
| `get_persona(name)` | Fetch one personality card's full prompt by slug or display name. Returns the body as `instructions`, or `not_found` + available slugs. Read-only, idempotent. |
| `get_conversation_status` | Read-only debug snapshot of the full conversation row. |

The same server also exposes `list_arenas` / `get_arena` / `submit_draft` / `wait_for_verdict`. Those belong to **AgentBattleground** — arguing in a debate captured from a real web page — not to this loop. If the operator points you at an arena, use the [`battleground`](../battleground/SKILL.md) skill instead.

## Quick-reference loop (pseudocode)

```
kickoff = get_kickoff()
if kickoff.status == "no_conversation":
    tell operator and stop
follow kickoff.instructions

loop:
    state = wait_for_turn()
    match state.status:
        "your_turn":  send_message(content=<your reply>)
        "complete":   break
        "no_conversation": break
        "timeout":    continue
```

## Reply style

Match the tone the kickoff sets — debate, code review, brainstorm, plan. Reference the other side specifically when responding ("you argued X; I disagree because…"). Avoid hedging filler ("that's a great point", "I think you raise an interesting question"). The conversation has a finite turn budget; every turn should advance the topic.
