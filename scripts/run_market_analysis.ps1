# Run twice-daily market analysis generator (single-shot).
param(
  [string]$EnvFile = ".env",
  [ValidateSet("auto", "us_close", "pre_tw_open")]
  [string]$Slot = "auto",
  [switch]$Force,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Running market analysis slot=$Slot ..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.market_analysis",
  "--env-file", $EnvFile,
  "--slot", $Slot,
  "--log-level", $LogLevel
)

if ($Force) {
  $cmdArgs += "--force"
}

& python @cmdArgs
