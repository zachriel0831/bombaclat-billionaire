# Archived Task: Fix market-analysis provider switch from OpenAI to Anthropic

## Scope
- model router ordering
- runtime LLM failover
- focused tests and readiness validation

## Outcome
- complete

## Evidence
- `python -m py_compile src/event_relay/llm_quota_router.py src/event_relay/market_analysis.py`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_llm_quota_router tests.test_market_analysis -v`
- `python scripts/validate_readiness.py`
- sanitized config check selected OpenAI primary with Anthropic ordered fallback

## Notes
- `NewsCollector-MarketAnalysis-UsClose` failed on OpenAI `429 insufficient_quota`.
- Runtime failover now reruns retryable OpenAI provider errors with Anthropic when configured.
- Weekly summary uses a separate provider path and was not changed.
