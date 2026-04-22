param(
  [string]$EnvFile = ".env",
  [string]$UsCloseTaskName = "NewsCollector-MarketAnalysis-UsClose",
  [string]$MarketContextTaskName = "NewsCollector-MarketContext-PreTwOpen",
  [string]$PreOpenTaskName = "NewsCollector-MarketAnalysis-PreTwOpen",
  [string]$UsCloseAt = "05:00",
  [string]$MarketContextAt = "07:20",
  [string]$PreOpenAt = "07:30",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunScript = Join-Path $ProjectRoot "scripts\\run_market_analysis.ps1"
$ContextScript = Join-Path $ProjectRoot "scripts\\run_market_context.ps1"

if (-not (Test-Path -LiteralPath $RunScript)) {
  throw "run_market_analysis.ps1 not found: $RunScript"
}
if (-not (Test-Path -LiteralPath $ContextScript)) {
  throw "run_market_context.ps1 not found: $ContextScript"
}

function Register-MarketAnalysisTask {
  param(
    [string]$TaskName,
    [string]$Slot,
    [string]$At,
    [string]$Description
  )

  $actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -EnvFile `"$EnvFile`" -Slot `"$Slot`" -LogLevel INFO"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
  $trigger = New-ScheduledTaskTrigger -Daily -At $At
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)

  if ($Force) {
    $null = Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  }

  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $Description -Force | Out-Null

  $task = Get-ScheduledTask -TaskName $TaskName
  $info = Get-ScheduledTaskInfo -TaskName $TaskName
  Write-Host "Scheduled task registered: $TaskName" -ForegroundColor Green
  Write-Host "  Slot: $Slot"
  Write-Host "  NextRunTime: $($info.NextRunTime)"
  Write-Host "  LastRunTime: $($info.LastRunTime)"
  Write-Host "  State: $($task.State)"
}

function Register-MarketContextTask {
  param(
    [string]$TaskName,
    [string]$At,
    [string]$Description
  )

  $actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$ContextScript`" -EnvFile `"$EnvFile`" -AnalysisSlot `"market_context_pre_tw_open`" -ScheduledTime `"$At`" -LogLevel INFO"
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
  $trigger = New-ScheduledTaskTrigger -Daily -At $At
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)

  if ($Force) {
    $null = Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  }

  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $Description -Force | Out-Null

  $task = Get-ScheduledTask -TaskName $TaskName
  $info = Get-ScheduledTaskInfo -TaskName $TaskName
  Write-Host "Scheduled task registered: $TaskName" -ForegroundColor Green
  Write-Host "  Slot: market_context_pre_tw_open"
  Write-Host "  NextRunTime: $($info.NextRunTime)"
  Write-Host "  LastRunTime: $($info.LastRunTime)"
  Write-Host "  State: $($task.State)"
}

Register-MarketAnalysisTask -TaskName $UsCloseTaskName -Slot "us_close" -At $UsCloseAt -Description "Generate stored-only U.S. close analysis at 05:00 local time."
Register-MarketContextTask -TaskName $MarketContextTaskName -At $MarketContextAt -Description "Collect pre-open market context and store it as event-only facts before Taiwan open."
Register-MarketAnalysisTask -TaskName $PreOpenTaskName -Slot "pre_tw_open" -At $PreOpenAt -Description "Generate stored-only Taiwan pre-open analysis at 07:30 local time."

foreach ($obsoleteTaskName in @("NewsCollector-AnalysisPush-UsClose", "NewsCollector-AnalysisPush-PreTwOpen")) {
  if (Get-ScheduledTask -TaskName $obsoleteTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $obsoleteTaskName -Confirm:$false
    Write-Host "Removed obsolete analysis push task: $obsoleteTaskName" -ForegroundColor Yellow
  }
}
