"""seed_conversation(): the single source of truth for creating a conversation row.

Extracted from ``src/start_conversation.py:main()`` so the CLI entrypoint and the
Web UI's ``POST /api/orchestrate`` handler both go through the same code path.
The CLI argparse layer (in ``start_conversation.py``) parses flags, applies
preset defaults, and then calls ``seed_conversation()``. The Web UI handler
parses form fields, runs preflight, and then calls the same function.

Schema and migration logic mirror ``src/agent_chat_mcp.py`` and ``src/web_ui.py``;
the constants below intentionally duplicate the SCHEMA / _MIGRATIONS strings so
this module can run against a fresh-clone DB without a prior connection from
either of those modules.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from presets import deliverable_for
from .conv_types import (
    DEFAULT_CONV_TYPE,
    ConvTypeError,
    get_conv_type,
    lead_of,
    normalize_conv_type,
    validate_roles,
    validate_seat_counts,
)

# Match every ```text ... ``` fenced block inside a Markdown source.
_TEMPLATE_BLOCK_RE = re.compile(r"```text\n(.*?)\n```", re.DOTALL)

# The canonical kickoff template is the first ```text block that contains
# this marker. prompts/Kickoff/kickoff.md has multiple ```text fences (an example
# snippet near the top, the actual template lower down); {{TOPIC}} is the
# unique distinguishing element of the real template.
_TEMPLATE_MARKER = "{{TOPIC}}"

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_TEMPLATE_PATH = _REPO_ROOT / "prompts" / "Kickoff" / "kickoff.md"


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    topic             TEXT NOT NULL,
    participants      TEXT NOT NULL,
    mode              TEXT NOT NULL,
    max_turns         INTEGER NOT NULL,
    current_turn      TEXT,
    status            TEXT NOT NULL,
    end_reason        TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    preset            TEXT,
    kickoff_template  TEXT,
    participant_personas TEXT,
    conv_type         TEXT NOT NULL DEFAULT 'debate',
    participant_roles TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL REFERENCES conversations(id),
    sender           TEXT NOT NULL,
    content          TEXT NOT NULL,
    signal           TEXT,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS personas (
    "group"      TEXT NOT NULL,
    slug         TEXT NOT NULL,
    name         TEXT NOT NULL,
    tags         TEXT,
    category     TEXT,
    subcategory  TEXT,
    body         TEXT NOT NULL,
    avatar_mime  TEXT,
    avatar_data  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY ("group", slug)
);

CREATE INDEX IF NOT EXISTS idx_personas_updated ON personas(updated_at);

CREATE TABLE IF NOT EXISTS battleground_arenas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,
    site          TEXT NOT NULL,
    title         TEXT NOT NULL,
    thread        TEXT NOT NULL,
    stance        TEXT,
    reply_to      TEXT,
    agent_id      TEXT,
    persona_slug  TEXT,
    persona_name  TEXT,
    persona_body  TEXT,
    status        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battleground_drafts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    arena_id      INTEGER NOT NULL REFERENCES battleground_arenas(id),
    agent_id      TEXT NOT NULL,
    reply_to      TEXT,
    content       TEXT NOT NULL,
    rationale     TEXT,
    status        TEXT NOT NULL,
    verdict_note  TEXT,
    posted_text   TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bg_arenas_status ON battleground_arenas(status, id);
CREATE INDEX IF NOT EXISTS idx_bg_drafts_arena ON battleground_drafts(arena_id, id);
"""

_MIGRATIONS = (
    ("conversations", "preset",           "ALTER TABLE conversations ADD COLUMN preset TEXT"),
    ("conversations", "kickoff_template", "ALTER TABLE conversations ADD COLUMN kickoff_template TEXT"),
    ("conversations", "participant_personas", "ALTER TABLE conversations ADD COLUMN participant_personas TEXT"),
    ("conversations", "conv_type",
     "ALTER TABLE conversations ADD COLUMN conv_type TEXT NOT NULL DEFAULT 'debate'"),
    ("conversations", "participant_roles",
     "ALTER TABLE conversations ADD COLUMN participant_roles TEXT"),
    ("battleground_arenas", "reply_to", "ALTER TABLE battleground_arenas ADD COLUMN reply_to TEXT"),
    ("personas", "avatar_mime", "ALTER TABLE personas ADD COLUMN avatar_mime TEXT"),
    ("personas", "avatar_data", "ALTER TABLE personas ADD COLUMN avatar_data TEXT"),
)


@dataclass
class SeedResult:
    """Return value of ``seed_conversation()``.

    ``kickoff_rendered`` is the rendered kickoff body when a template was used
    (preset/tone/template_file supplied), else None — UI surfaces can use it
    to confirm the agent will receive instructions via ``get_kickoff()``.
    """
    conversation_id: int
    topic: str
    participants: list[str]
    mode: str
    max_turns: int
    first: str
    preset: Optional[str]
    kickoff_rendered: Optional[str]
    conv_type: str = DEFAULT_CONV_TYPE
    participant_roles: dict[str, str] = field(default_factory=dict)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db_path() -> str:
    """Resolve DB path: $AGENT_CHAT_DB > <repo>/db/chat.db."""
    env_db = os.environ.get("AGENT_CHAT_DB")
    if env_db:
        return env_db
    return str(_REPO_ROOT / "db" / "chat.db")


def load_template(path: Path) -> str:
    """Load a kickoff template body.

    Two source shapes supported:
    - Markdown with one or more ```text fenced blocks — first block containing
      ``{{TOPIC}}`` is returned (so example snippets elsewhere don't shadow).
    - Plain text — returned verbatim (stripped).
    """
    raw = path.read_text(encoding="utf-8")
    for m in _TEMPLATE_BLOCK_RE.finditer(raw):
        body = m.group(1).rstrip()
        if _TEMPLATE_MARKER in body:
            return body
    return raw.strip()


def render_kickoff(template: str, topic: str, tone: str, n_participants: int) -> str:
    """Substitute placeholders and rewrite the participant declaration for 3+ agents.

    The template's opening line declares the conversation as "with another AI
    agent" (singular). For N >= 3 participants we rewrite to "with (N-1) other
    AI agents".
    """
    body = template.replace("{{TOPIC}}", topic).replace("{{TONE_INSTRUCTION}}", tone)
    if n_participants >= 3:
        others = n_participants - 1
        body = body.replace("with another AI agent", f"with {others} other AI agents")
    return body


def deliverable_clause(conv_type: str, preset: Optional[str]) -> str:
    """The paragraph appended to the tone for a type that produces an artifact.

    A collaboration's whole point is the thing it makes, and the kickoff body is
    the only place the *shape* of that thing can be stated — the role brief in
    ``agent_chat_mcp._ROLE_BRIEFS`` is generic across every collaboration, so it
    says "the deliverable the kickoff asked for" and this supplies the rest.

    Returns ``''`` for a type that produces no deliverable, which is every type
    but ``collaborate`` today — so a debate's and a podcast's kickoff bodies are
    byte-for-byte what they were before deliverables existed.
    """
    t = get_conv_type(conv_type)
    if not t.produces_deliverable:
        return ""
    shape = deliverable_for(preset) or (
        "the artifact this room was convened to produce, written out in full "
        "rather than described."
    )
    return (
        f"\n\nThis conversation exists to produce something, not to be read. "
        f"On their final turn the {t.lead_label.lower()} writes the "
        f"{t.deliverable_label.lower()} and sends it with signal='result', and "
        f"it takes this shape: {shape} Everyone else: your job is to make that "
        f"{t.deliverable_label.lower()} good, not to have the last word."
    )


class SeedError(ValueError):
    """Raised on invalid seed_conversation() arguments. Caller renders the
    .args[0] string back to the operator (CLI: stderr; Web UI: form error)."""


def seed_conversation(
    *,
    db_path: str,
    topic: str,
    participants: list[str],
    mode: str,
    max_turns: int,
    first: Optional[str] = None,
    preset: Optional[str] = None,
    tone: Optional[str] = None,
    kickoff_template_file: Optional[str] = None,
    initial_system_message: Optional[str] = None,
    participant_personas: Optional[dict] = None,
    conv_type: Optional[str] = None,
    participant_roles: Optional[dict[str, str]] = None,
) -> SeedResult:
    """Insert a conversation row, optionally rendering a kickoff template body.

    Validation matches the original ``start_conversation.py:main()`` behaviour:
    - at least 2 participants, all unique
    - ``first`` (if set) must be in ``participants``
    - ``max_turns >= 1``
    - if any of preset/tone/kickoff_template_file is set, a tone is required
      and the template file must exist

    ``conv_type`` (default ``'debate'``) and ``participant_roles`` are checked
    against the type's seat rules in ``orchestrator.conv_types`` — participant
    cap, member count, and one-lead-at-most. Omitting ``participant_roles``
    derives them from seat order: ``participants[0]`` takes the lead role for a
    type that requires one (matching the ``--first``-speaker convention), and
    everyone else is a member.

    For a ``conv_type`` that produces a deliverable, the rendered kickoff body
    also carries :func:`deliverable_clause` — the artifact's shape, taken from
    the preset. Both seeding callers (``start_conversation.py`` and
    ``POST /api/orchestrate``) come through here, so neither has to know.

    Returns a :class:`SeedResult`. Raises :class:`SeedError` on validation
    failure (caller renders the message). The DB connection is opened with the
    same isolation/WAL settings as the rest of the codebase and closed before
    return.
    """
    # ---- validation -----------------------------------------------------
    if len(participants) < 2:
        raise SeedError("need at least 2 participants")
    if len(set(participants)) != len(participants):
        raise SeedError("participant ids must be unique")
    if mode not in ("turns", "continuous"):
        raise SeedError(f"mode must be 'turns' or 'continuous', got {mode!r}")
    if max_turns < 1:
        raise SeedError("max_turns must be >= 1")

    first_speaker = first or participants[0]
    if first_speaker not in participants:
        raise SeedError(f"first speaker {first_speaker!r} is not in participants")

    # ---- conversation type + seat roles ---------------------------------
    try:
        resolved_type = normalize_conv_type(conv_type)
        resolved_roles = validate_roles(resolved_type, participants, participant_roles)
        validate_seat_counts(resolved_type, participants, resolved_roles)
    except ConvTypeError as e:
        raise SeedError(str(e)) from e

    # Whoever runs the room opens it. Every caller already seeds the lead first
    # (orchestrate puts the moderator at the head of the list); this keeps a
    # hand-rolled call from producing a host who speaks third.
    lead = lead_of(resolved_type, resolved_roles)
    if lead is not None and first_speaker != lead:
        raise SeedError(
            f"the {resolved_type}'s lead seat ({lead!r}) must speak first; "
            f"got first={first_speaker!r}"
        )

    # ---- optional kickoff template rendering ----------------------------
    kickoff_rendered: Optional[str] = None
    if preset or tone or kickoff_template_file:
        if not tone:
            raise SeedError(
                "tone is required when a custom template is provided without a preset "
                "(no tone to inject otherwise)"
            )
        template_path = Path(kickoff_template_file) if kickoff_template_file else _DEFAULT_TEMPLATE_PATH
        if not template_path.exists():
            raise SeedError(f"template file not found: {template_path}")
        template_body = load_template(template_path)
        kickoff_rendered = render_kickoff(
            template_body,
            topic,
            tone + deliverable_clause(resolved_type, preset),
            n_participants=len(participants),
        )

    # ---- DB write -------------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        for table, column, ddl in _MIGRATIONS:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(ddl)

        current_turn = first_speaker if mode == "turns" else None
        ts = now_iso()
        personas_json = json.dumps(participant_personas) if participant_personas else None
        cur = conn.execute(
            """
            INSERT INTO conversations
                (topic, participants, mode, max_turns, current_turn, status,
                 end_reason, created_at, updated_at, preset, kickoff_template,
                 participant_personas, conv_type, participant_roles)
            VALUES (?, ?, ?, ?, ?, 'active', NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (topic, json.dumps(participants), mode, max_turns,
             current_turn, ts, ts, preset, kickoff_rendered, personas_json,
             resolved_type, json.dumps(resolved_roles)),
        )
        conv_id = cur.lastrowid

        if initial_system_message:
            conn.execute(
                "INSERT INTO messages (conversation_id, sender, content, signal, created_at) "
                "VALUES (?, 'system', ?, NULL, ?)",
                (conv_id, initial_system_message, ts),
            )
    finally:
        conn.close()

    return SeedResult(
        conversation_id=int(conv_id),
        topic=topic,
        participants=participants,
        mode=mode,
        max_turns=max_turns,
        first=first_speaker,
        preset=preset,
        kickoff_rendered=kickoff_rendered,
        conv_type=resolved_type,
        participant_roles=resolved_roles,
    )
