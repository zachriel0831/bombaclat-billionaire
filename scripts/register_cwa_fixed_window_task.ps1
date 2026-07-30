# Register one visible fixed window for CWA typhoon/earthquake collection.
param(
  [string]$TaskName = "NewsCollector-CwaFixedWindow",
  [string]$EnvFile = ".env",
  [int]$WeatherEveryMinutes = 30,
  [int]$EarthquakeEveryMinutes = 5,
  [int]$WeatherLimit = 20,
  [int]$EarthquakeLimit = 50,
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$StartNow,
  [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$windowScript = Join-Path $PSScriptRoot "run_cwa_collectors_window.ps1"
$legacyTasks = @("NewsCollector-CwaWeather", "NewsCollector-CwaEarthquake")

if ($WeatherEveryMinutes -lt 1) {
  throw "WeatherEveryMinutes must be at least 1."
}
if ($EarthquakeEveryMinutes -lt 1) {
  throw "EarthquakeEveryMinutes must be at least 1."
}
if (-not (Test-Path -LiteralPath $windowScript)) {
  throw "run_cwa_collectors_window.ps1 not found: $windowScript"
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-NoExit",
  "-File", "`"$windowScript`"",
  "-EnvFile", "`"$EnvFile`"",
  "-WeatherEveryMinutes", $WeatherEveryMinutes,
  "-EarthquakeEveryMinutes", $EarthquakeEveryMinutes,
  "-WeatherLimit", $WeatherLimit,
  "-EarthquakeLimit", $EarthquakeLimit,
  "-LogLevel", $LogLevel
) -join " "

if ($PlanOnly) {
  Write-Host "Would disable legacy tasks: $($legacyTasks -join ', ')" -ForegroundColor DarkGray
  Write-Host "Would register $TaskName for interactive logon user $currentUser" -ForegroundColor Cyan
  Write-Host "Action: powershell.exe $actionArgs" -ForegroundColor DarkGray
  exit 0
}

foreach ($legacyTask in $legacyTasks) {
  $existingTask = Get-ScheduledTask -TaskName $legacyTask -ErrorAction SilentlyContinue
  if ($existingTask) {
    Disable-ScheduledTask -TaskName $legacyTask | Out-Null
    Write-Host "Disabled legacy popup task: $legacyTask" -ForegroundColor Yellow
  }
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Description "Keep CWA typhoon and earthquake public-record collection in one visible fixed PowerShell window." `
  -Force | Out-Null

Write-Host "Registered CWA fixed-window task: $TaskName" -ForegroundColor Green
Write-Host "User: $currentUser" -ForegroundColor DarkGray
Write-Host "WeatherEveryMinutes: $WeatherEveryMinutes" -ForegroundColor DarkGray
Write-Host "EarthquakeEveryMinutes: $EarthquakeEveryMinutes" -ForegroundColor DarkGray

if ($StartNow) {
  Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $actionArgs `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Normal
  Write-Host "Started visible CWA fixed window." -ForegroundColor Green
}
