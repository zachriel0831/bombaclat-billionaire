# Decision: Deterministic Scorecard and Context Pack Builder

Date: 2026-05-05

## Context
Daily market analysis was reading a flat recent-event window. During high news volume, stored market context, official data, and deterministic model inputs could be crowded out before the LLM prompt.

## Decision
- Emit a stored-only `market_context:scorecard` event from `event_relay.market_context`.
- Score five deterministic dimensions on -2..+2: `breadth_health`, `ai_capex_quality`, `energy_shock_risk`, `credit_stress`, and `liquidity_impulse`.
- Store evidence, counter-evidence, missing data, and freshness for each dimension in `raw_json.scorecard`.
- Add `event_relay.context_pack_builder` as the prompt-context selection layer.
- Fetch a larger candidate event window, then pack down to `MARKET_ANALYSIS_MAX_EVENTS` with quotas that reserve space for scorecard, market context, and important official data before filling with news/social rows.

## Consequences
- Prompts get more stable structural inputs and less news-only drift.
- `t_market_analyses.raw_json.context_pack` records selected counts, dropped counts, quotas, and guaranteed bucket status.
- RAG retrieval now uses the packed event set, matching the actual prompt context.
- Operators can disable with `MARKET_CONTEXT_SCORECARD_ENABLED=false` or `MARKET_ANALYSIS_CONTEXT_PACK_ENABLED=false` if a rollback is needed.
