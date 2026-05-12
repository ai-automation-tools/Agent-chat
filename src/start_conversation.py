"""
start_conversation.py - Seed a new conversation for the agent_chat MCP server.

Run this from PowerShell or WSL before prompting your agents. It writes a row
into the same SQLite DB the MCP server reads from, so when the agents call
get_my_turn() they discover the new conversation.

The DB path defaults to <repo>/db/chat.db (resolved from this script's
location), so the typical invocation skips --db-path entirely. Override via
the `AGENT_CHAT_DB` env var or an explicit `--db-path <path>` flag (flag
wins).

Examples:

    # Default DB (recommended): <repo>/db/chat.db
    python src/start_conversation.py ^
        --topic "Compare MCP vs A2A for peer agent communication" ^
        --participants claude-code,codex ^
        --first claude-code ^
        --mode turns ^
        --max-turns 10

    # Explicit override
    python src/start_conversation.py --db-path D:/custom/chat.db --topic "..." \
        --participants claude-code,codex --mode continuous --max-turns 10
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from presets import PRESETS, PRESET_NAMES, get_preset


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_TEMPLATE = _REPO_ROOT / "prompts" / "kickoff.md"

# Match every ```text ... ``` fenced block inside a Markdown source.
# Capture group 1 is the body without the fences.
_TEMPLATE_BLOCK_RE = re.compile(r"```text\n(.*?)\n```", re.DOTALL)

# The canonical kickoff template is the first ```text block that contains
# this marker. Required because prompts/kickoff.md now has multiple ```text
# fences (an example snippet near the top, the actual template lower down);
# {{TOPIC}} is the unique distinguishing element of the real template.
_TEMPLATE_MARKER = "{{TOPIC}}"


def _load_template(path: Path) -> str:
    """Load a kickoff template body.

    Two source shapes are supported:
    - A Markdown doc with one or more ```text fenced blocks. The first
      block containing ``{{TOPIC}}`` is returned (so example snippets
      elsewhere in the doc don't shadow the real template).
    - A plain-text file (no fenced block found). The whole file is
      returned verbatim, stripped of leading/trailing whitespace.
    """
    raw = path.read_text(encoding="utf-8")
    for m in _TEMPLATE_BLOCK_RE.finditer(raw):
        body = m.group(1).rstrip()
        if _TEMPLATE_MARKER in body:
            return body
    # No ```text block contained the marker. Fall back to the whole file
    # (operator may have authored a plain-text template).
    return raw.strip()


def render_kickoff(
    template: str,
    topic: str,
    tone: str,
    n_participants: int,
) -> str:
    """Substitute placeholders in the template and rewrite the participant
    declaration for 3+ agent conversations.

    The template's opening line declares the conversation as being "with
    another AI agent" (singular). For N >= 3 participants we rewrite that
    to "with (N-1) other AI agents". Each agent reading the result is
    one of the N, so the phrase reads correctly for everyone.
    """
    body = template.replace("{{TOPIC}}", topic).replace(
        "{{TONE_INSTRUCTION}}", tone
    )
    if n_participants >= 3:
        others = n_participants - 1
        body = body.replace(
            "with another AI agent",
            f"with {others} other AI agents",
        )
    return body


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
    kickoff_template  TEXT
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

# Mirrors _MIGRATIONS in src/agent_chat_mcp.py + src/web_ui.py. start_conversation.py
# only sees DBs that the MCP server or web_ui have already migrated (those run
# db_init() with the additive ALTER TABLE pass), but applying it here too keeps
# this script self-sufficient for fresh-clone seed-then-migrate flows where the
# operator runs start_conversation before any agent connects.
_MIGRATIONS = (
    ("conversations", "preset",           "ALTER TABLE conversations ADD COLUMN preset TEXT"),
    ("conversations", "kickoff_template", "ALTER TABLE conversations ADD COLUMN kickoff_template TEXT"),
)


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


def main() -> int:
    p = argparse.ArgumentParser(description="Start a new agent_chat conversation.")
    p.add_argument("--db-path", default=None,
                   help="Path to the shared SQLite database file. Defaults to "
                        "$AGENT_CHAT_DB, or <repo>/db/chat.db resolved relative "
                        "to this script.")
    p.add_argument("--topic", required=True,
                   help="The topic or task the agents should discuss.")
    p.add_argument("--participants", required=True,
                   help="Comma-separated list of agent ids (e.g., 'claude-code,codex'). "
                        "Order matters in turns mode — turn rotates through this list.")
    p.add_argument("--mode", choices=["turns", "continuous"], default=None,
                   help="'turns' enforces strict alternation, 'continuous' lets either "
                        "agent post anytime. Default: 'turns' (or the preset's default "
                        "when --preset is set).")
    p.add_argument("--max-turns", type=int, default=None,
                   help="Per-agent message cap. Conversation completes when any agent "
                        "hits this number. Default: 10 (or the preset's default when "
                        "--preset is set).")
    p.add_argument("--first", default=None,
                   help="Which agent goes first in turns mode. Defaults to the first "
                        "agent in --participants.")
    p.add_argument("--kickoff", default=None,
                   help="Optional. A system message inserted as the first message in "
                        "the conversation. Use this to give the agents extra context "
                        "or constraints beyond the topic.")
    p.add_argument("--preset", choices=PRESET_NAMES, default=None,
                   help="Apply a named kickoff preset (tone + mode + max_turns defaults). "
                        f"Choices: {', '.join(PRESET_NAMES)}. Triggers rendering of the "
                        "canonical kickoff template (prompts/kickoff.md) which agents "
                        "fetch via the get_kickoff() MCP tool.")
    p.add_argument("--tone", default=None,
                   help="Override the {{TONE_INSTRUCTION}} substitution in the rendered "
                        "kickoff template. Use with or without --preset. Pass a complete "
                        "sentence — see prompts/kickoff.md for examples.")
    p.add_argument("--kickoff-template-file", default=None,
                   help="Path to a custom kickoff template (Markdown with a ```text fenced "
                        "block, or plain text). Defaults to prompts/kickoff.md.")
    args = p.parse_args()
    if not args.db_path:
        args.db_path = _default_db_path()

    participants = [a.strip() for a in args.participants.split(",") if a.strip()]
    if len(participants) < 2:
        print("ERROR: need at least 2 participants", file=sys.stderr)
        return 2
    if len(set(participants)) != len(participants):
        print("ERROR: participant ids must be unique", file=sys.stderr)
        return 2

    # Resolve preset defaults. Precedence: explicit flag > preset default > script default.
    preset_data = get_preset(args.preset) if args.preset else None
    if args.mode is None:
        args.mode = preset_data["mode"] if preset_data else "turns"
    if args.max_turns is None:
        args.max_turns = preset_data["max_turns"] if preset_data else 10

    first = args.first or participants[0]
    if first not in participants:
        print(f"ERROR: --first '{first}' is not in --participants", file=sys.stderr)
        return 2

    if args.max_turns < 1:
        print("ERROR: --max-turns must be >= 1", file=sys.stderr)
        return 2

    # Render the kickoff template if any of --preset / --tone / --kickoff-template-file
    # were supplied. Without any of those, kickoff_template stays NULL on the row and
    # get_kickoff() returns its fallback string — preserves the old paste-the-prompt flow.
    kickoff_template: Optional[str] = None
    if args.preset or args.tone or args.kickoff_template_file:
        tone = args.tone or (preset_data["tone"] if preset_data else None)
        if not tone:
            print(
                "ERROR: --tone is required when --kickoff-template-file is set "
                "without --preset (no tone to inject otherwise).",
                file=sys.stderr,
            )
            return 2
        template_path = Path(args.kickoff_template_file) if args.kickoff_template_file else _DEFAULT_TEMPLATE
        if not template_path.exists():
            print(f"ERROR: template file not found: {template_path}", file=sys.stderr)
            return 2
        template = _load_template(template_path)
        kickoff_template = render_kickoff(
            template, args.topic, tone, n_participants=len(participants)
        )

    os.makedirs(os.path.dirname(os.path.abspath(args.db_path)), exist_ok=True)

    conn = sqlite3.connect(args.db_path, timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    for table, column, ddl in _MIGRATIONS:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(ddl)

    current_turn = first if args.mode == "turns" else None
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO conversations
            (topic, participants, mode, max_turns, current_turn, status,
             end_reason, created_at, updated_at, preset, kickoff_template)
        VALUES (?, ?, ?, ?, ?, 'active', NULL, ?, ?, ?, ?)
        """,
        (args.topic, json.dumps(participants), args.mode, args.max_turns,
         current_turn, ts, ts, args.preset, kickoff_template),
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
    if args.preset:
        print(f"  preset       : {args.preset}")
    if kickoff_template:
        print(f"  kickoff      : rendered ({len(kickoff_template)} chars) — agents fetch via get_kickoff()")
    print()
    if kickoff_template:
        print("Now paste this two-line prompt into each agent's CLI (substitute the agent id):")
        print()
        print('  "You\'re agent <id> on the agent_chat MCP server.')
        print('   Call get_kickoff() and follow the instructions it returns."')
    else:
        print("Next: see docs/Guides/start-new-chat.md §3 (\"Prompt each agent\") for the kickoff prompt to paste into each CLI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
