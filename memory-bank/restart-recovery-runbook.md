# Machine Restart Recovery Runbook

Use this when Windows/the machine was rebooted, long-running collectors stopped,
or the user asks whether society/politics news, finance news, or Taiwan pre-open
analysis ran after a restart.

Do not rediscover the flow from scratch. Start here, then inspect logs/DB evidence.

## Scope

- Repo root: `D:\work_space\stock\data-collecting`
- Shell: Windows PowerShell
- Python data services only; Java owns LINE delivery/webhook behavior
- Never operate outside `D:\work_space`

## 1. Restart Live Python Services

Start from repo root:

```powershell
Set-Location D:\work_space\stock\data-collecting
```

Restart the event relay and source bridge:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart_live_services.ps1 -EnvFile .env -LogLevel INFO
```

This script stops existing `event_relay.main` and `news_collector.relay_bridge`
Python processes, then opens two PowerShell windows:

- `scripts/run_event_relay.ps1`
- `scripts/run_source_bridge.ps1`

Keep both windows open. If one exits, inspect its visible error or latest log.

Restart the Taiwan society/politics `news_platform` loop separately. First check
for an existing loop:

```powershell
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and $_.CommandLine -match 'news_platform\.main' -and $_.CommandLine -match '--loop'
} | Select-Object ProcessId, CommandLine
```

If an old/stale loop exists, stop only that PID:

```powershell
Stop-Process -Id <PID>
```

Then start a fresh loop in a visible PowerShell window:

```powershell
Start-Process powershell -ArgumentList @(
  '-NoExit',
  '-ExecutionPolicy',
  'Bypass',
  '-Command',
  "Set-Location 'D:\work_space\stock\data-collecting'; `$env:PYTHONPATH='src'; python -m news_platform.main --loop 1> logs\news_platform_loop_current.log 2> logs\news_platform_loop_current.err.log"
)
```

## 2. Confirm Processes And Health

Expected Python process command lines:

- `event_relay.main`
- `news_collector.relay_bridge`
- `news_platform.main --loop`

Check:

```powershell
Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^python' -and $_.CommandLine -and (
    $_.CommandLine -match 'event_relay\.main' -or
    $_.CommandLine -match 'news_collector\.relay_bridge' -or
    $_.CommandLine -match 'news_platform\.main'
  )
} | Select-Object ProcessId, Name, CommandLine
```

Event relay health must return `{"ok": true}`:

```powershell
Invoke-RestMethod http://127.0.0.1:18090/healthz
```

Run the combined source-health report before calling restart recovery done:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_data_source_health.ps1 -EnvFile .env
```

Expected process probes count root Python service instances:

- `process_event_relay` rows=1
- `process_source_bridge` rows=1
- `process_news_platform_loop` rows=1

If `process_news_platform_loop` is greater than 1, stop only the extra
`news_platform.main --loop` PID and rerun the report.

## 3. Confirm Scheduled Tasks

If tasks are missing, register them again:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_market_analysis_tasks.ps1 -Force
powershell -ExecutionPolicy Bypass -File .\scripts\register_retention_cleanup_task.ps1 -Force
powershell -ExecutionPolicy Bypass -File .\scripts\register_weekly_summary_task.ps1 -Force
```

Check current task state:

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like 'NewsCollector-*' } |
  ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskName $_.TaskName
    [pscustomobject]@{
      TaskName = $_.TaskName
      State = $_.State
      LastRunTime = $info.LastRunTime
      NextRunTime = $info.NextRunTime
      LastTaskResult = $info.LastTaskResult
    }
  } | Format-Table -AutoSize
```

Important daily tasks:

- `NewsCollector-RagIndexer`
- `NewsCollector-BlsMacro`
- `NewsCollector-MarketContext-PreTwOpen`
- `NewsCollector-MarketAnalysis-PreTwOpen`
- `NewsCollector-TwMarketFlow`
- `NewsCollector-TwCloseContext`
- `NewsCollector-MarketAnalysis-TwClose`
- `NewsCollector-MarketAnalysis-UsClose`

Do not assume a task ran after reboot. Compare `LastRunTime` to today's expected
window.

## 4. Check Service Logs

Source bridge:

```powershell
$bridgeLog = Get-ChildItem runtime\logs\source-bridge-*.out.log |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
Get-Content -Path $bridgeLog.FullName -Tail 120
```

Look for:

- `X token preflight: resolved` if X is expected
- `Starting X account stream` or reconnect/backfill messages
- `X startup backfill complete` and `X filtered stream connected` when X is enabled
- `Polling source=truthsocial fetched=<n>` when Truth Social is enabled
- `Polling source=rss fetched=<n>`
- stored/duplicate counts for RSS/SEC/TWSE/MOPS
- US index tracker messages if enabled

If X is stale and the log shows `X stream got 429 and X_STOP_ON_429=true`,
restart the source bridge; this mode intentionally stops the stream until a
fresh process starts.

If Truth Social is stale, first prove the source still works without writing:

```powershell
$env:PYTHONPATH='src'
python -m news_collector.main fetch --source truthsocial --limit 5 --env-file .env --title-url-only --pretty --log-level INFO
```

If the no-write fetch succeeds but the bridge log has no
`Polling source=truthsocial`, restart the source bridge so it reloads `.env`
and resumes polling.

News platform:

```powershell
Get-Content logs\news_platform_loop_current.log -Tail 120
Get-Content logs\news_platform_loop_current.err.log -Tail 80
```

Look for:

- `News-platform ready`
- `Cycle complete fetched=<n> stored=<n> duplicates=<n> failed=<n>`
- `Keyword pass scanned=<n>`
- `Topic pass scanned=<n>`
- `Public records daily pass fetched=<n>`
- `Public-record link pass ...`

## 5. Check Society/Politics Data Freshness

No-write smoke check:

```powershell
$env:PYTHONPATH='src'
python -m news_platform.main --smoke
```

DB freshness check:

```powershell
mysql -h 127.0.0.1 -uroot -proot news_platform -e "
SELECT
  category,
  COUNT(*) AS rows_today,
  MAX(fetched_at) AS last_fetched_at,
  MAX(published_at) AS last_published_at,
  SUM(keywords_json IS NULL) AS missing_keywords,
  SUM(topics_json IS NULL) AS missing_topics
FROM t_news_articles
WHERE fetched_at >= CURDATE()
GROUP BY category
ORDER BY category;
"
```

Expected:

- both `society` and `politics` have same-day rows when sources are healthy
- `missing_keywords=0` and `missing_topics=0` after workers catch up

If rows exist but keywords/topics are missing:

```powershell
$env:PYTHONPATH='src'
python -m news_platform.main --extract-keywords --classify-topics
```

## 6. Check Finance/RSS Relay Data Freshness

No-write RSS smoke check:

```powershell
python -m news_collector.main fetch --source rss --limit 1 --title-url-only --pretty --log-level WARNING
```

DB freshness check:

```powershell
mysql -h 127.0.0.1 -uroot -proot news_relay -e "
SELECT
  source,
  COUNT(*) AS rows_today,
  MAX(created_at) AS last_created_at,
  MAX(published_at) AS last_published_at
FROM t_relay_events
WHERE created_at >= CURDATE()
  AND source LIKE 'official_rss%'
GROUP BY source
ORDER BY last_created_at DESC;
"
```

Expected:

- same-day `official_rss` rows exist
- bridge log shows recent `Polling source=rss fetched=<n>`

If stale, restart the source bridge with `scripts\restart_live_services.ps1` and
re-check the latest bridge log.

## 7. Check Taiwan Pre-Open Analysis

Check whether pre-open or market-calendar fallback ran today:

```powershell
mysql -h 127.0.0.1 -uroot -proot news_relay -e "
SELECT
  id,
  analysis_date,
  analysis_slot,
  scheduled_time_local,
  push_enabled,
  events_used,
  market_rows_used,
  updated_at
FROM t_market_analyses
WHERE analysis_date = DATE_FORMAT(CURDATE(), '%Y-%m-%d')
  AND analysis_slot IN ('pre_tw_open', 'macro_daily')
ORDER BY updated_at DESC;
"
```

For `pre_tw_open`, verify dynamic Taiwan intraday / short-swing candidate rows
in `t_trade_signals`. Fixed-pool fallback rows are no longer target behavior;
treat any new rows that look padded from the old pool as a regression:

```powershell
mysql -h 127.0.0.1 -uroot -proot news_relay -e "
SELECT ticker, name, status, updated_at
FROM t_trade_signals
WHERE analysis_date = DATE_FORMAT(CURDATE(), '%Y-%m-%d')
  AND analysis_slot = 'pre_tw_open'
ORDER BY ticker;
"
```

If the machine was down during the pre-open window, run catch-up manually:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -EnvFile .env -Slot pre_tw_open -Force
```

Then re-run the `t_market_analyses` and `t_trade_signals` checks.

## 8. Check Market Context Inputs

Before or after pre-open analysis, verify same-day context facts:

```powershell
mysql -h 127.0.0.1 -uroot -proot news_relay -e "
SELECT source, COUNT(*) AS rows_today, MAX(created_at) AS last_created_at
FROM t_relay_events
WHERE created_at >= CURDATE()
  AND source LIKE 'market_context:%'
GROUP BY source
ORDER BY last_created_at DESC;
"
```

If context is missing before analysis:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_bls_macro.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env
```

For Taiwan close:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_market_flow.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_close_context.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -EnvFile .env -Slot tw_close -Force
```

## 9. Optional UI / Market Candle Check

If the frontend shows stale TAIEX time after a restart, check candle API evidence
before changing UI again:

```powershell
Invoke-RestMethod 'http://localhost:8081/api/market/candles?symbol=TAIEX&market=TW&interval=1m&limit=3'
Invoke-RestMethod 'http://localhost:8081/api/market/candles?symbol=2330&market=TW&interval=1m&limit=3'
```

Rules:

- Compare UTC ISO timestamps to Asia/Taipei date.
- If index data is prior-day, UI must show date context such as `昨日 HH:mm`, not time-only.
- If TAIEX has no same-day candle but stocks do, treat it as upstream index-source freshness, not a frontend formatting bug.
- If SSE/live updates are expected, inspect stock-monitor Redis publish logs in the relevant service under `D:\work_space`.

## Minimum Done Criteria

Do not report restart recovery complete until there is evidence for:

- `event_relay.main`, `news_collector.relay_bridge`, and `news_platform.main --loop` running
- `/healthz` returns `{"ok": true}`
- source bridge log has recent RSS polling
- `news_platform` log has a recent cycle and topic pass or no pending work
- society/politics DB check has same-day rows and no stale missing topics after catch-up
- finance RSS DB check has same-day `official_rss` rows
- if X is enabled, bridge log shows X backfill/stream evidence or a current
  X health row
- if Truth Social is enabled, bridge log shows `Polling source=truthsocial` or
  a current Truth Social health row
- pre-open DB check has today's `pre_tw_open` or calendar-guarded `macro_daily` row
- if `pre_tw_open` ran, `t_trade_signals` has same-day dynamic candidate rows or the analysis records a clear data gap
