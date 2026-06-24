# `start-debate` skill — launch a multi-agent debate

An Agent Skill that teaches an assistant how to **kick off** a debate via the
CLI tools (primarily `scripts/debate.ps1`) — topic, the persona **group filter**,
agent count, exact CLI set, forced personas — plus the manual (`start.ps1`) and
web-form (`/orchestrate`) alternatives.

This is the **operator-facing** counterpart to the two participation skills:

| Skill | Who loads it | Job |
|---|---|---|
| [`start-debate`](SKILL.md) (this) | the operator's assistant | **start** a debate (run `debate.ps1`) |
| [`agent-chat`](../agent-chat/SKILL.md) | each participating CLI | run the `get_kickoff → wait_for_turn → send_message` loop |
| [`debate-mode`](../debate-mode/SKILL.md) | each participating CLI | argue well — cite, concede, no hedging |

## Install

Same mechanism as the other skills — the canonical copy lives here at
`skills/start-debate/`, and the setup script links every `skills/` subfolder
into each CLI's config dir automatically:

```powershell
.\scripts\setup\setup-skill-links.ps1      # Windows (POSIX: setup-skill-links.sh)
```

> **Operator session note:** unlike the participation skills (which the *spawned*
> CLI agents load from their `agents/CLIs/<cli>_agent1/` workspaces), `start-debate`
> is meant for the assistant **you** talk to at the repo root. For it to surface as
> a `/skill` there, link `skills/` into that session's discovery dir too — e.g.
> `New-Item -ItemType Junction -Path .claude\skills\start-debate -Target (Resolve-Path skills\start-debate)` —
> or just ask the assistant to "start a debate on X using group Y" and it will read
> this skill and run `debate.ps1` for you.

See the [`agent-chat` README](../agent-chat/README.md#install) for the full per-CLI
discovery-path reference.

## Verify

Ask the assistant: *"Use the start-debate skill to preview a debate on 'is cereal
soup' using the Celebrities group."* It should run:

```powershell
.\scripts\debate.ps1 -DryRun -Topic "Is cereal soup?" -Group "Celebrities"
```

…and show you the persona→CLI cast and launch plan without opening any windows.
