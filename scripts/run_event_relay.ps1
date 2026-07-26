# Start the legacy-named event relay service.
param(
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$env:PYTHONUNBUFFERED = "1"
. (Join-Path $PSScriptRoot "codex_observer.ps1")

Write-Host "Starting event relay..." -ForegroundColor Cyan
$exitCode = Invoke-CodexObservedCommand `
  -Job "event_relay" `
  -Category "service" `
  -Metadata @{ log_level = $LogLevel } `
  -Command { & python -m event_relay.main --env-file $EnvFile --log-level $LogLevel }

exit $exitCode
