# Collect Central Weather Administration typhoon and earthquake public records.
param(
  [string]$EnvFile = ".env",
  [int]$Limit = 20,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Collecting CWA typhoon and earthquake public records..." -ForegroundColor Cyan

& python -m news_platform.main `
  --env-file $EnvFile `
  --collect-public-records `
  --public-sources cwa_weather `
  --public-record-limit $Limit `
  --log-level $LogLevel

exit $LASTEXITCODE
