# Close a Roadmap item

Close out the Roadmap item for finished work, and write the docs that go with it.
Item: **$ARGUMENTS**

`docs/ROADMAP.md` is the source of truth for priorities and the user maintains it
carefully — treat it as a record, not a scratchpad. It follows the lab roadmap
standard: every item is one checkbox line, open work sits under
`## After public release` in `### 🔴 High`, `### 🟠 Medium` and `### 🟢 Low`, and
order within a group is priority.

## Instructions

1. **Find the item.** Read `docs/ROADMAP.md` and locate the matching `- [ ]` line
   under `## After public release`. If the item isn't there, or several lines
   plausibly match, ask which one rather than guessing — a wrong edit here
   rewrites the user's priorities.

2. **Confirm it's actually done.** Read the code the item describes and check the
   claim. Partially-done is common in this repo and is fine — but then the item
   **stays `- [ ]`** with a dated progress note appended to the end of its line
   (the existing items use `**(YYYY-MM-DD)** …` inline). Say which you're doing
   and why.

3. **Tick it in place, don't move or delete it.** Change `- [ ]` to `- [x]` and
   append ` — done YYYY-MM-DD: <what landed, where>` to the end of the same line,
   using today's real date. The item stays in its group. Preserve the existing
   detail text — the history on these lines is the point. Items are never
   deleted; one that became obsolete is ticked with a note saying why, or removed
   only in a commit whose CHANGELOG entry says why.

4. **Split when only part landed.** If the item covered several things and you
   shipped one, note the shipped half inline with a date and leave the rest
   described on the still-open line. Be specific about what remains, so the item
   is actionable later. When the shipped half is substantial enough to stand
   alone, add it as its own `- [x]` line directly below, with its done note.

5. **Write the CHANGELOG entry.** `docs/CHANGELOG.md` is reverse-chronological;
   add an entry under today's date for any user-visible behavior change, schema
   change, or new doc — in the same commit as the tick. Match the existing
   `### Added — …` / `### Changed — …` / `### Fixed — …` shape, and describe what
   changed for a *user*, not which functions moved.

6. **Check the rest of the doc surface.** Ask what else the change invalidates:
   `README.md` (the public feature tour), `skills/*/SKILL.md` (read by the CLI
   agents at runtime — stale guidance actively misleads them),
   `docs/Setup/INITIAL_SETUP.md`, `docs/App/*`, and the `CLAUDE.md` repo tree for
   a new module. The `agent-chat-docs-sync` agent audits this properly if the
   change is wide.

7. **Don't commit unless asked.** Show the diff and let the user look.

## Reporting

Say which item you ticked (or didn't, and why), quote the done date you set, and
list the other docs you touched. If you found the work incomplete, lead with
that — it's more useful than a tidy checkmark.
