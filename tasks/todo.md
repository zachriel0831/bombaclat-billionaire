# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Add official U.S. macro release calendar collection and Taiwan-time LINE reminder delivery.
- Requested by: user
- Start date: 2026-06-08
- Scope: Collect official release dates for U.S. CPI, PPI, Employment Situation/nonfarm payrolls, and Census retail sales; store normalized future release rows; let `line-relay-service` send one aggregated LINE reminder on the Taiwan date before release.

## Plan
- [x] Load repo boundaries, scheduler docs, source contracts, and official calendar sources.
- [x] Implement `t_macro_release_calendar` storage and collector in `data-collecting`.
- [x] Implement Java repository/scheduler/push flow in `line-relay-service`.
- [x] Update docs/spec/decision notes and scheduler runbooks.
- [x] Verify parser tests, Java tests, and a dry-run/current-calendar smoke check.

## Progress Notes
- 2026-06-08: Official sources selected: BLS annual release calendar for CPI/PPI/Employment Situation and U.S. Census Retail Trade release schedule for Advance Monthly Retail Trade.
- 2026-06-08: Architecture decision: store release-calendar facts in a dedicated long-lived table, not `t_relay_events` retention stream or `t_market_analyses`; Java owns reminder delivery and marks reminder state.
- 2026-06-08: Added `src/event_relay/macro_calendar.py`, migration SQL, runner script, and `NewsCollector-MacroCalendar` registration support.
- 2026-06-08: Added `line-relay-service` macro calendar repository, scheduler, reminder formatter, push-rate-limit type, and tests.
- 2026-06-08: Collector dry run against official 2026 sources returned 52 releases and zero fetch/parse errors.
- 2026-06-08: Live collector write inserted/updated 52 rows in `t_macro_release_calendar`.
- 2026-06-08: DB verification found upcoming reminders: CPI May 2026 on 2026-06-09, PPI May 2026 on 2026-06-10, Retail Sales May 2026 on 2026-06-16, and Nonfarm Payrolls June 2026 on 2026-07-01.
- 2026-06-08: Registered Windows Scheduled Task `NewsCollector-MacroCalendar` for daily 06:00 local/Taiwan time.
- 2026-06-08: Rebuilt and restarted `line-relay-service`; health check passed on `http://127.0.0.1:8080/health`.

## Current Verification
- [x] Python unit tests for macro calendar parsing/upsert.
- [x] Java unit/repository/scheduler tests for macro reminder delivery.
- [x] Live/dry-run collector output and DB state check.

## Current Review Summary
- Outcome: Implemented and smoke-tested.
- Open risks: Official BLS/Census HTML can change; the daily collector logs parse/fetch errors and leaves existing stored dates intact until corrected.
