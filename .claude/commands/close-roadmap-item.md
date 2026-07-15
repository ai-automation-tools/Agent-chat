# Close a Roadmap item

Close out the Roadmap row for finished work, and write the docs that go with it.
Item: **$ARGUMENTS**

`docs/Roadmap.md` is the source of truth for priorities and the user maintains it
carefully — treat it as a record, not a scratchpad.

## Instructions

1. **Find the row.** Read `docs/Roadmap.md` and locate the matching row in the
   `Open` table. If the item isn't there, or several rows plausibly match, ask
   which one rather than guessing — a wrong edit here rewrites the user's
   priorities.

2. **Confirm it's actually done.** Read the code the row describes and check the
   claim. Partially-done is common in this repo and is fine — but then the row
   **stays Open** with a dated progress note appended (the existing rows use
   `**(YYYY-MM-DD)** …` inline), rather than moving to Done. Say which you're
   doing and why.

3. **Move, don't delete.** A closed row moves from `Open` to `Done` with the
   `Closed` column filled in using today's real date (`YYYY-MM-DD`). Rows are
   never deleted. Preserve the existing detail text and append what shipped —
   the history in these cells is the point.

4. **Split when only part landed.** If the row covered several things and you
   shipped one, note the shipped half inline with a date and leave the rest
   described in the still-Open row. Be specific about what remains, so the row is
   actionable later.

5. **Write the CHANGELOG entry.** `docs/CHANGELOG.md` is reverse-chronological;
   add an entry under today's date for any user-visible behavior change, schema
   change, or new doc. Match the existing `### Added — …` / `### Changed — …` /
   `### Fixed — …` shape, and describe what changed for a *user*, not which
   functions moved.

6. **Check the rest of the doc surface.** Ask what else the change invalidates:
   `README.md` (the public feature tour), `skills/*/SKILL.md` (read by the CLI
   agents at runtime — stale guidance actively misleads them),
   `docs/Setup/INITIAL_SETUP.md`, `docs/App/*`, and the `CLAUDE.md` repo tree for
   a new module. The `agent-chat-docs-sync` agent audits this properly if the
   change is wide.

7. **Don't commit unless asked.** Show the diff and let the user look.

## Reporting

Say which row moved (or didn't, and why), quote the `Closed` date you set, and
list the other docs you touched. If you found the work incomplete, lead with
that — it's more useful than a tidy checkmark.
