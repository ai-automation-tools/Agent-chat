"""Settings: the notification sink, the delivery sinks, and the tab shell.

Standalone-runnable **and** pytest-compatible, like every suite here::

    .\\.venv\\Scripts\\python.exe tests\\test_notifications.py

The transport tests run against a real ``http.server`` on a loopback port
rather than a mocked ``urlopen``. The thing under test is what actually goes
over the wire — body mode, header templating, the ntfy-shaped URL — and a mock
would assert that we called a function we wrote, which proves nothing about
whether ntfy would accept it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

_TMP = tempfile.mkdtemp(prefix="agent-chat-notify-")
os.environ["AGENT_CHAT_DELIVERY_CONFIG"] = str(Path(_TMP) / "delivery.json")
os.environ["AGENT_CHAT_DB"] = str(Path(_TMP) / "chat.db")

from orchestrator import delivery  # noqa: E402
from web.api import delivery_settings as dl  # noqa: E402
from web.api import notifications as api  # noqa: E402


# ---------------------------------------------------------------------------
# A capturing HTTP endpoint — the stand-in for ntfy / Discord / a webhook
# ---------------------------------------------------------------------------

class _Capture(BaseHTTPRequestHandler):
    received: list[dict] = []
    status = 200

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        length = int(self.headers.get("Content-Length") or 0)
        _Capture.received.append({
            "path": self.path,
            "body": self.rfile.read(length).decode("utf-8"),
            "headers": {k.lower(): v for k, v in self.headers.items()},
        })
        self.send_response(_Capture.status)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args) -> None:  # keep the test output clean
        pass


def _serve() -> tuple[HTTPServer, str]:
    srv = HTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _reset_config() -> None:
    path = delivery.config_path()
    if path.exists():
        path.unlink()


def _write_config(cfg: dict) -> None:
    path = delivery.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Template filling
# ---------------------------------------------------------------------------

def test_template_substitutes_known_fields():
    out = delivery.fill_template("[{event}] #{conversation_id} {topic}",
                                 {"event": "complete", "conversation_id": 7,
                                  "topic": "AI jobs"})
    assert out == "[complete] #7 AI jobs", out


def test_unknown_placeholder_renders_empty_rather_than_raising():
    """`quiet_seconds` exists on a stalled payload and nowhere else. A template
    naming it must not blow up on the three events that lack it."""
    out = delivery.fill_template("a{nope}b", {"event": "complete"})
    assert out == "ab", out


def test_malformed_template_falls_back_to_the_literal():
    out = delivery.fill_template("50% { unbalanced", {"event": "x"})
    assert "unbalanced" in out, out


def test_summary_line_reads_differently_for_a_stall():
    done = delivery.summary_line(
        {"conversation_id": 3, "topic": "T", "status": "complete"}, "complete")
    stuck = delivery.summary_line(
        {"conversation_id": 3, "topic": "T", "quiet_seconds": 900,
         "current_turn": "codex"}, "stalled")
    assert "complete" in done, done
    assert "quiet 15 min" in stuck and "codex" in stuck, stuck


# ---------------------------------------------------------------------------
# The four events
# ---------------------------------------------------------------------------

def test_started_is_a_delivery_event():
    assert "started" in delivery.EVENTS
    assert delivery.EVENTS == ("started", "result", "complete", "stalled")


def test_started_is_not_in_the_default_event_list():
    """At seed time the bundle has no messages. A folder sink that inherited
    `started` would write an empty transcript over nothing."""
    assert "started" not in (delivery.STARTER_CONFIG.get("events") or [])


def test_seeding_fires_the_started_event():
    """The fourth deliver() call site. Proven by seeding for real and watching
    the sink receive it, not by grepping for the call."""
    srv, base = _serve()
    _Capture.received.clear()
    try:
        _write_config({
            "enabled": True,
            "sinks": [{"type": "webhook", "enabled": True,
                       "url": f"{base}/hook", "events": ["started"]}],
        })
        from orchestrator import seeding
        res = seeding.seed_conversation(
            db_path=os.environ["AGENT_CHAT_DB"],
            topic="Notification smoke test",
            participants=["claude-code", "codex"],
            max_turns=2,
            mode="turns",
        )
        assert _Capture.received, "seeding did not fire the started event"
        body = json.loads(_Capture.received[-1]["body"])
        assert body["event"] == "started", body
        assert body["conversation_id"] == res.conversation_id, body
        assert body["message_count"] == 0, body
    finally:
        srv.shutdown()
        _reset_config()


def test_a_broken_sink_cannot_fail_a_seed():
    """deliver() never raises, so a dead notification endpoint costs the
    message and never the conversation."""
    _write_config({
        "enabled": True,
        "sinks": [{"type": "webhook", "enabled": True,
                   # Nothing listens here.
                   "url": "http://127.0.0.1:9/nope", "events": ["started"],
                   "timeout": 1}],
    })
    try:
        from orchestrator import seeding
        res = seeding.seed_conversation(
            db_path=os.environ["AGENT_CHAT_DB"],
            topic="Seed survives a dead webhook",
            participants=["claude-code", "codex"],
            max_turns=2,
            mode="turns",
        )
        assert res.conversation_id > 0
    finally:
        _reset_config()


# ---------------------------------------------------------------------------
# Transport — what actually goes over the wire
# ---------------------------------------------------------------------------

def test_ntfy_posts_a_text_body_with_templated_headers():
    srv, base = _serve()
    _Capture.received.clear()
    try:
        sink = api._build_sink("ntfy", "my-topic", base, ["complete"], True)
        assert sink["url"] == f"{base}/my-topic", sink["url"]
        delivery.send_test(sink, "complete")
        got = _Capture.received[-1]
        assert got["path"] == "/my-topic", got["path"]
        assert got["headers"]["content-type"].startswith("text/plain"), got["headers"]
        # The title is templated per event, which is the whole point of it.
        assert got["headers"]["x-title"] == "Agent-Chat: complete", got["headers"]
        # A text body, not JSON — ntfy's topic-URL mode would show `{"event":…}`
        # verbatim on the lock screen otherwise.
        assert not got["body"].lstrip().startswith("{"), got["body"]
        assert "Test notification from Agent-Chat" in got["body"], got["body"]
    finally:
        srv.shutdown()


def test_ntfy_participants_render_joined_not_as_a_python_list():
    srv, base = _serve()
    _Capture.received.clear()
    try:
        delivery.send_test(api._build_sink("ntfy", "t", base, ["complete"], True))
        body = _Capture.received[-1]["body"]
        assert "claude-code, codex" in body, body
        assert "['" not in body, body
    finally:
        srv.shutdown()


def test_discord_and_slack_differ_only_by_one_key():
    srv, base = _serve()
    _Capture.received.clear()
    try:
        for service, key in (("discord", "content"), ("slack", "text")):
            sink = api._build_sink(service, "https://example.invalid/hook",
                                   "", ["complete"], True)
            assert sink["text_key"] == key, sink
            sink["url"] = f"{base}/{service}"          # retarget at the stub
            delivery.send_test(sink, "complete")
            body = json.loads(_Capture.received[-1]["body"])
            assert key in body, body
            assert body["conversation_id"] == 0, body
    finally:
        srv.shutdown()


def test_raw_webhook_sends_the_full_json_payload():
    srv, base = _serve()
    _Capture.received.clear()
    try:
        delivery.send_test(api._build_sink("webhook", f"{base}/raw", "",
                                           ["complete"], True))
        body = json.loads(_Capture.received[-1]["body"])
        for key in ("event", "conversation_id", "topic", "status", "participants"):
            assert key in body, (key, body)
    finally:
        srv.shutdown()


def test_send_test_raises_so_the_button_can_report_failure():
    """deliver() swallows; send_test() must not — a human is waiting for an
    answer and 'it worked' would be a lie."""
    sink = api._build_sink("webhook", "http://127.0.0.1:9/nope", "",
                           ["complete"], True)
    sink["timeout"] = 1
    try:
        delivery.send_test(sink)
    except Exception:
        return
    raise AssertionError("send_test() swallowed a failure")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_an_ntfy_topic_with_a_slash_is_refused():
    """A slash would silently retarget the POST at a different topic — the
    failure where you believe you are covered and are not."""
    for bad in ("a/b", "../other", "with space", ""):
        try:
            api._build_sink("ntfy", bad, "https://ntfy.sh", ["complete"], True)
        except ValueError:
            continue
        raise AssertionError(f"accepted bad ntfy topic {bad!r}")


def test_a_non_https_discord_url_is_refused():
    try:
        api._build_sink("discord", "http://example.com/x", "", ["complete"], True)
    except ValueError:
        return
    raise AssertionError("accepted a non-https Discord webhook")


def test_unknown_events_are_refused():
    try:
        api._parse({"service": "ntfy", "target": "t", "events": ["explode"]})
    except ValueError as e:
        assert "explode" in str(e), e
        return
    raise AssertionError("accepted an unknown event")


def test_empty_event_list_is_refused():
    try:
        api._parse({"service": "ntfy", "target": "t", "events": []})
    except ValueError:
        return
    raise AssertionError("accepted a notification config that notifies nothing")


# ---------------------------------------------------------------------------
# Config merge — the part that can lose an operator's work
# ---------------------------------------------------------------------------

def test_saving_preserves_hand_written_sinks():
    _write_config({
        "enabled": True,
        "sinks": [
            {"type": "folder", "enabled": True, "path": "deliveries",
             "scope": "opt-in"},
            {"type": "command", "enabled": False, "argv": ["echo", "{dir}"]},
        ],
    })
    try:
        cfg = delivery.load_config()
        sinks = [s for s in cfg["sinks"]
                 if s.get("id") != delivery.NOTIFY_SINK_ID]
        sinks.append(api._build_sink("ntfy", "t", "https://ntfy.sh",
                                     ["complete"], True))
        cfg["sinks"] = sinks
        _write_config(cfg)

        after = delivery.load_config()
        kinds = [s["type"] for s in after["sinks"]]
        assert kinds.count("folder") == 1, kinds
        assert kinds.count("command") == 1, kinds
        assert after["sinks"][0]["path"] == "deliveries", after["sinks"][0]
    finally:
        _reset_config()


def test_resaving_replaces_rather_than_duplicates_the_notify_sink():
    _reset_config()
    try:
        cfg: dict = {"enabled": True, "sinks": []}
        for topic in ("first", "second", "third"):
            cfg["sinks"] = [s for s in cfg["sinks"]
                            if s.get("id") != delivery.NOTIFY_SINK_ID]
            cfg["sinks"].append(
                api._build_sink("ntfy", topic, "https://ntfy.sh", ["complete"], True))
        _write_config(cfg)
        after = delivery.load_config()
        notify = [s for s in after["sinks"]
                  if s.get("id") == delivery.NOTIFY_SINK_ID]
        assert len(notify) == 1, after["sinks"]
        assert notify[0]["url"].endswith("/third"), notify[0]["url"]
    finally:
        _reset_config()


def test_the_notify_sink_does_not_force_the_orchestrate_copy_checkbox():
    """The /orchestrate box means 'save a copy of the bundle'. A notification
    sink is scoped 'all' by design; counting it there would tell the operator
    every run is being written to disk because they asked to be pinged."""
    _write_config({
        "enabled": True,
        "sinks": [api._build_sink("ntfy", "t", "https://ntfy.sh",
                                  ["complete"], True)],
    })
    try:
        offered = delivery.optin_offered()
        assert offered["available"] is False, offered
        assert offered["forced"] is False, offered
    finally:
        _reset_config()


def test_round_trip_through_the_state_reader():
    """What is saved must come back as what the form shows, or editing an
    existing config silently resets fields the operator can't see."""
    _reset_config()
    try:
        _write_config({
            "enabled": True,
            "sinks": [api._build_sink("ntfy", "my-topic", "https://ntfy.example",
                                      ["complete", "stalled", "started"], True)],
        })
        state = api._state(delivery.load_config())
        assert state["service"] == "ntfy", state
        assert state["target"] == "my-topic", state
        assert state["server"] == "https://ntfy.example", state
        assert state["events"] == ["complete", "stalled", "started"], state
        assert state["enabled"] is True and state["delivery_enabled"] is True, state
    finally:
        _reset_config()


def test_state_recognises_a_hand_written_sink_without_a_service_tag():
    """An older config, or one edited by hand, has no `service` key. Guessing
    from the URL beats rendering the wrong form."""
    _write_config({
        "enabled": True,
        "sinks": [{"type": "webhook", "id": delivery.NOTIFY_SINK_ID,
                   "enabled": True, "url": "https://ntfy.sh/hand-written",
                   "events": ["complete"]}],
    })
    try:
        state = api._state(delivery.load_config())
        assert state["service"] == "ntfy", state
        assert state["target"] == "hand-written", state
    finally:
        _reset_config()


def test_every_service_builds_a_usable_sink():
    """Parity guard: a service added to SERVICES without a _build_sink branch
    would render a radio button that 400s on save."""
    targets = {
        "ntfy": "topic", "gotify": "TokenAbc",
        "discord": "https://discord.com/api/webhooks/1/x",
        "slack": "https://hooks.slack.com/services/x",
        "webhook": "http://127.0.0.1:5678/webhook/x",
    }
    assert set(targets) == set(api.SERVICES), set(api.SERVICES) ^ set(targets)
    for service, target in targets.items():
        sink = api._build_sink(service, target, "", ["complete"], True)
        assert sink["url"], service
        assert sink["id"] == delivery.NOTIFY_SINK_ID, service
        assert sink["scope"] == "all", service


# ---------------------------------------------------------------------------
# Rendering — the part `tests/` historically cannot see (it asserts on HTML
# strings, and this page's behaviour is in its JS). These check the values the
# JS is *seeded* with, which is where the defaults actually live.
# ---------------------------------------------------------------------------

def test_a_fresh_page_seeds_the_send_toggle_ON():
    """`enabled` is False before anything is configured — there is no sink to be
    enabled. Seeding the toggle from that hands a first-time operator a form
    that fills in, saves, and arms nothing. Found in a browser, not by a test:
    the markup was correct either way, the JS unticked it a frame later."""
    from web.render.notifications import _render_notifications
    _reset_config()
    html = _render_notifications(api._state(delivery.load_config()))
    assert '"enabled": true' in html, "fresh page seeds the send toggle OFF"


def test_a_disabled_saved_config_seeds_the_toggle_OFF():
    """The other half: once it IS configured, the toggle must reflect what was
    saved rather than snapping back on."""
    from web.render.notifications import _render_notifications
    _write_config({
        "enabled": True,
        "sinks": [api._build_sink("ntfy", "t", "https://ntfy.sh",
                                  ["complete"], False)],
    })
    try:
        html = _render_notifications(api._state(delivery.load_config()))
        assert '"enabled": false' in html, "a saved-but-off config renders as on"
        assert "Saved but not sending" in html, html[:0]
    finally:
        _reset_config()


def test_every_event_renders_a_checkbox():
    """A fifth event added to delivery.EVENTS without a row here would be
    saveable through the API and invisible on the page."""
    from web.render.notifications import _EVENT_ROWS, _render_notifications
    assert {e for e, _l, _d in _EVENT_ROWS} == set(delivery.EVENTS), _EVENT_ROWS
    _reset_config()
    html = _render_notifications(api._state(delivery.load_config()))
    for event in delivery.EVENTS:
        assert f'value="{event}"' in html, event


def test_the_hosted_page_offers_no_form():
    from web.render.notifications import _render_notifications_readonly
    html = _render_notifications_readonly()
    assert "Notifications come from your own machine" in html
    assert "nt-form" not in html, "the hosted explainer shipped a form"


# ---------------------------------------------------------------------------
# Delivery tab — the folder and command sinks, which had no UI before
# ---------------------------------------------------------------------------

def test_delivery_tab_owns_the_first_sink_of_each_type():
    """Folder and command sinks predate any UI, so the ones already on disk
    carry no id. Ownership is by position; a second sink of a type is left
    alone and reported instead of being silently rewritten."""
    _write_config({"enabled": True, "sinks": [
        {"type": "folder", "enabled": True, "path": "first"},
        {"type": "folder", "enabled": False, "path": "second"},
        {"type": "command", "enabled": False, "argv": ["echo", "hi"]},
    ]})
    try:
        cfg = delivery.load_config()
        idx, sink = dl._first(cfg, "folder")
        assert idx == 0 and sink["path"] == "first", (idx, sink)
        assert dl._extras(cfg) == ["folder"], dl._extras(cfg)
    finally:
        _reset_config()


def test_the_delivery_tab_never_claims_the_notification_sink():
    """Two pages writing one sink is how a config loses an operator's work."""
    _write_config({"enabled": True, "sinks": [
        api._build_sink("ntfy", "t", "https://ntfy.sh", ["complete"], True),
    ]})
    try:
        cfg = delivery.load_config()
        assert dl._first(cfg, "folder") == (None, None)
        assert "webhook" not in dl.MANAGED_TYPES, dl.MANAGED_TYPES
    finally:
        _reset_config()


def test_saving_delivery_preserves_unknown_keys():
    """A config may carry a key a later version added. A settings page must not
    be a way to quietly delete it."""
    _write_config({"enabled": True, "sinks": [
        {"type": "folder", "enabled": True, "path": "deliveries",
         "some_future_key": 42},
    ]})
    try:
        cfg = delivery.load_config()
        _idx, existing = dl._first(cfg, "folder")
        folder, _cmd = dl._build({"folder": {"enabled": True, "path": "deliveries",
                                             "events": ["complete"], "scope": "all"},
                                  "command": {"present": False}})
        merged = dict(existing)
        merged.update(folder)
        assert merged["some_future_key"] == 42, merged
    finally:
        _reset_config()


def test_a_command_with_a_quoted_path_stays_one_argument():
    """argv is a list in the file and one line in the form. A naive split would
    turn a quoted Program Files path into two arguments."""
    _folder, command = dl._build({
        "folder": {"enabled": True, "path": "deliveries", "events": ["complete"],
                   "scope": "all"},
        "command": {"enabled": True, "events": ["complete"],
                    "argv": '"C:/Program Files/tool.exe" --dir {dir}'},
    })
    assert command["argv"] == ["C:/Program Files/tool.exe", "--dir", "{dir}"], command


def test_the_command_sink_cannot_be_enabled_without_the_folder_sink():
    """It acts on files the folder sink wrote. Enabled alone it can only ever
    log an error, at delivery time, where nobody is watching."""
    try:
        dl._build({
            "folder": {"enabled": False, "path": "deliveries",
                       "events": ["complete"], "scope": "all"},
            "command": {"enabled": True, "argv": "echo hi", "events": ["complete"]},
        })
    except ValueError as e:
        assert "folder sink" in str(e), e
        return
    raise AssertionError("accepted a command sink with no folder sink")


def test_delivery_rejects_bad_input():
    base = {"enabled": True, "path": "d", "events": ["complete"], "scope": "all"}
    cases = [
        ({"folder": {**base, "path": ""}, "command": {"present": False}},
         "empty folder path"),
        ({"folder": {**base, "scope": "sometimes"}, "command": {"present": False}},
         "bogus scope"),
        ({"folder": {**base, "events": []}, "command": {"present": False}},
         "no events"),
        ({"folder": {**base, "events": ["explode"]}, "command": {"present": False}},
         "unknown event"),
        ({"folder": base,
          "command": {"enabled": True, "argv": "", "events": ["complete"]}},
         "enabled command with no command"),
        ({"folder": base,
          "command": {"enabled": False, "argv": "x", "timeout": 0,
                      "events": ["complete"]}},
         "zero timeout"),
    ]
    for payload, why in cases:
        try:
            dl._build(payload)
        except ValueError:
            continue
        raise AssertionError(f"accepted {why}")


def test_delivery_state_round_trips():
    _write_config({"enabled": True, "sinks": [
        {"type": "folder", "enabled": True, "path": "out", "scope": "opt-in",
         "include_result": True, "events": ["complete", "result"]},
        {"type": "command", "enabled": False, "argv": ["pwsh", "-c", "echo {dir}"],
         "timeout": 60, "events": ["complete"]},
    ]})
    try:
        s = dl._state(delivery.load_config())
        assert s["folder"] == {"configured": True, "enabled": True, "path": "out",
                               "include_result": True, "scope": "opt-in",
                               "events": ["complete", "result"]}, s["folder"]
        assert s["command"]["argv"] == "pwsh -c 'echo {dir}'", s["command"]["argv"]
        assert s["command"]["timeout"] == 60, s["command"]
    finally:
        _reset_config()


# ---------------------------------------------------------------------------
# The settings shell
# ---------------------------------------------------------------------------

def test_every_tab_renders_and_an_unknown_tab_falls_back():
    from web.render import settings as st
    assert st.resolve_tab(None) == st.DEFAULT_TAB
    assert st.resolve_tab("notifications") == "notifications"
    assert st.resolve_tab("nonsense") == st.DEFAULT_TAB, "a mistyped tab should not 404"
    for slug, _label, _desc in st.TABS:
        html = st._render_settings_readonly(slug)
        assert 'class="set-tab on"' in html, slug
        assert f'href="/settings?tab={slug}"' in html, slug


def test_every_legacy_path_points_at_a_real_tab():
    from web.render import settings as st
    slugs = {t[0] for t in st.TABS}
    for path, tab in st.LEGACY_PATHS.items():
        assert tab in slugs, (path, tab)


def test_the_delivery_tab_offers_every_event():
    from web.render.settings import _delivery_body
    _reset_config()
    html = _delivery_body(dl._state(delivery.load_config()))
    for event in delivery.EVENTS:
        assert f'value="{event}"' in html, event


# ---------------------------------------------------------------------------

def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — this IS the reporter
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
