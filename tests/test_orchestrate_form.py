r"""Tests for the ``/orchestrate`` form's inline browser JS — string invariants only.

The form is ~750 lines of markup plus ~740 lines of inline script rendered from
one f-string in ``web/render/orchestrate.py``, and until this file it had zero
coverage of the script half. That is not a theoretical gap: the host seat picker
once shipped *invisible* because ``updatePersonaRows()`` collected every
``.orch-persona-row`` — the moderator's row included — and ``display:none``'d
them on every render. The markup was present and correct, so every HTML-string
assertion in ``tests/`` passed; the JS hid the section a frame later.

A browser would catch that class of bug, but a browser is a dependency this
repo deliberately does not have (every suite here runs on the bare venv). So
these are the pure-string invariants a browser would have made redundant — the
same shape as the ``ext``-alias grep in ``tests/test_battleground.py``:

1. every element the script looks up by id or by ``[name=…]`` is actually in
   the rendered page — or is a *conditionally* rendered control, in which case
   the script must null-guard it;
2. every ``.class`` the script queries exists, in the markup or in the row
   template the script itself builds;
3. no bulk query runs at document scope;
4. a class the script bulk-hides lives only inside the container that owns it —
   the invariant the shipped bug broke.

None of this proves the form *works*. It proves the script and the markup still
refer to the same page. Re-check ``/orchestrate`` in a browser before believing
a green run here.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_orchestrate_form.py
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orchestrator.conv_types import CONV_TYPES  # noqa: E402
from web.render.orchestrate import _render_orchestrate  # noqa: E402

# Controls the renderer emits only in some configurations. Each one must be
# null-guarded at *every* use in the script, because a machine without the
# feature renders a page without the element.
#   deliver_locally — _delivery_toggle_html() renders nothing unless
#                     config/delivery.json exists (delivery is off by default).
_CONDITIONAL_CONTROLS: dict[str, str] = {
    "deliver_locally": "delivery is off unless config/delivery.json exists",
}

# class -> id of the container that owns it. The script scopes its bulk-hide of
# these at `form`, which is the whole page — so this table is the containment
# the code does not state, and the thing the 2026-09 bug got wrong.
_BULK_HIDDEN_CLASSES: dict[str, str] = {
    "orch-preset": "orch-preset-grid",
}

# Tags that never close, so an ancestor stack must not wait for an end tag.
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})


def _page(conv_type: str | None = None) -> str:
    """Render the form the way the route does when no CLI is declared."""
    return _render_orchestrate([], conv_type=conv_type)


def _pages() -> dict[str, str]:
    """One render per conversation type — the form re-labels itself per type."""
    return {key: _page(key) for key in CONV_TYPES}


def _script(page: str) -> str:
    """The form's own <script> block (the page also carries the topbar's)."""
    blocks = [b for b in re.findall(r"<script>(.*?)</script>", page, re.S)
              if "orch-form" in b]
    assert len(blocks) == 1, f"expected exactly 1 orchestrate script, got {len(blocks)}"
    return blocks[0]


def _class_tokens(page: str) -> set[str]:
    """Every class token on the page, markup *and* JS row template.

    The chair row is built in JS from single-quoted strings holding
    ``class="seat-tool"`` and friends, so one regex over the whole page covers
    both — which is what we want: ``row.querySelector('.seat-tool')`` is
    unguarded, and renaming the class in the template alone would throw.
    """
    tokens: set[str] = set()
    for value in re.findall(r'class="([^"]*)"', page):
        tokens.update(value.split())
    # …and the ones the script assigns rather than writes into a template:
    # `row.className = 'orch-seat'`, `classList.add('has-custom')`.
    for value in re.findall(r"className\s*=\s*'([^']*)'", page):
        tokens.update(value.split())
    tokens.update(re.findall(r"classList\.(?:add|toggle|remove)\('([^']+)'", page))
    return tokens


class _Containment(HTMLParser):
    """Records, for each element carrying ``wanted``, its ancestor ids."""

    def __init__(self, wanted: str) -> None:
        super().__init__(convert_charrefs=True)
        self._wanted = wanted
        self._stack: list[tuple[str, str | None]] = []
        self.hits: list[tuple[str, ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if self._wanted in (attr.get("class") or "").split():
            self.hits.append(tuple(i for _, i in self._stack if i))
        if tag not in _VOID_TAGS:
            self._stack.append((tag, attr.get("id")))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                return


# ---------------------------------------------------------------------------
# 1. Every lookup resolves
# ---------------------------------------------------------------------------

def test_every_getelementbyid_in_the_script_resolves() -> None:
    """A renamed id makes the script silently no-op — the markup still renders."""
    for conv_type, page in _pages().items():
        script = _script(page)
        ids = set(re.findall(r"getElementById\('([^']+)'\)", script))
        assert ids, "no id lookups found — did the script move?"
        present = set(re.findall(r'id="([^"]+)"', page))
        missing = sorted(ids - present)
        assert not missing, \
            f"/orchestrate?type={conv_type}: script looks up ids with no markup: {missing}"


def test_every_root_scoped_name_lookup_resolves() -> None:
    """``form.querySelector('input[name=x]')`` needs an ``name="x"`` control."""
    for conv_type, page in _pages().items():
        script = _script(page)
        names = set(re.findall(
            r"(?:document|form)\.querySelector(?:All)?\("
            r"'(?:input|select|textarea|button)\[name=([A-Za-z_]+)\]'\)",
            script,
        ))
        assert names, "no [name=…] lookups found — did the script move?"
        present = set(re.findall(r'name="([^"]+)"', page))
        missing = sorted(names - present - set(_CONDITIONAL_CONTROLS))
        assert not missing, \
            f"/orchestrate?type={conv_type}: script reads controls that aren't " \
            f"rendered: {missing}. If one is deliberately conditional, add it to " \
            f"_CONDITIONAL_CONTROLS with the reason."


def test_conditional_controls_are_null_guarded() -> None:
    """A control the renderer may omit must never be dereferenced bare.

    ``deliver_locally`` is absent on every machine without config/delivery.json,
    which is the default — so an unguarded ``deliverToggle.checked`` would throw
    on the *common* configuration, not a rare one.
    """
    script = _script(_page())
    for name, why in _CONDITIONAL_CONTROLS.items():
        const = re.search(
            r"const\s+(\w+)\s*=\s*form\.querySelector\("
            r"'(?:input|select|textarea)\[name=" + re.escape(name) + r"\]'\)",
            script,
        )
        assert const, f"{name} is listed as conditional but nothing looks it up"
        var = const.group(1)
        uses = re.findall(rf"\b{re.escape(var)}\s*(\.|&&|\))", script)
        derefs = [u for u in uses if u == "."]
        # Every property read must sit behind a `var &&` / `if (var)` guard on
        # the same line; cheapest check that holds: no line dereferences it
        # without naming it as a truthiness test first.
        for line in script.splitlines():
            if f"{var}." not in line:
                continue
            guarded = re.search(rf"(if\s*\(\s*{re.escape(var)}\b|{re.escape(var)}\s*&&)", line)
            assert guarded, \
                f"{var} ({name}: {why}) is dereferenced unguarded: {line.strip()!r}"
        assert derefs, f"{var} is never used — drop it or the allowlist entry"


# ---------------------------------------------------------------------------
# 2. Every class selector resolves
# ---------------------------------------------------------------------------

def test_every_class_selector_in_the_script_exists() -> None:
    """Covers the JS-built chair row too — its classes live in the template."""
    for conv_type, page in _pages().items():
        script = _script(page)
        classes = set(re.findall(
            r"querySelector(?:All)?\('\.([A-Za-z0-9_-]+)'\)", script))
        assert classes, "no class lookups found — did the script move?"
        missing = sorted(classes - _class_tokens(page))
        assert not missing, \
            f"/orchestrate?type={conv_type}: script queries classes that exist " \
            f"nowhere in the page or the row template: {missing}"


# ---------------------------------------------------------------------------
# 3 + 4. Bulk queries stay inside their own section
# ---------------------------------------------------------------------------

def test_no_bulk_query_runs_at_document_scope() -> None:
    """The shape of the bug: a bulk query reaching past the section it belongs to.

    Every ``querySelectorAll`` in this script is rooted at ``form`` (radio/preset
    collections), at a section container (``seatsBox``, ``extraRows``) or at a
    row. A ``document.querySelectorAll`` is how a selector silently acquires
    another section's rows, so it is refused outright.
    """
    script = _script(_page())
    assert "document.querySelectorAll" not in script, \
        "document.querySelectorAll in the /orchestrate script — scope it to the " \
        "section container instead (that is how the host seat picker shipped hidden)"


def test_bulk_hidden_classes_stay_inside_their_own_container() -> None:
    """``presetCards`` is collected at *form* scope and every card is hidden by
    ``updatePresets()``. Nothing outside the preset grid may carry the class, or
    the next section to borrow it disappears without a test noticing."""
    for conv_type, page in _pages().items():
        for cls, container in _BULK_HIDDEN_CLASSES.items():
            parser = _Containment(cls)
            parser.feed(page)
            assert parser.hits, \
                f"/orchestrate?type={conv_type}: nothing carries .{cls} — stale table?"
            strays = [h for h in parser.hits if container not in h]
            assert not strays, (
                f"/orchestrate?type={conv_type}: .{cls} is bulk-hidden by the "
                f"script but {len(strays)} element(s) carrying it sit outside "
                f"#{container} — they will be hidden too."
            )


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
