# Personas

The debate **personality roster** is a typed, queryable registry plus two
read-only MCP tools, so an agent can browse the cast and adopt a character
**itself** — no operator step and no per-CLI file copying.

> [!IMPORTANT]
> **Storage moved to the database.** Personas now live in a `personas` table
> inside the shared SQLite DB (`db/chat.db`), and the [Fly sidecar](db-sync.md)
> syncs that table bidirectionally — so add/edit/delete works and persists on
> both the local box **and** the hosted mirror (`agent-chat.mikesailab.com`).
> The Markdown cards under [`agents/Debate-Agents/`](../../agents/Debate-Agents/)
> are now a **one-time import seed** only (they stay in git as the original
> snapshot). There is no DB→files export — the DB is the runtime source of truth.
> See [Storage & sync](#storage--sync) below.

Pairs with [`scripts/debate.ps1`](../Guides/auto-debate.md) (which injects a
*random* persona per CLI at launch — cast from `-Group <name>`, default
`Unique-Personas`) and the [`debate-mode`](../../skills/debate-mode/SKILL.md)
skill (which teaches how to argue *in* character).

---

## The seed cards

Each seed card is a Markdown file with YAML frontmatter:

```markdown
---
category: System_Prompts
subcategory: Podcast_Personalities
tags:
- crypto
- bro
title: "🤖 Crypto Chad"
---

# Crypto Chad

## Purpose
Act as a hyper-pumped crypto bro ...

## Instructions
You are Crypto Chad ...
```

Two canonical groups live side by side:

| Group | Seed folder | What's in it |
|:---|:---|:---|
| `Unique-Personas` | `agents/Debate-Agents/Unique-Personas/` | The debater roster — 25 exaggerated characters (Crypto Chad, Flat-Earth Fred, Pastor Cole, Vegan Vanessa, …). |
| `Debate-Hosts` | `agents/Debate-Agents/Debate-Hosts/` | Moderator / host personalities (4 cards — Jaxx Reign, Dr. Penelope Hartwell, …). |

`group` is just a label on the row — once imported, you can create a persona in
**any** group from the web UI, and groups are discovered dynamically from the DB
(see `discover_groups()` below). At seed time, any subfolder of
`agents/Debate-Agents/` becomes a group, so a new folder of `*.md` cards imports
with no code change.

Not every card uses the same `##` sections — the longer hand-authored cards
omit `## Purpose` / `## Instructions`. The registry never relies on section
structure: **everything after the frontmatter is the persona prompt**, and the
one-line `summary` is best-effort (the `## Purpose` paragraph if present, else
the first prose paragraph).

---

## The registry — `src/orchestrator/personas.py`

Stdlib-only (`sqlite3` + a hand-rolled frontmatter parser for the importer — no
PyYAML in the pinned deps). It is the single source of truth for "what
personalities exist and what is each one's prompt," reading and writing the
`personas` table directly.

```python
from orchestrator import personas

personas.list_personas()                        # canonical roster (Unique-Personas + Debate-Hosts), sorted by display name
personas.list_personas(group="Debate-Hosts")    # just the moderators
personas.get_persona("crypto-chad")             # by slug
personas.get_persona("Crypto Chad")             # …or display name (same Persona)

# write layer (used by the /personas web UI — works local + hosted)
personas.create_persona(name="New Bot", body="…", group="Unique-Personas", tags=["x"])
personas.update_persona("new-bot", body="…", group="Debate-Hosts")  # group= moves it
personas.delete_persona("new-bot")
```

- `Persona` is a frozen dataclass: `slug`, `name`, `group`, `tags`, `category`,
  `subcategory`, `summary`, `body`, `path`. `summary` and `path` are **derived**
  (not stored): `summary` is recomputed from `body`; `path` is synthesized as
  `agents/Debate-Agents/<group>/<slug>.md` so the shape is unchanged for callers
  (`debate.ps1` only displays `.path`, never opens it).
- `list_personas(group=None)` returns the **canonical roster** — the
  `PREFERRED_GROUPS = ("Unique-Personas", "Debate-Hosts")` constant. Passing a
  `group` filters to any group in the DB (case-insensitive).
- `discover_groups()` returns every group present in the `personas` table; the
  two `PREFERRED_GROUPS` sort first, the rest follow alphabetically.
- `get_persona()` matching is **case-, punctuation-, and emoji-insensitive**, so
  `crypto-chad`, `Crypto Chad`, and `🤖 Crypto Chad` all resolve to the same
  card. Returns `None` on no match.
- `create_persona` / `update_persona` / `delete_persona` write the table and
  raise `PersonaWriteError` on a blank name/body or a `(group, slug)` collision.
  `update_persona(..., group=...)` moves the row to another group (guarding
  against colliding with an existing target row).
- `root_exists()` now returns `True` whenever the DB is reachable (it used to gate
  on the on-disk `agents/` tree) — that's what un-gates management on the hosted
  mirror.
- An empty / unreachable DB yields an empty roster — the registry degrades
  gracefully.

### Seeding the DB from the cards — `import`

The on-disk seed cards are loaded into the DB once via the importer (idempotent —
`INSERT OR IGNORE`, or `--overwrite` to replace + bump `updated_at`):

```powershell
python src/orchestrator/personas.py import            # {"imported": 29, "skipped": 0}
python src/orchestrator/personas.py import --overwrite # re-seed from the cards
```

It's a no-op where the `agents/` tree isn't present (the hosted deploy seeds via
sync instead). `import_personas_from_files()` is the Python entry point.

### Non-Python callers — the JSON CLI

`scripts/debate.ps1` doesn't re-scan the folder; it shells out to the registry's
JSON CLI to cast its debaters:

```powershell
python src/orchestrator/personas.py list --group Unique-Personas          # roster as JSON array
python src/orchestrator/personas.py get crypto-chad --group Unique-Personas  # one persona (add --body for the prompt)
```

Output is always ASCII-safe JSON (`ensure_ascii=True`), so it round-trips through
any console encoding and PowerShell's `ConvertFrom-Json`. `list` emits
`{slug,name,group,tags,summary,path}` per card; `get` emits one such object (exit
code `1` + `{"status":"not_found"}` on a miss); `import` emits
`{"imported","skipped"}`.

---

## Storage & sync

Personas live in a `personas` table in `db/chat.db` — the same WAL SQLite file
that carries the conversation message bus:

```sql
CREATE TABLE personas (
    "group" TEXT NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL,
    tags TEXT, category TEXT, subcategory TEXT, body TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY ("group", slug)
);
```

(`group` is a SQL reserved word, so every query double-quotes it.) The schema is
duplicated in the `SCHEMA` constants of `agent_chat_mcp.py`, `web_ui.py`, and
`orchestrator/seeding.py`, plus a standalone `_PERSONA_DDL` in `personas.py` so
the registry works against a fresh DB before any server has booted.

Because the table is in `chat.db`, the [Fly db-sync sidecar](db-sync.md) mirrors
it **bidirectionally**, exactly like conversations — the only structural
difference is that personas key on a composite `(group, slug)` instead of an int
`id`. On the wire the key is serialized as `group␟slug` (using ASCII Unit
Separator `0x1F`, absent from group names and `[a-z0-9-]` slugs). Edits made on
the hosted UI flow back to your local DB; edits made locally push up. Conflict
resolution is last-write-wins by `updated_at`. See [db-sync.md](db-sync.md) for
the watermark mechanics.

---

## The MCP tools

Both are read-only and idempotent, mirroring `get_kickoff`'s annotation shape.

### `list_personas(group=None)`

Lightweight roster — **no body**, to keep it cheap to call. Optional `group`
filter (`"Unique-Personas"`, `"Debate-Hosts"`, or any curated-subset folder).
`group=None` returns the canonical roster (`Unique-Personas` + `Debate-Hosts`).

```json
{
  "count": 29,
  "group": null,
  "personas": [
    {"slug": "crypto-chad", "name": "Crypto Chad", "group": "Unique-Personas",
     "tags": ["crypto", "bro", "libertarian", "podcast"],
     "summary": "Act as a hyper-pumped crypto bro who believes blockchain ..."}
  ]
}
```

### `get_persona(name)`

Full card by slug or display name. The `instructions` field is the character's
full prompt body.

```json
{
  "status": "ok",
  "slug": "crypto-chad",
  "name": "Crypto Chad",
  "group": "Unique-Personas",
  "tags": ["crypto", "bro", "libertarian", "podcast"],
  "category": "System_Prompts",
  "subcategory": "Podcast_Personalities",
  "summary": "Act as a hyper-pumped crypto bro ...",
  "instructions": "# Crypto Chad\n\n## Purpose\n..."
}
```

On a miss it returns the query plus every available slug so the caller can
correct itself:

```json
{"status": "not_found", "query": "crpto chad", "available": ["ai-apostle-alex", "..."]}
```

---

## How an agent uses them

Inside a [`debate-mode`](../../skills/debate-mode/SKILL.md) session:

1. `list_personas()` → skim the roster (or `list_personas(group="Debate-Hosts")`
   if moderating).
2. `get_persona("crypto-chad")` → read the returned `instructions`.
3. Stay in character for the rest of the conversation, layered on top of the
   debate moves. A persona is a delivery style — it does **not** excuse hedging,
   strawmanning, or refusing to concede.

When the operator pre-assigned a persona at launch (via `scripts/debate.ps1`),
the agent already has it — these tools are for discovering or adopting one
mid-setup.

---

## Where to look for what

| You want… | Look at |
|:---|:---|
| The live persona data | the `personas` table in `db/chat.db` |
| The seed cards (one-time import + git snapshot) | `agents/Debate-Agents/{Unique-Personas,Debate-Hosts}/*.md` |
| The registry / write layer / importer | `src/orchestrator/personas.py` |
| The MCP tool definitions | `list_personas` / `get_persona` in `src/agent_chat_mcp.py` |
| How personas sync local↔hosted | [`docs/App/db-sync.md`](db-sync.md) |
| Manage personas in a browser | `GET /personas` (see [`web-ui.md`](web-ui.md)) |
| Random per-CLI assignment at launch | [`scripts/debate.ps1`](../Guides/auto-debate.md) |
| How to argue in character | [`skills/debate-mode/SKILL.md`](../../skills/debate-mode/SKILL.md) |
