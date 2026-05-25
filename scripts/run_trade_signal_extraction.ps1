param(
  [string]$EnvFile = ".env",
  [int]$Days = 14,
  [int]$Limit = 50,
  [int]$AnalysisId = 0,
  [switch]$FixedPoolFallback,
  [int]$EventDays = 1,
  [int]$EventLimit = 200,
  [int]$PriorDays = 30,
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PYTHONPATH = "src"
Write-Host "Extracting trade signals from market analyses..." -ForegroundColor Cyan

$argsList = @(
  "-m", "event_relay.trade_signals",
  "--env-file", $EnvFile,
  "--days", $Days,
  "--limit", $Limit,
  "--event-days", $EventDays,
  "--event-limit", $EventLimit,
  "--prior-days", $PriorDays,
  "--log-level", $LogLevel
)

if ($AnalysisId -gt 0) {
  $argsList += @("--analysis-id", $AnalysisId)
}

if ($FixedPoolFallback.IsPresent) {
  $argsList += "--fixed-pool-fallback"
}

& python @argsList

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
