# Register the international homepage headline crawler as one visible fixed window.
param(
  [string]$TaskName = "NewsCollector-InternationalHomepageHeadlines",
  [string]$EnvFile = ".env",
  [ValidateSet("direct-db", "relay")]
  [string]$EventSink = "direct-db",
  [string]$RelayUrl = "http://127.0.0.1:18090/events",
  [int]$Limit = 3,
  [int]$EveryMinutes = 60,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$NoInitialRun,
  [switch]$StartNow,
  [switch]$PlanOnly,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$windowScript = Join-Path $PSScriptRoot "run_international_homepage_headlines_window.ps1"
$logDir = Join-Path $ProjectRoot "runtime\logs"
$statusFile = Join-Path $ProjectRoot "runtime\status\international-homepage-headlines-window-status.json"

if (-not (Test-Path -LiteralPath $windowScript)) {
  throw "run_international_homepage_headlines_window.ps1 not found: $windowScript"
}
if ($EveryMinutes -lt 30) {
  throw "EveryMinutes must be at least 30 for public homepage headline sources."
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-NoExit",
  "-File", "`"$windowScript`"",
  "-EnvFile", "`"$EnvFile`"",
  "-EventSink", $EventSink,
  "-RelayUrl", "`"$RelayUrl`"",
  "-Limit", $Limit,
  "-EveryMinutes", $EveryMinutes,
  "-LogLevel", $LogLevel
)
if ($NoInitialRun) {
  $actionArgs += "-NoInitialRun"
}
$actionArgs = $actionArgs -join " "

Write-Host "Task: $TaskName"
Write-Host "Every: $EveryMinutes minutes"
Write-Host "User: $currentUser"
Write-Host "Action: powershell.exe $actionArgs"
Write-Host "Status: $statusFile"
Write-Host "Logs: $logDir\international-homepage-headlines-window-YYYYMMDD.log"

if ($PlanOnly) {
  exit 0
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}
if ($Force) {
  $null = Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal `
  -Description "Keep low-frequency international homepage headline collection in one visible fixed PowerShell window." `
  -Force | Out-Null

if ($StartNow) {
  $runningWindow = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*run_international_homepage_headlines_window.ps1*" } |
    Select-Object -First 1
  if ($runningWindow) {
    Write-Host "Visible international homepage headline window is already running (PID $($runningWindow.ProcessId))." -ForegroundColor Yellow
  } else {
    Start-Process `
      -FilePath "powershell.exe" `
      -ArgumentList $actionArgs `
      -WorkingDirectory $ProjectRoot `
      -WindowStyle Normal
    Write-Host "Started visible international homepage headline window." -ForegroundColor Green
  }
}

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Scheduled task registered: $TaskName" -ForegroundColor Green
Write-Host "  NextRunTime: $($info.NextRunTime)"
Write-Host "  LastRunTime: $($info.LastRunTime)"
Write-Host "  State: $($task.State)"
