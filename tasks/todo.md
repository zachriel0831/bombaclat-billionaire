# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's US close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-19
- Scope: Inspect today's `t_market_analyses` `us_close` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and `us_close` storage workflow/docs.
- [x] Inspect today's `us_close` analysis row, raw telemetry, market-calendar state, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-19: Started US close guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `us_close` storage row only.
- 2026-06-19: Loaded guard workflow, daily editorial template decision, and trust-gate rules. `us_close` delivery eligibility must continue to follow the existing calendar/trust-gate policy; `pushed` stays Java-owned.
- 2026-06-19: `t_market_analyses` had no `analysis_date=2026-06-19 AND analysis_slot='us_close'` row, so this run switched from inspection to local repair.
- 2026-06-19: First local repair/upsert created row `164`, but post-write verification showed mojibake because the shell-piped Python path was not UTF-8 safe. The row must be rewritten in place from a UTF-8 file-backed summary before this run can be marked healthy.
- 2026-06-19: Rewrote row `164` in place from `runtime/codex_guard_us_close_2026-06-19_summary.txt`, then re-verified readable Traditional Chinese text, exact seven-section visible template compliance, `claim_verifier.ok=true`, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- 2026-06-19: Because `2026-06-19` is a TW holiday and the relevant U.S. close session (`2026-06-18`) was open, the repaired `us_close` row remained delivery/signal eligible. Targeted `run_trade_signal_extraction.ps1 -AnalysisId 164 -FixedPoolFallback` stored 10 signals, all from prior-signal references.

## Current Verification
- [x] DB check for today's `us_close` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed with local repair.
- Open risks: Same-window `market_context:us_close` and broader U.S. close cross-section inputs were still unavailable, so the repaired digest leans on DJIA / S&P snapshots, BLS PPI points, and overnight relay headlines rather than a full Nasdaq / SOX / rates / FX / VIX closing bundle.
