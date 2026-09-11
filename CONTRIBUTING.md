# Contributing to Agent-Chat

Thanks for taking a look.

Agent-Chat is **experimental and pre-1.0**. It is a local MCP conversation bus for CLI
agents, and it is developed against a single machine's worth of real use — so the most
valuable contributions are usually the ones that come from running it, not from reading it.

## Before you change code

Read these first:

1. [`README.md`](README.md) — what it is and how to run it
2. [`CLAUDE.md`](CLAUDE.md) — the project instruction file: conventions, invariants, the
   things that will bite you
3. [`docs/Roadmap.md`](docs/Roadmap.md) — the living plan
4. [`docs/README.md`](docs/README.md) — the documentation map

If your change affects runtime behavior, docs, or roadmap status, update the matching docs
in the same PR.

## Setup

```powershell
git clone https://github.com/ai-automation-tools/Agent-chat.git
cd Agent-chat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Always invoke the venv interpreter explicitly rather than relying on activation. Full
walkthrough: [`docs/Setup/INITIAL_SETUP.md`](docs/Setup/INITIAL_SETUP.md).

## Tests

Every file in [`tests/`](tests/) is **pytest-compatible *and* standalone-runnable** — that is
deliberate, so no test dependency has to be pinned. The zero-dependency path is what CI runs:

```powershell
Get-ChildItem tests/test_*.py | ForEach-Object { .\.venv\Scripts\python.exe $_.FullName }
```

Each suite prints its own `N/N passed` line and exits non-zero on failure. If you have
pytest installed, `.\.venv\Scripts\python.exe -m pytest tests\` works too. Every suite
should pass before you open a PR.

Add cases for the behavior you changed — `tests/` is organised one file per surface. Keep
new suites standalone and named `test_*.py`: CI globs the directory rather than listing
files, precisely so a new suite can't be silently left out.

## The rules that are easy to break

These are invariants, not preferences. Each one has cost someone a debugging session:

- **Never `print()` to stdout in `src/agent_chat_mcp.py`.** Stdout carries the MCP JSON-RPC
  stream and any stray write corrupts it. Log to `sys.stderr`.
- **SQLite runs in WAL mode, and that is mandatory** — multiple per-CLI MCP processes write
  the same file. Keep `isolation_level=None` and `timeout=10.0`.
- **The generated files are generated.** The five per-seat role docs under `agents/CLIs/`
  come from [`scripts/setup/gen_agent_role_docs.py`](scripts/setup/gen_agent_role_docs.py).
  Edit the template in the script and re-run it; never edit the output.
- **Nothing tracked may hardcode a machine path.** Scripts resolve their own location; docs
  use the `<repo>` placeholder. A path that only works on one machine ships to every clone.
- **The local web UI binds `127.0.0.1`.** No `0.0.0.0` bind without an auth story — see
  [`SECURITY.md`](SECURITY.md).
- **Schema changes are a multi-file job.** The schema is the inline `SCHEMA` constant in
  `agent_chat_mcp.py`; changing it means bumping that constant, updating
  `start_conversation.py`, `inspect_conversations.py` and `web_ui.py`, and logging it in
  [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

## Pull requests

- Branch off `main`, keep changes small and focused.
- Imperative-mood commit subjects, with a body when the *why* isn't obvious from the diff.
  This repo does **not** use Conventional Commits — match the existing log.
- Never commit `.env`, `.venv/`, `__pycache__/`, `db/*.db*`, or anything under `docs/Local/`.
- Say what you ran. "All 14 suites pass (356 cases)" is worth more than "tested".

## Reporting things

- **Security vulnerabilities:** privately, via the Security tab — see
  [`SECURITY.md`](SECURITY.md). Not a public issue.
- **Bugs and ideas:** open an issue. If it involves a specific CLI, say which one and which
  version — the per-CLI config surfaces differ more than you would expect.
