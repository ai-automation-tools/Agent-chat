# Stop & Cleanup (end a debate early, tidy up)

Prompts for force-stopping a running debate and clearing out old conversations.
Stopping flips the row to `complete` so the agents end their `wait_for_turn` loop.

> Stop also available as the **Stop** button in the web UI. Delete is a web-UI /
> API action (`POST /api/conversations/{cid}/delete`) — there's no CLI delete, so
> deletion prompts go through the web UI.

## 1. Stop a specific debate now

```text
Force-stop conversation #<id> right now by running:
.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>
Then confirm its status is 'complete'.
```

## 2. Stop the debate that's dragging on

```text
List the active conversations, identify the one on topic "<topic>", and force-stop
it with inspect_conversations.py stop <id>. Show me the final status.
```

## 3. Stop everything that's still running

```text
Find every conversation still in 'active' status and force-stop each one with
inspect_conversations.py stop <id>. List what you stopped.
```

## 4. Delete a conversation (via the web UI)

```text
I want to delete conversation #<id>. Walk me through doing it in the local web UI
(the Delete action on the conversation page / POST /api/conversations/<id>/delete)
— don't try to delete it from the CLI.
```

## 5. Clean up stale launch files

```text
Show me the leftover per-agent prompt files under db/launch/ from past debate
runs, and delete the ones older than today so the folder stays tidy.
```
