# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's U.S.-close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-18
- Scope: Inspect today's `t_market_analyses` `us_close` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and `us_close` storage workflow/docs.
- [x] Inspect today's `us_close` analysis row, raw telemetry, market-calendar state, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-18: Started us-close guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `us_close` storage row only.
- 2026-06-18: Calendar check confirmed `local_date=2026-06-18`, `us_close_session_date=2026-06-17`, and `allowed_analysis_slots` includes `us_close`, but `t_market_analyses` had no `analysis_date=2026-06-18 AND analysis_slot='us_close'` row.
- 2026-06-18: Local repair evidence used the `us_index_tracker` close snapshot for 2026-06-17, same-morning `market_context:bls_macro` rows, and same-window relay headlines for Fed, U.S.-Iran, semiconductor packaging, passive components, and supply-chain direction.
- 2026-06-18: First upsert attempt produced mojibake because the transient shell script mangled Chinese text before Python received it; replaced the summary artifact with a UTF-8 repo file and re-upserted the same row from that file.
- 2026-06-18: Upserted repaired row `t_market_analyses.id=158` with `model=codex-guard-local-repair`, `prompt_version=codex_guard_us_close_v1`, `external_provider_api_called=false`, `events_used=9`, and `market_rows_used=2`.
- 2026-06-18: Targeted fixed-pool signal extraction ran for analysis `158` with `-FixedPoolFallback`; result stored `10` pending-review prior-reference signals and no quote-fallback additions.

## Current Verification
- [x] DB check for today's `us_close` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed.
- Open risks: The visible text is readable and contract-compliant, but the evidence pack is still narrow for `us_close`: only DJIA/S&P close snapshots plus BLS macro points and selected relay headlines were available, so the brief is a directionally useful digest rather than a full U.S. close cross-asset read.
