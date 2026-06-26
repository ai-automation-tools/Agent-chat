# Three-Way (3 debaters, 3 CLIs)

Three personas across three CLIs. The **first CLI named opens** the debate. Copy a
block into Claude Code to trigger the
[`start-debate`](../../../skills/start-debate/SKILL.md) skill (preview with
`-DryRun`, then launch).

> CLI preference order if you don't name them: `claude-code, antigravity, codex`.
> Real CLIs: `claude-code` · `antigravity` · `codex` · `kimi` · `opencode`.

## 1. The original 3-way (Scott / Musk / Obama)

```text
Use the start-debate skill to start a debate between claude-code, codex, and
antigravity, where claude-code = Michael Scott, codex = Elon Musk, and
antigravity = Barack Obama. Pick the debate topic at random.
```

## 2. AI in government, three takes

```text
Use the start-debate skill to start a 3-agent debate between claude-code, codex,
and antigravity, where claude-code = Barack Obama, codex = Heisenberg, and
antigravity = Dr. Gregory House. Topic: "Will AI eventually become a trusted
decision-maker in government?"
```

## 3. Chaos panel on social media

```text
Use the start-debate skill to start a debate between claude-code, antigravity,
and codex, where claude-code = Charlie Kelly, antigravity = Rick Sanchez, and
codex = Dennis Reynolds. Topic: "Should children under 16 be banned from social
media?"
```

## 4. Perfection vs id vs ego (Ramsay / Charlie / Dennis)

```text
Use the start-debate skill to start a 3-way debate between claude-code, codex,
and antigravity, where claude-code = Gordon Ramsay, codex = Charlie Kelly, and
antigravity = Dennis Reynolds. Topic: "Does relentless pursuit of excellence do
more harm than good?" Make it 10 turns.
```

## 5. Surprise cast, 3 agents

```text
Use the start-debate skill to start a random 3-agent debate. Pick the topic and
all three personas at random across all groups, using claude-code, antigravity,
and codex.
```
