# Auto-Debate sample prompts

Ready-to-paste **operator prompts** for kicking off a multi-agent debate with the
[`start-debate`](../../skills/start-debate/SKILL.md) skill (which runs
[`scripts/debate.ps1`](../../scripts/debate.ps1) under the hood).

## How to use these

1. Open Claude Code in this repo.
2. Copy one fenced block from any category file below and paste it as your prompt.
3. The skill **previews** first (`-DryRun`): topic + persona→CLI cast + launch plan.
4. Confirm, and it re-runs without `-DryRun` to seed the conversation and spawn one
   terminal per CLI — each launched in character.
5. Watch live at `http://127.0.0.1:8765/conversations/<id>` (or the hosted mirror).

These are natural-language prompts, not raw shell commands — the skill translates
them into the right `debate.ps1` flags (`-Topic`, `-Group`, `-Agents`, `-Cli`,
`-Personalities`, `-MaxTurns`, `-SkipPermissions`).

## Categories

| Folder | What it covers |
|---|---|
| [`Head-to-Head/`](Head-to-Head/head-to-head.md) | 2 personas, 2 CLIs — the simplest shape |
| [`Three-Way/`](Three-Way/three-way.md) | 3 personas across 3 CLIs |
| [`Group-Themed/`](Group-Themed/group-themed.md) | Restrict the cast to one persona group |
| [`Custom-Cast/`](Custom-Cast/custom-cast.md) | Force exact personas **and** exact CLIs (incl. 4-/5-way) |
| [`Surprise-Me/`](Surprise-Me/surprise-me.md) | Let the script pick topic, cast, and count |

> Already launched? See [`../Manage-Debates/`](../Manage-Debates/README.md) for
> prompts to watch, stop, review, and export a running debate.

## The real cast (source of truth = the `personas` table)

Personas and CLIs used in these examples are the ones actually registered today.
They can change — re-check before relying on a specific name:

```powershell
# Personas, grouped:
.\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
```

**Personas (12):**
- **Celebrities** — Elon Musk, Gordon Ramsay, Steve Irwin
- **Fictional Characters** — Charlie Kelly, Dennis Reynolds, Dr. Gregory House,
  Dwight Schrute, Heisenberg (Walter White), Jesse Pinkman, Michael Scott, Rick Sanchez
- **Political Figures** — Barack Obama

**CLIs (5):** `claude-code`, `antigravity`, `codex`, `kimi`, `opencode`
(preference order; the first one named opens the debate). `kimi`/`opencode` are
wired for 4-/5-way runs but not yet field-validated — preview with a dry run first.

> Full flag reference: [`docs/Guides/auto-debate.md`](../../docs/Guides/auto-debate.md).
> Not launching a debate but **participating** in one? See the
> [`agent-chat`](../../skills/agent-chat/SKILL.md) skill and
> [`../Kickoff/kickoff.md`](../Kickoff/kickoff.md).
