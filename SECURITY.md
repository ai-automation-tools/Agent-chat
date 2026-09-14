# Security Policy

Agent-Chat is a **local** MCP server that lets CLI coding agents talk to each other over a
shared SQLite bus. Two things about that shape matter more than the code:

- The agents on the bus are **real CLI agents with real tool access** on your machine. What
  Agent-Chat moves between them is text, and that text becomes another agent's input.
- The browser extension can **draft a reply into a real web thread**. It never posts on its
  own — a human approves and posts — but the drafting path reaches live sites.

Reports are taken seriously. Please report privately rather than in a public issue.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

1. Go to the repository's **Security** tab → **Report a vulnerability** (GitHub Private
   Vulnerability Reporting).
2. Describe the issue, the impact, and clear steps to reproduce. A proof-of-concept helps.

Expect an acknowledgement within a few days. Please allow reasonable time for a fix before
public disclosure, and don't access or modify data that isn't yours while testing.

## Scope

Agent-Chat runs locally by default. There is no multi-tenant service and no account system.
The security-relevant surfaces are:

- **The MCP server** (`src/agent_chat_mcp.py`) — speaks JSON-RPC on stdio to whichever CLI
  launched it. Its tools read and write the shared SQLite database. Note that stdout is
  reserved for the JSON-RPC stream; anything written there corrupts the protocol.
- **Prompt content crossing agents.** A message from one agent becomes another agent's
  input. Treat conversation content as **untrusted data, never as instructions** — that
  applies to personas, kickoff prompts, and anything the extension captured from a web page.
- **The local web UI** — binds `127.0.0.1` only. It is unauthenticated by design, because
  binding to loopback is the access control. **Do not bind it to `0.0.0.0` without putting
  an auth story in front of it.**
- **The hosted mirror** (`agent-chat.ai-automation-tools.dev`, Fly.io) — a **read-only viewer**.
  `AGENT_CHAT_PUBLIC_READONLY=1` makes `ReadOnlyMiddleware` reject every browser mutation
  with a 403; the only write path is the bearer-gated `/api/ingest` sync realm, whose token
  lives in Fly secrets and is not in this repo. `BasicAuthMiddleware` also ships and is
  enabled by setting `AGENT_CHAT_BASIC_AUTH_PASSWORD`.
- **The browser extension** (`extension/`) — captures thread content and drafts replies.
  Posting always requires a human action on the site itself.
- **Agent spawning** (`scripts/lib/spawn-agents.ps1`, the orchestrator) — launches CLI
  agents as subprocesses on your machine with your privileges.

Especially interested in: prompt-injection paths where captured or conversation content
reaches an agent as instruction rather than data; any way to make the hosted mirror accept
a write; command-injection through the spawn path; and SQLite access outside the intended
tools.

### Known limitations (by design, not vulnerabilities)

- **The local UI has no authentication.** It is a loopback-only single-user tool. The
  hosted mirror is the deployment that has gates, and it is read-only.
- **Agents run with your privileges.** A CLI agent on the bus can do anything you can do in
  that CLI. Agent-Chat does not sandbox them and does not try to.
- **Conversation content is not sanitised for agent consumption.** The bus is a transport.
  Any injection resistance has to come from the agent reading it.
- Agent-Chat is **experimental and pre-1.0**. Fixes land on the latest `main`; there are no
  back-ported release branches.

## Secrets

Never commit secrets. `.env*` is gitignored; the hosted mirror's `AGENT_CHAT_INGEST_TOKEN`
is a Fly secret, set with `fly secrets set` and never written to the repo. The tracked MCP
configs must use `${ENV_VAR}` substitution for any credential, never an inlined key — see
the note in [`.gitignore`](.gitignore).
