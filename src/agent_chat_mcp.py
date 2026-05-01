"""
agent_chat_mcp - Local MCP server for inter-agent conversations.

A SQLite-backed message bus that lets two or more CLI agents (Claude Code,
Codex CLI, etc.) hold structured conversations with each other. Each agent
connects to this same MCP server with a different --agent-id and shares the
same --db-path, so they read and write the same conversation state.

Usage:
    python agent_chat_mcp.py --agent-id claude-code --db-path D:/AI_Agents/Specialized_Agents/agent_chat/chat.db
    python agent_chat_mcp.py --agent-id codex      --db-path D:/AI_Agents/Specialized_Agents/agent_chat/chat.db

Conversations are created out-of-band by start_conversation.py and then
each agent calls get_my_turn() to participate.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Module-level config (populated by main() before mcp.run())
# ---------------------------------------------------------------------------

AGENT_ID: str = ""
DB_PATH: str = ""

# Stop signals an agent can send to end early.
SIGNAL_DONE = "done"
SIGNAL_BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    participants    TEXT NOT NULL,           -- JSON array of agent ids
    mode            TEXT NOT NULL,           -- 'turns' | 'continuous'
    max_turns       INTEGER NOT NULL,        -- per-agent cap
    current_turn    TEXT,                    -- agent id whose turn it is (turns mode)
    status          TEXT NOT NULL,           -- 'active' | 'complete'
    end_reason      TEXT,                    -- why it ended, if complete
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  INTEGER NOT NULL REFERENCES conversations(id),
    sender           TEXT NOT NULL,          -- agent id, or 'system' for kickoff
    content          TEXT NOT NULL,
    signal           TEXT,                   -- optional: 'done', 'blocked'
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
"""


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
    """Create schema if it doesn't exist."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with db_connect() as conn:
        conn.executescript(SCHEMA)


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
            "Optional stop signal. Use 'done' if the conversation's task is genuinely "
            "complete and should end. Use 'blocked' if you cannot proceed and need the "
            "human to intervene. Omit for normal messages."
        ),
    )


class GetStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    whenever you want to know if there's anything for you to do.

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
    with db_connect() as conn:
        conv = get_latest_conversation(conn, AGENT_ID)
        if conv is None:
            return json.dumps({
                "status": "no_conversation",
                "message": (
                    f"No active conversation includes agent '{AGENT_ID}'. "
                    "Wait for a conversation to be started, or ask the human "
                    "to run start_conversation.py."
                ),
            }, indent=2)

        # Re-evaluate stop conditions on every read so completion is sticky.
        end_reason = maybe_complete(conn, conv)
        # Refresh row after possible update
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv["id"],)
        ).fetchone()

        history = fetch_messages(conn, conv["id"])
        participants = json.loads(conv["participants"])
        my_count = count_messages_by_sender(conn, conv["id"], AGENT_ID)
        turns_remaining = max(0, conv["max_turns"] - my_count)

        base = {
            "conversation_id": conv["id"],
            "topic": conv["topic"],
            "mode": conv["mode"],
            "participants": participants,
            "history": history,
        }

        if conv["status"] == "complete":
            return json.dumps({
                "status": "complete",
                "end_reason": conv["end_reason"] or end_reason,
                **base,
            }, indent=2)

        if conv["mode"] == "turns" and conv["current_turn"] != AGENT_ID:
            return json.dumps({
                "status": "wait",
                "current_turn": conv["current_turn"],
                **base,
            }, indent=2)

        # Either continuous mode, or turns mode and it's our turn.
        return json.dumps({
            "status": "your_turn",
            "turns_remaining": turns_remaining,
            **base,
        }, indent=2)


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
            proceed without human input. Omit for normal messages.

    Returns a JSON object describing the resulting state, with the same shape
    as get_my_turn() so you can chain calls. After sending in turns mode,
    you will typically see status='wait' (the other agent is up next) or
    status='complete' (you hit the cap or signaled done).
    """
    if params.signal is not None and params.signal not in (SIGNAL_DONE, SIGNAL_BLOCKED):
        return json.dumps({
            "status": "error",
            "message": f"Invalid signal '{params.signal}'. Use 'done', 'blocked', or omit.",
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


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

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
        required=True,
        help="Absolute path to the shared SQLite database file. Both agents must point "
             "to the same path.",
    )
    return p.parse_args()


def main() -> None:
    global AGENT_ID, DB_PATH
    args = parse_args()
    AGENT_ID = args.agent_id.strip()
    DB_PATH = args.db_path

    if not AGENT_ID:
        print("ERROR: --agent-id cannot be empty", file=sys.stderr)
        sys.exit(2)

    db_init()
    # stdio transport — both Claude Code and Codex CLI launch this as a subprocess.
    mcp.run()


if __name__ == "__main__":
    main()
