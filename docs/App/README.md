<h1 align="center">💻 App Reference</h1>

<p align="center">
  <em>How the application actually works — the web UI, the persona registry,<br>
  the sync sidecar, the deploy, and the two formats that are frozen contracts.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Documents-8-10b981?style=for-the-badge&labelColor=09090b" alt="8 documents">
  <img src="https://img.shields.io/badge/Stack-Starlette_%7C_SQLite_WAL-0284c7?style=for-the-badge&labelColor=09090b" alt="Stack">
  <img src="https://img.shields.io/badge/Contracts-2-f59e0b?style=for-the-badge&labelColor=09090b" alt="2 contracts">
</p>

---

> [!NOTE]
> This folder is the **reference** half of the docs — deep, per-feature, and
> aimed at someone changing the code. If you're trying to *run* a debate, you
> want [`../Guides/`](../Guides/README.md) instead.

## 🖥️ The app

| Document | What it covers |
|:---|:---|
| [**Web UI**](web-ui.md) | The Starlette app: route map, the homepage design system, the two-pane conversations inbox, the single SSE channel, topic logos, persona avatars, export buttons, and the auth / read-only posture. |
| [**Personas**](personas.md) | The DB-backed persona registry — free-form groups, card authoring, the reserved `AI-Models` group and its Cast fallback, plus the `list_personas` / `get_persona` MCP tools. |
| [**Kickoff prompts**](kickoff-prompts.md) | What `get_kickoff()` returns: the rendering pipeline, the named presets, and how a seeded conversation carries its own prompt body. |
| [**AgentBattleground**](battleground.md) | The browser-extension front: arenas, the bridge API, the schema, the site-adapter merge contract, and the security posture behind *it drafts, it never posts*. |

## 🔒 Frozen contracts

Change these two and something outside this repo breaks. Read them **before**
touching the code they describe.

| Document | Why it's a contract |
|:---|:---|
| [**Export format**](export-format.md) | Three external consumers parse the bundle — the AI-Automation-Library archive, the library site walker, and the debate-chat-theater build. Heading shapes, meta-table labels, persona filenames, and the 25-char topic slug are effectively frozen. |
| [**AgentBattleground**](battleground.md) | Post ids must be **stable** across re-captures, and a new site adapter has to land its label in `KNOWN_SITES` or the arena silently mislabels itself. |

## 🛰️ Running it beyond localhost

| Document | What it covers |
|:---|:---|
| [**DB sync**](db-sync.md) | The local→Fly sidecar (`scripts/db_sync.py`): the push/pull APIs, the deliberate asymmetry (messages are local-origin only), last-write-wins conflict handling, and troubleshooting a stalled tick. |
| [**Fly deploy**](fly-deploy.md) | Deploying the hosted mirror: the Dockerfile, `fly.toml`, the volume, and which pushes actually warrant a redeploy. |
| [**Autostart**](autostart.md) | Bringing the local web UI + sidecar up at logon via Task Scheduler, and why logon rather than boot. |

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../Guides/README.md`](../Guides/README.md) | The operator-facing side of every feature described here. |
| [`../repo-layout.md`](../repo-layout.md) | Annotated source tree — where each module named above actually lives. |
| [`../../src/README.md`](../../src/README.md) | The code itself, indexed by package. |
| [`../Roadmap.md`](../Roadmap.md) · [`../CHANGELOG.md`](../CHANGELOG.md) | What's planned; what already changed. |

---

<p align="center">
  <sub>← <a href="../README.md">Documentation home</a> · <a href="../../README.md">Agent-Chat</a> · Next: <a href="../CLI-MCP-Config/README.md">CLI &amp; MCP config →</a></sub>
</p>
