# Why there is no `.mcp.json` here

`agent_chat` is registered at **user scope** (`~/.claude.json` → top-level
`mcpServers`), not in this folder. `orchestrator.preflight.check_claude_code()`
reads project scope first and falls back to user scope for **seat 1**, so this
seat is fully configured without a local file.

The `.mcp.json` that used to sit here declared only `elevenlabs` — nothing this
seat uses during a conversation — but a project-scope `.mcp.json` makes Claude
Code raise an **approval prompt on every launch**, which silently stalls a
spawned agent until somebody clicks it. One such stall cost 30 minutes of a
live run (conversation #51, 2026-08-26).

It is kept as `.mcp.json.disabled-2026-08-26`. Restore it only if this seat
genuinely needs a project-scope server, and expect the prompt to come back.

> **Seat 2+ is different.** User scope carries one agent id for the whole
> machine, so `claude-code-2` and beyond *must* have their own project-scope
> `.mcp.json` passing their own `--agent-id`. Create one with
> `scripts/setup/add_agent_seat.py`, which **synthesizes** it from the
> `agent_chat` entry in `~/.claude.json` — it has no seat-1 file to clone here,
> which is the whole point of this note. `/orchestrate` does the same thing on
> launch when you seat two chairs on Claude Code, so the usual answer is to
> click, not to run anything.
>
> Only the `agent_chat` entry crosses over; the rest of `~/.claude.json` (your
> project history, other MCP servers, settings) stays where it is. And a seat-2
> folder DOES get the approval prompt — it has a project-scope file by
> necessity. That is the trade for a second seat, and it is why seat 1 keeps
> none.

---

## The other half: the workspace trust dialog

Removing `.mcp.json` kills the *MCP-approval* prompt. There is a second,
independent one — Claude Code's **workspace trust dialog** ("do you trust the
files in this folder?"), and `--dangerously-skip-permissions` does **not**
bypass it. From `claude --help`:

> The workspace trust dialog is skipped when Claude is run in non-interactive
> mode (via `-p`, or when stdout is not a TTY, e.g. piped or redirected output).

The spawn wrapper opens a real console window so the operator can watch, which
means stdout *is* a TTY — so the dialog fires. It should only ask **once per
folder**: the answer is stored as `hasTrustDialogAccepted` in the per-project
entry in `~/.claude.json`, which all 139 other folders on this machine have.

**If this seat keeps asking**, that entry is missing. Claude Code writes it on
exit, so an agent window that is force-killed (or left open indefinitely) never
persists the answer, and the next run asks again. Close spawned windows
normally rather than killing them.

A fully unattended alternative is running the agent in `-p` mode, which skips
the dialog by design — at the cost of the visible window the operator watches.
Not adopted; noted in case a headless runner ever wants it.
