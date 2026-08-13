"""Tests for the per-conversation image/audio production prompts.

Covers orchestrator/media_prompts.py and the route that serves it. The prompts
are text handed to another tool, so what matters is that every fact in them is
drawn from the conversation (not hardcoded), that the filenames match the
export contract's slug, and that the endpoint stays GET-only so it survives on
the read-only mirror.

Runnable standalone (``python tests/test_media_prompts.py``) and under pytest.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from starlette.testclient import TestClient  # noqa: E402

import web_ui  # noqa: E402
from orchestrator.conv_types import CONV_TYPES  # noqa: E402
from orchestrator.export import topic_slug  # noqa: E402
from orchestrator.media_prompts import (  # noqa: E402
    PROMPT_KINDS,
    _MAX_CARD_CHARS,
    _trim_card,
    audio_prompt,
    build_prompt,
    image_prompt,
    prompt_filename,
)
from orchestrator.seeding import seed_conversation  # noqa: E402
from presets import get_preset  # noqa: E402
from web.db import db_init, get_conversation, set_db_path  # noqa: E402

_PASS = 0
_FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS
    if cond:
        _PASS += 1
        print(f"PASS  {name}")
    else:
        _FAIL.append(f"{name} — {detail}")
        print(f"FAIL  {name} — {detail}")


def _card(name: str) -> str:
    return f"# {name}\n\nSpeaks in short sentences. Wears a grey coat.\n"


def _seed(db: str, **kw):
    """Seed one conversation and return its full ``get_conversation`` payload."""
    preset = kw.pop("preset", "debate")
    personas = kw.pop("personas", None)
    r = seed_conversation(
        db_path=db, mode="turns", max_turns=6,
        preset=preset, tone=get_preset(preset)["tone"],
        participant_personas=personas, **kw,
    )
    return r.conversation_id


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    db = str(tmp / "chat.db")
    set_db_path(db)
    db_init()

    # --- a debate with a recorded cast ------------------------------------
    debate_personas = {
        "claude-code": {"persona_slug": "grey-coat-gil", "persona_name": "Grey-Coat Gil",
                        "persona_body": _card("Grey-Coat Gil")},
        "codex": {"persona_slug": "loud-linda", "persona_name": "Loud Linda",
                  "persona_body": _card("Loud Linda")},
    }
    d_id = _seed(db, topic="Is coffee overrated?", participants=["claude-code", "codex"],
                 first="claude-code", conv_type="debate", personas=debate_personas)
    d_data = get_conversation(d_id)
    img = image_prompt(d_data, d_id)
    aud = audio_prompt(d_data, d_id, "http://127.0.0.1:8765")

    slug = topic_slug("Is coffee overrated?")
    check("image prompt asks for cover-image.png", "`cover-image.png`" in img)
    check("debate gets debate-team.png", "`debate-team.png`" in img,
          "podcast-team leaked into a debate" if "podcast-team" in img else "")
    check("no podcast-team in a debate", "podcast-team.png" not in img)
    check("one portrait per seat, named by persona slug",
          "`grey-coat-gil.png`" in img and "`loud-linda.png`" in img)
    check("image count states cast + 2", "**4 PNG images**" in img,
          "expected 2 seats + cover + team")
    check("output folder uses the export topic slug", f"`{slug}/`" in img)
    check("persona card body reaches the prompt", "Wears a grey coat" in img)
    check("topic appears in the image prompt", "Is coffee overrated?" in img)

    check("audio prompt names the mp3 by slug", f"`{slug}.mp3`" in aud)
    check("audio prompt fetches the real export URL",
          f"http://127.0.0.1:8765/api/conversations/{d_id}/export.md" in aud)
    check("audio prompt carries a voice-casting table",
          "| Speaker | Seat | Notes |" in aud and "Grey-Coat Gil" in aud)
    check("audio prompt keeps the disclosure section", "## Disclosure" in aud)

    # --- a podcast: the team filename and seat labels follow the type -----
    pod_personas = {
        "claude-code": {"persona_slug": "host-hattie", "persona_name": "Host Hattie",
                        "persona_body": _card("Host Hattie")},
        "codex": {"persona_slug": "guest-gus", "persona_name": "Guest Gus",
                  "persona_body": _card("Guest Gus")},
    }
    p_id = _seed(db, topic="Does remote work work?", participants=["claude-code", "codex"],
                 first="claude-code", conv_type="podcast", preset="podcast",
                 participant_roles={"claude-code": CONV_TYPES["podcast"].lead_role},
                 personas=pod_personas)
    p_data = get_conversation(p_id)
    p_img = image_prompt(p_data, p_id)
    p_aud = audio_prompt(p_data, p_id)
    check("podcast gets podcast-team.png", "`podcast-team.png`" in p_img)
    check("no debate-team in a podcast", "debate-team.png" not in p_img)
    check("seat labels come from the type", "Host" in p_img and "Guest" in p_img)
    check("the lead is marked in the voice table",
          "opens and closes the show" in p_aud)

    # --- a conversation with no recorded personas -------------------------
    b_id = _seed(db, topic="Bare run", participants=["claude-code", "codex"],
                 first="claude-code", conv_type="debate")
    b_img = image_prompt(get_conversation(b_id), b_id)
    check("no-persona seats still get a portrait row", "`claude-code.png`" in b_img)
    check("no-persona seats are called out, not invented",
          "argued as the CLI itself" in b_img)

    # --- card trimming ----------------------------------------------------
    long_body = "\n".join(f"line {i} " + "x" * 60 for i in range(200))
    trimmed = _trim_card(long_body)
    check("a long card is trimmed", len(trimmed) < len(long_body))
    check("trimming stays near the budget",
          len(trimmed) <= _MAX_CARD_CHARS + 80, f"got {len(trimmed)}")
    check("trimming is announced, not silent", "card trimmed" in trimmed)
    check("a short card is untouched", _trim_card("short") == "short")

    # --- dispatch + filenames --------------------------------------------
    check("build_prompt dispatches both kinds",
          build_prompt("images", d_data, d_id) == img
          and build_prompt("audio", d_data, d_id, "http://127.0.0.1:8765") == aud)
    try:
        build_prompt("video", d_data, d_id)
        check("unknown kind raises", False, "no ValueError")
    except ValueError:
        check("unknown kind raises", True)
    check("download filename is slug + kind",
          prompt_filename("images", d_id, "Is coffee overrated?") == f"{slug}-images-prompt.md")

    # --- the route --------------------------------------------------------
    client = TestClient(web_ui.app)
    for kind in PROMPT_KINDS:
        r = client.get(f"/api/conversations/{d_id}/prompts/{kind}.md")
        check(f"GET prompts/{kind}.md is 200", r.status_code == 200, str(r.status_code))
        check(f"prompts/{kind}.md is markdown",
              r.headers["content-type"].startswith("text/markdown"))
    r = client.get(f"/api/conversations/{d_id}/prompts/images.md?download=1")
    check("?download=1 sets a filename",
          "attachment" in r.headers.get("content-disposition", ""))
    check("unknown kind 404s",
          client.get(f"/api/conversations/{d_id}/prompts/video.md").status_code == 404)
    check("missing conversation 404s",
          client.get("/api/conversations/999999/prompts/images.md").status_code == 404)

    # The audio prompt tells the reader to curl a URL — it has to be this host,
    # not a hardcoded localhost, or a hosted visitor gets an unusable command.
    body = client.get(f"/api/conversations/{d_id}/prompts/audio.md").text
    check("export URL is built from the request origin",
          f"http://testserver/api/conversations/{d_id}/export.md" in body)

    # --- read-only mirror: these are GETs, so they must still work --------
    # The middleware stack is built at import time (`app = Starlette(
    # middleware=_build_middleware())`), so the flag has to be set *before* a
    # reload — setting it against the already-built app tests nothing.
    saved = os.environ.get("AGENT_CHAT_PUBLIC_READONLY")
    try:
        os.environ["AGENT_CHAT_PUBLIC_READONLY"] = "1"
        importlib.reload(web_ui)
        web_ui.set_db_path(db)
        ro = TestClient(web_ui.app)
        check("read-only mode is actually on for this client",
              web_ui._is_public_readonly())
        # A write route proves the middleware is engaged, so the 200 below is
        # evidence rather than an artifact of a stack that never loaded.
        check("read-only blocks a known write route",
              ro.post(f"/api/conversations/{d_id}/stop").status_code == 403,
              str(ro.post(f"/api/conversations/{d_id}/stop").status_code))
        r = ro.get(f"/api/conversations/{d_id}/prompts/images.md")
        check("prompts still readable on the read-only mirror", r.status_code == 200,
              str(r.status_code))
        check("a POST to a prompt URL is refused",
              ro.post(f"/api/conversations/{d_id}/prompts/images.md").status_code in (403, 405),
              str(ro.post(f"/api/conversations/{d_id}/prompts/images.md").status_code))
    finally:
        if saved is None:
            os.environ.pop("AGENT_CHAT_PUBLIC_READONLY", None)
        else:
            os.environ["AGENT_CHAT_PUBLIC_READONLY"] = saved
        importlib.reload(web_ui)

    print()
    if _FAIL:
        print(f"{_PASS} passed, {len(_FAIL)} FAILED")
        for f in _FAIL:
            print("  -", f)
        return 1
    print(f"{_PASS}/{_PASS} passed")
    return 0


def test_media_prompts():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
