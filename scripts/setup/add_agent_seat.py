"""add_agent_seat.py — give a CLI tool a second (third, …) seat.

A **seat** is one participant slot. Seat 1 of a tool is the bare CLI id
(`codex`, launched from `agents/CLIs/codex_agent1/`); seat 2 is `codex-2`,
launched from `agents/CLIs/codex_agent2/`. Identity is config-only — the seat
folder's MCP config passes its own ``--agent-id`` to the launcher — so this
script's whole job is:

1. create ``agents/CLIs/<cli>_agent<N>/``,
2. copy seat 1's MCP config (and its role doc) into it,
3. rewrite the agent id inside that copy.

Step 2 has three sources, because two tools keep no config in the seat folder:
Codex's seat 1 is the global ``~/.codex/config.toml``, and **Claude Code's may
be registered at user scope with no project file at all** — that one is
synthesized from the ``agent_chat`` entry in ``~/.claude.json``. See
:func:`_seat_one_config_text`.

Run it once per extra seat, per machine. Seat 2+ folders are gitignored
(``agents/CLIs/*_agent[2-9]/``) — the copied config holds this machine's
launcher path — so this is setup, not source.

    .\\.venv\\Scripts\\python.exe scripts\\setup\\add_agent_seat.py --cli claude-code --seat 2
    .\\.venv\\Scripts\\python.exe scripts\\setup\\add_agent_seat.py --cli codex --seat 2 --dry-run

**Codex is the awkward one.** Its loader ignores per-folder config by default,
so a second Codex seat only gets its own agent id by relocating Codex's entire
user root with ``CODEX_HOME`` — which moves *credentials* too. This script seeds
``agents/CLIs/codex_agent<N>/.codex/config.toml`` from the global
``~/.codex/config.toml``, but you must run ``codex login`` once against the new
home (or copy ``auth.json`` into it) before that seat can talk to anything. The
spawn layer sets ``CODEX_HOME`` for seat 2+ automatically.

Subagent card trees (`.claude/agents/`, `.codex/agents/`) are **not** copied —
personas live in the DB now and those folders are a legacy import source.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from orchestrator import preflight, seats  # noqa: E402

_CLI_DIR = _REPO_ROOT / "agents" / "CLIs"


def _claude_user_entry() -> Optional[dict]:
    """Claude Code's user-scope ``agent_chat`` entry, or None.

    Delegates to ``preflight`` rather than re-reading ``~/.claude.json``: that
    module already decides what counts as a valid user-scope registration, and
    a second opinion here is how the two drift apart.
    """
    entry, _path = preflight._claude_user_scope_entry()
    return entry


@dataclass(frozen=True)
class CliShape:
    """Where a tool's MCP config lives and how its agent_chat entry is shaped.

    ``config_rel`` is relative to the seat folder. ``role_docs`` are copied
    verbatim so the new seat reads the same brief.

    Two tools don't keep a seat-1 config in the seat folder, and each says so
    here rather than in a branch further down:

    ``source_override``
        An absolute path to copy from — Codex, whose seat 1 *is* the global
        ``~/.codex/config.toml``.
    ``user_scope_entry``
        A callable returning the ``agent_chat`` entry registered at user scope,
        for a tool whose seat 1 may legitimately have no file at all. Claude
        Code: ``claude mcp add --scope user`` writes one entry to
        ``~/.claude.json``, and a project-scope ``.mcp.json`` next to it makes
        Claude Code raise an approval prompt on every launch (which silently
        stalls a spawned agent — it cost 30 minutes of run #51), so the seat-1
        folder here deliberately has none to clone. See
        ``agents/CLIs/claude-code_agent1/MCP-NOTE.md``.
    """
    config_rel: str
    fmt: str                      # 'json' | 'toml'
    json_path: tuple[str, ...] = ()   # keys down to the agent_chat entry
    command_is_array: bool = False    # OpenCode packs exe+args into one list
    source_override: Optional[Path] = None
    user_scope_entry: Optional[Callable[[], Optional[dict]]] = None
    role_docs: tuple[str, ...] = ()


SHAPES: dict[str, CliShape] = {
    "claude-code": CliShape(".mcp.json", "json", ("mcpServers", "agent_chat"),
                            user_scope_entry=_claude_user_entry,
                            role_docs=("claude.md", "CLAUDE.md")),
    "antigravity": CliShape(".agents/mcp_config.json", "json",
                            ("mcpServers", "agent_chat"), role_docs=("AGENTS.md",)),
    "gemini":      CliShape(".gemini/settings.json", "json",
                            ("mcpServers", "agent_chat"), role_docs=("GEMINI.md",)),
    "opencode":    CliShape("opencode.json", "json", ("mcp", "agent_chat"),
                            command_is_array=True, role_docs=("AGENTS.md",)),
    "codex":       CliShape(".codex/config.toml", "toml",
                            source_override=Path.home() / ".codex" / "config.toml",
                            role_docs=("AGENTS.md",)),
}


class SeatSetupError(RuntimeError):
    """Anything that should stop the run with a readable message."""


def _seat_one_config_text(cli: str, shape: CliShape, src_dir: Path) -> tuple[str, str]:
    """The config text seat N is cloned from, and a label saying where it came from.

    Three sources, in the order they are tried:

    1. ``source_override`` — Codex's global ``~/.codex/config.toml``.
    2. The seat-1 folder's own config — every normally-registered tool.
    3. ``user_scope_entry`` — a **synthesized** minimal config wrapping the
       entry the tool registered at user scope.

    (3) is what makes a second Claude Code seat possible at all. Its seat-1
    folder is expected to have no ``.mcp.json`` (see ``CliShape``), so cloning
    a file that must not exist used to fail with ``seat 1's config not found``
    on every machine — including a fresh clone, where the file is gitignored
    as well. Only the ``agent_chat`` entry is carried across: ``~/.claude.json``
    is the operator's whole Claude Code state (project histories, other MCP
    servers, settings) and none of that belongs in a seat folder.
    """
    if shape.source_override is not None:
        if not shape.source_override.exists():
            raise SeatSetupError(f"seat 1's config not found at {shape.source_override}")
        return shape.source_override.read_text(encoding="utf-8"), str(shape.source_override)

    own = src_dir / shape.config_rel
    if own.exists():
        return own.read_text(encoding="utf-8"), str(own)

    if shape.user_scope_entry is not None:
        entry = shape.user_scope_entry()
        if entry:
            doc: dict = {}
            node = doc
            for key in shape.json_path[:-1]:
                node[key] = {}
                node = node[key]
            node[shape.json_path[-1]] = entry
            return json.dumps(doc, indent=2) + "\n", f"{cli}'s user-scope registration"
        raise SeatSetupError(
            f"{cli} isn't registered anywhere this can copy from: no "
            f"{own} and no agent_chat entry at user scope. Register seat 1 "
            f"first — see docs/CLI-MCP-Config/."
        )

    raise SeatSetupError(f"seat 1's config not found at {own}")


def _rewrite_json(text: str, shape: CliShape, old_id: str, new_id: str) -> str:
    """Return ``text`` with the agent_chat entry's agent id set to ``new_id``.

    The agent id is the launcher's first positional argument, so it's found by
    locating the launcher path and taking the element after it — not by blind
    string replacement, which would also hit an id that appears in a comment or
    another server's config.
    """
    data = json.loads(text)
    node = data
    for key in shape.json_path:
        if not isinstance(node, dict) or key not in node:
            raise SeatSetupError(
                f"config has no {'.'.join(shape.json_path)} entry to copy"
            )
        node = node[key]

    if shape.command_is_array:
        argv = node.get("command")
        if not isinstance(argv, list):
            raise SeatSetupError("expected 'command' to be an array of strings")
        argv = list(argv)
        node["command"] = _replace_agent_arg(argv, old_id, new_id)
    else:
        args = node.get("args")
        if not isinstance(args, list):
            raise SeatSetupError("expected an 'args' list of strings")
        node["args"] = _replace_agent_arg(list(args), old_id, new_id)

    return json.dumps(data, indent=2) + "\n"


def _replace_agent_arg(argv: list, old_id: str, new_id: str) -> list:
    """Set the launcher's agent-id argument to ``new_id``.

    Prefers the element after the launcher script path; falls back to replacing
    an element that is exactly the old id, and appends when the launcher is the
    last element (a config that relies on the launcher's default).
    """
    launcher_idx = next(
        (i for i, a in enumerate(argv)
         if isinstance(a, str) and a.endswith((".ps1", ".sh"))),
        None,
    )
    if launcher_idx is not None:
        if launcher_idx + 1 < len(argv):
            argv[launcher_idx + 1] = new_id
        else:
            argv.append(new_id)
        return argv
    for i, a in enumerate(argv):
        if a == old_id:
            argv[i] = new_id
            return argv
    raise SeatSetupError(
        f"could not find the agent-id argument in {argv!r} — expected a "
        f"'.ps1'/'.sh' launcher path followed by the agent id"
    )


# The agent_chat args block inside a TOML config: everything from the section
# header up to the next section header (or EOF).
_TOML_SECTION_RE = re.compile(
    r"(\[mcp_servers\.agent_chat\].*?)(?=\n\[|\Z)", re.DOTALL
)


def _rewrite_toml(text: str, old_id: str, new_id: str) -> str:
    """Set the agent id inside a TOML ``[mcp_servers.agent_chat]`` block.

    Edits the text rather than round-tripping through a TOML writer: the file
    is the operator's whole Codex config and everything outside this one block
    — comments, ordering, unrelated servers — must survive byte-for-byte.
    """
    m = _TOML_SECTION_RE.search(text)
    if not m:
        raise SeatSetupError(
            "no [mcp_servers.agent_chat] section found in the source config"
        )
    section = m.group(1)
    quoted_old = f'"{old_id}"'
    if quoted_old not in section:
        raise SeatSetupError(
            f'[mcp_servers.agent_chat] does not pass "{old_id}" as its agent id; '
            f"edit the copy by hand"
        )
    # Only the *last* occurrence is the positional agent id (the launcher path
    # earlier in args could theoretically contain the same token).
    head, sep, tail = section.rpartition(quoted_old)
    new_section = head + f'"{new_id}"' + tail
    return text[:m.start(1)] + new_section + text[m.end(1):]


def add_seat(cli: str, seat: int, *, force: bool = False,
             dry_run: bool = False) -> Path:
    """Create ``agents/CLIs/<cli>_agent<seat>/``. Returns the new folder."""
    if cli not in SHAPES:
        raise SeatSetupError(
            f"unknown CLI {cli!r}; supported: {', '.join(sorted(SHAPES))}"
        )
    if not 2 <= seat <= seats.MAX_SEATS_PER_CLI:
        raise SeatSetupError(
            f"seat must be 2..{seats.MAX_SEATS_PER_CLI} (seat 1 already exists "
            f"as the bare '{cli}')"
        )
    shape = SHAPES[cli]
    new_id = seats.seat_id(cli, seat)
    src_dir = _CLI_DIR / f"{cli}_agent1"
    dst_dir = _CLI_DIR / f"{cli}_agent{seat}"

    text, src_label = _seat_one_config_text(cli, shape, src_dir)

    dst_config = dst_dir / shape.config_rel
    if dst_config.exists() and not force:
        raise SeatSetupError(
            f"{dst_config} already exists — pass --force to overwrite it"
        )

    if shape.fmt == "json":
        out = _rewrite_json(text, shape, cli, new_id)
    else:
        out = _rewrite_toml(text, cli, new_id)

    copied_docs = [d for d in shape.role_docs if (src_dir / d).exists()]

    print(f"seat        : {new_id}")
    print(f"folder      : {dst_dir}")
    print(f"config      : {dst_config}  (from {src_label})")
    if copied_docs:
        print(f"role docs   : {', '.join(copied_docs)}")
    if dry_run:
        print("\n--dry-run: nothing written. Config would read:\n")
        print(out)
        return dst_dir

    dst_config.parent.mkdir(parents=True, exist_ok=True)
    dst_config.write_text(out, encoding="utf-8")
    for doc in copied_docs:
        shutil.copy2(src_dir / doc, dst_dir / doc)

    print("\nwritten.")
    if cli == "codex":
        print(
            f"\nNEXT — Codex seats need their own credentials. This folder is the\n"
            f"seat's CODEX_HOME, and it has no auth yet:\n"
            f"    $env:CODEX_HOME = '{dst_dir / '.codex'}'; codex login\n"
            f"The spawn layer sets CODEX_HOME for seat 2+ automatically."
        )
    return dst_dir


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create an extra participant seat for a CLI tool.",
    )
    p.add_argument("--cli", required=True, choices=sorted(SHAPES),
                   help="the CLI tool to add a seat for")
    p.add_argument("--seat", required=True, type=int,
                   help=f"seat number, 2..{seats.MAX_SEATS_PER_CLI} "
                        f"(seat 1 is the existing bare id)")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing config for this seat")
    p.add_argument("--dry-run", action="store_true",
                   help="print what would be written and exit")
    args = p.parse_args()
    try:
        add_seat(args.cli, args.seat, force=args.force, dry_run=args.dry_run)
    except SeatSetupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
