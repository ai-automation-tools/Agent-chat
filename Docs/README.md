# agent_chat — Local MCP server for AI-to-AI conversations

A SQLite-backed message bus that lets two CLI agents (Claude Code, Codex CLI,
etc.) hold structured conversations with each other. Fully local — no cloud,
no daemon, no exposed ports. The whole thing is one Python file plus a SQLite
database.

## How it works

Both agents register the **same** MCP server, but each launches it with a
different `--agent-id`. They share a single SQLite file as the message bus.

```
   Claude Code                          Codex CLI
       │                                    │
       │ (stdio)                    (stdio) │
       ▼                                    ▼
 [agent_chat_mcp.py                   [agent_chat_mcp.py
  --agent-id claude-code]              --agent-id codex]
       │                                    │
       └────────────► chat.db ◄─────────────┘
                  (shared SQLite WAL)
```

Conversations are seeded out-of-band by `start_conversation.py`. Each agent
calls `get_my_turn()` to discover an active conversation, see history, and
find out whether it's their turn. They reply via `send_message()`. The server
enforces turn order, per-agent message caps, and explicit `done`/`blocked`
signals.

## Files

| File | What it does |
|---|---|
| `agent_chat_mcp.py` | The MCP server. Run as a subprocess by each agent's CLI. |
| `start_conversation.py` | Seed a new conversation in the DB. Run once before prompting agents. |
| `inspect_conversations.py` | List, show, tail, or stop conversations. Run in a third terminal to watch live. |

## One-time setup (Windows / WSL)

1. Pick a home for the project, e.g. `D:\AI_Agents\Specialized_Agents\agent_chat\`. Drop the three `.py` files there.
2. Install dependencies into whatever Python you'll point your CLIs at:

   ```powershell
   pip install mcp pydantic
   ```

3. Decide on a DB path, e.g. `D:\AI_Agents\Specialized_Agents\agent_chat\chat.db`. The file is created automatically on first run.

## Register the server with each CLI

The exact registration commands change occasionally — check current docs for
your CLI version — but the shape is:

**Claude Code** (`claude mcp add` or `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "python",
      "args": [
        "D:/AI_Agents/Specialized_Agents/agent_chat/agent_chat_mcp.py",
        "--agent-id", "claude-code",
        "--db-path", "D:/AI_Agents/Specialized_Agents/agent_chat/chat.db"
      ]
    }
  }
}
```

**Codex CLI** (config file or `codex mcp add` equivalent):

```toml
[mcp_servers.agent_chat]
command = "python"
args = [
  "D:/AI_Agents/Specialized_Agents/agent_chat/agent_chat_mcp.py",
  "--agent-id", "codex",
  "--db-path", "D:/AI_Agents/Specialized_Agents/agent_chat/chat.db"
]
```

The `--agent-id` is the **only** thing that differs between the two registrations. The `--db-path` must be identical.

> Windows note: forward slashes work fine for Python paths. If you prefer backslashes you'll need to double them in JSON (`"D:\\AI_Agents\\..."`).

## Running a conversation

**Terminal 1** — seed the conversation:

```powershell
python start_conversation.py `
  --db-path D:/AI_Agents/Specialized_Agents/agent_chat/chat.db `
  --topic "Compare your approaches to refactoring a legacy Python module" `
  --participants claude-code,codex `
  --first claude-code `
  --mode turns `
  --max-turns 10
```

**Terminal 2** — open Claude Code, then prompt:

> You're connected to the `agent_chat` MCP server as agent **claude-code**. Call `get_my_turn` to begin participating. When it's your turn, think about the topic, then call `send_message` with your reply. Keep going until the server tells you the conversation is complete.

**Terminal 3** — open Codex CLI, then prompt the same way but with **codex** as the agent id.

**Terminal 4 (optional)** — watch the conversation live:

```powershell
python inspect_conversations.py `
  --db-path D:/AI_Agents/Specialized_Agents/agent_chat/chat.db `
  tail 1
```

## Tools the server exposes

| Tool | Use it for |
|---|---|
| `get_my_turn` | Primary tool. Returns `your_turn`, `wait`, `complete`, or `no_conversation`, plus full history. Idempotent. |
| `send_message(content, signal=None)` | Post a message. `signal='done'` ends the conversation early; `signal='blocked'` flags that the agent needs human help. |
| `get_conversation_status` | Read-only snapshot for debugging. |

## Modes

- **`turns`** — strict alternation. The server rejects out-of-turn `send_message` calls. Best for "Q&A," "code review," "debate."
- **`continuous`** — either agent can post anytime, capped at `--max-turns` messages each. Best for parallel brainstorming.

## Stop conditions (any one ends the conversation)

- An agent reaches `--max-turns` messages.
- An agent calls `send_message` with `signal='done'` (task complete) or `signal='blocked'` (needs human).
- You manually run `inspect_conversations.py ... stop <id>`.

## Inspection / debugging

```powershell
# List all conversations
python inspect_conversations.py --db-path ... list

# Full transcript
python inspect_conversations.py --db-path ... show 1

# Tail live (Ctrl-C to stop)
python inspect_conversations.py --db-path ... tail 1

# Force-end a runaway conversation
python inspect_conversations.py --db-path ... stop 1
```

The DB is just SQLite — `sqlite3 chat.db` and `SELECT * FROM messages` works too.

## Design notes

- **WAL mode.** The DB uses `PRAGMA journal_mode=WAL` so two processes (the two MCP servers) can read/write the same file safely.
- **No background polling.** Agents pull state via `get_my_turn` whenever they want to check. If you want push-style behavior later, a `wait_for_turn(timeout=N)` tool that loops with `time.sleep(0.5)` is easy to add.
- **Identity is config-only.** There's no auth — anything that runs the server with `--agent-id X` *is* X. Fine for two local CLIs you control; do not expose this over a network without adding auth.
- **Conversations persist.** Killing both CLIs and reopening them resumes from the same DB. State survives restarts.

## Possible next steps

- `wait_for_turn` tool to make turn handoff feel responsive without polling.
- A "moderator" pseudo-agent that posts system reminders mid-conversation (e.g., "10 turns left, start wrapping up").
- Multi-conversation support — the schema already supports it; `get_latest_conversation` picks the newest one for the agent. To run many in parallel, switch to selecting by an explicit `--conversation-id` per agent registration.
- Three+ agents. Schema and turn rotation already handle this; just pass three ids in `--participants`.
