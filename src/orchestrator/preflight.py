"""Per-CLI preflight checks for the orchestrator.

Verifies that each selected CLI (``claude-code`` / ``codex`` / ``gemini`` /
``antigravity``) has the ``agent_chat`` MCP server registered correctly. Pure file-system
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
SUPPORTED_CLIS = ("claude-code", "codex", "gemini", "antigravity")


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


def check_claude_code() -> PreflightResult:
    """Preflight for Claude Code — reads ``agents/CLIs/claude-code_agent1/.mcp.json``."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / "claude-code_agent1" / ".mcp.json"
    if not config_path.exists():
        return PreflightResult(
            cli="claude-code",
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
            cli="claude-code",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Claude Code MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcpServers") or {}).get("agent_chat")
    return _check_mcp_entry("claude-code", config_path, mcp_block)


def check_codex() -> PreflightResult:
    """Preflight for Codex CLI — reads the **global** ``~/.codex/config.toml``.

    Codex's loader ignores per-folder ``.codex/config.toml`` by default, so
    the orchestrator never bothers checking project-local copies.
    """
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        return PreflightResult(
            cli="codex",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"Codex MCP config not found at {config_path}. "
                    f"See README 'Register the server' section for the [mcp_servers.agent_chat] block."
                ),
            )],
        )
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        return PreflightResult(
            cli="codex",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Codex MCP config at {config_path} did not parse as TOML: {e}",
            )],
        )
    mcp_block = (data.get("mcp_servers") or {}).get("agent_chat")
    return _check_mcp_entry("codex", config_path, mcp_block)


def check_gemini() -> PreflightResult:
    """Preflight for Gemini CLI — reads ``agents/CLIs/gemini_agent1/.gemini/settings.json``."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / "gemini_agent1" / ".gemini" / "settings.json"
    if not config_path.exists():
        return PreflightResult(
            cli="gemini",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"Gemini MCP config not found at {config_path}. "
                    f"See docs/CLI-MCP-Config/gemini.md for the mcpServers.agent_chat block."
                ),
            )],
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PreflightResult(
            cli="gemini",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Gemini MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcpServers") or {}).get("agent_chat")
    return _check_mcp_entry("gemini", config_path, mcp_block)


def check_antigravity() -> PreflightResult:
    """Preflight for the Antigravity CLI (Gemini CLI's successor) — reads
    ``agents/CLIs/antigravity_agent1/.agents/mcp_config.json``."""
    config_path = _REPO_ROOT / "agents" / "CLIs" / "antigravity_agent1" / ".agents" / "mcp_config.json"
    if not config_path.exists():
        return PreflightResult(
            cli="antigravity",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_missing",
                detail=(
                    f"Antigravity MCP config not found at {config_path}. "
                    f"See docs/CLI-MCP-Config/antigravity.md for the mcpServers.agent_chat block."
                ),
            )],
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return PreflightResult(
            cli="antigravity",
            ok=False,
            config_path=str(config_path),
            failures=[PreflightFailure(
                code="config_parse_error",
                detail=f"Antigravity MCP config at {config_path} did not parse as JSON: {e}",
            )],
        )
    mcp_block = (data.get("mcpServers") or {}).get("agent_chat")
    return _check_mcp_entry("antigravity", config_path, mcp_block)


_CHECKS = {
    "claude-code": check_claude_code,
    "codex":       check_codex,
    "gemini":      check_gemini,
    "antigravity": check_antigravity,
}


def run_preflight(clis: list[str]) -> list[PreflightResult]:
    """Run preflight on each requested CLI in order. Unknown CLI ids
    produce an explicit failure result rather than raising — keeps the
    Web UI's all-or-nothing failure handling simple."""
    results: list[PreflightResult] = []
    for cli in clis:
        check = _CHECKS.get(cli)
        if check is None:
            results.append(PreflightResult(
                cli=cli,
                ok=False,
                config_path="(unknown)",
                failures=[PreflightFailure(
                    code="unknown_cli",
                    detail=(
                        f"unknown CLI id {cli!r} — supported: "
                        f"{', '.join(SUPPORTED_CLIS)}"
                    ),
                )],
            ))
        else:
            results.append(check())
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
