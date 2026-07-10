# `publish-debate` skill — file a finished debate into the AI-Automation-Library

An Agent Skill that teaches an assistant how to **publish** a completed
conversation into the library archive
(`AI-Automation-Library/My-Library/Content/Agent-Debates/<Category>/<slug>/`):
run `scripts/publish_debate.py` (writes the export bundle straight from
`db/chat.db` — no ZIP download), then generate the `cover-image.png` from the
master cover prompt embedded in the skill.

The lifecycle counterpart to the other skills:

| Skill | Who loads it | Job |
|---|---|---|
| [`start-debate`](../start-debate/SKILL.md) | the operator's assistant | **start** a debate (run `debate.ps1`) |
| [`agent-chat`](../agent-chat/SKILL.md) | each participating CLI | run the participation loop |
| [`debate-mode`](../debate-mode/SKILL.md) | each participating CLI | argue well |
| [`publish-debate`](SKILL.md) (this) | the operator's assistant | **publish** the finished debate + cover to the library |

## Install

Same mechanism as the other skills — the canonical copy lives here at
`skills/publish-debate/`, and the setup script links every `skills/` subfolder
into each CLI's config dir automatically:

```powershell
.\scripts\setup\setup-skill-links.ps1      # Windows (POSIX: setup-skill-links.sh)
```

Like `start-debate`, this is an **operator-session** skill (the assistant you
talk to at the repo root), not one the spawned debater CLIs need. See the
[`start-debate` README](../start-debate/README.md#install) for the
operator-session linking note.

## Requirements

- The AI-Automation-Library repo cloned as a **sibling** of this repo
  (`…/Live_Apps/AI-Automation-Library`), or `$AGENT_DEBATES_ROOT` /
  `--library-root` pointing at its `Agent-Debates` folder.
- An image-generation tool available in the assistant's session for the cover
  step (the markdown publish works without one).

## Verify

Ask the assistant: *"Use the publish-debate skill to publish conversation #31
under Society-&-Culture."* It should run `scripts/publish_debate.py --cid 31
--category "Society-&-Culture"`, then generate and save the cover, then show
you both. (On an already-published debate it should instead surface the
script's "already exists" refusal and ask before using `--force`.)
