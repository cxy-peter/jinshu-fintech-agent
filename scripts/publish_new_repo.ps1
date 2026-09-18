# Run locally, after reviewing the included original-code license/redistribution rights.
# Requires Git and GitHub CLI, authenticated by YOU. Never paste a token into this script.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Repo = "cxy-peter/jinshu-fintech-agent"
& gh auth status
if ($LASTEXITCODE -ne 0) { throw "Run gh auth login first" }
& python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
& python scripts/verify_source.py
if ($LASTEXITCODE -ne 0) { throw "Source verification failed" }
& gh repo view $Repo --json name 2>$null
if ($LASTEXITCODE -eq 0) { throw "Repository already exists. This script never overwrites an existing project." }
if (Test-Path .git) { throw "Existing .git found. Review manually; automatic publication stopped." }
if ((Read-Host "Confirm private publication of reviewed source (type PRIVATE)") -ne "PRIVATE") { exit 1 }
& git init -b main
& git add .
& git commit -m "Add Jinshu fintech workflows and verified bounded evolution loop"
if ($LASTEXITCODE -ne 0) { throw "Git commit failed; check your local Git identity." }
& gh repo create $Repo --private --source . --remote origin --push
if ($LASTEXITCODE -ne 0) { throw "Repository publication failed; no success claimed." }
& gh repo view $Repo --web
