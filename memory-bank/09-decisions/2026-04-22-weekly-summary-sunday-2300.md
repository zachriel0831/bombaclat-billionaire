# Decision: Weekly summary runs Saturday 23:00 for Sunday 05:10 delivery

- Date: 2026-04-22
- Status: accepted
- Supersedes: `2026-04-19-weekly-summary-monday-0730.md`

## Context
- Java `MarketAnalysisScheduler` reads the `weekly_tw_preopen` slot at Taipei Sunday `05:10` (replacing `us_close` on Sundays).
- The weekly summary must exist in `t_market_analyses` before Java polls on Sunday morning.
- `analysis_date` must match the downstream Sunday delivery date rather than an ISO week label, or Java's exact date lookup will skip the row.

## Decision
- Run `weekly_summary` at Saturday `23:00` Asia/Taipei so the row exists before Sunday `05:10`.
- Store `analysis_date` as the target Sunday delivery date in `YYYY-MM-DD`, not `YYYY-Www`.
- Defaults are aligned in `scripts/register_weekly_summary_task.ps1`, `.env` (`WEEKLY_SUMMARY_WEEKDAY=5`, `HOUR=23`, `MINUTE=0`), and `event_relay.weekly_summary`.

## Consequences
- Java's Sunday `05:10` push has a fresh weekly summary available.
- Saturday-night generation stays close to the Sunday pre-open window without racing the Java scheduler.
- If the Saturday run fails, there is still a ~6-hour window before Java polls; operators can re-run with `--force` before 05:10.
