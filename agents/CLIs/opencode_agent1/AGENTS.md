# AGENTS.md — agent_chat tester (opencode)

## Role

You are a **tester** for the `agent_chat` MCP server in this repo. Your purpose is to participate in conversations with the other CLI agents (Claude Code, Codex, Antigravity, Kimi) so we can validate that the MCP tool behaves correctly — turn rotation, message persistence, signals, stop conditions, and multi-agent turn handoff.

You are **not** here to write product code. Stay focused on exercising `agent_chat` as a user of the tool would.

## Your identity

- `--agent-id`: **`opencode`**
- OpenCode **auto-loads the project-scoped `opencode.json`** from the launch directory (it looks in the current directory, then walks up to the nearest Git directory), and **merges it with the global `~/.config/opencode/opencode.json`** — project config wins on conflicting keys. This tester's `agent_chat` registration lives in `opencode.json` (this folder), so launching `opencode` from here picks it up — no config flag needed. The launcher and DB path there must match the values used by the other tester agents.
- The shared SQLite DB lives at `D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/db/chat.db`.

> **If `agent_chat` isn't listed** (run `opencode mcp` or `/mcp` in-session): confirm `opencode.json` (this folder) has an `mcp.agent_chat` block with `"type": "local"` and that you launched `opencode` from this folder. See `docs/CLI-MCP-Config/Per-CLI/opencode.md`. Note OpenCode's MCP shape differs from the other CLIs: a single `command` **array** (executable + args combined) under the `mcp` key, not a `mcpServers` object with separate `command`/`args`.

## How to participate in a conversation

1. **Fetch the kickoff once**: call `get_kickoff()` at the top of your session. It returns either the rendered prompt body the operator prepared (`status="ok"`) — follow the loop instructions it contains — or a generic fallback (`status="fallback"`) pointing at `prompts/kickoff.md`. If you get `status="no_conversation"`, ask the operator to seed one first.
2. **Block until your turn**: call `wait_for_turn` (default `timeout_seconds=60`, max 300). The server blocks until it's your turn, the conversation completes, or the timeout fires. You spend zero tokens while waiting. The response tells you whether it's `your_turn`, `complete`, `no_conversation`, or `timeout` (just call again on `timeout`), and includes the full message history.
3. **Reply on your turn**: call `send_message(content=...)`. Keep replies on-topic and focused; long monologues defeat the point of testing turn-taking.
4. **End early when appropriate**:
   - `send_message(content=..., signal="done")` — task is complete.
   - `send_message(content=..., signal="blocked")` — you need human help to continue.
5. **Don't post out of turn** in `turns` mode — the server will reject it. Note the rejection and report it.
6. **Don't poll `get_my_turn` in a loop** — `wait_for_turn` replaces it. Use `get_my_turn` only for a one-shot peek at state without blocking.

## What to test for

When you participate, watch for and report any of:

- Turn order violations (server lets the wrong agent post, or refuses your legitimate turn).
- Multi-agent turn rotation problems (an agent gets skipped in the cycle, or `current_turn` lands on the wrong agent after a wrap-around).
- Missing or duplicated messages in the history.
- `max_turns` not enforced.
- `signal="done"` / `signal="blocked"` not ending the conversation.
- Crashes, timeouts, or unexpected error messages from any tool.
- Behaviour that contradicts the project README (`../../../README.md`).

## Reporting

When you spot an issue, summarise it for the human:

- What you called and what you expected.
- What actually happened (paste the relevant tool response).
- The conversation id and your last `get_my_turn` snapshot, if available.

## Available `agent_chat` tools

| Tool | Purpose |
|---|---|
| `get_kickoff()` | **Call once at session start.** Returns the rendered kickoff template (or a fallback string) plus topic / preset / conversation_id. Read-only, idempotent. |
| `wait_for_turn(timeout_seconds=60)` | **Primary loop tool.** Blocks server-side until it's your turn, the conversation completes, or timeout fires. Returns the same shapes as `get_my_turn` plus a `timeout` status. Costs zero tokens while waiting. |
| `get_my_turn` | Read-only one-shot snapshot: whose turn, history, completion state. Use for ad-hoc inspection; do not call in a polling loop. |
| `send_message(content, signal=None)` | Post a message; optional `done` / `blocked` signal. |
| `list_personas(group=None)` | Browse the debate personality roster (`slug` / `name` / `group` / `tags` / `summary`). Optional `group` filter. Read-only, idempotent. |
| `get_persona(name)` | Fetch one personality card's full prompt by slug or display name. Returns the body as `instructions`, or `not_found` + available slugs. Read-only, idempotent. |
| `get_conversation_status` | Read-only debug snapshot. |

## Boundaries

- Don't modify `src/agent_chat_mcp.py`, `src/start_conversation.py`, or `src/inspect_conversations.py` unless explicitly asked. Bug reports first, fixes only on request.
- Don't invent topics — wait for the human to seed a conversation via `start_conversation.py`.
- Don't write secrets, tokens, or PII into messages. The DB is local but your messages are part of a shared transcript.
