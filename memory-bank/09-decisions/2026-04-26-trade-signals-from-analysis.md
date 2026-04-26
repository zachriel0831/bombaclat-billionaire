# Decision: Extract Trade Signals From Market Analyses

Date: 2026-04-26

## Context
- Market analyses can recommend Taiwan stocks, but free text is hard to review, monitor, backtest, or connect to a future order workflow.
- LLM output must not directly create broker orders.

## Decision
- Add `t_trade_signals` as the structured recommendation table.
- Derive signals only from `t_market_analyses.structured_json` after the analysis row is stored.
- Add separate `t_signal_reviews` and `t_signal_outcomes` tables for later risk gate / human review and performance feedback.
- Store every signal with `analysis_id`, slot/date, ticker, strategy, direction, optional entry/stop/target fields, source event IDs, and a stable `idempotency_key`.
- Default signal status is `pending_review`.

## Consequences
- `t_market_analyses` remains the source of the model's full reasoning.
- `t_trade_signals` becomes the machine-readable stock list.
- Risk gate, order intent, broker execution, and outcome scoring remain independent future layers.
