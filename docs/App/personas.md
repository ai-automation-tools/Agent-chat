# Personas

The debate **personality roster** is a typed, queryable registry plus two
read-only MCP tools, so an agent can browse the cast and adopt a character
**itself** — no operator step and no per-CLI file copying.

> [!IMPORTANT]
> **Storage moved to the database.** Personas now live in a `personas` table
> inside the shared SQLite DB (`db/chat.db`), and the optional mirror sidecar
> (`scripts/db_sync.py`) syncs that table bidirectionally — so add/edit/delete
> works and persists on both the local box **and** a self-hosted mirror.
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

> [!NOTE]
> **Avatars.** Each persona has an avatar image, shown wherever the web UI names
> a persona (personas page, cast panel, message headers, homepage
> roster/featured). Resolution is *uploaded image* → *shipped file* → *default
> silhouette*; see [Avatars](#avatars) below and
> [`web-ui.md` → Persona avatars](web-ui.md#persona-avatars-webavatars).

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

> [!IMPORTANT]
> **There is no fixed group list, and `PREFERRED_GROUPS` is only a sort hint.**
> Groups are whatever `SELECT DISTINCT "group" FROM personas` returns. Ask
> `discover_groups()` or open `/personas` — don't trust any list written down
> here, including this one.

Two kinds of group exist, and the distinction is load-bearing:

| Kind | Behaviour |
|:---|:---|
| **Castable** (everything else) | Eligible for random debate casting. Historically `Unique-Personas` (the `DEFAULT_DEBATER_GROUP`) + `Debate-Hosts`; in practice the roster has been reorganised into per-category groups — `Celebrities`, `Comedians`, `Fictional Characters`, `Scientists`, `Athletes`, `Musicians`, `Podcasters`, `Political Figures`, `Podcast Personalities`, `Everyday Archetypes` — and **`Unique-Personas` now holds zero rows**. |
| **Reserved** (`personas.RESERVED_GROUPS`) | Real, browsable, editable personas that are **never** drawn as random debaters. Currently `AI-Models` and `Practitioners`. |

### The host roster

**Every conversation type casts from the same personas.** A debate's moderator
and a podcast's host are drawn from `Debate-Hosts`, and debaters and guests are
drawn from the same castable roster as each other — there is no podcast-only
persona set, because the personalities that make good moderators make good
interviewers and one set of cards is enough to maintain.

The group is named per type by `ConvType.lead_group` in
[`orchestrator/conv_types.py`](../../src/orchestrator/conv_types.py) — every
type currently points at `Debate-Hosts`, but the field stays per-type so a
future format could have its own roster by changing one line in that table.

It only affects the **random** pick (🎲 random host on `/orchestrate`); an
explicit persona is resolved across every group, as always. A lead group holding
zero rows is **not** an error — the draw falls back to
`list_debater_personas()`, the whole castable roster.

> [!WARNING]
> Because `DEFAULT_DEBATER_GROUP` is empty, every random-cast path falls through
> to "all personas". That's why selection **must** go through
> `list_debater_personas()`, which excludes `RESERVED_GROUPS` — otherwise a
> random debate fields "Claude Code" against Gordon Ramsay. Callers:
> `POST /api/orchestrate` (debater + moderator draws) and `debate.ps1` via the
> JSON CLI's `list --castable`. `list_personas(None)` still means *literally
> everything* and is fine for browsing/counting; an explicit group is always
> honoured as asked.

### `Practitioners` — the work-role cards

Eleven cards for **collaborations** rather than debates: Full-Stack Developer,
Systems Architect, Product Designer, Product Strategist, Idea Generator, Code
Reviewer, Critical Thinker, Researcher, Security Researcher, Business Analyst,
Creative Writer. A debate wants Gordon Ramsay; a collaboration wants someone who
has shipped a migration.

Each is written to pair with a `collaborate` sub-type (`src/presets.py`) — the
sub-type decides what the room hands back, the card decides who is arguing about
it. The mapping and the full rationale live in the group's own seed folder,
[`agents/Debate-Agents/Practitioners/README.md`](../../agents/Debate-Agents/Practitioners/README.md).

Two things make these different from the entertainment roster, and both are
deliberate:

- **Every card names who it clashes with.** A collaboration's two failure modes
  are parallel monologues and agreement that adds nothing (see
  `skills/collaborate-mode`). Writing the friction into the cards is the
  cheapest defence against the second one.
- **Every card says how it behaves in a turn-based room** — contribute, don't
  chair; bring file paths, not impressions. The sources they are adapted from
  are Claude Code *subagent definitions*, which describe a tool-using worker;
  dropped into a conversation unedited, one of them will narrate its workflow
  instead of arguing its corner.

**Reserved**, for the same reason `AI-Models` is: a random debate cast drawing
"Full-Stack Developer" against a comedian is nonsense. Every explicit path still
sees them — the `/orchestrate` Cast panel lists them (it calls
`list_personas(None)`), and `-Group Practitioners` is honoured.

> [!NOTE]
> Random casting is **not type-aware yet**, so a random *collaboration* still
> draws from the entertainment roster. Making the random pool follow `conv_type`
> is its own change; reserving this group doesn't make that worse, it just
> doesn't fix it.

### `AI-Models` — the default Cast

One card per supported CLI (`preflight.SUPPORTED_CLIS`: `claude-code`, `codex`,
`gemini`, `antigravity`, `opencode`), **slugged with the agent id** so a
lookup is just `get_persona(agent_id, group="AI-Models")`. Defined in
[`src/orchestrator/model_personas.py`](../../src/orchestrator/model_personas.py)
and created on web-UI boot by `ensure_model_personas()` — **create-if-missing**,
so edits made on `/personas` survive a restart, and deleting a card restores the
stock version on the next boot.

They exist to give the reader page a Cast panel for conversations that recorded
no `participant_personas` — the ones seeded before the persona system, plus any
plain non-debate run. `_effective_cast()` in `web/render/conversations.py` merges
them in per participant and labels those rows `AI model`; a recorded persona
always wins. So conversation #16 (`gemini` + `codex`) reads as **Gemini vs
Codex** instead of showing nothing.

Card bodies are **original descriptions** of each CLI's publicly-observable
behaviour — deliberately not copies of any vendor's system prompt.

The matching seed cards live under `agents/Debate-Agents/<folder>/` as a frozen
git snapshot, and its folder names have drifted from the DB group strings — they
only line up the *first* time you import (see the warning under
[Seeding](#seeding-the-db-from-the-cards--import)). AI-Models has no seed folder:
it's defined in code.

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

personas.list_personas()                        # EVERY persona, all groups, sorted by group then name
personas.list_personas(group="Debate-Hosts")    # just the moderators
personas.list_debater_personas()                # every CASTABLE persona (all groups minus RESERVED_GROUPS)
personas.list_debater_personas("AI-Models")     # explicit group is honoured as asked
personas.get_persona("crypto-chad")             # by slug
personas.get_persona("Crypto Chad")             # …or display name (same Persona)
personas.get_persona("codex", group=personas.AI_MODELS_GROUP)  # a CLI's default card

# write layer (used by the /personas web UI — works local + hosted)
personas.create_persona(name="New Bot", body="…", group="Unique-Personas", tags=["x"])
personas.update_persona("new-bot", body="…", group="Debate-Hosts")  # group= moves it
personas.delete_persona("new-bot")
personas.import_persona_card(text, group="Unique-Personas", filename="new-bot.md",
                             overwrite=False)  # one raw .md card → a DB row

# avatars — see the Avatars section below
personas.set_avatar("new-bot", b64_png)
personas.get_avatar("new-bot")                  # ("image/png", b"\x89PNG…") | None
```

- `Persona` is a frozen dataclass: `slug`, `name`, `group`, `tags`, `category`,
  `subcategory`, `summary`, `body`, `avatar_mime`, `path` (plus a `has_avatar`
  property). The avatar **bytes** are deliberately not on it — see
  [Avatars](#avatars). `summary` and `path` are **derived**
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
python src/orchestrator/personas.py list --castable          # THE random-cast roster: all groups minus reserved
python src/orchestrator/personas.py list --all-groups        # literally everything, AI-Models included
python src/orchestrator/personas.py list --group Celebrities  # one group as a JSON array
python src/orchestrator/personas.py get crypto-chad --all-groups  # one persona (add --body for the prompt)
```

`debate.ps1` uses `--castable` when no `-Group` is passed, which is what keeps the
reserved `AI-Models` cards out of a random cast. Reach for `--all-groups` only
when you genuinely mean *every* persona.

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
    avatar_mime TEXT, avatar_data TEXT,          -- uploaded avatar (base64)
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY ("group", slug)
);
```

(`group` is a SQL reserved word, so every query double-quotes it.) The schema is
duplicated in the `SCHEMA` constants of `agent_chat_mcp.py`, `web_ui.py`, and
`orchestrator/seeding.py`, plus a standalone `_PERSONA_DDL` in `personas.py` so
the registry works against a fresh DB before any server has booted.

Because the table is in `chat.db`, the optional db-sync sidecar mirrors
it **bidirectionally**, exactly like conversations — the only structural
difference is that personas key on a composite `(group, slug)` instead of an int
`id`. On the wire the key is serialized as `group␟slug` (using ASCII Unit
Separator `0x1F`, absent from group names and `[a-z0-9-]` slugs). Edits made on
the hosted UI flow back to your local DB; edits made locally push up. Conflict
resolution is last-write-wins by `updated_at`; the watermark mechanics live in
`scripts/db_sync.py`.

> [!IMPORTANT]
> The sidecar's `PERSONA_COLUMNS` (in `scripts/db_sync.py`) must match
> `_PERSONA_COLUMNS` in `src/web/db.py` — **a column the sidecar doesn't carry
> never reaches the mirror.** `tests/test_persona_avatars.py` pins the two lists
> together. And because the mirror's `INSERT` names every column, a sync that
> includes a new one **fails until the mirror is redeployed** — deploy the web app
> before (or with) the sidecar restart.

### Two places a persona doesn't come from the registry

**An [AgentBattleground](battleground.md#custom-personas) arena** can be cast
with a card the operator types into the extension panel
(`✎ custom instructions…`) rather than picked from this roster. It writes
**nothing** to the `personas` table: arenas already snapshot `persona_slug` /
`persona_name` / `persona_body` onto their own row, so a one-off card just fills
those columns with `persona_slug` left `NULL`.

**A `/orchestrate` seat set to `custom`** does the same thing with a *file*. The
form's per-row **custom** button reads a persona card in the browser and sends it
as `persona_custom[cli] = {"filename", "text"}` alongside `personas[cli] =
"__custom__"`; `_custom_persona_entry()` parses it with the same
`parse_card_text()` the registry importer uses and puts the result straight into
`participant_personas` — with the **slug left empty**. Nothing is written to the
`personas` table, so a one-off card never reaches `/personas` or the hosted
mirror. The [importer](#seeding-the-db-from-the-cards--import) is where a card
goes to be *saved*; this is where one goes to be *used once*.

The empty slug is the load-bearing part, and every consumer already handles it:
`export.persona_doc()` falls back to the agent id for the name and
`bundle_files()` drops the `-<slug>` half of the filename (so the bundle gets
`personas/claude-code.md`, the same shape a no-persona run exports — **no
export-contract change**), `media_prompts` strips a blank slug, and the reader
resolves the avatar from the agent id. Writing the file stem there instead would
name an export file after a card nobody can look up.

So the roster stays the source of truth for everything that *browses* personas —
`list_personas`, `/personas`, random casting, the homepage — while an arena or a
custom-cast seat may legitimately name a character that has no row here. If
you're reading a `persona_name` off either, don't assume `get_persona()` can
resolve it.

---

## Avatars

A persona's picture is resolved in three steps — **uploaded image** → **shipped
file** → **default silhouette** — and served at `GET /avatars/{slug}`. Only the
first is new-ish; the other two are the original convention (see
[`web-ui.md` → Persona avatars](web-ui.md#persona-avatars-webavatars)).

**Uploads live on the persona row** (`avatar_mime` + base64 `avatar_data`), not
in `images/AgentChat-Avatars/`. That's deliberate: the `personas` table is
synced, so an avatar uploaded locally reaches the hosted mirror on the next tick
**with no redeploy**, and one uploaded on the mirror survives the next deploy — a
file written into the image's tree would do neither. Shipped art still needs a
commit + redeploy, as before.

Two ways to attach one, both on `/personas`:

| Where | How |
|:---|:---|
| **Editor** | Select a persona (or **+ New**) → **Choose image…** in the Avatar row → **Save**. **Remove** drops an uploaded image and falls back down the chain. |
| **Import** | Include the image in the upload next to its card — `crypto-chad.md` + `crypto-chad.png`, or a zip of either shape (flat, or a folder per persona). Instructions and art land together. |

Registry API:

```python
personas.create_persona(name="New Bot", body="…", avatar=b64)   # validated before the INSERT
personas.update_persona("new-bot", avatar=b64)                  # replace
personas.update_persona("new-bot", clear_avatar=True)           # remove
personas.set_avatar("new-bot", b64); personas.clear_avatar("new-bot")
personas.get_avatar("new-bot")     # ("image/png", b"\x89PNG…") | None
personas.avatar_index()            # {slug: updated_at} for personas that have one
```

- **The type comes from the bytes**, never from what the uploader claimed:
  `normalize_avatar()` sniffs the magic bytes and accepts PNG / JPEG / GIF / WebP
  only, up to `AVATAR_MAX_BYTES` (2 MB decoded). **SVG is refused** — it's
  script-capable markup, and these bytes are served back from the app's own
  origin. The browser rasterizes an SVG to PNG before upload, so picking one still
  works.
- `Persona.avatar_mime` / `.has_avatar` say *whether* a persona has an upload;
  the bytes are **never** on the dataclass and `list_personas()` doesn't select
  them, so listing the roster stays cheap.
- An avatar **survives an edit**: `update_persona()` with neither `avatar` nor
  `clear_avatar` leaves it alone, and both importers carry the existing image
  across an overwrite rather than blanking it.

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

### Persona voice beats the house style rules

Since 2026-08-01 every agent also receives a distilled
[`humanizer`](../../skills/humanizer/SKILL.md) block — in the rendered
kickoff for conversations, and as `_ARENA_RULES` rule 7 for arenas — telling it
to strip the patterns that mark text as AI-written.

**The persona card wins.** The block says so at every site where it ships, and
it matters: applied naively, advice like "use *I*, let some mess in, have
opinions" pulls every card toward the same chatty conversational register. Run
that across a 35-persona roster and every debater starts sounding alike, which
is its own kind of slop and defeats the point of having a roster.

So the rules only remove *machine tells* — puffery vocabulary, reflexive
three-item lists, `-ing` clauses bolted on to fake depth, uniform sentence
length. A terse persona stays terse, a crude one stays crude, and a persona
whose whole voice is grandiose rhetoric keeps it. If you're authoring a card
and worried the style rules will sand it down, they shouldn't — but say the
voice explicitly in the body (see [Card format standard](#card-format-standard))
rather than relying on the name to carry it.

---

## Where to look for what

| You want… | Look at |
|:---|:---|
| The live persona data | the `personas` table in `db/chat.db` |
| The seed cards (one-time import + git snapshot) | `agents/Debate-Agents/{Unique-Personas,Debate-Hosts}/*.md` |
| The registry / write layer / importer | `src/orchestrator/personas.py` |
| The single-card import helper | `import_persona_card()` / `parse_card_text()` in `src/orchestrator/personas.py` |
| The MCP tool definitions | `list_personas` / `get_persona` in `src/agent_chat_mcp.py` |
| How personas sync local↔mirror | `PERSONA_COLUMNS` / `apply_pull()` in [`scripts/db_sync.py`](../../scripts/db_sync.py) |
| Manage personas in a browser (add/edit, inline group creation, tag chips, Markdown import) | `GET /personas` (see [`web-ui.md`](web-ui.md)) |
| Random per-CLI assignment at launch | [`scripts/debate.ps1`](../Guides/auto-debate.md) |
| How to argue in character | [`skills/debate-mode/SKILL.md`](../../skills/debate-mode/SKILL.md) |
