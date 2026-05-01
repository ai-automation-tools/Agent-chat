"""
inspect_conversations.py - View agent_chat conversations from the CLI.

Useful for debugging and watching conversations unfold in a third terminal
while your two agents talk in the other two.

Examples:

    # List all conversations
    python inspect_conversations.py --db-path D:/AI_Agents/.../chat.db list

    # Show full transcript of a conversation
    python inspect_conversations.py --db-path ... show 1

    # Tail latest messages, refreshing every 2s (Ctrl-C to stop)
    python inspect_conversations.py --db-path ... tail 1

    # Force a conversation to end (e.g., agents are looping)
    python inspect_conversations.py --db-path ... stop 1
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def cmd_list(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT id, topic, mode, status, current_turn, end_reason, "
        "created_at, updated_at FROM conversations ORDER BY id DESC"
    ).fetchall()
    if not rows:
        print("(no conversations)")
        return 0
    for r in rows:
        msgs = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (r["id"],)
        ).fetchone()["n"]
        line = (
            f"#{r['id']:<4} [{r['status']:<8}] {r['mode']:<10} "
            f"msgs={msgs:<3} turn={r['current_turn'] or '-':<14} "
            f"topic={r['topic'][:60]}"
        )
        print(line)
        if r["end_reason"]:
            print(f"        end_reason: {r['end_reason']}")
    return 0


def render_messages(conn: sqlite3.Connection, conv_id: int) -> None:
    conv = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    if conv is None:
        print(f"(no conversation #{conv_id})")
        return

    print("=" * 72)
    print(f"Conversation #{conv['id']} — {conv['status']}")
    print(f"  topic       : {conv['topic']}")
    print(f"  participants: {json.loads(conv['participants'])}")
    print(f"  mode        : {conv['mode']}  max_turns={conv['max_turns']}")
    print(f"  current_turn: {conv['current_turn'] or '-'}")
    if conv["end_reason"]:
        print(f"  end_reason  : {conv['end_reason']}")
    print("=" * 72)

    msgs = conn.execute(
        "SELECT id, sender, content, signal, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()

    if not msgs:
        print("(no messages yet)")
        return

    for m in msgs:
        sig = f" [signal={m['signal']}]" if m["signal"] else ""
        print()
        print(f"--- #{m['id']} {m['sender']} @ {m['created_at']}{sig} ---")
        print(m["content"])


def cmd_show(conn: sqlite3.Connection, conv_id: int) -> int:
    render_messages(conn, conv_id)
    return 0


def cmd_tail(conn: sqlite3.Connection, conv_id: int, interval: float) -> int:
    last_id = 0
    try:
        while True:
            conv = conn.execute(
                "SELECT status FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if conv is None:
                print(f"(no conversation #{conv_id})")
                return 1

            new = conn.execute(
                "SELECT id, sender, content, signal, created_at FROM messages "
                "WHERE conversation_id = ? AND id > ? ORDER BY id ASC",
                (conv_id, last_id),
            ).fetchall()
            for m in new:
                sig = f" [signal={m['signal']}]" if m["signal"] else ""
                print(f"\n--- #{m['id']} {m['sender']} @ {m['created_at']}{sig} ---")
                print(m["content"])
                last_id = m["id"]

            if conv["status"] == "complete":
                print("\n(conversation complete)")
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n(stopped)")
        return 0


def cmd_stop(conn: sqlite3.Connection, conv_id: int) -> int:
    conv = conn.execute(
        "SELECT status FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    if conv is None:
        print(f"(no conversation #{conv_id})")
        return 1
    if conv["status"] == "complete":
        print(f"(conversation #{conv_id} already complete)")
        return 0
    conn.execute(
        "UPDATE conversations SET status='complete', end_reason='stopped by operator', "
        "current_turn=NULL, updated_at=? WHERE id=?",
        (now_iso(), conv_id),
    )
    print(f"Stopped conversation #{conv_id}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect agent_chat conversations.")
    p.add_argument("--db-path", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    sp_show = sub.add_parser("show")
    sp_show.add_argument("conversation_id", type=int)

    sp_tail = sub.add_parser("tail")
    sp_tail.add_argument("conversation_id", type=int)
    sp_tail.add_argument("--interval", type=float, default=2.0)

    sp_stop = sub.add_parser("stop")
    sp_stop.add_argument("conversation_id", type=int)

    args = p.parse_args()

    if not os.path.exists(args.db_path):
        print(f"ERROR: db not found at {args.db_path}", file=sys.stderr)
        return 1

    conn = connect(args.db_path)

    if args.cmd == "list":
        return cmd_list(conn)
    if args.cmd == "show":
        return cmd_show(conn, args.conversation_id)
    if args.cmd == "tail":
        return cmd_tail(conn, args.conversation_id, args.interval)
    if args.cmd == "stop":
        return cmd_stop(conn, args.conversation_id)
    return 2


if __name__ == "__main__":
    sys.exit(main())
