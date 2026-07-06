# Register CWA typhoon/earthquake collection.
param(
  [string]$TaskName = "NewsCollector-CwaWeather",
  [string]$EnvFile = ".env",
  [int]$EveryMinutes = 30,
  [int]$Limit = 20,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot "run_cwa_weather.ps1"

if (-not (Test-Path -LiteralPath $scriptPath)) {
  throw "run_cwa_weather.ps1 not found: $scriptPath"
}

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -EnvFile `"$EnvFile`" -Limit $Limit -LogLevel INFO"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$startAt = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger `
  -Once `
  -At $startAt `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

if ($Force) {
  $null = Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Collect CWA typhoon and earthquake public records into t_public_records." `
  -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered CWA weather task: $TaskName" -ForegroundColor Green
Write-Host "State: $($task.State)" -ForegroundColor DarkGray
Write-Host "NextRunTime: $($info.NextRunTime)" -ForegroundColor DarkGray
Write-Host "EveryMinutes: $EveryMinutes" -ForegroundColor DarkGray
