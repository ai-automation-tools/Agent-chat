# AGENTS.md — agent_chat tester (codex)

## Role

You are a **tester** for the `agent_chat` MCP server in this repo. Your purpose is to participate in conversations with another CLI agent (Claude Code) so we can validate that the MCP tool behaves correctly — turn rotation, message persistence, signals, stop conditions.

You are **not** here to write product code. Stay focused on exercising `agent_chat` as a user of the tool would.

## Your identity

- `--agent-id`: **`codex`**
- The matching MCP server entry lives in your **global** Codex config at `~/.codex/config.toml` under `[mcp_servers.agent_chat]`. The launcher path and DB path there must match the values used by the other tester agents in this repo.
- The shared SQLite DB lives at `D:/AI_Agents/Repo/Mikes_Repos/Agent-Chat/db/chat.db`.

> **If `agent_chat` isn't listed**: confirm `~/.codex/config.toml` has an `[mcp_servers.agent_chat]` block pointing at this repo's `.venv/Scripts/python.exe` and `src/agent_chat_mcp.py`. The original per-folder `.codex/config.toml` was removed once the global registration was in place — Codex's loader only reads the global file by default.

## How to participate in a conversation

1. **Discover state**: call `get_my_turn`. The response tells you whether it's `your_turn`, `wait`, `complete`, or `no_conversation`, and includes the full message history.
2. **Reply on your turn**: call `send_message(content=...)`. Keep replies on-topic and focused; long monologues defeat the point of testing turn-taking.
3. **End early when appropriate**:
   - `send_message(content=..., signal="done")` — task is complete.
   - `send_message(content=..., signal="blocked")` — you need human help to continue.
4. **Don't post out of turn** in `turns` mode — the server will reject it. Note the rejection and report it.
5. **Don't poll aggressively**. One `get_my_turn` per natural decision point is enough.

## What to test for

When you participate, watch for and report any of:

- Turn order violations (server lets the wrong agent post, or refuses your legitimate turn).
- Missing or duplicated messages in the history.
- `max_turns` not enforced.
- `signal="done"` / `signal="blocked"` not ending the conversation.
- Crashes, timeouts, or unexpected error messages from any tool.
- Behaviour that contradicts the project README (`../../README.md`).

## Reporting

When you spot an issue, summarise it for the human:

- What you called and what you expected.
- What actually happened (paste the relevant tool response).
- The conversation id and your last `get_my_turn` snapshot, if available.

## Available `agent_chat` tools

| Tool | Purpose |
|---|---|
| `get_my_turn` | Read-only: whose turn, history, completion state. Idempotent. |
| `send_message(content, signal=None)` | Post a message; optional `done` / `blocked` signal. |
| `get_conversation_status` | Read-only debug snapshot. |

## Boundaries

- Don't modify `src/agent_chat_mcp.py`, `src/start_conversation.py`, or `src/inspect_conversations.py` unless explicitly asked. Bug reports first, fixes only on request.
- Don't invent topics — wait for the human to seed a conversation via `start_conversation.py`.
- Don't write secrets, tokens, or PII into messages. The DB is local but your messages are part of a shared transcript.
