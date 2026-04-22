# Decision: Weekly summary runs Sunday 23:00 (supersedes 2026-04-19-weekly-summary-monday-0730)

- Date: 2026-04-22
- Status: accepted
- Supersedes: `2026-04-19-weekly-summary-monday-0730.md`

## Context
- Java `MarketAnalysisScheduler` reads the `weekly_tw_preopen` slot at Taipei Monday `05:10` (replacing `us_close` on Mondays).
- The previous Python schedule generated the weekly summary at Monday `07:30`, after Java already tried to read it. Java always saw no row and skipped push.
- The weekly summary must exist in `t_market_analyses` before Java polls on Monday morning.

## Decision
- Run `weekly_summary` at Sunday `23:00` Asia/Taipei (6 hours before Java polls).
- Defaults updated in `scripts/register_weekly_summary_task.ps1`, `.env` (`WEEKLY_SUMMARY_WEEKDAY=6`, `HOUR=23`, `MINUTE=0`), and the in-code defaults in `event_relay/weekly_summary.py` remain `0/7/30` (env overrides).

## Consequences
- Java's Monday `05:10` push has a fresh weekly summary available.
- Sunday-night generation is slightly further from Monday's decision window, but the alternative (Monday morning race) is unreliable.
- If the Sunday run fails, there is still a ~6-hour window before Java polls; operators can re-run with `--force` before 05:10.
