# Superseded: Fixed Watchlist Functional Spec

This document is superseded by:

- `spec/market-analysis-dynamic-trade-candidates.md`

The old fixed ten-stock pool was an observation/debugging aid. It is no longer the target trading-candidate policy.

Current target:

- Codex generates daily Taiwan intraday / short-swing candidates from `t_relay_events`, market context, quote evidence, RAG/history, and model judgment.
- `stock-monitor-service` monitors up to five ranked candidates.
- `order-dispatcher-service` will eventually trade at most three symbols concurrently after sandbox/paper state-machine validation.

Implementation note:

As of 2026-06-02, code still contains fixed-pool paths. Do not assume the runtime has already migrated.
