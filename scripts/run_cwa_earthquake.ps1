# Collect Central Weather Administration earthquake public records.
param(
  [string]$EnvFile = ".env",
  [int]$Limit = 50,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

Write-Host "Collecting CWA earthquake public records..." -ForegroundColor Cyan

$exitCode = Invoke-CodexObservedCommand `
  -Job "cwa_earthquake" `
  -Category "crawler" `
  -Skill "news-ingestion-skill" `
  -Metadata @{ source = "cwa_earthquake"; limit = $Limit; log_level = $LogLevel } `
  -Command {
    & python -m news_platform.main `
      --env-file $EnvFile `
      --collect-public-records `
      --public-sources cwa_earthquake_report `
      --public-record-limit $Limit `
      --log-level $LogLevel
  }

exit $exitCode
