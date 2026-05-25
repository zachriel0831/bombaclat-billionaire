# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Restore internal stock-monitor signals and fix entry-first strategy outcome scoring.
- Requested by: user
- Start date: 2026-05-25
- Scope: `data-collecting` must keep producing/backfilling internal `t_trade_signals` for fixed-pool daily analysis even when visible stock sections are hidden. Strategy outcome scoring must count a win/loss only from the first target/stop after entry.

## Plan
- [x] Confirm failure mode: 2026-05-25 `pre_tw_open` analysis exists but has no `t_trade_signals`; stock-monitor has no active watchlist.
- [x] Add deterministic signal repair/backfill path for analysis rows with empty structured stock watch.
- [x] Add entry-first lifecycle scoring for strategy/RAG outcome metadata.
- [x] Update tests and docs/runbooks.
- [x] Run targeted verification and, if safe, repair the 2026-05-25 row.

## Progress Notes
- 2026-05-25: Confirmed stock-monitor is healthy but has `activeWatchlistRows=0`; upstream `data-collecting` analysis `id=78` has no same-day `t_trade_signals`.
- 2026-05-25: Added targeted `run_trade_signal_extraction.ps1 -AnalysisId <id> -FixedPoolFallback` repair path; it honors stored trust-gate signal blocks.
- 2026-05-25: Updated RAG/outcome scoring so raw `target_hit` / `stop_hit` alone are neutral unless lifecycle metadata proves entry happened first.
- 2026-05-25: Repaired `t_market_analyses.id=78`; inserted 10 `t_trade_signals` (`id=174..183`), and stock-monitor synced cursor `173 -> 183` with 10 upserts.
- 2026-05-25: Updated stock-monitor fixed-pool priority so the 5-subscription cap selects triggerable core tickers first.

## Verification
- [x] Python compile/unit tests.
- [x] Stock-monitor focused tests, if Java code changes.
- [x] DB repair dry run / execution summary.

## Review Summary
- Outcome: fixed.
- Evidence: Python compile passed; `python -m unittest tests.test_trade_signals tests.test_rag tests.test_market_analysis -v` passed 71 tests; stock-monitor `WatchlistRepositoryTest` passed 9 tests; runtime `/health`, `/sync/status`, and `/quote/status` are ok.
- Open risks: It is after Taiwan market hours, so selected streams show `waiting_for_tick` until the next live trading session.
