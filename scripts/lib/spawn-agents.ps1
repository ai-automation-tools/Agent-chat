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
# Resolve-AgentSeat — map an agent id to the launch spec for its seat.
#
# Seat 1 of a tool is the bare CLI id ('codex'); seat N is '<cli>-N' ('codex-2')
# and launches from 'agents\CLIs\<cli>_agent<N>' instead of '..._agent1'. That
# folder holds the seat's own MCP config passing its own --agent-id, which is
# the only thing that makes two windows of the same tool distinct participants.
# Create one with scripts\setup\add_agent_seat.py.
#
# Mirrors src\orchestrator\seats.py — same id grammar, same folder convention.
# Splitting on the registered CLI names (longest first) rather than on trailing
# digits keeps a tool whose own name ends in a digit unambiguous.
#
# Returns @{ Cli; Seat; AgentId; Dir; Exe; PromptArg; SkipPerm; EnvPrefix },
# where EnvPrefix is a pwsh statement to run before the CLI (Codex seat 2+ needs
# CODEX_HOME relocated; everything else is empty). Throws on an id that is
# neither a registered CLI nor a seat on one.
# --------------------------------------------------------------------------
function Resolve-AgentSeat {
    param(
        [Parameter(Mandatory)] [string] $AgentId,
        [Parameter(Mandatory)] [string] $RepoRoot
    )

    $cli  = $null
    $seat = 1
    if ($Clis.Contains($AgentId)) {
        $cli = $AgentId
    } else {
        foreach ($name in (@($Clis.Keys) | Sort-Object -Property Length -Descending)) {
            if ($AgentId.StartsWith("$name-")) {
                $suffix = $AgentId.Substring($name.Length + 1)
                if ($suffix -match '^\d+$') { $cli = $name; $seat = [int]$suffix }
                break
            }
        }
    }
    if (-not $cli) {
        throw "Resolve-AgentSeat: unregistered agent id '$AgentId'. Registered CLIs: $(@($Clis.Keys) -join ', ') (plus numbered seats, e.g. 'codex-2')."
    }
    if ($seat -lt 1 -or $seat -gt 5) {
        throw "Resolve-AgentSeat: seat $seat out of range for '$AgentId' (1..5)."
    }

    $spec = $Clis[$cli]
    # $spec.Dir is seat 1's folder; swap the trailing _agent1 for this seat's.
    $dir = $spec.Dir -replace '_agent1$', "_agent$seat"

    # Codex ignores per-folder config, so an extra seat only gets its own
    # --agent-id by relocating Codex's whole user root. See add_agent_seat.py.
    $envPrefix = ''
    if ($cli -eq 'codex' -and $seat -ge 2) {
        $codexHome = Join-Path (Join-Path $RepoRoot $dir) '.codex'
        $envPrefix = "`$env:CODEX_HOME = '$codexHome'; "
    }

    @{
        Cli = $cli; Seat = $seat; AgentId = $AgentId; Dir = $dir
        Exe = $spec.Exe; PromptArg = $spec.PromptArg; SkipPerm = $spec.SkipPerm
        EnvPrefix = $envPrefix
    }
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
# $Role selects the prompt shape. Debate roles:
#   'debater'   (default) — argue a side in character.
#   'moderator'           — host the debate: open the topic, keep turns on track,
#                           ask pointed follow-ups, wrap up. Does NOT argue a side.
#                           Rides the same turns rotation (it's first in the order,
#                           so it opens and interjects each round).
# Podcast roles (conv_type='podcast' — see src/orchestrator/conv_types.py):
#   'host'                — interview the guests. Asks, never answers its own
#                           questions; no side to argue. Same rotation position
#                           as a moderator, so it opens and interjects each round.
#   'guest'               — answer at length, in character. NOT a debater: engage
#                           with the others without manufacturing conflict.
#
# These mirror _ROLE_BRIEFS in src/agent_chat_mcp.py, which ships the same
# guidance in-band with every turn payload (a hand-seeded conversation has no
# prompt file at all). Change one, change the other.
# --------------------------------------------------------------------------
function New-AgentPrompt {
    param(
        [Parameter(Mandatory)] [string] $Cli,
        [string] $PersonaBody,
        [string] $PersonaName,
        [Parameter(Mandatory)] [string] $Topic,
        [Parameter(Mandatory)] $ConvId,
        [ValidateSet('debater', 'moderator', 'host', 'guest')] [string] $Role = 'debater'
    )

    $hasPersona = -not [string]::IsNullOrWhiteSpace($PersonaBody)
    if ($hasPersona) {
        $personaLabel = switch ($Role) {
            'moderator' { 'YOUR HOST PERSONA' }
            'host'      { 'YOUR HOST PERSONA' }
            'guest'     { 'YOUR GUEST PERSONA' }
            default     { 'YOUR PERSONA' }
        }
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

    if ($Role -eq 'host') {
        $voiceHost = if ($hasPersona) { "in your persona's voice" } else { 'as a warm, sharp interviewer' }
        @"
$intro You are agent "$Cli" on the agent_chat MCP server. You are the HOST of a
podcast (conversation #$ConvId) on this topic:

    "$Topic"

This is a PODCAST, not a debate. You interview the guests $voiceHost. You do not
argue a side, and you never answer your own questions.

Do this now, without asking the operator for anything:

1. Call get_kickoff() once and use it for the turn mechanics (wait_for_turn ->
   on "your_turn" read the full history -> send_message -> repeat until
   "complete"). Its "roles" field tells you which seat each agent holds, and its
   "cast" field gives you each guest's NAME.
2. You speak FIRST: welcome listeners, introduce the topic in a sentence or two,
   introduce each guest BY THE NAME IN "cast" (never by their agent id -- "codex"
   is a tool, not a person) and say what makes them worth hearing, then ask your
   opening question and hand off. Keep addressing guests by name all the way
   through.
3. On every later turn, keep it SHORT -- a few sentences at most. React to what
   was just said, then ask ONE real follow-up. Chase the specific claim, not the
   general subject: "you said X -- what happened when...?" beats "interesting,
   what about Y?". Bring in a guest who has been quiet. Push back when an answer
   dodges, but stay curious rather than combative.
4. Pace the show with "turns_remaining" (how many turns YOU have left). Your job
   is to keep it going and open new ground -- do NOT start wrapping up while
   turns_remaining is high, and never signal='done' early. On your last turn or
   two, close the show: thank the guests, one line on the best thing said.
5. Do not ask the operator for confirmation between turns.

Begin now.
"@
    } elseif ($Role -eq 'guest') {
        $voiceGuest = if ($hasPersona) {
            "Answer as your persona would -- their voice, their opinions, their stories."
        } else {
            'Answer with substance: specifics, examples, and opinions you would actually defend.'
        }
        @"
$intro You are agent "$Cli" on the agent_chat MCP server. You are a GUEST on a
podcast (conversation #$ConvId) on this topic:

    "$Topic"

This is a PODCAST, not a debate. The host asks; you answer.

Do this now, without asking the operator for anything:

1. Call get_kickoff() once and follow the loop it describes (wait_for_turn ->
   on "your_turn" read the full history -> reply -> repeat until "complete").
2. $voiceGuest Answer the host's actual question first, then go somewhere with
   it -- a concrete story, a number, a thing that surprised you. Length is fine
   here; this is your airtime.
3. Talk to the other guests by name -- get_kickoff()'s "cast" field maps each
   agent id to the name of the person in that chair, so use those, not ids.
   Agree where you agree and say why it matters; disagree where you genuinely do
   and say what you think instead. Do NOT manufacture conflict, and do not treat
   this as a debate to win.
4. Stay a guest: don't interview the host back, don't run the show, and don't
   deliver a closing summary -- that's the host's job.
5. Pace yourself with "turns_remaining". Never send signal='done' to end early,
   and do not ask the operator for confirmation between turns.

Begin now.
"@
    } elseif ($Role -eq 'moderator') {
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
2. You speak FIRST: open by introducing the topic and framing the question,
   introduce the debaters by the names in get_kickoff()'s "cast" field (not by
   their agent ids), then hand off to them.
3. On each later turn, keep it BRIEF: surface the sharpest disagreement, ask one
   pointed follow-up, call out dodged questions, and keep things on track. Do not
   take a side or add your own arguments.
4. Pace the debate with the "turns_remaining" field in each turn response (how
   many turns YOU have left). Your job is to EXTEND and sharpen the debate across
   many rounds -- do NOT wrap up or send signal='done' while turns_remaining is
   still high; keep the debaters going and pushing new ground. ONLY when
   turns_remaining is low (you are on your last turn or two) deliver a short
   wrap-up -- what each side argued and what stayed unresolved -- and you may then
   signal='done'. Do not ask for confirmation between turns.

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
3. Pace yourself with the "turns_remaining" field in each turn response -- it is
   how many turns YOU have left. Keep opening NEW arguments and rebuttals every
   turn; do NOT give a closing or summary statement until turns_remaining shows
   you are on your last turn or two. Never send signal='done' to end early -- let
   max_turns close the debate so it runs its full length.
4. Do not ask for confirmation between turns. Keep going until the conversation
   completes.

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
# --first speaker; a moderator should be first). .Cli is the *agent id* — a
# registered CLI name or a numbered seat on one ('codex-2'), resolved through
# Resolve-AgentSeat, so two entries may run on the same tool in different seats.
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
        # .Cli carries the agent id, which may be a seat ('codex-2') rather than
        # a bare CLI name; Resolve-AgentSeat throws on anything unrecognised.
        $spec = Resolve-AgentSeat -AgentId ([string]$a.Cli) -RepoRoot $RepoRoot
        $role = if ($a.PSObject.Properties['Role'] -and $a.Role) { [string]$a.Role } else { 'debater' }
        $promptFile = Join-Path $LaunchDir ("conv{0}-{1}.txt" -f $ConvId, $a.Cli)
        if (-not $DryRun) {
            New-AgentPrompt -Cli $a.Cli -PersonaBody ([string]$a.PersonaBody) `
                -PersonaName ([string]$a.PersonaName) -Topic $Topic -ConvId $ConvId -Role $role |
                Set-Content -LiteralPath $promptFile -Encoding UTF8
        }

        # Tiny static opening prompt -- no persona content, trivial to quote.
        $opening = "Read the file at '$promptFile' in full and follow every instruction in it. Begin immediately; do not wait for further input."

        $dir     = Join-Path $RepoRoot $spec.Dir
        $argPart = $spec.PromptArg -f ('"' + $opening + '"')
        $skip    = if ($SkipPermissions -and $spec.SkipPerm) { " $($spec.SkipPerm)" } else { '' }
        $cmd     = "Set-Location -LiteralPath '$dir'; $($spec.EnvPrefix)$($spec.Exe)$skip $argPart"

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
