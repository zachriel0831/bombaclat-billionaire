# 2026-06-08 U.S. Macro Release Calendar Reminders

## Decision

Store official U.S. macro release dates in a dedicated long-lived table,
`t_macro_release_calendar`, and let `line-relay-service` send Taiwan-time
day-before reminders from that table.

## Rationale

- Release dates are durable calendar facts, not short-lived relay events.
- `t_relay_events` has retention cleanup and should not own LINE delivery state.
- `t_market_analyses` is for generated prose, not official schedule facts.
- Java already owns LINE targets, push toggles, Redis quota, and delivery state.

## Sources

- BLS annual release calendar for CPI, PPI, and Employment Situation.
- U.S. Census Retail Trade release schedule for retail sales.

## Runtime Shape

- `data-collecting`: `scripts/run_macro_calendar.ps1`
- Default Windows task: `NewsCollector-MacroCalendar` at `06:00` Asia/Taipei
- Java reminder cron: `LINE_SCHEDULE_MACRO_CALENDAR_REMINDER_CRON`, default `08:00` Asia/Taipei
- Reminder message type: `MACRO_CALENDAR`, separate from `PUBLIC_ANALYSIS`
