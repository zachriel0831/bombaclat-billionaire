# Collect Taiwan close context from existing relay events and write one stored-only t_relay_events fact.
param(
  [string]$EnvFile = ".env",
  [string]$ScheduledTime = "15:20",
  [string]$TradeDate = "",
  [int]$LookbackDays = 2,
  [int]$MaxEvents = 200,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Running Taiwan close context collector ..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.tw_close_context",
  "--env-file", $EnvFile,
  "--scheduled-time", $ScheduledTime,
  "--lookback-days", "$LookbackDays",
  "--max-events", "$MaxEvents",
  "--log-level", $LogLevel
)

if ($TradeDate) {
  $cmdArgs += @("--trade-date", $TradeDate)
}

& python @cmdArgs
exit $LASTEXITCODE
