"""Orchestrator package — debate-launch surface for the agent_chat MCP server.

Phase 2a (this module set):
- ``seeding`` — reusable ``seed_conversation()`` extracted from
  ``start_conversation.py:main()``. Called by both the CLI entrypoint and the
  Web UI form handler so there is a single source of truth for the seeding SQL.
- ``preflight`` — per-CLI configuration checks. Validates that each selected
  CLI has the ``agent_chat`` MCP server registered in the right config file at
  the expected location with a launcher path that resolves. Returns structured
  results suitable for both the Web UI's red-panel re-render and the per-run
  ``logs/orchestrator-<timestamp>.log`` audit file.

Phase 2b (not yet implemented):
- personality bundle picker (reads ``agents/Debate-Agents/``)
- CLI spawning via a PowerShell wrapper invoked from the Python orchestrator
"""

from __future__ import annotations
