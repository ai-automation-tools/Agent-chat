<#
.SYNOPSIS
  Register (or update) the Windows Task Scheduler job that brings up the
  Agent-Chat local app (web UI + db_sync sidecar) at user logon.

.DESCRIPTION
  Creates a scheduled task at:

      Task Scheduler Library \ Agent-Chat \ Start-AgentChat-App

  Trigger : At log on of the current user (runs with your interactive token,
            so your setx env vars -- AGENT_CHAT_INGEST_TOKEN etc. -- are
            visible to the sidecar).
  Action  : pwsh -File <repo>\scripts\startup-app.ps1  (hidden)
  Principal: current user, Interactive logon (no stored password needed),
             RunLevel Limited (no admin rights required at run time).

  Re-running this script updates the existing task in place. Use -Unregister
  to remove it (leaves the empty \Agent-Chat\ folder behind, which is fine).

.PARAMETER Unregister
  Remove the task instead of creating it.

.PARAMETER StartDelaySeconds
  Seconds to wait after logon before firing (default 15). Gives the desktop /
  network a moment to settle before the sidecar's first HTTPS tick.

.EXAMPLE
  .\scripts\setup\register-startup-task.ps1
  # Create/update the logon task.

.EXAMPLE
  .\scripts\setup\register-startup-task.ps1 -Unregister
  # Remove the task.
#>

[CmdletBinding()]
param(
    [switch] $Unregister,
    [int]    $StartDelaySeconds = 15
)

$ErrorActionPreference = 'Stop'

$TaskName = 'Start-AgentChat-App'
$TaskPath = '\Agent-Chat\'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$Launcher    = Join-Path $ProjectRoot 'scripts\startup-app.ps1'
$Pwsh        = (Get-Process -Id $PID).Path   # the pwsh running this script
$UserId      = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path $Launcher)) { throw "launcher not found at $Launcher" }

function Get-ExistingTask {
    Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
}

if ($Unregister) {
    if (Get-ExistingTask) {
        Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
        Write-Host "[register] removed $TaskPath$TaskName" -ForegroundColor Yellow
    } else {
        Write-Host "[register] no task at $TaskPath$TaskName -- nothing to remove" -ForegroundColor DarkGray
    }
    return
}

# --- Action: run the launcher hidden via pwsh -----------------------------
$argline = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`""
$action = New-ScheduledTaskAction -Execute $Pwsh -Argument $argline -WorkingDirectory $ProjectRoot

# --- Trigger: at logon of THIS user, with a short settle delay -------------
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
if ($StartDelaySeconds -gt 0) {
    # New-ScheduledTaskTrigger has no -Delay for AtLogOn; set it on the object.
    $trigger.Delay = "PT${StartDelaySeconds}S"
}

# --- Principal: run as this user, interactive, no elevation ----------------
$principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited

# --- Settings: resilient background startup task ---------------------------
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$desc = 'Brings up the Agent-Chat local web UI (127.0.0.1:8765) and the db_sync sidecar at logon. See scripts/startup-app.ps1.'

if (Get-ExistingTask) {
    Write-Host "[register] updating existing $TaskPath$TaskName" -ForegroundColor Cyan
} else {
    Write-Host "[register] creating $TaskPath$TaskName" -ForegroundColor Cyan
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $desc `
    -Force | Out-Null

Write-Host "[register] done." -ForegroundColor Green
Write-Host "  User    : $UserId (Interactive, at logon, +${StartDelaySeconds}s delay)" -ForegroundColor Gray
Write-Host "  Runs    : $Pwsh $argline" -ForegroundColor Gray
Write-Host "  WorkDir : $ProjectRoot" -ForegroundColor Gray
Write-Host ""
Write-Host "  Test now : Start-ScheduledTask -TaskPath '$TaskPath' -TaskName '$TaskName'" -ForegroundColor Gray
Write-Host "  Inspect  : taskschd.msc  ->  Task Scheduler Library \ Agent-Chat" -ForegroundColor Gray
Write-Host "  Remove   : .\scripts\setup\register-startup-task.ps1 -Unregister" -ForegroundColor Gray
