# Check live collector workers and restart them when a process probe is down.
param(
  [string]$EnvFile = ".env",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$logDir = Join-Path $ProjectRoot "runtime\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "live-service-monitor.log"

function Write-MonitorLog {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
  Write-Host $line
}

$healthRaw = & (Join-Path $PSScriptRoot "run_data_source_health.ps1") -EnvFile $EnvFile -Json
if ($LASTEXITCODE -ne 0) {
  Write-MonitorLog "health_check_failed exit=$LASTEXITCODE"
  if (-not $DryRun) {
    & (Join-Path $PSScriptRoot "restart_live_services.ps1") -EnvFile $EnvFile -LogLevel $LogLevel
  }
  exit 0
}

$report = $healthRaw | ConvertFrom-Json
$workerNames = @("process_event_relay", "process_source_bridge", "process_news_platform_loop")
$bad = @($report.probes | Where-Object {
  $workerNames -contains $_.name -and $_.status -ne "ok"
})

if ($bad.Count -eq 0) {
  Write-MonitorLog "workers_ok"
  exit 0
}

$details = ($bad | ForEach-Object { "$($_.name)=$($_.status)" }) -join ","
Write-MonitorLog "workers_unhealthy $details"
if (-not $DryRun) {
  & (Join-Path $PSScriptRoot "restart_live_services.ps1") -EnvFile $EnvFile -LogLevel $LogLevel
}
exit 0
