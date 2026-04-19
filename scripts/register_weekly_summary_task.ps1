param(
  [string]$TaskName = "NewsCollector-WeeklySummary",
  [string]$EnvFile = ".env",
  [string]$At = "18:00",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunScript = Join-Path $ProjectRoot "scripts\\run_weekly_summary.ps1"

if (-not (Test-Path -LiteralPath $RunScript)) {
  throw "run_weekly_summary.ps1 not found: $RunScript"
}

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -EnvFile `"$EnvFile`" -LogLevel INFO"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

if ($Force) {
  $null = Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Generate weekly political/economic summary and push to LINE at Sunday 18:00 local time." -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Scheduled task registered: $TaskName" -ForegroundColor Green
Write-Host "NextRunTime: $($info.NextRunTime)"
Write-Host "LastRunTime: $($info.LastRunTime)"
Write-Host "State: $($task.State)"

