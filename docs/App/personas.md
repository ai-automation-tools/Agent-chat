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
> **The seed folders' names and layout no longer affect anything at runtime** —
> renaming a folder or adding new ones changes nothing until someone *re-runs the
> importer*, which would create **new** DB groups alongside the existing rows (see
> [Seeding](#seeding-the-db-from-the-cards--import)). The canonical group name
> `Unique-Personas` is a **string in the DB** (and in `personas.py` /
> `debate.ps1`), independent of whatever the seed folder happens to be called on
> disk today. See [Storage & sync](#storage--sync) below.

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

Two canonical groups make up the default roster (these are **DB group strings**,
listed in `PREFERRED_GROUPS`):

| Group (DB string) | What's in it |
|:---|:---|
| `Unique-Personas` | The debater roster — ~25 exaggerated characters (Crypto Chad, Flat-Earth Fred, Pastor Cole, Vegan Vanessa, …). The `-Group` default for `debate.ps1`. |
| `Debate-Hosts` | Moderator / host personalities (4 cards — Jaxx Reign, Dr. Penelope Hartwell, …). |

The matching seed cards live under `agents/Debate-Agents/<folder>/` as a frozen
git snapshot. The on-disk folder for the debater roster has since been renamed to
`Random-Debate-Personas/`, and additional un-imported category folders exist
(`Actors/`, `Celebrities/`, `Comedians/`, `Fictional-Characters/`, `Politics/`,
`Sports/`, …) — **but none of that has touched the live DB**, where the roster is
still the single group `Unique-Personas`. The folder name and the DB group string
only line up the *first* time you import; after that they drift independently (see
the warning under [Seeding](#seeding-the-db-from-the-cards--import)).

`group` is just a label on the row — once imported, you can create a persona in
**any** group from the web UI (including a brand-new group, created inline at
save time — see [`web-ui.md`](web-ui.md)), and groups are discovered dynamically
from the DB (see `discover_groups()` below). At seed time, any subfolder of
`agents/Debate-Agents/` becomes a group, so a new folder of `*.md` cards imports
with no code change.

Cards are loose about structure. Not every card uses the same `##` sections — the
longer hand-authored cards omit `## Purpose` / `## Instructions`, and some newer
cards **omit the YAML frontmatter entirely** (just a `# Heading` + free-form
Markdown body). The registry never relies on section structure: **everything
after the frontmatter is the persona prompt** (the whole file when there's no
frontmatter); the display **name** is the frontmatter `title`, else the first
`# Heading`, else the slug; and the one-line `summary` is best-effort (the
`## Purpose` paragraph if present, else the first prose paragraph).

The registry *tolerates* that looseness, but for **new** cards there's a
canonical format — see below.

---

## Card format standard

The template lives at
[`agents/Debate-Agent-Templates/Agent-Personality.md`](../../agents/Debate-Agent-Templates/Agent-Personality.md)
(with a [`README`](../../agents/Debate-Agent-Templates/README.md) beside it).
Point an LLM at it for generation; it's also exactly what the importer parses
cleanly.

Every card has **two consumers**, and the format serves both:

1. **The parser** reads *only the YAML frontmatter* for `tags` / `category` /
   `subcategory`, and the `## Purpose` line for the roster `summary`. It does
   **not** read tags or category from the body — an inline `**Tags:** #x #y` line
   is decorative text the parser never sees.
2. **The model** reads the *entire body* (everything after the frontmatter) as
   its persona prompt — what `get_persona().instructions` returns and what
   `debate.ps1` injects at launch.

Because of (2), the body is **freeform**: the `## Persona` bullet menu (Voice,
Debate style, You believe, Intelligence, Strengths, Weaknesses, Decision
framework, Favorite topics, You avoid) is a *starter set*, not a schema — add,
drop, or rename traits per persona. Only the frontmatter and the `## Purpose`
line are machine-read.

Two rules follow from that:

- **Frontmatter must be the very first bytes of the file.** The frontmatter regex
  anchors at offset 0, so *anything* before the opening `---` (even a comment)
  makes the parser treat the whole file as body and silently drop `title` /
  `tags` / `category` / `summary`. This is the single most common way a card
  imports with empty metadata.
- **Write the body in the second person, as an instruction** (*"You are X. You
  believe… You speak…"*), not a third-person bio. The model adopts what it's told
  to be; it narrates what it's merely described as.

A worked example (compare to the looser trading-card cards under `Politics/`,
`Celebrities/`, … which import with **empty** tags/category/summary):

```markdown
---
title: "Machiavelli"
tags:
- political
- historical
- pragmatic
category: Debaters
---

# Machiavelli

## Purpose
A cold political realist who cares only about leverage and power, never morality.

## Persona
You are Machiavelli. You care nothing for what is morally right or wrong — only
for what is effective at maintaining stability, power, and control. You speak in
terms of leverage, optics, and human fallibility.

- **Voice:** cold, polite, calculating; never warm.
- **You believe:** power over morality; incentives over intentions.
- **Strengths:** game theory, leverage, clear-eyed reading of systemic corruption.
- **Weaknesses:** no moral appeal; the audience may distrust your motives.
- **Decision framework:** realpolitik — maximize control, reduce vulnerability.

## Example lines
- "It is much safer to be feared than loved — and the same applies to this fiscal policy."

## Stay in character
Never break character. The persona is a delivery style; it does not excuse hedging.
```

Frontmatter details: `tags` must be a **block list** (`- item` lines) — inline
`tags: [a, b]` flow syntax is **not** supported by the hand-rolled parser, and
neither are YAML `#` comments (a trailing `category: X  # note` imports the
comment as part of the value). The filename stem becomes the **slug** (stable
id); `title` is just the display name.

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
personas.import_persona_card(text, group="Unique-Personas", filename="new-bot.md",
                             overwrite=False)  # one raw .md card → a DB row
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
- `import_persona_card(text, *, group, filename=None, overwrite=False)` creates
  one row from a single **raw Markdown card** (frontmatter + body). The slug comes
  from `filename`'s stem when given, else the frontmatter title; `overwrite=True`
  replaces a colliding `(group, slug)` instead of raising. This backs the
  `/personas` "Import personas from Markdown files" tool and the
  `POST /api/personas/import` endpoint. Card parsing is shared with the on-disk
  loader via the `parse_card_text()` helper, so an imported card and a seeded card
  are parsed identically.
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

> [!WARNING]
> Re-running `import` reads the **current** folder names. Because the debater
> roster folder was renamed to `Random-Debate-Personas/` and new category folders
> were added after the original seed, a fresh `import` would create those as
> **new** DB groups (`Random-Debate-Personas`, `Celebrities`, `Sports`, …)
> *alongside* the existing `Unique-Personas` rows — it does not rename or replace
> the live group. If you want the new cards in the live roster under the existing
> group name, import them into `Unique-Personas` from the `/personas` Markdown-import
> tool (which lets you pick the target group) rather than bulk-importing the folders.

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
| The single-card import helper | `import_persona_card()` / `parse_card_text()` in `src/orchestrator/personas.py` |
| The MCP tool definitions | `list_personas` / `get_persona` in `src/agent_chat_mcp.py` |
| How personas sync local↔hosted | [`docs/App/db-sync.md`](db-sync.md) |
| Manage personas in a browser (add/edit, inline group creation, tag chips, Markdown import) | `GET /personas` (see [`web-ui.md`](web-ui.md)) |
| Random per-CLI assignment at launch | [`scripts/debate.ps1`](../Guides/auto-debate.md) |
| How to argue in character | [`skills/debate-mode/SKILL.md`](../../skills/debate-mode/SKILL.md) |
