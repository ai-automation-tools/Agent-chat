<#
.SYNOPSIS
  Register (or update) the Windows Task Scheduler jobs that operate the
  Agent-Chat local app: stop, restart, health check, and nightly maintenance.

.DESCRIPTION
  Creates these under Task Scheduler Library \ Agent-Chat \ :

      Stop-AgentChat-App         on demand   -- stop web UI + sidecar
      Restart-AgentChat-App      on demand   -- stop, then start
      Healthcheck-AgentChat-App  every N min -- probe, and repair what is down
      Maintain-AgentChat-App     daily       -- safe DB backup, prune, trim logs

  The logon task, Start-AgentChat-App, is NOT created here -- it belongs to
  scripts/setup/register-startup-task.ps1 and is left alone. This script warns
  if it is missing so a fresh clone knows to run the other one too.

  "On demand" means no trigger: the task exists so you can right-click -> Run in
  Task Scheduler, or `Start-ScheduledTask -TaskName Stop-AgentChat-App
  -TaskPath '\Agent-Chat\'`. That is worth having because it works from a
  locked-down shell, a remote session, or a shortcut, without needing to know
  where the repo lives.

  Principal matches the existing logon task: current user, Interactive logon
  (no stored password), RunLevel Limited (no admin needed). Interactive matters
  for the sidecar -- it reads AGENT_CHAT_INGEST_TOKEN from your user
  environment, which a SYSTEM-run task would not see.

  Every action is launched through scripts/run-hidden.vbs rather than pwsh.exe
  directly. Task Scheduler starts a console application by creating its conhost
  window first, so -WindowStyle Hidden arrives too late and the window flashes
  on the interactive desktop on every fire. wscript.exe is a windowless host and
  starts the child hidden outright, while still waiting on it so the exit code
  still reaches the task.

  Re-running updates in place. Use -Unregister to remove the four.

.PARAMETER Unregister
  Remove the tasks this script creates (leaves Start-AgentChat-App alone).

.PARAMETER HealthcheckMinutes
  Health-check interval (default 60). 0 registers it on demand only. The probe
  exists to catch a crashed web UI, not to measure uptime -- hourly is enough,
  and a tighter loop only adds noise to db/healthcheck.log.

.PARAMETER MaintenanceTime
  Daily maintenance time, HH:mm (default 03:30).

.EXAMPLE
  .\scripts\setup\register-app-tasks.ps1

.EXAMPLE
  .\scripts\setup\register-app-tasks.ps1 -HealthcheckMinutes 5
#>

[CmdletBinding()]
param(
    [switch] $Unregister,
    [int]    $HealthcheckMinutes = 60,
    [string] $MaintenanceTime = '03:30'
)

$ErrorActionPreference = 'Stop'

$TaskPath    = '\Agent-Chat\'
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$Pwsh        = (Get-Process -Id $PID).Path
$Wscript     = Join-Path $env:SystemRoot 'System32\wscript.exe'
$RunHidden   = Join-Path $ProjectRoot 'scripts\run-hidden.vbs'

$Tasks = @(
    @{ Name = 'Stop-AgentChat-App'
       Script = 'scripts\stop-app.ps1'
       Desc = 'Stop the Agent-Chat web UI and db_sync sidecar. On demand (no trigger). See scripts/stop-app.ps1.' }
    @{ Name = 'Restart-AgentChat-App'
       Script = 'scripts\restart-app.ps1'
       Desc = 'Restart the Agent-Chat web UI and sidecar -- needed after any change under src/, since web_ui.py runs uvicorn without --reload. On demand. See scripts/restart-app.ps1.' }
    @{ Name = 'Healthcheck-AgentChat-App'
       Script = 'scripts\healthcheck-app.ps1'
       Desc = 'Probe http://127.0.0.1:8765/ and the sidecar process; restart whatever is down. See scripts/healthcheck-app.ps1.' }
    @{ Name = 'Maintain-AgentChat-App'
       Script = 'scripts\maintain-app.ps1'
       Desc = 'Nightly: consistent SQLite backup of db/chat.db, prune old backups, trim db/*.log. See scripts/maintain-app.ps1.' }
)

# ---------------------------------------------------------------- unregister
if ($Unregister) {
    foreach ($t in $Tasks) {
        $existing = Get-ScheduledTask -TaskName $t.Name -TaskPath $TaskPath -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $t.Name -TaskPath $TaskPath -Confirm:$false
            Write-Host "removed  $TaskPath$($t.Name)"
        } else {
            Write-Host "absent   $TaskPath$($t.Name)"
        }
    }
    Write-Host "`nStart-AgentChat-App left alone -- remove it with register-startup-task.ps1 -Unregister."
    exit 0
}

# ------------------------------------------------------------------ register
foreach ($t in $Tasks) {
    $script = Join-Path $ProjectRoot $t.Script
    if (-not (Test-Path $script)) { throw "script not found: $script" }
}
if (-not (Test-Path $RunHidden)) { throw "launcher not found: $RunHidden" }

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                                        -LogonType Interactive -RunLevel Limited

# Wake-to-run off, and don't start on battery -- this is a local dev app, not
# something worth spinning a sleeping laptop up for.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                                         -DontStopIfGoingOnBatteries `
                                         -StartWhenAvailable `
                                         -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
                                         -MultipleInstances IgnoreNew

foreach ($t in $Tasks) {
    $script = Join-Path $ProjectRoot $t.Script
    # wscript, not pwsh -- see the note at the top about the conhost flash.
    $action = New-ScheduledTaskAction -Execute $Wscript `
        -Argument "`"$RunHidden`" `"$script`"" `
        -WorkingDirectory $ProjectRoot

    $triggers = @()
    switch ($t.Name) {
        'Healthcheck-AgentChat-App' {
            if ($HealthcheckMinutes -gt 0) {
                # Repeating trigger: start a minute out so registering doesn't
                # immediately fire one, then repeat effectively forever.
                $tr = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
                        -RepetitionInterval (New-TimeSpan -Minutes $HealthcheckMinutes) `
                        -RepetitionDuration (New-TimeSpan -Days 3650)
                $triggers += $tr
            }
        }
        'Maintain-AgentChat-App' {
            $triggers += New-ScheduledTaskTrigger -Daily -At $MaintenanceTime
        }
    }

    $params = @{
        TaskName    = $t.Name
        TaskPath    = $TaskPath
        Action      = $action
        Principal   = $principal
        Settings    = $settings
        Description = $t.Desc
        Force       = $true
    }
    if ($triggers.Count -gt 0) { $params['Trigger'] = $triggers }

    Register-ScheduledTask @params | Out-Null
    $when = if ($triggers.Count -gt 0) {
        if ($t.Name -like 'Health*') { "every $HealthcheckMinutes min" } else { "daily $MaintenanceTime" }
    } else { 'on demand' }
    Write-Host ("registered  {0,-28} {1}" -f $t.Name, $when)
}

# The logon task is someone else's job -- say so rather than silently not doing it.
$start = Get-ScheduledTask -TaskName 'Start-AgentChat-App' -TaskPath $TaskPath -ErrorAction SilentlyContinue
if ($start) {
    Write-Host ("present     {0,-28} {1}" -f 'Start-AgentChat-App', 'at logon (register-startup-task.ps1)')
} else {
    Write-Warning 'Start-AgentChat-App is NOT registered. Run: .\scripts\setup\register-startup-task.ps1'
}

Write-Host "`nRun one now : Start-ScheduledTask -TaskName Restart-AgentChat-App -TaskPath '$TaskPath'"
Write-Host "Remove these: .\scripts\setup\register-app-tasks.ps1 -Unregister"
