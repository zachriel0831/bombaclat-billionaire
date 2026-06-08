# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Add heavyweight-stock earnings dates to market release calendar.
- Requested by: user
- Start date: 2026-06-08
- Scope: Extend the existing long-lived release-calendar collector so day-before LINE reminders can include watched megacap / heavyweight earnings dates alongside U.S. macro data.

## Plan
- [x] Load repo boundaries, NEWS-5 source contract, current collector, and LINE reminder reader.
- [x] Add NEWS-7 spec and update calendar docs / workflow memory.
- [x] Extend `event_relay.macro_calendar` with earnings-calendar rows and tests.
- [x] Update `line-relay-service` reminder copy to group macro releases and earnings rows.
- [x] Run focused Python and Java tests plus a dry-run collector check.

## Progress Notes
- 2026-06-08: Existing `t_macro_release_calendar` is long-lived storage; Java owns LINE delivery and sends one aggregated reminder for `reminder_date_taipei=today`.
- 2026-06-08: Nasdaq public earnings calendar endpoint returns daily earnings rows with `time-pre-market`, `time-after-hours`, and `time-not-supplied`; Yahoo quoteSummary calendarEvents currently returns 401 without crumb/cookie handling.
- 2026-06-08: Chosen MVP: store earnings rows in the existing table using `indicator_code=earnings_<symbol>` and `source_id=nasdaq_earnings`; no schema migration is required. Taiwan local exact dates can be supplied through a manual JSON file until a MOPS-specific adapter is added.
- 2026-06-08: Python unit tests passed for macro calendar + earnings parsing; dry-run with CASY test symbol returned one `earnings_release` row and no errors.
- 2026-06-08: Java focused tests passed after setting `JAVA_HOME` to local Temurin 21 because the Maven wrapper otherwise used Corretto 11.
- 2026-06-08: Live collector write with default heavyweight symbols succeeded: releases=59, affected_rows=111, errors=0; preview included TSM, GOOGL, TSLA, META, MSFT, AAPL, and AMZN earnings rows.

## Current Verification
- [x] Python unit tests for macro calendar + earnings row parsing.
- [x] Collector dry-run with earnings enabled.
- [x] Java reminder tests for grouped macro / earnings message.

## Current Review Summary
- Outcome: Implemented and focused verification passed.
- Open risks: Nasdaq calendar rows may be estimates and may omit Taiwan local tickers; rows preserve raw payload and use a manual override file for confirmed Taiwan-heavyweight events.
