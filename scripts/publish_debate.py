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

    # Commit + push the debate folder to the library repo (typically re-run
    # with --push AFTER the cover image lands, so one commit carries the
    # whole debate; re-writing the markdown is idempotent)
    .\\.venv\\Scripts\\python.exe scripts\\publish_debate.py --cid 42 --category "Technology" --push

    # Overwrite a folder that belongs to a DIFFERENT conversation (slug
    # collision) or publish a non-complete conversation
    .\\.venv\\Scripts\\python.exe scripts\\publish_debate.py --cid 42 --category "Technology" --force

Re-publishing the SAME conversation over its own folder never needs ``--force``
(the folder's topic.md records the conversation id; a matching id means the
overwrite is an idempotent refresh and cover-image.png is never touched).

Git safety (--push): stages ONLY the debate folder (unrelated local changes in
the library repo are never swept in or blocked on), then ``git pull --rebase
--autostash`` before pushing so a remote that moved (the automation fleet
pushes to the same branch all day) is replayed cleanly; one retry on a push
race. If a rebase ever hits a real conflict it aborts, keeps the commit local,
and tells the operator — it never force-pushes.

Library root resolution: ``--library-root``  >  ``$AGENT_DEBATES_ROOT``  >
``<repo>/../AI-Automation-Library/My-Library/Content/Agent-Debates``.
DB path resolution (same precedence as the MCP server):
``--db-path``  >  ``$AGENT_CHAT_DB``  >  ``<repo>/db/chat.db``.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
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


def _existing_folder_cid(target: Path) -> int | None:
    """The conversation id recorded in an existing debate folder's topic.md.

    Lets a re-publish of the SAME conversation proceed without --force while
    still protecting a different conversation's folder (slug collision).
    """
    topic = target / "topic.md"
    if not topic.exists():
        return None
    m = re.search(r"^\|\s*Conversation\s*\|\s*#(\d+)\s*\|", topic.read_text(encoding="utf-8"), re.M)
    return int(m.group(1)) if m else None


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )


def commit_and_push(library_root: Path, target: Path, cid: int) -> None:
    """Stage ONLY the debate folder, commit, rebase onto the remote, push.

    Designed for a repo other processes also push to (the automation fleet):
    - unrelated local changes are never staged (no `add -A`) and never block
      the rebase (`--autostash`);
    - a moved remote is handled by `pull --rebase` + one push retry;
    - a real rebase conflict aborts cleanly, keeps the commit local, and
      surfaces instructions — never a force-push.
    """
    probe = _git(library_root, "rev-parse", "--show-toplevel")
    if probe.returncode != 0:
        raise SystemExit(f"error: {library_root} is not inside a git repo — can't --push")
    repo = Path(probe.stdout.strip())

    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not branch or branch == "HEAD":
        raise SystemExit("error: library repo is on a detached HEAD — check it out on a branch first")

    rel = target.relative_to(repo).as_posix()
    _git(repo, "add", "--", rel)
    staged = _git(repo, "diff", "--cached", "--quiet")
    if staged.returncode == 0:
        print(f"git: nothing new to commit under {rel} (already committed?)")
        return

    slug = target.name
    category = target.parent.name
    msg = (
        f"feat(agent-debates): publish {slug} (conversation #{cid})\n\n"
        f"Bundle + cover for the {category} debate, published from Agent-Chat\n"
        f"via scripts/publish_debate.py --push."
    )
    commit = _git(repo, "commit", "-m", msg)
    if commit.returncode != 0:
        raise SystemExit(f"error: git commit failed:\n{commit.stdout}{commit.stderr}")
    print(f"git: committed {rel} on {branch}")

    for attempt in (1, 2):
        pull = _git(repo, "pull", "--rebase", "--autostash", "origin", branch)
        if pull.returncode != 0:
            _git(repo, "rebase", "--abort")
            raise SystemExit(
                "error: rebase onto origin/" + branch + " hit a conflict — aborted the rebase.\n"
                "  Your publish commit is safe on the local branch; resolve manually:\n"
                f"  git -C {repo} pull --rebase origin {branch}   # fix conflicts, then push\n"
                f"  git output: {pull.stderr.strip() or pull.stdout.strip()}"
            )
        push = _git(repo, "push", "origin", branch)
        if push.returncode == 0:
            print(f"git: pushed to origin/{branch}")
            return
        if attempt == 1:
            print("git: push rejected (remote moved) — rebasing and retrying once…")
    raise SystemExit(
        f"error: push to origin/{branch} still rejected after a retry.\n"
        f"  The commit is safe locally; push manually when the remote settles.\n"
        f"  git output: {push.stderr.strip()}"
    )


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
        existing_cid = _existing_folder_cid(target)
        if existing_cid == cid:
            print(f"note: re-publishing conversation #{cid} over its own folder (idempotent refresh)")
        else:
            raise SystemExit(
                f"error: {target} already exists"
                + (f" and belongs to conversation #{existing_cid}" if existing_cid else "")
                + ".\n  Pass --force to overwrite its markdown files "
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
        help="Overwrite a different conversation's folder / publish a non-complete conversation",
    )
    ap.add_argument(
        "--push",
        action="store_true",
        help="After writing, stage the debate folder, commit, and push to the "
        "library repo (rebase --autostash + one retry; aborts safely on conflict)",
    )
    args = ap.parse_args()

    db_path = args.db_path or default_db_path()
    library_root = args.library_root or default_library_root()

    target = publish(args.cid, args.category, db_path, library_root, force=args.force)
    print(f"\npublished conversation #{args.cid} -> {target}")
    if args.push:
        commit_and_push(library_root, target, args.cid)


if __name__ == "__main__":
    main()
