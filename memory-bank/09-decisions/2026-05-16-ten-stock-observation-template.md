# Ten-Stock Observation Template

## Superseded

Superseded on 2026-06-02 by `2026-06-02-dynamic-intraday-candidate-pipeline.md`.

This document is historical. The ten-stock pool existed to make the system easy to observe and compare. The target trading-candidate flow is now dynamic Codex daily Taiwan intraday / short-swing candidate generation.

## Date
2026-05-16

## Superseded
Superseded on 2026-07-20 by `spec/market-analysis-dynamic-trade-candidates.md`. The ten-stock pool was for observation and debugging only; daily strategy candidates are now dynamic and evidence-backed.

## Decision
Historical decision: `market_analysis` kept the individual-stock section as a fixed monitoring pool, and expanded the visible pool from five to ten stocks:

| ticker | name | market | role |
|---|---|---|---|
| `2330` | 台積電 | TWSE | semiconductor mega-cap / AI cycle proxy |
| `2317` | 鴻海 | TWSE | AI server / assembly proxy |
| `2454` | 聯發科 | TWSE | IC design proxy |
| `2308` | 台達電 | TWSE | power / AI server infrastructure proxy |
| `2881` | 富邦金 | TWSE | financial / rate-insurance proxy |
| `2882` | 國泰金 | TWSE | financial / rate-insurance proxy |
| `2485` | 兆赫 | TWSE | networking / communications proxy |
| `3535` | 晶彩科 | TWSE | equipment / optoelectronics proxy |
| `3715` | 定穎投控 | TWSE | PCB / auto electronics proxy |
| `2351` | 順德 | TWSE | lead frame / semiconductor materials proxy |

## Visible Template Contract
- Append at most ten rows under `## 今日個股觀察`.
- Historical behavior only: the fixed pool stayed visible. Current behavior must not render neutral rows to pad an empty or thin dynamic candidate list.
- Every row must show:
  - `利多`: concrete catalyst, sector support, or current evidence chain that could support the stock.
  - `利空`: downside risk, valuation/relative-strength gap, invalidation condition, or missing evidence.
  - `買入注意`: the actionable watch condition, entry area, stop, first target, and confidence.
- If there is no valuation or relative-discount evidence, the row must put that gap under `利空` or `買入注意` instead of claiming the stock is undervalued.

## Boundaries
- This remains a watch/monitor template, not a model-selected stock-picking universe.
- The model must not introduce substitute Taiwan tickers outside the ten-stock pool.
- `t_trade_signals` rows remain `pending_review`; no row is an order.
- Existing exclusions still apply, including default exclusion of `4749`.

## Operational Contract
- `MARKET_CONTEXT_TWSE_CODES=2330,2317,2454,2308,2881,2882,2485,3535,3715,2351`
- `MARKET_CONTEXT_TW_YAHOO_SYMBOLS=2330.TW:台積電,2317.TW:鴻海,2454.TW:聯發科,2308.TW:台達電,2881.TW:富邦金,2882.TW:國泰金,2485.TW:兆赫,3535.TW:晶彩科,3715.TW:定穎投控,2351.TW:順德`
- Historical UI wording used `今日個股觀察` / fixed watch pool language and exposed the three reasoning lines above. Current UI/report output should use dynamic candidate language when showing trade candidates.
