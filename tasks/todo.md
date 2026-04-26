# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Extract trade signals from market-analysis structured output
- Requirement: REQ-024
- Requested by: User
- Start date: 2026-04-26
- Scope: add `t_trade_signals`, persist one signal per recommended Taiwan ticker from `t_market_analyses.structured_json`, keep review/risk/order/outcome layers independent.

## Plan
- [x] Inspect current structured analysis schema and storage flow.
- [x] Add signal storage dataclass, DDL, migration-safe indexes, and upsert path.
- [x] Extract stock recommendations from `structured_json.stock_watch` after analysis storage.
- [x] Add tests for parsing, idempotency key, and market-analysis write path.
- [x] Update docs for schema and trading boundary.
- [x] Run focused verification.

## Progress Notes
- 2026-04-26 - Started implementation. Existing dirty files are present; this task will avoid unrelated edits.
- 2026-04-26 - Added `t_trade_signals`, `t_signal_reviews`, and `t_signal_outcomes` DDL. Market analysis now stores analysis first, then extracts Taiwan ticker signals as `pending_review`.
- 2026-04-26 - Extended structured `stock_watch` schema with optional strategy/entry/stop/target/evidence fields.
- 2026-04-26 - Added pure extraction tests and market-analysis integration coverage.
- 2026-04-26 - Added `scripts/run_trade_signal_extraction.ps1` for backfilling existing structured analyses.
- 2026-04-26 - Ran DB initialization; confirmed `t_trade_signals`, `t_signal_reviews`, and `t_signal_outcomes` exist.
- 2026-04-26 - Backfilled recent analyses; wrote 1 signal row for `2330` with `status=pending_review`.
- 2026-04-26 - Integrated this task into `requirements.yml` as completed `REQ-024`; adjusted `REQ-026` to consume existing signals instead of creating them.

## Verification
- [x] Focused tests pass
- [x] Compile passes for touched Python files
- [x] `git diff --check` passes for touched files
- [x] Full unittest discovery passes

## Review Summary
- Outcome: completed
- Evidence:
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m unittest tests.test_analysis_stages tests.test_trade_signals tests.test_market_analysis -v` passed, 43 tests
  - `.venv\Scripts\python.exe -m compileall src\event_relay tests\test_trade_signals.py tests\test_market_analysis.py tests\test_event_relay.py tests\test_quote_snapshots_endpoint.py` passed
  - `git diff --check` passed for touched files
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` passed, 210 tests
  - `scripts/run_trade_signal_extraction.ps1 -EnvFile .env -Days 30 -Limit 50` processed 1 analysis and stored 1 signal
  - DB query confirmed latest `t_trade_signals` row: analysis_id=19, slot=`pre_tw_open`, ticker=`2330`, status=`pending_review`
- Open risks: live long-running services need restart to load the new extraction code for future scheduled analyses.
