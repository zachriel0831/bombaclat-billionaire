# Registers data/context collection tasks used by the news and market platform.
# Python LLM daily/weekly analysis tasks are retired and intentionally absent.
param(
  [string]$EnvFile = ".env",
  [string]$RagIndexerTaskName = "NewsCollector-RagIndexer",
  [string]$PalestineNewsTaskName = "NewsCollector-PalestineNews",
  [string]$NewsPlatformLowFrequencyTaskName = "NewsCollector-NewsPlatformLowFrequencySources",
  [string]$NewsSourceAccuracyTaskName = "NewsCollector-NewsSourceAccuracyAudit",
  [string]$BlsMacroTaskName = "NewsCollector-BlsMacro",
  [string]$MacroCalendarTaskName = "NewsCollector-MacroCalendar",
  [string]$MarketContextTaskName = "NewsCollector-MarketContext-PreTwOpen",
  [string]$TwMarketFlowTaskName = "NewsCollector-TwMarketFlow",
  [string]$TwCloseContextTaskName = "NewsCollector-TwCloseContext",
  [string]$RagIndexerAt = "04:40",
  [string]$PalestineNewsAt = "06:10",
  [int]$PalestineNewsEveryHours = 3,
  [string]$NewsPlatformLowFrequencyAt = "00:20",
  [int]$NewsPlatformLowFrequencyEveryHours = 1,
  [string]$NewsSourceAccuracyAt = "00:40",
  [int]$NewsSourceAccuracyEveryHours = 2,
  [string]$BlsMacroAt = "04:50",
  [string]$MacroCalendarAt = "06:00",
  [string]$MarketContextAt = "07:20",
  [string]$TwMarketFlowAt = "15:10",
  [string]$TwCloseContextAt = "15:20",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RagIndexerScript = Join-Path $ProjectRoot "scripts\\run_rag_indexer.ps1"
$PalestineNewsScript = Join-Path $ProjectRoot "scripts\\run_palestine_news.ps1"
$NewsPlatformLowFrequencyRegisterScript = Join-Path $ProjectRoot "scripts\\register_news_platform_low_frequency_sources_task.ps1"
$NewsSourceAccuracyScript = Join-Path $ProjectRoot "scripts\\run_news_source_accuracy_audit.ps1"
$ContextScript = Join-Path $ProjectRoot "scripts\\run_market_context.ps1"
$BlsMacroScript = Join-Path $ProjectRoot "scripts\\run_bls_macro.ps1"
$MacroCalendarScript = Join-Path $ProjectRoot "scripts\\run_macro_calendar.ps1"
$TwMarketFlowScript = Join-Path $ProjectRoot "scripts\\run_tw_market_flow.ps1"
$TwCloseContextScript = Join-Path $ProjectRoot "scripts\\run_tw_close_context.ps1"

if (-not (Test-Path -LiteralPath $RagIndexerScript)) {
  throw "run_rag_indexer.ps1 not found: $RagIndexerScript"
}
if (-not (Test-Path -LiteralPath $PalestineNewsScript)) {
  throw "run_palestine_news.ps1 not found: $PalestineNewsScript"
}
if (-not (Test-Path -LiteralPath $NewsPlatformLowFrequencyRegisterScript)) {
  throw "register_news_platform_low_frequency_sources_task.ps1 not found: $NewsPlatformLowFrequencyRegisterScript"
}
if (-not (Test-Path -LiteralPath $NewsSourceAccuracyScript)) {
  throw "run_news_source_accuracy_audit.ps1 not found: $NewsSourceAccuracyScript"
}
if (-not (Test-Path -LiteralPath $ContextScript)) {
  throw "run_market_context.ps1 not found: $ContextScript"
}
if (-not (Test-Path -LiteralPath $BlsMacroScript)) {
  throw "run_bls_macro.ps1 not found: $BlsMacroScript"
}
if (-not (Test-Path -LiteralPath $MacroCalendarScript)) {
  throw "run_macro_calendar.ps1 not found: $MacroCalendarScript"
}
if (-not (Test-Path -LiteralPath $TwMarketFlowScript)) {
  throw "run_tw_market_flow.ps1 not found: $TwMarketFlowScript"
}
if (-not (Test-Path -LiteralPath $TwCloseContextScript)) {
  throw "run_tw_close_context.ps1 not found: $TwCloseContextScript"
}

function Register-MarketContextTask {
  param(
    [string]$TaskName,
    [string]$At,
    [string]$Description
  )

  $actionArgs = "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$ContextScript`" -EnvFile `"$EnvFile`" -AnalysisSlot `"market_context_pre_tw_open`" -ScheduledTime `"$At`" -LogLevel INFO"
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
    [string]$ExtraArgs = "",
    [int]$RepeatEveryHours = 0
  )

  $actionArgs = "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -EnvFile `"$EnvFile`" -LogLevel INFO"
  if ($ExtraArgs) {
    $actionArgs = "$actionArgs $ExtraArgs"
  }
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArgs -WorkingDirectory $ProjectRoot
  if ($RepeatEveryHours -gt 0) {
    $startAt = [DateTime]::Today.Add([TimeSpan]::Parse($At))
    while ($startAt -le (Get-Date)) {
      $startAt = $startAt.AddHours($RepeatEveryHours)
    }
    $trigger = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval (New-TimeSpan -Hours $RepeatEveryHours) -RepetitionDuration (New-TimeSpan -Days 3650)
  } else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
  }
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
  if ($RepeatEveryHours -gt 0) {
    Write-Host "  RepeatEveryHours: $RepeatEveryHours"
  }
}

function Register-LowFrequencyFixedWindowTask {
  $registerArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $NewsPlatformLowFrequencyRegisterScript,
    "-TaskName", $NewsPlatformLowFrequencyTaskName,
    "-EnvFile", $EnvFile,
    "-SourceIds", "tvbs,udn,setn",
    "-Categories", "society,politics",
    "-Limit", 20,
    "-AuthorLimit", 30,
    "-EveryMinutes", ($NewsPlatformLowFrequencyEveryHours * 60),
    "-LogLevel", "INFO"
  )
  if ($Force) {
    $registerArgs += "-Force"
  }

  & powershell.exe @registerArgs
  if ($LASTEXITCODE -ne 0) {
    throw "low-frequency fixed-window task registration failed with exit code $LASTEXITCODE"
  }
}

function Register-TwCloseContextTask {
  param(
    [string]$TaskName,
    [string]$At,
    [string]$Description
  )

  $actionArgs = "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$TwCloseContextScript`" -EnvFile `"$EnvFile`" -ScheduledTime `"$At`" -LogLevel INFO"
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
Register-CollectorTask -TaskName $PalestineNewsTaskName -ScriptPath $PalestineNewsScript -At $PalestineNewsAt -Description "Collect English Palestine/Gaza/West Bank issue news into long-term t_palestine_news_items." -ExtraArgs "-Limit 20" -RepeatEveryHours $PalestineNewsEveryHours
Register-LowFrequencyFixedWindowTask
Register-CollectorTask -TaskName $NewsSourceAccuracyTaskName -ScriptPath $NewsSourceAccuracyScript -At $NewsSourceAccuracyAt -Description "Audit news-platform official-list coverage and compensate missing source rows." -ExtraArgs "-Categories `"society,politics`" -Limit 20 -MinCoverage 0.85 -Compensate -FailOnWarn" -RepeatEveryHours $NewsSourceAccuracyEveryHours
Register-CollectorTask -TaskName $BlsMacroTaskName -ScriptPath $BlsMacroScript -At $BlsMacroAt -Description "Collect BLS official macro facts into t_relay_events for downstream Codex analysis."
Register-CollectorTask -TaskName $MacroCalendarTaskName -ScriptPath $MacroCalendarScript -At $MacroCalendarAt -Description "Collect official U.S. macro release dates into t_macro_release_calendar before LINE reminder delivery."
Register-MarketContextTask -TaskName $MarketContextTaskName -At $MarketContextAt -Description "Collect pre-open market context and store it as event-only facts before Taiwan open."
Register-CollectorTask -TaskName $TwMarketFlowTaskName -ScriptPath $TwMarketFlowScript -At $TwMarketFlowAt -Description "Collect Taiwan official market-flow facts into t_relay_events before Taiwan close context."
Register-TwCloseContextTask -TaskName $TwCloseContextTaskName -At $TwCloseContextAt -Description "Collect Taiwan close context from relay events at 15:20 local time."

foreach ($obsoleteTaskName in @(
  "NewsCollector-AnalysisPush-UsClose",
  "NewsCollector-AnalysisPush-PreTwOpen",
  "NewsCollector-MarketAnalysis-UsClose",
  "NewsCollector-MarketAnalysis-PreTwOpen",
  "NewsCollector-MarketAnalysis-TwClose",
  "NewsCollector-WeeklySummary"
)) {
  if (Get-ScheduledTask -TaskName $obsoleteTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $obsoleteTaskName -Confirm:$false
    Write-Host "Removed obsolete analysis task: $obsoleteTaskName" -ForegroundColor Yellow
  }
}
