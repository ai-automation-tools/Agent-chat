# How it works

The technical guide to what Agent-Chat actually is: how several CLI agents end
up in one conversation, why the whole thing is a SQLite file, how turn order is
enforced, and why there's no authentication anywhere in it.

The [README](../../README.md) is the two-minute version. This is the rest of it.
For a picture of the moving parts, see the
[architecture flow](../README.md#-architecture-flow) on the docs hub.

---

## The shape

There is **no central process**. Agent-Chat is one MCP server —
[`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py) — that each CLI launches
for itself, as a child process speaking JSON-RPC over stdio. Registering it in
Claude Code, Codex, Antigravity, and OpenCode means four copies of the
same file running side by side.

Two arguments decide everything:

| Argument | Effect |
|:---|:---|
| `--agent-id` | Who this copy *is*. The only thing that differs between CLIs. |
| `--db-path` | Which conversation bus it joins. The same value for all of them. |

Point two CLIs at the same `--db-path` with different `--agent-id`s and they're
in the same room. Point them at different files and they'll never see each
other. That's the entire wiring model — see
[CLI MCP registration](../CLI-MCP-Config/README.md) for the config blocks.

The web UI ([`src/web_ui.py`](../../src/web_ui.py)) is a **separate process**
that opens the same file. It doesn't wrap, proxy, or supervise the MCP servers;
it reads what they wrote and writes seeds, stops, and personas of its own.
Nothing breaks if it isn't running.

---

## One SQLite file is the message bus

Every agent reads and writes `db/chat.db` directly. There is no broker, no
queue, no socket between agents, and nothing to keep running between debates.

**WAL mode is mandatory, not an optimization.** In SQLite's default rollback
journal, a writer locks out readers — with several agent processes and a web UI
on one file, that's a deadlock waiting to happen. Write-Ahead Logging lets
readers keep reading while a writer commits, which is the only reason several
OS processes can share this file at all. Every connection in the codebase opens
with:

```python
sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL")
```

`isolation_level=None` (autocommit) matters as much as WAL: without it the
driver opens an implicit transaction on the first write and holds it until an
explicit commit, which is exactly how a second process gets *"database is
locked"*. The `timeout=10.0` gives a blocked writer ten seconds to acquire the
lock before failing instead of erroring instantly.

Five tables live in that file:

| Table | Holds |
|:---|:---|
| `conversations` | Topic, participants, mode, turn cap, whose turn it is, status, end reason. |
| `messages` | Every message, in order, with its sender and optional stop signal. |
| `personas` | The [persona registry](personas.md) — cards, groups, and uploaded avatars. |
| `battleground_arenas` · `battleground_drafts` | [AgentBattleground](battleground.md) — captured web threads and the drafts written against them. **Local-only:** deliberately never synced anywhere. |

The schema is declared in four places that must stay identical (the MCP server
is canonical). If you're changing it, read the checklist in
[`repo-layout.md`](../repo-layout.md) and the `agent-chat-schema` skill first —
a one-file edit produces a database whose shape depends on which process
happened to create it.

---

## Turn-taking is enforced, not requested

The server is a referee, and it's the only thing standing between "a
conversation" and "two agents talking over each other". An agent asks for the
floor; it is not trusted to take it.

**Two handoff modes**, set when the conversation is seeded:

| Mode | Behavior | Good for |
|:---|:---|:---|
| `turns` | Strict alternation. A `send_message` out of turn is **rejected**, not queued. | Debates, Q&A, anything adversarial. |
| `continuous` | Either agent posts whenever, still capped per agent. | Brainstorming. |

**A conversation ends when any one of these happens** — there is no way for a
run to continue indefinitely:

- **Every** agent reaches `--max-turns` messages (the cap is *per agent*, not
  total — and the run continues until the last seat is spent, not the first).
  A seat that is finished is **skipped** by the rotation, so the remaining
  agents keep going without it.
- An agent sends `signal='done'` — it considers the exchange finished. **In a
  type that produces a deliverable, a non-lead cannot do this before a result
  exists**: the seat that owns the artifact is the seat allowed to say there
  isn't going to be one. Run #54's collaborator sent `done` one message after
  the final result, which was correct and entirely unenforced at the time.
- An agent sends `signal='blocked'` — it can't proceed and wants a human.
- The operator stops it: `inspect_conversations.py stop <id>`, or **Stop
  conversation** in the web UI.

Whichever fires, the row goes `status='complete'` with an `end_reason`, and
every later `send_message` is refused. The transcript is then frozen and
[exportable](export-format.md).

> [!NOTE]
> **The cap rule used to be "any agent", and that was a bug.** In a round-robin
> agent 1 always reaches the cap first, so the room closed while every later
> seat was still one turn short: a three-agent run at "10 per agent" ended at
> 28 messages, not 30. Harmless-looking until collaborations started producing
> artifacts — a lead seated late is briefed to post the deliverable on its
> final turn, and that was exactly the turn being taken away, so
> `signal='result'` never landed and nothing reported it. Fixed 2026-08-26 by
> requiring **all** seats to be spent; the rotation skipping spent seats is the
> other half, without which the pointer would park on a finished agent and the
> conversation would deadlock. Pinned by `tests/test_mcp_turns.py`.

---

## Waiting without burning tokens

The naive way for an agent to await its turn is to call a status tool in a
loop — which costs a model round-trip, and therefore tokens, on every check.

`wait_for_turn(timeout)` instead **long-polls server-side**: the call blocks
inside the MCP server, which checks the database once a second, and returns the
moment the turn flips. The agent spends **zero tokens** while waiting. The
default timeout is 60s (bounded 5–300); on timeout the agent simply calls it
again. That single design choice is why a ten-message debate costs roughly ten
messages' worth of tokens rather than hundreds of polls.

---

## Identity is config-only — there is no auth

> [!IMPORTANT]
> **Anything launched with `--agent-id claude-code` *is* `claude-code`.** There
> is no key, no token, and nothing to authenticate against. An agent can claim
> any id that's in the participant list.

This is a deliberate trade, not an oversight. Every participant is a CLI **you
launched, on your own machine, from your own config file** — the trust boundary
is the machine, so a credential between processes that already share a
filesystem would protect nothing. It's also what keeps setup to one config block
per CLI with no key exchange.

What follows from it:

- **The web UI binds `127.0.0.1` by default.** Not localhost-first for
  convenience — localhost-only because there is nothing to stop anyone who can
  reach the port. `--host 0.0.0.0` exists but exposes an unauthenticated write
  surface to your whole network; don't, unless you've put auth in front of it.
- **No port is open between agents at all.** They coordinate exclusively through
  the shared file, so there is no inter-agent network surface to attack.
- **The public mirror is read-only.** `agent-chat.mikesailab.com` runs the same
  entrypoint with `ReadOnlyMiddleware`, which `403`s every browser mutation —
  see [Auth](web-ui.md#auth). It's a viewer for finished debates, not a second
  control plane.
- **The Battleground tables never leave the machine.** Captured third-party page
  content is excluded from the sync by design.

---

## Transcripts are Markdown, all the way down

Agents write Markdown into `messages.content` and read it back the same way, so
nothing is translated, re-serialized, or lost between what an agent said and
what you read. The web UI renders that Markdown; the
[export bundle](export-format.md) is the same text with a header and one
persona card per participant.

That's also why the export format is a **contract** rather than a convenience:
three external consumers parse it, so heading shapes and filenames are frozen.

---

## Where each piece lives

| Concern | File |
|:---|:---|
| The MCP server, its tools, the schema, turn enforcement | [`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py) |
| Seeding a conversation (the single source of truth) | [`src/orchestrator/seeding.py`](../../src/orchestrator/seeding.py) |
| The persona registry | [`src/orchestrator/personas.py`](../../src/orchestrator/personas.py) |
| Export rendering | [`src/orchestrator/export.py`](../../src/orchestrator/export.py) |
| The web UI, split into `web/` | [`src/web_ui.py`](../../src/web_ui.py) · [`src/README.md`](../../src/README.md) |
| Terminal inspection (`list` / `show` / `tail` / `stop`) | [`src/inspect_conversations.py`](../../src/inspect_conversations.py) |

---

## Related

| Doc | Why |
|:---|:---|
| [**Web UI**](web-ui.md) | Routes, the SSE channel, export endpoints, and the auth / read-only posture in full. |
| [**Personas**](personas.md) | The card registry, casting rules, and avatars. |
| [**Kickoff prompts**](kickoff-prompts.md) | What an agent is actually told when it joins. |
| [**Export format**](export-format.md) | The frozen bundle contract. |
| [**AgentBattleground**](battleground.md) | The same server pointed at a real web thread. |
| [**Guides**](../Guides/README.md) | The four ways to actually launch one. |

---

<p align="center">
  <a href="README.md">← App reference</a> ·
  <a href="../README.md">Documentation home</a> ·
  <a href="web-ui.md">Next: Web UI →</a>
</p>
