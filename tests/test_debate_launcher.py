r"""Tests for ``scripts/debate.ps1 -Format podcast`` — the one-command podcast launcher.

The launcher is PowerShell, so these cases run the real script with ``-DryRun``
(it casts, plans seats and prints the seed command, but seeds nothing and opens
no window) against an isolated temp DB, then assert on what it printed. The
last case seeds through ``start_conversation.py`` with the same arguments the
script builds, so the flags it prints are flags the seeder accepts.

Skips (and says so) when ``pwsh`` or the project venv is missing: the script
refuses to run without ``.venv\Scripts\python.exe``, and CI installs into the
runner's own Python.

Runs under pytest *or* standalone with the project venv (no pytest needed):

    .\.venv\Scripts\python.exe tests\test_debate_launcher.py

Never touches the real ``db/chat.db``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "debate.ps1"
_VENV_PY = _ROOT / ".venv" / "Scripts" / "python.exe"
_PWSH = shutil.which("pwsh")

_ENV: dict[str, str] | None = None


def _skip_reason() -> str | None:
    if not _PWSH:
        return "pwsh not on PATH"
    if not _VENV_PY.exists():
        return f"no venv at {_VENV_PY} (debate.ps1 requires it)"
    return None


if __name__ != "__main__" and _skip_reason():  # under pytest, skip like the runner does
    import pytest

    pytest.skip(_skip_reason(), allow_module_level=True)


def _env() -> dict[str, str]:
    """A temp DB holding one host card and four castable guests, and a CLI
    declaration naming all four seat-1 tools so a 4-seat plan needs no seat-2
    folder."""
    global _ENV
    if _ENV is None:
        tmp = Path(tempfile.mkdtemp(prefix="agentchat-launcher-"))
        cli_cfg = tmp / "available-clis.json"
        cli_cfg.write_text(json.dumps(
            {"available": ["claude-code", "antigravity", "codex", "opencode"]}),
            encoding="utf-8")
        env = {**os.environ,
               "AGENT_CHAT_DB": str(tmp / "chat.db"),
               "AGENT_CHAT_CLI_CONFIG": str(cli_cfg)}
        os.environ["AGENT_CHAT_DB"] = env["AGENT_CHAT_DB"]   # personas resolves it per call
        src = str(_ROOT / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from orchestrator import personas

        personas.create_persona(name="Test Host", body="Asks short questions.",
                                group="Debate-Hosts")
        for n in range(1, 5):
            personas.create_persona(name=f"Test Guest {n}", body=f"Guest {n}.",
                                    group="Launcher-Test")
        _ENV = env
    return _ENV


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(_SCRIPT), "-DryRun", *args],
        env=_env(), capture_output=True, text=True, encoding="utf-8", timeout=120)


def _seed_line(out: str) -> str:
    m = re.search(r"would seed:\s+start\.ps1 (.+)", out)
    assert m, out
    return m.group(1)


def test_podcast_seats_a_host_first_then_the_guests() -> None:
    r = _run("-Format", "podcast", "-Topic", "How do lighthouses work?", "-Agents", "2")
    assert r.returncode == 0, r.stdout + r.stderr
    seed = _seed_line(r.stdout)
    assert "--preset podcast" in seed, seed
    assert "--participants claude-code,antigravity,codex" in seed, seed
    assert "--first claude-code" in seed, seed
    assert "--type podcast --host claude-code" in seed, seed
    assert re.search(r"claude-code\s+<- Test Host \[host\]", r.stdout), r.stdout
    assert len(re.findall(r"<- .+ \[guest\]", r.stdout)) == 2, r.stdout


def test_podcast_draws_its_topic_and_guest_count_from_the_podcast_library() -> None:
    r = _run("-Format", "podcast")
    assert r.returncode == 0, r.stdout + r.stderr
    m = re.search(r"topic requests (\d+) guests", r.stdout)
    assert m, r.stdout
    guests = int(m.group(1))
    participants = re.search(r"--participants (\S+)", _seed_line(r.stdout)).group(1)
    assert len(participants.split(",")) == guests + 1, (guests, participants)
    title = re.search(r"Topic \(random of .*?\): (.+)", r.stdout).group(1).strip()
    library = (_ROOT / "docs" / "chat-topics" / "Podcast-Topics.md").read_text(encoding="utf-8")
    assert title in library, title


def test_podcast_guest_count_is_bounded() -> None:
    r = _run("-Format", "podcast", "-Topic", "x", "-Agents", "5")
    assert r.returncode != 0
    assert "guests count must be 1-4" in (r.stdout + r.stderr), r.stdout + r.stderr


def test_host_persona_is_podcast_only() -> None:
    r = _run("-Topic", "x", "-HostPersona", "anyone")
    assert r.returncode != 0
    assert "-HostPersona only applies" in (r.stdout + r.stderr), r.stdout + r.stderr


def test_debate_is_unchanged_by_default() -> None:
    r = _run("-Topic", "Is a hot dog a sandwich?", "-Agents", "2")
    assert r.returncode == 0, r.stdout + r.stderr
    seed = _seed_line(r.stdout)
    assert "--preset debate" in seed and "--type" not in seed, seed
    assert "[host]" not in r.stdout and "[guest]" not in r.stdout, r.stdout


def test_the_printed_podcast_flags_seed_a_podcast() -> None:
    db = Path(_env()["AGENT_CHAT_DB"])
    subprocess.run(
        [str(_VENV_PY), str(_ROOT / "src" / "start_conversation.py"), "--db-path", str(db),
         "--preset", "podcast", "--topic", "How do lighthouses work?",
         "--participants", "claude-code,antigravity,codex", "--first", "claude-code",
         "--type", "podcast", "--host", "claude-code"],
        env=_env(), check=True, capture_output=True)
    con = sqlite3.connect(db)
    try:
        conv_type, preset, roles = con.execute(
            "SELECT conv_type, preset, participant_roles FROM conversations "
            "ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        con.close()
    assert (conv_type, preset) == ("podcast", "podcast")
    assert json.loads(roles) == {"claude-code": "host", "antigravity": "guest", "codex": "guest"}


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

def _main() -> int:
    reason = _skip_reason()
    if reason:
        print(f"SKIP  test_debate_launcher: {reason}")
        return 0
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
