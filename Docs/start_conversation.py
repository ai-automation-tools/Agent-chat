"""
start_conversation.py - Seed a new conversation for the agent_chat MCP server.

Run this from PowerShell or WSL before prompting your agents. It writes a row
into the same SQLite DB the MCP server reads from, so when the agents call
get_my_turn() they discover the new conversation.

Examples:

    # Strict turn-taking, claude-code goes first, 10 messages each, max
    python start_conversation.py ^
        --db-path D:/AI_Agents/Specialized_Agents/agent_chat/chat.db ^
        --topic "Compare MCP vs A2A for peer agent communication" ^
        --participants claude-code,codex ^
        --first claude-code ^
        --mode turns ^
        --max-turns 10

    # Continuous mode, either agent can post anytime, capped at 10 messages each
    python start_conversation.py --db-path ... --topic "..." \
        --participants claude-code,codex --mode continuous --max-turns 10
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT NOT NULL,
    participants    TEXT NOT NULL,
    mode            TEXT NOT NULL,
    max_turns       INTEGER NOT NULL,
    current_turn    TEXT,
    status          TEXT NOT NULL,
    end_reason      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
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
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    p = argparse.ArgumentParser(description="Start a new agent_chat conversation.")
    p.add_argument("--db-path", required=True,
                   help="Path to the shared SQLite database file.")
    p.add_argument("--topic", required=True,
                   help="The topic or task the agents should discuss.")
    p.add_argument("--participants", required=True,
                   help="Comma-separated list of agent ids (e.g., 'claude-code,codex'). "
                        "Order matters in turns mode — turn rotates through this list.")
    p.add_argument("--mode", choices=["turns", "continuous"], default="turns",
                   help="'turns' enforces strict alternation, 'continuous' lets either "
                        "agent post anytime (default: turns).")
    p.add_argument("--max-turns", type=int, default=10,
                   help="Per-agent message cap. Conversation completes when any agent "
                        "hits this number (default: 10).")
    p.add_argument("--first", default=None,
                   help="Which agent goes first in turns mode. Defaults to the first "
                        "agent in --participants.")
    p.add_argument("--kickoff", default=None,
                   help="Optional. A system message inserted as the first message in "
                        "the conversation. Use this to give the agents extra context "
                        "or constraints beyond the topic.")
    args = p.parse_args()

    participants = [a.strip() for a in args.participants.split(",") if a.strip()]
    if len(participants) < 2:
        print("ERROR: need at least 2 participants", file=sys.stderr)
        return 2
    if len(set(participants)) != len(participants):
        print("ERROR: participant ids must be unique", file=sys.stderr)
        return 2

    first = args.first or participants[0]
    if first not in participants:
        print(f"ERROR: --first '{first}' is not in --participants", file=sys.stderr)
        return 2

    if args.max_turns < 1:
        print("ERROR: --max-turns must be >= 1", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(args.db_path)), exist_ok=True)

    conn = sqlite3.connect(args.db_path, timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)

    current_turn = first if args.mode == "turns" else None
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO conversations
            (topic, participants, mode, max_turns, current_turn, status,
             end_reason, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', NULL, ?, ?)
        """,
        (args.topic, json.dumps(participants), args.mode, args.max_turns,
         current_turn, ts, ts),
    )
    conv_id = cur.lastrowid

    if args.kickoff:
        conn.execute(
            "INSERT INTO messages (conversation_id, sender, content, signal, created_at) "
            "VALUES (?, 'system', ?, NULL, ?)",
            (conv_id, args.kickoff, ts),
        )

    print(f"Started conversation #{conv_id}")
    print(f"  topic        : {args.topic}")
    print(f"  participants : {participants}")
    print(f"  mode         : {args.mode}")
    print(f"  max_turns    : {args.max_turns} (per agent)")
    if args.mode == "turns":
        print(f"  first turn   : {first}")
    print()
    print("Now prompt each agent in their CLI with something like:")
    print(f'  "You are connected to the agent_chat MCP server as agent ')
    print(f'   \\\"<your-id>\\\". Call get_my_turn() to begin participating ')
    print(f'   in conversation about: {args.topic}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
