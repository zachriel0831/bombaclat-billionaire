# Decision: BLS Macro Facts as Relay Events

## Date
2026-04-22

## Context
REQ-010 adds official U.S. macro facts for downstream market analysis. Source facts must be available to analysis through `t_relay_events`, not written directly into `t_market_analyses`.

## Decision
- Implement `event_relay.bls_macro` as a stored-only collector.
- Use BLS Public Data API v2 at `https://api.bls.gov/publicAPI/v2/timeseries/data/`.
- Support optional `BLS_API_KEY`; no-key mode remains available for low-frequency collection.
- Write one event per latest observation with `source=market_context:bls_macro`.
- Build stable event ids from `bls_macro`, `series_id`, `year`, and `period`.
- Preserve footnotes and normalized metrics in `raw_json`.

## Consequences
- `us_close`, `pre_tw_open`, and other analysis slots can read BLS facts through the same relay-event window as news and market context.
- Revised/preliminary BLS data remains traceable because raw footnotes and period metadata are stored with each event.
