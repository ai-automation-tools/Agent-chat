<h1 align="center">🧪 Tests</h1>

<p align="center">
  <em>Five suites, no pinned test dependency. Every file is pytest-compatible<br>
  <b>and</b> standalone-runnable, against an isolated temp database.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Suites-5-10b981?style=for-the-badge&labelColor=09090b" alt="5 suites">
  <img src="https://img.shields.io/badge/Test_deps-none_pinned-71717a?style=for-the-badge&labelColor=09090b" alt="no pinned test deps">
  <img src="https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=for-the-badge&labelColor=09090b&logo=githubactions&logoColor=white" alt="GitHub Actions">
</p>

---

## ▶️ Running them

```powershell
# Whole suite, if pytest is available
.\.venv\Scripts\python.exe -m pytest tests\

# Or any single file standalone — no pytest required
.\.venv\Scripts\python.exe tests\test_web_readonly.py
```

The dual-mode design is deliberate: it keeps `requirements.txt` free of a test
dependency while still letting CI run the whole tree. The [`/smoke-test`](../.claude/commands/smoke-test.md)
command walks the full manual checklist on top of these.

## 📋 The suites

| Suite | Covers |
|:---|:---|
| [**`test_web_readonly.py`**](test_web_readonly.py) | Basic-auth and read-only middleware, and the orchestrate guard — the paths that keep the hosted mirror from accepting browser mutations. **Add a case here whenever you add a write route.** |
| [**`test_battleground.py`**](test_battleground.py) | The arena bridge: capture scrubbing and post-id merge, the verdict gate, extension CORS narrowness, schema parity, and the MCP loop. Also **pins `KNOWN_SITES` against the adapter list** so a new site adapter can't be half-registered. |
| [**`test_topics.py`**](test_topics.py) | Topic → logo classification and the tie-break ordering in `web/topics.py`. |
| [**`test_model_personas.py`**](test_model_personas.py) | The `AI-Models` cards, the reserved-group casting guard (a random debate must never field "Claude Code" against a celebrity), and the Cast fallback. |
| [**`test_inspect_tail.py`**](test_inspect_tail.py) | The `inspect_conversations tail` completion guard. |

## 📐 Conventions

- **Isolated temp DB per suite.** Never point a test at `db/chat.db`.
- **Do not mock SQLite.** The WAL multi-process behaviour is the thing under
  test — mocking it tests nothing.
- **`pytest` fixtures** for new suites, with the same tmp-DB principle.
- Tests import the `web_ui` re-exports (`ReadOnlyMiddleware`, `db_init`, …) —
  keep those working when moving code inside [`src/web/`](../src/README.md).

## 🕳️ Known gaps

Tracked in the Roadmap's *Expand the test suite* row — suggested next suites:
`test_mcp_turns.py` (turn rotation, out-of-turn rejection, `max_turns`,
`done`/`blocked`), `test_web_routes.py` (export, stop/delete, SSE),
`test_sync.py` (conflict + delete propagation), `test_personas.py`
(parser/import, malformed frontmatter, zip limits).

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../src/README.md`](../src/README.md) | The modules under test and the invariants they must hold. |
| [`../docs/Roadmap.md`](../docs/Roadmap.md) | The coverage-expansion row. |
| [`../docs/App/README.md`](../docs/App/README.md) | Feature reference for the behaviour being pinned. |

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../src/README.md">Source</a></sub>
</p>
