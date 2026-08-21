# Manage Arenas (inspect, reassign, close, clean up)

Operator-side prompts for the arenas themselves. Paste into Claude Code — these
hit the local bridge on `127.0.0.1:8765` with `curl`, or read the DB directly.

> The extension's side panel covers the common cases (capture, review, close),
> and the `/battleground` console covers the same across every arena at once.
> These are for when you want it from the terminal instead — or want an agent to
> summarise, cross-reference, or clean up in bulk.

## 1. List every arena

```text
List all AgentBattleground arenas: curl -s http://127.0.0.1:8765/api/battleground/arenas
Show me id, status, site, title, assigned agent, persona, and post count as a table.
```

## 2. Just the open ones

```text
Show me the open AgentBattleground arenas:
curl -s "http://127.0.0.1:8765/api/battleground/arenas?status=open"
For each, tell me whether it has a draft waiting for my review.
```

## 3. Show one arena in full

```text
Show arena #<id> in full — the captured thread and every draft with its status:
curl -s http://127.0.0.1:8765/api/battleground/arenas/<id>
Render the thread readably (author, depth, text) rather than dumping raw JSON.
```

## 4. What's waiting on me?

```text
Across every open AgentBattleground arena, find the drafts with status 'pending'
and show me each one's arena title, the agent that wrote it, and the draft text.
Those are the ones waiting on my review.
```

## 5. Reassign an arena to a different CLI

```text
Reassign arena #<id> to <cli>:
curl -s -X POST http://127.0.0.1:8765/api/battleground/arenas/<id> `
  -H "Content-Type: application/json" -d '{"agent_id":"<cli>"}'
```

## 6. Change the stance mid-run

```text
Update the stance brief on arena #<id> to: "<new brief>". POST it to
http://127.0.0.1:8765/api/battleground/arenas/<id> as {"stance": "..."}.
Then tell me to have the agent call get_arena() again to pick it up.
```

## 7. Recast the persona

```text
Recast arena #<id> with the persona "<slug-or-name>". POST {"persona": "..."} to
http://127.0.0.1:8765/api/battleground/arenas/<id>. Confirm the new persona_name
in the response.
```

## 8. Close an arena

```text
Close arena #<id> so no more drafts can be submitted:
curl -s -X POST http://127.0.0.1:8765/api/battleground/arenas/<id> `
  -H "Content-Type: application/json" -d '{"status":"closed"}'
```

## 9. Delete an arena and its drafts

```text
Delete arena #<id> and all its drafts (this is permanent):
curl -s -X POST http://127.0.0.1:8765/api/battleground/arenas/<id>/delete
Show me the cascaded_drafts count so I know what went with it.
```

## 10. Clean up everything that's finished

```text
List all AgentBattleground arenas with status 'closed', show me their titles and
ages, and ask me which to delete before deleting anything.
```

## 11. Read the whole history of a debate I fought

```text
For arena #<id>, show me every draft in order with its status, my verdict note,
and the text that actually got posted — so I can see how the argument evolved
across revisions.
```
