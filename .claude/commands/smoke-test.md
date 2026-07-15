# Smoke-test Agent-Chat

Run the project's validation checklist and report what passed, what failed, and
what you skipped. Scope: **$ARGUMENTS** (default: everything below).

Always invoke the venv interpreter explicitly — never rely on activation state.

## Instructions

1. **Server imports cleanly.** stdout is reserved for the MCP JSON-RPC stream, so
   an import-time `print()` is a real bug:
   ```powershell
   .\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import agent_chat_mcp"
   ```

2. **Web UI imports cleanly**, including the re-exports the tests rely on:
   ```powershell
   .\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import web_ui; [getattr(web_ui, n) for n in ('db_init','set_db_path','ReadOnlyMiddleware','BasicAuthMiddleware','render_markdown')]"
   ```

3. **Test suites.** Each is pytest-compatible *and* standalone-runnable; run them
   standalone so no test dep is needed:
   ```powershell
   .\.venv\Scripts\python.exe tests\test_web_readonly.py
   .\.venv\Scripts\python.exe tests\test_inspect_tail.py
   .\.venv\Scripts\python.exe tests\test_topics.py
   ```
   Run every file in `tests/` — glob it rather than trusting this list to be
   current.

4. **JSON validity** of any `.mcp.json` / MCP config touched by the current diff
   (silent output = valid):
   ```powershell
   .\.venv\Scripts\python.exe -m json.tool path\to\.mcp.json
   ```
   Check `git status` / `git diff --name-only` to find which ones actually
   changed; don't validate the whole tree by default.

5. **Web UI responds** (only if it's expected to be up — it normally is, on
   `127.0.0.1:8765`):
   ```powershell
   curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8765/conversations
   ```
   If it's down, say so; start it only if the user asks. There is no hot reload,
   so a running instance won't reflect uncommitted changes until restarted.

6. **End-to-end** (only when asked, or when the change touches turn-taking or the
   DB): seed a `--max-turns 2` conversation against a **temp** DB path, run the
   CLIs, and confirm the row reaches `status='complete'`. Never mock SQLite — the
   WAL multi-process behaviour is the thing under test. Never point a throwaway
   run at `db/chat.db`.

## Reporting

Lead with the verdict: what passed, and the first real failure if there is one.
Quote actual output for failures — don't paraphrase. If you skipped a step
(e.g. no config changed, UI not running), say which and why. A test that fails is
a finding, not something to work around; never edit a test to make it pass
without flagging that's what you're doing.
