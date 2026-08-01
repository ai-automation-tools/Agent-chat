<h1 align="center">⚔️ Battleground Prompts</h1>

<p align="center">
  <em>Ready-to-paste operator prompts for <b>AgentBattleground</b> — sending a CLI
  agent into a debate captured from a real web page, managing the arenas, and
  diagnosing it when something's off.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/categories-3-2ea44f?style=for-the-badge" alt="3 categories">
  <img src="https://img.shields.io/badge/prompts-29-F97316?style=for-the-badge" alt="29 prompts">
  <a href="../../skills/battleground/SKILL.md"><img src="https://img.shields.io/badge/skill-battleground-8B5CF6?style=for-the-badge" alt="battleground skill"></a>
  <a href="../../extension/README.md"><img src="https://img.shields.io/badge/chrome-extension-0078D4?style=for-the-badge&logo=googlechrome&logoColor=white" alt="extension"></a>
</p>

<p align="center">
  <a href="#-categories">Categories</a> ·
  <a href="#-how-to-use-these">How to use</a> ·
  <a href="../../docs/Guides/battleground.md">Full guide ↗</a> ·
  <a href="../Auto-Debate/README.md">Start a CLI debate ↗</a>
</p>

---

These prompts assume the browser side is already done — the extension captured a
thread and opened an **arena**. For that half, follow
[`docs/Guides/battleground.md`](../../docs/Guides/battleground.md).

> [!IMPORTANT]
> **The agent drafts; you post.** No prompt here can make it publish to a
> website — the capability doesn't exist. Approving a draft types text into the
> page's reply box and stops.

```
 capture in the extension          →  arena #id
 Join-Arena/    ⚔️  send the agent in     — get_arena → submit_draft
 (review in the side panel)        →  approve / reject
 Manage-Arenas/ 🗂️  inspect · recast · close · delete
 Troubleshooting/ 🔧 bridge, adapters, stuck drafts
```

## 🗂️ Categories

| Category | Use it for | Prompts |
|:---|:---|:---|
| ⚔️ [`Join-Arena/`](Join-Arena/join-arena.md) | Sending the CLI in: the standard "join the battleground", explicit joins if the skill isn't loading, answering one specific post, redrafting after a rejection, follow-ups after a re-capture. | 8 |
| 🗂️ [`Manage-Arenas/`](Manage-Arenas/manage-arenas.md) | The arenas themselves: list, inspect, "what's waiting on me", reassign to another CLI, change the stance mid-run, recast the persona, close, delete, read a draft history. | 11 |
| 🔧 [`Troubleshooting/`](Troubleshooting/troubleshooting.md) | Bridge unreachable or serving old code, empty persona picker, agent claiming it posted, capture finding nothing, duplicate posts on re-capture, stuck drafts, verifying nothing leaked to the mirror. | 10 |

## 🚀 How to use these

Two different targets — check which one a prompt is for:

- **Join-Arena** prompts go to the **CLI you cast in the panel** (the one that
  will argue). Usually just `join the battleground`.
- **Manage-Arenas** and **Troubleshooting** prompts go to **Claude Code working
  on this repo** — they `curl` the local bridge or read the DB.

Replace `<id>`, `<cli>`, `<url>`, and `<slug-or-name>` before pasting.

## 📎 Quick reference

| | |
|:---|:---|
| Bridge | `http://127.0.0.1:8765/api/battleground/…` |
| Guide | [`docs/Guides/battleground.md`](../../docs/Guides/battleground.md) |
| Reference | [`docs/App/battleground.md`](../../docs/App/battleground.md) |
| Extension | [`extension/README.md`](../../extension/README.md) |
| Skill | [`skills/battleground/SKILL.md`](../../skills/battleground/SKILL.md) |
| Tests | `.\.venv\Scripts\python.exe tests\test_battleground.py` |
