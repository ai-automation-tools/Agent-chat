<#
.SYNOPSIS
  Stop the Agent-Chat local app — the web UI viewer and/or the db_sync sidecar.

.DESCRIPTION
  The counterpart to scripts/startup-app.ps1. Finds the processes that script
  starts and stops them, logging to db/startup-app.log so start and stop share
  one timeline.

  Identification mirrors startup-app.ps1 / start.ps1 exactly:
    * Web UI  -- a python.exe whose command line references THIS repo's
                 web_ui.py. Scoping to this clone matters: another clone on the
                 same machine runs its own, and stopping that one would be
                 someone else's outage. The test is the command line rather
                 than the interpreter path, because the venv's python.exe
                 re-execs the base interpreter -- the process that actually
                 serves reports C:\Python312\python.exe to WMI while running
                 as the venv, so an ExecutablePath test missed it entirely.
    * Sidecar -- a python.exe whose command line references db_sync.py, same
                 clone test.

  Deliberately does NOT touch spawned CLI agent windows. Those are conversation
  participants, not app infrastructure; killing one mid-run loses its turn and
  wedges the conversation on a seat that will never reply.

  Idempotent: stopping something already stopped is a no-op and exit 0.

.PARAMETER SkipSidecar
  Leave the sidecar running (stop only the web UI).

.PARAMETER SkipWebUI
  Leave the web UI running (stop only the sidecar).

.PARAMETER Wait
  Seconds to wait for a graceful exit before reporting (default 5).

.EXAMPLE
  .\scripts\stop-app.ps1
  # Stop both.

.EXAMPLE
  .\scripts\stop-app.ps1 -SkipSidecar
  # Stop the web UI, leave the sync running.
#>

[CmdletBinding()]
param(
    [switch] $SkipSidecar,
    [switch] $SkipWebUI,
    [int]    $Wait = 5
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Python      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDir      = Join-Path $ProjectRoot 'db'
$RunLog      = Join-Path $LogDir 'startup-app.log'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-RunLog {
    param([string] $Message, [string] $Level = 'INFO')
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "$ts [$Level] $Message"
    Add-Content -Path $RunLog -Value $line
    Write-Host $line
}

# Processes belonging to THIS clone: a python running $Marker from this repo.
# Identified by command line, NOT ExecutablePath -- see the .DESCRIPTION note.
function Get-AppProcess {
    param([string] $Marker)
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$Marker*" -and $_.CommandLine -like "*$ProjectRoot*" })
}

function Stop-AppProcess {
    param([string] $Label, [string] $Marker)
    $procs = Get-AppProcess -Marker $Marker
    if ($procs.Count -eq 0) { Write-RunLog "$Label`: not running -- nothing to stop"; return 0 }

    $pidList = ($procs | ForEach-Object { $_.ProcessId }) -join ', '
    Write-RunLog "$Label`: stopping PID $pidList"
    foreach ($p in $procs) {
        try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop }
        catch { Write-RunLog "$Label`: could not stop PID $($p.ProcessId) -- $($_.Exception.Message)" 'WARN' }
    }

    $deadline = (Get-Date).AddSeconds($Wait)
    while ((Get-Date) -lt $deadline -and (Get-AppProcess -Marker $Marker).Count -gt 0) {
        Start-Sleep -Milliseconds 250
    }
    $left = Get-AppProcess -Marker $Marker
    if ($left.Count -gt 0) {
        Write-RunLog "$Label`: still running after ${Wait}s (PID $(($left | ForEach-Object { $_.ProcessId }) -join ', '))" 'ERROR'
        return 1
    }
    Write-RunLog "$Label`: stopped"
    return 0
}

Write-RunLog "stop-app begin (root=$ProjectRoot, user=$env:USERNAME)"

$failed = 0
if ($SkipWebUI)   { Write-RunLog 'web UI: -SkipWebUI set, leaving it running' }
else              { $failed += Stop-AppProcess -Label 'web UI'  -Marker 'web_ui.py' }

if ($SkipSidecar) { Write-RunLog 'sidecar: -SkipSidecar set, leaving it running' }
else              { $failed += Stop-AppProcess -Label 'sidecar' -Marker 'db_sync.py' }

Write-RunLog "stop-app end (failures=$failed)"
exit $failed
