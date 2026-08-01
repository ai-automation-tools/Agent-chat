<#
.SYNOPSIS
  Stage the AgentBattleground browser extension for a target browser.

.DESCRIPTION
  Chrome loads extension/ directly -- manifest.json is already its manifest, so
  "Load unpacked" needs no build step and this script is only useful there for
  producing a zip.

  Firefox is a real port, not a copy: MV3 on Gecko has no chrome.sidePanel (it
  uses sidebar_action), takes a background `scripts` array rather than a service
  worker, and wants a browser_specific_settings id. Those differences live in
  extension/manifest.firefox.json; this script assembles a loadable folder from
  that manifest plus the shared src/ and icons/.

  Output goes to extension/dist/<browser>/ (gitignored). Load it with
  about:debugging -> This Firefox -> Load Temporary Add-on -> pick its
  manifest.json.

.PARAMETER Browser
  chrome or firefox. Default: firefox (the one that actually needs staging).

.PARAMETER Zip
  Also produce extension/dist/agentbattleground-<browser>-<version>.zip.

.EXAMPLE
  .\scripts\build-extension.ps1
  # Stage the Firefox build into extension/dist/firefox/.

.EXAMPLE
  .\scripts\build-extension.ps1 -Browser chrome -Zip
  # Stage Chrome and zip it for sharing.
#>

[CmdletBinding()]
param(
    [ValidateSet('chrome', 'firefox')]
    [string] $Browser = 'firefox',

    [switch] $Zip
)

$ErrorActionPreference = 'Stop'

$ProjectRoot   = (Resolve-Path "$PSScriptRoot\..").Path
$ExtensionRoot = Join-Path $ProjectRoot 'extension'
$OutRoot       = Join-Path $ExtensionRoot 'dist'
$OutDir        = Join-Path $OutRoot $Browser

$Manifest = if ($Browser -eq 'firefox') {
    Join-Path $ExtensionRoot 'manifest.firefox.json'
} else {
    Join-Path $ExtensionRoot 'manifest.json'
}

if (-not (Test-Path $Manifest)) {
    throw "Missing manifest for '$Browser': $Manifest"
}

# Fail loudly on a malformed manifest here rather than in the browser's
# "could not be installed" dialog.
$manifestJson = Get-Content -Raw -Path $Manifest | ConvertFrom-Json
$version      = $manifestJson.version

if (Test-Path $OutDir) {
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Copy-Item -Recurse -Force (Join-Path $ExtensionRoot 'src')   $OutDir
Copy-Item -Recurse -Force (Join-Path $ExtensionRoot 'icons') $OutDir
Copy-Item -Force $Manifest (Join-Path $OutDir 'manifest.json')

# The icon generator is a repo tool, not part of the shipped add-on.
Remove-Item -Force (Join-Path $OutDir 'icons\make_icons.py') -ErrorAction SilentlyContinue

Write-Host "Staged $Browser build v$version -> $OutDir"

if ($Zip) {
    $zipPath = Join-Path $OutRoot "agentbattleground-$Browser-$version.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Compress-Archive -Path (Join-Path $OutDir '*') -DestinationPath $zipPath
    Write-Host "Zipped -> $zipPath"
}

if ($Browser -eq 'firefox') {
    Write-Host ''
    Write-Host 'Load it: about:debugging#/runtime/this-firefox -> Load Temporary Add-on'
    Write-Host "         -> $(Join-Path $OutDir 'manifest.json')"
}
