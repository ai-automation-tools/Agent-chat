"""
inspect_conversations.py - View agent_chat conversations from the CLI.

Useful for debugging and watching conversations unfold in a third terminal
while your two agents talk in the other two.

The DB path defaults to <repo>/db/chat.db (resolved from this script's
location), so the typical invocation skips --db-path entirely. Override via
the `AGENT_CHAT_DB` env var or an explicit `--db-path <path>` flag (flag wins).

Examples:

    # List all conversations
    python src/inspect_conversations.py list

    # Show full transcript of a conversation
    python src/inspect_conversations.py show 1

    # Tail latest messages, refreshing every 2s (Ctrl-C to stop)
    python src/inspect_conversations.py tail 1

    # Force a conversation to end (e.g., agents are looping)
    python src/inspect_conversations.py stop 1

    # Report conversations that have gone quiet (the scheduler runs this)
    python src/inspect_conversations.py watch

    # Re-run delivery for a conversation (see docs/App/delivery.md)
    python src/inspect_conversations.py deliver 1
    python src/inspect_conversations.py deliver --show
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator import delivery, watchdog  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_path() -> str:
    """Resolve DB path with precedence: $AGENT_CHAT_DB > <repo>/db/chat.db.

    The computed default sits one level above this script (src/), so a fresh
    clone Just Works without any flag or env var: `<repo>/db/chat.db`.
    """
    env_db = os.environ.get("AGENT_CHAT_DB")
    if env_db:
        return env_db
    return str((Path(__file__).resolve().parent.parent / "db" / "chat.db"))


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def cmd_list(conn: sqlite3.Connection) -> int:
    # SELECT * rather than naming conv_type: this script declares no schema and
    # never runs db_init(), so it can be pointed at a DB that predates a column.
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY id DESC"
    ).fetchall()
    if not rows:
        print("(no conversations)")
        return 0
    for r in rows:
        msgs = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (r["id"],)
        ).fetchone()["n"]
        ctype = dict(r).get("conv_type") or "debate"
        line = (
            f"#{r['id']:<4} [{r['status']:<8}] {ctype:<8} "
            f"{r['mode']:<10} "
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


def _completion_line(conv: sqlite3.Row) -> str | None:
    """Banner to print when a tail loop should stop, or ``None`` to keep polling.

    The guard against the premature-"(conversation complete)" bug lives here: a
    quiet poll (no new messages) is **not** completion — only a conversation row
    whose ``status`` is literally ``'complete'`` ends the tail. When it does
    complete, surface ``end_reason`` so the operator can tell *why* it ended
    (max_turns vs ``signal='done'`` vs stopped by operator) rather than guessing
    whether it stopped early.

    ``conv`` must be a non-``None`` row (callers handle the deleted-conversation
    case separately, since "row missing" is distinct from "still active").
    """
    if conv["status"] != "complete":
        return None
    reason = conv["end_reason"]
    return "(conversation complete" + (f" — {reason}" if reason else "") + ")"


def cmd_tail(conn: sqlite3.Connection, conv_id: int, interval: float) -> int:
    last_id = 0
    try:
        while True:
            conv = conn.execute(
                "SELECT status, end_reason FROM conversations WHERE id = ?",
                (conv_id,),
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

            line = _completion_line(conv)
            if line is not None:
                print("\n" + line)
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n(stopped)")
        return 0


def cmd_stop(conn: sqlite3.Connection, conv_id: int, db_path: str) -> int:
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
    # No-op unless config/delivery.json turns a sink on. The DB path is
    # whatever this CLI was pointed at, so a delivery never reads a different
    # database than the row it just closed.
    for line in delivery.deliver(conv_id, "complete", db_path):
        print(f"  delivery {line}")
    return 0


def cmd_deliver(conv_id: int | None, event: str, db_path: str,
                init: bool = False, show: bool = False) -> int:
    """Re-run delivery for one conversation, or manage its config.

    Delivery normally fires on its own when a conversation ends (see
    docs/App/delivery.md). This is the manual handle: deliver a conversation
    that finished before delivery was switched on, re-deliver after editing a
    sink, or check what the config resolves to. Re-delivering is idempotent —
    the folder sink overwrites in place.

    The CLI lives here rather than in orchestrator/delivery.py because that
    module is a package member: `python -m orchestrator.delivery` can't find
    itself from the repo root, and this script already bootstraps sys.path and
    resolves --db-path with the right precedence.
    """
    cfg_path = delivery.config_path()

    if init:
        if cfg_path.exists():
            print(f"exists, not overwriting: {cfg_path}")
            return 1
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            json.dumps(delivery.STARTER_CONFIG, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {cfg_path}")
        print('Set "enabled": true to turn delivery on.')
        return 0

    if show or conv_id is None:
        cfg = delivery.load_config()
        state = "found" if cfg else "missing/empty - delivery is OFF"
        print(f"config: {cfg_path} ({state})")
        if cfg:
            print(json.dumps(cfg, indent=2))
        return 0

    # ignore_scope: typing this command IS the opt-in, so a sink scoped
    # 'opt-in' must not refuse a conversation whose launch box went unticked.
    lines = delivery.deliver(conv_id, event, db_path, ignore_scope=True)
    if not lines:
        print("no sinks configured for this event (nothing delivered)")
        return 0
    for line in lines:
        print(line)
    return 1 if any("ERROR" in ln for ln in lines) else 0


def cmd_watch(db_path: str, notify: bool = True) -> int:
    """Report active conversations that have gone quiet, and notify once each.

    The `quiet for N` badge on the conversation page only helps while somebody
    is looking at it. This is the half that works when nobody is: run it from a
    scheduler (the health-check task already does, every 10 minutes) and a
    stalled run reaches whatever delivery sinks are configured for the
    `stalled` event.

    Exit code is the number of stalled conversations, so a scheduler can key
    off it. Reports even when no sink is configured — the printout is useful on
    its own.
    """
    stalls = watchdog.check(db_path, notify=notify)
    if not stalls:
        print("(no stalled conversations)")
        return 0
    for s in stalls:
        mark = "notified" if s.get("notified") else "already reported"
        print(f"  {watchdog.describe(s)}  [{mark}]")
    return len(stalls)


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect agent_chat conversations.")
    p.add_argument("--db-path", default=None,
                   help="Path to the shared SQLite database file. Defaults to "
                        "$AGENT_CHAT_DB, or <repo>/db/chat.db resolved relative "
                        "to this script.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    sp_show = sub.add_parser("show")
    sp_show.add_argument("conversation_id", type=int)

    sp_tail = sub.add_parser("tail")
    sp_tail.add_argument("conversation_id", type=int)
    sp_tail.add_argument("--interval", type=float, default=2.0)

    sp_stop = sub.add_parser("stop")
    sp_stop.add_argument("conversation_id", type=int)

    sp_watch = sub.add_parser(
        "watch", help="Report active conversations that have gone quiet.")
    sp_watch.add_argument("--quiet", action="store_true",
                          help="Report only; do not fire delivery sinks.")

    sp_del = sub.add_parser(
        "deliver", help="Re-deliver a conversation to the configured sinks.")
    sp_del.add_argument("conversation_id", type=int, nargs="?",
                        help="Omit to print the resolved delivery config.")
    sp_del.add_argument("--event", default="complete", choices=list(delivery.EVENTS),
                        help="Which trigger to simulate (default: complete).")
    sp_del.add_argument("--init", action="store_true",
                        help="Write a disabled starter config/delivery.json and exit.")
    sp_del.add_argument("--show", action="store_true",
                        help="Print the resolved config and exit.")

    args = p.parse_args()
    if not args.db_path:
        args.db_path = _default_db_path()

    # `deliver --init` / `deliver --show` are config-only: they must work on a
    # clone that has never seeded a conversation, so they run before the
    # database check below.
    if args.cmd == "deliver" and (args.init or args.show or args.conversation_id is None):
        return cmd_deliver(None, args.event, args.db_path, args.init, args.show)

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
        return cmd_stop(conn, args.conversation_id, args.db_path)
    if args.cmd == "deliver":
        return cmd_deliver(args.conversation_id, args.event, args.db_path)
    if args.cmd == "watch":
        return cmd_watch(args.db_path, notify=not args.quiet)
    return 2


if __name__ == "__main__":
    sys.exit(main())
