param(
  [string]$EnvFile = ".env",
  [string]$Families = "all",
  [int]$TimeoutSeconds = 20,
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

Write-Host "Running Taiwan market-flow collector families=$Families ..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.tw_market_flow",
  "--env-file", $EnvFile,
  "--families", $Families,
  "--timeout-seconds", "$TimeoutSeconds",
  "--log-level", $LogLevel
)

if ($DryRun) {
  $cmdArgs += "--dry-run"
}

$exitCode = Invoke-CodexObservedCommand `
  -Job "tw_market_flow" `
  -Category "crawler" `
  -Skill "news-ingestion-skill" `
  -Metadata @{ source = "tw_market_flow"; families = $Families; dry_run = $DryRun.IsPresent; log_level = $LogLevel } `
  -Command { & python @cmdArgs }

exit $exitCode
