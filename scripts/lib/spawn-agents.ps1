<#
.SYNOPSIS
  Shared CLI registry + agent-prompt/spawn helpers for the debate launchers.

.DESCRIPTION
  Dot-sourced by BOTH scripts/debate.ps1 (the one-command auto-debate launcher)
  and scripts/orchestrate-debate.ps1 (the web-form spawn wrapper) so the CLI
  binary/flag table and the "write a per-agent prompt file, then open one pwsh
  window per agent" machinery live in exactly one place.

  Dot-source it (the path is relative to the calling script):

      . (Join-Path $PSScriptRoot 'lib\spawn-agents.ps1')

  After dot-sourcing, the caller's scope gains:
    * $Clis              — the ordered CLI registry (see below)
    * New-AgentPrompt     — render the per-agent in-character opening prompt body
    * New-AgentLaunchPlan — write prompt files + build the launch command per agent
    * Invoke-AgentLaunch  — open one pwsh window per agent (first entry first)

  The dot-source has NO side effects beyond defining those names — it never
  spawns, seeds, or writes files on load.
#>

# --------------------------------------------------------------------------
# CLI registry  --  EDIT THESE if your CLI binaries/flags differ.
#   Dir       : working directory the CLI must launch from (per-folder MCP config).
#   Exe       : the launcher binary on PATH.
#   PromptArg : how the CLI takes an INITIAL prompt. {0} is the quoted opening prompt.
#   SkipPerm  : flag to bypass tool-approval prompts (used only with -SkipPermissions).
# The opening prompt is intentionally tiny (it just points at a file), so
# embedding it as a CLI arg is safe regardless of persona length/content.
# CLI preference order = key order below; the first N are used, first = --first.
# --------------------------------------------------------------------------
$Clis = [ordered]@{
    'claude-code' = @{ Dir = 'agents\CLIs\claude-code_agent1'; Exe = 'claude'; PromptArg = '{0}';        SkipPerm = '--dangerously-skip-permissions' }
    'antigravity' = @{ Dir = 'agents\CLIs\antigravity_agent1'; Exe = 'agy';    PromptArg = '-i {0}';     SkipPerm = '--dangerously-skip-permissions' }
    'codex'       = @{ Dir = 'agents\CLIs\codex_agent1';       Exe = 'codex';  PromptArg = '{0}';         SkipPerm = '--yolo' }
    # kimi: auto-loads .kimi-code/mcp.json from the launch dir (no config flag).
    # Opening prompt is positional (like claude/codex); --yolo = unattended
    # auto-approve (NB: --prompt/-p is one-shot print mode and conflicts with
    # --yolo, so we use the positional form). Appended last so 2/3-agent runs are
    # unchanged; only -Agents 4 uses it. Requires `kimi login` once (device-code
    # auth, no API-key env var). Wired per the kimi docs, not yet live-validated.
    'kimi'        = @{ Dir = 'agents\CLIs\kimi_agent1';        Exe = 'kimi';   PromptArg = '{0}';         SkipPerm = '--yolo' }
    # opencode: auto-loads opencode.json from the launch dir (no config flag).
    # `opencode run "<prompt>"` is the headless agent loop (no TUI) — it keeps
    # executing tool calls (wait_for_turn -> send_message -> ...) until the agent
    # stops, which sustains the multi-turn debate. The Exe carries the `run`
    # subcommand so the SkipPerm flag lands after it (`opencode run
    # --dangerously-skip-permissions "<prompt>"`). Appended last so 2/3/4-agent
    # runs are unchanged; only -Agents 5 uses it. Auth via `opencode auth login`
    # (provider creds, no API-key env var assumed). Wired per the opencode docs,
    # not yet live-validated.
    'opencode'    = @{ Dir = 'agents\CLIs\opencode_agent1';    Exe = 'opencode run'; PromptArg = '{0}';    SkipPerm = '--dangerously-skip-permissions' }
}

# --------------------------------------------------------------------------
# New-AgentPrompt — the per-agent in-character opening prompt body.
#
# The persona body is the markdown card text, pulled from the DB (the runtime
# source of truth) — NOT read from disk. The on-disk cards under
# agents/Debate-Agents/ are a one-time import seed only.
#
# $PersonaBody may be empty: for a plain (non-persona) participant we drop the
# persona block entirely and just point the agent at get_kickoff(). This lets
# the web /orchestrate form spawn a mixed cast where only some CLIs are assigned
# a personality.
#
# $Role selects the prompt shape:
#   'debater'   (default) — argue a side in character.
#   'moderator'           — host the debate: open the topic, keep turns on track,
#                           ask pointed follow-ups, wrap up. Does NOT argue a side.
#                           Rides the same turns rotation (it's first in the order,
#                           so it opens and interjects each round).
# --------------------------------------------------------------------------
function New-AgentPrompt {
    param(
        [Parameter(Mandatory)] [string] $Cli,
        [string] $PersonaBody,
        [string] $PersonaName,
        [Parameter(Mandatory)] [string] $Topic,
        [Parameter(Mandatory)] $ConvId,
        [ValidateSet('debater', 'moderator')] [string] $Role = 'debater'
    )

    $hasPersona = -not [string]::IsNullOrWhiteSpace($PersonaBody)
    if ($hasPersona) {
        $personaLabel = if ($Role -eq 'moderator') { 'YOUR HOST PERSONA' } else { 'YOUR PERSONA' }
        $intro = @"
You are role-playing a persona. Stay FULLY in character in every message you send
via send_message -- never break character, never mention being an AI in an MCP
loop, never describe the tools you are using.

=== ${personaLabel}: $PersonaName ===
$PersonaBody
=== END PERSONA ===

"@
    } else {
        $intro = ''
    }

    if ($Role -eq 'moderator') {
        $voicePersona = if ($hasPersona) { "in your host persona's voice" } else { 'as a sharp, even-handed host' }
        @"
$intro You are agent "$Cli" on the agent_chat MCP server. You are the MODERATOR / HOST
of a multi-agent debate (conversation #$ConvId) on this topic:

    "$Topic"

You do NOT argue a side. Your job is to run a good debate $voicePersona.

Do this now, without asking the operator for anything:

1. Call get_kickoff() once. Use it ONLY for the turn mechanics (wait_for_turn ->
   on "your_turn" read the full history -> send_message -> repeat until "complete").
   IGNORE any "take a position / argue" framing in it -- that is for the debaters,
   not for you.
2. You speak FIRST: open by introducing the topic and framing the question, then
   hand off to the debaters.
3. On each later turn, keep it BRIEF: surface the sharpest disagreement, ask one
   pointed follow-up, call out dodged questions, and keep things on track. Do not
   take a side or add your own arguments.
4. When the debate is near its end, deliver a short wrap-up: what each side argued
   and what stayed unresolved. Do not ask for confirmation between turns.

Begin now.
"@
    } else {
        $voiceLine = if ($hasPersona) {
            "Write EVERY reply in your persona's voice and argue your persona's position."
        } else {
            "Make substantive, specific points and engage directly with what the others say."
        }
        @"
$intro You are agent "$Cli" on the agent_chat MCP server, taking part in a multi-agent
conversation (conversation #$ConvId) on this topic:

    "$Topic"

Do this now, without asking the operator for anything:

1. Call get_kickoff() once and follow the loop it describes (wait_for_turn ->
   on "your_turn" read the full history -> reply -> repeat until "complete").
2. $voiceLine
   React specifically to what the others said; push back, don't just agree.
3. Do not ask for confirmation between turns. Keep going until the conversation
   completes (max_turns will end it).

Begin now.
"@
    }
}

# --------------------------------------------------------------------------
# New-AgentLaunchPlan — for each assignment, (optionally) write its prompt file
# and build the exact pwsh launch command. Returns one object per agent:
#   { Cli; PromptFile; LaunchDir; Command }
#
# $Assignments is an array of objects each carrying .Cli, .PersonaName,
# .PersonaBody (PersonaName/PersonaBody may be empty), and an optional .Role
# ('debater' default | 'moderator'). Order is the spawn order (first entry =
# --first speaker; a moderator should be first). Every .Cli must be a key in $Clis.
#
# In -DryRun the prompt files are NOT written (the command still references the
# path so the operator can see what would run).
# --------------------------------------------------------------------------
function New-AgentLaunchPlan {
    param(
        [Parameter(Mandatory)] $Assignments,
        [Parameter(Mandatory)] [string] $Topic,
        [Parameter(Mandatory)] $ConvId,
        [Parameter(Mandatory)] [string] $LaunchDir,
        [Parameter(Mandatory)] [string] $RepoRoot,
        [switch] $SkipPermissions,
        [switch] $DryRun
    )

    New-Item -ItemType Directory -Path $LaunchDir -Force | Out-Null

    foreach ($a in $Assignments) {
        if (-not $Clis.Contains([string]$a.Cli)) {
            throw "New-AgentLaunchPlan: unregistered CLI id '$($a.Cli)'. Registered: $(@($Clis.Keys) -join ', ')"
        }
        $role = if ($a.PSObject.Properties['Role'] -and $a.Role) { [string]$a.Role } else { 'debater' }
        $promptFile = Join-Path $LaunchDir ("conv{0}-{1}.txt" -f $ConvId, $a.Cli)
        if (-not $DryRun) {
            New-AgentPrompt -Cli $a.Cli -PersonaBody ([string]$a.PersonaBody) `
                -PersonaName ([string]$a.PersonaName) -Topic $Topic -ConvId $ConvId -Role $role |
                Set-Content -LiteralPath $promptFile -Encoding UTF8
        }

        # Tiny static opening prompt -- no persona content, trivial to quote.
        $opening = "Read the file at '$promptFile' in full and follow every instruction in it. Begin immediately; do not wait for further input."

        $spec    = $Clis[[string]$a.Cli]
        $dir     = Join-Path $RepoRoot $spec.Dir
        $argPart = $spec.PromptArg -f ('"' + $opening + '"')
        $skip    = if ($SkipPermissions -and $spec.SkipPerm) { " $($spec.SkipPerm)" } else { '' }
        $cmd     = "Set-Location -LiteralPath '$dir'; $($spec.Exe)$skip $argPart"

        [pscustomobject]@{ Cli = $a.Cli; PromptFile = $promptFile; LaunchDir = $dir; Command = $cmd }
    }
}

# --------------------------------------------------------------------------
# Invoke-AgentLaunch — open one pwsh window per launch-plan entry, first first.
#
# The terminal host is configurable via $env:AGENT_CHAT_TERMINAL:
#   (unset) / 'pwsh'  → Start-Process pwsh          (default; max compatibility)
#   'wt'              → Start-Process wt.exe -w 0 nt (Windows Terminal, nicer UX)
# Either way the cd + CLI-launch command travels intact via -EncodedCommand
# (UTF-16LE base64), which sidesteps all Start-Process quote mangling.
# --------------------------------------------------------------------------
function Invoke-AgentLaunch {
    param([Parameter(Mandatory)] $LaunchPlan)

    $useWt = ($env:AGENT_CHAT_TERMINAL -eq 'wt')
    foreach ($p in $LaunchPlan) {
        $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($p.Command))
        if ($useWt) {
            Start-Process wt.exe -ArgumentList '-w', '0', 'nt', 'pwsh', '-NoExit', '-EncodedCommand', $enc
        } else {
            Start-Process pwsh -ArgumentList '-NoExit', '-EncodedCommand', $enc
        }
        Start-Sleep -Milliseconds 1500   # let --first queue its opening message before others wait
    }
}
