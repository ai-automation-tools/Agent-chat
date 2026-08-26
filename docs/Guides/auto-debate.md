# Auto-launch a debate (`scripts/debate.ps1`)

One command that picks a topic, casts random debate personas, seeds the
conversation, and **launches a CLI per persona already prompted in
character** — the hands-off version of
[`start-new-chat.md`](start-new-chat.md). Where that guide is the manual
daily-driver (seed, then paste a prompt into each CLI yourself), this one
does the whole thing for you.

---

## TL;DR

```powershell
# Preview only — picks topic + personas + prints the launch plan, opens nothing,
# writes nothing:
.\scripts\debate.ps1 -DryRun

# For real — seed, check the topic off the list, and launch every CLI hands-off:
.\scripts\debate.ps1 -SkipPermissions
```

`-SkipPermissions` is what makes it truly hands-off — without it, Claude Code
will prompt you to approve the `agent_chat` tools on the first turn.

---

## Prerequisites

Same as a manual run — see [`start-new-chat.md` Prerequisites](start-new-chat.md):

- Local venv + `requirements.txt` installed.
- All three CLIs (`claude`, `agy`, `codex`) on PATH, each with the
  `agent_chat` MCP server registered against this repo's `db/chat.db`
  (per-CLI guides under [`docs/CLI-MCP-Config/`](../CLI-MCP-Config/)).
- *(Optional)* DB-sync env vars, if you run a self-hosted mirror of the web UI —
  `start.ps1` brings the `scripts/db_sync.py` sidecar up automatically. Nothing
  about a debate depends on it.

> [!NOTE]
> The launch step depends on each CLI's exact flags. As wired today:
> `claude --dangerously-skip-permissions "<prompt>"`,
> `agy --dangerously-skip-permissions -i "<prompt>"`, `codex --yolo "<prompt>"`. If a CLI
> upgrade changes a flag, edit the `$Clis` table at the top of
> `scripts/debate.ps1` — every per-CLI launch detail lives there.

---

## What it does, step by step

1. **Pick a topic** at random from `docs/Chat-Topics/Topics.md` (the
   100-topic library). Already-used topics — those carrying a ✅ marker —
   are skipped. Override with `-Topic "..."` to force a specific one.
2. **Decide the debater count** from that topic's `- Debaters: N` line, then
   **deal that many seats over the CLIs you actually have.**

   Availability comes from `config/available-clis.json` — what you ticked on
   [`/setup`](../App/cli-setup.md) — or, with no answer saved, from probing each
   launcher on your `PATH`. Seats are dealt round-robin, one per tool before any
   tool gets a second:

   | You have | 2 debaters | 3 debaters |
   |:---|:---|:---|
   | all five tools | `claude-code` · `antigravity` | + `codex` |
   | claude-code + codex | `claude-code` · `codex` | + `claude-code-2` |
   | claude-code only | `claude-code` · `claude-code-2` | + `claude-code-3` |

   A seat past the first needs its config folder; if one is missing the script
   stops **before** seeding and prints the exact `add_agent_seat.py` command (or
   use the button on `/setup`).

   Override the count with `-Agents 2|3|4|5`. Topics with no `Debaters:` line
   fall back to `-DefaultAgents` (default `2`). To force an **exact seat set and
   order**, bypassing availability entirely, pass `-Cli` — e.g.
   `-Cli claude-code,opencode` for a head-to-head; the first entry is the
   `--first` speaker. (4-/5-agent rotation and the opencode auto-spawn row are
   wired but not yet validated in a live run.)
3. **Cast personas** — ask the shared persona registry
   (`src/orchestrator/personas.py`) for the roster, pick N **at random**, and map
   them to the CLIs in order (`claude-code`, `antigravity`, `codex`,
   `opencode`). **By default the random draw spans ALL persona groups** in the DB;
   pass `-Group <name>` to restrict it to one group (see
   [Changing the persona pool](#changing-the-persona-pool) below). Force specific
   personas with `-Personalities billy-bob,crypto-chad` (each a slug or display
   name resolved through the registry). Persona **bodies are read from the DB**
   (the `personas` table), not from the `agents/Debate-Agents/` card files — the
   script never opens those.
4. **Seed** via `scripts/start.ps1 --preset debate` (so the DB-sync
   sidecar comes up too) and capture the new conversation id.
5. **Check the topic off** — on a successful seed, append a marker to the
   topic's line in `Topics.md` so it won't be picked again:
   ```
   1. Should AI-generated content be clearly labeled everywhere online? ✅ <!--used 2026-06-16 conv#42-->
   ```
6. **Write a prompt file per agent** under `db/launch/conv<id>-<cli>.txt`
   — the persona body plus in-character kickoff instructions.
7. **Launch** one terminal window per agent (the `--first` speaker first,
   ~1.5s apart). Each window `cd`s into the agent's CLI folder (so its MCP
   config + role doc load) and starts the CLI with a tiny opener:
   *"Read the file at `<path>` and follow it."* The persona never rides on
   the command line, so there's nothing to mis-quote.

The shared `get_kickoff()` template (from `--preset debate`) carries the
debate loop + tone; the **persona** is injected here at launch because
`get_kickoff()` returns one template for the whole conversation. No schema
change.

---

## Watch it run

The final output prints the live URLs:

```
http://127.0.0.1:8765/conversations/<id>          # local
https://agent-chat.mikesailab.com/conversations/<id>   # hosted (needs sidecar)
```

Same live view, inspector commands, and end-of-run/export flow as a manual
run — see [`start-new-chat.md` §2, §4, §5](start-new-chat.md).

---

## Records: what ran, and which persona each CLI played

Three artifacts, each answering a different question:

| Want to see… | Look at |
|:---|:---|
| **Which persona each CLI played** (+ topic, per run) | `logs/debate-history.log` — one block per run with the timestamp, `conv#<id>`, debater count, topic, and the `cli <- Persona [file.md]` cast. Greppable: `Select-String 'conv#22' logs\debate-history.log`. |
| **The exact prompt an agent received** | `db/launch/conv<id>-<cli>.txt` — the full persona body + kickoff instructions handed to that CLI. Header line: `=== YOUR PERSONA: <Name> ===`. |
| **The debate transcript itself** | The DB — `inspect_conversations.py show <id>`, the web UI, or **Export Conversation**. The history log and prompt files deliberately do **not** duplicate message content. |

Example `logs/debate-history.log` entry:

```
=== 2026-06-16 12:20:00 | conv#22 | 2 debaters | max_turns=debate-preset (8) ===
topic: Has social media made people less happy overall?
  claude-code  <- Crypto Chad  [crypto-chad.md]
  antigravity  <- Chad "Alpha" Chadson  [chad-alpha-chadson.md]
```

> [!NOTE]
> Both `db/` and `logs/` are gitignored, so these records stay local. The
> log is append-only — it's never rotated automatically; trim it by hand if
> it grows large.

---

## Options

| Flag | Effect |
|:---|:---|
| `-DryRun` | Do everything except seed + open windows. Prints the topic, persona→CLI mapping, prompt-file paths, and the exact launch command per agent. Writes nothing. **Run this first.** |
| `-SkipPermissions` | Append each CLI's skip-approval flag so the run is fully hands-off. |
| `-Topic "..."` | Force a topic instead of random selection. (A forced topic is **not** checked off, since it may not be in the file.) |
| `-Agents 2\|3\|4\|5` | Force the debater count, overriding the topic's `Debaters:` line. `4` adds `opencode`; `5` has no 5th tool to reach for, so the seat planner deals a second seat on a tool already in play (e.g. `claude-code-2`). Both wired but not yet field-validated. |
| `-Cli a,b[,c…]` | Force the exact seat set **and** order (e.g. `claude-code,opencode`), bypassing the availability check and the round-robin seat plan. First entry = `--first` speaker; sets the debater count from its length (don't also pass a conflicting `-Agents`). Each id must be a registered CLI (`claude-code`, `antigravity`, `codex`, `opencode`) or a numbered seat on one (`codex-2`). |
| `-DefaultAgents N` | Count to use when a topic has no `Debaters:` line. Default `2`. |
| `-Personalities a,b[,c]` | Force personas by slug or display name (e.g. `crypto-chad` or `"Crypto Chad"`; a trailing `.md` is tolerated), resolved through the persona registry. Count must match the agent count. |
| `-Group <name>` | **Optional** filter — restrict the random draw to one `"group"` value in the DB `personas` table (e.g. `-Group "Fictional Characters"`). **Omitted (default): draw from ALL groups.** Auto-discovered; casting reads the DB, not the folder. See [Changing the persona pool](#changing-the-persona-pool). |
| `-MaxTurns N` | Per-agent message cap. Default: the `debate` preset's `8`. |
| `-TopicsGlob <glob>` | Topic-library file(s), relative to repo root. Default `docs/Chat-Topics/Topics.md`. |
| `-ForceSidecar` | Forwarded to `start.ps1` as `-Force` (kill + relaunch the DB-sync sidecar). |

### Examples

```powershell
# Force a specific 3-way debate with chosen personas and a longer run
.\scripts\debate.ps1 -Topic "Should humanity prioritize Mars colonization?" `
  -Agents 3 -Personalities pastor-cole,new-age-nadia,dr.-evelyn-vance `
  -MaxTurns 12 -SkipPermissions

# Random topic but always two debaters
.\scripts\debate.ps1 -Agents 2 -SkipPermissions

# Random topic, but draw personas only from one group
.\scripts\debate.ps1 -Agents 2 -Group "Fictional Characters" -SkipPermissions
```

---

## Changing the persona pool

By default the random cast is drawn from **every** persona group in the DB
`personas` table. Two ways to scope it:

- **Per run** — pass `-Group <name>` to restrict the draw (and `-Personalities`
  resolution) to one group, e.g. `-Group "Celebrities"`. List what groups exist:
  ```powershell
  .\.venv\Scripts\python.exe src\orchestrator\personas.py list --all-groups | ConvertFrom-Json | Group-Object group | Select-Object Name, Count
  ```
- **Change the default** — edit `scripts/debate.ps1`:
  - To make a specific group the default, give the `$Group` param a default value:
    `[string] $Group = 'Unique-Personas',`.
  - The all-groups-vs-one-group switch lives in **§3 "Pick personas"** — the
    `Get-Personas list --all-groups` / `--group $Group` branch. Swap or extend it
    there (e.g. to exclude a group like `Debate-Hosts` from the default pool).

> [!NOTE]
> With no `-Group`, the pool includes **every** group — including `Debate-Hosts`
> (the moderator roster). Pass a `-Group` if you want moderators kept out of the
> debater draw.

---

## Managing the topic list

- **Un-check one topic:** delete the trailing ` ✅ <!--...-->` from its line
  in `docs/Chat-Topics/Topics.md`.
- **Reset everything:** find-and-replace the ✅ marker away across the file.
- **All topics used:** the script aborts with a clear message — recycle by
  removing markers, or add new `N. Title` + `- Debaters: N` entries.
- **Add a topic:** append a `N. Title` line followed by an indented
  `- Debaters: 2` (or `3`) line; the parser picks it up automatically.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|:---|:---|:---|
| A CLI window opens then errors on the launch command | That CLI's flag/initial-prompt syntax changed | Edit the `$Clis` table at the top of `scripts/debate.ps1` |
| "could not parse conversation id" | `start.ps1` seed failed (e.g. >1 sidecar running without `-Force`) | Re-run with `-ForceSidecar`, or check the `start.ps1` output above the error |
| "all N topics ... are marked used" | The list is exhausted | Remove ✅ markers in `Topics.md` to recycle |
| Claude keeps prompting for tool approval | Ran without `-SkipPermissions` | Add `-SkipPermissions` |
| Window opens in the wrong folder / MCP server missing | CLI launched outside its `agents/CLIs/<name>_agent1/` folder | The script `cd`s for you; confirm the folder + its MCP config still exist |
| Agent breaks character | Persona injection is a launch-time prompt, not enforced | Lower `-MaxTurns`, or pick stronger-voiced personas from `Debate-Agents/Unique-Personas` |
