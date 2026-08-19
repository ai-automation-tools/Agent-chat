"""availability.py — which CLI tools this machine actually has.

Everything else in the orchestrator assumes the full registry: ``preflight.
discover_seats()`` lists seat 1 of every supported tool whether or not the
operator owns it, and ``debate.ps1`` takes the first N keys of its ``$Clis``
table. That is right for the machine this project was built on and wrong for a
fresh clone, which gets six rows and five failures with no statement of what to
do about it.

This module is the single source of truth for **which seats may be offered**.
It answers in two parts, and the split matters:

``detect``
    A probe, run fresh on every call. Is the launcher binary on PATH (the same
    executable names ``scripts/lib/spawn-agents.ps1`` launches), and does this
    tool's ``agent_chat`` MCP entry pass :mod:`orchestrator.preflight`?

``declare``
    What the operator said, persisted to a small JSON file. It **overrides
    detection in both directions** — "I do have Codex, it's just not registered
    yet" and "ignore Gemini, I'm never using it" are both things detection
    cannot know. Until they answer, detection stands in.

One CLI is enough. A seat is config, not a program (see
:mod:`orchestrator.seats`), so a lone Claude Code install can field
``claude-code`` against ``claude-code-2`` — :func:`plan_seats` is what turns
"N participants, M tools" into an actual participant list, dealing seats
round-robin so two tools still means one seat each (today's behaviour, and the
default that must not change).

Nothing here installs a CLI or writes an MCP config. When a tool is missing the
answer is a link to ``docs/CLI-MCP-Config/``, not a mutation of the operator's
machine.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import preflight, seats

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Launcher executables per tool, in probe order. These are the names
#: ``scripts/lib/spawn-agents.ps1`` actually runs — keep the two in sync, since
#: a name that is right here and wrong there detects a CLI we then fail to
#: spawn. ``antigravity`` ships as ``agy``; the long form is accepted too.
CLI_BINARIES: dict[str, tuple[str, ...]] = {
    "claude-code": ("claude",),
    "codex": ("codex",),
    "antigravity": ("agy", "antigravity"),
    "opencode": ("opencode",),
    "gemini": ("gemini",),
}

#: Tools kept for backward compatibility but never proposed to a new operator.
DEPRECATED_CLIS: tuple[str, ...] = ("gemini",)

#: Written by :func:`save_declared`, so a future format change can be migrated
#: rather than guessed at.
CONFIG_VERSION = 1


class AvailabilityError(ValueError):
    """A bad declaration. Callers render ``.args[0]`` straight to the operator."""


# ---------------------------------------------------------------------------
# The declaration file
# ---------------------------------------------------------------------------

def config_file() -> Path:
    """Where the operator's answer lives.

    ``$AGENT_CHAT_CLI_CONFIG`` wins, else ``<repo>/config/available-clis.json``.
    The folder is gitignored: this is per-machine setup, not source.
    """
    override = os.environ.get("AGENT_CHAT_CLI_CONFIG")
    if override:
        return Path(override).expanduser()
    return _REPO_ROOT / "config" / "available-clis.json"


def load_declared() -> Optional[list[str]]:
    """The operator's declared tool list, or ``None`` if they never answered.

    ``None`` and ``[]`` are different answers and both are legitimate: the
    first means "ask me", the second means "I have nothing wired up yet" — so a
    malformed or unreadable file degrades to ``None`` (fall back to detection)
    rather than to an empty list (offer nothing).
    """
    path = config_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = data.get("available") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return None
    return [c for c in seats.SUPPORTED_CLIS if c in raw]


def is_declared() -> bool:
    """True once the operator has answered, however they answered."""
    return load_declared() is not None


def save_declared(clis: list[str]) -> Path:
    """Persist the operator's tool list. Returns the file written.

    Order is normalised to registry order so the file reads the same whichever
    order the checkboxes were ticked in.
    """
    unknown = [c for c in clis if c not in seats.SUPPORTED_CLIS]
    if unknown:
        raise AvailabilityError(
            f"unknown CLI id(s): {', '.join(sorted(unknown))} — supported: "
            f"{', '.join(seats.SUPPORTED_CLIS)}"
        )
    ordered = [c for c in seats.SUPPORTED_CLIS if c in set(clis)]
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": CONFIG_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "available": ordered,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def clear_declared() -> bool:
    """Forget the declaration and go back to pure detection. True if removed."""
    path = config_file()
    try:
        path.unlink()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CliStatus:
    """Everything the setup page needs to say about one tool, in one row."""

    cli: str
    binaries: tuple[str, ...]
    binary_path: Optional[str]
    config_ok: bool
    config_path: str
    failure_code: Optional[str]
    failure_detail: Optional[str]
    declared: Optional[bool]
    deprecated: bool

    @property
    def detected(self) -> bool:
        """The launcher binary resolved on PATH."""
        return self.binary_path is not None

    @property
    def available(self) -> bool:
        """Whether this tool may be offered as a seat. Declaration wins."""
        return self.detected if self.declared is None else self.declared

    @property
    def ready(self) -> bool:
        """Available *and* its MCP config passes preflight — i.e. it can run."""
        return self.available and self.config_ok

    def to_dict(self) -> dict:
        return {
            "cli": self.cli,
            "binaries": list(self.binaries),
            "binary_path": self.binary_path,
            "detected": self.detected,
            "config_ok": self.config_ok,
            "config_path": self.config_path,
            "failure_code": self.failure_code,
            "failure_detail": self.failure_detail,
            "declared": self.declared,
            "deprecated": self.deprecated,
            "available": self.available,
            "ready": self.ready,
        }


def _which(names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def detect(cli: str, declared: Optional[list[str]] = None) -> CliStatus:
    """Probe one tool. Pass ``declared`` to avoid re-reading the config file."""
    if cli not in seats.SUPPORTED_CLIS:
        raise AvailabilityError(
            f"unknown CLI id {cli!r} — supported: {', '.join(seats.SUPPORTED_CLIS)}"
        )
    result = preflight.run_preflight([cli])[0]
    first = result.failures[0] if result.failures else None
    return CliStatus(
        cli=cli,
        binaries=CLI_BINARIES.get(cli, ()),
        binary_path=_which(CLI_BINARIES.get(cli, ())),
        config_ok=result.ok,
        config_path=result.config_path,
        failure_code=first.code if first else None,
        failure_detail=first.detail if first else None,
        declared=(cli in declared) if declared is not None else None,
        deprecated=cli in DEPRECATED_CLIS,
    )


def detect_all() -> list[CliStatus]:
    """Probe every supported tool, in registry order."""
    declared = load_declared()
    return [detect(cli, declared) for cli in seats.SUPPORTED_CLIS]


# ---------------------------------------------------------------------------
# What may be offered
# ---------------------------------------------------------------------------

def available_clis() -> list[str]:
    """Tools that may be offered, in registry order.

    The declaration if there is one, else whatever detection found. When
    neither yields anything — a fresh clone with no CLI on PATH — this returns
    the empty list, and callers are expected to say so and point at ``/setup``
    rather than silently offering the full registry back.
    """
    declared = load_declared()
    if declared is not None:
        return declared
    return [c for c in seats.SUPPORTED_CLIS if _which(CLI_BINARIES.get(c, ()))]


def available_seats(clis: Optional[list[str]] = None) -> list[str]:
    """Every seat id offerable right now: seat 1 per available tool, plus each
    extra seat that already has a config folder on disk.

    This is ``preflight.discover_seats()`` narrowed to the tools the operator
    has. Seats that *could* exist but have no folder yet aren't listed — see
    :func:`plan_seats` and :func:`missing_seat_folders` for the "you need one
    more seat, shall I make it" path.
    """
    allowed = set(available_clis() if clis is None else clis)
    return [s for s in preflight.discover_seats() if seats.seat_cli(s) in allowed]


def plan_seats(clis: list[str], count: int) -> list[str]:
    """Deal ``count`` participant seats round-robin across ``clis``.

    One seat per tool first, then a second seat on each, and so on — so two
    tools and two participants is one seat each (unchanged from before seats
    existed), and one tool and two participants is ``claude-code`` against
    ``claude-code-2``.

        >>> plan_seats(["claude-code"], 3)
        ['claude-code', 'claude-code-2', 'claude-code-3']
        >>> plan_seats(["claude-code", "codex"], 3)
        ['claude-code', 'codex', 'claude-code-2']
    """
    if count < 1:
        return []
    if not clis:
        raise AvailabilityError(
            "no CLI tools available — declare at least one on the setup page"
        )
    capacity = len(clis) * seats.MAX_SEATS_PER_CLI
    if count > capacity:
        raise AvailabilityError(
            f"{count} participants needs more seats than "
            f"{len(clis)} tool(s) can hold ({capacity} max, "
            f"{seats.MAX_SEATS_PER_CLI} per tool)"
        )
    out: list[str] = []
    index = 1
    while len(out) < count:
        for cli in clis:
            if len(out) >= count:
                break
            out.append(seats.seat_id(cli, index))
        index += 1
    return out


def seat_folder_path(seat: str) -> Path:
    """Where a seat's MCP config folder lives (whether or not it exists)."""
    return _REPO_ROOT / "agents" / "CLIs" / seats.seat_folder(seat)


def missing_seat_folders(seat_ids: list[str]) -> list[str]:
    """Which of ``seat_ids`` have no config folder yet.

    Seat 1 is never reported: its folder is part of registering the CLI at all,
    so a missing one is a preflight failure with its own advice, not something
    ``add_agent_seat`` should paper over.
    """
    return [
        s for s in seat_ids
        if seats.seat_index(s) > 1 and not seat_folder_path(s).is_dir()
    ]
