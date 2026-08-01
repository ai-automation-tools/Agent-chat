# `battleground` skill

An Agent Skill that teaches a CLI agent how to argue in **AgentBattleground** — a debate captured from a real web page (Reddit, X, Hacker News, YouTube, LinkedIn, Substack, a Discourse forum, any comment section) rather than a seeded CLI-vs-CLI conversation.

Same MCP server as [`agent-chat`](../agent-chat/), a different loop:

| | `agent-chat` | `battleground` |
|---|---|---|
| Opponent | another CLI agent | people on the internet |
| Loop | `get_kickoff` → `wait_for_turn` → `send_message` | `get_arena` → `submit_draft` → `wait_for_verdict` |
| Output | a row in `chat.db` | a **draft** a human reviews, then pastes into the page |

Three core teachings:

1. **You draft; you never post.** A human approves before anything reaches a website, and the extension only ever types into the composer.
2. **Persona ≠ identity.** Adopt the card's voice; never claim to *be* the named figure, and never invent quotes, credentials, or first-hand experience.
3. **Write for the room.** Real threads punish essay-length hedging. Answer a specific post, concede the true parts, cite what you can name.

It also carries the hard stops (no dogpiling a named private individual, no fabricated evidence, no brigading) and the `rationale` channel for declining to draft.

See [`SKILL.md`](SKILL.md) for the full guidance, [`docs/Guides/battleground.md`](../../docs/Guides/battleground.md) for the operator walkthrough, and [`docs/App/battleground.md`](../../docs/App/battleground.md) for the architecture reference.

## Install

`battleground` lives under the repo-root `skills/` folder like the others, so the standard setup script wires it up with no edit needed — the script links **every** subfolder of `skills/`.

```powershell
# Windows — junctions each CLI's skills dir to repo-root skills/
.\scripts\setup\setup-skill-links.ps1
```

```bash
# macOS/Linux
./scripts/setup/setup-skill-links.sh
```

Manual install follows the same per-CLI paths as the base skill — see [`../agent-chat/README.md`](../agent-chat/README.md), substituting `battleground` for `agent-chat`. Verify with `/skills`.

## Verify end-to-end

1. Start the web UI (the extension's bridge): `.\.venv\Scripts\python.exe src\web_ui.py`
2. Load the extension: Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → `extension/`. Firefox → `.\scripts\build-extension.ps1`, then `about:debugging` → **Load Temporary Add-on** → `extension\dist\firefox\manifest.json`.
3. Open a thread with an actual argument in it, click the AgentBattleground toolbar button, and **Capture this thread** → pick an agent + persona → **Open arena**.
4. In that CLI: `join the battleground`. The agent should call `get_arena`, then `submit_draft` — and **stop**, waiting on `wait_for_verdict`.
5. The draft appears in the panel. Approve it and confirm the text lands in the page's reply box **without being submitted**.

If the agent claims it posted something, the skill isn't loading — recheck `/skills`.

## Composes with `debate-mode`

`debate-mode`'s content guidance (argue a position, quote the other side, concede where warranted) applies here too — minus the turn-taking, which doesn't exist in a web thread. Install both.
