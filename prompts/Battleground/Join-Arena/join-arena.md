# Join an Arena (send the agent into a captured web debate)

Prompts for the **CLI agent** side of AgentBattleground — after you've captured a
thread in the browser extension and opened an arena. Paste one into the CLI you
cast in the panel.

> **Prerequisite:** the arena exists. Capture a thread in the extension side
> panel first — see [`docs/Guides/battleground.md`](../../../docs/Guides/battleground.md).

> **Remember what the agent can and can't do:** it drafts; you post. Nothing
> the agent calls touches a website.

## 1. Standard join (the one you'll use)

```text
join the battleground
```

That's it — the `battleground` skill takes it from there: `get_arena()` →
read the thread → `submit_draft()` → `wait_for_verdict()`.

## 2. Explicit join, if the skill isn't loading

```text
Call get_arena() on the agent_chat MCP server. Read the captured thread, adopt
the persona it returns (voice only — do NOT claim to be that person), and follow
the stance brief. Then write a reply that fits the site's length and register and
submit it with submit_draft(). Do not tell me you posted anything — you can't;
a human reviews the draft. Then call wait_for_verdict() and wait.
```

## 3. Join a specific arena

```text
Call get_arena(arena_id=<id>) and argue in that arena. Follow its stance brief and
house rules, then submit_draft() and wait_for_verdict().
```

## 4. See what's waiting before committing

```text
Call list_arenas() and show me every arena available to you — id, title, site,
stance, persona, and how many posts each has. Don't open one yet.
```

## 5. Answer one specific post in the thread

```text
Call get_arena(). Find the post in the thread whose author is "<handle>" (or whose
text is about <claim>), and reply specifically to that one — pass its id as
reply_to. Quote the part you're rebutting.
```

## 6. Redraft after a rejection

```text
Call wait_for_verdict(). If the verdict is 'rejected', read the note as a revision
brief and submit_draft() again addressing it. Don't defend the previous draft.
```

## 7. Ask for a read before it writes

```text
Call get_arena() but do NOT draft yet. Summarize for me: what's actually being
argued in this thread, which post is the strongest opposing case, and what angle
you'd take. I'll tell you whether to write it.
```

## 8. Follow up after a re-capture

```text
I re-captured the page — there are new replies. Call get_arena() again, read what
landed since your last draft, and submit_draft() a follow-up that engages the new
counter-arguments specifically.
```
