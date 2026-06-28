# Decision: Dynamic Intraday Candidate Pipeline

## Date
2026-06-02

## Status
Target design. Implementation pending.

## Context

The fixed ten-stock watch pool was introduced to make the platform easy to observe, debug, and compare while stock monitoring, signal extraction, and LINE/report flows were being stabilized.

That fixed pool is not the desired trading universe. The product direction is to let Codex produce a daily set of Taiwan stocks suitable for intraday trading or short swing trading, using `data-collecting` evidence plus Codex model judgment.

## Decision

Supersede the fixed-pool trading-candidate policy with dynamic daily candidates:

1. Codex generates daily Taiwan stock candidates from:
   - `t_relay_events`
   - market context rows
   - Taiwan market-flow context
   - recent quote/context evidence
   - RAG or historical cases when available
   - Codex model judgment
2. `data-collecting` stores selected candidates in `t_trade_signals`.
3. `stock-monitor-service` syncs `t_trade_signals` and monitors the top five ranked symbols.
4. `order-dispatcher-service` will eventually use approved `t_trade_signals` / trigger events for intraday and short-swing trading.
5. Trading caps:
   - monitor at most five symbols at a time
   - trade at most three symbols concurrently
   - keep live trading disabled until paper/sandbox validation, reconciliation, kill switch, and PnL reporting exist

## Boundaries

- `data-collecting` may generate candidates, but it does not submit broker orders.
- `stock-monitor-service` monitors quotes and writes trigger events only.
- `order-dispatcher-service` owns order intent, order lifecycle, fills, positions, and PnL.
- LINE delivery remains owned by `line-relay-service`.
- A signal is not an order.

## Required Future State Machine

The trading state machine must live in `order-dispatcher-service`.

Minimum lifecycle:

```text
candidate
  -> pending_review
  -> approved_for_monitor
  -> monitoring
  -> entry_triggered
  -> order_intent_created
  -> order_submitted
  -> partially_filled
  -> position_open
  -> exit_intent_created
  -> exit_order_submitted
  -> position_closed
```

Exception / terminal states:

```text
rejected
expired
cancelled
order_rejected
entry_missed
force_closed
error_needs_review
```

Position reporting must include realized and unrealized PnL, fees/tax, quantity, average entry/exit price, linked `analysis_id`, `signal_id`, and trigger-event ids.

## Current Gap

As of 2026-06-02:

- `data-collecting` still contains fixed-pool code such as `FIXED_MARKET_ANALYSIS_WATCH_POOL`.
- `stock-monitor-service` has quote status, selected watchlists, trigger evaluation, and entry-first trigger state, but no position or PnL state.
- `order-dispatcher-service` is still skeleton-only and has no trigger consumer, broker wrapper, audit schema, order lifecycle, position lifecycle, or PnL reporting.

## Consequences

- Existing fixed-pool docs are now superseded by `spec/market-analysis-dynamic-trade-candidates.md`.
- Future implementation should remove hard fixed-pool restrictions from dynamic candidate generation while preserving evidence, claim verification, review gates, and order-safety boundaries.
- Stock monitoring can remain capped at five even if `data-collecting` produces more candidates.
- Order execution cannot go live until the state machine and PnL reporting are implemented.
