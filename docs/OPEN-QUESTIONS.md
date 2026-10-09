# Open questions

Decisions the scheduled roadmap runs can't make on their own. Fill in an
`- Answer:` line and the next run applies it, then moves the entry to
**Answered**. Entries are never deleted.

## Open

### Add Playwright as a test dependency so `/orchestrate`'s JS actually runs in a test?
- Asked: 2026-10-08 by agent-chat-roadmap
- Context: Roadmap row "The /orchestrate form has ~600 lines of browser JS and zero coverage", option (b). Option (a) shipped 2026-09-17 (`tests/test_orchestrate_form.py`, string invariants), so the script and the markup provably refer to the same page, but nothing executes the script: derived seat ids, the per-tool cap, format clamping and the custom-card flow are still untested. A headless Playwright smoke would cover that class, at the cost of the repo's "tests need nothing beyond the venv" rule (a pinned `playwright` plus a ~150 MB browser download in CI). Options: (1) add it as a CI-only dev dependency in a separate requirements file, so `requirements.txt` and the standalone runner stay untouched; (2) add it to `requirements.txt`; (3) don't, and keep re-checking the page by hand. Recommendation: (1), with the suite skipping cleanly when Playwright isn't installed.
- Answer:

### One-command podcast launcher: a `-Format` flag on `debate.ps1`, or a separate `start-podcast` script and skill?
- Asked: 2026-10-08 by agent-chat-roadmap
- Context: Roadmap row "Podcast follow-ups", sub-item (1); the row says to decide this before building. `docs/Chat-Topics/Podcast-Topics.md` now exists in `debate.ps1`'s topic shape (`- Guests: N` for `- Debaters: N`), so either route can reuse the parser. A `-Format podcast` flag reuses the cast/seed/spawn pipeline and the existing `start-debate` skill, but `debate.ps1` gains a host-casting branch (from `Debate-Hosts`) and its name stops describing it. A separate launcher keeps each script single-purpose but duplicates the pipeline unless it's factored into `scripts/lib/`. Recommendation: `-Format` on `debate.ps1`, with `-TopicsGlob` defaulting by format.
- Answer:

## Answered
