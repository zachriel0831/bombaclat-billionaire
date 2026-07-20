# Superseded: Fixed Watchlist Data Contract

This document is superseded by:

- `spec/market-analysis-dynamic-trade-candidates.md`

The old contract constrained `structured_json.stock_watch` and `t_trade_signals` to a fixed ten-stock observation pool. The target contract now treats `t_trade_signals` as a daily dynamic intraday / short-swing candidate table.

New contract summary:

- Candidate tickers may change daily.
- Candidates must remain Taiwan tradable symbols.
- Every candidate must keep evidence references and machine-readable entry / invalidation / take-profit context when intended for monitoring.
- `status=pending_review` remains the default.
- No signal is an order.
- Order, fill, position, and PnL state belong to `order-dispatcher-service`, not `data-collecting` or `stock-monitor-service`.

Implementation note:

As of 2026-07-20, runtime code uses dynamic evidence-backed Taiwan four-digit stock candidates. Do not reintroduce fixed-pool guardrails or padding.
