# setup-skill-links.ps1 -- Windows
#
# Recreate the per-machine links each CLI tester agent uses to read the shared
# skills that live (canonically, git-tracked) at the repo-root skills/. The links
# sit under each CLI's own (gitignored) config dir inside agents/CLIs/, so they
# are never committed and every clone makes its own. Run once per fresh clone.
# Idempotent; safe to re-run.
#
# Junctions need no admin rights or Developer Mode, and the CLIs read through them
# transparently. Other (unshared) skills already present in those dirs are left
# untouched -- this only manages the <name>s that exist under repo-root skills/.
#
# Modelled on AI-Automation-Library/script/setup/setup-skill-links.ps1; the only
# differences are this repo's per-agent folder names and config-dir conventions.

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path   # scripts/setup/ -> repo root
$skillsDir = Join-Path $repo "skills"
if (-not (Test-Path $skillsDir)) { throw "No skills/ directory at $skillsDir" }

# Each CLI tester workspace's skills directory (relative to the repo root). Each
# path is the config dir that CLI natively discovers skills in AND is gitignored
# in this repo, so the junctions stay out of version control:
#   .claude/  .codex/  .gemini/  are ignored globally;
#   antigravity's .agents/* is ignored except mcp_config.json.
# The repo-root .claude/skills is this project's own Claude Code session config
# dir -- linking there lets the developer driving this repo use the same skills.
$cliSkillDirs = @(
    ".claude\skills",                                  # Claude Code  (this repo's own session -- repo-root .claude/skills)
    "agents\CLIs\claude-code_agent1\.claude\skills",   # Claude Code  (reads .claude/skills)
    "agents\CLIs\codex_agent1\.codex\skills",          # Codex        (reads .codex/skills)
    "agents\CLIs\gemini_agent1\.gemini\skills",        # Gemini       (reads .gemini/skills; deprecated fallback)
    "agents\CLIs\antigravity_agent1\.agents\skills"    # Antigravity  (agent-skills standard -- .agents/skills)
)
$names = (Get-ChildItem $skillsDir -Directory).Name

foreach ($rel in $cliSkillDirs) {
    $base = Join-Path $repo $rel
    New-Item -ItemType Directory -Force $base | Out-Null
    foreach ($name in $names) {
        $link = Join-Path $base $name
        $target = Join-Path $skillsDir $name
        $item = Get-Item $link -Force -ErrorAction SilentlyContinue
        if ($item) {
            if ($item.LinkType) {
                (Get-Item $link -Force).Delete()   # remove the existing junction/symlink only
            } else {
                Write-Warning "$link is a real directory (not a link) -- skipping. Remove it manually to relink."
                continue
            }
        }
        New-Item -ItemType Junction -Path $link -Target $target | Out-Null
        Write-Host "linked $rel\$name -> skills\$name"
    }
}
