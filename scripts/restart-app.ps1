<#
.SYNOPSIS
  Restart the Agent-Chat local app — stop the web UI + sidecar, then bring them
  back up.

.DESCRIPTION
  Thin wrapper: scripts/stop-app.ps1 then scripts/startup-app.ps1. It exists
  because "restart" is the single most common operation on this app — every
  code change under src/web/ needs one, since web_ui.py runs uvicorn WITHOUT
  --reload and so serves whatever it imported at boot.

  Both halves log to db/startup-app.log, so a restart reads as one continuous
  story in that file.

  **Does not touch spawned CLI agent windows.** They talk to db/chat.db through
  their own MCP server processes; the web UI is only a viewer and a seeder, so
  restarting it cannot disturb a conversation in flight. The SSE view in any
  open browser tab reconnects on its own.

.PARAMETER SkipSidecar
  Restart only the web UI; leave the sidecar alone throughout.

.PARAMETER SkipWebUI
  Restart only the sidecar.

.PARAMETER SettleSeconds
  Pause between stop and start (default 2). Gives the OS time to release port
  8765, without which the new web UI can fail to bind.

.EXAMPLE
  .\scripts\restart-app.ps1
  # The everyday one: pick up code changes under src/.
#>

[CmdletBinding()]
param(
    [switch] $SkipSidecar,
    [switch] $SkipWebUI,
    [int]    $SettleSeconds = 2
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$StopScript  = Join-Path $ProjectRoot 'scripts\stop-app.ps1'
$StartScript = Join-Path $ProjectRoot 'scripts\startup-app.ps1'
$RunLog      = Join-Path $ProjectRoot 'db\startup-app.log'
$Pwsh        = (Get-Process -Id $PID).Path

function Write-RunLog {
    param([string] $Message, [string] $Level = 'INFO')
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "$ts [$Level] $Message"
    Add-Content -Path $RunLog -Value $line
    Write-Host $line
}

foreach ($s in @($StopScript, $StartScript)) {
    if (-not (Test-Path $s)) { Write-RunLog "restart-app: missing $s -- aborting" 'ERROR'; exit 3 }
}

Write-RunLog "restart-app begin"

$fwd = @()
if ($SkipSidecar) { $fwd += '-SkipSidecar' }
if ($SkipWebUI)   { $fwd += '-SkipWebUI' }

# Child processes so a non-zero `exit` in either half can't kill this script
# before the other half runs -- a failed stop must still be followed by a start,
# or a restart that half-worked leaves the app down.
& $Pwsh -NoProfile -ExecutionPolicy Bypass -File $StopScript @fwd
$stopCode = $LASTEXITCODE
if ($stopCode -ne 0) { Write-RunLog "restart-app: stop reported $stopCode -- starting anyway" 'WARN' }

if ($SettleSeconds -gt 0) { Start-Sleep -Seconds $SettleSeconds }

& $Pwsh -NoProfile -ExecutionPolicy Bypass -File $StartScript @fwd
$startCode = $LASTEXITCODE

Write-RunLog "restart-app end (stop=$stopCode start=$startCode)"
exit $startCode
