# Register daily MySQL retention cleanup for relay event and X post tables.
param(
  [string]$TaskName = "NewsCollector-RetentionCleanup",
  [string]$At = "00:10",
  [string]$EnvFile = ".env",
  [int]$KeepDays = 0,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot "run_retention_cleanup.ps1"

$arguments = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$scriptPath`"",
  "-EnvFile", "`"$EnvFile`"",
  "-LogLevel", "INFO"
)
if ($KeepDays -gt 0) {
  $arguments += @("-KeepDays", "$KeepDays")
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($arguments -join " ") -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Delete rows older than the configured retention window from t_relay_events and t_x_posts." `
  -Force:$Force | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered retention cleanup task: $TaskName" -ForegroundColor Green
Write-Host "State: $($registered.State)" -ForegroundColor DarkGray
Write-Host "NextRunTime: $($info.NextRunTime)" -ForegroundColor DarkGray
