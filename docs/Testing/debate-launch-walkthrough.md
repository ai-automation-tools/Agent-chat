# Debate launch — technical walkthrough

A step-by-step trace of what actually happens when you run `scripts/debate.ps1`,
written from the live test that produced **conversation #23**
(*"Will lab-grown organs become common within 20 years?"* — claude-code as
**Boomer Bill** vs. antigravity as **Alien Andy**).

This is the "what really runs, in what order, touching which files" reference. For
the operator-facing recipe see [`../Guides/auto-debate.md`](../Guides/auto-debate.md);
for the per-CLI MCP wiring see [`../CLI-MCP-Config/`](../CLI-MCP-Config/).

> **Command under test**
> ```powershell
> .\scripts\debate.ps1 -Agents 2 -SkipPermissions
> ```

---

## The 30-second mental model

There is **no central engine** driving the debate. `debate.ps1` is a one-shot
*launcher*: it picks a topic and personas, writes a single conversation row to a
shared SQLite file, drops a prompt file per agent, and opens one terminal window
per CLI. After that, the script exits. The "conversation" is then an emergent
property of N independent CLI processes each polling the **same SQLite database**
through the `agent_chat` MCP server. SQLite (in WAL mode) is the entire message
bus — no daemon, no socket, no port.

```
debate.ps1  ──seeds──►  db/chat.db (conversations row, status='active')
     │
     ├─ writes db/launch/conv23-claude-code.txt   (persona + instructions)
     ├─ writes db/launch/conv23-antigravity.txt
     │
     ├─ spawns pwsh window 1 ─► cd claude-code_agent1 ─► `claude` ─┐
     └─ spawns pwsh window 2 ─► cd antigravity_agent1 ─► `agy`   ──┤
                                                                   ▼
                          each CLI loads its own .mcp.json / mcp_config.json,
                          starts an agent_chat MCP server (run-mcp-server.ps1),
                          and the two servers read/write the SAME db/chat.db.
```

---

## Stage-by-stage trace

### 1. Topic selection — `docs/Chat-Topics/Topics.md`

With no `-Topic` supplied, the script parses `Topics.md`, which is a numbered list
where each topic may carry a `- Debaters: N` sub-line:

```
12. Will lab-grown organs become common within 20 years?
    - Debaters: 2
```

- It builds the full topic list, skips any line already bearing the **✅** used-marker,
  and picks one unused topic at random (`Get-Random`).
- In the live run: *"random of 99 unused / 100 total"* → chose the lab-grown organs topic.
- The topic's `- Debaters: 2` line set the count; `-Agents 2` would have overridden
  it anyway (precedence: `-Agents` > topic line > `-DefaultAgents`).

### 2. Debater count resolution

`$count = -Agents ?? topic "Debaters:" ?? -DefaultAgents`, then bounds-checked to
`2..3` and against the number of registered CLIs. Here: **2**.

### 3. Persona selection — `src/orchestrator/personas.py`

The script does **not** scan the persona cards itself. It shells out to the shared
Python registry and consumes JSON:

```powershell
$all = Get-Personas list --group Unique-Personas     # -> .\.venv\Scripts\python.exe src\orchestrator\personas.py list --group Unique-Personas
$selected = $all | Get-Random -Count $count
```

Each returned persona carries `.slug / .name / .group / .tags / .summary / .path`
(`.path` is synthesized, not read — the data comes from the DB). The registry is
the single source of truth — it reads the `personas` table in `db/chat.db` (not
the card files) and does the display-name derivation, keeping `debate.ps1`
ignorant of the storage layer. Live draw: **Boomer Bill** and **Alien Andy**.
(With `-Personalities` you force specific cards instead, each resolved through the
same registry by slug or display name.)

### 4. Persona → CLI mapping

CLI preference order is fixed by the `$Clis` ordered hashtable in `debate.ps1`:

| Order | CLI key       | Working dir                       | Exe   | Initial-prompt flag | Skip-perms flag                  |
|-------|---------------|-----------------------------------|-------|---------------------|----------------------------------|
| 1     | `claude-code` | `agents\CLIs\claude-code_agent1`  | `claude` | `{0}`            | `--dangerously-skip-permissions` |
| 2     | `antigravity` | `agents\CLIs\antigravity_agent1`  | `agy` | `-i {0}`            | `--dangerously-skip-permissions` |
| 3     | `codex`       | `agents\CLIs\codex_agent1`        | `codex` | `{0}`             | `--yolo`                         |

The first `$count` CLIs are used, and **the first is the `--first` speaker**. So for
2 agents: `claude-code` (first) + `antigravity`. Personas are zipped onto CLIs by
index → claude-code = Boomer Bill, antigravity = Alien Andy.

> Gemini is intentionally **absent** from this launch table — it's the deprecated
> predecessor to Antigravity. It still exists in `preflight.py`'s `SUPPORTED_CLIS`
> as a fallback, but auto-launch uses `antigravity` (`agy`).

### 5. Seeding — `scripts/start.ps1` → `seed_conversation()`

The script invokes:

```powershell
start.ps1 --preset debate --topic "<topic>" --participants claude-code,antigravity --first claude-code
```

`start.ps1` does two things:

1. **Ensures the DB-sync sidecar is up.** It scans for an existing
   `db_sync.py` process owned by the venv interpreter. If none, it launches one
   hidden (`Start-Process -WindowStyle Hidden`), tails `db/db_sync.log` inline for
   10s to surface startup failures, then detaches. In the live run: *"sidecar PID
   18268"*. The sidecar is optional — it mirrors new local rows up to a self-hosted
   read-only viewer, and a debate runs identically without it.
   (Forward `-ForceSidecar`, i.e. `start.ps1 -Force`, to kill + relaunch it.)
2. **Forwards the seed args** to `src/start_conversation.py`, which parses flags,
   applies the `debate` preset defaults (e.g. `max_turns=8`, tone), and calls the
   single source of truth: **`orchestrator.seeding.seed_conversation()`**.

`seed_conversation()` (in `src/orchestrator/seeding.py`):
- Validates (≥2 unique participants, valid `first`, `max_turns ≥ 1`).
- Opens `db/chat.db` with `PRAGMA journal_mode=WAL`, `foreign_keys=ON`,
  `isolation_level=None`, `timeout=10.0` — the same connection contract the MCP
  server and web UI use.
- Runs the idempotent `SCHEMA` + additive `_MIGRATIONS` (adds `preset` /
  `kickoff_template` columns if missing).
- Renders the **kickoff template** once: reads `prompts/Kickoff/kickoff.md`, extracts the
  ` ```text ` block containing `{{TOPIC}}`, substitutes `{{TOPIC}}` and
  `{{TONE_INSTRUCTION}}`, and (for ≥3 agents) rewrites "another AI agent" →
  "N-1 other AI agents". The rendered body is stored in
  `conversations.kickoff_template`.
- `INSERT`s one `conversations` row: `status='active'`, `mode='turns'`,
  `current_turn=<first speaker>`. **No messages are written** — the conversation
  starts empty.

The new id is echoed as `Started conversation #23`. Back in `debate.ps1`, a regex
(`Started conversation #(\d+)`) scrapes that id from the captured output. If it
can't, the script throws (a failed seed must not silently launch agents).

### 6. Topic check-off

Only after a successful seed, and only for a topic drawn from the file (not a
forced `-Topic`), the script appends the ✅ marker + a comment to the chosen line
in `Topics.md`:

```
12. Will lab-grown organs become common within 20 years? ✅ <!--used 2026-06-22 conv#23-->
```

This makes the run **idempotent across launches** — the same topic won't be
re-picked until you strip the marker.

### 7. Per-agent prompt files — `db/launch/`

For each agent the script writes `db/launch/conv23-<cli>.txt`. The file contains:

- A "stay fully in character, never break role, never mention being an AI in an
  MCP loop" framing.
- The **entire persona card body** (read from `selected[i].path`) between
  `=== YOUR PERSONA ===` markers.
- The agent's own id, the conversation number, the topic, and a 3-step instruction:
  call `get_kickoff()` once, follow its loop, argue in persona's voice, don't ask
  for confirmation between turns.

The CLI itself is handed only a **tiny static opening prompt** — it does *not*
receive the persona inline. That opening prompt is just:

> *"Read the file at '`db/launch/conv23-<cli>.txt`' in full and follow every
> instruction in it. Begin immediately; do not wait for further input."*

This is the key trick: the long, quote-laden persona content lives in a file, so
the command line stays trivially quotable regardless of persona length or content.

### 8. Window spawning

For each agent the script builds:

```powershell
Set-Location -LiteralPath '<repo>\agents\CLIs\<cli>_agent1'; <exe>[ <skip-flag>] <prompt-arg>
```

e.g. for antigravity with `-SkipPermissions`:

```powershell
Set-Location -LiteralPath '...\antigravity_agent1'; agy --dangerously-skip-permissions -i "Read the file at '...conv23-antigravity.txt'..."
```

That command string is UTF-16LE base64-encoded and launched via
`Start-Process pwsh -NoExit -EncodedCommand <b64>`. `-EncodedCommand` sidesteps all
`Start-Process` quote-mangling — the `cd` + launch travels intact regardless of
embedded quotes. **The `cd` matters**: each CLI discovers its MCP config *relative
to its working directory*, so launching from the agent's folder is what wires up
`agent_chat`.

The `--first` agent's window is opened first, then `Start-Sleep 1500ms`, then the
next — giving the first speaker a head start to queue its opening message before
the others begin polling.

### 9. Run record — `logs/debate-history.log`

A one-block record (timestamp, conv id, debater count, max-turns, topic, and the
persona→CLI→card-file mapping) is appended so the cast for any conversation is
greppable in one place. The message transcript itself lives only in the DB.

After this, **`debate.ps1` exits.** Everything below happens inside the spawned
CLI windows.

---

## What happens inside each CLI window (after the script exits)

Each window is now an independent CLI process. The lifecycle per agent:

1. **CLI boots and loads MCP config** from its working directory:
   - `claude-code` reads `agents/CLIs/claude-code_agent1/.mcp.json`
   - `antigravity` reads `agents/CLIs/antigravity_agent1/.agents/mcp_config.json`
2. **The `agent_chat` server starts.** Both configs register the *same* launcher:
   ```
   pwsh -NoProfile -File scripts/run-mcp-server.ps1 <agent-id>
   ```
   `run-mcp-server.ps1` resolves the venv interpreter and `src/agent_chat_mcp.py`
   relative to itself, then runs:
   ```
   .venv\Scripts\python.exe src\agent_chat_mcp.py --agent-id <agent-id>
   ```
   The DB defaults to `<repo>/db/chat.db` (override via `$AGENT_CHAT_DB`). So both
   agents' servers point at the one DB the script just seeded. `--agent-id` is the
   **only** thing distinguishing the two server processes — identity is config-only,
   there is no auth.
3. **The CLI reads the opening prompt**, opens `db/launch/conv23-<cli>.txt`, and
   follows it: calls `get_kickoff()` once.
4. **`get_kickoff()`** returns the rendered template stored on the conversation
   row (the loop + tone), which tells the agent to drive itself through
   `wait_for_turn` → `get_my_turn` → `send_message` until the conversation completes.

### The turn loop (enforced server-side in `agent_chat_mcp.py`)

The server — not the agents — enforces order and termination:

- **`wait_for_turn`** long-polls (default `timeout_seconds=60`): it returns when
  `conversations.current_turn` equals the caller's `--agent-id`, else blocks. A
  blocked `wait_for_turn` looks idle in the window but burns no tokens.
- **`get_my_turn`** returns the full message history + remaining turn budget.
- **`send_message`** writes the agent's row, then **rotates `current_turn`** to the
  next participant in `participants` order, and calls `maybe_complete()`.
- **`maybe_complete()`** flips `status='complete'` and records an `end_reason` when
  either stop condition is met:
  - any agent's message count reaches `max_turns` (per-agent cap), **or**
  - the most recent message carried a `signal` of `done` or `blocked`.

That rotation is why the live poll showed clean `claude-code ↔ antigravity`
alternation with `current_turn` flipping every `send_message`.

---

## Persona selection — deep dive

Stage 3 above is the one-line version ("the script asks the registry for personas
and picks N"). Here's the full mechanism, plus how to edit the roster.

### The two-layer design

Persona selection is split between a **launcher that decides *which* personas** and
a **registry that knows *what personas exist***. The launcher never touches storage
itself — it shells out to the registry and consumes JSON.

```
debate.ps1  ──shells out──►  personas.py  ──reads──►  personas table in db/chat.db
 (picks N)                   (the catalog)            (the runtime source of truth)
```

- `src/orchestrator/personas.py` = the catalog. Reads the `personas` table, emits
  JSON. Also backs the `list_personas` / `get_persona` MCP tools.
- `scripts/debate.ps1` = the chooser. Calls the catalog and selects.

The `.md` cards under `agents/Debate-Agents/` are a **one-time import seed** + git
snapshot, not the live source — they're loaded into the DB once via the importer
(`personas.py import`). Adding a persona for real means writing the DB (the
`/personas` web page, or `import_persona_card()`), **not** dropping a file in a
folder. See [`docs/App/personas.md`](../App/personas.md) for the storage model.

### How selection runs in `debate.ps1`

**Random (default)** — the script pulls the entire `Unique-Personas` group and picks N at random
with no repeats:

```powershell
$all = @(Get-Personas list --group Unique-Personas)      # -> python personas.py list --group Unique-Personas
$selected = $all | Get-Random -Count $count   # pick N, no duplicates
```

**Forced** — `-Personalities` resolves each entry through the registry's forgiving
matcher (slug, display name, or a trailing `.md` all work, ignoring case/punctuation/emoji):

```powershell
.\scripts\debate.ps1 -Personalities "crypto-chad","alien-andy"
```

The count must equal the resolved agent count or the script throws.

### What groups the registry returns

`personas.py` keys off the `"group"` column and a preferred-group list:

```python
PREFERRED_GROUPS = ("Unique-Personas", "Debate-Hosts")   # the canonical roster
```

| DB group | Role |
|---|---|
| `Unique-Personas` | The **default debater roster** — what `-Group Unique-Personas` (the default) draws from |
| `Debate-Hosts` | Moderator/host personalities — not normally used by `debate.ps1` for debaters |
| `<your-group>` | Any **other group** present in the table — discovered dynamically, selectable via `-Group <name>` |

> Groups are discovered from the **DB** (`personas.discover_groups()` →
> `SELECT DISTINCT "group" …`): `Unique-Personas` and `Debate-Hosts` always sort
> first, and any other group with at least one row is valid. `debate.ps1 -Group
> <name>` (default `Unique-Personas`) casts debaters from that group. With **no**
> `--group`, the registry returns the canonical roster (`Unique-Personas` +
> `Debate-Hosts`) so the default browse stays free of duplicate cards a curated
> subset would reintroduce. (Groups are *seeded* from the subfolders of
> `agents/Debate-Agents/` at import time, but at runtime they're just `"group"`
> values in the table.)

### Card anatomy

A seed card is one `.md` file. This is how the **importer** parses a card into a
DB row (the canonical format + the full rationale live in
[`docs/App/personas.md` → Card format standard](../App/personas.md#card-format-standard),
with a fillable template at `agents/Debate-Agent-Templates/Agent-Personality.md`).
The fields are derived like this:

| Field | Source |
|---|---|
| `slug` | the **filename stem** (`boomer-bill`) — the stable id |
| `name` | frontmatter `title:` with leading emoji stripped → first `# Heading` → slug |
| `tags` / `category` / `subcategory` | frontmatter (optional) |
| `body` | **everything after the frontmatter** — this whole block becomes the persona prompt injected into the agent's `db/launch/` file |
| `summary` | best-effort one-liner (`## Purpose` paragraph, else first prose paragraph) |

Example (`Unique-Personas/boomer-bill.md`):

```markdown
---
category: System_Prompts
subcategory: Podcast_Personalities
tags:
- conservative
- grumpy
- boomer
title: "🤖 Boomer Bill"
---

# Boomer Bill

## Purpose
Act as a cranky old-school boomer who thinks America peaked in 1978...

## Instructions
You are Boomer Bill ...
```

Frontmatter is parsed by a tiny hand-rolled YAML subset (no PyYAML dependency) —
only `key: value` scalars and a `tags:` block of `- item` lines are understood. The
`##` section names are irrelevant to the registry; only the split between frontmatter
and body matters.

### Editing recipes

The roster lives in the `personas` table, so edits go through the DB — **not** the
card folder. (Dropping a `.md` file in a folder does nothing until it's imported.)

**➕ Add a persona**
- *Easiest:* the **`/personas` web page** → "＋ Add a new persona" (writes the DB
  directly; works local + hosted). Pick or create the group inline.
- *From a card file:* author one to the [card format standard](../App/personas.md#card-format-standard)
  and import it — either the "⬆ Import personas from Markdown files" tool on
  `/personas`, or in Python `personas.import_persona_card(text, group="Unique-Personas")`.

Verify it registered:
```powershell
.\.venv\Scripts\python.exe src\orchestrator\personas.py get "your-slug" --group Unique-Personas
```

**➖ Remove a persona from the rotation**
- Use the **delete** affordance on the `/personas` page (or `personas.delete_persona(slug)`).
- *Temporarily bench it:* move the row to a group **not** in `PREFERRED_GROUPS`
  (e.g. update its group to `Bench`). Anything outside `Unique-Personas` /
  `Debate-Hosts` is invisible to the default cast but preserved.

**🎯 Pin a specific matchup (no editing needed)**
```powershell
.\scripts\debate.ps1 -Personalities "boomer-bill","new-age-nadia" -Agents 2 -DryRun
```

**🗂 Cast from a curated subgroup**
Put cards in their own group, then pass its name to `-Group`. Create the group by
adding personas to it on the `/personas` page (or import a folder of cards into a
target group). Then:
```powershell
.\scripts\debate.ps1 -Group Crypto-Panel -Agents 2 -DryRun
```
`-Group` also scopes `-Personalities` resolution to that group. Confirm the registry
sees it:
```powershell
.\.venv\Scripts\python.exe src\orchestrator\personas.py list --group Crypto-Panel
```

### Inspect the roster from the CLI

```powershell
# Full roster as JSON (slug/name/group/tags/summary/path), sorted by display name
.\.venv\Scripts\python.exe src\orchestrator\personas.py list --group Unique-Personas

# One persona, including its full prompt body
.\.venv\Scripts\python.exe src\orchestrator\personas.py get "alien-andy" --group Unique-Personas --body
```

---

## Live run #23 — observed result

| Metric | Value |
|---|---|
| Conversation | #23, topic *"Will lab-grown organs become common within 20 years?"* |
| Cast | claude-code = **Boomer Bill** (first), antigravity = **Alien Andy** |
| Messages | 7 from each agent, perfectly alternating |
| Final status | `complete` |
| `end_reason` | **`agent signaled done`** (antigravity emitted `signal='done'` on its 7th turn) |
| Persona fidelity | Both stayed in voice throughout (Boomer Bill's "back in my day…" curmudgeon; Alien Andy's "the Greys grow organs in biosynthetic gel vats… it's called 'loosh', bro") |

### Why it stopped at 7, not 8

The `debate` preset sets `max_turns=8` **per agent**, but that's a *ceiling*, not a
target. Alien Andy (antigravity) chose to attach a `done` signal to its 7th
message, which tripped `maybe_complete()`'s done-signal branch before either agent
reached the cap. This is correct, intended behavior — an agent ending the debate
when it judges the exchange finished. To force a full 8 rounds you'd instruct
personas not to emit `done`, or rely solely on the cap.

---

## Component reference

| Concern | File |
|---|---|
| Launcher (this walkthrough) | `scripts/debate.ps1` |
| Sidecar-ensure + seed wrapper | `scripts/start.ps1` |
| CLI seed entrypoint (argparse + preset) | `src/start_conversation.py` |
| Seeding — single source of truth | `src/orchestrator/seeding.py` (`seed_conversation()`) |
| Per-CLI MCP-config preflight | `src/orchestrator/preflight.py` |
| Persona registry (JSON over stdout) | `src/orchestrator/personas.py` |
| MCP server (turn enforcement) | `src/agent_chat_mcp.py` |
| MCP server launcher | `scripts/run-mcp-server.ps1` |
| DB-sync sidecar | `scripts/db_sync.py` |
| Kickoff template | `prompts/Kickoff/kickoff.md` |
| Topic library | `docs/Chat-Topics/Topics.md` |
| Persona data (runtime) | `personas` table in `db/chat.db` |
| Persona seed cards (one-time import + git snapshot) | `agents/Debate-Agents/<group>/*.md`; template at `agents/Debate-Agent-Templates/` |
| Per-agent prompt drops (runtime) | `db/launch/conv<id>-<cli>.txt` |
| Run log | `logs/debate-history.log` |
| The message bus | `db/chat.db` (SQLite, WAL) |

---

## Quick troubleshooting

- **Dry run first.** `.\scripts\debate.ps1 -DryRun` prints the topic, persona→CLI
  map, prompt-file paths, and exact launch command per agent — no windows, no seed.
- **A window opens but no messages appear.** The CLI couldn't reach `agent_chat`.
  Confirm it launched from its `agents/CLIs/<cli>_agent1/` folder and that its MCP
  config parses (`python -m json.tool <config>`). Run the preflight, or `/mcp`
  inside Claude Code.
- **"could not parse conversation id".** The seed failed inside `start.ps1` /
  `seed_conversation()`. Scroll up for the validation/seed error; no agents are
  launched in this case.
- **Topic never gets re-picked.** It's checked off with ✅ in `Topics.md`. Remove
  the marker to recycle it.
- **Watch live:** `http://127.0.0.1:8765/conversations/<id>` (local web UI) or
  `https://agent-chat.mikesailab.com/conversations/<id>` (public, via the sidecar).
- **Inspect after the fact:**
  `.\.venv\Scripts\python.exe src\inspect_conversations.py show <id>`.
