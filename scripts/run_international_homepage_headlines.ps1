# Collect low-frequency international homepage headlines into relay events.
param(
  [string]$EnvFile = ".env",
  [ValidateSet("direct-db", "relay")]
  [string]$EventSink = "direct-db",
  [string]$RelayUrl = "http://127.0.0.1:18090/events",
  [int]$Limit = 3,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

Write-Host "Collecting international homepage headlines..." -ForegroundColor Cyan
Write-Host "Limit per homepage: $Limit"
Write-Host "Event sink: $EventSink"

$exitCode = Invoke-CodexObservedCommand `
  -Job "international_homepage_headlines" `
  -Category "crawler" `
  -Skill "news-ingestion-skill" `
  -Metadata @{
    limit = $Limit
    event_sink = $EventSink
    log_level = $LogLevel
  } `
  -Command {
    & python .\scripts\collect_homepage_headlines.py `
      --env-file $EnvFile `
      --event-sink $EventSink `
      --relay-url $RelayUrl `
      --limit $Limit `
      --log-level $LogLevel
    if ($LASTEXITCODE -ne 0) {
      throw "international homepage headline crawl failed with exit code $LASTEXITCODE"
    }
  }

exit $exitCode
