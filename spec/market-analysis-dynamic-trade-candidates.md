# Market Analysis Dynamic Trade Candidates

## Status

Partial runtime implementation. `t_trade_signals` now stores deterministic
candidate ranking fields, but the full fixed-pool removal / broad dynamic
candidate universe is not complete yet.

This supersedes the earlier fixed-pool watchlist documents:

- `spec/market-analysis-fixed-watchlist-functional-spec.md`
- `spec/market-analysis-fixed-watchlist-data-contract.md`
- `spec/market-analysis-fixed-watchlist-operations.md`

The earlier ten-stock pool existed to make the product easy to observe and debug. It is no longer the desired trading-candidate policy.

## Product Direction

Each trading day, Codex should produce Taiwan stock candidates suitable for intraday trading or short swing trading. The candidates must be based on:

- local `t_relay_events`
- market context rows
- Taiwan market-flow context
- recent quote/context evidence
- RAG or historical cases when available
- Codex model judgment inside the configured automation

Codex may select tickers outside the old observation pool, but every selected ticker must be traceable to evidence and must pass deterministic validation before it reaches monitoring or trading.

## End-To-End Flow

```text
data-collecting
  -> collect source facts into t_relay_events and market-context tables
  -> Codex daily candidate generation
  -> t_market_analyses
  -> t_trade_signals

stock-monitor-service
  -> sync t_trade_signals
  -> choose top 5 monitor candidates
  -> Fugle MarketData WebSocket
  -> entry_hit / stop_hit / target_hit trigger events

order-dispatcher-service
  -> consume approved trigger/order intents
  -> enforce risk caps
  -> max 3 concurrently traded symbols
  -> broker sandbox / paper first
  -> live trading only after explicit gate
```

## Candidate Generation Rules

`t_trade_signals` should represent a daily dynamic candidate list, not a fixed observation list.

Candidate requirements:

- Taiwan listed or TPEx tradable equity.
- Has enough same-day or recent evidence to justify monitoring.
- Has `strategy_type`, `direction`, `entry_zone`, `invalidation`, and `take_profit_zone` when intended for automated monitoring.
- Has deterministic `risk_reward_ratio`, `candidate_score`, and `avoid_reason`.
  `risk_reward_ratio` uses the same price-level semantics as
  `stock-monitor-service`: long uses `entry_zone.high`, short uses
  `entry_zone.low`, both against `invalidation.price` and
  `take_profit_zone.first`.
- Starts with `status=pending_review`.
- Is never an order.
- Keeps evidence references in `source_event_ids_json` or `raw_json`.
- Stores telemetry proving whether external paid provider APIs were called. Codex guard jobs should use `external_provider_api_called=false`.

Selection constraints:

- `data-collecting` may generate more than five candidates for review.
- `stock-monitor-service` subscribes to at most five active candidates because of current market-data subscription limits.
- `stock-monitor-service` only enables monitoring for complete long/short
  rows with `risk_reward_ratio >= 1.5` and no `avoid_reason`; non-qualifying
  rows remain stored for audit/review but are not subscribed.
- Deterministic quote/context fallback rows must calibrate `take_profit_zone.first`
  against the generated entry/stop levels so the first target is at least 1.5R.
  This calibration does not apply to structured LLM rows; low-R structured rows
  stay reviewable but non-monitorable.
- `order-dispatcher-service` may trade at most three symbols concurrently.
- Live broker submission remains disabled until paper/sandbox, reconciliation, and kill-switch checks pass.

## Monitoring Rules

`stock-monitor-service` owns market-data monitoring only:

- Reads `t_trade_signals`.
- Projects selected rows into `t_trade_watchlist`.
- Subscribes to the top five ranked symbols.
- Ranks monitorable rows by `candidate_score` first, falling back to older
  fixed-pool priority only when score is missing.
- Writes `t_watchlist_trigger_events`.
- Does not create order intents.
- Writes a local paper-trading observation ledger for virtual fills from
  Fugle ticks; this is not a broker position state machine.
- Does not call broker APIs.

Recommended ranking inputs for the top-five monitor set:

- signal freshness
- evidence quality
- liquidity
- volatility suitable for intraday movement
- complete entry/stop/target levels
- market theme alignment
- no symbol-level block or cooldown
- minimum R multiple (`risk_reward_ratio >= 1.5`)

## Trading Caps

The future order layer must enforce:

- `max_monitor_symbols = 5`
- `max_concurrent_traded_symbols = 3`
- `ORDER_DISPATCHER_TRADING_ENABLED=0` by default
- sandbox or paper mode before production
- global kill switch
- per-symbol cooldown after stop
- daily loss limit
- daily order count limit

The cap is on concurrently traded symbols, not watchlist rows. Monitoring five names while trading zero to three names is the intended steady state.

## Required Trading State Machine

Current implementation gap: this state machine does not exist yet.

`order-dispatcher-service` should own the trading state machine and persist it through order, fill, and position tables.

Minimal signal-to-position lifecycle:

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

Terminal or exception states:

```text
rejected
expired
cancelled
order_rejected
entry_missed
stop_hit_before_fill
force_closed
error_needs_review
```

PnL fields required on position/order reporting:

- quantity
- average entry price
- average exit price
- realized PnL
- unrealized PnL
- fees and tax
- gross PnL
- net PnL
- position state
- source `signal_id`
- source `analysis_id`
- entry trigger event id
- exit trigger event id

## Current Implementation Gap

As of 2026-06-02:

- `data-collecting` still contains fixed-pool code paths such as `FIXED_MARKET_ANALYSIS_WATCH_POOL`.
- `t_trade_signals` has deterministic `risk_reward_ratio`, `candidate_score`,
  and `avoid_reason` fields for downstream filtering.
- `stock-monitor-service` can monitor five qualified symbols, write trigger
  events, and record virtual paper fills, but it still has no broker
  order/position/PnL state.
- `order-dispatcher-service` is still a skeleton and has no trigger consumer, broker wrapper, audit schema, order lifecycle, position lifecycle, or PnL reporting.

Therefore the next implementation work should be:

1. Replace fixed-pool signal generation with Codex daily dynamic candidate generation.
2. Backtest and tune `candidate_score` inputs against paper-trading outcomes.
3. Implement `order-dispatcher-service` sandbox state machine before any live order path.
