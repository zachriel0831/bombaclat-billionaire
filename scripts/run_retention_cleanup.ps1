# Run MySQL retention cleanup for relay event and X post tables.
param(
  [string]$EnvFile = ".env",
  [int]$KeepDays = 0,
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

$argsList = @(
  "-m", "event_relay.retention_cleanup",
  "--env-file", $EnvFile,
  "--log-level", $LogLevel
)
if ($KeepDays -gt 0) {
  $argsList += @("--keep-days", "$KeepDays")
}
if ($DryRun) {
  $argsList += "--dry-run"
}

$exitCode = Invoke-CodexObservedCommand `
  -Job "retention_cleanup" `
  -Category "maintenance" `
  -Metadata @{ keep_days = $KeepDays; dry_run = $DryRun.IsPresent; log_level = $LogLevel } `
  -Command { & python @argsList }

exit $exitCode
