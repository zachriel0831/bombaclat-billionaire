# Collect pre-open market context and write directly to t_market_analyses.
param(
  [string]$EnvFile = ".env",
  [string]$AnalysisSlot = "market_context_pre_tw_open",
  [string]$ScheduledTime = "07:20",
  [int]$TimeoutSeconds = 15,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Running market context collector slot=$AnalysisSlot ..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.market_context",
  "--env-file", $EnvFile,
  "--analysis-slot", $AnalysisSlot,
  "--scheduled-time", $ScheduledTime,
  "--timeout-seconds", "$TimeoutSeconds",
  "--log-level", $LogLevel
)

& python @cmdArgs
