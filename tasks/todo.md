# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's pre-open market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-17
- Scope: Inspect today's `t_market_analyses` `pre_tw_open` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus signal/trust-gate status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and pre-open storage workflow/docs.
- [x] Inspect today's `pre_tw_open` analysis row, raw telemetry, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, eligible signal extraction status, and record the run result.

## Progress Notes
- 2026-06-17: Started pre-open guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `pre_tw_open` storage row only.
- 2026-06-17: DB query confirmed no `t_market_analyses` row exists for `analysis_date=2026-06-17` and `analysis_slot='pre_tw_open'`, so repair is required.
- 2026-06-17: Loaded Workflow 4C-G, trust-gate/editorial-template decisions, and the repo macro/LINE prompt assets before rebuilding visible text.
- 2026-06-17: Same-day `market_context_pre_tw_open` analysis row is absent, so the repair uses local `market_context:*` relay events plus same-window market headlines.
- 2026-06-17: Upserted repaired row `t_market_analyses.id=156` with `model=codex-market-analysis-guard-pre-open`, `prompt_version=codex-guard-pre-open-2026-06-17`, and `external_provider_api_called=false`.
- 2026-06-17: Targeted `run_trade_signal_extraction.ps1 -AnalysisId 156 -FixedPoolFallback` completed with `signals_stored=10`, all from context fallback stock-watch rows.

## Current Verification
- [x] DB check for today's `pre_tw_open` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed.
- Open risks: Same-day `market_context_pre_tw_open` still was not written as its own analysis row, so this brief is evidence-bound and suitable as a guarded macro/sector interpretation, not a high-precision intraday script.
