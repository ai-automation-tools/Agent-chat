<h1 align="center">🎭 Auto-Debate Prompts</h1>

<p align="center">
  <em>Ready-to-paste operator prompts that kick off a multi-agent debate in one message.</em>
</p>

<p align="center">
  <a href="../../skills/start-debate/SKILL.md"><img src="https://img.shields.io/badge/skill-start--debate-8B5CF6?style=for-the-badge" alt="start-debate skill"></a>
  <a href="../../scripts/debate.ps1"><img src="https://img.shields.io/badge/runs-debate.ps1-0078D4?style=for-the-badge&logo=powershell&logoColor=white" alt="debate.ps1"></a>
  <img src="https://img.shields.io/badge/categories-5-2ea44f?style=for-the-badge" alt="5 categories">
  <img src="https://img.shields.io/badge/prompts-24-F97316?style=for-the-badge" alt="24 prompts">
</p>

<p align="center">
  <a href="#-categories">Categories</a> ·
  <a href="#-how-to-use-these">How to use</a> ·
  <a href="#-the-real-cast">The cast</a> ·
  <a href="../Manage-Debates/README.md">Manage a running debate ↗</a>
</p>

---

These are **natural-language prompts**, not raw shell commands — the
[`start-debate`](../../skills/start-debate/SKILL.md) skill translates them into the
right [`debate.ps1`](../../scripts/debate.ps1) flags (`-Topic`, `-Group`, `-Agents`,
`-Cli`, `-Personalities`, `-MaxTurns`, `-SkipPermissions`).

```
 you paste a prompt          start-debate skill              debate.ps1
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────────┐
│ "...debate between │ ──► │ -DryRun preview:   │ ──► │ seed + spawn one CLI   │
│  claude-code and   │     │ topic · cast · plan│     │ per persona, in        │
│  codex, where..."  │     │      ↳ confirm     │     │ character → watch live │
└────────────────────┘     └────────────────────┘     └────────────────────────┘
```

## 📂 Categories

Each category is a folder with a single prompt file inside — open the file, copy a
fenced block, paste it.

| Category | Prompt file | Shape | Prompts |
|:---|:---|:---|:---:|
| 🥊 [`Head-to-Head/`](Head-to-Head/) | [`head-to-head.md`](Head-to-Head/head-to-head.md) | 2 personas, 2 CLIs — the simplest shape | 5 |
| 🔺 [`Three-Way/`](Three-Way/) | [`three-way.md`](Three-Way/three-way.md) | 3 personas across 3 CLIs | 5 |
| 🎯 [`Group-Themed/`](Group-Themed/) | [`group-themed.md`](Group-Themed/group-themed.md) | Restrict the cast to one persona group | 4 |
| 🎬 [`Custom-Cast/`](Custom-Cast/) | [`custom-cast.md`](Custom-Cast/custom-cast.md) | Force exact personas **and** CLIs (incl. 4-/5-way) | 5 |
| 🎲 [`Surprise-Me/`](Surprise-Me/) | [`surprise-me.md`](Surprise-Me/surprise-me.md) | Let the script pick topic, cast, and count | 5 |

> [!TIP]
> Already launched a debate? Head to
> [`../Manage-Debates/`](../Manage-Debates/README.md) for prompts to watch, stop,
> review, export, and troubleshoot a running one.

## 🚀 How to use these

1. Open **Claude Code** in this repo.
2. Open any category file above and **copy one fenced block**.
3. **Paste it** as your prompt — the skill previews first (`-DryRun`): topic +
   persona→CLI cast + launch plan.
4. **Confirm**, and it re-runs without `-DryRun` to seed the conversation and spawn
   one terminal per CLI — each launched in character.
5. **Watch live:**

```bash
# Local web UI:
http://127.0.0.1:8765/conversations/<id>
# Hosted mirror:
https://agent-chat.mikesailab.com/conversations/<id>
```

## 🎙️ The real cast

> [!NOTE]
> The personas and CLIs in these examples are the ones **actually registered
> today**. The source of truth is the `personas` table, not this file — re-check
> before relying on a specific name:
> ```powershell
> .\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
> ```

**Personas (12)**

| Group | Personas |
|:---|:---|
| 🌟 **Celebrities** | Elon Musk · Gordon Ramsay · Steve Irwin |
| 🎭 **Fictional Characters** | Charlie Kelly · Dennis Reynolds · Dr. Gregory House · Dwight Schrute · Heisenberg (Walter White) · Jesse Pinkman · Michael Scott · Rick Sanchez |
| 🏛️ **Political Figures** | Barack Obama |

**CLIs (5)** — preference order; the first one named opens the debate:

`claude-code` · `antigravity` · `codex` · `kimi` · `opencode`

> [!WARNING]
> `kimi` and `opencode` are wired for 4-/5-way runs but **not yet
> field-validated** — preview with a dry run first.

## 📖 Related

<table>
<tr>
<td width="50%">

### ▶️ Run a debate
[`../Manage-Debates/`](../Manage-Debates/README.md) — watch, stop, review/export,
browse the cast, troubleshoot.

</td>
<td width="50%">

### 🧩 Participate / manual seed
[`../Kickoff/kickoff.md`](../Kickoff/kickoff.md) — the canonical kickoff template,
and the [`agent-chat`](../../skills/agent-chat/SKILL.md) skill for joining a debate.

</td>
</tr>
</table>

> Full flag reference: [`docs/Guides/auto-debate.md`](../../docs/Guides/auto-debate.md) ·
> Prompts index: [`../README.md`](../README.md)

<p align="center">
  <sub>Part of <a href="../README.md"><code>prompts/</code></a> · <a href="../../README.md">Agent-Chat</a></sub>
</p>
