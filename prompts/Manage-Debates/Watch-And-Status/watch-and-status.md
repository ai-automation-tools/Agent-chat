# Watch & Status (check on running / past debates)

Prompts for seeing what's running, watching a debate live, and pulling up details.
Paste a block into Claude Code; it runs `src/inspect_conversations.py` (DB defaults
to `<repo>/db/chat.db`) or points you at the web UI.

> **Fastest live view is the browser:**
> - Local: `http://127.0.0.1:8765/conversations/<id>`
> - Hosted mirror: `https://agent-chat.ai-automation-tools.dev/conversations/<id>`

## 1. List all conversations

```text
List every agent_chat conversation with its id, status, topic, and turn count by
running: .\.venv\Scripts\python.exe src\inspect_conversations.py list
```

## 2. What's running right now?

```text
Show me which agent_chat conversations are still active (status = active). Run
inspect_conversations.py list and filter to the ones that aren't complete yet.
```

## 3. Show one debate's full transcript

```text
Show the full transcript and metadata for conversation #<id> by running:
.\.venv\Scripts\python.exe src\inspect_conversations.py show <id>
```

## 4. Tail a live debate in the terminal

```text
Tail conversation #<id> live so I can watch new messages arrive. Run:
.\.venv\Scripts\python.exe src\inspect_conversations.py tail <id>
(Stop it with Ctrl-C when I say so.)
```

## 5. Give me the live web links

```text
Give me the local and hosted web-UI links to watch conversation #<id> live, and
confirm the local web UI (port 8765) is running — if it isn't, tell me how to
start it.
```
