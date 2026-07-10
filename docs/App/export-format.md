# Export-bundle format (the contract)

The Markdown bundle that represents one finished conversation is produced in
exactly one place — **`src/orchestrator/export.py`** — and consumed by three
surfaces that parse it:

| Consumer | How it gets the bundle |
|:---|:---|
| Web UI downloads | `GET /api/conversations/{cid}/export.md` (transcript only) and `…/export.zip` (full bundle) in `src/web_ui.py` |
| AI-Automation-Library archive | `scripts/publish_debate.py` writes the same files into `AI-Automation-Library/My-Library/Content/Agent-Debates/<Category>/<topic-slug>/` |
| debate-chat-theater app | its `build.mjs` **parses** the archived files — the topic meta table + Cast section, the transcript's `## sender — timestamp` headings, and the persona cards |

> **Change policy:** any change to the render functions in
> `orchestrator/export.py` changes what all three see. Additive changes (a new
> meta-table row, a new optional section) are usually safe; renaming headings,
> the meta-table labels, the message-heading shape, or file names **breaks the
> theater parser and the archive convention** — update the consumers in the
> same change and note it in the CHANGELOG.

## The bundle

```text
topic.md                      # title + meta + cast + kickoff framing
personas/<agent>[-<slug>].md  # one per participant
transcript.md                 # the full debate
```

The `.zip` download contains exactly these entries; `publish_debate.py` writes
them as real files (LF newlines, UTF-8). `cover-image.png` is **not** part of
the bundle — it's generated separately (see the `publish-debate` skill) and
lives only in the library folder.

## `topic.md` — `render_export_overview()`

```markdown
# <topic>                                  ← or "# Conversation #<id>" if topic is empty

| Field | Value |
|:---|:---|
| Conversation | #<id> |
| Status | complete |
| Mode | turns (max 8 turns/agent) |
| Preset | debate |                        ← only when a preset was recorded
| Participants | claude-code, codex |
| Created | 2026-06-30 22:26:53 |          ← fmt_time(): "YYYY-MM-DD HH:MM:SS"
| Updated | 2026-06-30 22:33:35 |
| End reason | max_turns reached (8 per agent) |   ← only when set

## Cast                                    ← only when participant_personas exists

- **claude-code** — Gordon Ramsay
- **codex** — Dr. Gregory House

---

## Debate framing (kickoff)                ← only when kickoff_template exists

<the rendered kickoff template, verbatim>

_Exported from Agent Battleground._
```

The theater app reads the **Cast** bullets (`- **<agent>** — <persona name>`)
to label debaters, and the meta table for mode/timestamps.

## `transcript.md` — `render_export_markdown()`

```markdown
# Conversation #<id>: <topic>

| Field | Value |                          ← Status / Mode / Participants /
|:---|:---|                                  Created / Updated / End reason
…

---

## <sender> — <YYYY-MM-DD HH:MM:SS>        ← one heading per message; when the
                                             message carried a signal, the
                                             heading ends " — `signal=done`"
<message body, verbatim — agents already write Markdown>

---

_Exported from Agent Battleground. Source: Conversation #<id>._
```

Messages are separated by `---` rules. The `## sender — timestamp` heading
shape is what the theater's parser splits turns on — treat it as frozen.

## `personas/*.md` — `persona_doc()`

Filename: `personas/<safe(agent_id)>-<safe(persona_slug)>.md`, or just
`personas/<safe(agent_id)>.md` when no persona was recorded (`safe()` keeps
letters/digits/`._-`, collapses everything else to `-`). Body: `# <persona
name>` (falls back to the agent id), a meta table (`AI tool / CLI`,
`Persona`), then the full personality card under `## Personality card` when
one was recorded.

## Slug rules — `topic_slug()`

Lowercased ASCII, non-alphanumerics collapsed to single hyphens, trimmed, then
**truncated to 25 chars** (trailing hyphen stripped) — e.g. *"Should
restaurants be required…"* → `should-restaurants-be-req`. Empty result falls
back to `conversation-<id>`. The slug names the download files **and** the
library debate folder, so it's the join key between the DB, the archive, and
the theater — changing the truncation changes where re-publishes land.
