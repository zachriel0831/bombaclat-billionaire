# US Index Market Storage Decision

- Date: 2026-04-19
- Scope: DJIA / S&P 500 stored-only persistence

## Decision
- Route US index snapshots through the normal relay `/events` path.
- Add a dedicated MySQL table `t_market_index_snapshots` for structured quote storage.
- Write two rows per snapshot event, one for `DJIA` and one for `S&P 500`.
- Mark queued `us_index_tracker` rows as `stored_only_market` during relay dispatch so the data is stored but not pushed to LINE.

## Why
- A single `/events` ingestion path keeps storage behavior consistent with other sources.
- Analytics needs structured rows instead of parsing LINE message text.
- Stored-only dispatch status preserves auditability in `t_relay_events` without generating user-facing pushes.

## Verification Basis
- Relay `/events` accepts `market_snapshot`, writes the queue row, and records rows in `t_market_index_snapshots`.
- Dispatch marks the queued US index row as `stored_only_market`.
