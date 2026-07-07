<#
.SYNOPSIS
  Startup launcher for the Agent-Chat local app. Brings up the web UI viewer
  (http://127.0.0.1:8765) and the db_sync sidecar, both hidden.

.DESCRIPTION
  Intended to be run by the "\Agent-Chat\Start-AgentChat-App" Windows Task
  Scheduler job at user logon (register it with
  scripts/setup/register-startup-task.ps1). Safe to run by hand too.

  Idempotent:
    * Web UI  -- skipped if port 8765 is already listening, or a venv-python
                 web_ui.py process is already running.
    * Sidecar -- delegated to scripts/start.ps1 -SidecarOnly, which has its
                 own duplicate-guard (won't spawn a second racing sidecar).

  Logs each run to db/startup-app.log. The web UI's own stdout/stderr go to
  db/web_ui.out.log / db/web_ui.err.log; the sidecar logs to db/db_sync.log
  (via start.ps1). Nothing writes to the console -- the task runs hidden.

.PARAMETER SkipSidecar
  Bring up only the web UI (don't touch the sidecar).

.PARAMETER SkipWebUI
  Bring up only the sidecar (don't touch the web UI).

.EXAMPLE
  .\scripts\startup-app.ps1
  # Ensure both the web UI and the sidecar are up.
#>

[CmdletBinding()]
param(
    [switch] $SkipSidecar,
    [switch] $SkipWebUI
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Python      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$WebUI       = Join-Path $ProjectRoot 'src\web_ui.py'
$StartScript = Join-Path $ProjectRoot 'scripts\start.ps1'
$LogDir      = Join-Path $ProjectRoot 'db'
$RunLog      = Join-Path $LogDir 'startup-app.log'
$WebOutLog   = Join-Path $LogDir 'web_ui.out.log'
$WebErrLog   = Join-Path $LogDir 'web_ui.err.log'
$WebPort     = 8765

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-RunLog {
    param([string] $Message, [string] $Level = 'INFO')
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "$ts [$Level] $Message"
    Add-Content -Path $RunLog -Value $line
    Write-Host $line
}

Write-RunLog "startup-app begin (root=$ProjectRoot, user=$env:USERNAME)"

if (-not (Test-Path $Python)) { Write-RunLog "venv python not found at $Python -- aborting" 'ERROR'; exit 3 }

# --- Web UI ---------------------------------------------------------------
if ($SkipWebUI) {
    Write-RunLog "web UI: -SkipWebUI set, skipping"
} else {
    $portBusy = @(Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue)
    $webRunning = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*web_ui.py*' -and $_.ExecutablePath -ieq $Python })

    if ($portBusy.Count -gt 0) {
        Write-RunLog "web UI: port $WebPort already listening -- assuming it's up, skipping launch"
    } elseif ($webRunning.Count -gt 0) {
        $pids = ($webRunning | ForEach-Object { $_.ProcessId }) -join ', '
        Write-RunLog "web UI: web_ui.py already running (PID $pids) -- skipping launch"
    } else {
        Write-RunLog "web UI: launching hidden -> http://127.0.0.1:$WebPort/ (logs: $WebOutLog / $WebErrLog)"
        try {
            $proc = Start-Process -FilePath $Python `
                -ArgumentList @($WebUI) `
                -WorkingDirectory $ProjectRoot `
                -WindowStyle Hidden `
                -RedirectStandardOutput $WebOutLog `
                -RedirectStandardError $WebErrLog `
                -PassThru
            Start-Sleep -Milliseconds 1500
            if ($proc.HasExited) {
                Write-RunLog "web UI: process exited early (code $($proc.ExitCode)) -- see $WebErrLog" 'ERROR'
            } else {
                Write-RunLog "web UI: started (PID $($proc.Id))"
            }
        } catch {
            Write-RunLog "web UI: launch failed -- $($_.Exception.Message)" 'ERROR'
        }
    }
}

# --- Sidecar --------------------------------------------------------------
# Delegated to start.ps1 -SidecarOnly (its own duplicate-guard + hidden launch
# + logging to db/db_sync.log). Run it in a child pwsh process so its `exit`
# codes can't terminate this script.
if ($SkipSidecar) {
    Write-RunLog "sidecar: -SkipSidecar set, skipping"
} elseif (-not (Test-Path $StartScript)) {
    Write-RunLog "sidecar: start.ps1 not found at $StartScript -- skipping" 'WARN'
} else {
    Write-RunLog "sidecar: ensuring up via start.ps1 -SidecarOnly"
    try {
        & (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File $StartScript -SidecarOnly *>> $RunLog
        Write-RunLog "sidecar: start.ps1 -SidecarOnly returned exit code $LASTEXITCODE"
    } catch {
        Write-RunLog "sidecar: start.ps1 invocation failed -- $($_.Exception.Message)" 'ERROR'
    }
}

Write-RunLog "startup-app end"
exit 0
