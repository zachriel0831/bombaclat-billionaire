# Run weekly macro summary generator (single-shot).
param(
  [string]$EnvFile = ".env",
  [switch]$Force,
  [switch]$DryRun,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

Write-Host "Running weekly macro summary..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.weekly_summary",
  "--env-file", $EnvFile,
  "--log-level", $LogLevel
)

if ($Force) {
  $cmdArgs += "--force"
}
if ($DryRun) {
  $cmdArgs += "--dry-run"
}

$exitCode = Invoke-CodexObservedCommand `
  -Job "weekly_summary" `
  -Category "analysis" `
  -Skill "macro-weekly-summary-skill" `
  -Metadata @{ force = $Force.IsPresent; dry_run = $DryRun.IsPresent; log_level = $LogLevel } `
  -Command { & python @cmdArgs }

exit $exitCode
