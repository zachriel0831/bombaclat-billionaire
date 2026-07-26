param(
  [string]$EnvFile = ".env",
  [int]$Limit = 20,
  [int]$TimeoutSeconds = 15,
  [switch]$DryRun,
  [switch]$BackfillRelay,
  [switch]$BackfillOnly,
  [int]$BackfillLimit = 0,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

$argsList = @(
  "-m", "event_relay.palestine_news",
  "--env-file", $EnvFile,
  "--limit", [string]$Limit,
  "--timeout-seconds", [string]$TimeoutSeconds,
  "--log-level", $LogLevel
)

if ($DryRun) {
  $argsList += "--dry-run"
}
if ($BackfillRelay) {
  $argsList += "--backfill-relay"
}
if ($BackfillOnly) {
  $argsList += "--backfill-only"
}
if ($BackfillLimit -gt 0) {
  $argsList += @("--backfill-limit", [string]$BackfillLimit)
}

Write-Host "Collecting English Palestine issue news into long-term storage..." -ForegroundColor Cyan
$exitCode = Invoke-CodexObservedCommand `
  -Job "palestine_news" `
  -Category "crawler" `
  -Skill "news-ingestion-skill" `
  -Metadata @{
    source = "palestine_news"
    limit = $Limit
    dry_run = $DryRun.IsPresent
    backfill_relay = $BackfillRelay.IsPresent
    backfill_only = $BackfillOnly.IsPresent
    log_level = $LogLevel
  } `
  -Command { & python @argsList }

exit $exitCode
