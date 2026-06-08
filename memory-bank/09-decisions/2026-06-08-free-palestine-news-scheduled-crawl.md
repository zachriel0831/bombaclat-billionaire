# 2026-06-08 Free Palestine News Scheduled Crawl

## Decision

Run the Free Palestine English issue-news collector as a recurring Windows
Scheduled Task named `NewsCollector-PalestineNews`.

## Rationale

The `/timeline` module needs current English references, but these rows are
long-lived issue context. They must stay separate from the short-retention
finance/event relay stream.

## Operating Contract

- Schedule starts at the next 06:10 local/Taiwan time after registration.
- The task repeats every 3 hours.
- The task runs `scripts/run_palestine_news.ps1 -EnvFile .env -LogLevel INFO -Limit 20`.
- Accepted rows upsert into `t_palestine_news_items` by `url_hash`.
- Normal scheduled writes do not create `t_relay_events` rows.
- LINE delivery remains out of scope for this Python repo.

## Verification

- Unit tests: `python -m unittest tests.test_palestine_news -v`
- Dry run: `scripts/run_palestine_news.ps1 -EnvFile .env -Limit 5 -DryRun`
- Live write: `scripts/run_palestine_news.ps1 -EnvFile .env -Limit 20`
- Scheduler check: `Get-ScheduledTask -TaskName NewsCollector-PalestineNews`
