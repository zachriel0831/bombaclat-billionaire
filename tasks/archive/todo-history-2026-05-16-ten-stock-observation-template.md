# Archived Task - 2026-05-16 Ten-Stock Observation Template

## Task
Expand individual-stock observation template to 10 stocks with explicit buy logic.

## Outcome
Complete.

## Key Changes
- Expanded visible market-analysis watch pool to ten fixed tickers.
- Updated `今日個股觀察` rows to render `上漲邏輯`, `低估/補漲`, and `買入理由`.
- Added conservative valuation wording when no valuation or relative-discount evidence exists.
- Updated stage prompts/schema guidance, `.env`, docs, and tests.

## Verification
- `$env:PYTHONPATH='src'; python -m py_compile src/event_relay/trade_signals.py src/event_relay/service.py src/event_relay/analysis_stages/schemas.py src/event_relay/analysis_stages/stage3_tw_mapping.py src/event_relay/analysis_stages/stage4_synthesis.py src/event_relay/market_analysis.py` passed.
- `$env:PYTHONPATH='src'; python -m unittest tests.test_trade_signals -v` passed, 11 tests.
- `$env:PYTHONPATH='src'; python -m unittest tests.test_market_analysis -v` passed, 41 tests.
- `$env:PYTHONPATH='src'; python -m unittest tests.test_analysis_stages -v` passed, 26 tests.
- `python scripts/validate_readiness.py` passed.
- `git diff --check -- ...` passed with CRLF warnings only.

## Residual Risk
The `低估/補漲` row is deliberately conservative when no valuation or relative-price evidence exists.

