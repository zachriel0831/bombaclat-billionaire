# Collect official U.S. macro release calendar rows into t_macro_release_calendar.
param(
  [string]$EnvFile = ".env",
  [string]$Years = "",
  [int]$TimeoutSeconds = 30,
  [string]$EarningsSymbols = "",
  [int]$EarningsLookaheadDays = 75,
  [string]$EarningsManualFile = "",
  [switch]$SkipEarnings,
  [switch]$DryRun,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Running market release calendar collector..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.macro_calendar",
  "--env-file", $EnvFile,
  "--timeout-seconds", "$TimeoutSeconds",
  "--log-level", $LogLevel
)

if ($Years) {
  $cmdArgs += @("--years", $Years)
}
if ($EarningsSymbols) {
  $cmdArgs += @("--earnings-symbols", $EarningsSymbols)
}
if ($EarningsLookaheadDays -gt 0) {
  $cmdArgs += @("--earnings-lookahead-days", "$EarningsLookaheadDays")
}
if ($EarningsManualFile) {
  $cmdArgs += @("--earnings-manual-file", $EarningsManualFile)
}
if ($SkipEarnings) {
  $cmdArgs += "--skip-earnings"
}
if ($DryRun) {
  $cmdArgs += "--dry-run"
}

& python @cmdArgs
exit $LASTEXITCODE
