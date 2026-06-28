# Visible U.S. Close Fixed Watch Section

## Date
2026-05-09

## Status
Amended 2026-05-11 by `2026-05-11-fixed-market-analysis-watch-pool.md`.
Amended 2026-05-16 by `2026-05-16-ten-stock-observation-template.md`.
Superseded for trading-candidate policy on 2026-06-02 by `2026-06-02-dynamic-intraday-candidate-pipeline.md`.

## Decision
Delivery-eligible `us_close` analyses use the same visible fixed-pool watch path as `pre_tw_open`.

When `structured_json.stock_watch` rows name one of the fixed Taiwan symbols but omit entry, stop, or target levels, the market-analysis pipeline fills missing reference levels from deterministic Taiwan quote/context rows when recent price evidence exists. The stored report then appends a `## 今日個股觀察` section for the fixed pool only.

## Rationale
TW-holiday `us_close` rows can be user-visible delivery content. If price fields are null, deterministic quote/context levels keep the watch section useful without asking the model to guess prices or choose substitute tickers.

## Boundaries
- Fixed pool only: use the current ten-stock pool in `2026-05-16-ten-stock-observation-template.md`.
- Signals remain `pending_review`; they are not orders.
- Missing price levels stay as data gaps when no quote/context evidence exists.
- `tw_close` remains stored-only and does not append the visible stock watch section.

This decision remains historical context for visible U.S. close report behavior. It must not be used as the target source of Taiwan intraday / short-swing trading candidates after the dynamic-candidate migration.
