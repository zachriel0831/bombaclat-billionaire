# NEWS-6 Free Palestine News Scheduled Crawl

## Status

Done

## Context

NEWS-4 normalized Free Palestine English issue news into
`t_palestine_news_items`. The crawler can run manually, but the public
`/timeline` module needs periodic refreshes so the current-news section does
not depend on a human operator.

## Requirement

Run the Free Palestine English issue-news crawler on a recurring local schedule.
The scheduled task must:

- call `scripts/run_palestine_news.ps1`
- write accepted rows to `t_palestine_news_items`
- keep normal writes out of `t_relay_events`
- remain idempotent through `url_hash` upsert
- avoid LINE delivery or market-analysis side effects

## Schedule

Windows Scheduled Task:

- Task name: `NewsCollector-PalestineNews`
- Start time: next `06:10` local / Taiwan time after registration
- Repetition: every 3 hours
- Script: `scripts/run_palestine_news.ps1`
- Args: `-EnvFile .env -LogLevel INFO -Limit 20`

## Source Contract

Default feeds are configured in `event_relay.palestine_news`:

- Google News English search for Gaza / Palestine / Palestinian / West Bank
- Al Jazeera English RSS
- BBC Middle East RSS
- Guardian Palestinian territories RSS

Accepted rows must be likely English and match Palestine/Gaza/West Bank issue
terms. CJK or unrelated market/news rows are skipped.

## Verification

Focused tests:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_palestine_news -v
```

Dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 5 -DryRun
```

Live write:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 20
```

Scheduled task check:

```powershell
Get-ScheduledTask -TaskName NewsCollector-PalestineNews | Get-ScheduledTaskInfo
```

## DoD

- `register_market_analysis_tasks.ps1` can register `NewsCollector-PalestineNews`
- Local scheduled task exists and has a future `NextRunTime`
- Focused Python tests pass
- Dry-run fetch returns explicit fetched/accepted/skipped/error counts
- Live run stores or dedupes rows in `t_palestine_news_items`
- Documentation names the schedule and storage boundary
