# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair the calendar-guarded 2026-06-20 market-analysis brief if needed.
- Requested by: automation
- Start date: 2026-06-20
- Scope: Inspect the 2026-06-20 `pre_tw_open` guard target, respect market-calendar slot conversion, repair the allowed `macro_daily` row from local evidence only if missing or unhealthy, rebuild internal fixed-pool signals when eligible, and verify final DB/trust/style state without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, workflow 4C/4C-G guard rules, editorial template, and lessons.
- [x] Check 2026-06-20 calendar routing and inspect today's `pre_tw_open` / `macro_daily` DB rows.
- [x] Build and store a local-evidence `macro_daily` repair row when the allowed slot is missing.
- [x] Run targeted trade-signal extraction and verify final DB state, visible contract, and residual risk.

## Progress Notes
- 2026-06-20: Workspace already had many unrelated dirty files; this run stays scoped to `tasks/todo.md` plus the missing 2026-06-20 analysis storage row.
- 2026-06-20: `resolve_market_calendar_state()` shows local date `2026-06-20` is a Saturday, the relevant U.S. close session date is `2026-06-19` (NYSE Juneteenth), and the only allowed slot is `macro_daily`.
- 2026-06-20: There is no `t_market_analyses` row for `analysis_date=2026-06-20` in either `pre_tw_open` or `macro_daily`, so the guard must repair the calendar-guarded `macro_daily` row rather than invent a forbidden `pre_tw_open` row.
- 2026-06-20: Local evidence is available from today's `market_context:*` rows, the latest healthy `us_close` digest (`id=164`, `analysis_date=2026-06-19`), and same-window relay news about Fed hawkishness, oil-price rebound, and AI/semiconductor supply-chain themes.
- 2026-06-20: Wrote repaired `macro_daily` row `id=168` through `MySqlEventStore.upsert_market_analysis()` with `model=codex-guard-local-repair`, `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, `external_provider_api_called=false`, and passing style/garbled-text checks.
- 2026-06-20: `scripts/run_trade_signal_extraction.ps1 -AnalysisId 168 -FixedPoolFallback` completed without error but stored `0` monitor rows, so `t_trade_signals` remains empty for this holiday `macro_daily` brief.

## Current Verification
- [x] Calendar-state and allowed-slot check.
- [x] Missing-row check for `2026-06-20`.
- [x] Post-repair DB verification.
- [x] Trade-signal extraction verification.

## Current Review Summary
- Outcome: Completed with repaired `macro_daily` row `id=168`.
- Open risks: `t_trade_signals` stayed at `0`, so downstream fixed-pool monitoring has no fresh holiday row; energy commentary also still carries the known EIA crude-inventory gap.
