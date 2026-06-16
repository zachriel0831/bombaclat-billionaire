# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's US close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-17
- Scope: Inspect today's `t_market_analyses` `us_close` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus signal/trust-gate status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and US close storage workflow/docs.
- [x] Inspect today's `us_close` analysis row, raw telemetry, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, eligible signal extraction status, and record the run result.

## Progress Notes
- 2026-06-17: Started US close guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `us_close` storage row only.
- 2026-06-17: DB query confirmed no `t_market_analyses` row exists for `analysis_date=2026-06-17` and `analysis_slot='us_close'`, so repair is required.
- 2026-06-17: Loaded Workflow 4C-G, trust-gate/editorial-template decisions, and the repo macro/LINE prompt assets before rebuilding visible text.
- 2026-06-17: Upserted repaired row `t_market_analyses.id=155` through `MySqlEventStore.upsert_market_analysis` with `model=codex-guard-local-repair`, `prompt_version=codex_guard_us_close_v1`, and `external_provider_api_called=false`.
- 2026-06-17: Targeted `run_trade_signal_extraction.ps1 -AnalysisId 155 -FixedPoolFallback -EventDays 1 -PriorDays 30` completed with `signals_stored=10`, all from prior-signal fallback references.

## Current Verification
- [x] DB check for today's `us_close` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed.
- Open risks: The repaired digest still lacks a same-window `market_context` close bundle plus full U.S. cross-asset close data, so it should be treated as a direction brief rather than a high-precision trading script.
