# Archived Task: Refactor market-analysis pipeline toward pre-open trade decisions

## Outcome
- Added slot-aware pipeline mode.
- Added `digest` mode for U.S. close upstream context.
- Kept Taiwan pre-open as the main multi-stage trade-decision brief.
- Generated and verified a fresh `2026-05-16 us_close` digest.

## Evidence
- `python -m py_compile src/event_relay/market_analysis.py src/event_relay/analysis_stages/stage4_synthesis.py`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_market_analysis -v`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_llm_quota_router -v`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_analysis_stages -v`
- `python scripts/validate_readiness.py`

## Notes
- OpenAI still returned quota 429; runtime failover to Anthropic succeeded.
- `pre_tw_open` correctly skipped on Saturday because Taiwan market was closed.
