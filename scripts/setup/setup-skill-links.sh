#!/usr/bin/env bash
# setup-skill-links.sh -- Linux / macOS
#
# Recreate the per-machine symlinks each CLI tester agent uses to read the shared
# skills that live (canonically, git-tracked) at the repo-root skills/. The links
# sit under each CLI's own (gitignored) config dir inside agents/CLIs/, so they
# are never committed and every clone makes its own. Run once per fresh clone.
# Idempotent; safe to re-run.
#
# Other (unshared) skills already present in those dirs are left untouched -- this
# only manages the <name>s that exist under repo-root skills/.
#
# Modelled on AI-Automation-Library/script/setup/setup-skill-links.sh; the only
# differences are this repo's per-agent folder names and config-dir conventions.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"   # scripts/setup/ -> repo root
skills_dir="$repo/skills"
[ -d "$skills_dir" ] || { echo "No skills/ directory at $skills_dir" >&2; exit 1; }

# Each CLI tester workspace's skills directory (relative to the repo root). The
# relative symlink target climbs 5 levels (skills -> .../skills -> config dir ->
# <cli>_agent1 -> CLIs -> agents -> repo root) for all of them.
cli_skill_dirs=(
  "agents/CLIs/claude-code_agent1/.claude/skills"   # Claude Code  (reads .claude/skills)
  "agents/CLIs/codex_agent1/.codex/skills"          # Codex        (reads .codex/skills)
  "agents/CLIs/gemini_agent1/.gemini/skills"        # Gemini       (reads .gemini/skills; deprecated fallback)
  "agents/CLIs/antigravity_agent1/.agents/skills"   # Antigravity  (agent-skills standard -- .agents/skills)
)

for rel in "${cli_skill_dirs[@]}"; do
  base="$repo/$rel"
  mkdir -p "$base"
  for target in "$skills_dir"/*/; do
    name="$(basename "$target")"
    link="$base/$name"
    if [ -L "$link" ]; then
      rm "$link"
    elif [ -e "$link" ]; then
      echo "skip: $link is a real directory (not a link) -- remove it manually to relink."
      continue
    fi
    ln -s "../../../../../skills/$name" "$link"
    echo "linked $rel/$name -> skills/$name"
  done
done
