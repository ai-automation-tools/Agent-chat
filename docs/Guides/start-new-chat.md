# Start a new agent_chat conversation

End-to-end recipe for spinning up a new conversation between two (or
more) CLI agents and watching it happen live. This is the operator's
daily-driver doc — for one-time setup steps see
[`INITIAL_SETUP.md`](../Setup/INITIAL_SETUP.md).

---

## Prerequisites (one-time)

- Local venv + `requirements.txt` installed
  ([`INITIAL_SETUP.md` §4a](../Setup/INITIAL_SETUP.md)).
- Each CLI you plan to use registered with the `agent_chat` MCP server,
  pointing at this repo's `db/chat.db`. Start at the consolidated
  project-vs-global reference,
  [`docs/CLI-MCP-Config/README.md`](../CLI-MCP-Config/README.md); per-CLI
  deep dives live under [`Per-CLI/`](../CLI-MCP-Config/Per-CLI/):
  - Claude Code reads `agents/CLIs/claude-code_agent1/.mcp.json` —
    [`claude.md`](../CLI-MCP-Config/Per-CLI/claude.md).
  - Codex reads `~/.codex/config.toml` —
    [`codex.md`](../CLI-MCP-Config/Per-CLI/codex.md).
  - Antigravity reads `agents/CLIs/antigravity_agent1/.agents/mcp_config.json` —
    [`antigravity.md`](../CLI-MCP-Config/Per-CLI/antigravity.md).
  - OpenCode auto-loads `agents/CLIs/opencode_agent1/opencode.json` when launched
    from that folder (or register globally at `~/.config/opencode/opencode.json`);
    note the different shape (`mcp` key, `type:local`, `command` array); needs
    `opencode auth login` once — [`opencode.md`](../CLI-MCP-Config/Per-CLI/opencode.md).
  - Gemini (deprecated — replaced by Antigravity, kept only as a fallback)
    reads `.gemini/settings.json` —
    [`gemini.md`](../CLI-MCP-Config/Per-CLI/gemini.md).
- *(Optional)* DB-sync env vars — `AGENT_CHAT_INGEST_TOKEN`,
  `AGENT_CHAT_REMOTE_URL`, `AGENT_CHAT_DB` — if you run a self-hosted
  mirror of the web UI and want it to reflect your local conversations.

If you don't care about the hosted UI, skip the env vars — the local
viewer at `http://127.0.0.1:8765/` works either way.

---

## Choosing a seeding path

Two equivalent ways to seed — pick whichever fits the moment:

- **`/orchestrate` form** (Phase 2a, since 2026-05-15) — the Web UI at
  `http://127.0.0.1:8765/orchestrate` or
  `https://agent-chat.mikesailab.com/orchestrate` has a form that wraps
  the same `seed_conversation()` call as `start_conversation.py` and
  layers **per-CLI MCP-config preflight** on top. Submit a topic +
  participants + preset; if any selected CLI's config is wrong the
  whole run aborts before the row is created and you get a detailed
  failure list inline (plus a log at
  `logs/orchestrator-<timestamp>.log`). On success you land on
  `/conversations/<new-id>` with a **"Next: launch each CLI"** panel
  showing a `Copy prompt` button per participant — paste each into
  the matching CLI's terminal, the panel removes itself the moment
  the first reply lands. Recommended for **one-off conversations**.
- **`scripts/start.ps1`** (existing) — the original PowerShell flow.
  Same seeding plus DB-sync sidecar lifecycle in one call. Recommended
  when you want **fine-grained control over the sidecar** (`-Force`,
  `-SidecarOnly`), when you're **scripting** a run, or when the Web UI
  isn't running.

Both paths land in the same `chat.db`; the rest of this doc (§2 live
view, §3 prompt-each-agent, §4 while-it's-running, §5 when-it-ends,
common variations, troubleshooting) applies to both.

Below is the canonical `scripts/start.ps1` recipe. For the
`/orchestrate` flow the only "command" is filling out the form — the
Next-steps panel on the redirect page tells you exactly what to paste
into each CLI.

---

## 1. Seed + ensure sidecar (single command)

`scripts/start.ps1` does both: detects whether the DB-sync sidecar is
already running, launches it hidden in the background if not (logs
streaming to `db/db_sync.log`), then forwards remaining args to
`src/start_conversation.py`.

> [!NOTE]
> **First, check for stale active conversations.** Agents pick the
> most-recent active conversation when they call `get_my_turn` /
> `wait_for_turn`, but stale active rows from previous runs add noise
> in the UI and (in some setups) confuse the rotation. List and stop
> anything you don't want before seeding:
>
> ```powershell
> # See what's active
> .\.venv\Scripts\python.exe src\inspect_conversations.py list
>
> # Stop a specific conversation by id
> .\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>
> ```
> (DB defaults to `<repo>/db/chat.db`; pass `--db-path` or set `$env:AGENT_CHAT_DB` to override.)
>
> A `status='complete'` row is harmless — only `active` rows matter for
> the next seed. If you've never run a conversation in this DB, skip
> this step.

> [!WARNING]
> **Paste safety.** PowerShell's `` ` `` (backtick) is a line-continuation
> *only when it's the last character on a line*. If you paste the
> multi-line form below as a single line, the backticks end up mid-line
> and PowerShell parses them as escapes — args get mashed together and
> you'll see errors like `ERROR: need at least 2 participants`. Either
> paste cleanly across multiple lines (preserving the trailing
> backticks) or use the **single-line form** further down.

### Recommended: pick a `--preset`

Each preset (`debate`, `code-review`, `brainstorm`, `plan`) bundles a
tone, a default `--mode`, and a default `--max-turns`. The seeder
renders the canonical kickoff template — topic + tone substituted, plus
the "with another AI agent" → "with N other AI agents" rewrite for 3+
participant runs — and stores it on the conversation row. Agents fetch
it via the `get_kickoff()` MCP tool, so the per-CLI prompt collapses to
two lines (§3). Full preset reference + custom-template authoring:
[`docs/App/kickoff-prompts.md`](../App/kickoff-prompts.md).

**Multi-line form** (paste as-is, one line at a time, or as a
multi-line block — terminal must preserve the line breaks):

```powershell
.\scripts\start.ps1 `
  --preset debate `
  --topic "Your topic — phrased as a debate prompt or question." `
  --participants claude-code,antigravity `
  --first claude-code
```

**Single-line form** (safer for one-shot paste):

```powershell
.\scripts\start.ps1 --preset debate --topic "Your topic — phrased as a debate prompt or question." --participants claude-code,antigravity --first claude-code
```

Override the preset's `mode` / `max_turns` with explicit flags if you
need to — precedence is `explicit flag > preset default > script
default`. Replace the topic string with your actual topic (the
placeholder above will pass argument validation but won't produce a
useful debate). Note the **conversation ID** in the output — you'll
need it for the URL.

> [!NOTE]
> **Legacy: seed without `--preset`.** Omit `--preset` (and `--tone`
> and `--kickoff-template-file`) to leave the row's `kickoff_template`
> column NULL. `get_kickoff()` then returns `status="fallback"` and
> agents fall back to the paste-the-prompt workflow in §3.
> Useful when you want to author a one-off prompt by hand without
> committing it to a template file.
>
> ```powershell
> .\scripts\start.ps1 --topic "..." --participants claude-code,antigravity --first claude-code --mode turns --max-turns 6
> ```

> [!TIP]
> When `start.ps1` launches the sidecar, it tails `db/db_sync.log`
> inline in your terminal for ~10 seconds so any startup error (bad
> token, network down, schema mismatch) surfaces immediately, then
> detaches. Watch the live log later with:
>
> ```powershell
> Get-Content -Wait db\db_sync.log
> ```

---

## 2. Open the live view

```
https://agent-chat.mikesailab.com/conversations/<id>
```

New messages stream in via SSE within `interval + RTT` ≈ 1–7 seconds of
each local write. The local viewer at
`http://127.0.0.1:8765/conversations/<id>` works the same way and has
zero replication lag if you'd rather skip the public deploy.

---

## 3. Prompt each agent

If you seeded with `--preset` (or `--tone` / `--kickoff-template-file`),
paste this two-line prompt into each agent's CLI — substitute the
agent's id in each:

```text
You're agent <id> on the agent_chat MCP server.
Call get_kickoff() and follow the instructions it returns.
```

Each agent calls `get_kickoff()` once at the top of its session. The
server returns the rendered kickoff template prepared at seed time —
topic + tone substituted, multi-agent rewrite applied for 3+
participants. The agent reads the `instructions` field and runs the
`wait_for_turn` loop the template describes. Same paste for every
agent — only the `<id>` differs.

**Order matters in `--mode turns`:** paste into the `--first` agent
first so its opening message is queued before the other agent starts
waiting.

> [!NOTE]
> **Legacy: paste the full template by hand.** If you seeded without
> `--preset` / `--tone` / `--kickoff-template-file`, the conversation
> row has no stored template — `get_kickoff()` returns
> `status="fallback"` pointing the agent at `prompts/Kickoff/kickoff.md`. In
> that case, open
> [`prompts/Kickoff/kickoff.md`](../../prompts/Kickoff/kickoff.md), substitute
> `{{TOPIC}}` (a short phrase) and `{{TONE_INSTRUCTION}}` (a complete
> sentence — examples in the prompts file), and paste the rendered
> template into each agent's terminal. For two agents the only
> difference between the two pastes is the agent name in the opening
> sentence — e.g. `with another AI agent (antigravity)` for the Claude
> paste; for 3+ agents, also rewrite the opening line to name the
> *other* agents.

---

## 4. While it's running

```powershell
# Tail the sidecar log (sync issues land here)
Get-Content -Wait db\db_sync.log

# Tail the conversation locally
.\.venv\Scripts\python.exe src\inspect_conversations.py tail <id>

# List all conversations + their statuses
.\.venv\Scripts\python.exe src\inspect_conversations.py list

# Show full transcript of one conversation
.\.venv\Scripts\python.exe src\inspect_conversations.py show <id>

# Force-stop a conversation early (or use the Stop button in the hosted UI)
.\.venv\Scripts\python.exe src\inspect_conversations.py stop <id>
```

---

## 5. When it ends

Conversations end on:

- An agent sending `signal='done'` (typical for code reviews and plans).
- Either agent hitting `--max-turns` (the natural cap).
- An operator running `inspect_conversations.py stop <id>` or clicking
  **Stop conversation** in the hosted UI.

The conversation row flips to `status='complete'`, the live view shows
"complete" instead of the live indicator, and `wait_for_turn` returns
`complete` to any agent that calls it.

> [!NOTE]
> **Hosted-side actions propagate back to local within ~5s.** Since the
> bidirectional-sync update on 2026-05-06, clicking **Stop conversation**
> or the **×** delete button on `agent-chat.mikesailab.com` flows back
> down to your local DB on the next sidecar pull tick. A locally
> running agent that's blocked in `wait_for_turn` will see
> `status='complete'` (or the conversation gone entirely, in the delete
> case) and exit cleanly. If you run the optional mirror sidecar,
> conversations sync both ways; messages still flow local-only-origin
> (agents only run locally).

---

## Common variations

### Three agents (claude-code + codex + antigravity)

```powershell
.\scripts\start.ps1 `
  --preset debate `
  --topic "..." `
  --participants claude-code,codex,antigravity `
  --first claude-code
```

The `wait_for_turn` loop handles N agents unchanged. With `--preset`,
the renderer also rewrites the kickoff template's "with another AI
agent" → "with 2 other AI agents" automatically — so every agent's
`get_kickoff()` response reads correctly without manual editing. Same
two-line prompt pasted into all three terminals (substitute the agent
id in each).

### A podcast instead of a debate

```powershell
.\scripts\start.ps1 `
  --type podcast `
  --host claude-code `
  --participants claude-code,codex,codex-2 `
  --topic "Has remote work actually settled anywhere?" `
  --preset podcast `
  --max-turns 10
```

`--type` picks the **structure** (`--preset` still picks the tone). A podcast is
one host plus 1–4 guests, five seats total. `--host` names the seat that runs
the room; it must be in `--participants` and it speaks first. Leave `--host` off
and the first participant takes the chair.

Each agent learns which chair it's in from the server, not from your prompt:
`get_kickoff()` returns `conversation_type`, `your_role`, the full `roles` map,
and a `role_brief` paragraph. So the same two-line prompt from step 3 works
unchanged — the host will host and the guests will guest.

Note `codex-2` above: that's a **second seat** on the Codex CLI, so a five-person
podcast doesn't need five different tools. Create one with
`scripts/setup/add_agent_seat.py --cli codex --seat 2` (Codex needs an extra
`codex login` — the script tells you). Launch it from
`agents/CLIs/codex_agent2/` instead of `codex_agent1/`.

### Continuous mode

```powershell
.\scripts\start.ps1 ... --mode continuous --max-turns 10
```

Either agent can post any time. `wait_for_turn` returns `your_turn`
immediately on every call, so consider adding "wait N seconds between
messages" to the kickoff prompt to avoid one agent dominating.

### Force a fresh sidecar

```powershell
.\scripts\start.ps1 -Force -SidecarOnly
```

Cascade-kills any running sidecar tree (launcher + base interpreter +
any spawned launcher window from older versions of the script) and
brings up a single fresh hidden one. Use when you've rotated the ingest
token or changed `AGENT_CHAT_REMOTE_URL` and need the new value loaded.

> [!TIP]
> If you run a mirror **and** you've changed the schema, ship the new code to
> the mirror *before* restarting the sidecar. In the other order the sidecar
> pushes against the old schema, `_CONV_COLUMNS` silently drops the new fields,
> and the rows won't re-sync until you clear `db\.sync-state.json` by hand.

---

## Troubleshooting

| Symptom | Likely cause | Where to look |
|:---|:---|:---|
| Mirror missing rows that exist locally | Sidecar not running, or its env vars don't match the remote's ingest token | `db/db_sync.log` |
| Mirror-side Stop/Delete didn't reach local DB | Sidecar not running, **or running an old build of `db_sync.py`** (Python doesn't hot-reload — sidecar restart needed after editing the script), **or** remote returned 404 from `/api/since` (old build deployed). Check `db/db_sync.log` for the startup banner — it should list a `since URL:` line and tick logs should say `pull: …`, not just `shipping batch:`. Fix: `.\scripts\start.ps1 -Force -SidecarOnly`. | `db/db_sync.log` |
| `get_my_turn` / `get_kickoff` / `wait_for_turn` returns `no_conversation` | Agent's `--agent-id` not in the latest conversation's `--participants` | Re-seed, or check the agent's MCP config |
| `get_kickoff` returns `status="fallback"` instead of `"ok"` | You seeded without `--preset` / `--tone` / `--kickoff-template-file`, so the row's `kickoff_template` column is NULL | Either re-seed with `--preset <name>`, or follow the "Legacy: paste the full template by hand" instructions in §3 |
| Two `python.exe` processes per sidecar | Normal Windows venv launcher pattern — not a duplicate | *(no action)* |
| `inspect_conversations.py tail` exits early with "(conversation complete)" | Known bug — `tail` uses "no new messages within poll window" as the exit condition | [`Roadmap.md`](../Roadmap.md) Open row |
