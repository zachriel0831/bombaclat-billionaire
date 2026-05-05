param(
  [string]$EnvFile = ".env",
  [string]$UsCloseTaskName = "NewsCollector-MarketAnalysis-UsClose",
  [string]$RagIndexerTaskName = "NewsCollector-RagIndexer",
  [string]$BlsMacroTaskName = "NewsCollector-BlsMacro",
  [string]$MarketContextTaskName = "NewsCollector-MarketContext-PreTwOpen",
  [string]$PreOpenTaskName = "NewsCollector-MarketAnalysis-PreTwOpen",
  [string]$TwMarketFlowTaskName = "NewsCollector-TwMarketFlow",
  [string]$TwCloseContextTaskName = "NewsCollector-TwCloseContext",
  [string]$TwCloseTaskName = "NewsCollector-MarketAnalysis-TwClose",
  [string]$UsCloseAt = "05:00",
  [string]$RagIndexerAt = "04:40",
  [string]$BlsMacroAt = "04:50",
  [string]$MarketContextAt = "07:50",
  [string]$PreOpenAt = "08:00",
  [string]$TwMarketFlowAt = "15:10",
  [string]$TwCloseContextAt = "15:20",
  [string]$TwCloseAt = "15:30",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RunScript = Join-Path $ProjectRoot "scripts\\run_market_analysis.ps1"
$RagIndexerScript = Join-Path $ProjectRoot "scripts\\run_rag_indexer.ps1"
$ContextScript = Join-Path $ProjectRoot "scripts\\run_market_context.ps1"
$BlsMacroScript = Join-Path $ProjectRoot "scripts\\run_bls_macro.ps1"
$TwMarketFlowScript = Join-Path $ProjectRoot "scripts\\run_tw_market_flow.ps1"
$TwCloseContextScript = Join-Path $ProjectRoot "scripts\\run_tw_close_context.ps1"

if (-not (Test-Path -LiteralPath $RunScript)) {
  throw "run_market_analysis.ps1 not found: $RunScript"
}
if (-not (Test-Path -LiteralPath $RagIndexerScript)) {
  throw "run_rag_indexer.ps1 not found: $RagIndexerScript"
}
if (-not (Test-Path -LiteralPath $ContextScript)) {
  throw "run_market_context.ps1 not found: $ContextScript"
}
if (-not (Test-Path -LiteralPath $BlsMacroScript)) {
  throw "run_bls_macro.ps1 not found: $BlsMacroScript"
}
if (-not (Test-Path -LiteralPath $TwMarketFlowScript)) {
  throw "run_tw_market_flow.ps1 not found: $TwMarketFlowScript"
}
if (-not (Test-Path -LiteralPath $TwCloseContextScript)) {
  throw "run_tw_close_context.ps1 not found: $TwCloseContextScript"
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

function Register-CollectorTask {
  param(
    [string]$TaskName,
    [string]$ScriptPath,
    [string]$At,
    [string]$Description,
    [string]$ExtraArgs = ""
  )

  $actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -EnvFile `"$EnvFile`" -LogLevel INFO"
  if ($ExtraArgs) {
    $actionArgs = "$actionArgs $ExtraArgs"
  }
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
  Write-Host "  NextRunTime: $($info.NextRunTime)"
  Write-Host "  LastRunTime: $($info.LastRunTime)"
  Write-Host "  State: $($task.State)"
}

function Register-TwCloseContextTask {
  param(
    [string]$TaskName,
    [string]$At,
    [string]$Description
  )

  $actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$TwCloseContextScript`" -EnvFile `"$EnvFile`" -ScheduledTime `"$At`" -LogLevel INFO"
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
  Write-Host "  Slot: tw_close"
  Write-Host "  NextRunTime: $($info.NextRunTime)"
  Write-Host "  LastRunTime: $($info.LastRunTime)"
  Write-Host "  State: $($task.State)"
}

Register-CollectorTask -TaskName $RagIndexerTaskName -ScriptPath $RagIndexerScript -At $RagIndexerAt -Description "Index recent relay events and market analyses for historical-case RAG."
Register-CollectorTask -TaskName $BlsMacroTaskName -ScriptPath $BlsMacroScript -At $BlsMacroAt -Description "Collect BLS official macro facts into t_relay_events before U.S. close analysis."
Register-MarketAnalysisTask -TaskName $UsCloseTaskName -Slot "us_close" -At $UsCloseAt -Description "Generate U.S. close analysis at 05:00 local time; TW holidays with U.S. trading make it Java-delivery eligible."
Register-MarketContextTask -TaskName $MarketContextTaskName -At $MarketContextAt -Description "Collect pre-open market context and store it as event-only facts before Taiwan open."
Register-MarketAnalysisTask -TaskName $PreOpenTaskName -Slot "pre_tw_open" -At $PreOpenAt -Description "Generate Taiwan pre-open analysis, or macro_daily when both TW and U.S. close session are closed."
Register-CollectorTask -TaskName $TwMarketFlowTaskName -ScriptPath $TwMarketFlowScript -At $TwMarketFlowAt -Description "Collect Taiwan official market-flow facts into t_relay_events before Taiwan close context."
Register-TwCloseContextTask -TaskName $TwCloseContextTaskName -At $TwCloseContextAt -Description "Collect Taiwan close context from relay events at 15:20 local time."
Register-MarketAnalysisTask -TaskName $TwCloseTaskName -Slot "tw_close" -At $TwCloseAt -Description "Generate stored-only Taiwan close analysis at 15:30 local time; market calendar guard may skip it."

foreach ($obsoleteTaskName in @("NewsCollector-AnalysisPush-UsClose", "NewsCollector-AnalysisPush-PreTwOpen")) {
  if (Get-ScheduledTask -TaskName $obsoleteTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $obsoleteTaskName -Confirm:$false
    Write-Host "Removed obsolete analysis push task: $obsoleteTaskName" -ForegroundColor Yellow
  }
}
