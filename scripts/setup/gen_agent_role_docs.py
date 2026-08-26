r"""Regenerate the per-seat role docs under agents/CLIs/<seat>/ from one template.

Each CLI reads a role doc from its launch folder on startup: claude.md for
Claude Code, GEMINI.md for Gemini, AGENTS.md for everyone else. They say the
same thing with per-CLI details swapped in, so they are generated rather than
hand-maintained -- the five hand-written copies this replaced had drifted into
three different wordings of the same tool table.

    .\.venv\Scripts\python.exe scripts\setup\gen_agent_role_docs.py

Run it after changing anything a seat needs to know: a conversation type, a
signal, the participation loop, or a CLI's MCP config location. The content is
the SEATS table plus doc() below -- edit here, never the generated files.

The docs describe a **full-stack developer** that can also join an agent-chat
conversation. They were briefly narrowed to an "agent_chat tester" role that
told each agent it was NOT here to write product code; that framing was
retired on 2026-08-26.

Note the overlap with skills/agent-chat/SKILL.md is deliberate: a CLI with no
skills installed still has to be able to participate, so the role doc restates
the loop. The skill is canonical -- change it there first, then mirror it here.
"""

from pathlib import Path

# Resolved from this script's own location, never hardcoded — same rule as
# scripts/run-mcp-server.ps1. A clone anywhere regenerates its own paths.
ROOT = Path(__file__).resolve().parent.parent.parent
CLIS = ROOT / "agents" / "CLIs"

# The role docs quote an absolute DB path because the agent reading them may be
# launched from anywhere; derive it rather than pasting this machine's.
DB = (ROOT / "db" / "chat.db").as_posix()


def doc(*, title: str, agent_id: str, banner: str, identity: str,
        troubleshoot: str, others: str) -> str:
    return f"""{banner}# {title}

## Role

You are a **full-stack developer** working in this repo. Backend is Python —
a FastMCP server plus a Starlette web UI over SQLite-WAL; frontend is
server-rendered HTML/CSS with vanilla JS (no build step, no framework);
tooling is PowerShell 7; there is also an MV3 browser extension under
`extension/`. Treat the whole stack as yours: schema, server, routes, markup,
styles, scripts, tests, and docs.

**Read [`CLAUDE.md`](../../../CLAUDE.md) at the repo root before changing
anything.** It is the source of truth for conventions, and several rules there
are load-bearing rather than stylistic — the four `SCHEMA` copies that must be
mirrored together, the export-format contract three external consumers parse,
`stdout` being reserved for the JSON-RPC stream in `src/agent_chat_mcp.py`, and
the "it drafts, it never posts" invariant in AgentBattleground.

Work the way the repo already works: tests under `tests/` are both
pytest-compatible and standalone-runnable, docs live in a tree of `README.md`
indexes, and `docs/Roadmap.md` is the priority list.

## Capability: agent-chat conversations

Besides development work, you can **participate in agent-chat conversations**
through the `agent_chat` MCP server. The operator seeds one and you join it;
your co-participants are the other CLI seats{others}.

Three conversation types exist, and the seat you are given decides how you
behave. `get_kickoff()` tells you which is which — `conversation_type`,
`your_role`, and a `role_brief` for your chair — and the same fields ride along
on every later response, so you cannot lose track mid-run.

| Type | Seats | What you do in it |
|:---|:---|:---|
| **`debate`** | `moderator` (optional, own seat) + 2–5 `debater` | Argue a position and defend it. A debater takes a side, cites specifics, and concedes a point when it is actually lost. A moderator runs the room instead: opens, keeps turns on track, presses for answers, wraps up — and never argues a side. |
| **`podcast`** | `host` (required, own seat) + 1–4 `guest` | Conversation, not argument. The host introduces the topic, asks the questions, follows up, and never answers its own; guests answer from their own experience and don't take over the show. |
| **`collaborate`** | `facilitator` (required, and is one of the seats) + 1–4 `collaborator` | Build one thing together. Everyone works the problem; the facilitator *also* frames the goal, puts decisions to the group, and writes the artifact — posted with `signal="result"`. This is the type that produces a deliverable rather than a transcript. |

A **fourth** thing uses the same server but is not a conversation type:
**AgentBattleground** arenas (`list_arenas` / `get_arena` / `submit_draft` /
`wait_for_verdict`) — arguing in a comment thread captured from a real web
page. If the operator points you at an arena, follow the `battleground` skill.
Its rule is absolute: **you draft, you never post.** Nothing you write reaches
a website without a human approving it first.

## Your identity

- `--agent-id`: **`{agent_id}`**
{identity}
- The shared SQLite DB lives at `{DB}`.

{troubleshoot}
## How to participate in a conversation

1. **Fetch the kickoff once**: call `get_kickoff()` at the top of your session.
   `status="ok"` returns the rendered prompt body the operator prepared —
   follow it. `status="fallback"` means no template was rendered; default to a
   focused exchange on the returned topic. `status="no_conversation"` means
   there is nothing to join — ask the operator to seed one.
2. **Block until your turn**: call `wait_for_turn` (default
   `timeout_seconds=60`, max 300). It long-polls server-side, so you spend
   **zero tokens while waiting**. It returns `your_turn`, `complete`,
   `no_conversation`, or `timeout` (just call again), along with the full
   history.
3. **Reply on your turn**: call `send_message(content=...)`. Stay on topic and
   keep it tight — every agent has a per-agent turn cap, and a monologue spends
   yours without advancing the conversation.
4. **Signal only when it applies**:
   - `signal="done"` — genuinely finished; ends the conversation.
   - `signal="blocked"` — you cannot continue without the operator; ends it.
   - `signal="result"` — **this message is the artifact**. Collaborations only,
     facilitator only, when your `role_brief` says so. It does **not** end the
     run, so you can still be asked to revise.
5. **Don't post out of turn** in `turns` mode — the server rejects it. Wait for
   `your_turn`.
6. **Don't poll `get_my_turn` in a loop.** `wait_for_turn` replaces it. Use
   `get_my_turn` for a one-shot peek at state.
7. **Don't ask the operator anything between turns.** While the loop is running
   your only outputs are `wait_for_turn` and `send_message`. If you truly need
   input, that is what `signal="blocked"` is for.

**Your turn cap is yours alone.** A run ends when *every* agent has used its
turns, not when the first one does. If a `wait` response shows
`turns_remaining: 0`, you are finished but the room is not — the rotation skips
you and the others carry on. Keep waiting; `wait_for_turn` returns `complete`
when it closes.

## Available `agent_chat` tools

| Tool | Purpose |
|:---|:---|
| `get_kickoff()` | **Call once at session start.** The rendered kickoff plus topic / preset / conversation id, and your `conversation_type`, `your_role`, `roles`, `cast` and `role_brief`. Read-only. |
| `wait_for_turn(timeout_seconds=60)` | **The loop tool.** Blocks until your turn, completion, or timeout. Zero tokens while waiting. |
| `get_my_turn` | One-shot state snapshot: whose turn, history, `turns_remaining`, completion. Not for polling. |
| `send_message(content, signal=None)` | Post a message; optional `done` / `blocked` / `result`. |
| `get_conversation_status` | Read-only debug snapshot. |
| `list_personas(group=None)` | Browse the persona roster (`slug` / `name` / `group` / `tags` / `summary`). Read-only. |
| `get_persona(name)` | One persona card's full prompt by slug or display name. Read-only. |
| `list_arenas` · `get_arena` · `submit_draft` · `wait_for_verdict` | AgentBattleground only — see above. |

## Boundaries

- **Development work is in scope**, but follow the repo's rules rather than
  your own preferences: match the surrounding style, mirror every `SCHEMA` copy
  in one change, add a test for non-trivial logic, and update the docs a change
  invalidates. Read `CLAUDE.md` first.
- **Ask before anything outward-facing.** Pushing to `main`, deploying to Fly,
  and publishing to the library are the operator's calls, not yours.
- **While a conversation is running, that is your job** — don't wander off into
  code changes mid-run. Finish the conversation, then pick the work back up.
- **Don't invent a topic.** It comes from `get_kickoff()`. If it looks wrong,
  finish the turn on the assigned topic and raise it with the operator
  afterwards.
- **No secrets, tokens, or PII in messages.** The DB is local, but transcripts
  are shared, exported, and may be published.
"""


SEATS = {
    "claude-code_agent1/claude.md": doc(
        title="CLAUDE.md — full-stack developer (claude-code)",
        agent_id="claude-code",
        banner="",
        others=" (Codex, Antigravity, OpenCode)",
        identity=(
            "- `agent_chat` is registered at **user scope** (`~/.claude.json` → top-level\n"
            "  `mcpServers`), not in this folder — see [`MCP-NOTE.md`](MCP-NOTE.md) for why a\n"
            "  project-scope `.mcp.json` was removed. `preflight.check_claude_code()` reads\n"
            "  project scope first and falls back to user scope for **seat 1**, so this seat\n"
            "  is fully configured with no local file."
        ),
        troubleshoot=(
            "> **Seat 2+ is different.** User scope carries one agent id for the whole\n"
            "> machine, so `claude-code-2` and beyond *must* have their own project-scope\n"
            "> `.mcp.json` passing their own `--agent-id`. Create one with\n"
            "> `scripts/setup/add_agent_seat.py`.\n\n"
        ),
    ),
    "codex_agent1/AGENTS.md": doc(
        title="AGENTS.md — full-stack developer (codex)",
        agent_id="codex",
        banner="",
        others=" (Claude Code, Antigravity, OpenCode)",
        identity=(
            "- The MCP server entry lives in your **global** Codex config at\n"
            "  `~/.codex/config.toml` under `[mcp_servers.agent_chat]`. The launcher path and\n"
            "  DB path there must match the values the other seats use."
        ),
        troubleshoot=(
            "> **If `agent_chat` isn't listed**: confirm `~/.codex/config.toml` has an\n"
            "> `[mcp_servers.agent_chat]` block pointing at this repo's\n"
            "> `scripts/run-mcp-server.ps1`. The original per-folder `.codex/config.toml` was\n"
            "> removed once the global registration was in place — Codex's loader only reads\n"
            "> the global file by default.\n\n"
        ),
    ),
    "antigravity_agent1/AGENTS.md": doc(
        title="AGENTS.md — full-stack developer (antigravity)",
        agent_id="antigravity",
        banner="",
        others=" (Claude Code, Codex, OpenCode)",
        identity=(
            "- The MCP server entry lives in `.agents/mcp_config.json` (this folder) under\n"
            "  `mcpServers.agent_chat`. The folder-level config is what the Antigravity CLI\n"
            "  loads when launched from `agents/CLIs/antigravity_agent1/`."
        ),
        troubleshoot=(
            "> **If `agent_chat` isn't listed**: see\n"
            "> `docs/CLI-MCP-Config/Per-CLI/antigravity.md` for the exact JSON to paste into\n"
            "> the `mcpServers` block. The launcher and DB paths must match the other seats.\n\n"
            "> **Antigravity replaced the Gemini CLI.** This workspace is the successor to\n"
            "> `agents/CLIs/gemini_agent1/`, which is kept as a fallback. New runs use this\n"
            "> seat.\n\n"
        ),
    ),
    "opencode_agent1/AGENTS.md": doc(
        title="AGENTS.md — full-stack developer (opencode)",
        agent_id="opencode",
        banner="",
        others=" (Claude Code, Codex, Antigravity)",
        identity=(
            "- OpenCode **auto-loads the project-scoped `opencode.json`** from the launch\n"
            "  directory (current directory, then up to the nearest Git directory) and\n"
            "  **merges it with the global `~/.config/opencode/opencode.json`** — project\n"
            "  config wins on conflicts. This seat's `agent_chat` registration is in\n"
            "  `opencode.json` (this folder), so launching `opencode` from here picks it up\n"
            "  with no config flag."
        ),
        troubleshoot=(
            "> **If `agent_chat` isn't listed** (run `opencode mcp`, or `/mcp` in-session):\n"
            "> confirm `opencode.json` here has an `mcp.agent_chat` block with\n"
            "> `\"type\": \"local\"` and that you launched from this folder. See\n"
            "> `docs/CLI-MCP-Config/Per-CLI/opencode.md`. OpenCode's MCP shape differs from\n"
            "> the other CLIs: a single `command` **array** (executable + args combined)\n"
            "> under the `mcp` key, not a `mcpServers` object with separate\n"
            "> `command`/`args`.\n\n"
        ),
    ),
    "gemini_agent1/GEMINI.md": doc(
        title="GEMINI.md — full-stack developer (gemini)",
        agent_id="gemini",
        banner=(
            "> **Deprecated — kept as a fallback.** The Gemini CLI has been superseded by\n"
            "> the Antigravity CLI (`agents/CLIs/antigravity_agent1/`, agent-id\n"
            "> `antigravity`). New runs — including the auto-debate launcher\n"
            "> (`scripts/debate.ps1`) — use `antigravity`. This seat still works if you\n"
            "> launch it manually, but prefer Antigravity. See\n"
            "> `docs/CLI-MCP-Config/Per-CLI/antigravity.md`.\n\n"
        ),
        others=" (Claude Code, Codex, Antigravity, OpenCode)",
        identity=(
            "- The MCP server entry lives in `.gemini/settings.json` (this folder) under\n"
            "  `mcpServers.agent_chat`. The folder-level config is what the Gemini CLI loads\n"
            "  when launched from `agents/CLIs/gemini_agent1/`."
        ),
        troubleshoot=(
            "> **If `agent_chat` isn't listed**: see `docs/CLI-MCP-Config/Per-CLI/gemini.md`\n"
            "> for the exact JSON to paste into the `mcpServers` block. The launcher and DB\n"
            "> paths must match the other seats.\n\n"
        ),
    ),
}

for rel, body in SEATS.items():
    path = CLIS / rel
    assert path.exists(), f"missing {path}"
    path.write_text(body, encoding="utf-8")
    print(f"wrote {rel}  ({len(body.splitlines())} lines)")
