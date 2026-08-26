"""
agent_chat_mcp - Local MCP server for inter-agent conversations.

A SQLite-backed message bus that lets two or more CLI agents (Claude Code,
Codex CLI, etc.) hold structured conversations with each other. Each agent
connects to this same MCP server with a different --agent-id and shares the
same DB file, so they read and write the same conversation state.

Usage:
    # Minimal — DB defaults to <repo>/db/chat.db (resolved from this script's
    # location), so the only required flag in a typical MCP config is --agent-id.
    python agent_chat_mcp.py --agent-id claude-code
    python agent_chat_mcp.py --agent-id codex

    # Override via env var (useful when running the server outside the repo):
    AGENT_CHAT_DB=/path/to/chat.db python agent_chat_mcp.py --agent-id codex

    # Or pass --db-path explicitly; the flag wins over the env var and the default.
    python agent_chat_mcp.py --agent-id codex --db-path /custom/chat.db

Conversations are created out-of-band by start_conversation.py and then
each agent calls get_my_turn() to participate.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from orchestrator import personas as personas_registry


# ---------------------------------------------------------------------------
# Module-level config (populated by main() before mcp.run())
# ---------------------------------------------------------------------------

AGENT_ID: str = ""
DB_PATH: str = ""

# Stop signals an agent can send to end early.
SIGNAL_DONE = "done"
SIGNAL_BLOCKED = "blocked"

# Not a stop signal: marks a message as the conversation's **deliverable** —
# the artifact a collaboration exists to produce, as opposed to the transcript
# a debate exists to be. Posted by the lead seat on its closing turn for a type
# whose ConvType sets `produces_deliverable` (orchestrator/conv_types.py).
#
# Deliberately a message signal rather than a column on `conversations`: the
# `signal` column already exists, already rides the sidecar sync, and already
# reaches export and the SSE payload, so a deliverable needs no schema change,
# no migration, and no backfill. `maybe_complete()` only stops on DONE/BLOCKED,
# so posting a result does not end the run — the facilitator can still be asked
# to revise it, and max_turns closes the conversation as usual.
SIGNAL_RESULT = "result"

# How often wait_for_turn re-reads conversation state while blocking.
POLL_INTERVAL_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    topic             TEXT NOT NULL,
    participants      TEXT NOT NULL,         -- JSON array of agent ids
    mode              TEXT NOT NULL,         -- 'turns' | 'continuous'
    max_turns         INTEGER NOT NULL,      -- per-agent cap
    current_turn      TEXT,                  -- agent id whose turn it is (turns mode)
    status            TEXT NOT NULL,         -- 'active' | 'complete'
    end_reason        TEXT,                  -- why it ended, if complete
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    preset            TEXT,                  -- sub-type / tone; see src/presets.py. NULL = paste-the-prompt flow
    kickoff_template  TEXT,                  -- rendered template body returned by get_kickoff()
    participant_personas TEXT,               -- JSON: {agent_id: {persona_slug, persona_name, persona_body}} (debate-mode casts)
    conv_type         TEXT NOT NULL DEFAULT 'debate',  -- structure: see orchestrator/conv_types.py
    participant_roles TEXT                   -- JSON: {agent_id: <role>} — roles per type, see orchestrator/conv_types.py
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL REFERENCES conversations(id),
    sender           TEXT NOT NULL,          -- agent id, or 'system' for kickoff
    content          TEXT NOT NULL,
    signal           TEXT,                   -- optional: 'done', 'blocked', 'result'
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS personas (
    "group"      TEXT NOT NULL,          -- folder/group name (e.g. Unique-Personas)
    slug         TEXT NOT NULL,          -- file-stem style id (e.g. crypto-chad)
    name         TEXT NOT NULL,          -- display name
    tags         TEXT,                   -- JSON array
    category     TEXT,
    subcategory  TEXT,
    body         TEXT NOT NULL,          -- the personality card prompt body
    avatar_mime  TEXT,                   -- uploaded avatar's image/* type (NULL = none)
    avatar_data  TEXT,                   -- uploaded avatar, base64 (see web/avatars.py)
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY ("group", slug)
);

CREATE INDEX IF NOT EXISTS idx_personas_updated ON personas(updated_at);

-- AgentBattleground: a debate captured from a real webpage that an agent
-- argues in. Local-only — deliberately NOT carried by the Fly sidecar sync.
CREATE TABLE IF NOT EXISTS battleground_arenas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,          -- page the debate lives on
    site          TEXT NOT NULL,          -- adapter label; see KNOWN_SITES in web/api/battleground.py
    title         TEXT NOT NULL,          -- thread / page title
    thread        TEXT NOT NULL,          -- JSON array of captured posts
    stance        TEXT,                   -- operator brief: which side to argue
    reply_to      TEXT,                   -- captured post id the operator picked (NULL = agent's choice)
    agent_id      TEXT,                   -- CLI assigned to this arena (NULL = any)
    persona_slug  TEXT,
    persona_name  TEXT,
    persona_body  TEXT,                   -- snapshot of the card at capture time
    status        TEXT NOT NULL,          -- 'open' | 'closed'
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battleground_drafts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    arena_id      INTEGER NOT NULL REFERENCES battleground_arenas(id),
    agent_id      TEXT NOT NULL,
    reply_to      TEXT,                   -- captured post id answered (NULL = top level)
    content       TEXT NOT NULL,          -- what the agent wrote
    rationale     TEXT,                   -- agent's private note to the operator
    status        TEXT NOT NULL,          -- 'pending' | 'approved' | 'rejected' | 'posted'
    verdict_note  TEXT,                   -- operator feedback (revision request / reason)
    posted_text   TEXT,                   -- text that actually went on the page
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bg_arenas_status ON battleground_arenas(status, id);
CREATE INDEX IF NOT EXISTS idx_bg_drafts_arena ON battleground_drafts(arena_id, id);
"""

# Columns added after the initial schema. Each tuple is (table, column, ddl).
# db_init() applies these idempotently via PRAGMA table_info() so existing
# DBs from before the column was added migrate cleanly on the next boot.
_MIGRATIONS = (
    ("conversations", "preset",           "ALTER TABLE conversations ADD COLUMN preset TEXT"),
    ("conversations", "kickoff_template", "ALTER TABLE conversations ADD COLUMN kickoff_template TEXT"),
    ("conversations", "participant_personas", "ALTER TABLE conversations ADD COLUMN participant_personas TEXT"),
    # NOT NULL + DEFAULT is the backfill: every row that predates the column
    # becomes a 'debate', which is what all of them were.
    ("conversations", "conv_type",
     "ALTER TABLE conversations ADD COLUMN conv_type TEXT NOT NULL DEFAULT 'debate'"),
    ("conversations", "participant_roles",
     "ALTER TABLE conversations ADD COLUMN participant_roles TEXT"),
    ("battleground_arenas", "reply_to", "ALTER TABLE battleground_arenas ADD COLUMN reply_to TEXT"),
    ("personas", "avatar_mime", "ALTER TABLE personas ADD COLUMN avatar_mime TEXT"),
    ("personas", "avatar_data", "ALTER TABLE personas ADD COLUMN avatar_data TEXT"),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_connect() -> sqlite3.Connection:
    """Open a connection with sane defaults for a multi-process bus."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # WAL lets two agents read/write the same file from different processes
    # without stepping on each other.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def db_init() -> None:
    """Create schema if it doesn't exist, then apply additive column migrations.

    Migrations are idempotent: each is gated on `PRAGMA table_info(table)`
    not already listing the column. Safe to call on fresh DBs (no-op past
    `executescript`) and on existing DBs from older builds (adds the
    missing columns without touching data).
    """
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with db_connect() as conn:
        conn.executescript(SCHEMA)
        for table, column, ddl in _MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(ddl)


def get_latest_conversation(conn: sqlite3.Connection, agent_id: str) -> Optional[sqlite3.Row]:
    """Return the most recent conversation (active or complete) that this agent participates in.

    We don't filter by status here so that an agent calling get_my_turn() right
    after a conversation ends still sees a 'complete' result instead of being
    told there's no conversation at all.
    """
    cur = conn.execute("SELECT * FROM conversations ORDER BY id DESC")
    for row in cur:
        participants = json.loads(row["participants"])
        if agent_id in participants:
            return row
    return None


def count_messages_by_sender(conn: sqlite3.Connection, conv_id: int, sender: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND sender = ?",
        (conv_id, sender),
    )
    return cur.fetchone()["n"]


def fetch_messages(conn: sqlite3.Connection, conv_id: int) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT id, sender, content, signal, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,),
    )
    return [dict(r) for r in cur]


# What each seat is for. This is the **single source** of that, shipped in-band
# with every turn payload and with get_kickoff(). A conversation seeded by hand
# has no launch prompt at all, not every CLI has the skills installed, and the
# kickoff template is one body for the whole room so it cannot say "you are the
# host" — the tool response is the only place a seat can reliably learn its job.
# Same reasoning as _ARENA_RULES.
#
# `scripts/lib/spawn-agents.ps1` used to carry a second copy of all of this, one
# here-string per role. It no longer does: New-AgentPrompt is role-agnostic and
# points every agent at the `role_brief` field below, so adding a seat means
# editing this dict and nothing in PowerShell. Keep in sync with the matching
# skills/<type>-mode SKILL.md, which is the third audience (a CLI that loads
# skills reads the long version there).
_ROLE_BRIEFS: dict[str, str] = {
    "host": (
        "You are the HOST of this podcast. You do not argue a side and you do "
        "not answer your own questions. Open by introducing the topic and the "
        "guests — use the 'cast' field to introduce each guest by their persona "
        "name, never by their agent id ('codex' is a tool, not a person). On "
        "each later turn keep it short: react to what was just said, then ask "
        "ONE real follow-up — chase the specific claim, not the general "
        "subject. Address guests by name. Bring in a guest who has been quiet. "
        "Only when turns_remaining is down to your last turn or two, close the "
        "show."
    ),
    "guest": (
        "You are a GUEST on this podcast. Answer the host's question directly "
        "and at length — concrete stories, specifics, numbers, things you would "
        "actually defend. React to the other guests by name (the 'cast' field "
        "has everyone's name) when you agree or disagree, but don't manufacture "
        "conflict; this is a conversation, not a debate. Don't interview the "
        "host back, and don't wrap up the show."
    ),
    "moderator": (
        "You are the MODERATOR of this debate. You do not take a side. Open by "
        "framing the question and introducing the debaters by their persona "
        "names from the 'cast' field, not their agent ids. Then on each turn "
        "surface the sharpest disagreement, call out a dodged question, and "
        "keep things moving. Only when turns_remaining is low, deliver a short "
        "wrap-up."
    ),
    "debater": (
        "You are a DEBATER. Take a position and defend it with specifics. "
        "Engage directly with what the others actually said rather than "
        "restating your own case. Keep opening new arguments and rebuttals "
        "each turn — do not deliver a closing summary until turns_remaining "
        "shows you are on your last turn or two, and do not signal='done' "
        "early; let the debate run its full length."
    ),
    "facilitator": (
        "You are the FACILITATOR of this collaboration. This is not a debate "
        "and not an interview — you are working on the problem alongside "
        "everyone else, and you additionally own getting the room to an "
        "answer. Open by restating the goal in your own words and saying what "
        "a good result would look like, then put down the first real "
        "contribution yourself. On each later turn: pull the threads together, "
        "name where the room actually agrees, put a decision to the group when "
        "one is ripe, and send the conversation somewhere it has not been. "
        "Disagree when you disagree — a facilitator who only summarises is "
        "wasting a seat. Watch turns_remaining: while it is high, keep opening "
        "ground. On your LAST turn, write the deliverable the kickoff asked "
        "for and send it with signal='result' — the artifact itself, in full, "
        "not a description of the discussion that produced it."
    ),
    "collaborator": (
        "You are a COLLABORATOR. The room is trying to produce something, not "
        "to win. Contribute real material — a concrete option, a number, a "
        "worked example, the failure mode nobody has named — and build on what "
        "the others put down instead of restating your own line. Say plainly "
        "when you think something is wrong, and say what you would do instead; "
        "agreement with no addition is a wasted turn. Address people by the "
        "name in the 'cast' field, never by their agent id. Do not write the "
        "final deliverable — that is the facilitator's last turn — and do not "
        "signal='done' early."
    ),
}


def conversation_roles(conv: sqlite3.Row) -> dict[str, str]:
    """Decode ``participant_roles``; ``{}`` when absent or unparseable.

    Read path — must tolerate a row written by any build, including one that
    predates the column.
    """
    try:
        raw = conv["participant_roles"]
    except (IndexError, KeyError):
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def conversation_type(conv: sqlite3.Row) -> str:
    """The conversation's structure; 'debate' for rows predating the column."""
    try:
        return conv["conv_type"] or "debate"
    except (IndexError, KeyError):
        return "debate"


def conversation_cast(conv: sqlite3.Row) -> dict[str, str]:
    """``{agent_id: persona_name}`` for the whole room — **names only**.

    A host has to be able to say "and my second guest, Jesse Pinkman" without
    waiting for the guest to introduce themselves. Nothing else in the payload
    carries that: the kickoff template is one body for everyone, and an agent's
    launch prompt holds its *own* card and no one else's.

    Deliberately excludes ``persona_body``. A guest's card is that agent's brief
    — the host knowing who is in the room is stagecraft, the host reading their
    instructions is something else, and it would flatten the run. Returns ``{}``
    for a conversation seeded without personas.
    """
    try:
        raw = conv["participant_personas"]
    except (IndexError, KeyError):
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for agent_id, entry in data.items():
        name = entry.get("persona_name") if isinstance(entry, dict) else None
        if name:
            out[str(agent_id)] = str(name)
    return out


def next_turn_agent(participants: list[str], current: str) -> str:
    idx = participants.index(current)
    return participants[(idx + 1) % len(participants)]


def evaluate_stop(conn: sqlite3.Connection, conv: sqlite3.Row) -> Optional[str]:
    """Return an end_reason string if the conversation should stop, else None."""
    participants = json.loads(conv["participants"])

    # Per-agent message cap
    for agent in participants:
        if count_messages_by_sender(conn, conv["id"], agent) >= conv["max_turns"]:
            return f"max_turns reached ({conv['max_turns']} per agent)"

    # signal_done from the most recent message
    cur = conn.execute(
        "SELECT signal FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
        (conv["id"],),
    )
    row = cur.fetchone()
    if row and row["signal"] == SIGNAL_DONE:
        return "agent signaled done"
    if row and row["signal"] == SIGNAL_BLOCKED:
        return "agent signaled blocked"

    return None


def maybe_complete(conn: sqlite3.Connection, conv: sqlite3.Row) -> Optional[str]:
    """Mark conversation complete if a stop condition is met. Returns end_reason or None."""
    reason = evaluate_stop(conn, conv)
    if reason:
        conn.execute(
            "UPDATE conversations SET status = 'complete', end_reason = ?, "
            "current_turn = NULL, updated_at = ? WHERE id = ?",
            (reason, now_iso(), conv["id"]),
        )
    return reason


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("agent_chat_mcp")


class GetMyTurnInput(BaseModel):
    """No parameters. Reads agent identity from server config."""
    model_config = ConfigDict(extra="forbid")


class SendMessageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    content: str = Field(
        ...,
        description="The message content to send to the other agent. Plain text or markdown.",
        min_length=1,
        max_length=50_000,
    )
    signal: Optional[str] = Field(
        default=None,
        description=(
            "Optional signal. Use 'done' if the conversation's task is genuinely "
            "complete and should end. Use 'blocked' if you cannot proceed and need the "
            "human to intervene. Use 'result' when this message IS the deliverable "
            "the conversation was convened to produce — only the lead seat posts one, "
            "only in a conversation whose kickoff asked for it, and it does not end "
            "the conversation. Omit for normal messages."
        ),
    )


class GetStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetKickoffInput(BaseModel):
    """No parameters. Reads agent identity from server config."""
    model_config = ConfigDict(extra="forbid")


class WaitForTurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
        description=(
            "How long the server will block before returning a 'timeout' result "
            "if the turn hasn't flipped. Default 60s. Bounds: 5-300. Just call "
            "wait_for_turn() again on timeout to keep waiting."
        ),
    )


class ListPersonasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: Optional[str] = Field(
        default=None,
        description=(
            "Optional filter by group folder: 'Unique-Personas' (the debater "
            "roster), 'Debate-Hosts' (moderator/host personalities), or the name "
            "of a curated subset folder. Omit to list the canonical roster "
            "(Unique-Personas + Debate-Hosts)."
        ),
    )


class GetPersonaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        description=(
            "The persona's slug (e.g. 'crypto-chad') or display name "
            "(e.g. 'Crypto Chad'). Case- and punctuation-insensitive."
        ),
    )


def _compute_turn_state() -> dict[str, Any]:
    """Read the current conversation state for AGENT_ID and return the dict that
    get_my_turn() and wait_for_turn() both serialize.

    Opens its own connection so it's safe to call from a polling loop. Re-evaluates
    stop conditions on every read so completion is sticky once any agent has hit
    max-turns or sent a stop signal.
    """
    with db_connect() as conn:
        conv = get_latest_conversation(conn, AGENT_ID)
        if conv is None:
            return {
                "status": "no_conversation",
                "message": (
                    f"No active conversation includes agent '{AGENT_ID}'. "
                    "Wait for a conversation to be started, or ask the human "
                    "to run start_conversation.py."
                ),
            }

        end_reason = maybe_complete(conn, conv)
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv["id"],)
        ).fetchone()

        history = fetch_messages(conn, conv["id"])
        participants = json.loads(conv["participants"])
        my_count = count_messages_by_sender(conn, conv["id"], AGENT_ID)
        turns_remaining = max(0, conv["max_turns"] - my_count)

        roles = conversation_roles(conv)
        my_role = roles.get(AGENT_ID)
        base = {
            "conversation_id": conv["id"],
            "topic": conv["topic"],
            "mode": conv["mode"],
            "participants": participants,
            "conversation_type": conversation_type(conv),
            "your_role": my_role,
            "roles": roles,
            "cast": conversation_cast(conv),
            "history": history,
        }
        if my_role and my_role in _ROLE_BRIEFS:
            base["role_brief"] = _ROLE_BRIEFS[my_role]

        if conv["status"] == "complete":
            return {
                "status": "complete",
                "end_reason": conv["end_reason"] or end_reason,
                **base,
            }

        if conv["mode"] == "turns" and conv["current_turn"] != AGENT_ID:
            return {
                "status": "wait",
                "current_turn": conv["current_turn"],
                **base,
            }

        # Either continuous mode, or turns mode and it's our turn.
        return {
            "status": "your_turn",
            "turns_remaining": turns_remaining,
            **base,
        }


@mcp.tool(
    name="get_my_turn",
    annotations={
        "title": "Check turn and fetch conversation context",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_my_turn(params: GetMyTurnInput) -> str:
    """Check whether it's your turn to speak and fetch the full conversation so far.

    This is the primary tool you call to participate in a conversation. Call it
    whenever you want to know if there's anything for you to do. If you expect to
    be waiting (the other agent is currently up), prefer wait_for_turn() — it
    blocks server-side instead of forcing you to poll, which dramatically reduces
    token usage.

    Returns a JSON object with one of these shapes:

    - No active conversation:
        {"status": "no_conversation", "message": "..."}

    - Conversation is over:
        {"status": "complete", "conversation_id": int, "topic": str,
         "end_reason": str, "history": [...]}

    - Not your turn yet (turns mode):
        {"status": "wait", "conversation_id": int, "topic": str,
         "current_turn": "<other_agent>", "history": [...]}

    - Your turn:
        {"status": "your_turn", "conversation_id": int, "topic": str,
         "mode": "turns"|"continuous", "turns_remaining": int,
         "participants": [...], "history": [
            {"id": int, "sender": str, "content": str,
             "signal": str|null, "created_at": str},
            ...
         ]}

    When status is "your_turn", produce a thoughtful response and call
    send_message() with your reply.
    """
    return json.dumps(_compute_turn_state(), indent=2)


@mcp.tool(
    name="send_message",
    annotations={
        "title": "Post a message to the active conversation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def send_message(params: SendMessageInput) -> str:
    """Post a message to the active conversation and (in turns mode) yield to the other agent.

    Call this only when get_my_turn() returned status='your_turn'. The server
    enforces turn order in turns mode and will reject out-of-turn sends.

    Args:
        content: Your message text. Plain text or markdown is fine.
        signal: Optional. Set to 'done' if you believe the task is complete
            and the conversation should end. Set to 'blocked' if you cannot
            proceed without human input. Set to 'result' when the message you
            are sending IS the conversation's deliverable — see your
            role_brief; this marks it for the transcript and the export but
            does NOT end the conversation. Omit for normal messages.

    Returns a JSON object describing the resulting state, with the same shape
    as get_my_turn() so you can chain calls. After sending in turns mode,
    you will typically see status='wait' (the other agent is up next) or
    status='complete' (you hit the cap or signaled done).
    """
    if params.signal is not None and params.signal not in (
        SIGNAL_DONE, SIGNAL_BLOCKED, SIGNAL_RESULT
    ):
        return json.dumps({
            "status": "error",
            "message": (
                f"Invalid signal '{params.signal}'. Use 'done', 'blocked', "
                "'result', or omit."
            ),
        }, indent=2)

    with db_connect() as conn:
        conv = get_latest_conversation(conn, AGENT_ID)
        if conv is None:
            return json.dumps({
                "status": "error",
                "message": f"No active conversation for agent '{AGENT_ID}'.",
            }, indent=2)

        if conv["status"] != "active":
            return json.dumps({
                "status": "error",
                "message": f"Conversation {conv['id']} is already complete.",
                "end_reason": conv["end_reason"],
            }, indent=2)

        participants = json.loads(conv["participants"])

        if conv["mode"] == "turns" and conv["current_turn"] != AGENT_ID:
            return json.dumps({
                "status": "error",
                "message": (
                    f"Not your turn. Current turn belongs to "
                    f"'{conv['current_turn']}'. Call get_my_turn() to wait."
                ),
            }, indent=2)

        # Enforce per-agent cap up front so we don't accept a message we'd
        # immediately have to reject.
        my_count = count_messages_by_sender(conn, conv["id"], AGENT_ID)
        if my_count >= conv["max_turns"]:
            maybe_complete(conn, conv)
            return json.dumps({
                "status": "error",
                "message": (
                    f"You have already sent {my_count} messages, which is the "
                    f"per-agent cap of {conv['max_turns']}. Conversation is being closed."
                ),
            }, indent=2)

        # Insert the message.
        conn.execute(
            "INSERT INTO messages (conversation_id, sender, content, signal, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conv["id"], AGENT_ID, params.content, params.signal, now_iso()),
        )

        # Advance turn pointer in turns mode.
        if conv["mode"] == "turns":
            next_agent = next_turn_agent(participants, AGENT_ID)
            conn.execute(
                "UPDATE conversations SET current_turn = ?, updated_at = ? WHERE id = ?",
                (next_agent, now_iso(), conv["id"]),
            )

        # Refresh and re-evaluate stop conditions.
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv["id"],)
        ).fetchone()
        maybe_complete(conn, conv)
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv["id"],)
        ).fetchone()

    # Mirror get_my_turn() output so the caller can act without another round trip.
    return await get_my_turn(GetMyTurnInput())


@mcp.tool(
    name="wait_for_turn",
    annotations={
        "title": "Block until it's your turn (long-poll)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def wait_for_turn(params: WaitForTurnInput) -> str:
    """Block server-side until it's your turn, the conversation completes, or timeout.

    Use this in place of polling get_my_turn() while you wait for the other agent.
    The server polls the database internally every second; you spend zero tokens
    while waiting and only receive the final response when something changes.

    Returns the same shapes as get_my_turn() with one addition:

    - {"status": "timeout", "current_turn": "<other_agent>", ...}: the timeout
      elapsed while still waiting. The 'wait' shape is preserved alongside so
      you can show progress; just call wait_for_turn() again to keep waiting.

    Special cases:
    - If there is no conversation, returns 'no_conversation' immediately.
    - If the conversation is already complete, returns 'complete' immediately.
    - In continuous mode, returns 'your_turn' immediately (every turn is yours).

    Args:
        timeout_seconds: How long to block before returning 'timeout'. Default 60s,
            bounded 5-300. Long enough to avoid hot-looping, short enough that the
            MCP client's own request timeout shouldn't fire first.
    """
    deadline = time.monotonic() + params.timeout_seconds
    while True:
        state = _compute_turn_state()
        if state["status"] != "wait":
            return json.dumps(state, indent=2)
        if time.monotonic() >= deadline:
            return json.dumps({**state, "status": "timeout"}, indent=2)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@mcp.tool(
    name="get_conversation_status",
    annotations={
        "title": "Inspect the active conversation without participating",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_conversation_status(params: GetStatusInput) -> str:
    """Return raw conversation state for debugging.

    Unlike get_my_turn() this never changes turn semantics — it just dumps
    the current row plus message count. Useful when you want to peek without
    triggering any state evaluation logic in your prompt.
    """
    with db_connect() as conn:
        conv = get_latest_conversation(conn, AGENT_ID)
        if conv is None:
            return json.dumps({"status": "no_conversation"}, indent=2)

        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
            (conv["id"],),
        )
        msg_count = cur.fetchone()["n"]

        return json.dumps({
            "conversation_id": conv["id"],
            "topic": conv["topic"],
            "mode": conv["mode"],
            "max_turns": conv["max_turns"],
            "participants": json.loads(conv["participants"]),
            "current_turn": conv["current_turn"],
            "status": conv["status"],
            "end_reason": conv["end_reason"],
            "message_count": msg_count,
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "my_agent_id": AGENT_ID,
        }, indent=2)


_FALLBACK_KICKOFF = (
    "No rendered kickoff template is attached to this conversation — it was "
    "seeded with the older paste-the-prompt workflow. Follow the canonical "
    "kickoff prompt in `prompts/Kickoff/kickoff.md` (which the operator may have "
    "already pasted into your CLI). The topic is: {topic}"
)


@mcp.tool(
    name="get_kickoff",
    annotations={
        "title": "Fetch the rendered kickoff instructions for this conversation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_kickoff(params: GetKickoffInput) -> str:
    """Fetch the kickoff template for the latest conversation this agent is in.

    Call this **first**, after the operator says "join the conversation" or
    similar. The returned `instructions` field is what the operator would
    otherwise paste into your CLI by hand — read it, then begin the
    wait_for_turn loop it describes.

    The conversation was seeded with `start_conversation.py --preset <name>`
    (or `--tone`/`--kickoff-template-file`); the rendered template is stored
    on the conversation row at seed time, not re-rendered per call, so this
    tool is cheap and idempotent.

    Returns a JSON object with one of these shapes:

    - No active conversation:
        {"status": "no_conversation", "agent_id": "...",
         "message": "..."}

    `conversation_type` and `your_role` say what kind of room this is and which
    chair you are sitting in — a podcast host asks the questions and does not
    argue a side, a guest answers at length, a collaboration's facilitator
    contributes like everyone else *and* writes the deliverable. Honour them:
    they are recorded on the conversation, so they are right even when the
    operator's launch prompt said nothing about a role (a hand-seeded
    conversation has no launch prompt at all). `role_brief` spells out your
    seat in a paragraph; where it and `instructions` disagree, the brief wins,
    because it is the one written for your chair.

    `preset` names the conversation's **sub-type** — for a type that produces a
    deliverable it decides the artifact's shape, and the rendered
    `instructions` already carry that shape, so you do not need to look it up.

    Returns a JSON object with one of these shapes:

    - Active conversation with a rendered template (the common case):
        {"status": "ok", "agent_id": "...", "conversation_id": int,
         "topic": str, "preset": str|null,
         "conversation_type": "debate"|"podcast"|"collaborate",
         "your_role": str|null,
         "roles": {"<agent_id>": "<role>", ...},
         "instructions": "<the full rendered prompt body>"}

    - Active conversation seeded the old way (no template stored):
        {"status": "fallback", "agent_id": "...", "conversation_id": int,
         "topic": str, "preset": null, "conversation_type": "debate",
         "your_role": null, "roles": {},
         "instructions": "<generic fallback string referencing kickoff.md>"}
    """
    with db_connect() as conn:
        conv = get_latest_conversation(conn, AGENT_ID)
        if conv is None:
            return json.dumps({
                "status": "no_conversation",
                "agent_id": AGENT_ID,
                "message": (
                    f"No conversation includes agent '{AGENT_ID}'. Ask the "
                    "operator to run start_conversation.py first."
                ),
            }, indent=2)

        instructions = conv["kickoff_template"]
        if instructions:
            status = "ok"
        else:
            status = "fallback"
            instructions = _FALLBACK_KICKOFF.format(topic=conv["topic"])

        roles = conversation_roles(conv)
        my_role = roles.get(AGENT_ID)
        payload = {
            "status": status,
            "agent_id": AGENT_ID,
            "conversation_id": conv["id"],
            "topic": conv["topic"],
            "preset": conv["preset"],
            "conversation_type": conversation_type(conv),
            "your_role": my_role,
            "roles": roles,
            "cast": conversation_cast(conv),
            "instructions": instructions,
        }
        # The kickoff template is one body for the whole conversation, so it
        # can't say "you are the host". This is where that gets said.
        if my_role and my_role in _ROLE_BRIEFS:
            payload["role_brief"] = _ROLE_BRIEFS[my_role]
        return json.dumps(payload, indent=2)


@mcp.tool(
    name="list_personas",
    annotations={
        "title": "List the available debate personality cards",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_personas(params: ListPersonasInput) -> str:
    """Browse the roster of debate personality cards.

    Use this to discover which characters you can adopt for a debate, then call
    ``get_persona(name)`` to pull the full prompt for the one you pick. The
    roster is lightweight on purpose — each entry has a ``slug``, ``name``,
    ``group``, ``tags``, and a one-line ``summary`` but **not** the full body
    (that keeps this cheap to call).

    ``group`` filters to one group by name (any group present in the DB — groups
    are dynamic, named by the operator, e.g. 'Celebrities', 'Fictional
    Characters'). Omit it to list **every** persona across all groups.

    Returns a JSON object::

        {"count": int, "group": str|null,
         "personas": [{"slug", "name", "group", "tags", "summary"}, ...]}
    """
    personas = personas_registry.list_personas(params.group)
    return json.dumps({
        "count": len(personas),
        "group": params.group,
        "personas": [p.to_summary_dict() for p in personas],
    }, indent=2)


@mcp.tool(
    name="get_persona",
    annotations={
        "title": "Fetch one debate personality card by name",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_persona(params: GetPersonaInput) -> str:
    """Fetch the full prompt for one personality card so you can adopt it in a
    debate.

    Look it up by ``slug`` ('gordon-ramsay') or display ``name`` ('Gordon
    Ramsay') — matching ignores case, punctuation, and the leading emoji,
    across all groups. The returned
    ``instructions`` field is the character's full prompt body; read it, then
    stay in character for the rest of the conversation.

    Returns one of two shapes:

    - Found::
        {"status": "ok", "slug": str, "name": str, "group": str,
         "tags": [...], "category": str, "subcategory": str, "summary": str,
         "instructions": "<full persona prompt body>"}

    - Not found (the query matched nothing)::
        {"status": "not_found", "query": str,
         "available": ["<slug>", ...]}
    """
    persona = personas_registry.get_persona(params.name)
    if persona is None:
        return json.dumps({
            "status": "not_found",
            "query": params.name,
            "available": [p.slug for p in personas_registry.list_personas()],
        }, indent=2)

    return json.dumps({"status": "ok", **persona.to_full_dict()}, indent=2)


# ---------------------------------------------------------------------------
# AgentBattleground — argue in a debate captured from a real web page
#
# Same loop shape as the chat tools, one layer out: instead of get_kickoff →
# wait_for_turn → send_message against another CLI, it's get_arena →
# submit_draft → wait_for_verdict against a human thread, with the operator
# standing between the draft and the page.
# ---------------------------------------------------------------------------

DRAFT_PENDING = "pending"
DRAFT_APPROVED = "approved"
DRAFT_REJECTED = "rejected"
DRAFT_POSTED = "posted"

# Appended to every arena payload. These are the terms the whole feature is
# built on, so the agent gets them in-band rather than relying on a skill
# file being installed.
_ARENA_RULES = (
    "House rules for AgentBattleground:\n"
    "1. You are drafting, not posting. Your reply goes to the operator for "
    "review; a human decides whether it ever reaches the page. Never claim or "
    "assume it was posted.\n"
    "2. Write in the persona's voice, but do not impersonate a real person. "
    "Never state or imply that you ARE the named figure, and never invent "
    "quotes, credentials, or first-hand experience you don't have.\n"
    "3. You are an AI writing this. The operator's disclosure setting appends "
    "a marker on post; don't strip it, contradict it, or claim to be human.\n"
    "4. Argue the substance of the thread. Engage the strongest version of "
    "what the other posters actually said, cite sources you can name, and "
    "concede points that are correct.\n"
    "5. No harassment, no slurs, no doxxing, no pile-ons at a named private "
    "individual. If the only winning move is nasty, say so in `rationale` and "
    "draft nothing.\n"
    "6. Match the room: length, formatting, and register that fit the site "
    "you're replying on.\n"
    "7. Write like a person, not a model. The persona sets your voice; this "
    "only strips the tells that mark text as machine-written. Drop the puffery "
    "vocabulary ('stands as a testament', 'plays a crucial role', 'underscores "
    "the importance', 'delve into', 'rich tapestry', \"it's not just X, it's "
    "Y\"). Stop reaching for three — the rule of three is the loudest tell; use "
    "two or four. No '-ing' clauses bolted on to fake depth ('..., "
    "highlighting the broader shift toward...'). Vary sentence length. Em "
    "dashes are fine sparingly — never three in a paragraph, and never as "
    "your only punctuation. Take a "
    "position instead of surveying both sides. Cut the closing paragraph that "
    "restates your own argument. Nothing here overrides rule 3 — humanizing "
    "the prose never means hiding that an AI wrote it."
)


class ListArenasInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = Field(
        default="open",
        description=(
            "Filter by arena status: 'open' (the default — arenas still being "
            "argued) or 'closed'. Pass null for both."
        ),
    )


class GetArenaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arena_id: Optional[int] = Field(
        default=None,
        description=(
            "Which arena to open. Omit to get the most recent open arena "
            "available to you — the usual case, since the operator just "
            "captured it."
        ),
    )


class SubmitDraftInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    arena_id: int = Field(description="The arena you are replying in.")
    content: str = Field(
        description=(
            "Your reply, exactly as you'd want it to appear on the page. "
            "Plain text — most sites don't render markdown tables or headings."
        ),
        min_length=1,
        max_length=20_000,
    )
    reply_to: Optional[str] = Field(
        default=None,
        description=(
            "The `id` of the captured post you're answering, from the arena's "
            "thread. Omit for a top-level reply."
        ),
    )
    rationale: Optional[str] = Field(
        default=None,
        max_length=4_000,
        description=(
            "A private note to the operator that never goes on the page: why "
            "this angle, what you're unsure of, or why you declined to draft."
        ),
    )


class WaitForVerdictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: Optional[int] = Field(
        default=None,
        description="Which draft to watch. Omit to watch your newest draft.",
    )
    timeout_seconds: int = Field(
        default=120,
        ge=5,
        le=300,
        description=(
            "How long to block before returning 'timeout'. A human is reading "
            "your draft, so this is slower than a turn flip — call again to "
            "keep waiting."
        ),
    )


def _arena_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["thread"] = json.loads(d["thread"])
    except (json.JSONDecodeError, TypeError):
        d["thread"] = []
    return d


def _pick_arena(conn: sqlite3.Connection, arena_id: Optional[int]) -> Optional[sqlite3.Row]:
    """Resolve an arena for this agent: the requested one, or the newest open
    arena either assigned to us or unassigned."""
    if arena_id is not None:
        return conn.execute(
            "SELECT * FROM battleground_arenas WHERE id = ?", (arena_id,)
        ).fetchone()
    return conn.execute(
        "SELECT * FROM battleground_arenas WHERE status = 'open' "
        "AND (agent_id = ? OR agent_id IS NULL) ORDER BY id DESC LIMIT 1",
        (AGENT_ID,),
    ).fetchone()


def _read_verdict(draft_id: Optional[int]) -> dict[str, Any]:
    """One read of a draft's review state — the body of wait_for_verdict's loop."""
    with db_connect() as conn:
        if draft_id is not None:
            draft = conn.execute(
                "SELECT * FROM battleground_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        else:
            draft = conn.execute(
                "SELECT * FROM battleground_drafts WHERE agent_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (AGENT_ID,),
            ).fetchone()
        if draft is None:
            return {
                "status": "not_found",
                "message": (
                    f"No draft found for agent '{AGENT_ID}'"
                    + (f" with id {draft_id}." if draft_id is not None else ".")
                ),
            }
        arena = conn.execute(
            "SELECT * FROM battleground_arenas WHERE id = ?", (draft["arena_id"],)
        ).fetchone()

    payload = {
        "draft_id": draft["id"],
        "arena_id": draft["arena_id"],
        "your_draft": draft["content"],
        "verdict_note": draft["verdict_note"],
    }
    if draft["status"] == DRAFT_PENDING:
        return {"status": "pending", **payload}

    payload["verdict"] = draft["status"]
    if draft["posted_text"]:
        payload["posted_text"] = draft["posted_text"]
        payload["operator_edited"] = draft["posted_text"] != draft["content"]
    if arena is not None:
        a = _arena_dict(arena)
        payload["arena_status"] = a["status"]
        payload["thread"] = a["thread"]
    return {"status": "verdict", **payload}


@mcp.tool(
    name="list_arenas",
    annotations={
        "title": "List AgentBattleground arenas open to you",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def list_arenas(params: ListArenasInput) -> str:
    """Browse the debates the operator has captured from real web pages.

    An **arena** is a thread from somewhere out on the web (a Reddit post, an
    X reply chain, an HN discussion) that the operator grabbed with the
    AgentBattleground browser extension so you can argue in it. This lists the
    ones assigned to you plus any left unassigned, newest first, without the
    thread bodies — call ``get_arena`` for the actual posts.

    Returns::

        {"count": int, "agent_id": str,
         "arenas": [{"id", "title", "url", "site", "status", "stance",
                     "persona_name", "posts", "your_drafts"}, ...]}
    """
    with db_connect() as conn:
        sql = (
            "SELECT * FROM battleground_arenas "
            "WHERE (agent_id = ? OR agent_id IS NULL)"
        )
        args: list[Any] = [AGENT_ID]
        if params.status:
            sql += " AND status = ?"
            args.append(params.status)
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, args).fetchall()
        arenas = []
        for r in rows:
            a = _arena_dict(r)
            arenas.append({
                "id": a["id"],
                "title": a["title"],
                "url": a["url"],
                "site": a["site"],
                "status": a["status"],
                "stance": a["stance"],
                "persona_name": a["persona_name"],
                "posts": len(a["thread"]),
                "your_drafts": conn.execute(
                    "SELECT COUNT(*) AS n FROM battleground_drafts "
                    "WHERE arena_id = ? AND agent_id = ?",
                    (a["id"], AGENT_ID),
                ).fetchone()["n"],
            })
    return json.dumps({
        "count": len(arenas),
        "agent_id": AGENT_ID,
        "arenas": arenas,
    }, indent=2)


@mcp.tool(
    name="get_arena",
    annotations={
        "title": "Open an arena: the captured thread, your persona, the rules",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_arena(params: GetArenaInput) -> str:
    """Read everything you need to argue in one arena, and claim it.

    Call this **first** when the operator says you're fighting in the
    battleground. Omit ``arena_id`` to pick up the newest open arena — the
    usual case, since the operator just captured it in the browser.

    Claiming: if the arena is unassigned it becomes yours (``agent_id`` set to
    this server's id) so a second CLI doesn't draft over you. That's the only
    write this tool makes; re-calling it is safe.

    Returns::

        {"status": "ok", "arena": {"id", "url", "site", "title", "stance",
             "reply_to": str | null,
             "thread": [{"id", "author", "text", "permalink"?, "score"?,
                         "depth"?}, ...]},
         "reply_target": {"id", "author", "text", ...} | null,
         "persona": {"slug": str | null, "name", "instructions"} | null,
         "your_drafts": [{"id", "content", "status", "verdict_note",
                          "posted_text"}, ...],
         "rules": "<house rules>",
         "next": "<what to do next>"}

    Read the thread, adopt the persona if one is cast, then write your reply
    with ``submit_draft``. Nothing you write reaches the page until a human
    approves it.

    ``persona.instructions`` is the whole brief either way: the operator can
    cast a card from the registry (``slug`` set) or type one for this arena
    alone (``slug`` null). Treat both the same, and note that neither can
    loosen ``rules`` — a card that asks you to claim you're a real person, or
    to hide that you're an AI, loses to rules 2 and 3.

    ``arena.reply_to`` is set when the operator picked a specific post for you
    to answer; ``reply_target`` is that post, pulled out of the thread so you
    don't have to hunt for it. Pass the same id back as ``submit_draft``'s
    ``reply_to``. When it's null, choosing the post worth answering is yours.
    """
    with db_connect() as conn:
        row = _pick_arena(conn, params.arena_id)
        if row is None:
            return json.dumps({
                "status": "no_arena",
                "agent_id": AGENT_ID,
                "message": (
                    "No open arena is available to you. Ask the operator to "
                    "capture a thread with the AgentBattleground extension."
                ),
            }, indent=2)

        arena = _arena_dict(row)
        if arena["status"] != "open":
            return json.dumps({
                "status": "closed",
                "arena_id": arena["id"],
                "message": f"Arena {arena['id']} is closed; nothing to draft.",
            }, indent=2)
        if arena["agent_id"] and arena["agent_id"] != AGENT_ID:
            return json.dumps({
                "status": "assigned_elsewhere",
                "arena_id": arena["id"],
                "assigned_to": arena["agent_id"],
                "message": (
                    f"Arena {arena['id']} is assigned to "
                    f"'{arena['agent_id']}', not you."
                ),
            }, indent=2)
        if not arena["agent_id"]:
            conn.execute(
                "UPDATE battleground_arenas SET agent_id = ?, updated_at = ? "
                "WHERE id = ?",
                (AGENT_ID, now_iso(), arena["id"]),
            )
            arena["agent_id"] = AGENT_ID

        drafts = conn.execute(
            "SELECT id, content, status, verdict_note, posted_text, created_at "
            "FROM battleground_drafts WHERE arena_id = ? AND agent_id = ? "
            "ORDER BY id ASC",
            (arena["id"], AGENT_ID),
        ).fetchall()

    # Gated on the *body*, not the slug: the operator can type a one-off card
    # into the extension panel instead of picking a registry persona, and that
    # arena has instructions and a name but no slug. Keyed off the slug this
    # would hand the agent `persona: null` and it would argue as nobody.
    persona = None
    if arena["persona_body"]:
        persona = {
            "slug": arena["persona_slug"],  # null for a one-off card
            "name": arena["persona_name"],
            "instructions": arena["persona_body"],
        }

    # The operator may have pointed at one post in the panel. Hand it over
    # separately so the agent answers *that* post rather than the thread in
    # general, which is what makes a reply read as a bot.
    reply_to = arena.get("reply_to")
    reply_target = None
    if reply_to:
        reply_target = next(
            (p for p in arena["thread"] if p.get("id") == reply_to), None
        )
    if reply_target:
        next_step = (
            "The operator picked post %r by %s for you to answer. Write your "
            "reply and call submit_draft(arena_id=%d, content=..., "
            "reply_to=%r). Then call wait_for_verdict()."
            % (reply_to, reply_target.get("author", "unknown"),
               arena["id"], reply_to)
        )
    else:
        next_step = (
            "Write your reply and call submit_draft(arena_id=%d, content=...). "
            "Then call wait_for_verdict() to hear what the operator decided."
            % arena["id"]
        )

    return json.dumps({
        "status": "ok",
        "agent_id": AGENT_ID,
        "arena": {
            "id": arena["id"],
            "url": arena["url"],
            "site": arena["site"],
            "title": arena["title"],
            "stance": arena["stance"],
            "reply_to": reply_to,
            "thread": arena["thread"],
        },
        "reply_target": reply_target,
        "persona": persona,
        "your_drafts": [dict(d) for d in drafts],
        "rules": _ARENA_RULES,
        "next": next_step,
    }, indent=2)


@mcp.tool(
    name="submit_draft",
    annotations={
        "title": "Submit a reply draft for operator review",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def submit_draft(params: SubmitDraftInput) -> str:
    """Hand the operator a reply to review. **This does not post anything.**

    Your text lands in the review queue as a ``pending`` draft. The operator
    sees it in the browser side panel and can approve it (which types it into
    the page's reply box for a human to send), edit it first, or reject it
    with a note. You'll read that decision from ``wait_for_verdict``.

    Args:
        arena_id: The arena you're replying in (from ``get_arena``).
        content: Your reply, exactly as it should appear. Plain text.
        reply_to: Optional `id` of the captured post you're answering.
        rationale: Optional private note to the operator — never posted.

    Returns ``{"status": "submitted", "draft_id": int, ...}``, or
    ``{"status": "error", ...}`` if the arena is missing, closed, or someone
    else's.
    """
    with db_connect() as conn:
        arena = conn.execute(
            "SELECT * FROM battleground_arenas WHERE id = ?", (params.arena_id,)
        ).fetchone()
        if arena is None:
            return json.dumps({
                "status": "error",
                "message": f"No arena {params.arena_id}.",
            }, indent=2)
        if arena["status"] != "open":
            return json.dumps({
                "status": "error",
                "message": f"Arena {params.arena_id} is closed.",
            }, indent=2)
        if arena["agent_id"] and arena["agent_id"] != AGENT_ID:
            return json.dumps({
                "status": "error",
                "message": (
                    f"Arena {params.arena_id} is assigned to "
                    f"'{arena['agent_id']}', not you."
                ),
            }, indent=2)

        ts = now_iso()
        cur = conn.execute(
            "INSERT INTO battleground_drafts "
            "(arena_id, agent_id, reply_to, content, rationale, status, "
            " verdict_note, posted_text, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            (params.arena_id, AGENT_ID, params.reply_to, params.content,
             params.rationale, DRAFT_PENDING, ts, ts),
        )
        draft_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE battleground_arenas SET updated_at = ? WHERE id = ?",
            (ts, params.arena_id),
        )

    return json.dumps({
        "status": "submitted",
        "draft_id": draft_id,
        "arena_id": params.arena_id,
        "review_state": DRAFT_PENDING,
        "note": (
            "Nothing has been posted. The operator reviews this in the "
            "AgentBattleground side panel."
        ),
        "next": "Call wait_for_verdict() to block until the operator decides.",
    }, indent=2)


@mcp.tool(
    name="wait_for_verdict",
    annotations={
        "title": "Block until the operator rules on your draft (long-poll)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def wait_for_verdict(params: WaitForVerdictInput) -> str:
    """Block until the operator approves, rejects, or posts your draft.

    The battleground twin of ``wait_for_turn``: the server polls the DB every
    second so you spend no tokens waiting on a human.

    Returns one of:

    - ``{"status": "verdict", "verdict": "approved"|"rejected"|"posted",
      "verdict_note": str|null, "posted_text": str?, "operator_edited": bool?,
      "thread": [...]}`` — the decision, plus the arena's current thread so
      you can see any replies that landed while you waited.
    - ``{"status": "timeout", ...}`` — still pending; call again.
    - ``{"status": "not_found", ...}`` — you have no drafts.

    What each verdict means for you:

    - **rejected** — read ``verdict_note`` as a revision brief and
      ``submit_draft`` again, or stop if the note says to.
    - **posted** — your reply is live on the page. If ``operator_edited`` is
      true, read ``posted_text``: that's the voice the thread will answer.
      Ask the operator to re-capture before drafting a follow-up.
    - **approved** — queued for a human to send; no action needed yet.

    Args:
        draft_id: Which draft to watch. Omit for your newest.
        timeout_seconds: Block duration, 5-300 (default 120).
    """
    deadline = time.monotonic() + params.timeout_seconds
    while True:
        state = _read_verdict(params.draft_id)
        if state["status"] != "pending":
            return json.dumps(state, indent=2)
        if time.monotonic() >= deadline:
            return json.dumps({**state, "status": "timeout"}, indent=2)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _default_db_path() -> str:
    """Resolve DB path with precedence: $AGENT_CHAT_DB > <repo>/db/chat.db.

    The computed default sits one level above this script (src/), so a fresh
    clone Just Works without any flag or env var: `<repo>/db/chat.db`.
    """
    env_db = os.environ.get("AGENT_CHAT_DB")
    if env_db:
        # A RELATIVE value here is always a bug, and a silent one. This server
        # is launched by a CLI that has already `Set-Location`d into its own
        # seat folder, so a relative path resolves against *that* — quietly
        # creating `agents/CLIs/<seat>/db/chat.db`, an empty database whose
        # get_kickoff() reports no conversation. The agent then sits doing
        # nothing, with no error anywhere, which is how conversation #52 burned
        # ten minutes (2026-08-26). Refusing is strictly better than guessing:
        # resolving it here would just make the wrong path absolute, since the
        # cwd that gives it meaning belongs to whoever exported it.
        if not Path(env_db).is_absolute():
            raise SystemExit(
                f"AGENT_CHAT_DB must be an absolute path; got {env_db!r}. "
                f"It is inherited by agents launched from their own seat "
                f"folders, so a relative path silently points each one at a "
                f"different, empty database. Export a resolved path "
                f"(web.db.set_db_path() does this for you), or pass --db-path."
            )
        return env_db
    return str((Path(__file__).resolve().parent.parent / "db" / "chat.db"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="agent_chat MCP server")
    p.add_argument(
        "--agent-id",
        required=True,
        help="Identity for this MCP server instance (e.g., 'claude-code' or 'codex'). "
             "Each agent must register the server with a unique id.",
    )
    p.add_argument(
        "--db-path",
        default=None,
        help="Absolute path to the shared SQLite database file. Both agents must point "
             "to the same path. Defaults to $AGENT_CHAT_DB, or <repo>/db/chat.db "
             "resolved relative to this script.",
    )
    return p.parse_args()


def main() -> None:
    global AGENT_ID, DB_PATH
    args = parse_args()
    AGENT_ID = args.agent_id.strip()
    DB_PATH = args.db_path if args.db_path else _default_db_path()

    if not AGENT_ID:
        print("ERROR: --agent-id cannot be empty", file=sys.stderr)
        sys.exit(2)

    db_init()
    # stdio transport — both Claude Code and Codex CLI launch this as a subprocess.
    mcp.run()


if __name__ == "__main__":
    main()
