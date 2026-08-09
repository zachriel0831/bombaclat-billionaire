# Run live service monitor checks in one persistent console window.
param(
  [string]$EnvFile = ".env",
  [int]$EveryMinutes = 5,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [int]$AutoRepairCooldownMinutes = 60,
  [int]$SourceAccuracyMaxAgeMinutes = 180,
  [switch]$DisableAutoRepair,
  [switch]$NoInitialRun,
  [switch]$Once,
  [switch]$PlanOnly,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$monitorScript = Join-Path $PSScriptRoot "monitor_live_services.ps1"
$autoRepairScript = Join-Path $PSScriptRoot "run_service_auto_repair_watch.ps1"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusDir = Join-Path $ProjectRoot "runtime\status"
$logFile = Join-Path $logDir ("live-service-monitor-window-{0}.log" -f (Get-Date).ToString("yyyyMMdd"))
$statusFile = Join-Path $statusDir "live-service-monitor-window-status.json"

if ($EveryMinutes -lt 1) {
  throw "EveryMinutes must be at least 1."
}
if (-not (Test-Path -LiteralPath $monitorScript)) {
  throw "monitor_live_services.ps1 not found: $monitorScript"
}
if (-not $DisableAutoRepair -and -not (Test-Path -LiteralPath $autoRepairScript)) {
  throw "run_service_auto_repair_watch.ps1 not found: $autoRepairScript"
}

New-Item -ItemType Directory -Force -Path $logDir, $statusDir | Out-Null

function Write-LiveMonitorLog {
  param(
    [string]$Message,
    [ConsoleColor]$Color = "Gray"
  )

  $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
  Write-Host $line -ForegroundColor $Color
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Write-LiveMonitorState {
  param(
    [string]$LastJob,
    [int]$LastExitCode,
    [int]$LastAutoRepairExitCode,
    [datetime]$NextRun
  )

  [ordered]@{
    updated_at = (Get-Date).ToString("o")
    pid = $PID
    last_job = $LastJob
    last_exit_code = $LastExitCode
    last_auto_repair_exit_code = $LastAutoRepairExitCode
    next_run = $NextRun.ToString("o")
    dry_run = [bool]$DryRun
    auto_repair_enabled = -not [bool]$DisableAutoRepair
    log_file = $logFile
  } | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Invoke-LiveMonitor {
  Write-LiveMonitorLog "Starting live service monitor (log=$LogLevel, dry_run=$([bool]$DryRun))..." Cyan

  $monitorArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $monitorScript,
    "-EnvFile", $EnvFile,
    "-LogLevel", $LogLevel
  )
  if ($DryRun) {
    $monitorArgs += "-DryRun"
  }

  & powershell.exe @monitorArgs 2>&1 |
    ForEach-Object { Write-LiveMonitorLog $_ }
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) {
    $exitCode = 0
  }

  if ($exitCode -eq 0) {
    Write-LiveMonitorLog "Live service monitor finished." Green
  } else {
    Write-LiveMonitorLog "Live service monitor failed with exit code $exitCode; the fixed window will keep running." Red
  }

  return $exitCode
}

function Invoke-ServiceAutoRepairWatch {
  if ($DisableAutoRepair) {
    Write-LiveMonitorLog "Service auto-repair watcher disabled for this window." Yellow
    return 0
  }

  Write-LiveMonitorLog "Starting service auto-repair watcher..." Cyan

  $watchArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $autoRepairScript,
    "-EnvFile", $EnvFile,
    "-CooldownMinutes", $AutoRepairCooldownMinutes,
    "-SourceAccuracyMaxAgeMinutes", $SourceAccuracyMaxAgeMinutes,
    "-LaunchAgent"
  )
  if ($DryRun) {
    $watchArgs += "-DryRun"
  }

  & powershell.exe @watchArgs 2>&1 |
    ForEach-Object { Write-LiveMonitorLog $_ }
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) {
    $exitCode = 0
  }

  if ($exitCode -eq 0) {
    Write-LiveMonitorLog "Service auto-repair watcher finished." Green
  } else {
    Write-LiveMonitorLog "Service auto-repair watcher failed with exit code $exitCode; the fixed window will keep running." Red
  }

  return $exitCode
}

if ($PlanOnly) {
  Write-LiveMonitorLog "Plan only: live service monitor fixed window would run from $ProjectRoot." Cyan
  Write-LiveMonitorLog "Cadence: every $EveryMinutes minutes, script=$monitorScript"
  Write-LiveMonitorLog "Auto-repair: enabled=$(-not [bool]$DisableAutoRepair), script=$autoRepairScript, cooldown=${AutoRepairCooldownMinutes}m"
  exit 0
}

$mutex = [System.Threading.Mutex]::new($false, "Global\NewsCollectorLiveServiceMonitorWindow")
if (-not $mutex.WaitOne(0)) {
  Write-LiveMonitorLog "Another live service monitor fixed window is already running. Exiting duplicate launcher." Yellow
  exit 0
}

try {
  try {
    [Console]::Title = "NewsCollector live service monitor"
  } catch {
  }

  Set-Location -LiteralPath $ProjectRoot
  Write-LiveMonitorLog "Live service monitor fixed window started. Close this window to stop the local schedule." Green
  Write-LiveMonitorLog "Cadence: $EveryMinutes minutes."
  Write-LiveMonitorLog "Service auto-repair enabled: $(-not [bool]$DisableAutoRepair), cooldown=${AutoRepairCooldownMinutes}m."
  Write-LiveMonitorLog "Log file: $logFile"
  Write-LiveMonitorLog "Status file: $statusFile"

  $interval = New-TimeSpan -Minutes $EveryMinutes
  $now = Get-Date
  $nextRun = if ($NoInitialRun) { $now.Add($interval) } else { $now }
  Write-LiveMonitorState -LastJob "startup" -LastExitCode 0 -LastAutoRepairExitCode 0 -NextRun $nextRun

  do {
    $now = Get-Date
    if ($now -ge $nextRun) {
      $exitCode = Invoke-LiveMonitor
      $autoRepairExitCode = Invoke-ServiceAutoRepairWatch
      $nextRun = (Get-Date).Add($interval)
      Write-LiveMonitorState -LastJob "monitor+auto_repair" -LastExitCode $exitCode -LastAutoRepairExitCode $autoRepairExitCode -NextRun $nextRun
    }

    if ($Once) {
      break
    }

    Write-LiveMonitorLog ("Next live service monitor check={0}" -f $nextRun.ToString("HH:mm:ss"))
    $sleepSeconds = [Math]::Max(5, [Math]::Min(30, [int][Math]::Ceiling(($nextRun - (Get-Date)).TotalSeconds)))
    Start-Sleep -Seconds $sleepSeconds
  } while ($true)
} finally {
  $mutex.ReleaseMutex()
  $mutex.Dispose()
}
