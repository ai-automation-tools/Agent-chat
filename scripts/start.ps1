<#
.SYNOPSIS
  Convenience wrapper: ensure db_sync.py sidecar is running, then seed a new conversation.

.DESCRIPTION
  Checks whether the local DB-sync sidecar is already running. If not, launches it
  hidden in the background, with logs routed to db/db_sync.log via the sidecar's
  --log-file flag. After launching, tails the log file inline for 10 seconds so
  startup banner / immediate failures are visible in this terminal — then detaches.
  Then forwards all remaining arguments to src/start_conversation.py.

  Tail the live log later with:
    Get-Content -Wait db\db_sync.log

.EXAMPLE
  .\scripts\start.ps1 --db-path db\chat.db --topic "..." --participants claude-code,gemini `
                      --first claude-code --mode turns --max-turns 6

.EXAMPLE
  # Kill any existing sidecar(s) and relaunch a fresh one — no seed.
  .\scripts\start.ps1 -Force -SidecarOnly
#>

[CmdletBinding()]
param(
    [switch] $Force,
    [switch] $SidecarOnly,
    # Typed [object[]] not [string[]] so that PowerShell preserves command-line
    # array literals like `claude-code,gemini` as nested Object[] entries
    # (instead of stringifying them as space-joined "claude-code gemini",
    # which breaks --participants in start_conversation.py). The forwarding
    # block below re-joins those sub-arrays with commas before splatting.
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]] $StartArgs
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Python      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$SyncScript  = Join-Path $ProjectRoot 'scripts\db_sync.py'
$SeedScript  = Join-Path $ProjectRoot 'src\start_conversation.py'
$LogFile     = Join-Path $ProjectRoot 'db\db_sync.log'
$TailSeconds = 10

if (-not (Test-Path $Python))     { throw "venv python not found at $Python" }
if (-not (Test-Path $SyncScript)) { throw "sidecar not found at $SyncScript" }
if (-not (Test-Path $SeedScript)) { throw "seeder not found at $SeedScript" }

# Each invocation of the venv python on Windows creates *two* python.exe
# processes: the venv launcher (.venv\Scripts\python.exe) and its child, the
# real interpreter (typically C:\Python312\python.exe). Both match the
# 'db_sync.py' command line. We count *only the venv launcher* as the logical
# sidecar — its system-python child is normal Windows venv behavior, not a
# duplicate. See docs/db-sync.md "Multiple sidecars running" for details.
$venvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

function Stop-SidecarTree {
    param([Parameter(Mandatory)] [int] $LauncherPid)
    # Resolve the parent pwsh window (if any) BEFORE killing the launcher —
    # once the launcher exits, ParentProcessId becomes stale (Windows does
    # not refresh it on parent death). We only target a `-NoExit` pwsh
    # whose command line references db_sync.py — i.e. one of the launcher
    # windows we spawned via Start-Process — so the user's interactive
    # shell can never be killed by mistake.
    $parentPwshPid = $null
    $launcher = Get-CimInstance Win32_Process -Filter "ProcessId = $LauncherPid" -ErrorAction SilentlyContinue
    if ($launcher) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($launcher.ParentProcessId)" -ErrorAction SilentlyContinue
        if ($parent -and ($parent.Name -eq 'pwsh.exe' -or $parent.Name -eq 'powershell.exe') -and
            $parent.CommandLine -like '*-NoExit*' -and $parent.CommandLine -like '*db_sync.py*') {
            $parentPwshPid = $parent.ProcessId
        }
    }
    # Kill child python processes first so they don't survive as orphans.
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' AND ParentProcessId = $LauncherPid" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $LauncherPid -Force -ErrorAction SilentlyContinue
    # Close the spawned -NoExit launcher window, if we identified one.
    if ($parentPwshPid) {
        Stop-Process -Id $parentPwshPid -Force -ErrorAction SilentlyContinue
    }
}

$running = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -like '*db_sync.py*' -and
        $_.ExecutablePath -ieq $venvPython
    })

if ($running.Count -gt 1) {
    $pidList = ($running | ForEach-Object { $_.ProcessId }) -join ', '
    if ($Force) {
        Write-Host "[start] -Force: killing $($running.Count) sidecar launchers + children ($pidList)" -ForegroundColor Yellow
        $running | ForEach-Object { Stop-SidecarTree -LauncherPid $_.ProcessId }
        Start-Sleep -Seconds 1
        $running = @()
    } else {
        Write-Host "[start] WARNING: $($running.Count) venv-launcher sidecars are running ($pidList)." -ForegroundColor Red
        Write-Host "        They will race on db/.sync-state.json. Re-run with -Force to kill all and relaunch." -ForegroundColor Red
        exit 1
    }
}

if ($running.Count -eq 1) {
    if ($Force) {
        Write-Host "[start] -Force: killing existing sidecar tree (launcher PID $($running[0].ProcessId)) and relaunching" -ForegroundColor Yellow
        Stop-SidecarTree -LauncherPid $running[0].ProcessId
        Start-Sleep -Seconds 1
        $running = @()
    } else {
        Write-Host "[start] sidecar already running (launcher PID $($running[0].ProcessId))" -ForegroundColor Green
    }
}

if ($running.Count -eq 0) {
    Write-Host "[start] launching sidecar (hidden) → log: $LogFile" -ForegroundColor Yellow

    # Capture pre-launch log size so the inline tail only shows fresh output.
    $preLaunchSize = if (Test-Path $LogFile) { (Get-Item $LogFile).Length } else { 0 }

    # Ensure the log dir exists (Python side also does this, but creating
    # it here lets the tail loop assume the file path is reachable).
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

    # -WindowStyle Hidden = no visible console window. -PassThru returns the
    # Process object so we can poll HasExited during the inline tail.
    $proc = Start-Process -FilePath $Python `
        -ArgumentList @($SyncScript, '--log-file', $LogFile) `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru

    Write-Host "[start] sidecar PID $($proc.Id), tailing log for $TailSeconds`s..." -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds($TailSeconds)
    $cursor = $preLaunchSize
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            Write-Host "[start] sidecar exited early (code $($proc.ExitCode)) — full log below:" -ForegroundColor Red
            if (Test-Path $LogFile) { Get-Content $LogFile }
            exit 4
        }
        if (Test-Path $LogFile) {
            $size = (Get-Item $LogFile).Length
            if ($size -gt $cursor) {
                # Open with FileShare.ReadWrite so we don't fight the writer.
                $stream = [System.IO.File]::Open($LogFile, 'Open', 'Read', 'ReadWrite')
                try {
                    [void] $stream.Seek($cursor, 'Begin')
                    $reader = [System.IO.StreamReader]::new($stream)
                    $chunk = $reader.ReadToEnd()
                    if ($chunk) { Write-Host -NoNewline $chunk }
                    $reader.Dispose()
                } finally { $stream.Dispose() }
                $cursor = $size
            }
        }
        Start-Sleep -Milliseconds 250
    }

    Write-Host "[start] sidecar still running — detaching. Tail live with: Get-Content -Wait '$LogFile'" -ForegroundColor Green
}

if ($SidecarOnly) {
    exit 0
}

if (-not $StartArgs -or $StartArgs.Count -eq 0) {
    Write-Host "[start] no seed args supplied. Pass --topic etc. or use -SidecarOnly." -ForegroundColor Red
    exit 2
}

Write-Host "[start] seeding conversation..." -ForegroundColor Cyan

# Re-join nested arrays back into comma-separated strings before forwarding.
# PowerShell parses `a,b` on the command line as the array @('a','b'); we
# preserve the user's intent by stringifying it back to "a,b".
$forwardedArgs = @()
foreach ($a in $StartArgs) {
    if ($a -is [array]) { $forwardedArgs += ($a -join ',') }
    else                { $forwardedArgs += [string] $a }
}

& $Python $SeedScript @forwardedArgs
exit $LASTEXITCODE
