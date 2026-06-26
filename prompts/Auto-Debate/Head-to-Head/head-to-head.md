# Head-to-Head (2 debaters, 2 CLIs)

Two personas, two CLIs, one topic — the simplest debate shape. Copy any block
below and paste it into Claude Code; it triggers the
[`start-debate`](../../../skills/start-debate/SKILL.md) skill (which previews with
`-DryRun`, then launches `scripts/debate.ps1`).

> **Real cast** — personas in the DB right now:
> **Celebrities:** Elon Musk · Gordon Ramsay · Steve Irwin •
> **Fictional Characters:** Charlie Kelly · Dennis Reynolds · Dr. Gregory House ·
> Dwight Schrute · Heisenberg (Walter White) · Jesse Pinkman · Michael Scott · Rick Sanchez •
> **Political Figures:** Barack Obama.
> **CLIs:** `claude-code` · `antigravity` · `codex` · `kimi` · `opencode`.

## 1. Ramsay vs House on AI cooking

```text
Use the start-debate skill to start a head-to-head debate between claude-code and
codex, where claude-code = Gordon Ramsay and codex = Dr. Gregory House. Topic:
"Should restaurants be required to disclose when a dish was designed by AI?"
```

## 2. Musk vs Obama on AI licensing

```text
Use the start-debate skill to start a 2-agent debate between claude-code and
antigravity, where claude-code = Elon Musk and antigravity = Barack Obama.
Topic: "Should governments require licenses for advanced AI development?"
```

## 3. Heisenberg vs Dennis — the manipulators

```text
Use the start-debate skill to start a head-to-head between claude-code and
opencode, where claude-code = Heisenberg and opencode = Dennis Reynolds. Topic:
"Is it ever rational to lie to someone for their own good?" Make it 10 turns.
```

## 4. Steve Irwin vs Rick Sanchez on space

```text
Use the start-debate skill to start a debate between claude-code and codex, where
claude-code = Steve Irwin and codex = Rick Sanchez. Topic: "Should humanity
prioritize protecting Earth's ecosystems over colonizing Mars?"
```

## 5. Dwight vs Michael Scott — let the script pick the topic

```text
Use the start-debate skill to start a head-to-head debate between claude-code and
antigravity, where claude-code = Dwight Schrute and antigravity = Michael Scott.
Pick the debate topic at random.
```
