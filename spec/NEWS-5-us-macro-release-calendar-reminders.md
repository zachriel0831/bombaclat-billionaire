# NEWS-5 U.S. Macro Release Calendar Reminders

Status: In Progress

## Goal

Collect official release dates for the most market-moving U.S. macro data and
enable LINE reminders on the Taiwan date before release.

Covered indicators:

- U.S. CPI
- U.S. PPI
- U.S. Employment Situation / nonfarm payrolls
- U.S. Advance Monthly Retail Trade / retail sales

## Source Contract

- BLS annual release calendar: `https://www.bls.gov/schedule/<year>/home.htm`
- Census Retail Trade release schedule:
  `https://www.census.gov/retail/release_schedule.html`
- Official source times are interpreted as U.S. Eastern time.
- Stored rows must include UTC and Asia/Taipei release timestamps.

## Storage Contract

Table: `t_macro_release_calendar`

Required fields:

- `event_key`: stable SHA-1 key built from source, indicator, period, and UTC release time.
- `indicator_code`: `us_cpi`, `us_ppi`, `us_nonfarm_payrolls`, or `us_retail_sales`.
- `release_at_utc`, `release_at_taipei`.
- `reminder_date_taipei`: `DATE(release_at_taipei) - 1 day`.
- `reminder_pushed`, `reminder_pushed_at`, `reminder_push_status`, `reminder_push_error`.
- `source_url` and `raw_json` for traceability.

This table is long-lived calendar storage. Do not store these reminders in
`t_relay_events` retention storage or `t_market_analyses` prose rows.

## Service Boundary

- `data-collecting` fetches official calendars and upserts rows.
- `line-relay-service` reads pending rows and sends LINE reminders.
- `data-collecting` must not contact LINE.

## Scheduling

- Data collector: `NewsCollector-MacroCalendar`, default daily `06:00` Asia/Taipei.
- LINE reminder: default daily `08:00` Asia/Taipei via `LINE_SCHEDULE_MACRO_CALENDAR_REMINDER_CRON`.
- Reminder semantics: send one aggregated message when rows exist with
  `reminder_date_taipei = today` and `reminder_pushed = 0`.

## Acceptance

- Python collector dry-run shows official rows with correct Taipei release time.
- Python collector writes/upserts `t_macro_release_calendar` without duplicates.
- Java reminder sends with `PushMessageType.MACRO_CALENDAR`.
- Java marks rows as sent only after at least one target receives the reminder.
- Redis rate limits for macro reminders do not consume `PUBLIC_ANALYSIS` quota.
