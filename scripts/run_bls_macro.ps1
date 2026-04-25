# Run BLS macro collector and write stored-only events to t_relay_events.
param(
  [string]$EnvFile = ".env",
  [string]$Series = "",
  [int]$TimeoutSeconds = 30,
  [switch]$DryRun,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"

Write-Host "Running BLS macro collector..." -ForegroundColor Cyan

$cmdArgs = @(
  "-m", "event_relay.bls_macro",
  "--env-file", $EnvFile,
  "--timeout-seconds", "$TimeoutSeconds",
  "--log-level", $LogLevel
)

if ($Series) {
  $cmdArgs += @("--series", $Series)
}
if ($DryRun) {
  $cmdArgs += "--dry-run"
}

& python @cmdArgs
exit $LASTEXITCODE
