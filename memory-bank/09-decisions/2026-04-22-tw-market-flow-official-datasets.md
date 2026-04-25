# Decision: Taiwan Official Market-Flow Events

## Date
2026-04-22

## Context
REQ-009 adds official Taiwan market-flow facts for downstream market analysis. Source/context facts must be stored in `t_relay_events` first and must not write directly to `t_market_analyses`.

## Decision
- Implement `event_relay.tw_market_flow` as a stored-only dataset collector.
- Use official OpenAPI endpoints from TWSE, TPEx, and TAIFEX.
- Write one dataset-level event per official dataset into `t_relay_events`.
- Use source families `market_context:twse_flow`, `market_context:tpex_flow`, and `market_context:taifex_flow`.
- Build stable dedupe/event ids from source family, trade date, and dataset.
- Store official rows and dataset-level normalized metrics in `raw_json`.

## Consequences
- Market-analysis jobs can consume Taiwan flow facts from the existing `market_context:*` event window.
- Dataset-level metrics keep the first version compact while retaining official rows for traceability.
- Scheduler integration runs this collector before Taiwan close context so `tw_close` analysis can consume same-day flow facts when official datasets are available.
