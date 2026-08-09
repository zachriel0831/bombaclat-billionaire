# Register the low-frequency Taiwan news source crawler.
param(
  [string]$TaskName = "NewsCollector-NewsPlatformLowFrequencySources",
  [string]$EnvFile = ".env",
  [string]$SourceIds = "tvbs,udn,setn",
  [string]$Categories = "society,politics",
  [int]$Limit = 20,
  [int]$AuthorLimit = 30,
  [int]$EveryMinutes = 60,
  [string]$FirstRunAt = "00:20",
  [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
  [string]$LogLevel = "INFO",
  [switch]$StartNow,
  [switch]$PlanOnly,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$runScript = Join-Path $PSScriptRoot "run_news_platform_low_frequency_sources.ps1"

if (-not (Test-Path -LiteralPath $runScript)) {
  throw "run_news_platform_low_frequency_sources.ps1 not found: $runScript"
}
if ($EveryMinutes -lt 15) {
  throw "EveryMinutes must be at least 15 for public HTML list sources."
}

$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$runScript`"",
  "-EnvFile", "`"$EnvFile`"",
  "-SourceIds", "`"$SourceIds`"",
  "-Categories", "`"$Categories`"",
  "-Limit", $Limit,
  "-AuthorLimit", $AuthorLimit,
  "-LogLevel", $LogLevel
) -join " "

$startAt = [DateTime]::Today.Add([TimeSpan]::Parse($FirstRunAt))
if ($startAt -le (Get-Date)) {
  $startAt = $startAt.AddMinutes($EveryMinutes)
}

Write-Host "Task: $TaskName"
Write-Host "Every: $EveryMinutes minutes"
Write-Host "First run: $startAt"
Write-Host "Sources: $SourceIds"
Write-Host "Categories: $Categories"
Write-Host "Action: powershell.exe $actionArgs"

if ($PlanOnly) {
  exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Once -At $startAt `
  -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
  -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 1)

if ($Force) {
  $null = Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings `
  -Description "Collect low-frequency TVBS/UDN/SETN public society-politics list pages and enrich reporter metadata." `
  -Force | Out-Null

if ($StartNow) {
  Start-ScheduledTask -TaskName $TaskName
}

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Scheduled task registered: $TaskName" -ForegroundColor Green
Write-Host "  NextRunTime: $($info.NextRunTime)"
Write-Host "  LastRunTime: $($info.LastRunTime)"
Write-Host "  State: $($task.State)"
