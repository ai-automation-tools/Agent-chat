<#
.SYNOPSIS
  Check that the Agent-Chat web UI and db_sync sidecar are alive, and bring
  back whatever isn't.

.DESCRIPTION
  Run on a timer by the "\Agent-Chat\Healthcheck-AgentChat-App" scheduled task.
  Safe and cheap to run by hand.

  Two checks, deliberately different in kind:

    * Web UI  -- an HTTP GET of http://127.0.0.1:8765/, AND one of a real
                 conversation page. A *process* check is not enough: uvicorn
                 can be running and still not serving (bind failure, an
                 exception during startup). Nor is the homepage enough -- it
                 renders no agent Markdown, so a broken renderer leaves it
                 answering 200 while every transcript 500s. That happened:
                 a server started with the system interpreter had no
                 `linkify-it-py`, and this check called it healthy for as
                 long as it ran.
    * Sidecar -- a process check. It has no listening port to probe, and a
                 synthetic push would write real rows to the hosted mirror.

  Repair is delegated to scripts/startup-app.ps1, which is idempotent and
  already knows how to launch each half. A web UI that is running but not
  answering is stopped first, since startup-app.ps1 skips launching when it
  sees the process.

  **Never touches spawned CLI agent windows.** Those are conversation
  participants; a health check that killed one would end a live debate.

  Logs to db/healthcheck.log -- separate from startup-app.log so a timer firing
  every few minutes cannot bury the start/stop history in noise.

.PARAMETER SkipConversations
  Skip the stalled-conversation check (processes only).

.PARAMETER Repair
  Attempt to restart anything found down (default: on). -Repair:$false makes
  this a pure probe, which is what you want when diagnosing by hand.

.PARAMETER TimeoutSeconds
  HTTP probe timeout (default 10).

.EXAMPLE
  .\scripts\healthcheck-app.ps1 -Repair:$false
  # Report only.
#>

[CmdletBinding()]
param(
    [switch] $Repair = $true,
    [int]    $TimeoutSeconds = 10,
    [switch] $SkipConversations
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Python      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$StartScript = Join-Path $ProjectRoot 'scripts\startup-app.ps1'
$StopScript  = Join-Path $ProjectRoot 'scripts\stop-app.ps1'
$LogDir      = Join-Path $ProjectRoot 'db'
$HealthLog   = Join-Path $LogDir 'healthcheck.log'
$WebUrl      = 'http://127.0.0.1:8765/'
$Pwsh        = (Get-Process -Id $PID).Path

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-HealthLog {
    param([string] $Message, [string] $Level = 'INFO')
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "$ts [$Level] $Message"
    Add-Content -Path $HealthLog -Value $line
    Write-Host $line
}

# Identify OUR processes by the command line, not by ExecutablePath.
#
# `.venv\Scripts\python.exe` on Windows re-execs the base interpreter, so a
# perfectly healthy server runs as a CHILD whose WMI ExecutablePath is
# `C:\Python312\python.exe` — even though inside it `sys.executable` and
# `sys.prefix` are the venv's and it imports the venv's packages. Matching on
# ExecutablePath therefore missed the process that actually serves, which is
# how a half-working server sat on port 8765 unnoticed: nothing could see it,
# and startup-app.ps1 skips its launch while the port answers.
#
# The command line carries this clone's absolute script path, which is the
# thing we actually mean by "ours" — it distinguishes this checkout from
# another clone on the same machine (the reason the venv test existed) without
# depending on which of the two processes we catch.
function Get-AppProcess {
    param([string] $Marker)
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$Marker*" -and $_.CommandLine -like "*$ProjectRoot*" })
}

$problems = 0

# --- Web UI: does it actually answer? -------------------------------------
# Two requests, because they fail independently. The homepage proves the server
# is up; a conversation page proves it can render what an agent wrote, which is
# the only thing this app exists to show.
$webOk = $false
try {
    $r = Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec $TimeoutSeconds
    $webOk = ($r.StatusCode -eq 200)
    if (-not $webOk) { Write-HealthLog "web UI: HTTP $($r.StatusCode) from $WebUrl" 'WARN' }
} catch {
    Write-HealthLog "web UI: no answer from $WebUrl -- $($_.Exception.Message)" 'WARN'
}

if ($webOk) {
    # Newest conversation, found from the list page rather than the DB: this is
    # a probe of what a browser gets, and it must not need the venv to run.
    try {
        $list = Invoke-WebRequest -Uri "$WebUrl`conversations" -UseBasicParsing -TimeoutSec $TimeoutSeconds
        $m = [regex]::Match($list.Content, '/conversations/(\d+)')
        if (-not $m.Success) {
            Write-HealthLog 'web UI: no conversations yet -- transcript probe skipped'
        } else {
            $cid = $m.Groups[1].Value
            $t = Invoke-WebRequest -Uri "$WebUrl`conversations/$cid" -UseBasicParsing -TimeoutSec $TimeoutSeconds
            if ($t.StatusCode -eq 200) {
                Write-HealthLog "web UI: transcript #$cid renders (HTTP 200)"
            } else {
                $webOk = $false
                Write-HealthLog "web UI: transcript #$cid returned HTTP $($t.StatusCode)" 'WARN'
            }
        }
    } catch {
        # A 500 here is the case this probe exists for: the server is up and the
        # homepage is fine, but it cannot render a transcript.
        $webOk = $false
        Write-HealthLog "web UI: transcript page failed -- $($_.Exception.Message)" 'ERROR'
    }
}

if ($webOk) {
    Write-HealthLog 'web UI: OK (HTTP 200)'
} else {
    $problems++
    if (-not $Repair) {
        Write-HealthLog 'web UI: DOWN (-Repair off, leaving it)' 'ERROR'
    } else {
        # A process that is up but not answering will make startup-app.ps1 skip
        # the launch, so clear it out first.
        if ((Get-AppProcess -Marker 'web_ui.py').Count -gt 0) {
            Write-HealthLog 'web UI: process alive but not serving -- stopping it first' 'WARN'
            & $Pwsh -NoProfile -ExecutionPolicy Bypass -File $StopScript -SkipSidecar | Out-Null
        }
        # startup-app.ps1 skips its launch when the port is busy, so a holder
        # this script could not identify would make "restarting" a no-op that
        # still logged success. Say so instead.
        $held = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
        if ($held.Count -gt 0) {
            $owners = ($held | ForEach-Object { $_.OwningProcess } | Select-Object -Unique) -join ', '
            Write-HealthLog "web UI: port 8765 still held by PID $owners after the stop -- the restart below will be skipped; stop that process by hand" 'ERROR'
        }
        Write-HealthLog 'web UI: restarting'
        & $Pwsh -NoProfile -ExecutionPolicy Bypass -File $StartScript -SkipSidecar | Out-Null
        Start-Sleep -Seconds 3
        try {
            $r2 = Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec $TimeoutSeconds
            if ($r2.StatusCode -eq 200) { Write-HealthLog 'web UI: recovered (HTTP 200)'; $problems-- }
            else { Write-HealthLog "web UI: still unhealthy (HTTP $($r2.StatusCode))" 'ERROR' }
        } catch {
            Write-HealthLog "web UI: still down after restart -- $($_.Exception.Message)" 'ERROR'
        }
    }
}

# --- Sidecar: is the process there? ---------------------------------------
$sidecar = Get-AppProcess -Marker 'db_sync.py'
if ($sidecar.Count -gt 0) {
    Write-HealthLog "sidecar: OK (PID $(($sidecar | ForEach-Object { $_.ProcessId }) -join ', '))"
} else {
    $problems++
    if (-not $Repair) {
        Write-HealthLog 'sidecar: DOWN (-Repair off, leaving it)' 'ERROR'
    } else {
        Write-HealthLog 'sidecar: not running -- restarting'
        & $Pwsh -NoProfile -ExecutionPolicy Bypass -File $StartScript -SkipWebUI | Out-Null
        Start-Sleep -Seconds 2
        if ((Get-AppProcess -Marker 'db_sync.py').Count -gt 0) {
            Write-HealthLog 'sidecar: recovered'; $problems--
        } else {
            Write-HealthLog 'sidecar: still down after restart' 'ERROR'
        }
    }
}

# --- Stalled conversations -------------------------------------------------
# Different in kind from the two checks above: a quiet conversation is not an
# app fault and there is nothing here to restart. It rides this schedule
# because the schedule already exists and already runs as the interactive user
# -- adding a sixth task to run one read-only query would be worse.
#
# It NEVER touches an agent. A stalled run usually needs a human to click
# something in a CLI window, and "fixing" it by ending the conversation would
# destroy the run it was meant to rescue. Same rule the rest of these scripts
# follow: spawned CLI windows are participants, not infrastructure. So this
# does not add to $problems either -- the exit code stays a statement about the
# app, not about the agents.
if (-not $SkipConversations) {
    $inspect = Join-Path $ProjectRoot 'src\inspect_conversations.py'
    if ((Test-Path $Python) -and (Test-Path $inspect)) {
        try {
            # -Repair off => report only, so a dry run never fires a webhook.
            $args = @($inspect, 'watch')
            if (-not $Repair) { $args += '--quiet' }
            $out = & $Python @args 2>&1
            $stalled = $LASTEXITCODE
            if ($stalled -gt 0) {
                Write-HealthLog "conversations: $stalled stalled" 'WARN'
                foreach ($line in @($out)) {
                    if ("$line".Trim()) { Write-HealthLog "  $line" 'WARN' }
                }
            } else {
                Write-HealthLog 'conversations: none stalled'
            }
        } catch {
            Write-HealthLog "conversations: check failed -- $($_.Exception.Message)" 'WARN'
        }
    }
}

exit ([Math]::Max(0, $problems))
