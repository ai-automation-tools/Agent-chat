"""start_conversation.py - Seed a new conversation for the agent_chat MCP server.

Run this from PowerShell or WSL before prompting your agents. It writes a row
into the same SQLite DB the MCP server reads from, so when the agents call
get_my_turn() they discover the new conversation.

The DB path defaults to <repo>/db/chat.db (resolved from this script's
location), so the typical invocation skips --db-path entirely. Override via
the `AGENT_CHAT_DB` env var or an explicit `--db-path <path>` flag (flag
wins).

This is a thin argparse wrapper around ``orchestrator.seeding.seed_conversation``;
the Web UI's POST /api/orchestrate handler calls the same function so the
seeding logic has a single source of truth.

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
import sys
from pathlib import Path

# When invoked as a script (``python src/start_conversation.py``), sys.path
# does not yet include this file's parent, so the sibling ``orchestrator``
# package can't be imported. Add it before the first import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator import seeding  # noqa: E402
from presets import PRESET_NAMES, get_preset  # noqa: E402


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
    p.add_argument("--participant-personas-file", default=None,
                   help="Path to a JSON file mapping agent_id -> {persona_slug, persona_name, "
                        "persona_body}. Stored verbatim on the conversation so a debate's cast "
                        "(tool + personality) is self-describing in the DB and exports. "
                        "Written by scripts/debate.ps1; optional.")
    args = p.parse_args()

    db_path = args.db_path or seeding.default_db_path()

    participant_personas = None
    if args.participant_personas_file:
        try:
            with open(args.participant_personas_file, encoding="utf-8") as f:
                participant_personas = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: could not read --participant-personas-file: {e}", file=sys.stderr)
            return 2

    participants = [a.strip() for a in args.participants.split(",") if a.strip()]

    # Resolve preset defaults. Precedence: explicit flag > preset default > script default.
    preset_data = get_preset(args.preset) if args.preset else None
    mode = args.mode if args.mode is not None else (preset_data["mode"] if preset_data else "turns")
    max_turns = args.max_turns if args.max_turns is not None else (preset_data["max_turns"] if preset_data else 10)
    tone = args.tone or (preset_data["tone"] if preset_data else None)

    try:
        result = seeding.seed_conversation(
            db_path=db_path,
            topic=args.topic,
            participants=participants,
            mode=mode,
            max_turns=max_turns,
            first=args.first,
            preset=args.preset,
            tone=tone,
            kickoff_template_file=args.kickoff_template_file,
            initial_system_message=args.kickoff,
            participant_personas=participant_personas,
        )
    except seeding.SeedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"Started conversation #{result.conversation_id}")
    print(f"  topic        : {result.topic}")
    print(f"  participants : {result.participants}")
    print(f"  mode         : {result.mode}")
    print(f"  max_turns    : {result.max_turns} (per agent)")
    if result.mode == "turns":
        print(f"  first turn   : {result.first}")
    if result.preset:
        print(f"  preset       : {result.preset}")
    if result.kickoff_rendered:
        print(f"  kickoff      : rendered ({len(result.kickoff_rendered)} chars) — agents fetch via get_kickoff()")
    print()
    if result.kickoff_rendered:
        print("Now paste this two-line prompt into each agent's CLI (substitute the agent id):")
        print()
        print('  "You\'re agent <id> on the agent_chat MCP server.')
        print('   Call get_kickoff() and follow the instructions it returns."')
    else:
        print("Next: see docs/Guides/start-new-chat.md §3 (\"Prompt each agent\") for the kickoff prompt to paste into each CLI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
