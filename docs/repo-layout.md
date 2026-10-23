# Repository layout

The annotated source tree for Roundtable. (Moved out of the root `README.md` to
keep it lean — this is the canonical reference.)

> [!TIP]
> **Every folder marked `README.md ★` is an index.** Open any folder on GitHub
> and its README tells you what's inside and links one level down. Start at the
> root [`README.md`](../README.md) and you can reach every document by clicking.

```
roundtable/
├── README.md ★                   # Front door — links down to every folder index below
├── AGENTS.md                     # Agent instructions for every CLI — canonical (tracked, not user docs)
├── CLAUDE.md                     # `@AGENTS.md` + Claude Code-only notes
├── src/
│   ├── README.md ★               # Source index — entrypoints, packages, invariants
│   ├── agent_chat_mcp.py         # The MCP server (MCPServer + sqlite3) — canonical SCHEMA
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
│   │   │                         #     · personas · settings (clis/notifications/delivery)
│   │   │                         #     · setup · notifications · extension · battleground
│   │   └── api/                  #   /api/*: conversations (+SSE) · sync · orchestrate · personas
│   │                             #     · setup · notifications · delivery_settings · battleground
│   └── orchestrator/             # /orchestrate form + preflight + seed
│       ├── seeding.py            #   seed_conversation() — single source of truth
│       ├── preflight.py          #   per-CLI MCP-config checks (no subprocess); SUPPORTED_CLIS
│       ├── availability.py       #   which CLIs THIS machine has (detect + declare) + seat planner
│       ├── personas.py           #   DB-backed persona registry + groups + JSON CLI
│       ├── delivery.py           #   push a finished conversation out — folder/webhook/command sinks
│       ├── watchdog.py           #   notice a run that went quiet; fires delivery's 'stalled' event
│       ├── model_personas.py     #   built-in AI-Models cards (one per CLI) — Cast fallback
│       └── export.py             #   export-bundle renderers — single source of truth
├── homepage/                     # Static product homepage → GitHub Pages (.github/workflows/homepage.yml)
│   ├── index.html · 404.html     #   the page · deep-link redirect to the -demo host (the hosted app)
│   └── favicon.svg · CNAME       #   shared app icon · roundtable.ai-automation-tools.dev
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
│   ├── test_delivery.py          #   delivery sinks; folder output == export.zip, byte for byte
│   ├── test_notifications.py     #   ntfy/Discord/Slack transport over a real loopback server
│   ├── test_mcp_turns.py         #   turn rotation, the per-agent cap race, stop signals
│   ├── test_deliverable_flow.py  #   last-result-wins, the premature-done guard, quiet badge
│   ├── test_model_personas.py    #   AI-Models cards, reserved-group casting guard, Cast fallback
│   ├── test_site_homepage.py     #   homepage/ keeps its required links + the 404 redirect
│   ├── test_orchestrate_form.py  #   /orchestrate inline JS ↔ markup, by string invariants
│   └── test_inspect_tail.py      #   inspect `tail` completion guard (regression)
├── scripts/
│   ├── README.md ★               # Script index, grouped by job (wire / run / serve / publish)
│   ├── run-mcp-server.ps1 · .sh  # Per-CLI MCP launcher (resolves venv + server relative to itself)
│   ├── start.ps1                 # Sidecar lifecycle + seed-conversation wrapper
│   ├── startup-app.ps1           # Logon launcher: brings up web UI + sidecar hidden (idempotent)
│   ├── debate.ps1                # One-command auto-debate (or -Format podcast): pick topic + personas, seed, launch CLIs
│   ├── orchestrate-debate.ps1    # Web-form spawn wrapper for an already-seeded conversation
│   ├── build-extension.ps1       # Stage the Firefox extension build (Chrome needs no build)
│   ├── db_sync.py                # Local → Fly DB-mirror sidecar (stdlib only)
│   ├── publish_debate.py         # Publish a finished debate into the AI-Automation-Library archive
│   ├── build_diagram.py          # Rebuild / --check the process-flow diagram (docs/diagrams/)
│   ├── stop-app.ps1              # Stop web UI + sidecar (this clone's venv only)
│   ├── restart-app.ps1           # Stop + start — needed after any src/ change
│   ├── healthcheck-app.ps1       # HTTP-probe + repair; scheduled hourly
│   ├── maintain-app.ps1          # Nightly SQLite-API backup, prune, log trim
│   ├── lib/spawn-agents.ps1      # Shared CLI registry + prompt-file/spawn helpers
│   └── setup/                    # setup-skill-links · register-startup-task · register-app-tasks
│                                 #   · add_agent_seat · gen_agent_role_docs (per-seat role docs)
├── prompts/
│   ├── README.md ★               # Prompt-library index
│   ├── Kickoff/kickoff.md        # Canonical reusable kickoff prompt template
│   ├── Auto-Debate/ ★            # START a debate  (6 categories)
│   ├── Manage-Debates/ ★         # RUN a debate — watch / stop / export / troubleshoot
│   ├── Battleground/ ★           # FIGHT on the web — join-arena / manage-arenas / troubleshooting
│   └── Avatars/ ★                # Persona avatar image prompts, one file per group
├── skills/                       # Agent Skills — every CLI reads the same SKILL.md format
│   ├── README.md ★               #   Skills overview — what each does + how they compose
│   ├── agent-chat/               #   Base participation loop (role-agnostic)   [SKILL.md + README.md]
│   ├── debate-mode/              #   Layered skill — argue, cite, no hedging   [SKILL.md + README.md]
│   ├── podcast-mode/             #   Layered skill — host asks, guests answer  [SKILL.md + README.md]
│   ├── collaborate-mode/         #   Layered skill — build one artifact        [SKILL.md + README.md]
│   ├── battleground/             #   Argue in a captured web thread            [SKILL.md + README.md]
│   ├── start-debate/             #   Operator skill — launch a debate          [SKILL.md + README.md]
│   └── publish-debate/           #   Operator skill — publish a finished one   [SKILL.md + README.md]
├── agents/                       # Per-CLI agent workspaces + persona SEED cards
│   ├── README.md ★               #   Agents index — workspaces, role docs, persona caveat
│   ├── CLIs/                     #   Role docs (full-stack dev + agent-chat) + per-CLI MCP configs
│   │   ├── claude-code_agent1/   #     claude.md + .mcp.json
│   │   ├── codex_agent1/         #     AGENTS.md (MCP in global ~/.codex/config.toml)
│   │   ├── antigravity_agent1/   #     AGENTS.md + .agents/mcp_config.json
│   │   ├── opencode_agent1/      #     AGENTS.md + opencode.json (mcp key, type:local, command array)
│   │   └── <cli>_agent2..5/      #     Extra seats — generated per machine, GITIGNORED (add_agent_seat.py)
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
├── deliveries/                   # Delivered conversation bundles — the .zip, unzipped (gitignored)
├── db/                           # chat.db + db/launch/ per-agent prompt files (gitignored)
├── logs/                         # debate-history.log + orchestrator audit logs (gitignored)
├── docs/
│   ├── README.md ★               # THE HUB — architecture diagram + map of every section
│   ├── guides/ ★                 # The 4 ways to run an agent + a worked example
│   │   ├── start-new-chat.md     #   Manual CLI seed — daily-driver operator flow ⭐
│   │   ├── auto-debate.md        #   Auto-debate — one-command launcher (scripts/debate.ps1)
│   │   ├── orchestrate-form.md   #   Web UI seed form (local /orchestrate)
│   │   ├── battleground.md       #   AgentBattleground — argue in a real web debate (extension)
│   │   └── example-conversation-startup.md  # Concrete 3-agent worked example
│   ├── app/ ★                    # Per-feature application reference
│   │   ├── how-it-works.md       #   Technical guide — WAL bus, turn enforcement, long-poll, no-auth
│   │   ├── web-ui.md             #   Routes, homepage design system, SSE, topic logos, export, auth
│   │   ├── personas.md           #   Persona registry + AI-Models group + MCP tools
│   │   ├── kickoff-prompts.md    #   Server-delivered kickoff + presets (get_kickoff)
│   │   ├── cli-setup.md          #   Which CLIs a machine has; the detect-then-declare model
│   │   ├── battleground.md       #   Arenas, the bridge API, the draft-review gate
│   │   ├── delivery.md           #   Folder / webhook / command sinks; off unless configured
│   │   ├── running-the-local-app.md  # Scheduled tasks: start/stop/restart/health/backup
│   │   └── export-format.md      #   Export-bundle format CONTRACT (web · library · theater)
│   ├── diagrams/ ★               # Process-flow diagram: JSON source (edit) + generated HTML/PNG
│   ├── cli-mcp-config/ ★         # MCP registration — project + global, per CLI
│   │   └── per-cli/ ★            #   Deep dives: claude · codex · antigravity · opencode
│   ├── chat-topics/ ★            # Curated topic libraries
│   │   ├── Topics.md             #   100 debate topics, ✅-checked-off as used
│   │   ├── Podcast-Topics.md     #   40 podcast interview subjects, with guest counts
│   │   └── legacy/ ★             #   Earlier 50-Topics-GPT / 50-Topics-Grok sets
│   ├── setup/INITIAL_SETUP.md    # Bootstrap reproduction (git, venv, agent wiring) — single doc
│   ├── testing/                  # debate-launch-walkthrough.md — single doc
│   ├── repo-layout.md            # This file
│   ├── mcp-server.md             # The roundtable MCP server at a glance: tools, env vars, install
│   ├── CHANGELOG.md              # Reverse-chronological changelog
│   ├── OPEN-QUESTIONS.md         # Decisions the scheduled roadmap runs need from the maintainer
│   └── ROADMAP.md                # Priorities: checkbox items, High / Medium / Low
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
   │      ├─► docs/guides/README.md      ─► the 5 guides
   │      ├─► docs/app/README.md         ─► the 9 app docs
   │      ├─► docs/diagrams/README.md    ─► process-flow.html (+ .png, .json)
   │      ├─► docs/cli-mcp-config/README.md ─► per-cli/README.md ─► the 6 CLI guides
   │      └─► docs/chat-topics/README.md ─► Topics.md · Podcast-Topics.md · legacy/README.md
   ├─► src/README.md · scripts/README.md · tests/README.md
   ├─► skills/README.md · prompts/README.md · extension/README.md
   └─► agents/README.md · images/README.md
```

A folder holding a **single** document (`docs/setup/`, `docs/testing/`) is linked
straight to that document rather than getting an index of its own.

---

<p align="center">
  <sub>← <a href="README.md">Documentation home</a> · <a href="../README.md">Roundtable</a> · <a href="ROADMAP.md">Roadmap</a></sub>
</p>
