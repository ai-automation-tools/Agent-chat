"""The homepage renders self-contained, in the shared chrome, with its anchors.

Until 2026-10-05 the landing page pulled Tailwind from a CDN and styled itself
with inline utility classes, so it could not render with no network — the one
thing the local operator's page is supposed to do. These pins keep it that way
and keep the pieces the rest of the app links to (the ``#resources`` anchor the
rail points at from every page, the shared source bar, topbar and rail) on the
page. Pytest-compatible and standalone-runnable, like every suite here.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_tmp = tempfile.mkdtemp(prefix="agent-chat-home-")
os.environ["AGENT_CHAT_DB"] = str(Path(_tmp) / "chat.db")

import web_ui  # noqa: E402
from web import assets  # noqa: E402
from web.render import home  # noqa: E402

web_ui.set_db_path(os.environ["AGENT_CHAT_DB"])
web_ui.db_init()

PAGE = home._render_homepage({"conversations": 0, "active": 0, "messages": 0}, [])

# The section ids the rail (`/#resources`) and the in-page links depend on.
SECTION_IDS = ("what", "personas", "how", "latest", "extension", "resources")


def test_no_cdn_or_utility_classes():
    """The page loads nothing from a CDN and carries no Tailwind utilities."""
    assert "cdn.tailwindcss.com" not in PAGE
    assert "<script src=" not in PAGE, "every script on the homepage is inline"
    # A utility-class signature: responsive prefixes and the zinc/emerald palette
    # names Tailwind generates. None may survive in a class attribute.
    for cls in re.findall(r'class="([^"]*)"', PAGE):
        assert not re.search(r"(^|\s)(md|sm|lg):", cls), cls
        assert not re.search(r"\b(text|bg|border)-(zinc|emerald|amber|sky|violet)-\d", cls), cls


def test_shared_chrome_and_anchors():
    assert '<div class="src-bar">' in PAGE
    assert '<div class="topbar">' in PAGE
    assert '<nav class="siderail"' in PAGE
    for sid in SECTION_IDS:
        assert f'id="{sid}"' in PAGE, f"missing section #{sid}"
    # Every section below the fold reveals on scroll, and the hero rises once.
    assert PAGE.count('class="wrap band reveal"') == len(SECTION_IDS)
    assert 'class="hero-grid rise"' in PAGE


def test_stylesheet_is_the_shared_one():
    """HOME_CSS composes the tokens + chrome block, and carries every class the
    template emits — a renamed class would otherwise style nothing, silently."""
    assert assets.HOME_CSS.startswith(assets.DESIGN_TOKENS)
    assert assets.TOPBAR_CSS in assets.HOME_CSS
    assert "--ease:" in assets.DESIGN_TOKENS
    # The ground + spotlight live in the shared block so every page has them.
    assert ".spot::before" in assets.TOPBAR_CSS
    assert "background-image" in assets.TOPBAR_CSS
    # Every class the page uses has a rule. Dynamic ones (status words on the
    # latest rows, the stat colours) are listed by hand.
    styled = set(re.findall(r"\.([a-zA-Z][\w-]*)", assets.HOME_CSS))
    styled |= {"active", "complete", "spot"}
    used: set[str] = set()
    for cls in re.findall(r'class="([^"]*)"', PAGE):
        used.update(c for c in cls.split() if c)
    # Classes owned by the shared chrome (rail, topbar, palette, source bar)
    # are styled by TOPBAR_CSS, which is inside HOME_CSS — so they pass too.
    missing = sorted(c for c in used if c not in styled and not c.startswith(("btn-", "rail-", "cmdk", "live-", "src-", "mark")))
    assert not missing, f"classes on the page with no rule in HOME_CSS: {missing}"


def test_empty_states_render():
    assert "No conversations yet" in PAGE
    assert "Nothing has finished yet" in PAGE
    assert "Browse all conversations" in PAGE


def test_resources_tiles_are_data_driven():
    """The five project tiles render through _res_tile like the generated ones,
    with the links the old hand-written markup carried."""
    html = home._render_homepage_res_groups()
    assert html.count('class="res-tile spot"') == 11
    for href in (
        "https://github.com/ai-automation-tools/Agent-chat/blob/main/docs/Roadmap.md",
        "https://prompts.mikesailab.com/?library=public&section=agents",
        "/conversations/14",
        "https://www.sqlite.org/wal.html",
        "https://github.com/michaelschecht",
    ):
        assert href in html, href


def test_spotlight_tracker_is_wired():
    assert "initSpot" in assets.SHELL_JS
    assert "closest('.spot')" in assets.SHELL_JS


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:  # noqa: PERF203
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
