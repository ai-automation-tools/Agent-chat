"""The static homepage in ``homepage/`` keeps the links it exists for.

``homepage/`` is published to GitHub Pages at roundtable.ai-automation-tools.dev
(``.github/workflows/homepage.yml``); the running app is on the ``-demo`` host.
Not to be confused with ``test_homepage.py``, which covers the web UI's own home
page. Nothing here runs the page's JS; it pins the HTML strings.

    .\\.venv\\Scripts\\python.exe tests\\test_site_homepage.py
"""

from __future__ import annotations

from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "homepage"
PAGE = (SITE / "index.html").read_text(encoding="utf-8")
NOT_FOUND = (SITE / "404.html").read_text(encoding="utf-8")

DEMO = "https://agent-chat-demo.ai-automation-tools.dev"
REPO = "https://github.com/ai-automation-tools/roundtable"
BLOB = REPO + "/blob/main/"


def test_required_links():
    for href in (
        DEMO + "/",
        REPO,
        "#start",
        "https://ai-automation-tools.dev/",
        "https://ai-automation-tools.dev/cookies.html",
        BLOB + "docs/CHANGELOG.md",
        BLOB + "docs/ROADMAP.md",
    ):
        assert f'href="{href}"' in PAGE, href
    assert 'data-ail-consent="manage"' in PAGE
    assert '<script src="https://ai-automation-tools.dev/consent.js" defer></script>' in PAGE
    assert '<link rel="canonical" href="https://roundtable.ai-automation-tools.dev/" />' in PAGE


def test_source_bar_first_and_primary_cta_is_demo():
    body = PAGE.split("<body>", 1)[1]
    assert body.index('class="skip"') < body.index('class="src-bar"') < body.index('class="topbar"')
    assert f'class="btn btn-primary" href="{DEMO}/"' in PAGE


def test_blob_links_point_at_files_that_exist():
    root = SITE.parent
    for chunk in PAGE.split(f'href="{BLOB}')[1:]:
        rel = chunk.split('"', 1)[0]
        assert (root / rel).is_file(), rel


def test_self_contained_and_site_files():
    assert "cdn.tailwindcss.com" not in PAGE
    assert (SITE / "favicon.svg").is_file()
    assert (SITE / ".nojekyll").is_file()
    assert (SITE / "CNAME").read_text(encoding="utf-8").strip() == "roundtable.ai-automation-tools.dev"


def test_404_forwards_deep_links_to_demo():
    assert f"var DEMO = '{DEMO}';" in NOT_FOUND
    assert "location.pathname !== '/'" in NOT_FOUND
    assert "location.replace(DEMO + location.pathname + location.search + location.hash)" in NOT_FOUND
    assert f'href="{DEMO}/"' in NOT_FOUND  # no-JS fallback


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
