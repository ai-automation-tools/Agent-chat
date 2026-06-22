# `debate-mode` skill

A layered Agent Skill that teaches a CLI agent how to **argue a position** inside an `agent_chat` debate — composing on top of the base [`agent-chat`](../agent-chat/) skill which handles the participation loop.

Three core teachings:

1. Argue a position; don't survey the question.
2. Cite the other side specifically (quote, engage, no strawmen).
3. Concede partial points where warranted, hold ground where you can.

Anti-patterns to avoid (each turn must advance the argument):

- "That's a great point" / "I think you raise an interesting question"
- "There are valid arguments on both sides"
- Restating your previous position with more words

See [`SKILL.md`](SKILL.md) for the full guidance and the canonical example conversation.

## Install

`debate-mode` lives alongside `agent-chat` under the repo-root `skills/` folder, so the recommended install wires both at once.

### Recommended: run the setup-link script once per clone

```powershell
# Windows — junctions every CLI's skills dir to repo-root skills/ (agent-chat + debate-mode)
.\scripts\setup\setup-skill-links.ps1
```

```bash
# macOS/Linux
./scripts/setup/setup-skill-links.sh
```

This links the repo-root `skills/` into each CLI's per-clone, gitignored config dir — `.claude/skills` (Claude Code), `.codex/skills` (Codex), `.agents/skills` (Antigravity), `.gemini/skills` (Gemini, deprecated fallback). Edits to `skills/debate-mode/SKILL.md` then propagate to every CLI. Re-run once per clone.

### Manual install (per-CLI reference)

Same per-CLI discovery paths as the base `agent-chat` skill — see [`../agent-chat/README.md`](../agent-chat/README.md). Substitute `debate-mode` wherever `agent-chat` appears:

```powershell
# Claude Code (project-local)
New-Item -ItemType Directory -Force "$PWD/.claude/skills/debate-mode" | Out-Null
Copy-Item "$PWD/skills/debate-mode/SKILL.md" "$PWD/.claude/skills/debate-mode/SKILL.md"

# Codex (project-local — .agents/skills/ is the standard path; .codex/skills/ also works empirically)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/debate-mode" | Out-Null
Copy-Item "$PWD/skills/debate-mode/SKILL.md" "$PWD/.agents/skills/debate-mode/SKILL.md"

# Antigravity (project-local — .agents/skills/)
New-Item -ItemType Directory -Force "$PWD/.agents/skills/debate-mode" | Out-Null
Copy-Item "$PWD/skills/debate-mode/SKILL.md" "$PWD/.agents/skills/debate-mode/SKILL.md"
```

Verify with `/skills` — both `agent-chat` and `debate-mode` should appear in the list.

## Verify end-to-end

Seed a debate conversation:

```powershell
.\.venv\Scripts\python.exe src\start_conversation.py `
  --participants claude-code,codex `
  --topic "Should startups still write code by hand in 2027?" `
  --preset debate `
  --max-turns 4
```

In each CLI, give a one-line prompt: `join the agent_chat conversation`. Each agent should:

1. Open with a clear position (not a survey)
2. Quote or paraphrase the other side's specific argument
3. Concede or counter — no hedging filler

If you see "that's a great point" anywhere in the transcript, the skill isn't loading or the model is ignoring it. Recheck `/skills` first; if `debate-mode` is listed but the language is still hedged, the kickoff body may need a stronger reference to debate-mode in the tone block.

## Composes with `agent-chat`

`agent-chat` covers the loop mechanics (when to call which tool, how to use signals). `debate-mode` covers the content shape. Install both. The skills' frontmatter `description` fields are distinct enough that they don't conflict — each fires on its own triggers, and Claude Code, Codex, and Antigravity all support multiple active skills per session.
