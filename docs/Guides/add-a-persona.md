<h1 align="center">🎭 Add your own persona</h1>

<p align="center">
  <em>Write a character, drop in a card someone else wrote, or import a whole folder.<br>
  Personas live in the database, so this takes no code change and no restart.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Where-%2Fpersonas-10b981?style=for-the-badge&labelColor=09090b" alt="The /personas page">
  <img src="https://img.shields.io/badge/Code_change-none-0284c7?style=for-the-badge&labelColor=09090b" alt="No code change">
  <img src="https://img.shields.io/badge/Restart-not_needed-8b5cf6?style=for-the-badge&labelColor=09090b" alt="No restart">
</p>

---

A persona is the character an agent plays — its voice, what it believes, how it
argues. One row in the `personas` table: a display name, a **group**, tags, an
avatar, and a Markdown body that becomes the agent's system prompt for the run.

Nothing about this is file-based at runtime. Add a persona on the web UI and the
next conversation can cast it immediately. If you run the [mirror
sidecar](../../scripts/README.md), the new card syncs to the hosted copy on its own.

> [!TIP]
> Want to know how the registry works rather than how to use it —
> groups, the reserved `AI-Models` cards, avatar resolution order, the
> `list_personas` / `get_persona` MCP tools? That's
> [`../App/personas.md`](../App/personas.md).

---

## 🖊️ Option 1 — write one in the browser

Start the local app (`scripts\startup-app.ps1`, or `.\.venv\Scripts\python.exe
src\web_ui.py`) and open **<http://127.0.0.1:8765/personas>**.

1. **`+ New`** opens the editor panel.
2. Fill in:

| Field | What goes in it |
|:---|:---|
| **Display name** | What appears in the transcript and the cast panel — *Crypto Chad*. The slug is derived from it. |
| **Group** | Which roster the card belongs to. Pick an existing one or choose *New group* and type a name — groups are free-form, and a group exists as soon as a card lands in it. |
| **Avatar** | Optional. PNG, JPEG, GIF, or WebP, squared off and scaled to 512px. Leave it empty for the default silhouette. **SVG is refused on purpose** — it can carry script, and these are served from the app's own origin. |
| **Tags** | Free text chips. Used for filtering and search, never for casting. |
| **System prompt / bio** | The card body. Markdown, with an **Edit** / **Preview** toggle. This whole field is what the model is told to be. |

3. **Save.** The persona is live.

Every card in the roster also has **✎ edit**, **⧉ duplicate** (the fastest way to
write a variant), and **🗑 delete**. `Select` turns on multi-select for bulk
deletion.

### Writing a body that works

The body is freeform — the app reads all of it and hands it to the model. Two
rules earn their keep:

- **Write in the second person, as an instruction.** *"You are X. You believe…
  You speak in short, flat sentences."* A model adopts what it is told to be and
  merely narrates what it is described as.
- **Give it something to disagree about.** A persona with no stated beliefs,
  no dislikes, and no style produces the same agent you already had. Voice,
  convictions, and what it refuses to concede are what make a transcript
  readable.

The canonical structure — Purpose, Persona (voice / debate style / beliefs /
strengths / weaknesses), example lines, stay-in-character rules — is in
[`agents/Debate-Agent-Templates/Agent-Personality.md`](../../agents/Debate-Agent-Templates/Agent-Personality.md).
It is a starter set, not a schema.

---

## 📥 Option 2 — import cards you already have

**`Import`** on `/personas` takes loose `.md` files, images, and `.zip`
archives in one go.

| You have | Drop in |
|:---|:---|
| One card | `crypto-chad.md` |
| A card and its picture | `crypto-chad.md` + `crypto-chad.png` |
| A folder of them | A `.zip` — flat, or one subfolder per persona holding a card and an image |

Pick a **target group**, tick **Overwrite existing personas with the same slug**
if you're updating rather than adding, and import. The result reports how many
landed, how many were skipped, and any per-card errors, so a partial import is
never silent.

**Images pair with cards by filename** — `crypto-chad.png` beside
`crypto-chad.md`, or a bare `avatar.png` inside a per-persona folder. An image
that matches nothing is reported and skipped; it never blocks its batch.

> [!IMPORTANT]
> **Frontmatter must be the first bytes of the file.** The parser anchors at
> offset 0, so anything above the opening `---` — even a comment — makes it read
> the whole file as body and silently drop `title`, `tags`, and `category`. This
> is the most common way a card imports with empty metadata.

```markdown
---
title: "Machiavelli"
tags:
- political
- historical
category: Debaters
---

# Machiavelli

## Purpose
Argue from power and consequence rather than principle.

You are Niccolò Machiavelli. You believe intentions are decoration and
outcomes are the only evidence…
```

The filename becomes the slug; `title`, `tags`, and `category` come from the
frontmatter; the roster summary comes from the `## Purpose` line.

### Where to find cards

The [**Persona Registry**](https://library.mikesailab.com/tools/persona-registry/)
is a public catalogue in this format — download a card and its avatar, then drop
both into the import modal. The `Import` modal links to it directly.

This repo also ships 62 seed cards under
[`agents/Debate-Agents/`](../../agents/Debate-Agents/). They are a **one-time
import source**, not a runtime folder: nothing reads them during a conversation,
and editing one changes nothing until someone re-imports it.

> [!NOTE]
> The file-tree importer (`import_personas_from_files()`) reads **one level
> down** — the `.md` files directly inside each group folder. Cards nested
> deeper, like `AI-Library-Imports/Celebrities/`, come in through the `Import`
> modal instead: select that folder's cards, or zip it and drop the zip.

---

## 🎬 Casting what you made

| Launcher | How your persona gets picked |
|:---|:---|
| [**`/orchestrate` form**](orchestrate-form.md) | Each chair row has a persona dropdown. Pick yours, or use **✎ custom instructions…** for a one-off card that never enters the registry. |
| [**`debate.ps1`**](auto-debate.md) | `-Group <name>` casts at random from that group. Put your cards in their own group and the launcher will only draw from it. |
| [**Manual seed**](start-new-chat.md) | Pass personas explicitly when seeding. |
| **The agent itself** | `list_personas()` / `get_persona(name)` are MCP tools — an agent can browse the roster and adopt a character without an operator step. |

> [!NOTE]
> **Random casting skips reserved groups.** The `AI-Models` group holds one card
> per supported CLI (*"you are Claude Code"*) and is excluded from random draws,
> so a random debate never fields Claude Code against Gordon Ramsay. An explicit
> pick is always honoured.

---

## 🔗 What pairs with this

| Next | Why |
|:---|:---|
| [`../App/personas.md`](../App/personas.md) | The reference half — the registry API, group semantics, avatar resolution, the MCP tools, storage and sync. |
| [`add-a-cli.md`](add-a-cli.md) | The other half of "make it yours": which CLI tools sit in the chairs. |
| [`debate.md`](debate.md) · [`podcast.md`](podcast.md) · [`collaborate.md`](collaborate.md) | Put the persona to work. |
| [`../../skills/debate-mode/SKILL.md`](../../skills/debate-mode/SKILL.md) | What the agent is taught about staying *in* character. |

---

<p align="center">
  <sub>← <a href="README.md">Guides</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="add-a-cli.md">Add your own CLI →</a></sub>
</p>
