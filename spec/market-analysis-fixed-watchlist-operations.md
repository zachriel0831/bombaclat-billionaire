# Superseded: Fixed Watchlist Operations

This document is superseded by:

- `spec/market-analysis-dynamic-trade-candidates.md`

Operational target:

```text
t_relay_events / market context
  -> Codex daily candidate generation
  -> t_trade_signals
  -> stock-monitor-service watches top 5
  -> order-dispatcher-service trades max 3 concurrently after paper/sandbox gates
```

Do not use the old fixed ten-stock pool as the target operating rule. It was useful for observation and debugging, but the platform direction is dynamic daily Taiwan intraday / short-swing candidates.

Current implementation state:

- As of 2026-07-20, `data-collecting` daily strategy candidates are dynamic and evidence-backed. Legacy fixed-pool names may remain only as compatibility aliases.
- `stock-monitor-service` can monitor and trigger, but does not manage positions or PnL.
- `order-dispatcher-service` still needs the trading state machine, audit tables, broker wrapper, and PnL reporting.
