# Conversations Redesign Recommendations

Date: 2026-06-30

## Current Issue

The current `/conversations` page mixes two competing browsing models:

- A left rail list of conversations.
- A centered "Recent" list repeating the same items.

That makes the page feel less intentional than `/personas`, which has a clear workspace model: left navigation, center list, right detail/editor.

## Recommendation

Use **Mockup 1: Personas-style tri-pane** as the primary direction.

It keeps visual continuity with `/personas`, removes duplicated conversation lists, and gives the page a useful right-side detail panel for the selected conversation: status, cast, message count, latest-message preview, and export/open actions.

Suggested implementation shape:

- Left rail: saved filters and participant filters.
- Center pane: sortable conversation table/list.
- Right pane: selected conversation summary and quick actions.
- Right pane: include a full-screen action that opens `/conversations/<id>?fullscreen=1`.
- Full-screen mode: hide the shell/rail, keep transcript export controls, add Previous, Next, and Exit full-screen controls.
- Mobile: collapse to a single list first; open the detail pane as a drawer or navigate to the transcript.

## Alternative Directions

### Mockup 2: Ops Dashboard

Best if `/conversations` should behave like an archive/reporting dashboard. It is clean, but it does not match `/personas` as closely and uses more vertical dashboard space.

### Mockup 3: Inbox + Transcript Preview

Best if users mostly read transcripts directly from the list. It is the most immersive, but it overlaps conceptually with the existing `/conversations/{id}` detail page, so it may add more complexity than needed.

## Files

- `images/redesign-conversations/current-conversations-desktop.png`
- `images/redesign-conversations/current-conversations-mobile.png`
- `images/redesign-conversations/reference-personas-desktop.png`
- `images/redesign-conversations/reference-personas-mobile.png`
- `images/redesign-conversations/conversations-redesign-mockups.html`
- `images/redesign-conversations/mockup-1-personas-style-tri-pane.png`
- `images/redesign-conversations/mockup-2-ops-dashboard.png`
- `images/redesign-conversations/mockup-3-inbox-preview.png`
- `images/redesign-conversations/mockup-1-mobile.png`
- `images/redesign-conversations/implemented-conversation-normal.png`
- `images/redesign-conversations/implemented-conversation-fullscreen.png`
