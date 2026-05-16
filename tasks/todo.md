# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Fix market-analysis provider switch from OpenAI to Anthropic.
- Requested by: user
- Start date: 2026-05-16
- Scope: model router ordering, runtime LLM failover, tests, and verification.

## Plan
- [x] Record the task before implementation.
- [x] Inspect current market-analysis provider selection and scheduled failure.
- [x] Make router honor the preferred provider before default alternatives.
- [x] Add runtime failover from OpenAI provider errors to Anthropic.
- [x] Update focused tests for startup routing and runtime failover.
- [x] Run focused tests and readiness validation.

## Progress Notes
- 2026-05-16: `NewsCollector-MarketAnalysis-UsClose` ran at 05:00 but returned task result 1.
- 2026-05-16: Manual reproduction showed OpenAI `429 insufficient_quota`; Anthropic manual run succeeded after disabling the router.
- 2026-05-16: Current router can put OpenAI before a preferred Anthropic provider when no explicit `MARKET_ANALYSIS_PROVIDER_ORDER` exists.
- 2026-05-16: Added runtime failover so retryable OpenAI provider errors rerun the same analysis with Anthropic when an Anthropic key is configured.
- 2026-05-16: `.env` now enables the market-analysis router with provider order `openai,anthropic` and runtime failover enabled.

## Verification
- [x] `python -m py_compile src/event_relay/llm_quota_router.py src/event_relay/market_analysis.py`
- [x] `$env:PYTHONPATH='src'; python -m unittest tests.test_llm_quota_router tests.test_market_analysis -v`
- [x] `python scripts/validate_readiness.py`
- [x] Sanitized config check shows provider `openai`, model `gpt-5`, router enabled, provider order `openai,anthropic`.

## Review Summary
- Outcome: complete.
- Evidence: syntax check passed; 46 focused tests passed; readiness validation passed; sanitized config check selected OpenAI primary with Anthropic ordered fallback.
- Open risks: Weekly summary has its own provider path and is not covered by this market-analysis-specific change.
