# Visible U.S. Close Fixed Watch Section

## Date
2026-05-09

## Status
Amended 2026-05-11 by `2026-05-11-fixed-market-analysis-watch-pool.md`.

## Decision
Delivery-eligible `us_close` analyses use the same visible fixed-pool watch path as `pre_tw_open`.

When `structured_json.stock_watch` rows name one of the fixed Taiwan symbols but omit entry, stop, or target levels, the market-analysis pipeline fills missing reference levels from deterministic Taiwan quote/context rows when recent price evidence exists. The stored report then appends a `## 今日個股觀察` section for the fixed pool only.

## Rationale
TW-holiday `us_close` rows can be user-visible delivery content. If price fields are null, deterministic quote/context levels keep the watch section useful without asking the model to guess prices or choose substitute tickers.

## Boundaries
- Fixed pool only: `2330`, `2603`, `2882`, `1605`, `4956`.
- Signals remain `pending_review`; they are not orders.
- Missing price levels stay as data gaps when no quote/context evidence exists.
- `tw_close` remains stored-only and does not append the visible stock watch section.
