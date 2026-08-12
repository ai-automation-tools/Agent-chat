<div align="center">

# 🧰 CLI setup

**Which CLI tools this machine has — and why one is enough**

</div>

---

Agent-Chat supports six CLIs. It does not require six. It requires **one**.

That sentence used to be true of the code and false of the interface. Every
surface assumed the full registry: `/orchestrate` listed seat 1 of every
supported tool whether or not you owned it, so a fresh clone met six rows and
five red failures with no statement of what to do about them; `debate.ps1` took
the first N keys of its `$Clis` table and hoped; the homepage advertised "6
CLIs" as though that were the entry price.

This is the machinery that fixed that: [`src/orchestrator/availability.py`](../../src/orchestrator/availability.py),
the `/setup` page, and the seat planner they share.

---

## The model: detect, then let the operator confirm

Two separate questions, deliberately kept apart.

| | What it is | Where it lives |
|:---|:---|:---|
| **Detect** | A probe, re-run on every call. Is the launcher binary on `PATH`? Does this tool's `agent_chat` MCP entry pass [preflight](web-ui.md#preflight-checks-per-cli)? | `availability.detect()` / `detect_all()` |
| **Declare** | What the operator said, persisted to JSON. | `config/available-clis.json` |

**Declaration overrides detection in both directions.** "I do have Codex, it's
just not registered yet" and "ignore Gemini, I'm never using it" are both things
a probe cannot know. Until the operator answers, detection stands in.

Three states, and the difference between the last two matters:

| State | `load_declared()` | Meaning |
|:---|:---|:---|
| No file | `None` | Never answered — fall back to detection, and say so on the form. |
| `{"available": []}` | `[]` | "I have nothing wired up yet." A real answer. Stop guessing. |
| `{"available": ["claude-code"]}` | `["claude-code"]` | Offer exactly this. |

A malformed or unreadable file degrades to `None`, **not** to `[]` — falling
back to "nothing available" on a corrupt file would leave the operator with a
dead form; falling back to detection is recoverable.

### The file

```json
{
  "version": 1,
  "updated_at": "2026-08-12T14:02:11+00:00",
  "available": ["claude-code", "codex"]
}
```

`config/available-clis.json`, or wherever `$AGENT_CHAT_CLI_CONFIG` points.
**Gitignored** — this is per-machine setup, not source; committing it would hand
every clone one box's tool list. Order is normalised to registry order on save,
so the file reads the same whichever order the boxes were ticked in.

### Launcher binaries

`CLI_BINARIES` maps each tool to the executables to probe. These are the names
[`scripts/lib/spawn-agents.ps1`](../../scripts/lib/spawn-agents.ps1) actually
launches, and `tests/test_availability.py` pins the two lists together —
detecting a CLI under one name and launching it under another is a silent
failure where setup says "on PATH" and the launcher says "not found".

| Tool | Probes for |
|:---|:---|
| `claude-code` | `claude` |
| `codex` | `codex` |
| `antigravity` | `agy`, `antigravity` |
| `kimi` | `kimi` |
| `opencode` | `opencode` |
| `gemini` | `gemini` (deprecated — detected, never proposed) |

---

## Why one CLI is enough: seat planning

A **seat** is configuration, not a program (see
[`orchestrator/seats.py`](../../src/orchestrator/seats.py)). Seat 1 of a tool
keeps the bare id; seat 2 is `claude-code-2`, launched from its own folder whose
MCP config passes its own `--agent-id`. The message bus never cared what program
is on the other end.

So `plan_seats(clis, count)` deals seats **round-robin**: one per tool first,
then a second on each.

```python
plan_seats(["claude-code"], 2)            # ['claude-code', 'claude-code-2']
plan_seats(["claude-code", "codex"], 2)   # ['claude-code', 'codex']
plan_seats(["claude-code", "codex"], 3)   # ['claude-code', 'codex', 'claude-code-2']
```

Round-robin rather than filling one tool at a time is the whole point of the
middle line: **two tools and two debaters must still be one seat each**, because
that was the behaviour before any of this existed and nothing should change for
an operator who was already set up.

Capacity is `len(clis) × MAX_SEATS_PER_CLI` (5 per tool), and a conversation
caps at 5 participants anyway — so one CLI can fill any conversation this app
can seed.

### Missing seat folders

A planned seat past the first needs `agents/CLIs/<cli>_agent<N>/` to exist.
`missing_seat_folders()` reports which don't, and `/setup` offers to create them
by calling `add_seat()` from
[`scripts/setup/add_agent_seat.py`](../../scripts/setup/add_agent_seat.py)
**in process** — a web request that shells out to a script is a different thing
to reason about, and this one only ever writes inside `agents/CLIs/`.

Seat 1 is never reported as missing. Its folder is part of registering the CLI
at all, so its absence is a preflight failure with its own advice, not something
to paper over by cloning.

> [!WARNING]
> **Codex seats need their own login.** Codex ignores per-folder config, so an
> extra seat only gets its own `--agent-id` by relocating `CODEX_HOME` — which
> moves credentials with it. `/setup` says so after creating one; the spawn
> layer exports the variable at launch. See
> [Per-CLI: Codex](../CLI-MCP-Config/Per-CLI/codex.md).

---

## What reads it

| Consumer | Behaviour |
|:---|:---|
| `GET /orchestrate` | Lists only seats on available tools (`available_seats()`). Banners above the participant list for the three states worth interrupting on: no CLI at all, exactly one seat, or never-declared. A settled two-plus-seat setup gets **silence** — the point is to stop nagging people who are set up. |
| `GET /` | The hero's CLI stat is the count of *your* CLIs locally (amber at 0 or 1, with a matching prompt under the CTA) and the registry size on the hosted mirror, where no one's machine is being described. |
| `scripts/debate.ps1` | Defaults its seat set from the same JSON via `Get-AvailableCliIds` + `Get-PlannedSeats`, and throws early — naming the exact command — if a planned seat has no folder yet. An explicit `-Cli` list overrides all of it. |
| `POST /api/orchestrate` | **Nothing.** Availability is advisory; preflight stays the authoritative gate, so a stale declaration can never seed a conversation that can't run. |

---

## The page

`GET /setup` — one row per supported tool: a tick the operator owns, and the two
probe results as pills (`on PATH` / `no claude`, `MCP config OK` /
`MCP config config_missing`). A failing config check expands into the preflight
detail plus a link to that CLI's registration doc.

Below it, a live preview of what the current ticks buy: the exact seat list a
2- and 3-agent run would use, a note when one tool is doing the work of two,
and — when the plan needs folders that don't exist — a button to create them.

Nothing on this page installs a CLI or edits an MCP config. When a tool needs
registering, the answer is a link to
[`docs/CLI-MCP-Config/`](../CLI-MCP-Config/README.md), not a mutation of the
operator's machine.

**Hosted:** a local-only explainer. Which CLIs you have is a fact about your own
computer; a Fly machine has no `PATH` worth probing and nothing to save. The two
POSTs `403` through `ReadOnlyMiddleware` by method, with no path list to keep in
sync.

---

## Tests

[`tests/test_availability.py`](../../tests/test_availability.py) — 31 cases: the
three declaration states, malformed-file degradation, declaration overriding
detection both ways, the `plan_seats` round-robin (including the two-tool
no-change case), the `/setup` page and API, `/orchestrate` filtering, and the
`CLI_BINARIES` ↔ `spawn-agents.ps1` parity check.

---

<div align="center">

[⬅️ App docs](README.md) &nbsp;·&nbsp; [🏠 Docs home](../README.md) &nbsp;·&nbsp; [📦 Repo root](../../README.md)

</div>
