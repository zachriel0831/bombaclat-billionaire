# NEWS-7 Heavyweight Earnings Calendar Reminders

Status: Done

## Goal

Add tracked heavyweight-stock earnings dates to the existing long-lived market
release calendar so the day-before LINE reminder can mention both:

- U.S. macro releases from NEWS-5.
- Watched megacap / heavyweight earnings releases.

## Non-goals

- Do not move LINE delivery into `data-collecting`.
- Do not create a second reminder schedule or a second LINE quota type.
- Do not treat estimated earnings dates as official confirmations.
- Do not place earnings calendar rows into `t_relay_events`; relay retention is
  too short for calendar facts.

## Source Contract

Primary MVP source:

- Nasdaq public daily earnings calendar endpoint:
  `https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`

Default watched symbols are calendar-tracking coverage only, not trading
recommendations. They should focus on the names most likely to move U.S. tech,
ADR, Taiwan AI / semiconductor sentiment, and Taiwan index-heavy financials:

- U.S. / ADR: `NVDA`, `AAPL`, `MSFT`, `AMZN`, `GOOGL`, `META`, `TSLA`,
  `AVGO`, `AMD`, `ASML`, `QCOM`, `MU`, `ORCL`, `ARM`, `TSM`.
- Taiwan local: `2330`, `2317`, `2454`, `2308`, `2382`, `3711`, `3231`,
  `6669`, `2303`, `2881`, `2882`, `2891`.

Nasdaq can populate U.S. / ADR rows automatically. Taiwan local symbols are in
the same tracking config, but their exact earnings / board-meeting dates must
come from `MACRO_CALENDAR_EARNINGS_MANUAL_FILE` or a future MOPS adapter.

Configurable overrides:

- `MACRO_CALENDAR_EARNINGS_SYMBOLS`: comma-separated list. Each item can be
  `SYMBOL` or `SYMBOL:Display Name:Market:Importance`.
- `MACRO_CALENDAR_EARNINGS_LOOKAHEAD_DAYS`: default `75`.
- `MACRO_CALENDAR_EARNINGS_ENABLED`: default `true`.
- `MACRO_CALENDAR_EARNINGS_MANUAL_FILE`: optional JSON file for confirmed or
  manually curated earnings events, especially Taiwan local tickers whose exact
  earnings / board-meeting dates are not available from Nasdaq.

Manual JSON item shape:

```json
{
  "symbol": "2330",
  "company_name": "台積電",
  "market": "TW",
  "release_date": "2026-07-16",
  "release_time": "14:00",
  "timezone": "Asia/Taipei",
  "time_label": "法說會",
  "period_label": "2026 Q2",
  "source_url": "https://example.com/source",
  "importance": 5,
  "date_status": "confirmed"
}
```

## Storage Contract

Table remains `t_macro_release_calendar` for backward compatibility.

Earnings rows use existing columns:

- `source_id`: `nasdaq_earnings` or `manual_earnings`.
- `indicator_code`: `earnings_<symbol>`, normalized to lowercase
  alphanumeric / underscore.
- `indicator_name`: human-readable earnings event name.
- `period_label`: fiscal quarter ending or manually supplied period.
- `release_at_utc`, `release_at_taipei`: calculated from the source date and
  source time label. Nasdaq `time-pre-market`, `time-after-hours`, and
  `time-not-supplied` are approximate time buckets, not precise company times.
- `reminder_date_taipei`: `DATE(release_at_taipei) - 1 day`.
- `raw_json`: must include `event_type=earnings_release`, `symbol`, `market`,
  `time_type`, `time_label`, `date_status`, and source payload fields.

No DDL change is required. Java can identify earnings rows by
`indicator_code LIKE 'earnings_%'`.

## Service Boundary

- `data-collecting` fetches / normalizes earnings calendar rows and upserts them
  into `t_macro_release_calendar`.
- `line-relay-service` reads pending rows and sends one grouped reminder.
- `data-collecting` must not contact LINE.

## Reminder Behavior

The existing macro calendar reminder schedule remains the owner:

- Collector: `NewsCollector-MacroCalendar`, default `06:00` Asia/Taipei.
- Reminder: `LINE_SCHEDULE_MACRO_CALENDAR_REMINDER_CRON`, default `08:00`
  Asia/Taipei.

When pending rows include both macro and earnings events, the LINE message should
group them into:

- `美國經濟數據`
- `權值股財報`

Rows are marked pushed only after at least one target receives the aggregated
message.

## Acceptance

- Collector dry-run includes earnings rows when watched symbols appear in the
  lookahead window or manual JSON file.
- Existing CPI/PPI/nonfarm payrolls/retail sales behavior remains unchanged.
- Earnings event keys remain stable when an estimated date shifts for the same
  symbol and fiscal period.
- Java reminder message groups earnings rows separately from macro rows.
- Focused Python and Java tests pass.
