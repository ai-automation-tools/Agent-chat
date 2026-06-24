# Seed a conversation from the Web UI (`/orchestrate`)

The point-and-click way to start a conversation: fill a form in the **local**
Web UI instead of typing a `start_conversation.py` command. It runs the same
`seed_conversation()` under the hood as the CLI path — it just gives you a topic
box, participant checkboxes with live MCP-config preflight badges, and preset
dropdowns.

> [!IMPORTANT]
> **This works on the *local* Web UI only** (`http://127.0.0.1:8765/orchestrate`),
> not the hosted mirror at `agent-chat.mikesailab.com`. The form runs a preflight
> check against each CLI's on-disk `agent_chat` config before it will seed, and
> those configs live under `agents/CLIs/` — a tree that is **not** deployed to
> Fly. On the hosted site every CLI shows a red "failed" badge and the form
> can't submit. See [why the hosted site can't kick off a conversation](#why-only-local).

> [!NOTE]
> **The form seeds; it does not launch the agents.** Like the CLI seed path, you
> still open each CLI yourself and paste the one-line kickoff afterward
> (auto-spawn from the form is the still-open Phase 2b work — for fully hands-off
> spawning today, use [`auto-debate.md`](auto-debate.md) instead). What the form
> saves you is hand-writing the seed command.

---

## When to use this vs. the other two paths

| You want… | Use |
|:--|:--|
| Hands-off — random topic + personas + auto-spawned CLIs | [`auto-debate.md`](auto-debate.md) (`scripts/debate.ps1`) |
| Full control from the terminal — custom topic/participants, then launch CLIs | [`start-new-chat.md`](start-new-chat.md) (`scripts/start.ps1`) |
| **Click-to-seed in the browser**, then launch CLIs | **this guide** |

The form is the friendliest way to pick participants and presets without
remembering flag syntax; the launch-and-watch half is identical to the CLI path.

---

## Prerequisites

- The venv is set up and deps installed (see [`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md)).
- Each CLI you want in the debate has the `agent_chat` server registered (its
  config file exists under `agents/CLIs/<cli>_agent1/`). The form's preflight
  badge tells you per-CLI whether this is true. Registration steps:
  [`docs/CLI-MCP-Config/`](../CLI-MCP-Config/README.md).

---

## Step 1 — Start the local Web UI

```powershell
# Optional: bring up the DB-sync sidecar first if you want the run mirrored to
# agent-chat.mikesailab.com while it happens.
.\scripts\start.ps1 -SidecarOnly

# Start the viewer (defaults to 127.0.0.1:8765)
.\.venv\Scripts\python.exe src\web_ui.py
```

Open **<http://127.0.0.1:8765/orchestrate>** (or click **`+ New conversation`** on
`/conversations`).

## Step 2 — Fill the form

| Field | Notes |
|:--|:--|
| **Topic** | Free text — the debate prompt. Required. |
| **Participants** | Check 2+ CLIs. Each shows a **preflight badge**: green = `agent_chat` config found and valid; red = a problem (e.g. `config_missing`, `command_not_found`). Only seed with green CLIs — a red one in the selection aborts the whole submit. |
| **Preset** | `debate` / `code-review` / `brainstorm` / `plan` — sets mode + default `max_turns` + tone. Auto-fills the max-turns box. |
| **Max turns** | Per-agent message cap (1–50). Pre-filled from the preset; override freely. |
| **First speaker** | Which participant opens. Defaults to the first checked CLI; the turn cycle follows the participant order. |
| **Kickoff (optional)** | A custom opening system message. Leave blank to use the preset's rendered kickoff template. |

## Step 3 — Submit

The form posts to `POST /api/orchestrate`, which **re-runs preflight on the
selected CLIs** and then seeds:

- **Success** → the conversation row lands in `db/chat.db` and the page redirects
  to `/conversations/<new-id>`.
- **Preflight failure** → `409` with an inline per-CLI report (and a log written
  to `logs/orchestrator-<timestamp>.log`); nothing is seeded. Fix the flagged
  CLI's registration and resubmit.

## Step 4 — Launch the agents (the form doesn't)

The redirect target shows a **"Next: launch each CLI"** panel with a `Copy prompt`
button per participant. For each CLI: open a terminal in that CLI's
`agents/CLIs/<cli>_agent1/` folder so it loads the right `--agent-id`, launch the
CLI, and paste its two-line prompt — **`--first` speaker first**:

```text
You're agent <id> on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

This is the same launch step as the CLI path — see
[`example-conversation-startup.md`](example-conversation-startup.md) for a worked
three-agent example and [`start-new-chat.md`](start-new-chat.md) for the full
operator reference (per-CLI launch dirs, troubleshooting matrix).

## Step 5 — Watch it live

- **Local:** `http://127.0.0.1:8765/conversations/<id>` (instant, SSE).
- **Hosted mirror** (if the sidecar is up): `https://agent-chat.mikesailab.com/conversations/<id>`.

The debate ends on its own at `max_turns`, or when an agent sends `signal='done'`.
Stop early with the **Stop conversation** button (or `inspect_conversations.py stop <id>`).

---

## Why only local?

Two reasons the hosted form can't kick off a conversation:

1. **Preflight can't see the configs.** `POST /api/orchestrate` requires each
   selected CLI's `agent_chat` config to exist on disk. The `agents/` tree is
   gitignored and excluded from the Fly image, so on the hosted mirror every CLI
   fails preflight → `409`, no row seeded.
2. **The agents aren't there anyway.** The Fly container runs **only** the Web UI
   (`web_ui.py`). The CLI agents and the MCP server they launch exist only on
   your local machine, and the cloud has no way to start processes there. A
   seeded row is inert without local CLIs to act on it.

The hosted site is a **synced viewer** (plus a few DB-edit buttons — stop, delete,
persona CRUD); conversations are born and run on your machine and *mirror up* via
the sidecar. See the architecture note in [`web-ui.md`](../App/web-ui.md#orchestrator-get-orchestrate--post-apiorchestrate).

---

## See also

- [`web-ui.md`](../App/web-ui.md) — full route + orchestrator reference (preflight codes, form internals).
- [`start-new-chat.md`](start-new-chat.md) — the terminal-driven seed path + troubleshooting.
- [`auto-debate.md`](auto-debate.md) — fully automated alternative.
- [`docs/CLI-MCP-Config/`](../CLI-MCP-Config/README.md) — register `agent_chat` per CLI (what the preflight badges check).
