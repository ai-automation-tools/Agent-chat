# `prompts/`

Reusable prompts for driving Agent-Chat conversations — both the canonical kickoff
template every CLI agent runs, and a library of paste-ready operator prompts for
launching debates.

## What's here

| Path | What it is |
|---|---|
| [`Auto-Debate/`](Auto-Debate/README.md) | **Start a debate** — sample operator prompts for the `start-debate` skill (`scripts/debate.ps1`), organized by category. |
| [`Manage-Debates/`](Manage-Debates/README.md) | **Run a debate** — watch, stop, review/export, browse the cast, troubleshoot a launched debate. |
| [`Kickoff/kickoff.md`](Kickoff/kickoff.md) | **Canonical kickoff template.** What `get_kickoff()` returns and what you paste for a manual (non-debate) seed. Verified current 2026-06-26. |

## Pick your starting point

- **Launching a debate?** Go to [`Auto-Debate/`](Auto-Debate/README.md), copy a
  block, paste it into Claude Code. Categories:
  [Head-to-Head](Auto-Debate/Head-to-Head/head-to-head.md) ·
  [Three-Way](Auto-Debate/Three-Way/three-way.md) ·
  [Group-Themed](Auto-Debate/Group-Themed/group-themed.md) ·
  [Custom-Cast](Auto-Debate/Custom-Cast/custom-cast.md) ·
  [Surprise-Me](Auto-Debate/Surprise-Me/surprise-me.md)
- **Already running one?** Go to [`Manage-Debates/`](Manage-Debates/README.md) to
  watch, stop, review, export, or troubleshoot. Categories:
  [Watch-And-Status](Manage-Debates/Watch-And-Status/watch-and-status.md) ·
  [Stop-And-Cleanup](Manage-Debates/Stop-And-Cleanup/stop-and-cleanup.md) ·
  [Review-And-Export](Manage-Debates/Review-And-Export/review-and-export.md) ·
  [Personas-And-Topics](Manage-Debates/Personas-And-Topics/personas-and-topics.md) ·
  [Troubleshooting](Manage-Debates/Troubleshooting/troubleshooting.md)
- **Seeding a manual / non-debate conversation?** Use
  [`Kickoff/kickoff.md`](Kickoff/kickoff.md) — it documents the
  `get_kickoff()` flow and the legacy hand-pasted template.

## How a prompt becomes a conversation

```
operator prompt (Auto-Debate/**/*.md)
   └─ start-debate skill ──► scripts/debate.ps1
        ├─ seeds the conversation (--preset debate) via start_conversation.py
        ├─ stores the rendered kickoff template (Kickoff/kickoff.md) on the row
        └─ spawns one CLI per persona; each calls get_kickoff() and runs the loop
```

## Keep these honest

The Auto-Debate examples reference **real** personas and CLIs. The source of truth
is the `personas` table, not these files — re-check before relying on a name:

```powershell
.\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
```

Related: [`docs/Guides/auto-debate.md`](../docs/Guides/auto-debate.md) (full flag
reference) · [`skills/start-debate/SKILL.md`](../skills/start-debate/SKILL.md) (the
skill these prompts trigger) · [`docs/Guides/start-new-chat.md`](../docs/Guides/start-new-chat.md)
(manual seed recipe).
