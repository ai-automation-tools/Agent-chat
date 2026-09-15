<h1 align="center">🧪 Tests</h1>

<p align="center">
  <em>Fifteen suites, no pinned test dependency. Every file is pytest-compatible<br>
  <b>and</b> standalone-runnable, against an isolated temp database.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Suites-15-10b981?style=for-the-badge&labelColor=09090b" alt="15 suites">
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
| [**`test_battleground.py`**](test_battleground.py) | The arena bridge: capture scrubbing and post-id merge, the verdict gate, extension CORS narrowness, schema parity, the MCP loop, and a grep keeping the panel's extension-API calls on the `ext` alias so the Firefox build keeps booting. Covers both ways to cast an arena — a registry card and a **typed-in custom card** (NULL slug, the double-cast 400, the slug clear on re-cast, and `get_arena` gating on `persona_body` rather than the slug). Also **pins `KNOWN_SITES` against the adapter list** so a new site adapter can't be half-registered, and covers the `/battleground` console — the list, the status filter, the verdict buttons tracking draft state, the hosted explainer, and the escaping of captured page content. |
| [**`test_availability.py`**](test_availability.py) | Which CLIs a machine has: the three declaration states (absent ≠ empty), declaration overriding detection in both directions, the `plan_seats` round-robin (**including the two-tool case that must not change**), the `/setup` page and its API, `/orchestrate` filtering, the hosted demo strip, the two-group nav rail, and **`CLI_BINARIES` ↔ `$Clis[…].Exe` parity** — detecting a CLI under a name we then fail to spawn is silent. |
| [**`test_topics.py`**](test_topics.py) | Topic → logo classification and the tie-break ordering in `web/topics.py`. |
| [**`test_model_personas.py`**](test_model_personas.py) | The `AI-Models` cards, the reserved-group casting guard (a random debate must never field "Claude Code" against a celebrity), and the Cast fallback. |
| [**`test_persona_avatars.py`**](test_persona_avatars.py) | Persona avatars: magic-byte validation (SVG stays out), the uploaded → file → silhouette resolution order, card↔image pairing on import, the "an edit must not delete the art" rule, and **persona column-list parity between `web/db.py` and `scripts/db_sync.py`** — a column the sidecar drops never reaches the mirror. |
| [**`test_conv_types.py`**](test_conv_types.py) | Conversation types: seat rules per type, the `conv_type` backfill, **schema-mirror parity across all three `SCHEMA` copies**, conversation column parity between `web/db.py` and `scripts/db_sync.py`, and the export's Type/Role rows. |
| [**`test_seats.py`**](test_seats.py) | The agent-id grammar (`codex-2`), per-seat config paths, Codex's `CODEX_HOME`, and **parity across `preflight._CHECKS` ↔ `SUPPORTED_CLIS` ↔ `add_agent_seat.SHAPES` ↔ `Resolve-AgentSeat`** — four lists that must agree or a seat exists in one place and not another. |
| [**`test_media_prompts.py`**](test_media_prompts.py) | The image and audio prompt builders and the `/prompts/{kind}.md` route. |
| [**`test_deliverable_flow.py`**](test_deliverable_flow.py) | The five process fixes drawn from live run #54: last-result-wins (and that the export's transcript **headings stay clean**, since three external consumers parse them), the reader collapsing superseded drafts, the guard stopping a non-lead ending a deliverable run before the deliverable exists (with its four allow-cases — lead, post-result, `blocked`, and transcript types), the relative quiet-for threshold, and the briefs matching what the server now enforces. |
| [**`test_mcp_turns.py`**](test_mcp_turns.py) | The turn engine, driving the real MCP tool functions against a real DB. Headline case is the **cap race**: `evaluate_stop()` used to end a run when the *first* agent hit `max_turns`, which in a round-robin is always agent 1 — so every later seat silently lost a turn, and a lead seated late lost the very turn it was briefed to post `signal='result'` on. Pins that all seats reach the cap, that the rotation **skips spent seats** (without which fixing the stop rule deadlocks the pointer), out-of-turn rejection, `done`/`blocked`/`result` semantics, continuous mode, and the no-conversation shapes. |
| [**`test_notifications.py`**](test_notifications.py) | The `/notifications` sink: template filling (unknown `{placeholder}` renders empty, malformed falls back to the literal), the four events, and **the transport against a real loopback `http.server` rather than a mocked `urlopen`** — the ntfy plain-text body with a templated `X-Title`, the one key that separates Discord from Slack, the full JSON payload for a raw webhook. Plus: seeding genuinely fires `started`, a dead endpoint cannot fail a seed, `send_test()` raises where `deliver()` swallows, an ntfy topic containing a slash is refused, and saving preserves hand-written folder/command sinks instead of clobbering them. |
| [**`test_delivery.py`**](test_delivery.py) | Delivery sinks **and the stall watchdog** (detection thresholds, notify-once-and-re-arm, the `stalled` payload, opt-in-like-every-event, dry-run mode, and greps of the module + the health-check script to keep it read-only and agent-safe). The load-bearing one: **the folder sink's output is compared byte-for-byte against the real `render_export_zip()`**, so "unzipped == the zip" survives any future export change (and catches Windows text-mode CRLF rewriting). Plus: off unless configured, malformed config treated as absent, `complete`-only default events, a failing sink taking neither the conversation nor the next sink down, and that **all three completion paths call `deliver()`**. |
| [**`test_db_sync_watermarks.py`**](test_db_sync_watermarks.py) | The sidecar's two cursors, and the rule that **each runs on exactly one clock**. The push cursor used to fold in the mirror's `server_time`, so a local edit stamped behind it was never pushed and never would be — the watermark only grows. Headline case stamps an edit behind a year-2099 `server_time` and asserts the next tick ships it. Also pins the properties that made the old guard look reasonable: the pull cursor still advancing to `server_time`, a hosted-side delete still propagating, and the echo of a just-pulled row being **self-terminating** rather than ping-pong. Plus the `--force-push` rewind. |
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
`test_web_routes.py` (export, stop/delete, SSE) and `test_personas.py`
(parser/import, malformed frontmatter, zip limits). Two earlier suggestions have
since shipped: `test_mcp_turns.py`, and the watermark half of `test_sync.py` as
[`test_db_sync_watermarks.py`](test_db_sync_watermarks.py) — the sidecar's
conflict resolution across a *live* remote is still uncovered.

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
