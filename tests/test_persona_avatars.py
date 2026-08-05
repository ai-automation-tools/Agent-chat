r"""Tests for persona avatars — upload, import pairing, serving, and sync.

An avatar lives on the persona's DB row rather than in
``images/AgentChat-Avatars/``, because that's the only placement the local→Fly
sidecar can carry. The things worth pinning:

* **Validation is by magic bytes**, never by what the uploader claimed — that's
  what keeps script-capable SVG out of a path that serves bytes back from the
  app's own origin.
* **Resolution order**: uploaded row > shipped file > default silhouette.
* **Import pairing**: a card and an image in the same upload (loose, flat zip, or
  one folder per persona) land as one persona with both instructions and art.
* **An avatar survives an edit** — saving a body without touching the picture,
  or re-importing an edited card, must not silently delete it.
* **Column-list parity** across the sync sites, since a column the sidecar
  doesn't carry never reaches the mirror.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_persona_avatars.py

Uses an isolated temp DB — never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# A valid 1x1 transparent PNG. Only its 8-byte signature matters to the sniffer,
# but a real file keeps the browser-side assumptions honest too.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB"
    "0C8AAAAASUVORK5CYII="
)
PNG_B64 = base64.b64encode(PNG_1PX).decode("ascii")
GIF_1PX = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _fresh_db() -> Path:
    """Point the whole stack at an empty temp DB and return its path."""
    tmp = Path(tempfile.mkdtemp(prefix="agentchat-avatars-")) / "chat.db"
    import web.db as webdb

    webdb.set_db_path(str(tmp))
    webdb.db_init()
    assert os.environ["AGENT_CHAT_DB"] == str(tmp)
    from web import avatars

    avatars.invalidate_index()
    return tmp


def _client() -> TestClient:
    import web_ui

    return TestClient(web_ui.app)


def _zip(entries: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, blob in entries.items():
            zf.writestr(name, blob)
    return base64.b64encode(buf.getvalue()).decode("ascii")


CARD = "---\ntitle: Crypto Chad\ntags:\n- crypto\n---\n\n# Crypto Chad\n\nTo the moon.\n"


# ---------------------------------------------------------------------------
# 1. Validation
# ---------------------------------------------------------------------------

def test_normalize_accepts_raster_and_derives_mime_from_bytes() -> None:
    from orchestrator import personas

    mime, clean = personas.normalize_avatar(PNG_B64)
    assert mime == "image/png"
    assert base64.b64decode(clean) == PNG_1PX

    # A data: URI and embedded whitespace are both tolerated, and the stored
    # base64 comes back canonical either way.
    wrapped = "data:image/png;base64," + "\n".join(
        PNG_B64[i:i + 40] for i in range(0, len(PNG_B64), 40)
    )
    assert personas.normalize_avatar(wrapped) == (mime, clean)

    gif_mime, _ = personas.normalize_avatar(base64.b64encode(GIF_1PX).decode())
    assert gif_mime == "image/gif"


def test_normalize_rejects_svg_and_junk() -> None:
    from orchestrator import personas

    # The declared type is irrelevant — SVG is script-capable markup and these
    # bytes get served from the app's own origin.
    for payload in (
        base64.b64encode(SVG_BYTES).decode(),
        "data:image/png;base64," + base64.b64encode(SVG_BYTES).decode(),
        base64.b64encode(b"not an image at all").decode(),
    ):
        try:
            personas.normalize_avatar(payload)
        except personas.PersonaWriteError:
            continue
        raise AssertionError(f"non-image accepted: {payload[:40]}")

    for bad in ("", "%%%not base64%%%"):
        try:
            personas.normalize_avatar(bad)
        except personas.PersonaWriteError:
            continue
        raise AssertionError(f"invalid base64 accepted: {bad!r}")


def test_normalize_rejects_oversized_image() -> None:
    from orchestrator import personas

    huge = PNG_1PX + b"\x00" * (personas.AVATAR_MAX_BYTES + 1)
    try:
        personas.normalize_avatar(base64.b64encode(huge).decode())
    except personas.PersonaWriteError as e:
        assert "too large" in str(e)
    else:
        raise AssertionError("oversized avatar accepted")


# ---------------------------------------------------------------------------
# 2. Registry writes
# ---------------------------------------------------------------------------

def test_create_with_avatar_then_edit_keeps_it() -> None:
    _fresh_db()
    from orchestrator import personas

    p = personas.create_persona(name="Crypto Chad", body="To the moon.",
                                group="Testers", avatar=PNG_B64)
    assert p.has_avatar and p.avatar_mime == "image/png"
    assert personas.get_avatar("crypto-chad") == ("image/png", PNG_1PX)

    # A body edit that says nothing about the avatar must leave it alone —
    # the editor saves the card on every change.
    edited = personas.update_persona("crypto-chad", body="Still to the moon.")
    assert edited.has_avatar
    assert personas.get_avatar("crypto-chad") is not None

    cleared = personas.update_persona("crypto-chad", clear_avatar=True)
    assert not cleared.has_avatar
    assert personas.get_avatar("crypto-chad") is None


def test_bad_avatar_fails_the_whole_create() -> None:
    """A rejected image must not leave an avatar-less persona behind."""
    _fresh_db()
    from orchestrator import personas

    try:
        personas.create_persona(name="Ghost", body="Boo.", group="Testers",
                                avatar=base64.b64encode(SVG_BYTES).decode())
    except personas.PersonaWriteError:
        pass
    else:
        raise AssertionError("SVG avatar accepted on create")
    assert personas.get_persona("ghost") is None


def test_listing_never_carries_avatar_bytes() -> None:
    """list_personas() must not haul base64 images through memory."""
    _fresh_db()
    from orchestrator import personas

    personas.create_persona(name="Crypto Chad", body="To the moon.",
                            group="Testers", avatar=PNG_B64)
    (card,) = personas.list_personas("Testers")
    assert card.has_avatar, "the flag still has to come through"
    assert PNG_B64 not in repr(card), "avatar bytes leaked into the roster shape"


def test_avatar_index_and_url_version_track_the_upload() -> None:
    _fresh_db()
    from orchestrator import personas
    from web import avatars

    personas.create_persona(name="Crypto Chad", body="To the moon.",
                            group="Testers")
    avatars.invalidate_index()
    assert personas.avatar_index() == {}
    plain = avatars.avatar_url("crypto-chad")

    personas.set_avatar("crypto-chad", PNG_B64)
    avatars.invalidate_index()
    assert set(personas.avatar_index()) == {"crypto-chad"}
    versioned = avatars.avatar_url("crypto-chad")
    assert versioned != plain and "?v=" in versioned


# ---------------------------------------------------------------------------
# 3. Serving
# ---------------------------------------------------------------------------

def test_uploaded_avatar_wins_over_file_art_and_default() -> None:
    _fresh_db()
    from orchestrator import personas
    from web import avatars

    client = _client()
    # No persona, no file: the silhouette, and the sentinel URL the editor uses.
    assert client.get("/avatars/nobody-at-all").headers["content-type"].startswith("image/svg")
    assert client.get(avatars.DEFAULT_AVATAR_URL).status_code == 200

    personas.create_persona(name="Crypto Chad", body="To the moon.",
                            group="Testers", avatar=PNG_B64)
    avatars.invalidate_index()
    resp = client.get("/avatars/crypto-chad")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == PNG_1PX
    # Operator-supplied bytes are served locked down.
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in resp.headers["content-security-policy"]

    # An agent id that IS a shipped brand mark keeps resolving to the file.
    shipped = client.get("/avatars/claude-code")
    assert shipped.status_code == 200


# ---------------------------------------------------------------------------
# 4. HTTP write endpoints
# ---------------------------------------------------------------------------

def test_create_and_update_via_api() -> None:
    _fresh_db()
    from orchestrator import personas

    client = _client()
    r = client.post("/api/personas", json={
        "name": "Crypto Chad", "body": "To the moon.", "group": "Testers",
        "avatar": {"b64": PNG_B64},
    })
    assert r.status_code == 200 and r.json()["has_avatar"] is True

    # No avatar key at all -> untouched.
    r = client.post("/api/personas/crypto-chad", json={"body": "Moon soon."})
    assert r.json()["has_avatar"] is True

    r = client.post("/api/personas/crypto-chad", json={"clear_avatar": True})
    assert r.json()["has_avatar"] is False
    assert personas.get_avatar("crypto-chad") is None

    r = client.post("/api/personas/crypto-chad",
                    json={"avatar": base64.b64encode(SVG_BYTES).decode()})
    assert r.status_code == 400 and "PNG" in r.json()["error"]


# ---------------------------------------------------------------------------
# 5. Import pairing
# ---------------------------------------------------------------------------

def _import(client: TestClient, **payload) -> dict:
    payload.setdefault("group", "Testers")
    r = client.post("/api/personas/import", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_zip_with_card_and_image_applies_both() -> None:
    _fresh_db()
    from orchestrator import personas

    client = _client()
    body = _import(client, zips=[{"filename": "cast.zip", "b64": _zip({
        "crypto-chad.md": CARD.encode(),
        "crypto-chad.png": PNG_1PX,
    })}])
    assert (body["imported"], body["avatars"], body["errors"]) == (1, 1, [])
    card = personas.get_persona("crypto-chad")
    assert card is not None and card.name == "Crypto Chad"
    assert card.tags == ["crypto"], "instructions and frontmatter still apply"
    assert personas.get_avatar("crypto-chad") == ("image/png", PNG_1PX)


def test_zip_folder_per_persona_pairs_by_folder() -> None:
    """<persona>/card.md + <persona>/avatar.png — names don't have to match."""
    _fresh_db()
    from orchestrator import personas

    client = _client()
    body = _import(client, zips=[{"filename": "cast.zip", "b64": _zip({
        "crypto-chad/card.md": CARD.encode(),
        "crypto-chad/avatar.png": PNG_1PX,
        "gordon/gordon.md": "# Gordon\n\nIt's raw.\n".encode(),
        "gordon/gordon-avatar.gif": GIF_1PX,
    })}])
    assert body["imported"] == 2 and body["avatars"] == 2, body
    assert personas.get_avatar("card")[0] == "image/png"
    assert personas.get_avatar("gordon")[0] == "image/gif"


def test_loose_card_and_image_pair_by_name() -> None:
    _fresh_db()
    from orchestrator import personas

    client = _client()
    body = _import(
        client,
        files=[{"filename": "crypto-chad.md", "text": CARD}],
        images=[{"filename": "crypto-chad-avatar.png", "b64": PNG_B64}],
    )
    assert body["imported"] == 1 and body["avatars"] == 1
    assert personas.get_avatar("crypto-chad") is not None


def test_unmatched_image_is_reported_not_guessed() -> None:
    _fresh_db()
    from orchestrator import personas

    client = _client()
    body = _import(
        client,
        files=[{"filename": "crypto-chad.md", "text": CARD},
               {"filename": "gordon.md", "text": "# Gordon\n\nIt's raw.\n"}],
        images=[{"filename": "holiday-photo.png", "b64": PNG_B64}],
    )
    assert body["imported"] == 2 and body["avatars"] == 0
    assert any("no matching card" in e for e in body["errors"]), body["errors"]
    assert personas.get_avatar("crypto-chad") is None
    assert personas.get_avatar("gordon") is None


def test_bad_image_costs_the_picture_not_the_persona() -> None:
    _fresh_db()
    from orchestrator import personas

    client = _client()
    body = _import(client, zips=[{"filename": "cast.zip", "b64": _zip({
        "crypto-chad.md": CARD.encode(),
        "crypto-chad.png": SVG_BYTES,  # .png extension, SVG content
    })}])
    assert body["imported"] == 1 and body["avatars"] == 0
    assert any("avatar skipped" in e for e in body["errors"]), body["errors"]
    assert personas.get_persona("crypto-chad") is not None


def test_reimport_without_an_image_keeps_the_existing_avatar() -> None:
    _fresh_db()
    from orchestrator import personas

    client = _client()
    _import(client, zips=[{"filename": "cast.zip", "b64": _zip({
        "crypto-chad.md": CARD.encode(), "crypto-chad.png": PNG_1PX,
    })}])
    body = _import(
        client, overwrite=True,
        files=[{"filename": "crypto-chad.md", "text": CARD + "\nEdited.\n"}],
    )
    assert body["imported"] == 1
    assert personas.get_avatar("crypto-chad") == ("image/png", PNG_1PX), \
        "re-importing an edited card must not delete art uploaded separately"


def test_images_alone_are_rejected() -> None:
    _fresh_db()
    client = _client()
    r = client.post("/api/personas/import", json={
        "group": "Testers", "images": [{"filename": "x.png", "b64": PNG_B64}],
    })
    assert r.status_code == 400 and "card" in r.json()["error"]


# ---------------------------------------------------------------------------
# 6. Schema / sync parity
# ---------------------------------------------------------------------------

def test_persona_column_lists_match_across_sync_sites() -> None:
    """A column web/db.py carries but scripts/db_sync.py doesn't never syncs."""
    import ast

    from web.db import _PERSONA_COLUMNS

    # Read the sidecar's tuple out of the source rather than importing it — the
    # script is an operator entrypoint, not a library.
    src = (Path(__file__).resolve().parent.parent / "scripts" / "db_sync.py"
           ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    sidecar = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "PERSONA_COLUMNS" for t in node.targets)
    )
    assert sidecar == _PERSONA_COLUMNS
    assert "avatar_data" in _PERSONA_COLUMNS and "avatar_mime" in _PERSONA_COLUMNS


def test_every_schema_site_declares_the_avatar_columns() -> None:
    """Four declaration sites; a DB's shape must not depend on who created it."""
    _fresh_db()
    import sqlite3

    import agent_chat_mcp
    import web.db as webdb
    from orchestrator import personas, seeding

    for label, ddl in (
        ("agent_chat_mcp.SCHEMA", agent_chat_mcp.SCHEMA),
        ("web.db.SCHEMA", webdb.SCHEMA),
        ("seeding.SCHEMA", seeding.SCHEMA),
        ("personas._PERSONA_DDL", personas._PERSONA_DDL),
    ):
        tmp = Path(tempfile.mkdtemp(prefix="agentchat-ddl-")) / "chat.db"
        conn = sqlite3.connect(tmp)
        conn.executescript(ddl)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(personas)")}
        conn.close()
        assert {"avatar_mime", "avatar_data"} <= cols, f"{label} is missing them"


def test_migration_adds_the_columns_to_a_pre_avatar_db() -> None:
    """An existing db/chat.db upgrades in place rather than erroring."""
    import sqlite3

    import web.db as webdb

    tmp = Path(tempfile.mkdtemp(prefix="agentchat-migrate-")) / "chat.db"
    conn = sqlite3.connect(tmp)
    conn.executescript(
        'CREATE TABLE personas ("group" TEXT NOT NULL, slug TEXT NOT NULL, '
        "name TEXT NOT NULL, tags TEXT, category TEXT, subcategory TEXT, "
        "body TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        ' PRIMARY KEY ("group", slug));'
    )
    conn.execute(
        'INSERT INTO personas VALUES ("Testers", "old-timer", "Old Timer", '
        'NULL, "", "", "Been here a while.", "2026-01-01", "2026-01-01")'
    )
    conn.commit()
    conn.close()

    webdb.set_db_path(str(tmp))
    webdb.db_init()
    from web import avatars
    from orchestrator import personas

    avatars.invalidate_index()
    card = personas.get_persona("old-timer")
    assert card is not None and not card.has_avatar
    personas.set_avatar("old-timer", PNG_B64)
    assert personas.get_avatar("old-timer") == ("image/png", PNG_1PX)


def test_ingest_round_trips_an_avatar() -> None:
    """The sidecar's payload must carry the image to the hosted mirror."""
    _fresh_db()
    from web.db import _PERSONA_COLUMNS, ingest_payload, since_payload

    row = dict(zip(_PERSONA_COLUMNS, (
        "Testers", "crypto-chad", "Crypto Chad", None, "", "",
        "To the moon.", "image/png", PNG_B64, "2026-08-05", "2026-08-05",
    )))
    result = ingest_payload([], [], [], [row], [])
    assert result["personas_upserted"] == 1

    from orchestrator import personas
    assert personas.get_avatar("crypto-chad") == ("image/png", PNG_1PX)

    payload = since_payload("1970-01-01", [], "1970-01-01", [])
    assert payload["personas"][0]["avatar_data"] == PNG_B64


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {fn.__name__}: {exc!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
