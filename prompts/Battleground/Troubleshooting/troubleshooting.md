# Troubleshooting (AgentBattleground)

Paste-ready diagnostic prompts for when the extension, the bridge, or the agent
isn't behaving.

## 1. Is the bridge even up?

```text
Check whether the AgentBattleground bridge is reachable:
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/api/battleground/roster
200 = good. 404 = the web UI is running OLD code and needs a restart.
Anything else = the web UI isn't running; tell me how to start it.
```

## 2. The web UI is running old code

```text
The battleground routes are 404ing. Find the process listening on port 8765, stop
it, and restart the web UI from the venv via scripts/startup-app.ps1. Then confirm
/api/battleground/roster returns 200.
```

## 3. Persona dropdown is empty

```text
The extension's persona picker is empty. Check what the roster endpoint returns:
curl -s http://127.0.0.1:8765/api/battleground/roster
If personas is [], list what's in the DB — remember AI-Models cards are excluded
from casting on purpose, so a roster of only those shows as empty.
```

## 4. Agent claims it posted something

```text
The agent said it posted a reply to the website. That's impossible — it can only
draft. Check whether the battleground skill is actually loaded in that CLI, and
show me the arena's drafts and their real statuses:
curl -s http://127.0.0.1:8765/api/battleground/arenas/<id>
```

## 5. Agent can't find the arena

```text
The agent says there's no arena for it. Show me every arena and who each is
assigned to: curl -s http://127.0.0.1:8765/api/battleground/arenas
Tell me whether arena #<id> is assigned to a different CLI or is closed.
```

## 6. Capture found nothing

```text
The extension captured 0 posts on <url>. Which adapter should have handled that
domain? Read extension/src/capture.js and tell me what selectors it looks for on
that site, and whether the generic fallback should have caught it.
```

If the comments on that page live in a third-party frame, the panel offers an
**Include &lt;host&gt;** button under the capture summary — grant that origin and
capture again before assuming the adapter is broken.

## 6b. Adding an adapter for a new site

```text
Add a capture adapter for <site> to extension/src/capture.js. Follow the
existing ones: detect the site, find posts, and give each a STABLE id (the
site's own comment id) so re-capture merges instead of duplicating. Then add
the label to KNOWN_SITES in src/web/api/battleground.py — both edits are
required or the bridge silently downgrades the arena to 'generic'. Verify
against a live page before you tell me it works.
```

## 7. Re-capture is duplicating posts

```text
Re-capturing arena #<id> keeps adding duplicate posts instead of merging. That
means the adapter isn't producing stable post ids. Show me the thread's post ids
from the API and tell me which adapter produced them and why they're unstable.
```

## 8. Draft is stuck pending

```text
Draft #<id> has been pending for a while. Show me its full row and its arena's
status. Confirm whether it's waiting on my verdict or whether something failed:
curl -s http://127.0.0.1:8765/api/battleground/arenas/<arena-id>
```

## 9. Verify the whole loop still works

```text
Run the AgentBattleground test suite and report the result:
.\.venv\Scripts\python.exe tests\test_battleground.py
```

## 10. Did any of this leak to the hosted mirror?

```text
Confirm that AgentBattleground data is NOT syncing to Fly. Check that
battleground_arenas / battleground_drafts don't appear in the sidecar's column
lists in src/web/db.py and scripts/db_sync.py, and that /api/since returns no
arena keys. Report either way.
```
