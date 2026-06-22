# Kickoff prompts

Server-delivered kickoff for `agent_chat` conversations. Replaces the
"paste a 30-line prompt into every CLI" workflow with a single
`get_kickoff()` MCP tool plus named presets — so seeding a debate,
code review, brainstorm, or plan is one `start_conversation.py`
invocation and each per-CLI prompt collapses to two lines.

Pairs with [`prompts/kickoff.md`](../../prompts/kickoff.md) (the
canonical template body) and [`docs/Guides/start-new-chat.md`](../Guides/start-new-chat.md)
(the operator daily-driver flow).

---

## What changed

Before this feature (still works — see [Backward compatibility](#backward-compatibility)):

1. Operator runs `start_conversation.py --topic "..." --participants ...`.
2. Operator opens `prompts/kickoff.md`, manually substitutes `{{TOPIC}}`
   and `{{TONE_INSTRUCTION}}`, and pastes the whole template into each
   CLI's terminal. For 3+ agent runs, the operator also rewrites the
   "another AI agent" opening line by hand.

After:

1. Operator runs `start_conversation.py --preset debate --topic "..." --participants ...`.
   The seeder renders the template once and stores the body on the
   `conversations` row.
2. Operator pastes a two-line prompt into each CLI: *"You're agent
   &lt;id&gt; on the agent_chat MCP server. Call `get_kickoff()` and
   follow the instructions it returns."*
3. Each agent calls `get_kickoff()` once at session start, reads the
   `instructions` field, and runs the loop it describes.

---

## Architecture

```text
                            +-----------------------------+
                            |  src/presets.py             |
                            |  PRESETS dict (4 entries)   |
                            +--------------+--------------+
                                           |
                          read at flag-resolve time
                                           |
                                           v
+--------------------------+    +-----------------------------+
| prompts/kickoff.md       |--->|  orchestrator/seeding.py    |
| (Markdown w/ ```text     |    |  - renders the template     |
|  fenced template body)   |    |  - rewrites for N agents    |
+--------------------------+    |  - INSERTs conversation row |
       ^                        |    with preset +            |
       |                        |    kickoff_template columns |
       |                        +--------------+--------------+
       |                                       |
       | optional: --kickoff-template-file     |
       | override pulls from another file      v
       |                       +-----------------------------+
       |                       |  db/chat.db                 |
       |                       |  conversations row          |
       |                       +--------------+--------------+
       |                                       |
       |                                       | get_kickoff()
       |                                       v
       |                       +-----------------------------+
       |                       |  src/agent_chat_mcp.py      |
       |                       |  get_kickoff() MCP tool     |
       |                       |  - reads kickoff_template   |
       |                       |    column for AGENT_ID's    |
       |                       |    latest conversation      |
       |                       |  - falls back to a generic  |
       +-----------------------+    "follow prompts/         |
                               |    kickoff.md" string when  |
                               |    column is NULL           |
                               +-----------------------------+
```

Key property: rendering happens **once at seed time**, not on every
`get_kickoff()` call. The MCP tool is a cheap read of the stored
column, idempotent across any number of calls.

---

## CLI flags on `start_conversation.py`

```
--preset {debate,code-review,brainstorm,plan}
    Apply a named kickoff preset. Triggers rendering + storage of the
    kickoff_template. Each preset bundles a tone, default mode, and
    default max_turns — see the table below.

--tone "<sentence>"
    Override the {{TONE_INSTRUCTION}} substitution. Use with or without
    --preset. Combined with --preset: overrides the preset's tone.
    Without --preset: still triggers rendering; mode/max_turns then
    fall back to the script defaults (turns / 10) unless explicitly
    set.

--kickoff-template-file <path>
    Path to a custom kickoff template. Two source shapes supported:

    1. Markdown with a ```text fenced block — the first such block's
       body is extracted. (Same shape as prompts/kickoff.md, so you
       can fork that file for one-off customization.)
    2. Plain text — the whole file is used verbatim (whitespace
       stripped).

    Defaults to prompts/kickoff.md.
```

Precedence for `mode` and `max_turns`:

```
explicit --mode / --max-turns   >   preset's default   >   script default
```

---

## Available presets

Defined in [`src/presets.py`](../../src/presets.py). Tone strings are
copied verbatim from the `{{TONE_INSTRUCTION}}` examples in
`prompts/kickoff.md`.

| Preset | Tone (one full sentence) | Mode | max_turns |
|:---|:---|:---:|:---:|
| `debate` | "Have a real debate — take positions, push back, share concrete predictions. Don't just agree with each other." | turns | 8 |
| `code-review` | "Review the proposal critically. Reference specific lines or claims. Distinguish blocking issues from suggestions. End with an explicit approve / request-changes signal." | turns | 6 |
| `brainstorm` | "Generate ideas freely. Build on each other rather than evaluating. Quantity first, then we converge." | continuous | 10 |
| `plan` | "Work toward a concrete plan. By the end I want a numbered list of steps with owners and a definition of done." | turns | 8 |

To add a preset, add an entry to `PRESETS` in `src/presets.py` and
update this table.

---

## The rendering pipeline

`render_kickoff(template, topic, tone, n_participants)` in
[`src/orchestrator/seeding.py`](../../src/orchestrator/seeding.py)
performs three transformations on the loaded template:

1. **Topic substitution.** `{{TOPIC}}` → the `--topic` value.
2. **Tone substitution.** `{{TONE_INSTRUCTION}}` → the resolved tone
   (preset's tone, or `--tone`, with the latter winning if both are
   set).
3. **Multi-agent rewrite.** For 3+ participants, the literal phrase
   `with another AI agent` (singular) in the opening line is rewritten
   to `with (N-1) other AI agents` (plural with count). For 2-agent
   runs the phrase is left unchanged.

The 3-agent rewrite is a single targeted substitution — only the
opening declaration is touched. Later mentions of "the other agent"
in the loop instructions refer to "whichever agent went immediately
before you" and still read correctly with N agents in the cycle.

The rendered body is stored verbatim in the `kickoff_template` column.
Re-rendering on the agent side is unnecessary (and would require
duplicating the renderer in the MCP server, which we intentionally
avoid — `agent_chat_mcp.py` only reads).

---

## The `get_kickoff()` MCP tool

```python
@mcp.tool(name="get_kickoff", annotations={"readOnlyHint": True,
                                            "idempotentHint": True, ...})
async def get_kickoff(params: GetKickoffInput) -> str: ...
```

No input parameters. Reads `AGENT_ID` from server config (same as the
other tools).

### Response shapes

**Conversation exists with a stored template (the common case):**

```json
{
  "status": "ok",
  "agent_id": "claude-code",
  "conversation_id": 42,
  "topic": "Should AI agents have persistent memory?",
  "preset": "debate",
  "instructions": "You're participating in an agent_chat conversation\nwith 2 other AI agents..."
}
```

**Conversation exists but no template stored (legacy / no `--preset`):**

```json
{
  "status": "fallback",
  "agent_id": "claude-code",
  "conversation_id": 42,
  "topic": "Should AI agents have persistent memory?",
  "preset": null,
  "instructions": "No rendered kickoff template is attached to this conversation — it was seeded with the older paste-the-prompt workflow. Follow the canonical kickoff prompt in `prompts/kickoff.md`..."
}
```

**No conversation includes this agent:**

```json
{
  "status": "no_conversation",
  "agent_id": "claude-code",
  "message": "No conversation includes agent 'claude-code'. Ask the operator to run start_conversation.py first."
}
```

### When agents should call it

- **At session start**, after the operator says "join the conversation"
  or pastes the two-line prompt. Once per session is enough — the
  return value doesn't change for the same conversation.
- **Not in a loop.** Use `wait_for_turn` for the turn loop. The
  kickoff is a one-time read.

---

## Custom templates

Two layers of customization:

### Override just the tone

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --preset debate `
  --tone "Argue from a 5-year-out timeline. Be specific about predictions." `
  --topic "..." --participants ...
```

The preset still supplies mode + max_turns; only the tone string
changes.

### Author a custom template body

Copy `prompts/kickoff.md` to a new file. Edit the `` ```text `` fenced
block — keep `{{TOPIC}}` and `{{TONE_INSTRUCTION}}` placeholders if
you want them substituted, otherwise hardcode whatever you need. Then:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --kickoff-template-file path\to\custom-kickoff.md `
  --tone "..." `
  --topic "..." --participants ...
```

Plain-text files (no `` ```text `` fence) are also supported — the
whole file body is used.

If a custom template doesn't contain `{{TONE_INSTRUCTION}}`, the tone
flag is still required (passing one without the other errors out) —
but the substitution is a no-op. This keeps the contract simple: tone
is always required when rendering, even if the template doesn't use
it.

The multi-agent rewrite (`with another AI agent` → `with N other AI
agents`) only fires when that exact phrase exists in the loaded
template. Custom templates that don't use that phrasing are left
alone for the N-agent case.

---

## Schema

Two additive columns on `conversations`:

```sql
preset            TEXT  -- 'debate' | 'code-review' | 'brainstorm' | 'plan' | NULL
kickoff_template  TEXT  -- rendered template body, or NULL
```

The migration is **idempotent**: `db_init()` checks
`PRAGMA table_info(conversations)` and `ALTER TABLE` ADDs each
missing column. Safe on fresh DBs (no-op past `executescript`) and on
existing DBs from older builds. Mirrored in several places — keep in
sync when adding columns:

- `src/agent_chat_mcp.py` — `_MIGRATIONS` constant + `db_init()`.
- `src/web_ui.py` — `_MIGRATIONS` constant + `db_init()`. Also
  `_CONV_COLUMNS` (ingest/since endpoints).
- `src/orchestrator/seeding.py` — `_MIGRATIONS` constant + the migration
  block in `seed_conversation()` (`start_conversation.py` is a thin
  wrapper that delegates here).
- `scripts/db_sync.py` — `CONV_COLUMNS` (sidecar push column list).

Pre-existing rows have NULL in both columns. `get_kickoff()`'s
`fallback` branch is exactly the "row exists, kickoff_template is
NULL" case.

---

## Backward compatibility

- **Existing conversations** (rows that pre-date this feature) are
  unaffected. `kickoff_template` migrates to NULL; agents calling
  `get_kickoff()` get `status="fallback"` and the generic instruction
  string pointing them at `prompts/kickoff.md`. Old paste-the-prompt
  flow still works on these conversations.
- **Seeding without `--preset` / `--tone` / `--kickoff-template-file`**
  works exactly as before. `kickoff_template` stays NULL. Operator can
  paste the full template by hand into each CLI.
- **Agents that don't call `get_kickoff()`** are fine. The MCP server
  doesn't require it — `wait_for_turn` / `get_my_turn` / `send_message`
  all work standalone, same as before. `get_kickoff()` is opt-in for
  agents that want the rendered prompt.

---

## Where to look for what

| Concern | File / function |
|:---|:---|
| Add or rename a preset | `PRESETS` dict in [`src/presets.py`](../../src/presets.py); update the table in this doc + `prompts/kickoff.md`. |
| Change the multi-agent rewrite rule | `render_kickoff()` in [`src/orchestrator/seeding.py`](../../src/orchestrator/seeding.py). |
| Change the default template path | `_DEFAULT_TEMPLATE_PATH` constant in [`src/orchestrator/seeding.py`](../../src/orchestrator/seeding.py). |
| Change the `get_kickoff()` response shape | Tool body in [`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py); update the response-shape examples in this doc. |
| Change the fallback string | `_FALLBACK_KICKOFF` constant in [`src/agent_chat_mcp.py`](../../src/agent_chat_mcp.py). |
| Add a new schema column | `SCHEMA` + `_MIGRATIONS` in `agent_chat_mcp.py`, `web_ui.py`, and `orchestrator/seeding.py` **plus** `_CONV_COLUMNS` (web_ui.py) and `CONV_COLUMNS` (db_sync.py). Per-feature doc update goes here. |
