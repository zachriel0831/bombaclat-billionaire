# Register the live collector worker monitor as one visible fixed window.
param(
  [string]$TaskName = "NewsCollector-LiveServiceMonitor",
  [string]$EnvFile = ".env",
  [int]$EveryMinutes = 5,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [int]$AutoRepairCooldownMinutes = 60,
  [int]$SourceAccuracyMaxAgeMinutes = 180,
  [switch]$DisableAutoRepair,
  [switch]$StartNow,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$windowScript = Join-Path $PSScriptRoot "run_live_service_monitor_window.ps1"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusFile = Join-Path $ProjectRoot "runtime\status\live-service-monitor-window-status.json"

if (-not (Test-Path -LiteralPath $windowScript)) {
  throw "run_live_service_monitor_window.ps1 not found: $windowScript"
}
if ($EveryMinutes -lt 1) {
  throw "EveryMinutes must be at least 1."
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-NoExit",
  "-File", "`"$windowScript`"",
  "-EnvFile", "`"$EnvFile`"",
  "-EveryMinutes", $EveryMinutes,
  "-LogLevel", $LogLevel,
  "-AutoRepairCooldownMinutes", $AutoRepairCooldownMinutes,
  "-SourceAccuracyMaxAgeMinutes", $SourceAccuracyMaxAgeMinutes
)
if ($DisableAutoRepair) {
  $actionArgs += "-DisableAutoRepair"
}
$actionArgs = $actionArgs -join " "

Write-Host "Task: $TaskName"
Write-Host "Every: $EveryMinutes minutes"
Write-Host "AutoRepair: $(-not [bool]$DisableAutoRepair), cooldown=${AutoRepairCooldownMinutes}m, sourceAccuracyMaxAge=${SourceAccuracyMaxAgeMinutes}m"
Write-Host "User: $currentUser"
Write-Host "Action: powershell.exe $actionArgs"
Write-Host "Status: $statusFile"
Write-Host "Logs: $logDir\live-service-monitor-window-YYYYMMDD.log"

if ($PlanOnly) {
  exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew `
  -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal `
  -Description "Keep data-collecting live worker monitoring and service auto-repair watch in one visible fixed PowerShell window." `
  -Force | Out-Null

if ($StartNow) {
  Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $actionArgs `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Normal
  Write-Host "Started visible live service monitor window." -ForegroundColor Green
}

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State
