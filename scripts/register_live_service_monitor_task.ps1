# Register the live collector worker monitor as a repeating Windows task.
param(
  [string]$TaskName = "NewsCollector-LiveServiceMonitor",
  [string]$EnvFile = ".env",
  [int]$EveryMinutes = 5,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$StartNow,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$monitorScript = Join-Path $PSScriptRoot "monitor_live_services.ps1"

if (-not (Test-Path -LiteralPath $monitorScript)) {
  throw "Monitor script not found: $monitorScript"
}
if ($EveryMinutes -lt 1) {
  throw "EveryMinutes must be >= 1"
}

$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$monitorScript`"",
  "-EnvFile", "`"$EnvFile`"",
  "-LogLevel", $LogLevel
) -join " "

Write-Host "Task: $TaskName"
Write-Host "Every: $EveryMinutes minutes"
Write-Host "Action: powershell.exe $actionArgs"

if ($PlanOnly) {
  exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Description "Monitors data-collecting live workers and restarts the stack when a worker exits." `
  -Force | Out-Null

if ($StartNow) {
  Start-ScheduledTask -TaskName $TaskName
}

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State
