# Repository layout

The annotated source tree for Agent Battleground. (Moved out of the root
`README.md` to keep it lean — this is the canonical reference.)

```
Agent-chat/
├── src/
│   ├── agent_chat_mcp.py         # The MCP server (FastMCP + sqlite3)
│   ├── start_conversation.py     # Seed a conversation row (CLI — thin wrapper)
│   ├── inspect_conversations.py  # CLI: list / show / tail / stop
│   ├── web_ui.py                 # Starlette + SSE viewer · also ships POST /api/ingest
│   └── orchestrator/             # Phase 2a — /orchestrate form + preflight + seed
│       ├── __init__.py
│       ├── preflight.py          #   per-CLI MCP-config checks (no subprocess)
│       ├── personas.py           #   DB-backed persona registry (list/get/CRUD/import)
│       └── seeding.py            #   reusable seed_conversation() function
├── tests/                        # Pytest-compatible + standalone-runnable (run by CI)
│   ├── test_web_readonly.py      #   read-only mode / auth middleware / orchestrate guard
│   └── test_inspect_tail.py      #   inspect `tail` completion guard (regression)
├── scripts/
│   ├── start.ps1                 # Sidecar lifecycle + seed-conversation wrapper (Windows)
│   ├── debate.ps1                # One-command auto-debate: pick topic + personas, seed, launch CLIs
│   ├── run-mcp-server.ps1        # Per-CLI MCP launcher (resolves venv + server relative to itself)
│   └── db_sync.py                # Local → Fly DB-mirror sidecar (stdlib only)
├── prompts/
│   └── kickoff.md                # Canonical reusable kickoff prompt template
├── skills/                       # Agent Skills — every CLI reads the same SKILL.md format (linked in via scripts/setup/setup-skill-links.ps1 / .sh)
│   ├── agent-chat/               #   Base participation loop (role-agnostic)
│   │   ├── SKILL.md
│   │   └── README.md             #     Per-CLI install paths + verification
│   └── debate-mode/              #   Layered skill — argue, cite, no hedging
│       ├── SKILL.md
│       └── README.md             #     Install reference + verification
├── agents/                       # Per-CLI tester workspaces (NOT shipped to users)
│   ├── CLIs/                     # Tester role docs + per-CLI MCP configs
│   │   ├── claude-code_agent1/   # claude.md + .mcp.json
│   │   ├── codex_agent1/         # AGENTS.md
│   │   ├── gemini_agent1/        # GEMINI.md + .gemini/settings.json (gitignored — deprecated)
│   │   ├── antigravity_agent1/   # AGENTS.md + .agents/mcp_config.json (tokens via ${ENV}) — Gemini's successor
│   │   ├── kimi_agent1/          # AGENTS.md + .kimi-code/mcp.json (auto-loaded from launch dir)
│   │   └── opencode_agent1/      # AGENTS.md + opencode.json (mcp key, type:local, command array; auto-loaded)
│   ├── Debate-Agents/            # Personality/role bundles for debate-mode runs
│   │   ├── Unique-Personas/      # 25-card debater roster (default persona group)
│   │   ├── Debate-Hosts/         # 4 moderator/host cards
│   │   └── <Curated-Subset>/     # Any subfolder is a valid persona group (auto-discovered)
│   └── Debate-Agent-Templates/   # Canonical persona-card template + authoring README
├── db/                           # chat.db + db/launch/ per-agent prompt files (gitignored)
├── logs/                         # debate-history.log + orchestrator audit logs (gitignored)
├── docs/
│   ├── App/                      # Application docs
│   │   ├── web-ui.md             # Routes, homepage design system, SSE, export, auth
│   │   ├── kickoff-prompts.md    # Server-delivered kickoff + presets (get_kickoff)
│   │   ├── personas.md           # Persona registry + list_personas / get_persona tools
│   │   ├── db-sync.md            # Local → Fly sidecar setup + troubleshooting
│   │   └── fly-deploy.md         # Public deploy on Fly.io
│   ├── Setup/
│   │   └── INITIAL_SETUP.md      # Bootstrap reproduction (git, venv, agent wiring)
│   ├── Guides/                   # The 3 ways to start a conversation + a worked example
│   │   ├── start-new-chat.md     # Manual CLI seed — daily-driver operator flow ⭐
│   │   ├── auto-debate.md        # Auto-debate — one-command launcher (scripts/debate.ps1)
│   │   ├── orchestrate-form.md   # Web UI seed form (local /orchestrate)
│   │   └── example-conversation-startup.md  # Concrete 3-agent worked example
│   ├── Testing/                  # Test walkthroughs (debate-launch-walkthrough.md)
│   ├── CLI-MCP-Config/           # MCP registration — project + global, per CLI
│   │   ├── README.md             #   Consolidated project-vs-global reference (start here)
│   │   └── Per-CLI/              #   Deep dives: claude.md · codex.md · antigravity.md · kimi.md · opencode.md · gemini.md (deprecated)
│   ├── Chat-Topics/              # Curated topic-prompt libraries
│   │   ├── Topics.md             # 100 topics + per-topic debater count; ✅-checked-off as used
│   │   └── Legacy/               # Earlier 50-Topics-GPT / 50-Topics-Grok sets
│   ├── repo-layout.md            # This file
│   ├── README.md                 # Documentation index
│   ├── CHANGELOG.md              # Reverse-chronological changelog
│   └── Roadmap.md                # Priority-ordered Open + Done tables
├── .github/
│   └── workflows/ci.yml          # CI on push/PR: deps · import/compile · validate configs · run tests (windows-latest)
├── requirements.txt              # Pinned: mcp, pydantic, starlette, markdown-it-py, …
└── README.md
```
