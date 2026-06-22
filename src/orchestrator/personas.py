"""Persona registry — read the debate personality cards under
``agents/Debate-Agents/`` into a typed, queryable list.

This is the single source of truth for "what personalities exist and what is
each one's prompt body". It is intentionally dependency-light (stdlib only —
no PyYAML) so the MCP server can import it without growing the pinned dep set.

Card layout (see ``agents/Debate-Agents/Unique-Personas/*.md`` and
``Debate-Hosts/*.md``)::

    ---
    category: System_Prompts
    subcategory: Podcast_Personalities
    tags:
    - crypto
    - bro
    title: "🤖 Crypto Chad"
    ---

    # Crypto Chad

    ## Purpose
    Act as a hyper-pumped crypto bro ...

    ## Instructions
    You are Crypto Chad ...

Not every card has the same ``##`` sections (the longer hand-authored cards
omit ``## Purpose`` / ``## Instructions``), so the registry never relies on
section structure: the whole post-frontmatter body *is* the persona prompt.
A one-line ``summary`` is best-effort — the ``## Purpose`` paragraph if present,
else the first prose paragraph of the body.

Consumers:
- ``agent_chat_mcp.py`` — ``list_personas`` / ``get_persona`` MCP tools so an
  agent can browse the roster and adopt a card itself.
- ``scripts/debate.ps1`` — calls the JSON CLI at the bottom of this module
  (``list`` / ``get``) to cast its debaters, instead of re-scanning the folder.
- (future) the ``/orchestrate`` Web UI picker, on the same registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# agents/Debate-Agents/ lives at the repo root; this file is
# <repo>/src/orchestrator/personas.py → parents[2] is <repo>.
_PERSONAS_ROOT = Path(__file__).resolve().parents[2] / "agents" / "Debate-Agents"

# Persona group folders live under agents/Debate-Agents/. "Unique-Personas" is
# the debater roster; "Debate-Hosts" holds moderator/host personalities. These
# two always sort first when present and form the canonical roster returned when
# no group is requested. ANY OTHER subdirectory is also a valid group — curated
# topic subsets (e.g. "Group1", "Crypto-Panel") are discovered dynamically, so
# dropping a folder of *.md cards in makes it selectable with no code change.
PREFERRED_GROUPS: tuple[str, ...] = ("Unique-Personas", "Debate-Hosts")

# The default debater roster folder — what debate.ps1 -Group falls back to and
# the first entry browsers see. Kept as a named constant so a future rename is a
# one-line change here (mirror it in scripts/debate.ps1's -Group default).
DEFAULT_DEBATER_GROUP: str = "Unique-Personas"


def discover_groups() -> list[str]:
    """Return every persona group folder name under the registry root.

    ``PREFERRED_GROUPS`` (those that exist on disk) come first in declared
    order; any other subfolder follows, sorted case-insensitively. A missing
    registry root yields an empty list.
    """
    if not _PERSONAS_ROOT.is_dir():
        return []
    on_disk = {p.name for p in _PERSONAS_ROOT.iterdir() if p.is_dir()}
    ordered = [g for g in PREFERRED_GROUPS if g in on_disk]
    extra = sorted(on_disk.difference(ordered), key=str.lower)
    return ordered + extra

_SUMMARY_MAX = 240


@dataclass(frozen=True)
class Persona:
    """One personality card. ``body`` is the full markdown prompt (everything
    after the frontmatter); ``summary`` is a short best-effort blurb."""

    slug: str          # file stem, e.g. "crypto-chad"
    name: str          # display name, emoji stripped, e.g. "Crypto Chad"
    group: str         # the folder name, e.g. "Unique-Personas" or "Debate-Hosts"
    tags: list[str] = field(default_factory=list)
    category: str = ""
    subcategory: str = ""
    summary: str = ""
    body: str = ""
    path: Path = field(default=Path(), compare=False)

    def to_summary_dict(self) -> dict[str, object]:
        """Lightweight roster shape — no ``body`` (keeps token cost low)."""
        return {
            "slug": self.slug,
            "name": self.name,
            "group": self.group,
            "tags": self.tags,
            "summary": self.summary,
        }

    def to_full_dict(self) -> dict[str, object]:
        """Full shape including the persona prompt body as ``instructions``."""
        return {
            "slug": self.slug,
            "name": self.name,
            "group": self.group,
            "tags": self.tags,
            "category": self.category,
            "subcategory": self.subcategory,
            "summary": self.summary,
            "instructions": self.body,
        }


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split a card into (metadata, body). Hand-rolls the tiny subset of YAML
    the cards actually use: ``key: value`` scalars and a ``tags:`` block of
    ``- item`` lines. Cards without frontmatter return ({}, text)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()

    raw_meta, body = match.group(1), match.group(2)
    meta: dict[str, object] = {}
    current_list_key: str | None = None

    for line in raw_meta.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # A "- item" line belongs to the most recent list-valued key.
        if stripped.startswith("- ") and current_list_key is not None:
            meta.setdefault(current_list_key, [])
            meta[current_list_key].append(_strip_quotes(stripped[2:].strip()))  # type: ignore[union-attr]
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            # Either a list header (tags:) or an empty scalar; assume list and
            # let subsequent "- " lines fill it. Reset to [] if no items follow.
            current_list_key = key
            meta.setdefault(key, [])
        else:
            current_list_key = None
            meta[key] = _strip_quotes(value)

    return meta, body.strip()


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        # Strip the surrounding quotes, then unescape any \" inside, e.g.
        # `"🤖 Arthur \"Two-Pints\" Sullivan"` → `🤖 Arthur "Two-Pints" Sullivan`.
        return value[1:-1].replace("\\" + quote, quote)
    return value


# Leading emoji / symbol + whitespace on the frontmatter title, e.g. "🤖 ".
_LEADING_SYMBOLS_RE = re.compile(r"^[^\w(]+", re.UNICODE)


def _display_name(meta: dict[str, object], body: str, slug: str) -> str:
    """Prefer the frontmatter title (emoji stripped); fall back to the first
    ``# Heading`` in the body; finally the slug."""
    title = meta.get("title")
    if isinstance(title, str) and title.strip():
        return _LEADING_SYMBOLS_RE.sub("", title).strip() or slug
    heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if heading:
        return heading.group(1).strip()
    return slug


def _summary(body: str) -> str:
    """Best-effort one-liner: the ``## Purpose`` paragraph if present, else the
    first prose paragraph (skipping headings)."""
    purpose = re.search(
        r"^##\s+Purpose\s*\n(.+?)(?:\n##\s|\n#\s|\Z)", body,
        re.DOTALL | re.MULTILINE,
    )
    if purpose:
        text = purpose.group(1)
    else:
        text = ""
        for block in re.split(r"\n\s*\n", body):
            block = block.strip()
            if block and not block.startswith("#"):
                text = block
                break
    text = " ".join(text.split())  # collapse whitespace/newlines
    if len(text) > _SUMMARY_MAX:
        text = text[: _SUMMARY_MAX - 1].rstrip() + "…"
    return text


def _load_card(path: Path, group: str) -> Persona:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    slug = path.stem
    tags = meta.get("tags")
    return Persona(
        slug=slug,
        name=_display_name(meta, body, slug),
        group=group,
        tags=[str(t) for t in tags] if isinstance(tags, list) else [],
        category=str(meta.get("category", "")),
        subcategory=str(meta.get("subcategory", "")),
        summary=_summary(body),
        body=body,
        path=path,
    )


def list_personas(group: str | None = None) -> list[Persona]:
    """All persona cards, sorted by display name.

    ``group`` filters to a single group folder (case-insensitive) — *any*
    folder under ``agents/Debate-Agents/``, including curated subsets, not just
    the canonical two. ``None`` returns the canonical roster (``PREFERRED_GROUPS``
    = "Unique-Personas" + "Debate-Hosts") rather than every folder, so the
    default browse stays free of the duplicate cards a curated subset would
    reintroduce. Missing folders are skipped silently so the registry degrades to
    whatever is on disk.
    """
    if group is not None:
        wanted = [g for g in discover_groups() if g.lower() == group.lower()]
    else:
        wanted = [g for g in PREFERRED_GROUPS if (_PERSONAS_ROOT / g).is_dir()]
    personas: list[Persona] = []
    for g in wanted:
        folder = _PERSONAS_ROOT / g
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            personas.append(_load_card(path, g))
    personas.sort(key=lambda p: p.name.lower())
    return personas


def _normalize(value: str) -> str:
    """Lowercase and strip non-alphanumerics so 'Crypto Chad', 'crypto-chad',
    and '🤖 Crypto Chad' all compare equal."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def get_persona(query: str, group: str | None = None) -> Persona | None:
    """Look up one persona by slug or display name (case-insensitive, ignoring
    punctuation/emoji). Returns ``None`` if nothing matches."""
    target = _normalize(query)
    if not target:
        return None
    for persona in list_personas(group):
        if target in (_normalize(persona.slug), _normalize(persona.name)):
            return persona
    return None


# ---------------------------------------------------------------------------
# JSON CLI — lets non-Python callers (e.g. scripts/debate.ps1) reuse this
# registry instead of re-scanning the folder. Output is always ASCII-safe JSON
# (json.dumps default ``ensure_ascii=True``) so it round-trips through any
# console encoding and PowerShell's ConvertFrom-Json.
#
#   python src/orchestrator/personas.py list [--group Unique-Personas|Debate-Hosts]
#   python src/orchestrator/personas.py get  <slug-or-name> [--group ...] [--body]
#
# ``list`` emits a JSON array of {slug,name,group,tags,summary,path}.
# ``get`` emits one such object (plus ``instructions`` when --body is passed),
# or {"status":"not_found","query":...} with exit code 1.
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Query the debate-persona registry as JSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list all personas (optionally one group)")
    p_list.add_argument(
        "--group", default=None,
        help="group folder to list: Unique-Personas, Debate-Hosts, or any curated subset",
    )

    p_get = sub.add_parser("get", help="resolve one persona by slug or display name")
    p_get.add_argument("query")
    p_get.add_argument(
        "--group", default=None,
        help="restrict lookup to one group folder (Unique-Personas, Debate-Hosts, or a curated subset)",
    )
    p_get.add_argument(
        "--body", action="store_true",
        help="include the full persona prompt body as 'instructions'",
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        items = [
            {**p.to_summary_dict(), "path": str(p.path)}
            for p in list_personas(args.group)
        ]
        print(json.dumps(items))
        return 0

    # args.command == "get"
    persona = get_persona(args.query, args.group)
    if persona is None:
        print(json.dumps({"status": "not_found", "query": args.query}))
        return 1
    out: dict[str, object] = {**persona.to_full_dict(), "path": str(persona.path)}
    if not args.body:
        out.pop("instructions", None)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
