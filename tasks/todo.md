# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's `us_close` market-analysis row if needed.
- Requested by: automation
- Start date: 2026-06-16
- Scope: Inspect today's latest `t_market_analyses` `us_close` row, verify readability/template/trust-gate state, repair only if missing or visibly broken using local evidence, preserve Java delivery ownership, and verify final DB state including trade signals when applicable.

## Plan
- [x] Read repo instructions, prior automation memory, and Workflow 4C / guard rules.
- [x] Inspect today's `us_close` row, raw telemetry, and local evidence sources.
- [x] Repair the row only if missing or non-compliant; preserve row ownership semantics and rebuild signals only when allowed.
- [x] Verify final DB state, readability/template checks, and capture the run summary.

## Progress Notes
- 2026-06-16: Loaded repo instructions, prior guard memory, and the scheduled market-analysis storage / Codex guard workflow for `us_close`.
- 2026-06-16: No same-day `t_market_analyses` `us_close` row existed for `analysis_date=2026-06-16`.
- 2026-06-16: Same-day evidence was available from local `t_relay_events` and `t_market_index_snapshots` even though no fresh `market_context:us_close` bundle was stored.
- 2026-06-16: Repaired the missing row as `t_market_analyses.id=150` using a UTF-8 local helper path, local relay headlines, and close snapshot rows only; no paid external provider API was called.
- 2026-06-16: Deterministic verification passed with `claim_verifier.ok=true`, no garbled-text markers, valid visible template order, and exactly three bullets under `三個檢查點`.
- 2026-06-16: Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 150 -FixedPoolFallback`; stored 10 `t_trade_signals` rows from prior-signal fallback references.

## Current Verification
- [x] Read-only DB query for today's `us_close`, latest market-context rows, and same-row signal count.
- [x] Local calendar/state check confirmed `us_close` ownership on `2026-06-16`.
- [x] Readability/template check passed: no garbled chars, heading order valid, forbidden sections absent, and exactly three section-2 bullets.

## Current Review Summary
- Outcome: Repaired missing `2026-06-16 us_close` row as `id=150`; final DB state is healthy, `push_enabled=0`, `pushed=0`, and internal signals were rebuilt.
- Open risks: The row uses local relay headlines plus DJIA/S&P close snapshots without a same-window `market_context:us_close` bundle or fuller U.S. cross-asset close pack, so it is suitable as a readable digest but still lighter than the full staged provider path.
