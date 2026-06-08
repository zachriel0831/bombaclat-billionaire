# 2026-06-08 Heavyweight Earnings Calendar Reminders

## Context

The platform already collects U.S. macro release dates into
`t_macro_release_calendar` and lets `line-relay-service` send one Taiwan-time
day-before reminder. The user asked to include heavyweight-stock earnings dates
in the same calendar.

## Decision

Use the existing long-lived `t_macro_release_calendar` table and reminder
pipeline. Earnings rows are identified without a schema change:

- `source_id=nasdaq_earnings` or `manual_earnings`
- `indicator_code=earnings_<symbol>`
- `raw_json.event_type=earnings_release`

The Python collector fetches Nasdaq daily earnings calendar rows over a
lookahead window and filters to configured heavyweight symbols. A manual JSON
file can override or add confirmed dates, especially Taiwan local tickers whose
exact earnings / board-meeting dates are not available from Nasdaq.

The default calendar-tracking list is:

- U.S. / ADR: `NVDA`, `AAPL`, `MSFT`, `AMZN`, `GOOGL`, `META`, `TSLA`,
  `AVGO`, `AMD`, `ASML`, `QCOM`, `MU`, `ORCL`, `ARM`, `TSM`.
- Taiwan local: `2330`, `2317`, `2454`, `2308`, `2382`, `3711`, `3231`,
  `6669`, `2303`, `2881`, `2882`, `2891`.

These symbols are for release-calendar coverage, not trade recommendation.
Taiwan local rows still require manual confirmed dates or a future MOPS adapter.

`line-relay-service` still owns delivery and sends one grouped message. It
separates rows into `美國經濟數據` and `權值股財報`.

## Rationale

- Reuses the tested reminder table, delivery state, Redis quota, and scheduled
  LINE job.
- Avoids a second push channel while ngrok / LINE quota has been a recurring
  operational concern.
- Keeps estimated Nasdaq earnings dates traceable in `raw_json` instead of
  presenting them as official company confirmations.
- Keeps Taiwan local exact dates possible through manual confirmed rows until a
  dedicated MOPS adapter is designed.

## Consequences

- No DDL migration is required.
- Sub-agents should not store earnings dates in `t_relay_events`.
- If a manual row and Nasdaq row share the same `indicator_code` and
  `period_label`, the collector keeps the manual row.
- Future MOPS work should either emit the same `earnings_<symbol>` contract or
  propose a replacement market-calendar table in a new NEWS requirement.
