# Personas

The debate **personality cards** under [`agents/Debate-Agents/`](../../agents/Debate-Agents/)
turned into a typed, queryable registry plus two read-only MCP tools, so an
agent can browse the roster and adopt a character **itself** — no operator step
and no per-CLI file copying.

Pairs with [`scripts/debate.ps1`](../Guides/auto-debate.md) (which injects a
*random* persona per CLI at launch) and the [`debate-mode`](../../skills/debate-mode/SKILL.md)
skill (which teaches how to argue *in* character).

---

## The cards

Each card is a Markdown file with YAML frontmatter:

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

Two groups live side by side:

| Group | Folder | What's in it |
|:---|:---|:---|
| `All` | `agents/Debate-Agents/All/` | The debater roster — 25 exaggerated characters (Crypto Chad, Flat-Earth Fred, Pastor Cole, Vegan Vanessa, …). |
| `Hosts` | `agents/Debate-Agents/Hosts/` | Moderator / host personalities (Jaxx Reign, Dr. Penelope Hartwell, …). |

Not every card uses the same `##` sections — the longer hand-authored cards
omit `## Purpose` / `## Instructions`. The registry never relies on section
structure: **everything after the frontmatter is the persona prompt**, and the
one-line `summary` is best-effort (the `## Purpose` paragraph if present, else
the first prose paragraph).

---

## The registry — `src/orchestrator/personas.py`

Stdlib-only (a hand-rolled frontmatter parser — no PyYAML in the pinned deps).
It is the single source of truth for "what personalities exist and what is each
one's prompt."

```python
from orchestrator import personas

personas.list_personas()              # every card, sorted by display name
personas.list_personas(group="Hosts") # just the moderators
personas.get_persona("crypto-chad")   # by slug
personas.get_persona("Crypto Chad")   # …or display name (same Persona)
```

- `Persona` is a frozen dataclass: `slug`, `name`, `group`, `tags`, `category`,
  `subcategory`, `summary`, `body`, `path`.
- `get_persona()` matching is **case-, punctuation-, and emoji-insensitive**, so
  `crypto-chad`, `Crypto Chad`, and `🤖 Crypto Chad` all resolve to the same
  card. Returns `None` on no match.
- Missing folders are skipped silently — the registry degrades to whatever is on
  disk.

### Non-Python callers — the JSON CLI

`scripts/debate.ps1` doesn't re-scan the folder; it shells out to the registry's
JSON CLI to cast its debaters:

```powershell
python src/orchestrator/personas.py list --group All          # roster as JSON array
python src/orchestrator/personas.py get crypto-chad --group All  # one persona (add --body for the prompt)
```

Output is always ASCII-safe JSON (`ensure_ascii=True`), so it round-trips through
any console encoding and PowerShell's `ConvertFrom-Json`. `list` emits
`{slug,name,group,tags,summary,path}` per card; `get` emits one such object (exit
code `1` + `{"status":"not_found"}` on a miss). The remaining future call site —
the `/orchestrate` web picker — should import the registry directly.

---

## The MCP tools

Both are read-only and idempotent, mirroring `get_kickoff`'s annotation shape.

### `list_personas(group=None)`

Lightweight roster — **no body**, to keep it cheap to call. Optional `group`
filter (`"All"` or `"Hosts"`).

```json
{
  "count": 29,
  "group": null,
  "personas": [
    {"slug": "crypto-chad", "name": "Crypto Chad", "group": "All",
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
  "group": "All",
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

1. `list_personas()` → skim the roster (or `list_personas(group="Hosts")` if
   moderating).
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
| The persona cards themselves | `agents/Debate-Agents/{All,Hosts}/*.md` |
| The registry / parser | `src/orchestrator/personas.py` |
| The MCP tool definitions | `list_personas` / `get_persona` in `src/agent_chat_mcp.py` |
| Random per-CLI assignment at launch | [`scripts/debate.ps1`](../Guides/auto-debate.md) |
| How to argue in character | [`skills/debate-mode/SKILL.md`](../../skills/debate-mode/SKILL.md) |
