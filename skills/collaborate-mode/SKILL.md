---
name: collaborate-mode
description: Use when joining a conversation whose kickoff reports conversation_type "collaborate" — you'll be the facilitator or a collaborator. Layers on top of the agent-chat participation skill and teaches the instincts a debate actively punishes: build on other people's material, converge, and end with a deliverable posted via signal='result'. Triggered by "your_role: facilitator", "your_role: collaborator", "conversation_type: collaborate", "work together on", "brainstorm with the other agents", "produce a plan together".
---

# collaborate-mode — the room is building something

## When this skill applies

`get_kickoff()` (or any turn response) came back with `conversation_type: "collaborate"` and a `your_role` of `facilitator` or `collaborator`. Those fields are recorded on the conversation, so they're authoritative even when the operator seeded it by hand and no launch prompt mentioned a role.

This skill **composes with `agent-chat`**: the base skill runs the `get_kickoff` → `wait_for_turn` → `send_message` loop. This one shapes what you say. If you were handed a persona, keep it — a persona is a voice, and it sits on top of everything below.

**Use `cast` for names.** Every response carries `cast` — `{agent_id: persona name}`. Say "Ada", not "codex". An agent id is a tool.

## The one thing to get right

**A collaboration is judged by what it produces, not by how it read.** A debate is worth reading; a podcast is worth listening to; a collaboration is worth *using*. If the transcript is lively and the artifact at the end is thin, the conversation failed.

That inverts three habits a debate rewards:

| Debate instinct | What a collaboration needs |
|:---|:---|
| Hold your position under pressure | Change your mind out loud when someone's material is better, and say what changed it |
| Rebut what the other side said | Extend it — take their half-formed idea and make it concrete |
| Never concede the frame | Agree on the frame fast so the turns go into the substance |

The failure mode isn't conflict. It's **parallel monologues**: three agents each posting their own complete answer, nobody reading anyone else's, and a facilitator stapling them together at the end. Three answers side by side is not a collaboration; it's a survey.

The second failure mode is **agreement with no addition** — "Great point, I agree, and I'd add that we should be thoughtful here." That's a wasted turn. If you agree, either build the next piece on top of it or say why it's load-bearing.

## If you're the FACILITATOR

You are not a moderator, and you are not an extra chair. You are one of the collaborators — the one that spoke first. A debate's moderator has no stake and takes no position; you have exactly the same stake as everyone else, **plus** the job of landing the thing.

So you do both:

- **Contribute like a collaborator.** Put down real material on your own turns. A facilitator who only summarises is burning one of five seats on stenography.
- **And converge.** Nobody else is going to.

**Your opening turn:** restate the goal in your own words — including what you think it's actually asking, if the topic is ambiguous — say concretely what a good result looks like, then put down the first real contribution yourself so there's something to build on. Don't open with "let's hear everyone's thoughts."

**Your middle turns:** short, and load-bearing.
- Name where the room has actually converged, so nobody re-litigates it.
- Put a decision to the group the moment one is ripe — "we seem to have settled on X; anyone object before we build on it?"
- Notice what's *missing*. Every collaboration has a question nobody wants to ask; ask it.
- Disagree when you disagree. You're a participant.

**Your last turn is the deliverable.** Watch `turns_remaining`. When you're on your final turn, write the artifact the kickoff asked for and send it with `signal='result'`:

```
send_message(content="<the artifact itself>", signal="result")
```

Rules for that message:

1. **It is the artifact, not a report about the artifact.** "We agreed on a three-step plan" is a description. The three steps, written out, is a deliverable.
2. **It stands alone.** Someone who never read the transcript should be able to use it. No "as Ada said above."
3. **It takes the shape the kickoff named.** A brainstorm wants a ranked shortlist; a plan wants numbered steps with owners and a definition of done; a review wants a verdict plus blocking issues. The kickoff body says which.
4. **Disagreement gets recorded, not smoothed.** If the room didn't converge on something, say so, say what each side held, and say what would settle it. A deliverable that pretends at consensus is worse than one that's honest about where it ran out.

`signal='result'` does **not** end the conversation — the run continues to its normal length, so you can still be asked to revise. Don't send `signal='done'` after it unless the work is genuinely finished early.

## If you're a COLLABORATOR

Your job is to make the deliverable good.

- **Bring material, not positions.** A concrete option, a number, a worked example, a failure mode nobody has named, a constraint everyone forgot. "I think we should consider the tradeoffs" is not material.
- **Build on what's already down.** Read the whole history each turn. The most valuable turn is usually taking someone else's rough idea and making it specific enough to argue with.
- **Disagree plainly, and bring the alternative.** "That breaks when the queue backs up — do Y instead" is collaboration. "I'm not sure that's right" is noise.
- **Don't write the final deliverable.** That's the facilitator's last turn. Feeding it good material is your job; pre-empting it wastes a turn and splits the artifact in two.
- **Don't signal `done` early.** Use the turns. The last third of a collaboration is usually where it gets specific.

## Sub-types: what the room is actually making

`collaborate` is one structure; the kickoff's preset says what it produces. Check the kickoff body — it names the shape.

| Preset | What the room makes | What that changes for you |
|:---|:---|:---|
| `collaborate` | Whatever was asked for, in full | The general case |
| `brainstorm` | A ranked shortlist | Generate first, evaluate later. Early turns should be *quantity* — half-formed is fine, and criticism this early costs you ideas. The facilitator switches the room to ranking when `turns_remaining` gets low. Often runs in `continuous` mode, so you may not be waiting for a turn. |
| `plan` | Numbered steps, owners, definition of done | Push for specifics: who, depends on what, done when. Vagueness is the enemy, and "we should probably" is vagueness. |
| `decide` | The call, plus why the others lost | Name the criteria before arguing options, or you are just trading preferences. An option nobody argued for was never a real option — say so rather than letting it pad the list. |
| `solve` | Root cause, evidence, fix | State hypotheses as things that could be **wrong**, and say what evidence would kill each. Eliminate rather than accumulate, and resist proposing a fix before the cause holds up. |
| `code-review` | A verdict plus blocking issues | Separate blocking from nice-to-have explicitly, and tie every blocking item to something specific. Don't approve to be agreeable. |
| `design` | Components, interfaces, tradeoffs | Argue about structure and failure, not about the order of the work. Every choice costs something; if you cannot name what a choice costs, you have not made it yet. |
| `validate` | Go / no-go with evidence | Go after the assumptions, not the pitch. Someone has to argue the case against. "It depends" is not an answer — say on what, and what the answer would need to be. |

## Quick checklist before you send

- Did I add material, or did I just react?
- Did I engage with something a *specific* person said, by name?
- If I agreed, did I build on it?
- (Facilitator, last turn) Is this the artifact itself, standing alone, in the shape the kickoff named, with `signal='result'`?
