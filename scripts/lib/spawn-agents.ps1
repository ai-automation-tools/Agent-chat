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
    # opencode: auto-loads opencode.json from the launch dir (no config flag).
    # `opencode run "<prompt>"` is the headless agent loop (no TUI) — it keeps
    # executing tool calls (wait_for_turn -> send_message -> ...) until the agent
    # stops, which sustains the multi-turn debate. The Exe carries the `run`
    # subcommand so the SkipPerm flag lands after it (`opencode run --auto
    # "<prompt>"`). `--auto` is the documented skip-permissions flag as of the
    # 2026-08-29 CLI-docs audit (`--dangerously-skip-permissions` still works but
    # is an undocumented/hidden alias — see opencode.md). Appended last so
    # 2/3-agent runs are unchanged; only -Agents 4 uses it. Auth via `opencode
    # auth login` (provider creds, no API-key env var assumed). Wired per the
    # opencode docs, not yet live-validated.
    'opencode'    = @{ Dir = 'agents\CLIs\opencode_agent1';    Exe = 'opencode run'; PromptArg = '{0}';    SkipPerm = '--auto' }
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
# Get-AvailableCliIds — the CLI tools THIS machine has, in registry order.
#
# Mirrors src\orchestrator\availability.py: the operator's declaration from
# config\available-clis.json wins; with no declaration we fall back to probing
# each tool's launcher binary on PATH. If neither yields anything (no file, and
# nothing found — which also covers a machine where PATH lookups are unusual),
# we hand back the whole registry, because a launcher that refuses to run is a
# worse failure than one that tries and reports what's missing.
#
# The web UI's /setup page writes that file. This function only reads it.
# --------------------------------------------------------------------------
function Get-AvailableCliIds {
    param([Parameter(Mandatory)] [string] $RepoRoot)

    $configPath = if ($env:AGENT_CHAT_CLI_CONFIG) { $env:AGENT_CHAT_CLI_CONFIG }
                  else { Join-Path $RepoRoot 'config\available-clis.json' }
    if (Test-Path -LiteralPath $configPath) {
        try {
            $declared = (Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).available
            if ($null -ne $declared) {
                $set = [System.Collections.Generic.HashSet[string]]::new([string[]]@($declared))
                $ordered = @(@($Clis.Keys) | Where-Object { $set.Contains($_) })
                if ($ordered.Count) { return $ordered }
            }
        } catch {
            Write-Warning "could not read $configPath ($($_.Exception.Message)); falling back to PATH detection"
        }
    }
    # No usable declaration: detect. $spec.Exe may carry a subcommand
    # ('opencode run'), so probe the first token only.
    $found = @(@($Clis.Keys) | Where-Object {
        $exe = ($Clis[$_].Exe -split '\s+')[0]
        [bool](Get-Command $exe -ErrorAction SilentlyContinue)
    })
    if ($found.Count) { return $found }
    return @($Clis.Keys)
}

# --------------------------------------------------------------------------
# Get-PlannedSeats — deal $Count participant seats round-robin over $CliIds.
#
# Mirrors availability.plan_seats(): one seat per tool first, then a second on
# each. Two tools and two debaters is still one seat each; ONE tool and two
# debaters is 'claude-code' vs 'claude-code-2', which is the whole point — a
# seat is config, not a program, so a single install can fill both chairs.
#
# Throws when a planned seat has no config folder yet, naming the command that
# creates it: an unhelpfully-late failure would be the CLI launching into a
# folder that doesn't exist.
# --------------------------------------------------------------------------
function Get-PlannedSeats {
    param(
        [Parameter(Mandatory)] [string[]] $CliIds,
        [Parameter(Mandatory)] [int]      $Count,
        [Parameter(Mandatory)] [string]   $RepoRoot
    )
    if (-not $CliIds.Count) { throw "no CLI tools available — run the /setup page or install one" }
    $capacity = $CliIds.Count * 5
    if ($Count -gt $capacity) {
        throw "need $Count seats but $($CliIds.Count) tool(s) can hold at most $capacity (5 per tool)"
    }
    $seats = @()
    $index = 1
    while ($seats.Count -lt $Count) {
        foreach ($cli in $CliIds) {
            if ($seats.Count -ge $Count) { break }
            $seats += if ($index -eq 1) { $cli } else { "$cli-$index" }
        }
        $index++
    }
    foreach ($seat in $seats) {
        $spec = Resolve-AgentSeat -AgentId $seat -RepoRoot $RepoRoot
        if ($spec.Seat -ge 2 -and -not (Test-Path -LiteralPath (Join-Path $RepoRoot $spec.Dir))) {
            throw ("seat '$seat' has no config folder ($($spec.Dir)). Create it with: " +
                   ".\.venv\Scripts\python.exe scripts\setup\add_agent_seat.py --cli $($spec.Cli) --seat $($spec.Seat)" +
                   "  (or use the 'Create the missing seat folders' button on http://127.0.0.1:8765/setup)")
        }
    }
    return $seats
}

# --------------------------------------------------------------------------
# New-AgentPrompt — the per-agent opening prompt body.
#
# ROLE-AGNOSTIC BY DESIGN. This function used to carry one 40-line here-string
# per role, duplicating what `_ROLE_BRIEFS` in src/agent_chat_mcp.py already
# ships in-band with every turn payload and with get_kickoff(). That copy was
# the reason a new conversation type cost a PowerShell edit, and it could drift
# from the briefs the agents actually receive at runtime.
#
# So it no longer branches on $Role. The prompt names the seat, then points the
# agent at get_kickoff()'s "role_brief" field as its primary instruction. One
# template covers every role of every conversation type — debate, podcast,
# collaborate, and anything added later — and adding a seat means editing
# _ROLE_BRIEFS and nothing here.
#
# $Role is therefore a free-form string (whatever the type assigns: 'moderator',
# 'host', 'facilitator', …). It is stated in the prompt and otherwise unused; an
# unrecognised value degrades to "the agent is told its seat name and reads the
# brief", which is the correct behaviour rather than an error.
#
# The persona body is the markdown card text, pulled from the DB (the runtime
# source of truth) — NOT read from disk. The on-disk cards under
# agents/Debate-Agents/ are a one-time import seed only.
#
# $PersonaBody may be empty: for a plain (non-persona) participant we drop the
# persona block entirely. This lets the web /orchestrate form spawn a mixed cast
# where only some CLIs are assigned a personality.
# --------------------------------------------------------------------------
function New-AgentPrompt {
    param(
        [Parameter(Mandatory)] [string] $Cli,
        [string] $PersonaBody,
        [string] $PersonaName,
        [Parameter(Mandatory)] [string] $Topic,
        [Parameter(Mandatory)] $ConvId,
        [string] $Role = 'debater'
    )

    $hasPersona = -not [string]::IsNullOrWhiteSpace($PersonaBody)
    if ($hasPersona) {
        $intro = @"
You are role-playing a persona. Stay FULLY in character in every message you send
via send_message -- never break character, never mention being an AI in an MCP
loop, never describe the tools you are using.

=== YOUR PERSONA: $PersonaName ===
$PersonaBody
=== END PERSONA ===

"@
        $voiceLine = 'Write every message in your persona''s voice, holding the opinions that persona would actually hold.'
    } else {
        $intro = ''
        $voiceLine = 'Write with substance: specifics, examples, numbers, and claims you would actually defend.'
    }

    $seat = $Role.ToUpper()

    @"
$intro You are agent "$Cli" on the agent_chat MCP server, taking part in a
multi-agent conversation (conversation #$ConvId) on this topic:

    "$Topic"

Your seat in this conversation is: $seat.

Do this now, without asking the operator for anything:

1. Call get_kickoff() once and read all of it. Two fields decide how you behave:
     * "role_brief" -- what YOUR seat is for. This is your PRIMARY instruction.
       Where the shared kickoff and your role_brief disagree, the role_brief
       wins: it is the one thing written for your chair specifically. (A host
       asks and never argues a side; a moderator does not take a position; a
       facilitator contributes AND lands the result.)
     * "instructions" -- the shared kickoff for the whole room: the topic, the
       tone, and, when this conversation is meant to produce a deliverable, the
       shape that deliverable has to take.
   Also read "cast", which maps each agent id to the NAME of the person in that
   chair. Address people by those names, never by an agent id -- "codex" is a
   tool, not a person. "roles" tells you which seat each of them holds.
2. $voiceLine
   React specifically to what the others actually said rather than restating
   your own line.
3. Then run the loop and keep running it: wait_for_turn() -> on "your_turn" read
   the full history -> send_message() -> repeat until status is "complete".
4. Pace yourself with "turns_remaining" -- how many turns YOU have left. While it
   is high, keep opening new ground; do NOT deliver a wrap-up early and do NOT
   send signal='done' to end the conversation before its length is used up. Your
   role_brief says what your last turn or two should do.
5. Do not ask the operator for confirmation between turns. Keep going until the
   conversation completes.

Begin now.
"@
}

# --------------------------------------------------------------------------
# New-AgentLaunchPlan — for each assignment, (optionally) write its prompt file
# and build the exact pwsh launch command. Returns one object per agent:
#   { Cli; PromptFile; LaunchDir; Command }
#
# $Assignments is an array of objects each carrying .Cli, .PersonaName,
# .PersonaBody (PersonaName/PersonaBody may be empty), and an optional .Role —
# any role the conversation's type assigns (see src/orchestrator/conv_types.py),
# defaulting to 'debater'. Order is the spawn order (first entry = --first
# speaker; the type's lead seat should be first). .Cli is the *agent id* — a
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
