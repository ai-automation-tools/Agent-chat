#!/usr/bin/env bash
#
# Launch the agent_chat MCP server via the local venv. Companion to
# scripts/run-mcp-server.ps1 — same contract, different shell.
#
# Usage:
#   ./scripts/run-mcp-server.sh <agent-id> [extra args forwarded to agent_chat_mcp.py]
#
# Stdout is reserved for the MCP server's JSON-RPC stream. Errors go to
# stderr. The script execs Python so the MCP loader's signal handling
# reaches the server directly.

set -euo pipefail

# Resolve the absolute directory containing this script, following symlinks.
SOURCE="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE" ]]; do
  DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON="$REPO_ROOT/.venv/bin/python"
SERVER="$REPO_ROOT/src/agent_chat_mcp.py"

if [[ ! -x "$PYTHON" ]]; then
  echo "venv python not found at $PYTHON. Run: python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt" >&2
  exit 2
fi
if [[ ! -f "$SERVER" ]]; then
  echo "MCP server script not found at $SERVER" >&2
  exit 2
fi

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <agent-id> [extra args forwarded to agent_chat_mcp.py]" >&2
  exit 2
fi

AGENT_ID="$1"
shift

exec "$PYTHON" "$SERVER" --agent-id "$AGENT_ID" "$@"
