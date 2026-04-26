param(
  [string]$EnvFile = ".env",
  [int]$Days = 14,
  [int]$Limit = 50,
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PYTHONPATH = "src"
Write-Host "Extracting trade signals from recent market analyses..." -ForegroundColor Cyan

& python -m event_relay.trade_signals `
  --env-file $EnvFile `
  --days $Days `
  --limit $Limit `
  --log-level $LogLevel

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
