# Group-Themed (restrict the cast to one persona group)

Same auto-debate, but personas are drawn only from a **single group** instead of
the whole roster (the skill passes `-Group` to `debate.ps1`). Group names are
dynamic — read from the DB; quote names that contain spaces.

> **Groups in the DB right now:**
> - `"Celebrities"` → Elon Musk · Gordon Ramsay · Steve Irwin
> - `"Fictional Characters"` → Charlie Kelly · Dennis Reynolds · Dr. Gregory House ·
>   Dwight Schrute · Heisenberg · Jesse Pinkman · Michael Scott · Rick Sanchez
> - `"Political Figures"` → Barack Obama
>
> Check live:
> ```powershell
> .\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
> ```

## 1. All-Celebrities head-to-head, random cast

```text
Use the start-debate skill to start a 2-agent debate using the Celebrities group.
Topic: "Is a relentless work ethic worth the personal cost?" Let the script cast
the personas at random.
```

## 2. Fictional Characters free-for-all (3 agents)

```text
Use the start-debate skill to start a 3-agent debate using the "Fictional
Characters" group, with claude-code, antigravity, and codex. Pick the topic and
the personas at random from that group.
```

## 3. Celebrities, surprise me

```text
Use the start-debate skill to start a debate restricted to the Celebrities group.
Pick the topic, the number of debaters, and the personas all at random.
```

## 4. Fictional Characters, two CLIs, your topic

```text
Use the start-debate skill to start a head-to-head debate using the "Fictional
Characters" group between claude-code and opencode. Topic: "Should we trust
people who are certain they're always right?"
```
