---
name: agent-chat-schema
description: Use when changing the Agent-Chat SQLite schema — adding/renaming/dropping a column or table, adding a migration, or touching db_init()/db_connect() pragmas. The schema is duplicated across four files and is the contract between processes, so a one-file edit silently breaks the other writers. Triggered by work on src/agent_chat_mcp.py SCHEMA, src/web/db.py, src/orchestrator/seeding.py, src/orchestrator/personas.py, _MIGRATIONS, "add a column", "migrate the DB", "new table".
---

# Agent-Chat schema changes

The DB **is** the contract between processes: the MCP server, the web UI, the
seeder and the persona registry all open the same SQLite-WAL file. There is no
ORM and no single migration tool — the schema is **copy-pasted across four
files**, so changing one and not the others produces a DB whose shape depends on
which process happened to create it first.

## The four declaration sites

| File | Constant | Scope |
|:---|:---|:---|
| `src/agent_chat_mcp.py` | `SCHEMA` | **canonical** — all 3 tables + 2 indexes |
| `src/web/db.py` | `SCHEMA` | full mirror (comments stripped) |
| `src/orchestrator/seeding.py` | `SCHEMA` | full mirror |
| `src/orchestrator/personas.py` | `_PERSONA_DDL` | `personas` table only |

`_MIGRATIONS` is duplicated in the first three as an identical tuple of
`(table, column, ddl)` triples, applied by `db_init()` gated on
`PRAGMA table_info({table})` so it stays idempotent:

```python
("conversations", "preset", "ALTER TABLE conversations ADD COLUMN preset TEXT"),
```

> [!IMPORTANT]
> `CLAUDE.md` tells you to update `start_conversation.py` and
> `inspect_conversations.py` on a schema change. **That guidance is stale** —
> neither declares schema. `start_conversation.py` is argparse-only and delegates
> to `orchestrator.seeding`; `inspect_conversations.py` only has `connect()` plus
> raw SELECT/UPDATE. Update them only if you changed a *column they query*.

## Checklist for a schema change

1. **Additive only, by default.** New columns are safe: add to the canonical
   `SCHEMA`, mirror into the other declaration sites, and append a
   `(table, column, ddl)` row to every `_MIGRATIONS` copy so existing
   `db/chat.db` files upgrade in place. Renames and drops need an explicit
   migration plan — SQLite can't drop a column on older versions, and every
   running CLI holds the old shape.
2. **Mirror all four sites in the same change.** Grep for the constant to be
   sure: `SCHEMA`, `_MIGRATIONS`, `_PERSONA_DDL`.
3. **Update every reader of the changed column** — `inspect_conversations.py`,
   `web/db.py` helpers, `orchestrator/export.py`, the SSE payload in
   `web/api/conversations.py`, and the `/api/ingest` + `/api/since` sync path
   (a column the sidecar doesn't carry won't reach the Fly mirror).
4. **Note it in `docs/CHANGELOG.md`.** Schema changes are always changelog-worthy.
5. **Verify against a real DB**, never a mock — the WAL multi-process behaviour
   is the thing under test:
   ```powershell
   .\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import agent_chat_mcp"
   .\.venv\Scripts\python.exe tests\test_web_readonly.py
   ```
   Then seed a `--max-turns 2` conversation against a **temp** DB and confirm it
   reaches `status='complete'`.

## Connection rules

WAL is mandatory (`PRAGMA journal_mode=WAL`) — two processes write the same file.
Connections use `timeout=10.0` and `isolation_level=None`. Parameterize every
query; no string-concatenated SQL.

Pragmas are **not** uniform today, which is worth knowing before you "fix" one:

| Site | Notes |
|:---|:---|
| `agent_chat_mcp.db_connect()` | the full set: WAL + `synchronous=NORMAL` + `foreign_keys=ON` |
| `web/db.py:_connect()` | WAL only, and **omits `isolation_level=None`** — deviates from CLAUDE.md |
| `seeding.py` / `personas.py` / `inspect_conversations.py` | WAL + `isolation_level=None` |

## Current shape

- **`conversations`** — `id`, `topic`, `participants` (JSON array), `mode`
  (`turns`|`continuous`), `max_turns`, `current_turn`, `status`
  (`active`|`complete`), `end_reason`, `created_at`, `updated_at`, `preset`,
  `kickoff_template`, `participant_personas` (JSON
  `{agent_id: {persona_slug, persona_name, persona_body}}`).
- **`messages`** — `id`, `conversation_id` → conversations(id), `sender`,
  `content`, `signal` (`done`|`blocked`), `created_at`.
- **`personas`** — `"group"` (quoted — SQL reserved word), `slug`, `name`,
  `tags` (JSON), `category`, `subcategory`, `body`, `created_at`, `updated_at`;
  `PRIMARY KEY ("group", slug)`.
- Indexes: `idx_messages_conv ON messages(conversation_id, id)`,
  `idx_personas_updated ON personas(updated_at)`.
