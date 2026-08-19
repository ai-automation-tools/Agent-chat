# Add-a-CLI — file-by-file reference

Exact edits and config templates for each surface in the Step 4 checklist. Symbols are referenced by name because line numbers drift; grep for the symbol to find it. `<id>` = the new agent-id (e.g. `opencode`), `<Display>` = "OpenCode", `<Vendor>` = "SST".

---

## 1. `src/orchestrator/preflight.py` — canonical

Three edits:

- **`SUPPORTED_CLIS`** tuple — append `"<id>"`.
- **`check_<id>()`** — copy the existing checker whose config shape matches your CLI and change the path + the key the MCP block lives under. The four shapes already in the file:
  - `check_claude_code()` — repo dotfile `agents/CLIs/<id>_agent1/.mcp.json`, JSON, block at `data["mcpServers"]["agent_chat"]`.
  - `check_codex()` — **global** `~/.codex/config.toml`, TOML, block at `data["mcp_servers"]["agent_chat"]`.
  - `check_antigravity()` / `check_gemini()` — repo dotfolder JSON, `mcpServers.agent_chat`.
  - `check_opencode()` — repo-root `opencode.json`, **top-level `mcp` key**, and it **normalizes a single `command` array** into `(command, args)` before calling `_check_mcp_entry`. Reuse this branch if your CLI uses a command array.
  All checkers end by delegating to `_check_mcp_entry(...)` — that CLI-agnostic helper validates command/args/launcher; do not duplicate its logic.
- **`_CHECKS`** dict — add `"<id>": check_<id>,`.

`run_preflight()` and `PreflightResult`/`PreflightFailure` need no change.

---

## 2. `src/web/render/home.py` — homepage (two lists + prose)

- **`_SUPPORTED_CLIS`** (drives the Supported-CLIs matrix table via `_render_homepage_clis_table()`). Entry shape:
  `("<Display>", "<Vendor>", "<id>", "<repo-or-home-url>", "Active", True)`.
  For a deprecated/fallback CLI use `"Deprecated · fallback", False` (greys the row).
- **`_CLI_RESOURCES`** (drives the "Supported CLIs" Resources tile via `_res_cli_row()`). Entry shape:
  `("<Display>", "<repo-url>", "<docs-url>")`. Use the tool's real docs URL.
- **Prose / stat updates:** search the file for `Six` and the standalone CLI-count `6` stat card and bump them (they're hardcoded in the hero + meta description + a stat tile). Grep: `grep -n "Six\|>6<" src/web/render/home.py`.

---

## 3. `src/web/render/orchestrate.py` — the /orchestrate form

- **`_ORCH_CLI_IDS`** tuple — append `"<id>"`.
- **Checkbox block** — the participant checkboxes are hand-written `<label><input value="<id>">…</label>` blocks, NOT generated from the tuple. Copy an existing block and change the value + label. For a deprecated CLI add the inline `<em>(deprecated)</em>` like Gemini's.

`src/web/api/orchestrate.py` validates `moderator_cli` against the imported `SUPPORTED_CLIS` — no change.

---

## 4. `src/orchestrator/model_personas.py` — AI-Models card

Add an entry to **`MODEL_CARDS`**, keyed by `<id>` (the key doubles as the slug):

```python
"<id>": (
    "<Display>",
    ["ai-model", "<vendor-lower>", "cli"],   # tags; add "deprecated" if fallback
    """<original 1–3 paragraph description of the tool — what it is, who makes it,
its strengths as a debate participant. NOT a copy of any vendor system prompt.""",
),
```

`ensure_model_personas()` creates it on web-UI boot (create-if-missing), so it lands in the reserved `AI-Models` group and backs the Cast panel automatically.

---

## 5. `scripts/lib/spawn-agents.ps1` — spawn registry (auto-spawn only)

Add an entry to the **`$Clis`** ordered hashtable. Shape per entry:

```powershell
'<id>' = @{
    Dir       = "$RepoRoot\agents\CLIs\<id>_agent1"   # launch dir (reads its role doc here)
    Exe       = '<binary-on-PATH>'                     # e.g. 'opencode'
    PromptArg = '<how the opening prompt is passed>'   # {0} = quoted opening prompt; e.g. 'run "{0}"'
    SkipPerm  = '<unattended flag>'                    # e.g. '--yolo' or '' if none
}
```

Order matters — it's the CLI preference order; the first entry is the default `--first`. **Omit this entry entirely for a seedable-only CLI** (no prompt-arg / no unattended mode) — that's exactly why `gemini` is in `SUPPORTED_CLIS` but not in `$Clis`.

If you added a spawnable entry, in **`scripts/debate.ps1`** bump the `[ValidateSet(2,3,4,5)]` on `-Agents` to include the new count, and update the `.PARAMETER Cli` / `.PARAMETER SkipPermissions` help text.

---

## 6. `scripts/setup/setup-skill-links.ps1` (+ `.sh`) — skills junctions

Optional (runtime-skills parity). The script hardcodes the workspaces it junctions `skills/` into. Add `agents/CLIs/<id>_agent1/.<id>/skills` (or the CLI's skills dir) if the tool supports skills. OpenCode is currently absent here — parity is nice-to-have, not required to add a CLI.

---

## 7. `agents/CLIs/<id>_agent1/` — the config folder

Create two files. **The MCP config path must exactly match what `check_<id>()` reads.**

**Role doc** — `AGENTS.md` (default standard) unless the CLI reads a specific name (`claude.md`, `GEMINI.md`). Copy an existing one (e.g. `agents/CLIs/opencode_agent1/AGENTS.md`) — it's the tester-role instructions + a pointer to the agent-chat participation loop.

**MCP config** — pick the template matching the CLI's format:

*Standard `mcpServers` JSON* (claude-code / antigravity / gemini style):
```json
{
  "mcpServers": {
    "agent_chat": {
      "command": "pwsh",
      "args": ["-NoProfile", "-File",
               "D:/AI_Agents/Projects/Mikes_AI_Lab/Repos/Live_Apps/Agent-Chat/scripts/run-mcp-server.ps1",
               "<id>"]
    }
  }
}
```

*OpenCode style* — top-level `mcp`, `type: "local"`, single `command` **array**:
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "agent_chat": {
      "type": "local",
      "enabled": true,
      "command": ["pwsh", "-NoProfile", "-File",
                  "D:/AI_Agents/.../scripts/run-mcp-server.ps1", "<id>"]
    }
  }
}
```

*Codex style* — **global** `~/.codex/config.toml` (outside the repo), TOML:
```toml
[mcp_servers.agent_chat]
command = "pwsh"
args = ["-NoProfile", "-File", "D:/AI_Agents/.../scripts/run-mcp-server.ps1", "<id>"]
```

Notes:
- `run-mcp-server.ps1` resolves the venv + server + DB relative to itself, so the **only** hardcoded absolute path is the launcher path string — match the convention in the sibling configs (forward slashes, full `D:/…` path).
- `.sh` twin (`run-mcp-server.sh`) exists for POSIX; mirror the config if cross-platform matters.

**`.gitignore`** — if the config sits in an otherwise-ignored dotfolder, add an un-ignore exception mirroring the existing pattern, e.g.:
```
agents/CLIs/<id>_agent1/.<id>/*
!agents/CLIs/<id>_agent1/.<id>/mcp.json
```

---

## 8. Docs

- **`README.md`** — add a row to the "CLI MCP Registration" table (CLI → config file → setup-guide link); update the "Supported CLIs" shields.io badge string (it's currently stale — safe to refresh the whole list while you're there).
- **`docs/CLI-MCP-Config/README.md`** — three tables to update: the "Jump to your CLI × scope" table, the canonical-id prose list, and the vendor-docs table.
- **`docs/CLI-MCP-Config/Per-CLI/<id>.md`** — NEW deep-dive file. Copy `opencode.md` as the template; preflight failure messages reference these by name.
- **`CLAUDE.md`** — the intro one-paragraph CLI list, and the `agents/CLIs/` annotation in the repo-layout tree (one line: role doc + MCP config filename). If this skill list is shown there, it's already covered.
- **`docs/Guides/start-new-chat.md`** — the per-CLI "where each CLI reads its config" bullet list.
- **`docs/CHANGELOG.md`** — new reverse-chron entry. The "OpenCode CLI support" entry is a ready-made template listing exactly what a CLI-add touched.
- **`docs/Roadmap.md`** — if an "add <tool>" row is Open, move it to Done with today's date.

---

## Deprecated / fallback status — where it's encoded

There's no single flag. To mark a CLI deprecated (rare — only for a superseded fallback like Gemini), replicate across:
- `home.py` `_SUPPORTED_CLIS` → `is_active=False` + `"Deprecated · fallback"` label.
- `orchestrate.py` → inline `<em>(deprecated)</em>` on the checkbox.
- `model_personas.py` → `"deprecated"` tag + a line in the card body.
- Docs → `(deprecated)` in the README table, CLI-MCP-Config README, start-new-chat bullet, CLAUDE.md.
- Omit from the `$Clis` spawn registry (preflight-supported but not auto-launched).
