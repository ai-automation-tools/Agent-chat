<h1 align="center">🧩 Source</h1>

<p align="center">
  <em>Four entrypoints and two packages. The MCP server, the seeder,<br>
  the inspector, and a Starlette web UI — all talking to one SQLite file.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&labelColor=09090b&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Bus-SQLite_WAL-003B57?style=for-the-badge&labelColor=09090b" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/Web-Starlette_+_SSE-0e1526?style=for-the-badge&labelColor=09090b" alt="Starlette + SSE">
</p>

---

## 🚪 Entrypoints

Each is an `argparse` CLI. Always invoke the venv interpreter explicitly.

| Module | What it is | Run it |
|:---|:---|:---|
| [**`agent_chat_mcp.py`**](agent_chat_mcp.py) | **The MCP server.** FastMCP + `sqlite3`. Registers every tool an agent calls — `get_kickoff`, `wait_for_turn`, `send_message`, the persona tools, and the four AgentBattleground arena tools. Holds the canonical `SCHEMA`. | Registered per CLI via [`scripts/run-mcp-server.ps1`](../scripts/run-mcp-server.ps1) |
| [**`web_ui.py`**](web_ui.py) | **Web-UI entrypoint only** — page routes, the route table, app assembly, `main()`. Implementation lives in [`web/`](#-webpackage). Binds `127.0.0.1:8765`. | `.\.venv\Scripts\python.exe src\web_ui.py` |
| [**`start_conversation.py`**](start_conversation.py) | Thin `argparse` wrapper around `orchestrator.seeding` — seeds a conversation out of band. Declares no schema of its own. | `.\.venv\Scripts\python.exe src\start_conversation.py --topic "..."` |
| [**`inspect_conversations.py`**](inspect_conversations.py) | Operator CLI: `list` / `show` / `tail` / `stop` / `deliver` / `watch`. Read-mostly; only SELECT, a stop UPDATE, and delivery's local bookkeeping. | `.\.venv\Scripts\python.exe src\inspect_conversations.py list` |
| [**`presets.py`**](presets.py) | The named presets that shape a seeded kickoff — tone, mode, `max_turns`, and for a collaboration the deliverable's shape. Also the **sub-type axis**: `conv_type` is the room's structure, a preset is what it produces. | imported |

## 🌐 `web/` package

Split out of `web_ui.py` on 2026-07-10. Keep new code in the matching module,
keep route paths defined only in `web_ui.py`, and keep the `web_ui` re-exports
working — the tests import them.

| Module | Owns |
|:---|:---|
| [**`db.py`**](web/db.py) | Connection handling, the `SCHEMA` mirror + `_MIGRATIONS`, every SQL helper, and `set_db_path()` (which also exports `$AGENT_CHAT_DB`). |
| [**`security.py`**](web/security.py) | `BasicAuthMiddleware`, `ReadOnlyMiddleware`, and `_build_middleware()` — what makes the hosted mirror refuse browser mutations. |
| [**`assets.py`**](web/assets.py) | CSS / JS / SVG constants (`BASE_CSS`, `HOME_CSS`, `_CONV_CSS`, `_PERSONAS_CSS`, favicon). |
| [**`avatars.py`**](web/avatars.py) | Persona avatar resolution by slug: uploaded DB image → shipped PNG/SVG → default silhouette. Serves `GET /avatars/{slug}`. |
| [**`topics.py`**](web/topics.py) | The `TOPICS` keyword/glyph/gradient table that classifies a conversation topic into a logo at render time. No schema, no backfill. |
| [**`render/`**](web/render/) | Per-page HTML — `common` (shell, markdown, icons, the hosted demo strip), `home`, `conversations` (two-pane inbox), `orchestrate`, `personas`, `setup` (which CLIs you have), `extension` (the AgentBattleground explainer), `battleground` (the arena console — list, thread, drafts, verdicts; renders only, its buttons call the existing bridge routes). |
| [**`api/`**](web/api/) | `/api/*` handlers — `conversations` (incl. the SSE stream), `sync` (ingest/since), `orchestrate`, `personas`, `setup` (CLI availability + seat creation), `notifications` (arms one delivery sink), `delivery_settings` (the folder + command sinks), `battleground` (the extension bridge). |

## 🎬 `orchestrator/` package

| Module | Owns |
|:---|:---|
| [**`seeding.py`**](orchestrator/seeding.py) | `seed_conversation()` — **the single source of truth** for creating a conversation. Both `start_conversation.py` and `POST /api/orchestrate` go through it. |
| [**`preflight.py`**](orchestrator/preflight.py) | Per-CLI MCP-config checks with no subprocess, plus `SUPPORTED_CLIS` — the canonical CLI list. |
| [**`availability.py`**](orchestrator/availability.py) | Which CLI tools *this machine* has — detection (binary on `PATH` + preflight) versus the operator's declaration in `config/available-clis.json`, plus `plan_seats()`. The reason one CLI is enough. |
| [**`personas.py`**](orchestrator/personas.py) | The DB-backed persona registry: groups, CRUD, import, and a JSON CLI. Holds the `personas`-table DDL mirror. |
| [**`model_personas.py`**](orchestrator/model_personas.py) | The built-in `AI-Models` cards (one per supported CLI) used as the Cast fallback when a conversation recorded no personas. |
| [**`export.py`**](orchestrator/export.py) | Export-bundle renderers — **single source of truth** for `/export.md`, `/export.zip`, and `scripts/publish_debate.py`. |
| [**`watchdog.py`**](orchestrator/watchdog.py) | Notices an active conversation that has gone quiet and fires delivery's `stalled` event — once per stall, keyed on the last message id so a new message re-arms it. Read-only and **never touches an agent**: a stalled run needs a human to click something in a CLI window, not a watchdog that ends it. |
| [**`delivery.py`**](orchestrator/delivery.py) | Push a finished conversation out — folder / webhook / command sinks, fired from the three places a conversation can end **plus `started` at seed time**. The webhook sink is also what `/notifications` arms. Renders nothing itself: the folder sink writes `export.bundle_files()` verbatim. Off unless `config/delivery.json` says otherwise, and **never raises** — a dead sink costs an artifact, not a turn. |

## ⚠️ Before you change anything

| Rule | Detail |
|:---|:---|
| **Schema lives in four places** | `agent_chat_mcp.py` (canonical), `web/db.py`, `orchestrator/seeding.py`, and `orchestrator/personas.py` (personas table only). Mirror all of them **plus** a `_MIGRATIONS` row per copy, in the same change. |
| **Never `print()` in the MCP server** | stdout is the JSON-RPC stream. Write to `sys.stderr`. |
| **WAL is mandatory** | Two processes write the same file. Connections use `isolation_level=None` + `timeout=10.0`; the write paths rely on autocommit for their explicit `BEGIN`/`COMMIT`. |
| **The export format is frozen** | Three external consumers parse it — see [`docs/App/export-format.md`](../docs/App/export-format.md). |
| **Battleground drafts, never posts** | Nothing in `web/api/battleground.py` or the arena tools may submit to a website. See [`docs/App/battleground.md`](../docs/App/battleground.md). |
| **No `0.0.0.0` bind** | The web UI has no auth locally. Don't add a network bind without an auth story. |

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../docs/App/README.md`](../docs/App/README.md) | Per-feature reference for everything in this tree. |
| [`../docs/repo-layout.md`](../docs/repo-layout.md) | Annotated tree for the whole repo. |
| [`../tests/README.md`](../tests/README.md) | The suites that pin this behaviour. |
| [`../scripts/README.md`](../scripts/README.md) | The launchers and operator wrappers that drive these modules. |

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../docs/App/README.md">App reference</a></sub>
</p>
