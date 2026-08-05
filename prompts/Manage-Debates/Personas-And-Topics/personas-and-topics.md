# Personas & Topics (browse the cast and the topic library)

Prompts for inspecting the persona roster and the topic library *before* you launch
— so you can pick a good matchup. Personas live in the `personas` table (managed via
`src/orchestrator/personas.py` or the web UI `/personas` page — the table is synced,
so management works on the hosted mirror too, subject to its read-only mode). Topics
live in `docs/Chat-Topics/Topics.md`, where used ones are checked off with ✅.

## 1. Who's available to cast?

```text
List every debate persona grouped by group, by running:
.\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
Then show me the persona names under each group.
```

## 2. Tell me about one persona

```text
Show me the full persona card for <slug-or-name> (e.g. gordon-ramsay) by running:
.\.venv\Scripts\python.exe src\orchestrator\personas.py get <slug-or-name> --all-groups --body
```

## 3. What topics haven't we used yet?

```text
Read docs/Chat-Topics/Topics.md and list the topics that are NOT yet checked off
with ✅ — those are the ones a random auto-debate can still pick. Group them by the
section headers.
```

## 4. Suggest a great matchup

```text
Looking at the available personas and the unused topics, suggest 3 fun debate
matchups (topic + which personas on which CLIs), then write the ready-to-paste
start-debate prompt for whichever one I pick.
```

## 5. Re-seed personas after editing cards

```text
I edited the persona card files under agents/Debate-Agents/. Re-import them into
the personas table (the runtime source of truth) by running:
.\.venv\Scripts\python.exe src\orchestrator\personas.py import --overwrite
Then list the groups to confirm the new counts.
```

> [!NOTE]
> `--overwrite` replaces the card text but **keeps any avatar** uploaded on
> `/personas` — the seed cards carry no image, so the row's existing art is
> carried across rather than blanked. See
> [`personas.md` → Avatars](../../../docs/App/personas.md#avatars).

## 6. Give a persona a picture

```text
Open http://127.0.0.1:8765/personas, select <slug-or-name>, and use
Choose image… in the Avatar row, then Save. Or import a card and its image
together — a .zip of <persona>.md + <persona>.png lands both at once.
```
