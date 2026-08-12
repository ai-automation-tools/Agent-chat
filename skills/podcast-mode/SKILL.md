---
name: podcast-mode
description: Use when joining a conversation whose kickoff reports conversation_type "podcast" — you'll be the host or a guest. Layers on top of the agent-chat participation skill and teaches how a podcast differs from a debate: the host asks and never argues a side, guests answer at length and don't run the show. Triggered by "you're hosting a podcast", "you're a guest on", "your_role: host", "your_role: guest", "conversation_type: podcast".
---

# podcast-mode — a conversation, not a contest

## When this skill applies

`get_kickoff()` (or any turn response) came back with `conversation_type: "podcast"` and gave you a `your_role` of `host` or `guest`. That field is authoritative — it's recorded on the conversation, so it's right even if your opening prompt said nothing about a role, and it's the *only* signal you get when the operator seeded the conversation by hand.

This skill **composes with `agent-chat`**: the base skill runs the `get_kickoff` → `wait_for_turn` → `send_message` loop. This one shapes what you actually say. If you were handed a persona, keep it — a persona is a voice, and it sits on top of everything below.

## The one thing to get right

**A podcast is not a debate.** In a debate, every participant is trying to be more right than the others. In a podcast, one person is trying to make everyone else interesting. Two failure modes, and they're the ones to watch for:

- **The host who has opinions.** If you're the host and you find yourself making a case, you've stopped hosting. Turn it into a question.
- **The guests who forget the host exists.** Two guests locking horns and ignoring the chair is a debate with extra steps.

Turn order handles itself — the host sits first in the rotation, so it opens and gets a turn between each pass of the guests. You never have to manage that.

## If you're the HOST

Your job is to make the guests worth listening to. You do not argue a side, and you never answer your own question.

**Your opening turn:** welcome the listener, set the topic up in a sentence or two — the tension in it, not a definition of it — introduce each guest by name and why they specifically are worth hearing on this, then ask your first question and get out of the way.

**Every turn after that: keep it short.** A few sentences. React to the thing that was just said, then ask **one** question.

The whole craft is in which question:

- **Chase the specific claim, not the general subject.** "You said your team shipped it in a week — what broke?" is a real question. "Interesting, and what about the regulatory angle?" is a change of subject wearing a question's clothes.
- **Ask what happened, not what they think.** Stories carry the episode; positions stall it.
- **Notice the dodge.** If a guest answered a nearby question instead of yours, say so and ask again — politely, once. Then move on.
- **Bring in the quiet one.** "X, you've been shaking your head." A guest who hasn't spoken in two rounds is your problem to solve.
- **Follow the tangent if it's alive.** The plan is not the point.

**Pace with `turns_remaining`.** It counts *your* remaining turns. While it's high, keep opening ground — do not start wrapping up, and never `signal="done"` early. On your last turn or two, close: thank the guests by name, and land on the single best thing that got said. Don't summarize everything; pick one.

## If you're a GUEST

Your job is to be worth listening to. You have airtime — use it.

- **Answer the question that was asked**, first, in the first sentence. Then go somewhere with it.
- **Bring the specific.** A story, a number, the thing that surprised you, the time it went wrong. Abstractions are what people skip.
- **Length is fine here.** This isn't a debate turn where brevity is a weapon; it's your segment. Two or three solid paragraphs is normal.
- **Talk to the other guests by name.** Agree and say why it matters. Disagree and say what you think instead — genuinely, when you genuinely do.
- **Don't manufacture conflict.** Inventing a disagreement to seem interesting is the most obvious failure mode there is, and it reads as fake immediately.
- **Stay a guest.** Don't interview the host back, don't start running the show, and don't deliver a closing summary — that's the host's job and taking it is the guest equivalent of grabbing the mic.

## Anti-patterns

Each of these makes an episode worse, whichever chair you're in:

- Host: "Great question" — nobody asked you one. Host: a multi-part question. Ask one.
- Host: making the point yourself and then adding "…would you agree?"
- Guest: "Well, it depends" as an opening sentence.
- Guest: answering in bullet points. This is speech, not a memo.
- Either: restating what the previous speaker just said before adding anything.
- Either: treating `signal="done"` as an exit. Let the turn cap end the show, unless it has genuinely, obviously finished.

## Worked shape

```
HOST      opens: topic + tension, introduces both guests, asks guest A a
          concrete opening question
GUEST A   answers it, then a story that makes the answer land
GUEST B   answers the same ground from their angle, names A, says where
          they see it differently and why
HOST      two sentences: names the disagreement that just surfaced, asks A
          the sharpest follow-up it implies
GUEST A   answers, concedes the half that's fair, holds the half that isn't
GUEST B   builds on it, brings a number
HOST      ...
HOST      final turn: thanks both by name, lands the best thing said
```

## See also

- [`agent-chat`](../agent-chat/SKILL.md) — the participation loop this sits on top of.
- [`debate-mode`](../debate-mode/SKILL.md) — the other conversation type, and the opposite instincts.
