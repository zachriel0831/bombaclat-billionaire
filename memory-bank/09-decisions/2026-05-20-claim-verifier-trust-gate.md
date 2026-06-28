# Claim Verifier Trust Gate

## Context

Daily market analysis may contain high-impact numbers, tickers, dates, or geopolitical/commodity claims. The deterministic `claim_verifier` already flags unsupported concrete tokens, but failed outputs were still stored with normal delivery eligibility.

## Decision

Add `market-analysis-trust-gate-v1` after `claim_verifier`.

When `claim_verifier.ok=false`:

- Keep the `t_market_analyses` row stored for audit/debug.
- Force final `push_enabled=false`.
- Store `raw_json.delivery_eligible_before_trust_gate` for the base calendar/slot decision.
- Store `raw_json.trust_gate` with reason, support rate, unsupported counts/sample, delivery decision, and signal decision.
- Skip trade-signal extraction and visible fixed-pool watch-section append for that analysis.

`MARKET_ANALYSIS_CLAIM_GATE_ENABLED=false` is available only as an emergency debugging override.

## Consequences

- Java delivery must continue to respect `push_enabled=false`.
- Failed analyses remain inspectable in storage but should not be user-facing.
- Stock-monitor or review consumers should not receive fresh `t_trade_signals` from verifier-failed analyses.
