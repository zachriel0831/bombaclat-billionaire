# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's pre-open market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-18
- Scope: Inspect today's `t_market_analyses` `pre_tw_open` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and `pre_tw_open` storage workflow/docs.
- [x] Inspect today's `pre_tw_open` analysis row, raw telemetry, market-calendar state, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-18: Started pre-open guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `pre_tw_open` storage row only.
- 2026-06-18: `t_market_analyses` had no `analysis_date=2026-06-18 AND analysis_slot='pre_tw_open'` row, so this run switched from inspection to local repair.
- 2026-06-18: Local repair evidence used fresh `market_context:collector` / `market_context:scorecard` relay facts, same-window U.S. cross-asset snapshot rows, today-dated Taiwan tracked-market rows, the repaired `us_close` digest, and relay headlines for Fed, oil/geopolitics, advanced packaging, Intel process progress, and passive/material pricing.
- 2026-06-18: Upserted repaired row `t_market_analyses.id=160` with `model=codex-guard-local-repair`, `prompt_version=codex_guard_pre_tw_open_v1`, `events_used=20`, `market_rows_used=11`, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- 2026-06-18: First guard-style telemetry pass stored a false negative in `style_quality` because the transient shell script mangled heading literals inside the checker; re-upserted the same row with UTF-8-safe heading checks, leaving the visible summary unchanged.
- 2026-06-18: Targeted fixed-pool signal extraction ran for analysis `160` with `-FixedPoolFallback`; result stored `10` `pending_review` monitor rows with quote-fallback additions.

## Current Verification
- [x] DB check for today's `pre_tw_open` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed with local repair.
- Open risks: The row is healthy and contract-compliant, but there is still no separately stored `market_context_pre_tw_open` analysis row; this repair depended on relay facts plus the same-day `us_close` digest, so it is stronger on direction and sector transmission than on deep cross-asset attribution.
