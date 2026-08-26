<#
.SYNOPSIS
  Nightly housekeeping: back up db/chat.db safely, prune old backups, and trim
  the app logs.

.DESCRIPTION
  Run by the "\Agent-Chat\Maintain-AgentChat-App" scheduled task. Safe by hand.

  **The backup uses SQLite's own backup API, not a file copy.** chat.db runs in
  WAL mode with several writers -- the web UI, the sidecar, and one MCP server
  per live agent. Copying the file while a transaction is in flight yields a
  torn database, and copying it *without* the -wal sidecar file silently loses
  every committed-but-not-checkpointed row. sqlite3.Connection.backup() takes a
  consistent snapshot with the writers still running.

  Worth having even though the sidecar mirrors to Fly: that sync carries
  conversations, messages and personas, but the battleground_arenas /
  battleground_drafts tables are deliberately excluded from it (captured
  third-party content must not leave this machine), so they exist in exactly
  one place until this task runs.

  Log trimming keeps the newest -MaxLogLines of each db/*.log. They are append-
  only and unbounded otherwise; a busy day adds thousands of lines.

.PARAMETER KeepDays
  Delete backups older than this (default 14).

.PARAMETER MaxLogLines
  Lines to keep per log file (default 5000). 0 disables trimming.

.PARAMETER SkipBackup
  Trim logs only.

.EXAMPLE
  .\scripts\maintain-app.ps1
#>

[CmdletBinding()]
param(
    [int]    $KeepDays = 14,
    [int]    $MaxLogLines = 5000,
    [switch] $SkipBackup
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Python      = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Db          = Join-Path $ProjectRoot 'db\chat.db'
$BackupDir   = Join-Path $ProjectRoot 'db\backups'
$LogDir      = Join-Path $ProjectRoot 'db'
$RunLog      = Join-Path $LogDir 'maintain-app.log'

function Write-RunLog {
    param([string] $Message, [string] $Level = 'INFO')
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line = "$ts [$Level] $Message"
    Add-Content -Path $RunLog -Value $line
    Write-Host $line
}

Write-RunLog "maintain-app begin (root=$ProjectRoot)"

# --- Backup ---------------------------------------------------------------
if ($SkipBackup) {
    Write-RunLog 'backup: -SkipBackup set, skipping'
} elseif (-not (Test-Path $Db)) {
    Write-RunLog "backup: no database at $Db -- nothing to back up" 'WARN'
} elseif (-not (Test-Path $Python)) {
    Write-RunLog "backup: venv python not found at $Python -- skipping" 'ERROR'
} else {
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }
    $stamp  = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $target = Join-Path $BackupDir "chat-$stamp.db"

    # Python rather than inline SQL: sqlite3's backup API is the only way to
    # snapshot a live WAL database consistently, and it reports progress.
    $py = @"
import sqlite3, sys
src = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
n = dst.execute('SELECT COUNT(*) FROM conversations').fetchone()[0]
m = dst.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
dst.close(); src.close()
print(f'{n} conversations, {m} messages')
"@
    try {
        $out = & $Python -c $py $Db $target 2>&1
        if ($LASTEXITCODE -eq 0 -and (Test-Path $target)) {
            $mb = [Math]::Round((Get-Item $target).Length / 1MB, 2)
            Write-RunLog "backup: $target ($mb MB) -- $out"
        } else {
            Write-RunLog "backup: FAILED -- $out" 'ERROR'
        }
    } catch {
        Write-RunLog "backup: FAILED -- $($_.Exception.Message)" 'ERROR'
    }

    # --- Prune ------------------------------------------------------------
    if ($KeepDays -gt 0) {
        $cutoff = (Get-Date).AddDays(-$KeepDays)
        $old = @(Get-ChildItem -Path $BackupDir -Filter 'chat-*.db' -ErrorAction SilentlyContinue |
                 Where-Object { $_.LastWriteTime -lt $cutoff })
        foreach ($f in $old) {
            try { Remove-Item $f.FullName -Force; Write-RunLog "prune: removed $($f.Name)" }
            catch { Write-RunLog "prune: could not remove $($f.Name) -- $($_.Exception.Message)" 'WARN' }
        }
        $kept = @(Get-ChildItem -Path $BackupDir -Filter 'chat-*.db' -ErrorAction SilentlyContinue).Count
        Write-RunLog "prune: $($old.Count) removed, $kept kept (KeepDays=$KeepDays)"
    }
}

# --- Log trimming ---------------------------------------------------------
if ($MaxLogLines -le 0) {
    Write-RunLog 'logs: trimming disabled'
} else {
    foreach ($log in @(Get-ChildItem -Path $LogDir -Filter '*.log' -ErrorAction SilentlyContinue)) {
        try {
            $lines = @(Get-Content -Path $log.FullName -ErrorAction Stop)
            if ($lines.Count -gt $MaxLogLines) {
                $keep = $lines[-$MaxLogLines..-1]
                Set-Content -Path $log.FullName -Value $keep -Encoding UTF8
                Write-RunLog "logs: trimmed $($log.Name) $($lines.Count) -> $MaxLogLines lines"
            }
        } catch {
            # A log held open by a running process is normal -- skip it quietly.
            Write-RunLog "logs: skipped $($log.Name) -- $($_.Exception.Message)" 'WARN'
        }
    }
}

Write-RunLog 'maintain-app end'
exit 0
