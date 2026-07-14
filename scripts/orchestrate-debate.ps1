<#
.SYNOPSIS
  Web-form spawn wrapper: launch one CLI per agent for an ALREADY-SEEDED
  conversation, prompting each in character.

.DESCRIPTION
  The counterpart to scripts/debate.ps1 for the web /orchestrate form. Where
  debate.ps1 picks a topic + personas and seeds the conversation itself, this
  script assumes the Python handler (POST /api/orchestrate) has ALREADY seeded
  the conversation row and resolved the persona cast. Its only job is step 6-7
  of debate.ps1 — write the per-agent prompt files and open one pwsh window per
  agent — using the shared helpers in lib/spawn-agents.ps1.

  All inputs arrive in a single JSON file (written by the handler under
  db/launch/) so nothing but a file path crosses the process boundary — the
  topic/persona bodies never have to survive command-line quoting. Shape:

      {
        "conversation_id": 42,
        "topic": "Should AI agents have persistent memory?",
        "skip_permissions": false,
        "agents": [
          { "cli": "claude-code", "persona_name": "Crypto Chad", "persona_body": "..." },
          { "cli": "codex",       "persona_name": "",            "persona_body": "" }
        ]
      }

  Agents are launched in array order (first entry = --first speaker). An agent
  with an empty persona_body is spawned with a plain (non-persona) prompt.

.PARAMETER AssignmentsFile
  Path to the JSON described above. Required.

.PARAMETER DryRun
  Build the launch plan and print it WITHOUT writing prompt files or opening
  windows. Mirrors debate.ps1 -DryRun.

.EXAMPLE
  .\scripts\orchestrate-debate.ps1 -AssignmentsFile db\launch\orch-42-ab12.json
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $AssignmentsFile,
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

$RepoRoot  = (Resolve-Path "$PSScriptRoot\..").Path
$LaunchDir = Join-Path $RepoRoot 'db\launch'
$SpawnLib  = Join-Path $PSScriptRoot 'lib\spawn-agents.ps1'

if (-not (Test-Path $SpawnLib))        { throw "spawn lib not found at $SpawnLib" }
if (-not (Test-Path $AssignmentsFile)) { throw "assignments file not found at $AssignmentsFile" }

# Shared CLI registry ($Clis) + prompt-file/spawn helpers.
. $SpawnLib

function Write-Step { param([string]$m) Write-Host "[orchestrate] $m" -ForegroundColor Cyan }
function Write-Pick { param([string]$m) Write-Host "              $m" -ForegroundColor Gray }

# --------------------------------------------------------------------------
# Parse the assignments file
# --------------------------------------------------------------------------
$spec = Get-Content -LiteralPath $AssignmentsFile -Raw -Encoding UTF8 | ConvertFrom-Json

$convId = $spec.conversation_id
$topic  = [string]$spec.topic
$skip   = [bool]$spec.skip_permissions
$agents = @($spec.agents)

if (-not $convId)      { throw "assignments file has no conversation_id" }
if (-not $topic)       { throw "assignments file has no topic" }
if ($agents.Count -lt 2) { throw "assignments file needs at least 2 agents, got $($agents.Count)" }

Write-Step "Conversation #$convId — $($agents.Count) agents"
Write-Step "Topic: $topic"

$spawnAssignments = foreach ($a in $agents) {
    if (-not $a.cli) { throw "an agent entry is missing its 'cli' id" }
    [pscustomobject]@{
        Cli         = [string]$a.cli
        PersonaName = [string]$a.persona_name
        PersonaBody = [string]$a.persona_body
    }
}
foreach ($a in $spawnAssignments) {
    $label = if ($a.PersonaName) { $a.PersonaName } else { '(no persona)' }
    Write-Pick ("{0,-12} <- {1}" -f $a.Cli, $label)
}
Write-Pick "first speaker: $($spawnAssignments[0].Cli)"

# --------------------------------------------------------------------------
# Write prompt files + build the launch plan (shared helper)
# --------------------------------------------------------------------------
$launchPlan = New-AgentLaunchPlan -Assignments $spawnAssignments -Topic $topic `
    -ConvId $convId -LaunchDir $LaunchDir -RepoRoot $RepoRoot `
    -SkipPermissions:$skip -DryRun:$DryRun

if ($DryRun) {
    Write-Step 'DRY RUN — launch plan (no windows opened):'
    foreach ($p in $launchPlan) {
        Write-Host ""
        Write-Host "  # $($p.Cli)" -ForegroundColor Yellow
        Write-Host "  prompt file : $($p.PromptFile)"
        Write-Host "  pwsh -NoExit -Command `"$($p.Command)`""
    }
    Write-Host ""
    Write-Step 'Re-run without -DryRun to launch for real.'
    return
}

# --------------------------------------------------------------------------
# Launch (first speaker first)
# --------------------------------------------------------------------------
Write-Step 'Launching CLIs (first speaker first)...'
foreach ($p in $launchPlan) { Write-Pick "opening window: $($p.Cli)" }
Invoke-AgentLaunch -LaunchPlan $launchPlan

Write-Host ""
Write-Step "Done. Watch live:"
Write-Host "  http://127.0.0.1:8765/conversations/$convId" -ForegroundColor Green
