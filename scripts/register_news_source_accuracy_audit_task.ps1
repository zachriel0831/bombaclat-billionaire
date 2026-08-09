# Register the news source official-list coverage audit.
param(
  [string]$TaskName = "NewsCollector-NewsSourceAccuracyAudit",
  [string]$EnvFile = ".env",
  [string]$Categories = "society,politics",
  [string]$SourceIds = "",
  [string]$SkipSourceIds = "ctee",
  [int]$Limit = 20,
  [double]$MinCoverage = 0.85,
  [int]$MinItems = 3,
  [int]$EveryMinutes = 120,
  [string]$FirstRunAt = "00:40",
  [switch]$NoCompensate,
  [switch]$StartNow,
  [switch]$PlanOnly,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$runScript = Join-Path $PSScriptRoot "run_news_source_accuracy_audit.ps1"

if (-not (Test-Path -LiteralPath $runScript)) {
  throw "run_news_source_accuracy_audit.ps1 not found: $runScript"
}
if ($EveryMinutes -lt 30) {
  throw "EveryMinutes must be at least 30 for source accuracy audits."
}

$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$runScript`"",
  "-EnvFile", "`"$EnvFile`"",
  "-Categories", "`"$Categories`"",
  "-SkipSourceIds", "`"$SkipSourceIds`"",
  "-Limit", $Limit,
  "-MinCoverage", $MinCoverage,
  "-MinItems", $MinItems,
  "-FailOnWarn"
)
if (-not [string]::IsNullOrWhiteSpace($SourceIds)) {
  $actionArgs += @("-SourceIds", "`"$SourceIds`"")
}
if (-not $NoCompensate) {
  $actionArgs += "-Compensate"
}
$actionArgs = $actionArgs -join " "

$startAt = [DateTime]::Today.Add([TimeSpan]::Parse($FirstRunAt))
if ($startAt -le (Get-Date)) {
  $startAt = $startAt.AddMinutes($EveryMinutes)
}

Write-Host "Task: $TaskName"
Write-Host "Every: $EveryMinutes minutes"
Write-Host "First run: $startAt"
Write-Host "Categories: $Categories"
Write-Host "Sources: $(if ([string]::IsNullOrWhiteSpace($SourceIds)) { 'default+low_frequency' } else { $SourceIds })"
Write-Host "Skip: $SkipSourceIds"
Write-Host "Compensate: $(-not $NoCompensate)"
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
  -Description "Audit news-platform official-list coverage and compensate missing source rows." `
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
