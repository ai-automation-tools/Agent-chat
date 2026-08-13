"""media_prompts.py — per-conversation image and audio production prompts.

A finished debate or podcast is a transcript. Turning it into something you'd
actually publish takes cover art and a voiced episode, and both of those are
jobs you hand to another tool: an image model, or a TTS render. This module
writes the **prompt** for that hand-off, filled in with one conversation's
topic, format, cast, and persona cards.

The web UI surfaces them as two buttons on the conversation page (served by
``GET /api/conversations/{cid}/prompts/{images,audio}.md``). Nothing here
generates media or calls an API — it produces text you paste into whatever tool
you use, which is the same posture as the battleground panel's copyable launch
command.

Both prompts are modelled on the ones already in service in the
AI-Automation-Library podcast pipeline (``My-Library/Podcasts/Podcasts/
Prompts/create-podcast-cover-images.md`` and ``render-weekly-audio-podcast.md``)
so their output drops into that archive's folder shape without translation:

- **Images** — one ``cover-image.png``, one ``<type>-team.png``, and one
  portrait per seat, named by persona slug.
- **Audio** — one MP3 per conversation, rendered per-speaker and stitched, with
  the transcript pulled from this app's own export endpoint rather than pasted
  into the prompt (it stays correct when the conversation grows, and keeps the
  prompt short enough to paste).

Filenames follow ``export.topic_slug()``, the 25-char slug that is already the
join key between the DB, the library archive, and the theater app. Don't
introduce a second slugging rule here.
"""

from __future__ import annotations

from typing import Any

from orchestrator.conv_types import (
    lead_of,
    parse_roles,
    role_label,
    type_label,
)
from orchestrator.export import parse_participant_personas, safe_name, topic_slug

# The two kinds this module knows how to write. The route validates against it.
PROMPT_KINDS: tuple[str, ...] = ("images", "audio")

# Where a finished bundle lands in the library archive. Used only to tell the
# receiving tool where to put its output; nothing here writes to disk.
_ARCHIVE_HINT = "Agent-Debates/<Topic-Slug>/"

# Per-card budget, in characters. Persona bodies run ~5KB and are mostly
# *behavioural* instruction — how to argue, what to never concede — which an
# image or voice tool has no use for. The part it does need (who this is, how
# they carry themselves, how they sound) is at the top of every card, because
# that's the shape the registry writes. Five uncapped cards would put a
# five-seat prompt near 30KB; capped, the whole prompt stays paste-sized.
_MAX_CARD_CHARS = 2000


def _trim_card(body: str) -> str:
    """Card body clipped to the budget on a line boundary, with a visible mark.

    Truncation is stated rather than silent — a reader who wants the rest can
    open the persona in the app, and a tool that sees the marker knows it isn't
    working from the whole card.
    """
    if len(body) <= _MAX_CARD_CHARS:
        return body
    cut = body[:_MAX_CARD_CHARS]
    nl = cut.rfind("\n")
    if nl > _MAX_CARD_CHARS // 2:
        cut = cut[:nl]
    return cut.rstrip() + "\n\n[... card trimmed — full text on the persona page ...]"


def _folder_slug(cid: int, topic: str) -> str:
    """Output folder name for this conversation's media."""
    return topic_slug(topic) or f"conversation-{cid}"


def _cast_rows(c: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per seat: agent id, seat label, persona name/slug/body.

    Order follows ``participants`` so the lead comes first for a type that has
    one. A seat with no recorded persona still gets a row — the CLI argues as
    itself, and it still needs a portrait.
    """
    personas = parse_participant_personas(c)
    conv_type = c.get("conv_type")
    roles = parse_roles(c.get("participant_roles"))
    lead = lead_of(conv_type, roles)
    rows: list[dict[str, Any]] = []
    for agent_id in (c.get("participants") or []):
        agent_id = str(agent_id)
        p = personas.get(agent_id) or {}
        name = str(p.get("persona_name") or "").strip()
        slug = str(p.get("persona_slug") or "").strip()
        rows.append({
            "agent_id": agent_id,
            "name": name or agent_id,
            "slug": slug or safe_name(agent_id).lower(),
            "body": str(p.get("persona_body") or "").strip(),
            "seat": role_label(conv_type, roles.get(agent_id)),
            "is_lead": agent_id == lead,
            "has_persona": bool(name),
        })
    return rows


def _cast_table(rows: list[dict[str, Any]]) -> str:
    """Markdown table of the cast — the at-a-glance version."""
    out = ["| Portrait file | Character | Seat | Played by |",
           "|:---|:---|:---|:---|"]
    for r in rows:
        seat = r["seat"] or "—"
        played = f"`{r['agent_id']}`"
        name = r["name"] if r["has_persona"] else f"{r['name']} _(no persona — argues as itself)_"
        out.append(f"| `{r['slug']}.png` | {name} | {seat} | {played} |")
    return "\n".join(out)


def _cast_cards(rows: list[dict[str, Any]]) -> str:
    """Full persona card per seat, so the image tool can read appearance and
    attitude out of the same text the agent was given."""
    blocks: list[str] = []
    for r in rows:
        head = f"### {r['name']}"
        if r["seat"]:
            head += f" — {r['seat']}"
        meta = [f"- **Portrait filename:** `{r['slug']}.png`",
                f"- **Played by:** `{r['agent_id']}`"]
        blocks.append("\n".join([head, "", *meta, ""]))
        if r["body"]:
            blocks.append("```text\n" + _trim_card(r["body"]) + "\n```\n")
        else:
            blocks.append(
                "_No persona card — this seat argued as the CLI itself. Depict it as a "
                "neutral, stylized AI participant rather than inventing a human character._\n"
            )
    return "\n".join(blocks)


def _header(c: dict[str, Any], cid: int, kind_title: str,
            n_messages: int | None = None) -> tuple[str, str, str]:
    """(title line, meta table, folder slug) shared by both prompts."""
    topic = str(c.get("topic") or "").strip() or f"Conversation #{cid}"
    label = type_label(c.get("conv_type"))
    slug = _folder_slug(cid, topic)
    meta = "\n".join([
        "| Field | Value |",
        "|:---|:---|",
        f"| Topic | {topic} |",
        f"| Format | {label} |",
        f"| Conversation | #{cid} |",
        f"| Topic slug | `{slug}` |",
        f"| Started | {c.get('created_at') or '—'} |",
        f"| Messages | {n_messages if n_messages is not None else '—'} |",
    ])
    return f"# {kind_title}: {topic}", meta, slug


def image_prompt(data: dict[str, Any], cid: int) -> str:
    """Prompt that produces this conversation's cover art, team shot, and
    one portrait per seat.

    Mirrors the library's cover-image prompt, trimmed to the set the operator
    asked for: **one** cover rather than three alternates, plus a portrait per
    participant that the podcast flow never needed (its personalities already
    have portraits on disk; a debate cast is drawn fresh each run).
    """
    c = data["conversation"]
    rows = _cast_rows(c)
    title, meta, slug = _header(c, cid, "Generate images", len(data.get("messages") or []))
    label = type_label(c.get("conv_type"))
    lower = label.lower()
    team_file = f"{lower}-team.png"
    n = len(rows)

    return f"""{title}

Generate the artwork for one finished {lower} from the Agent-Chat arena. Read
the cast cards below — they are the exact character briefs the agents were
given, so the portraits match how each one actually argued.

{meta}

## The cast

{_cast_table(rows)}

## Output

Generate exactly **{n + 2} PNG images** into a folder named `{slug}/`
(in the library archive that's `{_ARCHIVE_HINT.replace('<Topic-Slug>', slug)}`):

| File | What it is |
|:---|:---|
| `cover-image.png` | The episode cover. One strong visual concept for the topic itself — this is the card the web app and the archive surface. |
| `{team_file}` | A stylized group shot of the whole cast, in character, together. |
{chr(10).join(f"| `{r['slug']}.png` | Portrait of {r['name']}, alone. |" for r in rows)}

Square or near-square for the portraits. Do not overwrite an existing file —
stop and say so if any of these names is already taken.

## Cover image

- One idea, executed well: a visual metaphor for **{str(c.get('topic') or '').strip()}**, not a
  collage of everything discussed.
- Cinematic editorial photograph or premium digital illustration. Rich enough to
  reward a second look, readable as a thumbnail.
- Avoid the generic microphone-and-headphones shot unless the microphone is
  genuinely part of the concept.

## Team image

Every character in the table above, together, in one frame — a promo shot for
this specific episode. Use the cards to drive posture, clothing, props, and who
is clearly about to interrupt whom. Their relationships in the transcript should
be legible in the staging.

## Portraits

One per character, matching the team shot in style and lighting so the set reads
as one production. Infer appearance, age, dress, and attitude from the card. A
seat with no persona card is a stylized AI participant, not an invented person.

## Text rules

- No large blocks of embedded text. A short, correctly spelled title on the
  cover is optional.
- No fake platform logos and no real podcast-service branding.
- Do not put the character's name on their portrait.

## Likeness

Several personas are written after real public figures. Render them as
**stylized, clearly illustrative characters** — recognizable as the archetype
being played, not as photoreal impersonations of a specific living person, and
never in a way that suggests the real person said what this transcript contains.
If a card names a real person, treat the name as a costume: the caricature is
the character, not a claim about them.

## The cast cards

{_cast_cards(rows)}"""


def audio_prompt(data: dict[str, Any], cid: int,
                 base_url: str = "http://127.0.0.1:8765") -> str:
    """Prompt that turns this conversation into a voiced MP3 episode.

    Follows the shape of the library's ``render-weekly-audio-podcast.md``
    (workflow → generated files → requirements → rules), with one change worth
    knowing: the transcript is **fetched from the export endpoint** rather than
    pasted in. A long debate would blow past a comfortable paste, and the export
    is the format the archive already parses.
    """
    c = data["conversation"]
    rows = _cast_rows(c)
    title, meta, slug = _header(c, cid, "Generate audio", len(data.get("messages") or []))
    label = type_label(c.get("conv_type"))
    lower = label.lower()
    export_url = f"{base_url.rstrip('/')}/api/conversations/{cid}/export.md"

    voice_rows = "\n".join(
        f"| {r['name']} | {r['seat'] or '—'} | "
        f"{'the lead — opens and closes the show' if r['is_lead'] else 'participant'} |"
        for r in rows
    )

    return f"""{title}

Render this finished {lower} into a single voiced MP3. Every speaker gets its
own voice, held consistent across the whole episode.

{meta}

## 1. Get the transcript

```bash
curl -o "{slug}.md" "{export_url}"
```

The export is Markdown: a metadata table, then one `## <speaker> — <timestamp>`
heading per turn. **Those headings are the segment boundaries** — one TTS clip
per heading, in file order. Don't re-summarize, re-order, or merge turns; the
turn structure is the show.

> Fetch it rather than working from a paste — a conversation can still be
> running, and the export always reflects the current state.

## 2. Cast the voices

| Speaker | Seat | Notes |
|:---|:---|:---|
{voice_rows}

Assign one distinct voice per speaker before rendering anything, and **resolve
the whole cast first**. If a speaker can't be mapped, stop and say which one —
losing a character's voice signature partway through is worse than failing the
run. Reuse the same voice for the same character in future episodes.

Pick voices against the persona cards below, not against the speaker's CLI name.
Accent, age, and energy are in the card. Where two characters would land on
similar voices, move one — a listener has to be able to tell who is talking
without being told.

## 3. Render and stitch

- One audio clip per turn, numbered `001`…`NNN` so the concat order survives.
- Render in small concurrent batches to stay inside your provider's per-minute
  limits.
- Stitch with `ffmpeg`, **re-encoding** through `libmp3lame -b:a 128k -ar 44100`.
  Do not use `-c copy` — mixed clip parameters produce a file that plays for
  some players and not others.
- Keep parentheticals like `(laughs)` in the text unless your voice model reads
  them aloud; they're part of the delivery.

## Output

| File | What it is |
|:---|:---|
| `{slug}.mp3` | The finished episode. |
| `{slug}.md` | The transcript it was rendered from (keep it alongside the audio). |
| `README.md` | Title, date, format, cast, and the voice each speaker got. |

Into the folder `{slug}/` — in the library archive that's
`{_ARCHIVE_HINT.replace('<Topic-Slug>', slug)}`, next to the images from the
Generate-images prompt.

Do not overwrite an existing `{slug}.mp3` — fail clearly and stop.

## Rules

- Speak the transcript as written. This is a recording of an argument that
  already happened, not a new script: no new lines, no smoothing of a turn that
  reads awkwardly, no cutting a point someone lost.
- Report the final duration, size, and bitrate from `ffprobe`.
- If a step fails, stop and name the blocker. Don't ship a partial episode.

## Disclosure

Every speaker here is an AI agent playing a character. If you publish this
anywhere, say so in the episode description. Where a persona is written after a
real public figure, the voice must not be a clone of that person's actual voice.

## The cast cards

{_cast_cards(rows)}"""


def build_prompt(kind: str, data: dict[str, Any], cid: int,
                 base_url: str = "http://127.0.0.1:8765") -> str:
    """Dispatch by kind. Raises ``ValueError`` for an unknown kind."""
    if kind == "images":
        return image_prompt(data, cid)
    if kind == "audio":
        return audio_prompt(data, cid, base_url)
    raise ValueError(f"unknown prompt kind {kind!r}; choices: {', '.join(PROMPT_KINDS)}")


def prompt_filename(kind: str, cid: int, topic: str) -> str:
    """Download filename for a generated prompt."""
    return f"{_folder_slug(cid, topic)}-{kind}-prompt.md"
