"""Export-bundle rendering — the single source of truth for debate exports.

The Markdown bundle that represents one finished conversation
(``topic.md`` + ``personas/<agent>.md`` + ``transcript.md``) is consumed by
three surfaces that must never drift apart:

- the Web UI download endpoints (``/api/conversations/{cid}/export.md`` and
  ``…/export.zip`` in ``src/web_ui.py``),
- ``scripts/publish_debate.py``, which writes the same files straight into the
  AI-Automation-Library archive (``My-Library/Content/Agent-Debates/``),
- downstream consumers of that archive (the library site and the
  debate-chat-theater app), which parse the ``topic.md`` meta table + Cast
  section and the ``## sender — timestamp`` transcript headings.

Format changes here ripple to all of them — see docs/App/export-format.md.

All render functions are pure (dict in, str/bytes out). ``load_conversation``
is the one DB touch, provided so non-web callers don't reimplement the fetch.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import zipfile
from typing import Any


def fmt_time(ts: str | None) -> str:
    """ISO timestamp → ``YYYY-MM-DD HH:MM:SS`` (drop T, tz offset, micros)."""
    return (ts or "").replace("T", " ").split("+")[0].split(".")[0]


def topic_slug(topic: str, max_len: int = 25) -> str:
    """Convert a conversation topic to a filename-safe slug.

    Lowercased, ASCII-only (non-ASCII chars are dropped), runs of
    non-alphanumeric collapsed to single hyphens, leading/trailing
    hyphens stripped. Truncated to ``max_len`` characters. Returns
    an empty string if no usable characters remain — callers should
    fall back to a default like ``conversation-{cid}``.

    The slug is the join key between the DB, the library archive folder
    and the theater app — keep any change backward-compatible.
    """
    cleaned = (topic or "").encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def export_filename(cid: int, topic: str) -> str:
    """Filename for the single-file Markdown export download."""
    slug = topic_slug(topic)
    return f"{slug}.md" if slug else f"conversation-{cid}.md"


def export_zip_filename(cid: int, topic: str) -> str:
    """Filename for the .zip bundle download (topic slug, else conversation-<id>)."""
    slug = topic_slug(topic)
    return f"{slug}.zip" if slug else f"conversation-{cid}.zip"


def safe_name(s: str) -> str:
    """Filename-safe token for a bundle entry (keeps letters/digits/._-)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", (s or "").strip()).strip("-") or "x"


def parse_participant_personas(c: dict[str, Any]) -> dict[str, Any]:
    """Decode the conversation's ``participant_personas`` JSON column.

    Recorded by scripts/debate.ps1 at launch (and synced to the hosted
    mirror). Returns ``{}`` for conversations seeded without personas or
    with unparseable JSON.
    """
    raw = c.get("participant_personas")
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def persona_doc(agent_id: str, persona: dict[str, Any] | None) -> str:
    """One participant's Markdown doc — which CLI tool + which personality."""
    name = (persona or {}).get("persona_name") or agent_id
    slug = (persona or {}).get("persona_slug")
    body = (persona or {}).get("persona_body")

    lines: list[str] = [f"# {name}", "", "| Field | Value |", "|:---|:---|",
                        f"| AI tool / CLI | `{agent_id}` |"]
    if slug:
        lines.append(f"| Persona | {name} (`{slug}`) |")
    else:
        lines.append("| Persona | _not recorded for this conversation_ |")
    lines.append("")
    if body:
        lines += ["---", "", "## Personality card", "", str(body).rstrip(), ""]
    return "\n".join(lines)


def render_export_overview(c: dict[str, Any], personas: dict[str, Any]) -> str:
    """The topic + overview-metadata document (no invented subtopics)."""
    cid = c["id"]
    topic = str(c.get("topic", "") or "").strip()
    participants = c.get("participants") or []

    lines: list[str] = [f"# {topic}" if topic else f"# Conversation #{cid}", "",
                        "| Field | Value |", "|:---|:---|",
                        f"| Conversation | #{cid} |",
                        f"| Status | {c.get('status','')} |",
                        f"| Mode | {c.get('mode','')} (max {c.get('max_turns','?')} turns/agent) |"]
    if c.get("preset"):
        lines.append(f"| Preset | {c['preset']} |")
    lines.append(f"| Participants | {', '.join(participants)} |")
    lines.append(f"| Created | {fmt_time(c.get('created_at'))} |")
    lines.append(f"| Updated | {fmt_time(c.get('updated_at'))} |")
    if c.get("end_reason"):
        lines.append(f"| End reason | {c['end_reason']} |")
    lines.append("")

    if personas:
        lines += ["## Cast", ""]
        for ag in participants:
            nm = (personas.get(ag) or {}).get("persona_name")
            lines.append(f"- **{ag}** — {nm}" if nm else f"- **{ag}**")
        lines.append("")

    framing = c.get("kickoff_template")
    if framing:
        lines += ["---", "", "## Debate framing (kickoff)", "", str(framing).rstrip(), ""]

    lines += ["_Exported from Agent Battleground._", ""]
    return "\n".join(lines)


def render_export_markdown(data: dict[str, Any]) -> str:
    """Return a self-contained Markdown document for one conversation.

    Served via /api/conversations/{cid}/export.md, and written as
    ``transcript.md`` in the bundle. Each message body is emitted as-is —
    agents already write Markdown, so we keep their formatting verbatim
    instead of re-rendering through the HTML pipeline.
    """
    c = data["conversation"]
    msgs = data["messages"]
    parts = ", ".join(c.get("participants") or [])

    lines: list[str] = []
    topic = str(c.get("topic", "") or "").strip()
    lines.append(f"# Conversation #{c['id']}: {topic}" if topic else f"# Conversation #{c['id']}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|:---|:---|")
    lines.append(f"| Status | {c['status']} |")
    lines.append(f"| Mode | {c['mode']} (max {c['max_turns']} turns/agent) |")
    lines.append(f"| Participants | {parts} |")
    lines.append(f"| Created | {fmt_time(c['created_at'])} |")
    lines.append(f"| Updated | {fmt_time(c['updated_at'])} |")
    if c.get("end_reason"):
        lines.append(f"| End reason | {c['end_reason']} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not msgs:
        lines.append("_No messages yet._")
    else:
        for m in msgs:
            signal = f" — `signal={m['signal']}`" if m.get("signal") else ""
            lines.append(f"## {m['sender']} — {fmt_time(m['created_at'])}{signal}")
            lines.append("")
            lines.append((m.get("content") or "").rstrip())
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append(
        f"_Exported from Agent Battleground. Source: Conversation #{c['id']}._"
    )
    lines.append("")
    return "\n".join(lines)


def bundle_files(data: dict[str, Any]) -> list[tuple[str, str]]:
    """The full export bundle as ``(relative_path, content)`` pairs:

    - ``topic.md``            — the topic + overview metadata (+ kickoff framing).
    - ``personas/<agent>.md`` — one per participant: the CLI tool + its personality card.
    - ``transcript.md``       — the full debate (same body as the single-file export).

    Shared by the .zip endpoint and scripts/publish_debate.py so the browser
    download and the library archive can never diverge. Conversations seeded
    without personas still get one doc per participant noting the persona
    wasn't recorded.
    """
    c = data["conversation"]
    participants = c.get("participants") or []
    personas = parse_participant_personas(c)

    files: list[tuple[str, str]] = [("topic.md", render_export_overview(c, personas))]
    for ag in participants:
        p = personas.get(ag)
        slug = (p or {}).get("persona_slug")
        fname = f"personas/{safe_name(ag)}" + (f"-{safe_name(slug)}" if slug else "") + ".md"
        files.append((fname, persona_doc(ag, p)))
    files.append(("transcript.md", render_export_markdown(data)))
    return files


def render_export_zip(data: dict[str, Any]) -> bytes:
    """Build the multi-file Markdown bundle (.zip) for one conversation."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in bundle_files(data):
            zf.writestr(name, content)
    return buf.getvalue()


def load_conversation(db_path: str, cid: int) -> dict[str, Any] | None:
    """Fetch one conversation + its messages straight from chat.db.

    Mirrors web_ui.get_conversation() for non-web callers (the publish
    script). Read-only; standard connection settings (WAL DB, 10s timeout).
    """
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
        if not c:
            return None
        msgs = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (cid,),
        ).fetchall()
        conv = dict(c)
        try:
            conv["participants"] = json.loads(conv["participants"])
        except (json.JSONDecodeError, TypeError):
            pass
        return {"conversation": conv, "messages": [dict(m) for m in msgs]}
    finally:
        conn.close()
