"""Persona registry — the typed, queryable list of debate personality cards.

This is the single source of truth for "what personalities exist and what is
each one's prompt body". It is intentionally dependency-light (stdlib only —
no PyYAML) so the MCP server can import it without growing the pinned dep set.

**Storage:** personas live in a ``personas`` table inside the shared SQLite DB
(``db/chat.db``, the same file the conversation message bus uses). The DB is the
runtime source of truth, and the bidirectional Fly sidecar syncs the table, so
add/edit/delete works and persists on both the local box and the hosted mirror —
unlike the old on-disk-card layout, which the hosted deploy couldn't write.

The markdown cards under ``agents/Debate-Agents/`` are now a one-time **import
seed** only (``import_personas_from_files`` / the ``import`` CLI subcommand).
There is no DB→files export — the cards remain in git as the original snapshot.

Seed card layout (see ``agents/Debate-Agents/Unique-Personas/*.md`` and
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

Not every card has the same ``##`` sections (the longer hand-authored cards
omit ``## Purpose`` / ``## Instructions``), so the registry never relies on
section structure: the whole post-frontmatter body *is* the persona prompt.
A one-line ``summary`` is best-effort — the ``## Purpose`` paragraph if present,
else the first prose paragraph of the body. ``summary`` and ``path`` are derived
(not stored): ``summary`` is recomputed from ``body``, ``path`` is synthesized as
``agents/Debate-Agents/<group>/<slug>.md`` so the Persona shape is unchanged for
callers (``debate.ps1`` only displays ``.path``, never opens it).

Consumers:
- ``agent_chat_mcp.py`` — ``list_personas`` / ``get_persona`` MCP tools so an
  agent can browse the roster and adopt a card itself.
- ``scripts/debate.ps1`` — calls the JSON CLI at the bottom of this module
  (``list`` / ``get``) to cast its debaters, instead of re-scanning the folder.
- ``web_ui.py`` — the ``/personas`` management page (CRUD over the same table).
"""

from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# agents/Debate-Agents/ lives at the repo root; this file is
# <repo>/src/orchestrator/personas.py → parents[2] is <repo>.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PERSONAS_ROOT = _REPO_ROOT / "agents" / "Debate-Agents"


# --- SQLite layer ----------------------------------------------------------
# "group" is a SQL reserved word → always quoted in DDL/DML. This DDL mirrors
# the personas block in the SCHEMA constants of agent_chat_mcp.py / web_ui.py /
# orchestrator/seeding.py; it's duplicated here (same rationale as seeding
# duplicating SCHEMA) so the registry works against a fresh DB even when neither
# the MCP server nor the web UI has booted to create the table.
_PERSONA_DDL = """
CREATE TABLE IF NOT EXISTS personas (
    "group"      TEXT NOT NULL,
    slug         TEXT NOT NULL,
    name         TEXT NOT NULL,
    tags         TEXT,
    category     TEXT,
    subcategory  TEXT,
    body         TEXT NOT NULL,
    avatar_mime  TEXT,
    avatar_data  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY ("group", slug)
);
CREATE INDEX IF NOT EXISTS idx_personas_updated ON personas(updated_at);
"""

# Columns added to `personas` after its initial shape. Mirrors the personas rows
# of _MIGRATIONS in agent_chat_mcp.py / web/db.py / seeding.py — applied here too
# because this module is reachable without any of them booting first (the MCP
# tools, the JSON CLI that debate.ps1 calls).
_PERSONA_MIGRATIONS = (
    ("avatar_mime", "ALTER TABLE personas ADD COLUMN avatar_mime TEXT"),
    ("avatar_data", "ALTER TABLE personas ADD COLUMN avatar_data TEXT"),
)


def _db_path() -> str:
    """Resolve the DB path: ``$AGENT_CHAT_DB`` > ``<repo>/db/chat.db``.

    Copies ``orchestrator.seeding.default_db_path()`` rather than importing it,
    to keep this module's import graph stdlib-only (seeding pulls pydantic)."""
    env_db = os.environ.get("AGENT_CHAT_DB")
    if env_db:
        return env_db
    return str(_REPO_ROOT / "db" / "chat.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    """Open the shared DB in the same mode every other process uses (WAL,
    autocommit). Creates the parent dir + file on first use."""
    db_path = _db_path()
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create the personas table if a fresh DB hasn't been booted by the server
    or web UI yet, then apply additive column migrations to an older one.

    Both halves are idempotent — ``IF NOT EXISTS`` for the table, and each
    migration gated on ``PRAGMA table_info`` not already listing the column."""
    conn.executescript(_PERSONA_DDL)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(personas)")}
    for column, ddl in _PERSONA_MIGRATIONS:
        if column not in cols:
            conn.execute(ddl)

# Persona group folders live under agents/Debate-Agents/. "Unique-Personas" is
# the debater roster; "Debate-Hosts" holds the personalities that RUN a room —
# shared across conversation types, since a good moderator is a good podcast
# host and the operator keeps one set of cards (see
# ``conv_types.ConvType.lead_group``, which every type points here). These two
# always sort first when present and form the canonical roster returned when
# no group is requested. ANY OTHER subdirectory is also a valid group — curated
# topic subsets (e.g. "Group1", "Crypto-Panel") are discovered dynamically, so
# dropping a folder of *.md cards in makes it selectable with no code change.
PREFERRED_GROUPS: tuple[str, ...] = ("Unique-Personas", "Debate-Hosts")

# The default debater roster folder — what debate.ps1 -Group falls back to and
# the first entry browsers see. Kept as a named constant so a future rename is a
# one-line change here (mirror it in scripts/debate.ps1's -Group default).
DEFAULT_DEBATER_GROUP: str = "Unique-Personas"

# Reference-card groups: real personas, browsable and editable on /personas, but
# never eligible for random debate casting. "AI-Models" holds one card per CLI
# (claude-code, codex, …) used as the default Cast for conversations that were
# seeded without personas — casting "Claude Code" as a random debater against
# Gordon Ramsay would be nonsense. Selection paths must go through
# list_debater_personas(); an explicit --group request is still honoured.
AI_MODELS_GROUP: str = "AI-Models"
RESERVED_GROUPS: tuple[str, ...] = (AI_MODELS_GROUP,)


def discover_groups() -> list[str]:
    """Return every persona group present in the DB.

    ``PREFERRED_GROUPS`` (those with at least one row) come first in declared
    order; any other group follows, sorted case-insensitively. An empty /
    unreachable DB yields an empty list.
    """
    try:
        conn = _connect()
    except sqlite3.Error:
        return []
    try:
        _ensure_table(conn)
        rows = conn.execute('SELECT DISTINCT "group" FROM personas').fetchall()
    finally:
        conn.close()
    present = {r["group"] for r in rows}
    ordered = [g for g in PREFERRED_GROUPS if g in present]
    extra = sorted(present.difference(ordered), key=str.lower)
    return ordered + extra

_SUMMARY_MAX = 240

# Every column a Persona is built from — i.e. everything except ``avatar_data``.
# Reads go through this rather than ``SELECT *`` so listing the roster doesn't
# drag a few hundred KB of base64 image per card through memory; the bytes are
# fetched on their own by get_avatar() when one is actually being served.
_PERSONA_READ_COLS = (
    '"group", slug, name, tags, category, subcategory, body, avatar_mime, '
    "created_at, updated_at"
)


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
    # Non-empty when the persona carries an uploaded avatar in the DB (the
    # image/* type of the stored bytes). The bytes themselves are deliberately
    # NOT on this dataclass — every list_personas() call would then haul a few
    # hundred KB per card. Fetch them with get_avatar() when serving.
    avatar_mime: str = ""
    path: Path = field(default=Path(), compare=False)

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar_mime)

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


def _row_get(row: sqlite3.Row, key: str, default: object = None) -> object:
    """``row[key]`` that tolerates a column the DB doesn't have yet — a row read
    through a connection that hasn't run ``_ensure_table``'s migrations."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _row_to_persona(row: sqlite3.Row) -> Persona:
    """Build a Persona from a ``personas`` table row. ``tags`` is JSON-decoded,
    ``summary`` recomputed from ``body``, and ``path`` synthesized under the
    (possibly absent) seed-card root so the shape matches the old loader."""
    raw_tags = row["tags"]
    try:
        tags = json.loads(raw_tags) if raw_tags else []
    except (ValueError, TypeError):
        tags = []
    if not isinstance(tags, list):
        tags = []
    group = row["group"]
    slug = row["slug"]
    body = row["body"] or ""
    return Persona(
        slug=slug,
        name=row["name"],
        group=group,
        tags=[str(t) for t in tags],
        category=row["category"] or "",
        subcategory=row["subcategory"] or "",
        summary=_summary(body),
        body=body,
        avatar_mime=str(_row_get(row, "avatar_mime") or ""),
        path=_PERSONAS_ROOT / group / f"{slug}.md",
    )


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


def parse_card_text(text: str, slug: str, group: str,
                    path: Path | None = None) -> Persona:
    """Build a Persona from raw markdown-card text (frontmatter + body).

    Shared by ``_load_card`` (on-disk seed cards) and the Web UI's markdown
    importer (``import_persona_card``) so both parse the frontmatter the same
    way. ``slug`` is the file stem / chosen slug; ``group`` is the target
    folder. ``path`` is synthesized when not given so the Persona shape matches
    the loader's."""
    meta, body = _parse_frontmatter(text)
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
        path=path if path is not None else _PERSONAS_ROOT / group / f"{slug}.md",
    )


def _load_card(path: Path, group: str) -> Persona:
    return parse_card_text(path.read_text(encoding="utf-8"), path.stem, group, path)


def list_personas(group: str | None = None) -> list[Persona]:
    """Persona cards, sorted by display name.

    ``group`` filters to a single group (case-insensitive) — *any* group in the
    DB. ``None`` returns **every** persona across all groups (ordered by group,
    then name), so the agent-facing MCP ``list_personas`` / ``get_persona`` tools
    surface the whole roster regardless of how the operator named their groups.
    (Group names are dynamic; there is no fixed "canonical" set.) An empty or
    unreachable DB yields an empty list.
    """
    try:
        conn = _connect()
    except sqlite3.Error:
        return []
    try:
        _ensure_table(conn)
        if group is not None:
            rows = conn.execute(
                f"SELECT {_PERSONA_READ_COLS} FROM personas "
                'WHERE "group" = ? COLLATE NOCASE ORDER BY name COLLATE NOCASE',
                (group,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_PERSONA_READ_COLS} FROM personas "
                'ORDER BY "group" COLLATE NOCASE, name COLLATE NOCASE'
            ).fetchall()
    finally:
        conn.close()
    return [_row_to_persona(r) for r in rows]


def list_debater_personas(group: str | None = None) -> list[Persona]:
    """Personas eligible for **random debate casting**.

    Same as ``list_personas()``, except that with no ``group`` the reserved
    groups (``RESERVED_GROUPS`` — the AI-Models reference cards) are left out, so
    a random cast never draws "Claude Code" as a debater. An explicit ``group``
    is honoured as-is: asking for AI-Models gets AI-Models.

    Every random-selection path should use this, not ``list_personas()``:
    ``DEFAULT_DEBATER_GROUP`` may hold zero rows (the roster was reorganised into
    per-category groups), and the callers' `or`-fallback to "all personas" is
    what would otherwise pull the reference cards in.
    """
    if group is not None:
        return list_personas(group)
    reserved = {g.lower() for g in RESERVED_GROUPS}
    return [p for p in list_personas(None) if p.group.lower() not in reserved]


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
# Write layer — create / update / delete persona rows in the DB. Used by the Web
# UI's persona-management page. Because personas now live in the DB (synced to
# the hosted mirror by the sidecar), this works on both local and hosted — the
# old local-only gate is gone. category/subcategory are preserved on update.
# ---------------------------------------------------------------------------

class PersonaWriteError(ValueError):
    """Raised on invalid create/update/delete. Caller renders ``.args[0]``."""


def _find_persona_any_group(query: str) -> Persona | None:
    """Locate a persona by slug/name across **every** group folder (not just the
    canonical roster ``get_persona`` searches when no group is given). First
    match in ``discover_groups()`` order wins. Used by the write layer so cards
    in curated subset groups are still editable/deletable."""
    for g in discover_groups():
        found = get_persona(query, g)
        if found is not None:
            return found
    return None


def root_exists() -> bool:
    """True whenever the persona DB is reachable.

    Personas now live in the synced ``personas`` table, not the (un-deployed)
    agents/ tree, so management is available on the hosted mirror too — callers
    that gated on this to disable persona writes now stay enabled everywhere.
    Returns False only if the DB can't be opened at all.
    """
    try:
        conn = _connect()
    except sqlite3.Error:
        return False
    try:
        _ensure_table(conn)
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return True


def slugify(value: str) -> str:
    """File-stem slug from a display name: ASCII, lowercase, hyphen-separated."""
    cleaned = (value or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")


def _tags_json(tags: list[str] | None) -> str | None:
    """Serialize a tag list to the JSON stored in the ``tags`` column (None when
    empty, so the column reads NULL rather than ``"[]"``)."""
    if not tags:
        return None
    return json.dumps([str(t) for t in tags])


# ---------------------------------------------------------------------------
# Avatars
#
# An uploaded avatar lives on the persona row — base64 in ``avatar_data``, its
# type in ``avatar_mime`` — rather than as a file under images/AgentChat-Avatars/.
# That placement is the whole point: the personas table is carried by the
# local→Fly sidecar, so an avatar uploaded locally reaches the hosted mirror on
# the next sync tick with no redeploy, and one uploaded on the mirror survives
# the next deploy (a file written into the image's tree would not).
#
# web/avatars.py resolves in the order: uploaded row > shipped file > default
# silhouette, so this only ever adds art — nothing that renders today changes.
# ---------------------------------------------------------------------------

# Decoded ceiling for one avatar. Generous for a 512px square (the web UI
# downscales before upload) and small enough that a row still syncs comfortably.
AVATAR_MAX_BYTES = 2 * 1024 * 1024

# Raster formats only, and the type is decided by the file's magic bytes — never
# by what the uploader claimed. SVG is deliberately unsupported: it is
# script-capable markup and these bytes are served back from the app's own
# origin. The web UI converts everything (SVG included) to PNG client-side, so
# this costs the operator nothing at the point of upload.
AVATAR_MIME_TYPES: tuple[str, ...] = (
    "image/png", "image/jpeg", "image/gif", "image/webp",
)


def sniff_image_mime(data: bytes) -> str | None:
    """The image type of ``data`` by signature, or None if it isn't one we
    accept. This is the only thing that decides ``avatar_mime``."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_avatar(data_b64: str) -> tuple[str, str]:
    """Validate an uploaded avatar and return ``(mime, canonical_base64)``.

    Accepts a bare base64 string or a full ``data:image/png;base64,…`` URI, with
    or without embedded whitespace. Raises :class:`PersonaWriteError` on
    unreadable base64, an oversized image, or bytes that aren't one of
    :data:`AVATAR_MIME_TYPES`. The returned base64 is re-encoded from the
    decoded bytes, so what lands in the DB is always canonical and prefix-free.
    """
    raw_str = (data_b64 or "").strip()
    if not raw_str:
        raise PersonaWriteError("avatar image is empty")
    if raw_str.startswith("data:"):
        _, _, raw_str = raw_str.partition(",")
    raw_str = "".join(raw_str.split())  # tolerate wrapped/pretty-printed base64
    try:
        data = base64.b64decode(raw_str, validate=True)
    except (ValueError, TypeError):
        raise PersonaWriteError("avatar image is not valid base64")
    if not data:
        raise PersonaWriteError("avatar image is empty")
    if len(data) > AVATAR_MAX_BYTES:
        cap = AVATAR_MAX_BYTES // (1024 * 1024)
        raise PersonaWriteError(f"avatar image is too large (max {cap} MB)")
    mime = sniff_image_mime(data)
    if mime is None:
        raise PersonaWriteError(
            "avatar must be a PNG, JPEG, GIF, or WebP image"
        )
    return mime, base64.b64encode(data).decode("ascii")


def get_avatar(slug: str, group: str | None = None) -> tuple[str, bytes] | None:
    """The stored avatar for ``slug`` as ``(mime, bytes)``, or None.

    Keyed on slug alone (optionally narrowed by ``group``), matching the
    file-based convention in web/avatars.py — an avatar belongs to a persona
    name, not to a group. In the rare case the same slug exists in two groups
    with two avatars, the most recently updated one wins.
    """
    if not slug:
        return None
    sql = (
        "SELECT avatar_mime, avatar_data FROM personas "
        "WHERE slug = ? AND avatar_data IS NOT NULL AND avatar_data != ''"
    )
    params: list[str] = [slug]
    if group:
        sql += ' AND "group" = ? COLLATE NOCASE'
        params.append(group)
    sql += " ORDER BY updated_at DESC LIMIT 1"
    try:
        conn = _connect()
    except sqlite3.Error:
        return None
    try:
        _ensure_table(conn)
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    try:
        return str(row["avatar_mime"] or "image/png"), base64.b64decode(
            row["avatar_data"], validate=True
        )
    except (ValueError, TypeError):
        return None


def avatar_index() -> dict[str, str]:
    """``{slug: updated_at}`` for every persona carrying an uploaded avatar.

    One query for the whole roster — the render path asks "does this slug have
    an uploaded avatar, and how fresh is it?" once per avatar slot, and that has
    to stay off the per-row query path. ``updated_at`` doubles as the
    cache-busting token for the ``/avatars/{slug}`` URL.
    """
    try:
        conn = _connect()
    except sqlite3.Error:
        return {}
    try:
        _ensure_table(conn)
        rows = conn.execute(
            "SELECT slug, MAX(updated_at) AS updated_at FROM personas "
            "WHERE avatar_data IS NOT NULL AND avatar_data != '' "
            "GROUP BY slug"
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    return {r["slug"]: str(r["updated_at"] or "") for r in rows}


def set_avatar(slug: str, data_b64: str, *, group: str | None = None) -> Persona:
    """Attach (or replace) an uploaded avatar on an existing persona."""
    mime, clean = normalize_avatar(data_b64)
    return _write_avatar(slug, mime, clean, group=group)


def clear_avatar(slug: str, *, group: str | None = None) -> Persona:
    """Drop a persona's uploaded avatar. It falls back to whatever
    web/avatars.py resolves next — a shipped file, else the default
    silhouette."""
    return _write_avatar(slug, None, None, group=group)


def _write_avatar(slug: str, mime: str | None, data: str | None, *,
                  group: str | None = None) -> Persona:
    existing = (get_persona(slug, group) if group
                else _find_persona_any_group(slug))
    if existing is None:
        raise PersonaWriteError(f"persona not found: '{slug}'")
    conn = _connect()
    try:
        _ensure_table(conn)
        conn.execute(
            'UPDATE personas SET avatar_mime = ?, avatar_data = ?, '
            'updated_at = ? WHERE "group" = ? AND slug = ?',
            (mime, data, now_iso(), existing.group, existing.slug),
        )
        row = conn.execute(
            f"SELECT {_PERSONA_READ_COLS} FROM personas "
            'WHERE "group" = ? AND slug = ?',
            (existing.group, existing.slug),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_persona(row)


def create_persona(*, name: str, body: str, group: str = DEFAULT_DEBATER_GROUP,
                   tags: list[str] | None = None, category: str = "",
                   subcategory: str = "", slug: str | None = None,
                   avatar: str | None = None) -> Persona:
    """Insert a new persona row under ``group``. Raises PersonaWriteError on a
    blank name/body or a (group, slug) collision.

    ``avatar`` is an optional base64 image (or ``data:`` URI) validated by
    :func:`normalize_avatar`; omit it and the persona renders whatever
    web/avatars.py resolves for its slug."""
    name = (name or "").strip()
    body = (body or "").strip()
    if not name:
        raise PersonaWriteError("name is required")
    if not body:
        raise PersonaWriteError("body is required")
    group = (group or DEFAULT_DEBATER_GROUP).strip() or DEFAULT_DEBATER_GROUP
    the_slug = slugify(slug or name)
    if not the_slug:
        raise PersonaWriteError("name has no usable ASCII characters for a slug")
    # Validate the image before the INSERT so a bad upload fails the whole
    # create rather than leaving an avatar-less persona behind.
    avatar_mime, avatar_data = (
        normalize_avatar(avatar) if avatar else (None, None)
    )
    ts = now_iso()
    conn = _connect()
    try:
        _ensure_table(conn)
        try:
            conn.execute(
                'INSERT INTO personas ("group", slug, name, tags, category, '
                "subcategory, body, avatar_mime, avatar_data, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (group, the_slug, name, _tags_json(tags), category or "",
                 subcategory or "", body, avatar_mime, avatar_data, ts, ts),
            )
        except sqlite3.IntegrityError:
            raise PersonaWriteError(
                f"a persona with slug '{the_slug}' already exists in '{group}'"
            )
        row = conn.execute(
            f'SELECT {_PERSONA_READ_COLS} FROM personas '
            'WHERE "group" = ? AND slug = ?',
            (group, the_slug),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_persona(row)


def update_persona(slug: str, *, name: str | None = None, body: str | None = None,
                   tags: list[str] | None = None, group: str | None = None,
                   avatar: str | None = None,
                   clear_avatar: bool = False) -> Persona:
    """Update an existing persona (matched by slug or display name). Preserves
    category/subcategory. ``group`` moves the row to another group (it keeps its
    slug). Raises PersonaWriteError if not found or if a group-move would collide
    with an existing row.

    ``avatar`` is a base64 image that replaces any current one; ``clear_avatar``
    removes it. Passing neither leaves the existing avatar alone — the common
    case, since the edit form saves the card body on every keystroke-worth of
    work and must not drop the art each time."""
    existing = _find_persona_any_group(slug)
    if existing is None:
        raise PersonaWriteError(f"persona not found: '{slug}'")
    new_name = (name.strip() if name is not None else existing.name) or existing.name
    new_body = (body if body is not None else existing.body).strip()
    if not new_body:
        raise PersonaWriteError("body is required")
    new_tags = tags if tags is not None else existing.tags
    target_group = (group or existing.group).strip() or existing.group
    # Validate before touching the row, so a rejected image doesn't half-apply
    # the rest of the edit.
    avatar_sql, avatar_params = "", ()
    if avatar:
        mime, data = normalize_avatar(avatar)
        avatar_sql = ", avatar_mime = ?, avatar_data = ?"
        avatar_params = (mime, data)
    elif clear_avatar:
        avatar_sql = ", avatar_mime = NULL, avatar_data = NULL"
    ts = now_iso()
    conn = _connect()
    try:
        _ensure_table(conn)
        if target_group.lower() != existing.group.lower():
            clash = conn.execute(
                'SELECT 1 FROM personas WHERE "group" = ? AND slug = ?',
                (target_group, existing.slug),
            ).fetchone()
            if clash:
                raise PersonaWriteError(
                    f"a persona with slug '{existing.slug}' already exists in "
                    f"'{target_group}'"
                )
        conn.execute(
            'UPDATE personas SET "group" = ?, name = ?, body = ?, tags = ?'
            f'{avatar_sql}, updated_at = ? WHERE "group" = ? AND slug = ?',
            (target_group, new_name, new_body, _tags_json(new_tags),
             *avatar_params, ts, existing.group, existing.slug),
        )
        row = conn.execute(
            f'SELECT {_PERSONA_READ_COLS} FROM personas '
            'WHERE "group" = ? AND slug = ?',
            (target_group, existing.slug),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_persona(row)


def delete_persona(slug: str, group: str | None = None) -> bool:
    """Delete a persona row by slug/name. Returns False if it wasn't found."""
    existing = get_persona(slug, group) if group else _find_persona_any_group(slug)
    if existing is None:
        return False
    conn = _connect()
    try:
        _ensure_table(conn)
        conn.execute(
            'DELETE FROM personas WHERE "group" = ? AND slug = ?',
            (existing.group, existing.slug),
        )
    finally:
        conn.close()
    return True


def import_persona_card(text: str, *, group: str = DEFAULT_DEBATER_GROUP,
                        filename: str | None = None,
                        overwrite: bool = False,
                        avatar: str | None = None) -> Persona:
    """Create a persona from a single raw markdown card (frontmatter + body).

    Used by the Web UI's "import from Markdown files" feature. The slug is
    derived from ``filename`` (its stem) when given, else from the frontmatter
    title; the name/tags/category/subcategory come from the frontmatter and the
    body is everything after it. Raises ``PersonaWriteError`` on an empty body,
    an unusable slug, or a (group, slug) collision when ``overwrite`` is False.

    ``avatar`` is the base64 image that shipped alongside the card — an image
    paired with it in the same upload or zip (see ``web/api/personas.py``). When
    an overwrite carries no image, the row's existing avatar is carried across
    rather than dropped: re-importing an edited card must not silently delete
    art the operator uploaded separately.
    """
    group = (group or DEFAULT_DEBATER_GROUP).strip() or DEFAULT_DEBATER_GROUP
    stem = Path(filename).stem if filename else ""
    parsed = parse_card_text(text, slugify(stem) or "persona", group)
    body = parsed.body.strip()
    if not body:
        raise PersonaWriteError("markdown card has no body after the frontmatter")
    the_slug = slugify(stem) or slugify(parsed.name)
    if not the_slug:
        raise PersonaWriteError("no usable slug from the filename or title")
    avatar_mime, avatar_data = (
        normalize_avatar(avatar) if avatar else (None, None)
    )
    ts = now_iso()
    conn = _connect()
    try:
        _ensure_table(conn)
        clash = conn.execute(
            "SELECT avatar_mime, avatar_data FROM personas "
            'WHERE "group" = ? AND slug = ?',
            (group, the_slug),
        ).fetchone()
        if clash and not overwrite:
            raise PersonaWriteError(
                f"a persona with slug '{the_slug}' already exists in '{group}' "
                "(enable overwrite to replace it)"
            )
        # INSERT OR REPLACE deletes the old row, so an avatar-less re-import
        # would blank the art unless we carry it forward explicitly.
        if clash and avatar_data is None:
            avatar_mime = clash["avatar_mime"]
            avatar_data = clash["avatar_data"]
        verb = "INSERT OR REPLACE" if overwrite else "INSERT"
        conn.execute(
            f'{verb} INTO personas ("group", slug, name, tags, category, '
            "subcategory, body, avatar_mime, avatar_data, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (group, the_slug, parsed.name, _tags_json(parsed.tags),
             parsed.category, parsed.subcategory, body, avatar_mime,
             avatar_data, ts, ts),
        )
        row = conn.execute(
            f'SELECT {_PERSONA_READ_COLS} FROM personas '
            'WHERE "group" = ? AND slug = ?',
            (group, the_slug),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_persona(row)


# ---------------------------------------------------------------------------
# Importer — one-time seed of the DB from the on-disk seed cards under
# agents/Debate-Agents/. The cards are no longer the runtime source of truth
# (the DB is), so this is run once after upgrading; it's a no-op where the cards
# aren't present (the hosted deploy). There is no DB→files export (DB-only).
# ---------------------------------------------------------------------------

def import_personas_from_files(overwrite: bool = False) -> dict[str, int]:
    """Walk the seed-card tree and load each card into the ``personas`` table.

    ``overwrite=False`` (default) uses INSERT OR IGNORE — existing (group, slug)
    rows are left untouched. ``overwrite=True`` uses INSERT OR REPLACE and bumps
    ``updated_at`` so the change syncs. Returns ``{"imported": N, "skipped": M}``.
    A missing seed-card root yields ``{"imported": 0, "skipped": 0}``.
    """
    if not _PERSONAS_ROOT.is_dir():
        return {"imported": 0, "skipped": 0}
    cards: list[Persona] = []
    for folder in sorted(p for p in _PERSONAS_ROOT.iterdir() if p.is_dir()):
        for path in sorted(folder.glob("*.md")):
            cards.append(_load_card(path, folder.name))
    imported = 0
    conn = _connect()
    try:
        _ensure_table(conn)
        for c in cards:
            ts = now_iso()
            verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"
            # The avatar columns are read back from the row being replaced:
            # OR REPLACE deletes it first, and a seed card carries no image, so
            # without this a re-seed would wipe every uploaded avatar.
            cur = conn.execute(
                f'{verb} INTO personas ("group", slug, name, tags, category, '
                "subcategory, body, avatar_mime, avatar_data, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, "
                '(SELECT avatar_mime FROM personas WHERE "group" = ? AND slug = ?), '
                '(SELECT avatar_data FROM personas WHERE "group" = ? AND slug = ?), '
                "?, ?)",
                (c.group, c.slug, c.name, _tags_json(c.tags), c.category,
                 c.subcategory, c.body, c.group, c.slug, c.group, c.slug,
                 ts, ts),
            )
            imported += cur.rowcount if cur.rowcount > 0 else 0
    finally:
        conn.close()
    return {"imported": imported, "skipped": len(cards) - imported}


# ---------------------------------------------------------------------------
# JSON CLI — lets non-Python callers (e.g. scripts/debate.ps1) reuse this
# registry instead of re-scanning the folder. Output is always ASCII-safe JSON
# (json.dumps default ``ensure_ascii=True``) so it round-trips through any
# console encoding and PowerShell's ConvertFrom-Json.
#
#   python src/orchestrator/personas.py list [--group Unique-Personas|Debate-Hosts | --all-groups]
#   python src/orchestrator/personas.py get  <slug-or-name> [--group ... | --all-groups] [--body]
#   python src/orchestrator/personas.py import [--overwrite]
#
# ``list`` emits a JSON array of {slug,name,group,tags,summary,path}.
# ``get`` emits one such object (plus ``instructions`` when --body is passed),
# or {"status":"not_found","query":...} with exit code 1.
# ``import`` seeds the DB from the on-disk cards, emitting {"imported","skipped"}.
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Query the debate-persona registry as JSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list all personas (optionally one group)")
    p_list.add_argument(
        "--group", default=None,
        help="group to list: Unique-Personas, Debate-Hosts, or any curated subset",
    )
    p_list.add_argument(
        "--all-groups", action="store_true",
        help="list every persona across ALL groups, reserved ones included "
             "(ignores --group)",
    )
    p_list.add_argument(
        "--castable", action="store_true",
        help="list every persona eligible for random debate casting: all groups "
             f"except the reserved reference groups ({', '.join(RESERVED_GROUPS)}). "
             "This is what a random cast should draw from (ignores --group)",
    )

    p_get = sub.add_parser("get", help="resolve one persona by slug or display name")
    p_get.add_argument("query")
    p_get.add_argument(
        "--group", default=None,
        help="restrict lookup to one group (Unique-Personas, Debate-Hosts, or a curated subset)",
    )
    p_get.add_argument(
        "--all-groups", action="store_true",
        help="resolve across ALL groups (ignores --group)",
    )
    p_get.add_argument(
        "--body", action="store_true",
        help="include the full persona prompt body as 'instructions'",
    )

    p_import = sub.add_parser(
        "import", help="seed the DB from the on-disk seed cards (one-time)")
    p_import.add_argument(
        "--overwrite", action="store_true",
        help="replace existing rows (default skips them)",
    )

    args = parser.parse_args(argv)

    if args.command == "import":
        print(json.dumps(import_personas_from_files(overwrite=args.overwrite)))
        return 0

    if args.command == "list":
        if args.castable:
            personas_out = list_debater_personas()
        elif args.all_groups:
            personas_out = [p for g in discover_groups() for p in list_personas(g)]
        else:
            personas_out = list_personas(args.group)
        items = [
            {**p.to_summary_dict(), "path": str(p.path)}
            for p in personas_out
        ]
        print(json.dumps(items))
        return 0

    # args.command == "get"
    persona = (_find_persona_any_group(args.query) if args.all_groups
               else get_persona(args.query, args.group))
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
