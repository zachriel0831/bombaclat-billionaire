# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's Taiwan-close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-17
- Scope: Inspect today's `t_market_analyses` `tw_close` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and `tw_close` storage workflow/docs.
- [x] Inspect today's `tw_close` analysis row, raw telemetry, market-calendar state, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-17: Started tw-close guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `tw_close` storage row only.
- 2026-06-17: DB query confirmed no `t_market_analyses` row exists for `analysis_date=2026-06-17` and `analysis_slot='tw_close'`, so repair is required unless the market calendar intentionally skipped the slot.
- 2026-06-17: Loaded Workflow 4C-G, trust-gate/editorial-template decisions, and recent healthy `tw_close` guard rows before rebuilding visible text.
- 2026-06-17: Same-day `market_context:tw_close` exists and aggregates five `market_context:twse_flow` rows; no same-day close-window RSS/company rows were present in `t_relay_events`, so the repair must stay evidence-bound to local market-context rows plus today's guarded pre-open analysis context.
- 2026-06-17: Upserted repaired row `t_market_analyses.id=157` with `model=codex-market-analysis-guard-tw-close`, `prompt_version=codex-guard-tw-close-2026-06-17`, and `external_provider_api_called=false`.
- 2026-06-17: Post-write DB verification passed: `claim_verifier.ok=true`, `support_rate=1.0`, `push_enabled=0`, `pushed=0`, `signals_allowed=true`, `t_trade_signals` count remains `0`, garbled-text check passed, and the visible-template contract passed with exactly three `三個檢查點` bullets.
- 2026-06-17: Internal signal extraction was intentionally skipped because `tw_close` is not an eligible fixed-pool signal slot under current repo policy.

## Current Verification
- [x] DB check for today's `tw_close` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed.
- Open risks: Same-day `tw_close` context is still thin and dominated by TWSE flow aggregation plus the morning guarded analysis context, so this repaired row is suitable as a readable storage/audit brief, not as a high-confidence close-session breadth read.
