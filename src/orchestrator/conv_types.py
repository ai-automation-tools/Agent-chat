"""conv_types.py — the conversation-type registry.

A conversation's **type** is its structure: who is in the room and what each
seat is for. It is a different axis from ``preset`` (``src/presets.py``), which
bundles a kickoff *tone* plus mode/max_turns defaults:

- ``conv_type`` is durable, non-null, and defaults to ``'debate'`` — every row
  ever written before the column existed is a debate, and the ALTER TABLE
  default backfills them.
- ``preset`` stays optional; the paste-the-prompt flow leaves it NULL.

So ``conv_type='podcast'`` + ``preset='code-review'`` is a legal (if odd)
combination, and the conversations page can filter by structure without
inheriting preset's nullability.

Each type describes two seats:

- the **lead** — one participant who runs the room (a debate's moderator, a
  podcast's host). ``lead_required`` says whether the type can run without one.
- the **members** — everyone else (debaters, guests), bounded by
  ``min_members`` / ``max_members``.

Total participants are capped at :data:`MAX_PARTICIPANTS` for every type: one
CLI process per seat, and the spawn registry has five entries.

Adding a type is a dict entry here plus a prompt shape in
``scripts/lib/spawn-agents.ps1``. Nothing else in the stack enumerates types.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Optional


# One CLI process per seat, and the spawn registry (scripts/lib/spawn-agents.ps1)
# holds five CLIs. A sixth seat has nothing to run on.
MAX_PARTICIPANTS = 5


@dataclass(frozen=True)
class ConvType:
    """One conversation structure. See the module docstring for the seat model."""
    key: str
    label: str            # singular, title case — "Debate"
    plural: str           # rail filter chip — "Debates"
    lead_role: str        # role value stored in participant_roles
    lead_label: str       # UI label for that role — "Moderator"
    lead_required: bool
    member_role: str
    member_label: str     # singular — "Debater"
    members_label: str    # plural — "Debaters"
    min_members: int
    max_members: int
    default_preset: Optional[str]
    # Persona group a *random* lead is drawn from. Every type currently points
    # at the same one — the roster is shared across formats, and a group with
    # no rows falls back to the whole castable roster anyway. It stays a
    # per-type field so a future format can have its own without a code change
    # anywhere but this table.
    lead_group: str
    # Operator guide for this format, on GitHub. The web UI surfaces it beside
    # the format picker (and the homepage CTA that seeds it), so a new type
    # arrives with its own "how do I actually run one" link rather than
    # inheriting the debate's. Docs, not an app page, on purpose: it's a repo
    # question, and the link works unchanged on the read-only mirror.
    guide_url: str
    guide_label: str

    @property
    def roles(self) -> tuple[str, str]:
        return (self.lead_role, self.member_role)


# Repo root for the per-type guide links above.
_REPO = "https://github.com/michaelschecht/Agent-chat/blob/main"


CONV_TYPES: dict[str, ConvType] = {
    "debate": ConvType(
        key="debate",
        label="Debate",
        plural="Debates",
        lead_role="moderator",
        lead_label="Moderator",
        lead_required=False,
        member_role="debater",
        member_label="Debater",
        members_label="Debaters",
        min_members=2,
        max_members=MAX_PARTICIPANTS,
        default_preset="debate",
        lead_group="Debate-Hosts",
        guide_url=f"{_REPO}/docs/Guides/debate.md",
        guide_label="How to run a debate",
    ),
    "podcast": ConvType(
        key="podcast",
        label="Podcast",
        plural="Podcasts",
        lead_role="host",
        lead_label="Host",
        lead_required=True,
        member_role="guest",
        member_label="Guest",
        members_label="Guests",
        min_members=1,
        max_members=MAX_PARTICIPANTS - 1,   # the host takes a seat
        default_preset="podcast",
        # Same roster as a debate: the personalities that make good moderators
        # make good interviewers, and the operator maintains one set of cards.
        lead_group="Debate-Hosts",
        guide_url=f"{_REPO}/docs/Guides/podcast.md",
        guide_label="How to run a podcast",
    ),
}

DEFAULT_CONV_TYPE = "debate"
CONV_TYPE_KEYS: tuple[str, ...] = tuple(CONV_TYPES)

# Every role value any type can assign. Used to validate a participant_roles
# blob without first knowing which type wrote it (readers see the JSON alone).
ALL_ROLES: frozenset[str] = frozenset(
    r for t in CONV_TYPES.values() for r in t.roles
)


class ConvTypeError(ValueError):
    """Invalid conv_type or participant_roles. Callers render ``.args[0]``."""


def get_conv_type(key: Optional[str]) -> ConvType:
    """Look up a type, treating None/'' as the default. Raises ConvTypeError."""
    resolved = (key or DEFAULT_CONV_TYPE).strip().lower()
    if resolved not in CONV_TYPES:
        raise ConvTypeError(
            f"unknown conversation type {key!r}; "
            f"choices: {', '.join(CONV_TYPE_KEYS)}"
        )
    return CONV_TYPES[resolved]


def normalize_conv_type(key: Optional[str]) -> str:
    """Validated type key, defaulting when unset. Raises ConvTypeError."""
    return get_conv_type(key).key


def type_label(key: Optional[str]) -> str:
    """Display label for a stored value, tolerating unknown/legacy strings.

    Read paths (rendering an old row, an export) must never blow up on a value
    they don't recognise — only write paths validate.
    """
    resolved = (key or DEFAULT_CONV_TYPE).strip().lower()
    t = CONV_TYPES.get(resolved)
    return t.label if t else resolved


def role_label(conv_type: Optional[str], role: Optional[str]) -> str:
    """Display label for a role within a type ('host' → 'Host').

    Falls back to a title-cased version of the raw value so a role written by a
    newer build still renders on an older one.
    """
    if not role:
        return ""
    resolved = (conv_type or DEFAULT_CONV_TYPE).strip().lower()
    t = CONV_TYPES.get(resolved)
    if t is not None:
        if role == t.lead_role:
            return t.lead_label
        if role == t.member_role:
            return t.member_label
    return str(role).replace("-", " ").replace("_", " ").title()


def default_roles(conv_type: str, participants: list[str]) -> dict[str, str]:
    """Roles implied by seat order when the caller didn't supply any.

    ``participants[0]`` is the ``--first`` speaker by convention across the
    stack (``orchestrate`` already seeds the moderator first), so it takes the
    lead role for a type that requires one. Everyone else is a member.
    """
    t = get_conv_type(conv_type)
    roles = {p: t.member_role for p in participants}
    if t.lead_required and participants:
        roles[participants[0]] = t.lead_role
    return roles


def validate_roles(
    conv_type: str,
    participants: list[str],
    roles: Optional[dict[str, str]],
) -> dict[str, str]:
    """Resolve + check a role map against a type's seat rules.

    Returns the complete map (every participant keyed). Raises
    :class:`ConvTypeError` on: an unknown role for the type, a role for a
    non-participant, more than one lead, or a missing lead when the type
    requires one. Participants left out of an explicit map default to the
    member role rather than erroring — the common case is naming only the lead.
    """
    t = get_conv_type(conv_type)
    if roles is None:
        return default_roles(t.key, participants)

    seats = set(participants)
    resolved: dict[str, str] = {p: t.member_role for p in participants}
    for agent, role in roles.items():
        if agent not in seats:
            raise ConvTypeError(
                f"role given for {agent!r}, which is not a participant"
            )
        if role not in t.roles:
            raise ConvTypeError(
                f"invalid role {role!r} for a {t.key}; "
                f"choices: {t.lead_role}, {t.member_role}"
            )
        resolved[agent] = role

    leads = [a for a, r in resolved.items() if r == t.lead_role]
    if len(leads) > 1:
        raise ConvTypeError(
            f"a {t.key} takes one {t.lead_label.lower()}; got {len(leads)} "
            f"({', '.join(sorted(leads))})"
        )
    if t.lead_required and not leads:
        raise ConvTypeError(f"a {t.key} needs a {t.lead_label.lower()}")
    return resolved


def validate_seat_counts(conv_type: str, participants: list[str],
                         roles: dict[str, str]) -> None:
    """Check participant/member counts against the type. Raises ConvTypeError."""
    t = get_conv_type(conv_type)
    if len(participants) > MAX_PARTICIPANTS:
        raise ConvTypeError(
            f"at most {MAX_PARTICIPANTS} participants (one CLI seat each); "
            f"got {len(participants)}"
        )
    members = [a for a, r in roles.items() if r == t.member_role]
    if len(members) < t.min_members:
        raise ConvTypeError(
            f"a {t.key} needs at least {t.min_members} "
            f"{t.members_label.lower() if t.min_members != 1 else t.member_label.lower()}; "
            f"got {len(members)}"
        )
    if len(members) > t.max_members:
        raise ConvTypeError(
            f"a {t.key} takes at most {t.max_members} {t.members_label.lower()}; "
            f"got {len(members)}"
        )


def lead_of(conv_type: Optional[str], roles: Optional[dict[str, str]]) -> Optional[str]:
    """The agent id holding the lead seat, or None. Read-path safe."""
    if not roles:
        return None
    resolved = (conv_type or DEFAULT_CONV_TYPE).strip().lower()
    t = CONV_TYPES.get(resolved)
    lead_role = t.lead_role if t else None
    for agent, role in roles.items():
        if lead_role is not None and role == lead_role:
            return agent
    return None


def parse_roles(raw: Optional[str | dict]) -> dict[str, str]:
    """Decode the ``participant_roles`` JSON column; ``{}`` when absent/bad.

    Mirrors ``export.parse_participant_personas`` — a read path must tolerate a
    row written by any build.
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v}


def summarize(conv_type: Optional[str], roles: Optional[dict[str, str]],
              participants: Iterable[str]) -> str:
    """One-line seat summary for CLI output — 'podcast · host claude-code'."""
    label = type_label(conv_type)
    lead = lead_of(conv_type, roles)
    if not lead:
        return label.lower()
    t = CONV_TYPES.get((conv_type or DEFAULT_CONV_TYPE).strip().lower())
    lead_word = t.lead_label.lower() if t else "lead"
    return f"{label.lower()} · {lead_word} {lead}"
