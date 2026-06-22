---
name: debate-mode
description: Use when joining a conversation framed as a debate, being asked to argue a position or defend a stance, being assigned a side, or when the kickoff `preset` is "debate". Layers on top of the agent-chat participation skill — teaches how to argue effectively. Triggered by phrases like "argue for X", "defend the position", "debate this topic", "take the side that…", "kickoff preset: debate".
---

# debate-mode — argue a position, don't survey the question

## When this skill applies

You've been assigned a position to argue in a multi-turn debate — usually inside an `agent_chat` conversation seeded with `--preset debate`. The other participant is also a CLI agent arguing the opposing or adjacent position. The operator is not standing by; the two of you have a finite turn budget to reach a substantive conclusion together.

This skill **composes with `agent-chat`**: the base skill handles the `get_kickoff` → `wait_for_turn` → `send_message` loop. This one shapes the **content** of each `send_message` call.

## Optional: adopt a persona

The repo ships a roster of debate personality cards under `agents/Debate-Agents/` — exaggerated characters (Crypto Chad, Flat-Earth Fred, Pastor Cole, …) plus a few moderator/host personalities. If the kickoff assigns you a persona by name, or you just want a sharper voice than a neutral one, you can pick one up yourself — no operator step needed:

1. **`list_personas()`** — browse the roster. Each entry has a `slug`, `name`, `group` (`Unique-Personas` = debaters, `Debate-Hosts` = moderators), `tags`, and a one-line `summary`. Pass `group="Debate-Hosts"` if you're moderating.
2. **`get_persona(name)`** — pull the full card by `slug` or display name (e.g. `get_persona("crypto-chad")` or `get_persona("Crypto Chad")`). The returned `instructions` field is the character's full prompt.
3. **Stay in character** for the rest of the conversation: adopt the persona's voice and worldview *on top of* the three core moves below. A persona is a delivery style — it does **not** excuse hedging, strawmanning, or refusing to concede. Crypto Chad still has to cite your actual argument and stake a falsifiable bet; he just does it yelling "to the moon."

When the operator pre-assigned a persona at launch (e.g. via `scripts/debate.ps1`), you'll already have it — only reach for these tools when you need to discover or adopt one mid-setup.

## The three core moves

### 1. Argue a position — don't survey the question

Open and stay with a clear, falsifiable claim. Not "there are good arguments on both sides." Not "it depends on how you define X." Pick the side the kickoff assigned (or the strongest version of one you genuinely hold) and commit.

Concrete predictions beat abstractions. "Median total comp for software engineers in SF/NYC is flat-to-down in real terms by 2029" beats "compensation may face pressure." A number you can be wrong about is worth more than a paragraph of hedged nuance.

### 2. Cite the other side specifically

Quote or paraphrase the *actual* argument your opponent made. Engage with the strongest version of it, not a strawman.

Good engagement looks like:
> "Your strongest point is the one I was glossing over: 'judgment usually came from shipping boring tickets under supervision.' That's a real Chesterton's Fence and I'll concede it partway. Where I'd push back: judgment doesn't *only* come from writing the boring ticket…"

Bad engagement looks like:
> "You raise an interesting point about juniors. I think there are several perspectives to consider…"

If you didn't read what they wrote carefully enough to quote a specific phrase, read it again before replying.

### 3. Concede where you should, hold ground where you can

Strong debaters concede partial points; weak debaters retreat to "well, we're both kind of right." The pattern:

- **Full concession** when the opponent's point genuinely defeats yours: "Concession on accountability: you're right and I underweighted it."
- **Partial concession + counter** when they're directionally right but you can sharpen or qualify: "I buy the pressure on mid-career generalists, but I think you understate how brutal the junior on-ramp gets."
- **Direct counter** when you actually disagree: "Where I'd invert your frame…"

Conceding is not weakness — it earns credibility for the points you hold.

## Phrases that signal good debate

Steal these openings. They commit to a stance and engage specifically.

- "Your strongest point is X. I'll concede it partway. Where I'd push back: …"
- "I buy A, but I think you understate B."
- "Where I want to invert your frame: …"
- "Concrete bet I'll stake on the table: …"
- "Concession on X — you're right. But notice what that implies: …"
- "A piece neither of us has named: …"
- "Your reframe of X is better than mine. I'll adopt it."

## Anti-patterns — these waste turns

| Don't write | Why it's bad |
|---|---|
| "That's a great point." | Empty filler. Engage with the *content*. |
| "I think you raise an interesting question." | Same. Restate the question or quote it, then answer. |
| "There are valid arguments on both sides." | You were assigned a side. Argue it. |
| "It really depends on how we define X." | If a definition genuinely matters, pick one and defend it. Otherwise this is a dodge. |
| "I largely agree with everything you said." | Then you're not debating. Find a real disagreement, sharpen a point, or add an angle they missed. |
| Restating your own previous position with more words. | Each turn must move the argument forward — concede, counter, or open a new front. |

## Make falsifiable predictions

A debate without stakes is a discussion. Where the topic admits it, commit to a prediction someone could check:

- "By 2029, >40% of US software developers are 1099/contract/agency."
- "At least 3 of the top 10 US bootcamps are dead by 2028."
- "Cybersecurity headcount in the US grows >50% by 2030 while general SWE headcount is flat."

If your opponent ups the stakes with a concrete bet, meet them with one of yours.

## When to signal `done`

A debate reaches a natural end when:

1. Both sides have stated their positions, exchanged their best counters, and converged on a shared picture (even one that retains real disagreements).
2. One side concedes a load-bearing point that resolves the original question.
3. The argument has cycled — both sides are restating without advancing.

In case 1 or 2, close with `send_message(content=<final synthesis>, signal="done")`. The final message should compress the agreement: what you both ended up believing, the disagreements that survived, and (if it fits) a single sentence of practical implication.

Case 3 — the cycle — is a failure mode. If you notice it, try one of: introduce an angle neither of you has named, ask which falsifiable prediction would change the opponent's mind, or concede partway to break the symmetry. If that doesn't move things, signal `done` with a brief note that the disagreement is genuine and unresolved.

## Reference: what a good debate looks like

[`docs/Agent-Conversations/future-of-tech-jobs/Conversation.md`](../../docs/Agent-Conversations/future-of-tech-jobs/Conversation.md) is the canonical example. Eight turns, both sides held positions while conceding sharp points, ended on a compressed thesis ("AI doesn't eliminate tech jobs; it unbundles them") that neither would have written alone. Read it before your first debate-mode session if you have the budget.

## Composes with `agent-chat`

This skill assumes the [`agent-chat`](../agent-chat/SKILL.md) skill is also loaded. Concretely:

| Concern | Where it lives |
|---|---|
| When to call `get_kickoff`, `wait_for_turn`, `send_message` | `agent-chat` |
| When to use `signal="done"` vs `signal="blocked"` | `agent-chat` |
| "Don't ask the operator between turns" | `agent-chat` |
| **What to put inside `content=…`** | **`debate-mode`** (this skill) |

If only `agent-chat` is loaded, you'll participate correctly but your replies may be too hedged for a debate. If only `debate-mode` is loaded, you'll argue well but won't know the loop mechanics. Install both.
