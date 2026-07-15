---
name: agent-chat-export-contract
description: Use before changing anything about the Agent-Chat export bundle — src/orchestrator/export.py, the /export.md or /export.zip endpoints, scripts/publish_debate.py, the topic slug, persona filenames, or the transcript heading shape. The format is a frozen contract parsed by three external consumers, so a cosmetic rename silently breaks the library archive and the theater app. Triggered by "change the export", "export format", "publish a debate", "topic_slug", "bundle", "transcript.md".
---

# Agent-Chat export bundle — a frozen contract

`src/orchestrator/export.py` is the **single source of truth** for bundle
rendering. Three surfaces call it: the web downloads (`GET
/api/conversations/{cid}/export.md`, `…/export.zip`) and
`scripts/publish_debate.py`. Never reimplement rendering in `web_ui.py` or the
publish script.

Its output is **parsed by external consumers that live in other repos**, so the
format is effectively frozen. Read `docs/App/export-format.md` before changing
any of it, and update the consumers in the same change:

1. The **AI-Automation-Library** archive — `scripts/publish_debate.py` writes
   `My-Library/Content/Agent-Debates/<Category>/<topic-slug>/`.
2. The **library site walker**, which indexes those folders.
3. The **debate-chat-theater** app, whose `build.mjs` parses the meta table, the
   Cast section, the `## sender — timestamp` headings, and the persona cards.

## What is frozen

Heading shapes, meta-table labels, the message heading, persona filenames, and
the 25-char `topic_slug`. Additive changes (a new meta row, a new optional
section) are usually safe; **renames break consumers**.

- **Meta table** — header is always `| Field | Value |` / `|:---|:---|`.
  `topic.md` rows: `Conversation` (`#<id>`), `Status`, `Mode`
  (`<mode> (max <n> turns/agent)`), `Preset` (only when set), `Participants`
  (comma-joined), `Created`, `Updated`, `End reason` (only when set).
  `transcript.md` omits the `Conversation` and `Preset` rows.
- **Headings** — `topic.md`: `# <topic>` (or `# Conversation #<id>`), `## Cast`
  (only when personas exist; bullets `- **<agent>** — <persona name>`),
  `## Debate framing (kickoff)` (only when `kickoff_template` is set).
  `transcript.md`: `# Conversation #<id>: <topic>`.
- **Message heading** — `## {sender} — {fmt_time(created_at)}`, plus a
  `` — `signal={signal}` `` suffix when a signal is set. Messages are separated
  by `---`. `fmt_time` renders ISO → `YYYY-MM-DD HH:MM:SS`.
- **Persona filenames** — `personas/{safe_name(agent_id)}-{safe_name(slug)}.md`,
  or `personas/{safe_name(agent_id)}.md` with no slug. `safe_name()` keeps
  `A-Za-z0-9._-`, collapses everything else to `-`, and falls back to `"x"`.
- **`topic_slug(topic, max_len=25)`** — ASCII-ignore → lowercase →
  `re.sub(r"[^a-z0-9]+", "-")` → `strip("-")` → truncate to 25 →
  `rstrip("-")`. Returns `""` when nothing is usable, and callers
  (`export_filename` / `export_zip_filename`) fall back to `conversation-<id>`.
  **The 25 is load-bearing** — it's the archive's folder name.
- **Bundle contents** (`bundle_files()`) — `topic.md`, one
  `personas/<agent>[-<slug>].md` per participant, and `transcript.md`.
  `cover-image.png` is deliberately **not** in the bundle.
- **Footers** — `_Exported from Agent Battleground._` (topic.md) and
  `_Exported from Agent Battleground. Source: Conversation #<id>._`
  (transcript.md). An empty transcript renders `_No messages yet._`.

## The functions

`fmt_time` · `topic_slug` · `export_filename` · `export_zip_filename` ·
`safe_name` · `parse_participant_personas` · `persona_doc` ·
`render_export_overview` · `render_export_markdown` · `bundle_files` ·
`render_export_zip` · `load_conversation`

All are pure except `load_conversation()`, which opens the DB. (Note: the doc
refers to `safe()`; the actual name is `safe_name()`.)

## If you must change the format

1. Read `docs/App/export-format.md` first — it is the contract document.
2. Prefer **additive**. A new optional row or section won't break a parser that
   looks for known labels.
3. If you rename or reshape anything, update all three consumers in the same
   change and say so explicitly in `docs/CHANGELOG.md`.
4. Re-render a real bundle and diff it against the previous output before
   committing — `GET /api/conversations/<cid>/export.md` on a finished
   conversation is the cheapest check.
