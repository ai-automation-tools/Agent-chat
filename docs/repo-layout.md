# Repository layout

The annotated source tree for Agent-Chat. (Moved out of the root `README.md` to
keep it lean — this is the canonical reference.)

> [!TIP]
> **Every folder marked `README.md ★` is an index.** Open any folder on GitHub
> and its README tells you what's inside and links one level down. Start at the
> root [`README.md`](../README.md) and you can reach every document by clicking.

```
Agent-chat/
├── README.md ★                   # Front door — links down to every folder index below
├── CLAUDE.md                     # Claude Code project instructions (tracked, not user docs)
├── src/
│   ├── README.md ★               # Source index — entrypoints, packages, invariants
│   ├── agent_chat_mcp.py         # The MCP server (FastMCP + sqlite3) — canonical SCHEMA
│   ├── start_conversation.py     # Seed a conversation row (CLI — thin wrapper over seeding)
│   ├── inspect_conversations.py  # CLI: list / show / tail / stop
│   ├── presets.py                # Named conversation presets (debate / code-review / …)
│   ├── web_ui.py                 # Web-UI ENTRYPOINT only: page routes + route table + main()
│   ├── web/                      # Web-UI implementation package (split out of web_ui.py 2026-07-10)
│   │   ├── db.py                 #   connection + SCHEMA/migrations + SQL helpers + set_db_path()
│   │   ├── security.py           #   BasicAuth / ReadOnly middleware + _build_middleware()
│   │   ├── assets.py             #   CSS/JS/SVG constants (BASE_CSS, HOME_CSS, _CONV_CSS, …)
│   │   ├── avatars.py            #   persona avatar resolution (DB upload → PNG/SVG; GET /avatars/{slug})
│   │   ├── topics.py             #   topic → logo classifier (TOPICS keyword/glyph/gradient table)
│   │   ├── render/               #   per-page HTML: common · home · conversations · orchestrate
│   │   │                         #     · personas · setup · extension
│   │   └── api/                  #   /api/*: conversations (+SSE) · sync · orchestrate · personas
│   │                             #     · setup · battleground
│   └── orchestrator/             # /orchestrate form + preflight + seed
│       ├── seeding.py            #   seed_conversation() — single source of truth
│       ├── preflight.py          #   per-CLI MCP-config checks (no subprocess); SUPPORTED_CLIS
│       ├── availability.py       #   which CLIs THIS machine has (detect + declare) + seat planner
│       ├── personas.py           #   DB-backed persona registry + groups + JSON CLI
│       ├── model_personas.py     #   built-in AI-Models cards (one per CLI) — Cast fallback
│       └── export.py             #   export-bundle renderers — single source of truth
├── extension/                    # AgentBattleground — MV3 extension (the browser front)
│   ├── README.md ★               #   Install + operator walkthrough + adapter table
│   ├── manifest.json             #   Chrome. No static content scripts; per-domain opt-in at capture
│   ├── manifest.firefox.json     #   Gecko port (sidebar_action, background scripts, gecko id)
│   ├── icons/                    #   icon-{16,32,48,128}.png + the script that generates them
│   └── src/                      #   background.js · capture.js (site adapters) · panel/ (review UI)
├── tests/
│   ├── README.md ★               # Test index — how to run, conventions, known gaps
│   ├── test_web_readonly.py      #   read-only mode / auth middleware / orchestrate guard
│   ├── test_availability.py      #   CLI detect-vs-declare, seat planning, /setup, the demo strip
│   ├── test_battleground.py      #   arena bridge, verdict gate, CORS, schema parity, MCP loop
│   ├── test_topics.py            #   topic → logo classification + tie-breaks
│   ├── test_model_personas.py    #   AI-Models cards, reserved-group casting guard, Cast fallback
│   └── test_inspect_tail.py      #   inspect `tail` completion guard (regression)
├── scripts/
│   ├── README.md ★               # Script index, grouped by job (wire / run / serve / publish)
│   ├── run-mcp-server.ps1 · .sh  # Per-CLI MCP launcher (resolves venv + server relative to itself)
│   ├── start.ps1                 # Sidecar lifecycle + seed-conversation wrapper
│   ├── startup-app.ps1           # Logon launcher: brings up web UI + sidecar hidden (idempotent)
│   ├── debate.ps1                # One-command auto-debate: pick topic + personas, seed, launch CLIs
│   ├── orchestrate-debate.ps1    # Web-form spawn wrapper for an already-seeded conversation
│   ├── build-extension.ps1       # Stage the Firefox extension build (Chrome needs no build)
│   ├── db_sync.py                # Local → Fly DB-mirror sidecar (stdlib only)
│   ├── publish_debate.py         # Publish a finished debate into the AI-Automation-Library archive
│   ├── lib/spawn-agents.ps1      # Shared CLI registry + prompt-file/spawn helpers
│   └── setup/                    # setup-skill-links.ps1/.sh · register-startup-task.ps1
├── prompts/
│   ├── README.md ★               # Prompt-library index
│   ├── Kickoff/kickoff.md        # Canonical reusable kickoff prompt template
│   ├── Auto-Debate/ ★            # START a debate  (6 categories)
│   ├── Manage-Debates/ ★         # RUN a debate — watch / stop / export / troubleshoot
│   └── Battleground/ ★           # FIGHT on the web — join-arena / manage-arenas / troubleshooting
├── skills/                       # Agent Skills — every CLI reads the same SKILL.md format
│   ├── README.md ★               #   Skills overview — what each does + how they compose
│   ├── agent-chat/               #   Base participation loop (role-agnostic)   [SKILL.md + README.md]
│   ├── debate-mode/              #   Layered skill — argue, cite, no hedging   [SKILL.md + README.md]
│   ├── battleground/             #   Argue in a captured web thread            [SKILL.md + README.md]
│   ├── start-debate/             #   Operator skill — launch a debate          [SKILL.md + README.md]
│   └── publish-debate/           #   Operator skill — publish a finished one   [SKILL.md + README.md]
├── agents/                       # Per-CLI tester workspaces + persona SEED cards
│   ├── README.md ★               #   Agents index — workspaces, role docs, persona caveat
│   ├── CLIs/                     #   Tester role docs + per-CLI MCP configs
│   │   ├── claude-code_agent1/   #     claude.md + .mcp.json
│   │   ├── codex_agent1/         #     AGENTS.md (MCP in global ~/.codex/config.toml)
│   │   ├── antigravity_agent1/   #     AGENTS.md + .agents/mcp_config.json
│   │   ├── kimi_agent1/          #     AGENTS.md + .kimi-code/mcp.json (auto-loaded from launch dir)
│   │   ├── opencode_agent1/      #     AGENTS.md + opencode.json (mcp key, type:local, command array)
│   │   └── gemini_agent1/        #     GEMINI.md + .gemini/settings.json (deprecated fallback)
│   ├── Debate-Agents/            #   SEED CARDS ONLY — live personas are DB rows, not these files
│   │   ├── Debate-Agents-Random/ #     Original roster + Debate-Hosts/ moderators
│   │   └── AI-Library-Imports/   #     Cards imported from the AI-Automation-Library (+ cover art)
│   └── Debate-Agent-Templates/ ★ #   Canonical persona-card template + generator prompt
├── images/
│   ├── README.md ★               # Image index — what ships vs what's docs-only
│   ├── AgentChat-Avatars/        #   RUNTIME art — <slug>-avatar.png/svg, COPYed into the Fly image
│   ├── AgentChat-Images/         #   Brand marks: logos/ ★ + icons/ ★ (light + dark) + preview.html
│   ├── mcp/ · mcp-bidirectional/ #   Architecture diagrams used in the docs
│   └── redesign-conversations/   #   Design history for the two-pane conversations redesign
├── artifacts/                    # One-off written analyses (conversations redesign recommendations)
├── db/                           # chat.db + db/launch/ per-agent prompt files (gitignored)
├── logs/                         # debate-history.log + orchestrator audit logs (gitignored)
├── docs/
│   ├── README.md ★               # THE HUB — architecture diagram + map of every section
│   ├── Guides/ ★                 # The 4 ways to run an agent + a worked example
│   │   ├── start-new-chat.md     #   Manual CLI seed — daily-driver operator flow ⭐
│   │   ├── auto-debate.md        #   Auto-debate — one-command launcher (scripts/debate.ps1)
│   │   ├── orchestrate-form.md   #   Web UI seed form (local /orchestrate)
│   │   ├── battleground.md       #   AgentBattleground — argue in a real web debate (extension)
│   │   └── example-conversation-startup.md  # Concrete 3-agent worked example
│   ├── App/ ★                    # Per-feature application reference
│   │   ├── how-it-works.md       #   Technical guide — WAL bus, turn enforcement, long-poll, no-auth
│   │   ├── web-ui.md             #   Routes, homepage design system, SSE, topic logos, export, auth
│   │   ├── personas.md           #   Persona registry + AI-Models group + MCP tools
│   │   ├── kickoff-prompts.md    #   Server-delivered kickoff + presets (get_kickoff)
│   │   ├── battleground.md       #   Arenas, the bridge API, the draft-review gate
│   │   └── export-format.md      #   Export-bundle format CONTRACT (web · library · theater)
│   ├── CLI-MCP-Config/ ★         # MCP registration — project + global, per CLI
│   │   └── Per-CLI/ ★            #   Deep dives: claude · codex · antigravity · kimi · opencode · gemini
│   ├── Chat-Topics/ ★            # Curated topic libraries
│   │   ├── Topics.md             #   100 topics, ✅-checked-off as used
│   │   └── Legacy/ ★             #   Earlier 50-Topics-GPT / 50-Topics-Grok sets
│   ├── Setup/INITIAL_SETUP.md    # Bootstrap reproduction (git, venv, agent wiring) — single doc
│   ├── Testing/                  # debate-launch-walkthrough.md — single doc
│   ├── repo-layout.md            # This file
│   ├── CHANGELOG.md              # Reverse-chronological changelog
│   └── Roadmap.md                # Priority-ordered Open + Done tables
├── .github/workflows/ci.yml      # CI on push/PR: deps · import/compile · validate configs · tests
├── .claude/                      # Claude Code config (agents/ + commands/ + skills/ tracked)
├── requirements.txt              # Pinned: mcp, pydantic, starlette, markdown-it-py, …
├── Dockerfile · fly.toml         # The hosted mirror (web UI only)
└── .gitignore · .dockerignore
```

## The index chain

Documentation is a tree of `README.md` index files. Each one lists its
**immediate children** and links back up to its parent:

```
README.md  (root — front door)
   ├─► docs/README.md  (the hub / map)
   │      ├─► docs/Guides/README.md      ─► the 5 guides
   │      ├─► docs/App/README.md         ─► the 6 app docs
   │      ├─► docs/CLI-MCP-Config/README.md ─► Per-CLI/README.md ─► the 6 CLI guides
   │      └─► docs/Chat-Topics/README.md ─► Topics.md · Legacy/README.md
   ├─► src/README.md · scripts/README.md · tests/README.md
   ├─► skills/README.md · prompts/README.md · extension/README.md
   └─► agents/README.md · images/README.md
```

A folder holding a **single** document (`docs/Setup/`, `docs/Testing/`) is linked
straight to that document rather than getting an index of its own.

---

<p align="center">
  <sub>← <a href="README.md">Documentation home</a> · <a href="../README.md">Agent-Chat</a> · <a href="Roadmap.md">Roadmap</a></sub>
</p>
