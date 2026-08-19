"""Per-CLI preflight checks for the orchestrator.

Verifies that each selected CLI (``claude-code`` / ``codex`` / ``gemini`` /
``antigravity`` / ``opencode``) has the ``agent_chat`` MCP server registered correctly. Pure file-system
checks; no subprocesses are spawned, no CLIs are launched. The full launcher
probe happens in Phase 2b alongside the actual spawn step.

Each check returns a :class:`PreflightResult`. The result is suitable for:

- the Web UI's red-panel re-render (``failures`` list flattens into bullets)
- a per-run audit log at ``logs/orchestrator-<timestamp>.log``
- programmatic gating (``ok=False`` on any CLI aborts the whole run)
"""

from __future__ import annotations

import json
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import seats

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class PreflightFailure:
    """A single failed check.

    ``code`` is the failure category — useful for programmatic handling
    (e.g. "config_missing" vs "launcher_missing" need different operator
    advice). ``detail`` is the human-readable string surfaced to the UI
    and the log.
    """
    code: str
    detail: str


@dataclass
class PreflightResult:
    """Aggregate result for one CLI.

    ``failures`` is empty iff every check passed (``ok == True``). On
    partial success (config parsed but launcher missing), we still surface
    everything we could extract (``command``, ``launcher_path``) so the
    operator sees what *was* found alongside what failed.
    """
    cli: str
    ok: bool
    config_path: str
    failures: list[PreflightFailure] = field(default_factory=list)
    command: Optional[str] = None
    launcher_path: Optional[str] = None


# Supported CLI ids; orchestrator UI checkbox values must match these.
# ``gemini`` is kept for now as a fallback; ``antigravity`` is its successor.
# Defined in ``orchestrator.seats`` (which derives seat ids from it) and
# re-exported here, where every caller already imports it from.
SUPPORTED_CLIS = seats.SUPPORTED_CLIS


def _extract_launcher_path(command: str, args: list[str]) -> Optional[str]:
    """Best-effort extraction of the launcher script path from an MCP entry.

    Matches the two registration shapes documented in the README:

    - ``command="pwsh"``, ``args=["-NoProfile", "-File", "<launcher>", "<agent-id>"]``
      → returns the value following ``-File``.
    - ``command="<launcher.{sh,ps1}>"``, ``args=["<agent-id>"]``
      → returns ``command``.

    Returns ``None`` if neither shape matches.
    """
    if "-File" in args:
        idx = args.index("-File")
        if idx + 1 < len(args):
            return args[idx + 1]
    if command.endswith(".sh") or command.endswith(".ps1"):
        return command
    return None


def _command_resolves(command: str) -> bool:
    """True if ``command`` is a path-like that exists, or a bare binary on PATH."""
    if "/" in command or "\\" in command:
        return Path(command).expanduser().exists()
    return shutil.which(command) is not None


def _check_mcp_entry(
    cli: str,
    config_path: Path,
    mcp_block: Optional[dict],
) -> PreflightResult:
    """Shared validation for a parsed ``agent_chat`` MCP entry.

    Inputs:
      cli:         the CLI id ("claude-code" / "codex" / "gemini")
      config_path: where the config was loaded from (for the result)
      mcp_block:   the parsed dict for the ``agent_chat`` entry, or None
                   if the parent config had no such key

    Checks (each accumulates a failure if it doesn't pass):
      1. mcp_block is not None
      2. has ``command`` (str)
      3. has ``args`` (list of str)
      4. command resolves (PATH lookup or file exists)
      5. launcher path can be extracted from command/args
      6. extracted launcher path exists on disk
    """
    result = PreflightResult(cli=cli, ok=True, config_path=str(config_path))

    if not mcp_block:
        result.failures.append(PreflightFailure(
            code="no_mcp_entry",
            detail=f"{config_path} does not contain an 'agent_chat' MCP server entry",
        ))
        result.ok = False
        return result

    command = mcp_block.get("command")
    args = mcp_block.get("args")

    if not isinstance(command, str) or not command:
        result.failures.append(PreflightFailure(
            code="missing_command",
            detail=f"'agent_chat' entry in {config_path} is missing a 'command' string",
        ))
    else:
        result.command = command
        if not _command_resolves(command):
            result.failures.append(PreflightFailure(
                code="command_not_found",
                detail=(
                    f"'agent_chat' command {command!r} did not resolve — "
                    f"not on PATH and not an existing file path. "
                    f"(For pwsh: install via 'winget install Microsoft.PowerShell'.)"
                ),
            ))

    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        result.failures.append(PreflightFailure(
            code="missing_args",
            detail=f"'agent_chat' entry in {config_path} is missing an 'args' list of strings",
        ))
    elif isinstance(command, str):
        launcher = _extract_launcher_path(command, args)
        if launcher is None:
            result.failures.append(PreflightFailure(
                code="launcher_not_extractable",
                detail=(
                    f"could not extract a launcher script path from command={command!r} "
                    f"args={args!r} — expected either pwsh + ['-File', '<path>', ...] "
                    f"or a direct '.sh'/'.ps1' command"
                ),
            ))
        else:
            result.launcher_path = launcher
            if not Path(launcher).expanduser().exists():
                result.failures.append(PreflightFailure(
                    code="launcher_missing",
                    detail=(
                        f"launcher script {launcher!r} referenced in {config_path} "
                        f"does not exist on disk"
                    ),
                ))

    if result.failures:
        result.ok = False
    return result


def check_claude_code(agent_id: str = "claude-code") -> PreflightResult:
    """Preflight for Claude Code — reads ``agents/CLIs/claude-code_agent1/.mcp.json``."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / seats.seat_folder(agent_id) / ".mcp.json"
    if not config_path.exists():
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"Claude Code MCP config not found at {config_path}. "
                    f"See README 'Register the server' section for the JSON snippet."
                ),
            )],
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Claude Code MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcpServers") or {}).get("agent_chat")
    return _check_mcp_entry(agent_id, config_path, mcp_block)


def codex_home(agent_id: str) -> Optional[Path]:
    """The ``CODEX_HOME`` a Codex seat must launch with, or ``None`` for seat 1.

    Codex's loader ignores per-folder ``.codex/config.toml`` by default, so seat
    1 uses the global ``~/.codex`` and a second seat can only get its own
    ``--agent-id`` by relocating Codex's whole user root. That relocation also
    moves credentials, so each extra Codex seat needs its own ``codex login``
    — see docs/CLI-MCP-Config/Per-CLI/codex.md.
    """
    if seats.seat_index(agent_id) <= 1:
        return None
    return _REPO_ROOT / "agents" / "CLIs" / seats.seat_folder(agent_id) / ".codex"


def check_codex(agent_id: str = "codex") -> PreflightResult:
    """Preflight for Codex CLI — the **global** ``~/.codex/config.toml`` for seat
    1, or the seat's own ``CODEX_HOME`` folder for seat 2+ (see :func:`codex_home`).
    """
    home = codex_home(agent_id)
    config_path = (home or (Path.home() / ".codex")) / "config.toml"
    if not config_path.exists():
        hint = (
            "See README 'Register the server' section for the "
            "[mcp_servers.agent_chat] block."
            if home is None else
            f"Seat {seats.seat_index(agent_id)} needs its own CODEX_HOME. Create it "
            f"with: .\\scripts\\setup\\add-agent-seat.ps1 -Cli codex -Seat "
            f"{seats.seat_index(agent_id)}  (then run 'codex login' once against it)."
        )
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=f"Codex MCP config not found at {config_path}. {hint}",
            )],
        )
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Codex MCP config at {config_path} did not parse as TOML: {e}",
            )],
        )
    mcp_block = (data.get("mcp_servers") or {}).get("agent_chat")
    return _check_mcp_entry(agent_id, config_path, mcp_block)


def check_gemini(agent_id: str = "gemini") -> PreflightResult:
    """Preflight for Gemini CLI — reads ``agents/CLIs/gemini_agent1/.gemini/settings.json``."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / seats.seat_folder(agent_id) / ".gemini" / "settings.json"
    if not config_path.exists():
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"Gemini MCP config not found at {config_path}. "
                    f"See docs/CLI-MCP-Config/Per-CLI/gemini.md for the mcpServers.agent_chat block."
                ),
            )],
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Gemini MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcpServers") or {}).get("agent_chat")
    return _check_mcp_entry(agent_id, config_path, mcp_block)


def check_antigravity(agent_id: str = "antigravity") -> PreflightResult:
    """Preflight for the Antigravity CLI (Gemini CLI's successor) — reads
    ``agents/CLIs/antigravity_agent1/.agents/mcp_config.json``."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / seats.seat_folder(agent_id) / ".agents" / "mcp_config.json"
    if not config_path.exists():
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"Antigravity MCP config not found at {config_path}. "
                    f"See docs/CLI-MCP-Config/Per-CLI/antigravity.md for the mcpServers.agent_chat block."
                ),
            )],
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Antigravity MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcpServers") or {}).get("agent_chat")
    return _check_mcp_entry(agent_id, config_path, mcp_block)


def check_opencode(agent_id: str = "opencode") -> PreflightResult:
    """Preflight for the OpenCode CLI — reads the project-scoped config at
    ``agents/CLIs/opencode_agent1/opencode.json``.

    OpenCode auto-loads ``opencode.json`` from the launch directory (it looks in
    the current directory, then walks up to the nearest Git directory) and merges
    it with the global ``~/.config/opencode/opencode.json`` — project config wins
    on conflicting keys. We check the in-repo project file because it's the
    reproducible, committed source of truth — same rationale as antigravity's
    in-repo ``.agents/mcp_config.json``.

    OpenCode's MCP shape differs from the other CLIs: servers live under a top-
    level ``mcp`` key (not ``mcpServers``), each with ``type: "local"`` and a
    single ``command`` **array** (executable + args combined) rather than separate
    ``command`` (str) / ``args`` (list) fields. We normalize that array into the
    (command, args) pair the shared ``_check_mcp_entry`` validator expects so the
    launcher-path extraction logic is reused unchanged."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / seats.seat_folder(agent_id) / "opencode.json"
    if not config_path.exists():
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"OpenCode MCP config not found at {config_path}. "
                    f"See docs/CLI-MCP-Config/Per-CLI/opencode.md for the mcp.agent_chat block."
                ),
            )],
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PreflightResult(
            cli=agent_id,
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"OpenCode MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcp") or {}).get("agent_chat")
    # Normalize OpenCode's single ``command`` array into the (command, args) shape
    # the shared validator expects: command=array[0], args=array[1:]. Leave any
    # non-array command untouched so _check_mcp_entry surfaces the right failure.
    if isinstance(mcp_block, dict) and isinstance(mcp_block.get("command"), list):
        cmd = mcp_block["command"]
        normalized = dict(mcp_block)
        normalized["command"] = cmd[0] if cmd else None
        normalized["args"] = cmd[1:]
        mcp_block = normalized
    return _check_mcp_entry(agent_id, config_path, mcp_block)


_CHECKS = {
    "claude-code": check_claude_code,
    "codex":       check_codex,
    "gemini":      check_gemini,
    "antigravity": check_antigravity,
    "opencode":    check_opencode,
}


def discover_seats() -> list[str]:
    """Every agent id this machine has a config folder for, in registry order.

    Seat 1 of each supported tool is always listed — its absence is a preflight
    *failure* the operator should see on the form, not a row that quietly
    vanishes. Extra seats are listed only when ``agents/CLIs/<cli>_agent<N>/``
    exists, so running ``scripts/setup/add_agent_seat.py`` makes the new seat
    appear on the next page load with no code change.
    """
    found: list[str] = []
    for cli in SUPPORTED_CLIS:
        found.append(cli)
        for n in range(2, seats.MAX_SEATS_PER_CLI + 1):
            if (_REPO_ROOT / "agents" / "CLIs" / f"{cli}_agent{n}").is_dir():
                found.append(seats.seat_id(cli, n))
    return found


def run_preflight(agent_ids: list[str]) -> list[PreflightResult]:
    """Run preflight on each requested seat in order.

    Accepts bare CLI ids (`codex`) and numbered seats on them (`codex-2`); a
    seat is checked against its own config folder, since that's where its
    ``--agent-id`` is declared. Unrecognised ids produce an explicit failure
    result rather than raising — that keeps the Web UI's all-or-nothing
    failure handling simple.
    """
    results: list[PreflightResult] = []
    for agent_id in agent_ids:
        cli = seats.seat_cli(agent_id)
        check = _CHECKS.get(cli) if cli else None
        if check is None:
            results.append(PreflightResult(
                cli=agent_id,
                ok=False,
                config_path="(unknown)",
                failures=[PreflightFailure(
                    code="unknown_cli",
                    detail=(
                        f"unknown agent id {agent_id!r} — supported: "
                        f"{', '.join(SUPPORTED_CLIS)}, or a numbered seat on one "
                        f"(e.g. 'codex-2', up to -{seats.MAX_SEATS_PER_CLI})"
                    ),
                )],
            ))
        else:
            results.append(check(agent_id))
    return results


def format_preflight_log(results: list[PreflightResult]) -> str:
    """Render a preflight-result set as plain text suitable for
    ``logs/orchestrator-<timestamp>.log``. One line per failure plus a
    summary header so a grep on ``FAIL`` lists every problem."""
    lines: list[str] = []
    n_ok = sum(1 for r in results if r.ok)
    lines.append(f"# Preflight: {n_ok}/{len(results)} OK")
    for r in results:
        if r.ok:
            lines.append(f"  OK   {r.cli:<12} {r.config_path}")
        else:
            for f in r.failures:
                lines.append(f"  FAIL {r.cli:<12} [{f.code}] {f.detail}")
    return "\n".join(lines) + "\n"
