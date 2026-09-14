# Deploy the hosted mirror to Fly

Decide whether the hosted mirror actually needs a deploy, then run it. Context:
**$ARGUMENTS**

The Fly app `agent-chat-mikesailab` (→ `agent-chat.ai-automation-tools.dev`) runs **only
the web UI** (`src/web_ui.py` and the `src/web/` package it imports). Most of
this repo never runs there.

## Instructions

1. **Check what actually changed** — `git log origin/<branch>..HEAD --stat` for
   unpushed work, or `git diff --name-only` against the last deploy. Deploy
   **iff** the change touches something the hosted app runs:
   - `src/web_ui.py` or anything under `src/web/`
   - `requirements.txt`
   - `fly.toml` or the `Dockerfile`

2. **Skip the deploy** — and say so rather than deploying "to be safe" — for
   changes that only touch docs, `scripts/` (including `debate.ps1`), the MCP
   server, `start_conversation.py`, `agents/`, `skills/`, or persona/DB data.
   None of that runs on Fly.

   **Data never needs a deploy.** Conversations and personas reach the mirror
   through the local→Fly sidecar sync (`scripts/db_sync.py`), not through code.
   If new conversations aren't showing up, that's a sidecar question — see
   `docs/Local/db-sync.md` (gitignored, operator-only) — not a reason to redeploy.

3. **Push first.** The deploy builds from the working tree, but shipping code
   that isn't on the remote strands the mirror on a commit nobody can see.
   Confirm the branch is pushed.

4. **Confirm with the user before deploying.** This is outward-facing. Skip the
   ask only if they've already told you to proceed in this session.

5. **Deploy:**
   ```powershell
   fly deploy --app agent-chat-mikesailab
   ```
   A `fly deploy` can fail transiently — retry once before investigating.

6. **Verify it's live**, don't just trust the exit code:
   ```powershell
   fly status --app agent-chat-mikesailab
   ```
   The machine's `LAST UPDATED` should be the deploy you just ran, and the
   version number should have incremented. Then hit the real URL and confirm the
   change is actually visible — e.g.
   `curl.exe -s https://agent-chat.ai-automation-tools.dev/conversations | Select-String "<something your change added>"`.
   Reaching for the browser is fine too, but a `curl` grep is the cheapest proof.

## Reporting

State plainly whether you deployed or skipped, and why. If you deployed, give the
version number and the evidence it's serving the new code. If a step failed, quote
the output.
