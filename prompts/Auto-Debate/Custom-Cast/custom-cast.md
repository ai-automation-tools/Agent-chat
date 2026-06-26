# Custom-Cast (force exact personas AND exact CLIs)

Full control: name every persona, every CLI, and who opens. The skill maps these to
`debate.ps1`'s `-Personalities` + `-Cli` flags. **Persona count must match CLI
count;** the first CLI listed is the opening speaker.

> **Persona slugs** (display names work too — the registry is forgiving):
> `elon-musk` · `gordon-ramsay` · `steve-irwin` ·
> `charlie-kelly-from-its-always-sunny-in-philadelphia` ·
> `dennis-from-its-always-sunny-in-philadelphia` · `gregory-house` ·
> `dwight-schrute-from-the-office` · `heisenberg-from-breaking-bad` ·
> `jesse-pinkman-from-breaking-bad` · `michael-scott-from-the-office` ·
> `rick-sanchez` · `barack-obama`
> **CLIs:** `claude-code` · `antigravity` · `codex` · `kimi` · `opencode`

## 1. Mentor vs protégé (Heisenberg vs Jesse)

```text
Use the start-debate skill to start a debate between claude-code and codex, where
claude-code = Heisenberg and codex = Jesse Pinkman. Topic: "Do the ends ever
justify the means?" Make it 10 turns.
```

## 2. Four-CLI free-for-all

```text
Use the start-debate skill to start a 4-agent debate using claude-code,
antigravity, codex, and kimi, cast as Elon Musk, Barack Obama, Dr. Gregory House,
and Dwight Schrute respectively. Topic: "Will AI create more jobs than it
eliminates?"
```

## 3. Pin the opener (codex speaks first)

```text
Use the start-debate skill to start a head-to-head debate between codex and
claude-code (codex opens), where codex = Rick Sanchez and claude-code = Steve
Irwin. Topic: "Is human extinction something we should actually worry about?"
```

## 4. Exact slugs, exact CLIs

```text
Use the start-debate skill to start a debate between claude-code and opencode,
casting claude-code = michael-scott-from-the-office and
opencode = dwight-schrute-from-the-office. Topic: "Should gene editing be allowed
for non-medical enhancements?"
```

## 5. Five-way blowout (all CLIs)

```text
Use the start-debate skill to start a 5-agent debate using claude-code,
antigravity, codex, kimi, and opencode, cast as Gordon Ramsay, Charlie Kelly,
Dennis Reynolds, Rick Sanchez, and Barack Obama. Pick the topic at random.
```

> **Note:** 4- and 5-CLI runs add `kimi`/`opencode` — wired but not yet
> field-validated. Preview with `-DryRun` first.
