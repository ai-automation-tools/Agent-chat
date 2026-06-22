<#
.SYNOPSIS
  One-command debate launcher: pick a topic + random debate personas, seed a
  conversation, then auto-launch one CLI per persona and prompt each in character.

.DESCRIPTION
  Pipeline (deterministic; persona lookup delegates to the shared Python registry
  at src/orchestrator/personas.py rather than re-scanning the cards here):

    1. Parse the topic libraries under docs/Chat-Topics/ (numbered "**Title**"
       lists). Each topic may carry a trailing agent-count marker — "[2]" or
       "[3]". Pick one topic at random (or pass -Topic to force one).
    2. Decide N debaters from the topic's "- Debaters: N" line (fallback -DefaultAgents).
    3. Ask the persona registry for the chosen group's roster (default
       "Unique-Personas"; override with -Group to draw from a curated subset
       folder) and pick N at
       random (or resolve the names passed via -Personalities through the same
       registry, restricted to that group).
    4. Map persona -> CLI in a fixed CLI preference order
       (claude-code, antigravity, codex). The first CLI is the --first speaker.
    5. Seed the conversation via scripts/start.ps1 (ensures the DB-sync sidecar
       is up) with --preset debate. Capture the new conversation id from output.
    6. Write a per-agent prompt file (persona body + in-character kickoff
       instructions) under db/launch/. The CLI is handed only a tiny static
       opening prompt that tells it to read that file -- no quoting/length hell.
    7. Spawn one pwsh window per agent: cd into the agent's CLI folder (so its
       MCP config + tester role load), launch the CLI with the opening prompt.
       The --first agent is launched first so its opening message is queued
       before the others start waiting.

  The shared get_kickoff() template (rendered by --preset debate) carries the
  debate loop + tone; the per-agent persona is injected here at launch because
  get_kickoff() returns ONE template for the whole conversation. No schema change.

.PARAMETER Topic
  Force a specific topic string instead of random selection. Skips topic-file parsing.

.PARAMETER Agents
  Force the debater count (2 or 3), overriding the topic's [N] marker.

.PARAMETER DefaultAgents
  Debater count to use when the chosen topic has no "- Debaters: N" line. Default: 2.

.PARAMETER Personalities
  Force specific personas instead of random selection — each entry is a slug or
  display name resolved through the registry (e.g. "crypto-chad" or "Crypto Chad";
  a trailing .md is tolerated). Count must match the resolved agent count.
  Resolution is restricted to -Group.

.PARAMETER Group
  Persona group folder to cast from. Default "Unique-Personas" (the full debater
  roster). Any subfolder of agents/Debate-Agents/ is a valid group — create a
  curated subset folder (e.g. "Group1", "Crypto-Panel") of *.md cards and pass
  its name here to draw debaters only from that set. Discovered dynamically; no
  code change needed. ("Debate-Hosts" is the moderator roster, not normally used
  as debaters.)

.PARAMETER MaxTurns
  Per-agent message cap. Default: let the 'debate' preset decide (8).

.PARAMETER TopicsGlob
  Glob (relative to repo root) for topic-library markdown. Default: docs/Chat-Topics/Topics.md
  (Topics are "N. Title" lines, each optionally followed by a "- Debaters: N" line.)

.PARAMETER SkipPermissions
  Append each CLI's "skip tool-approval prompts" flag so the run is hands-off.
  Wired for all three CLIs (claude-code + antigravity --dangerously-skip-permissions,
  codex --yolo). Edit the SkipPerm field in the $Clis table below if a flag changes.

.PARAMETER DryRun
  Do everything EXCEPT spawn the CLI windows. Prints the seed result, the
  persona->CLI mapping, the prompt-file paths, and the exact launch command per
  agent. Use this first to sanity-check before going live.

.PARAMETER ForceSidecar
  Forwarded to start.ps1 as -Force (kill + relaunch the DB-sync sidecar).

.EXAMPLE
  .\scripts\debate.ps1 -DryRun
  # See exactly what it would pick + launch, without opening any windows.

.EXAMPLE
  .\scripts\debate.ps1
  # Random topic + personas, seed, and launch all CLIs.

.EXAMPLE
  .\scripts\debate.ps1 -Topic "Are we living in a simulation?" -Agents 3 -MaxTurns 10
#>

[CmdletBinding()]
param(
    [string]   $Topic,
    [ValidateSet(2, 3)]
    [int]      $Agents,
    [int]      $DefaultAgents = 2,
    [string[]] $Personalities,
    [string]   $Group = 'Unique-Personas',
    [int]      $MaxTurns,
    [string]   $TopicsGlob = 'docs/Chat-Topics/Topics.md',
    [switch]   $SkipPermissions,
    [switch]   $DryRun,
    [switch]   $ForceSidecar
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
$RepoRoot   = (Resolve-Path "$PSScriptRoot\..").Path
$StartPs1   = Join-Path $RepoRoot 'scripts\start.ps1'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$PersonasPy = Join-Path $RepoRoot 'src\orchestrator\personas.py'
$LaunchDir  = Join-Path $RepoRoot 'db\launch'
$LogFile    = Join-Path $RepoRoot 'logs\debate-history.log'

# A topic line carrying this marker has already been used and is skipped on the
# next run. Appended to the chosen topic's line after a successful seed.
$UsedMarker = [char]0x2705   # ✅

if (-not (Test-Path $StartPs1))   { throw "start.ps1 not found at $StartPs1" }
if (-not (Test-Path $VenvPython)) { throw "venv python not found at $VenvPython" }
if (-not (Test-Path $PersonasPy)) { throw "persona registry not found at $PersonasPy" }
New-Item -ItemType Directory -Path $LaunchDir -Force | Out-Null

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
}

function Write-Step { param([string]$m) Write-Host "[debate] $m" -ForegroundColor Cyan }
function Write-Pick { param([string]$m) Write-Host "         $m" -ForegroundColor Gray }

# Query the shared persona registry (src/orchestrator/personas.py) as JSON, so
# this script never re-implements the folder scan, frontmatter parsing, or
# display-name derivation. Returns the parsed object(s), or $null on a non-zero
# exit (e.g. `get` not-found). Each persona has .slug/.name/.group/.tags/.summary/.path.
function Get-Personas {
    param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $RegistryArgs)
    $json = & $VenvPython $PersonasPy @RegistryArgs
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($json | ConvertFrom-Json)
}

# --------------------------------------------------------------------------
# 1-2. Resolve topic + agent count
# --------------------------------------------------------------------------
$resolvedCount  = $null
$chosenTopicRow = $null   # set only when a topic is randomly drawn from a file

if ($Topic) {
    Write-Step "Topic (forced): $Topic"
} else {
    $topicFiles = @(Get-ChildItem -Path (Join-Path $RepoRoot $TopicsGlob) -ErrorAction SilentlyContinue)
    if (-not $topicFiles) { throw "no topic files matched '$TopicsGlob' under $RepoRoot" }

    # Topics.md format:
    #   12. Should children under 16 be banned from social media?
    #       - Debaters: 2
    # A "N. Title" line; the agent count is on the following "- Debaters: N" line.
    $rxTopic = [regex]'^\s*\d+\.\s+(?<title>.+?)\s*$'
    $rxCount = [regex]'^\s*-\s*Debaters:\s*(?<n>\d+)\s*$'
    $topics = foreach ($f in $topicFiles) {
        $lines = @(Get-Content -LiteralPath $f.FullName)
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $mt = $rxTopic.Match($lines[$i])
            if (-not $mt.Success) { continue }
            $used = $lines[$i].Contains($UsedMarker)
            # Look at the next few non-blank lines for a Debaters: marker.
            $cnt = $null
            for ($j = $i + 1; $j -lt [Math]::Min($i + 4, $lines.Count); $j++) {
                if ($lines[$j].Trim() -eq '') { continue }
                $mc = $rxCount.Match($lines[$j])
                if ($mc.Success) { $cnt = [int]$mc.Groups['n'].Value }
                break
            }
            [pscustomobject]@{
                Title     = ($mt.Groups['title'].Value -replace [regex]::Escape($UsedMarker), '').Trim()
                Count     = $cnt
                Used      = $used
                File      = $f.FullName
                LineIndex = $i
            }
        }
    }
    if (-not $topics) { throw "parsed 0 topics from: $($topicFiles.Name -join ', ')" }

    $available = @($topics | Where-Object { -not $_.Used })
    if (-not $available) {
        throw "all $($topics.Count) topics in $($topicFiles.Name -join ', ') are marked used ($UsedMarker). " +
              "Remove the markers to recycle, or add new topics."
    }

    $chosenTopicRow = $available | Get-Random
    $Topic          = $chosenTopicRow.Title
    $resolvedCount  = $chosenTopicRow.Count
    Write-Step "Topic (random of $($available.Count) unused / $($topics.Count) total): $Topic"
    if ($resolvedCount) { Write-Pick "topic requests $resolvedCount debaters" }
}

# Precedence: explicit -Agents > topic "Debaters:" line > -DefaultAgents
$count = if ($Agents) { $Agents } elseif ($resolvedCount) { $resolvedCount } else { $DefaultAgents }
if ($count -lt 2 -or $count -gt 3) { throw "agent count must be 2 or 3, got $count" }
if ($count -gt $Clis.Count)        { throw "need $count CLIs but only $($Clis.Count) are registered" }
Write-Step "Debaters: $count"

# --------------------------------------------------------------------------
# 3. Pick personas (from the shared registry; -Group selects the roster folder,
#    default "Unique-Personas" = the full debater roster, or any curated subset)
# --------------------------------------------------------------------------
Write-Step "Persona group: $Group"
if ($Personalities) {
    if ($Personalities.Count -ne $count) {
        throw "-Personalities has $($Personalities.Count) entries but agent count is $count"
    }
    # Resolve each by slug OR display name via the registry's forgiving matcher
    # (a trailing .md is tolerated for back-compat with the old file-name form).
    $selected = foreach ($name in $Personalities) {
        $query = if ($name.EndsWith('.md')) { $name.Substring(0, $name.Length - 3) } else { $name }
        $one = Get-Personas get $query --group $Group
        if (-not $one) { throw "persona not found in registry group '$Group': '$name'" }
        $one
    }
} else {
    $all = @(Get-Personas list --group $Group)
    if (-not $all)               { throw "persona registry returned nothing for group '$Group' (does agents/Debate-Agents/$Group/ exist with *.md cards?)" }
    if ($all.Count -lt $count)   { throw "only $($all.Count) personas available in group '$Group', need $count" }
    $selected = $all | Get-Random -Count $count
}

# --------------------------------------------------------------------------
# 4. Map persona -> CLI (first N CLIs in preference order; first = --first)
# --------------------------------------------------------------------------
$cliIds = @($Clis.Keys) | Select-Object -First $count
$assign = for ($i = 0; $i -lt $count; $i++) {
    [pscustomobject]@{
        Cli         = $cliIds[$i]
        PersonaFile = $selected[$i].path   # absolute path from the registry
        PersonaName = $selected[$i].name   # display name from the registry
        PersonaSlug = $selected[$i].slug   # stable id from the registry
    }
}
$participants = ($cliIds -join ',')
$first        = $cliIds[0]

Write-Step 'Assignments:'
foreach ($a in $assign) { Write-Pick ("{0,-12} <- {1}" -f $a.Cli, $a.PersonaName) }
Write-Pick "first speaker: $first"

# Persona metadata to persist on the conversation row (agent_id -> tool + persona
# + the full card body). seed_conversation stores it as JSON so the cast is
# self-describing in the DB and in the .zip export -- including on the hosted
# mirror, where the persona cards under agents/ are not deployed. Pulled from the
# registry (body via `get <slug> --body` => .instructions).
$personaMap = [ordered]@{}
foreach ($a in $assign) {
    $full = Get-Personas get $a.PersonaSlug --body
    $personaMap[$a.Cli] = [pscustomobject]@{
        persona_slug = $a.PersonaSlug
        persona_name = $a.PersonaName
        persona_body = if ($full) { [string]$full.instructions } else { '' }
    }
}
# Unique temp name -- conv id isn't known until after the seed, and this file is
# read DURING the seed. Lives in db/launch/ (gitignored). Harmless to leave.
$personasFile = Join-Path $LaunchDir ("personas-{0}.json" -f ([guid]::NewGuid().ToString('N')))

# --------------------------------------------------------------------------
# 5. Seed via start.ps1 (ensures sidecar) and capture the conversation id
# --------------------------------------------------------------------------
$seedArgs = @()
if ($ForceSidecar) { $seedArgs += '-Force' }
$seedArgs += @('--preset', 'debate', '--topic', $Topic, '--participants', $participants, '--first', $first)
if ($MaxTurns) { $seedArgs += @('--max-turns', $MaxTurns) }
$seedArgs += @('--participant-personas-file', $personasFile)

if ($DryRun) {
    Write-Step "DRY RUN -- would seed:  start.ps1 $($seedArgs -join ' ')"
    if ($chosenTopicRow) { Write-Pick "(dry run -- would mark topic used in $([IO.Path]::GetFileName($chosenTopicRow.File)))" }
    $convId = '<dry-run>'
} else {
    # Write the persona metadata file the seed reads (--participant-personas-file).
    ($personaMap | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $personasFile -Encoding UTF8
    Write-Step "Seeding:  start.ps1 $($seedArgs -join ' ')"
    $seedOut = & $StartPs1 @seedArgs 2>&1 | Out-String
    Write-Host $seedOut
    $m = [regex]::Match($seedOut, 'Started conversation #(\d+)')
    if (-not $m.Success) { throw "could not parse conversation id from start.ps1 output (seed may have failed)" }
    $convId = $m.Groups[1].Value
    Write-Step "Conversation #$convId seeded."

    # Check the topic off so the next run won't pick it again. Only for topics
    # drawn from a file (not -Topic), and only after the seed actually succeeded.
    if ($chosenTopicRow) {
        $fl = @(Get-Content -LiteralPath $chosenTopicRow.File)
        $idx = $chosenTopicRow.LineIndex
        if (-not $fl[$idx].Contains($UsedMarker)) {
            $stamp = (Get-Date -Format 'yyyy-MM-dd')
            $fl[$idx] = $fl[$idx].TrimEnd() + " $UsedMarker <!--used $stamp conv#$convId-->"
            Set-Content -LiteralPath $chosenTopicRow.File -Value $fl -Encoding UTF8
            Write-Pick "checked off in $([IO.Path]::GetFileName($chosenTopicRow.File)) ($UsedMarker $stamp)"
        }
    }
}

# --------------------------------------------------------------------------
# 6. Write per-agent prompt files
# --------------------------------------------------------------------------
function New-AgentPrompt {
    param($Cli, $PersonaFile, $PersonaName, $ConvId)
    $persona = Get-Content -LiteralPath $PersonaFile -Raw
    @"
You are role-playing a debate persona. Stay FULLY in character in every message
you send via send_message -- never break character, never mention being an AI in
an MCP loop, never describe the tools you are using.

=== YOUR PERSONA: $PersonaName ===
$persona
=== END PERSONA ===

You are agent "$Cli" on the agent_chat MCP server, taking part in a multi-agent
debate (conversation #$ConvId) on this topic:

    "$Topic"

Do this now, without asking the operator for anything:

1. Call get_kickoff() once and follow the loop it describes (wait_for_turn ->
   on "your_turn" read the full history -> reply -> repeat until "complete").
2. Write EVERY reply in your persona's voice and argue your persona's position.
   React specifically to what the other debaters said; push back, don't just agree.
3. Do not ask for confirmation between turns. Keep going until the conversation
   completes (max_turns will end it).

Begin now.
"@
}

$launchPlan = foreach ($a in $assign) {
    $promptFile = Join-Path $LaunchDir ("conv{0}-{1}.txt" -f $convId, $a.Cli)
    if (-not $DryRun) {
        New-AgentPrompt -Cli $a.Cli -PersonaFile $a.PersonaFile -PersonaName $a.PersonaName -ConvId $convId |
            Set-Content -LiteralPath $promptFile -Encoding UTF8
    }

    # Tiny static opening prompt -- no persona content, trivial to quote.
    $opening = "Read the file at '$promptFile' in full and follow every instruction in it. Begin immediately; do not wait for further input."

    $spec    = $Clis[$a.Cli]
    $dir     = Join-Path $RepoRoot $spec.Dir
    $argPart = $spec.PromptArg -f ('"' + $opening + '"')
    $skip    = if ($SkipPermissions -and $spec.SkipPerm) { " $($spec.SkipPerm)" } else { '' }
    $cmd     = "Set-Location -LiteralPath '$dir'; $($spec.Exe)$skip $argPart"

    [pscustomobject]@{ Cli = $a.Cli; PromptFile = $promptFile; LaunchDir = $dir; Command = $cmd }
}

# --------------------------------------------------------------------------
# 7. Launch (or, in -DryRun, just print the plan)
# --------------------------------------------------------------------------
if ($DryRun) {
    Write-Step 'DRY RUN -- launch plan (no windows opened):'
    foreach ($p in $launchPlan) {
        Write-Host ""
        Write-Host "  # $($p.Cli)" -ForegroundColor Yellow
        Write-Host "  prompt file : $($p.PromptFile)"
        Write-Host "  pwsh -NoExit -Command `"$($p.Command)`""
    }
    Write-Host ""
    Write-Step 'Re-run without -DryRun to seed + launch for real.'
    return
}

Write-Step 'Launching CLIs (first speaker first)...'
foreach ($p in $launchPlan) {
    Write-Pick "opening window: $($p.Cli)"
    # -EncodedCommand (UTF-16LE base64) sidesteps all Start-Process quote mangling:
    # the cd + CLI-launch command travels intact regardless of embedded quotes.
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($p.Command))
    Start-Process pwsh -ArgumentList '-NoExit', '-EncodedCommand', $enc
    Start-Sleep -Milliseconds 1500   # let --first queue its opening message before others wait
}

# Append a one-block run record so the topic + persona->CLI mapping for this
# conversation is greppable in one place (the message transcript itself lives in
# the DB -- see inspect_conversations.py / the web UI / Export).
New-Item -ItemType Directory -Path (Split-Path $LogFile -Parent) -Force | Out-Null
$turnsLabel = if ($MaxTurns) { $MaxTurns } else { 'debate-preset (8)' }
$logBlock   = [System.Text.StringBuilder]::new()
[void]$logBlock.AppendLine("=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | conv#$convId | $count debaters | max_turns=$turnsLabel ===")
[void]$logBlock.AppendLine("topic: $Topic")
foreach ($a in $assign) {
    [void]$logBlock.AppendLine(("  {0,-12} <- {1}  [{2}]" -f $a.Cli, $a.PersonaName, [IO.Path]::GetFileName($a.PersonaFile)))
}
Add-Content -LiteralPath $LogFile -Value $logBlock.ToString() -Encoding UTF8

Write-Host ""
Write-Step "Done. Watch live:"
Write-Host "  http://127.0.0.1:8765/conversations/$convId" -ForegroundColor Green
Write-Host "  https://agent-chat.mikesailab.com/conversations/$convId" -ForegroundColor Green
Write-Step "Cast + topic logged to: $LogFile"
