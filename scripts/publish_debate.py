"""
publish_debate.py — publish a finished conversation to the AI-Automation-Library.

Writes the export bundle (``topic.md`` + ``personas/*.md`` + ``transcript.md``)
for one conversation straight from ``db/chat.db`` into the library archive::

    <library>/My-Library/Content/Agent-Debates/<Category>/<topic-slug>/

No ZIP, no browser download — the renderers are the same ones behind the Web
UI's ``/export.md`` / ``/export.zip`` endpoints (``src/orchestrator/export.py``),
so the published files and the browser export can never drift apart.

The cover image is NOT generated here — that's the creative half of the flow,
handled by the ``publish-debate`` Agent Skill (fills the scene/metaphor fields
of the cover master-prompt from the transcript, generates ``cover-image.png``
into the debate folder). This script prints a reminder when the cover is
missing.

Local-only by design: the library repo lives on this machine (sibling of this
repo under ``Live_Apps/``), not on the Fly mirror.

Usage::

    .\\.venv\\Scripts\\python.exe scripts\\publish_debate.py --cid 42 --category "Technology"

    # Custom locations
    .\\.venv\\Scripts\\python.exe scripts\\publish_debate.py --cid 42 --category "Space-&-Science" `
        --db-path db\\chat.db --library-root D:\\path\\to\\Agent-Debates

    # Re-publish over an existing folder (e.g. after a transcript fix)
    .\\.venv\\Scripts\\python.exe scripts\\publish_debate.py --cid 42 --category "Technology" --force

Library root resolution: ``--library-root``  >  ``$AGENT_DEBATES_ROOT``  >
``<repo>/../AI-Automation-Library/My-Library/Content/Agent-Debates``.
DB path resolution (same precedence as the MCP server):
``--db-path``  >  ``$AGENT_CHAT_DB``  >  ``<repo>/db/chat.db``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from orchestrator.export import bundle_files, load_conversation, topic_slug  # noqa: E402


def default_library_root() -> Path:
    """The Agent-Debates tree in the sibling AI-Automation-Library repo."""
    env = os.environ.get("AGENT_DEBATES_ROOT")
    if env:
        return Path(env)
    return (
        REPO_ROOT.parent
        / "AI-Automation-Library"
        / "My-Library"
        / "Content"
        / "Agent-Debates"
    )


def default_db_path() -> Path:
    env = os.environ.get("AGENT_CHAT_DB")
    if env:
        return Path(env)
    return REPO_ROOT / "db" / "chat.db"


def publish(
    cid: int,
    category: str,
    db_path: Path,
    library_root: Path,
    force: bool = False,
) -> Path:
    """Write the export bundle for ``cid`` into the library. Returns the folder.

    Raises SystemExit with a readable message on any refusal — this is a CLI
    helper, not a library function.
    """
    if not db_path.exists():
        raise SystemExit(f"error: DB not found: {db_path}")
    if not library_root.exists():
        raise SystemExit(
            f"error: library root not found: {library_root}\n"
            "  (is the AI-Automation-Library repo cloned as a sibling of this repo? "
            "override with --library-root or $AGENT_DEBATES_ROOT)"
        )

    category = category.strip().strip("/\\")
    if not category:
        raise SystemExit("error: --category must not be empty")

    data = load_conversation(str(db_path), cid)
    if data is None:
        raise SystemExit(f"error: conversation #{cid} not found in {db_path}")

    c = data["conversation"]
    if c.get("status") != "complete" and not force:
        raise SystemExit(
            f"error: conversation #{cid} is status={c.get('status')!r}, not complete.\n"
            "  Publish is meant for finished debates — pass --force to publish anyway."
        )

    slug = topic_slug(str(c.get("topic") or "")) or f"conversation-{cid}"
    category_dir = library_root / category
    target = category_dir / slug

    if target.exists() and not force:
        raise SystemExit(
            f"error: {target} already exists.\n"
            "  Pass --force to overwrite its markdown files "
            "(cover-image.png is never touched)."
        )

    if not category_dir.exists():
        print(f"note: creating new category bucket: {category_dir}")
    (target / "personas").mkdir(parents=True, exist_ok=True)

    for rel, content in bundle_files(data):
        path = target / Path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"  wrote {path.relative_to(library_root)}")

    if not (target / "cover-image.png").exists():
        print(
            "\nnext: generate the cover — this folder has no cover-image.png yet.\n"
            "  The publish-debate skill (or Prompts/debate-cover-photos.md in the "
            "library) covers the how."
        )
    return target


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Publish a conversation's export bundle into the "
        "AI-Automation-Library Agent-Debates archive."
    )
    ap.add_argument("--cid", type=int, required=True, help="Conversation id to publish")
    ap.add_argument(
        "--category",
        required=True,
        help='Topic bucket folder, e.g. "Technology", "Space-&-Science", '
        '"Society-&-Culture" (created if new)',
    )
    ap.add_argument("--db-path", type=Path, default=None, help="Path to chat.db")
    ap.add_argument(
        "--library-root",
        type=Path,
        default=None,
        help="Agent-Debates root in the library repo (default: sibling repo)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing debate folder / publish a non-complete conversation",
    )
    args = ap.parse_args()

    db_path = args.db_path or default_db_path()
    library_root = args.library_root or default_library_root()

    target = publish(args.cid, args.category, db_path, library_root, force=args.force)
    print(f"\npublished conversation #{args.cid} -> {target}")


if __name__ == "__main__":
    main()
