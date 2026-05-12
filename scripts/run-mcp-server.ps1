<#
.SYNOPSIS
  Launch the agent_chat MCP server via the local venv, resolving the venv
  interpreter and server script relative to this launcher's own location.

.DESCRIPTION
  Each CLI registers this script as the MCP `command` instead of hardcoding
  the venv interpreter + agent_chat_mcp.py paths. The launcher reads
  --agent-id (positional, required) and forwards any additional flags
  (e.g. --db-path, custom env overrides) verbatim to the underlying
  Python process.

  Stdout is reserved for the MCP server's JSON-RPC stream. Diagnostic
  output (missing venv, missing server script) goes to stderr via
  Write-Error.

.PARAMETER AgentId
  The agent identity ("claude-code", "codex", "gemini", ...). Becomes the
  `--agent-id` value passed to agent_chat_mcp.py.

.EXAMPLE
  # Typical invocation (what an MCP loader runs):
  pwsh -NoProfile -File scripts\run-mcp-server.ps1 claude-code

.EXAMPLE
  # Override the DB path (the launcher forwards extra args verbatim):
  pwsh -NoProfile -File scripts\run-mcp-server.ps1 codex --db-path D:/custom/chat.db
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string] $AgentId,

    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]] $ExtraArgs
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Python   = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Server   = Join-Path $RepoRoot 'src\agent_chat_mcp.py'

if (-not (Test-Path $Python)) {
    Write-Error "venv python not found at $Python. Run: python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 2
}
if (-not (Test-Path $Server)) {
    Write-Error "MCP server script not found at $Server"
    exit 2
}

$forwarded = @()
if ($ExtraArgs) {
    foreach ($a in $ExtraArgs) {
        if ($a -is [array]) { $forwarded += $a }
        else                { $forwarded += [string] $a }
    }
}

& $Python $Server --agent-id $AgentId @forwarded
exit $LASTEXITCODE
