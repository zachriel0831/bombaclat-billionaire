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

& python @cmdArgs
exit $LASTEXITCODE
