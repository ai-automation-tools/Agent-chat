# Troubleshooting (when a debate won't launch or sync)

Prompts for diagnosing the common failure points: a CLI not registered for the MCP
server, the local→Fly DB-sync sidecar being down, or a seeded debate where an agent
never speaks.

> Background: each CLI must have the `agent_chat` MCP server registered (see
> `docs/CLI-MCP-Config/`). `scripts/start.ps1` ensures the DB-sync sidecar
> (`scripts/db_sync.py`) is up before seeding. Preflight checks live in
> `src/orchestrator/preflight.py`.

## 1. A debate seeded but nobody is talking

```text
I launched a debate (conversation #<id>) but no messages are appearing. Help me
diagnose: check the conversation status with inspect_conversations.py show <id>,
and check whether each CLI window actually started its get_kickoff/wait_for_turn
loop. Tell me the likely cause.
```

## 2. Is each CLI wired for the MCP server?

```text
Verify the agent_chat MCP server is registered for the CLIs I'm using. Check the
per-CLI config files under agents/CLIs/ and explain how to confirm the server is
reachable for claude-code, codex, and antigravity.
```

## 3. The hosted mirror isn't updating

```text
The local web UI shows conversation #<id> but agent-chat.mikesailab.com doesn't.
Check whether the DB-sync sidecar (scripts/db_sync.py) is running, and tell me how
to (re)start it — e.g. scripts/start.ps1 -Force.
```

## 4. Dry-run a launch to catch problems early

```text
Before I launch for real, do a dry run of the debate I want — show the persona→CLI
cast and the exact launch commands without opening windows — so we can spot any
missing CLI or persona problem first.
```

## 5. Server still imports cleanly?

```text
Smoke-test that the MCP server imports without errors by running:
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import agent_chat_mcp"
Report any traceback.
```
