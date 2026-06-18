# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's pre-open market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-19
- Scope: Inspect today's `t_market_analyses` `pre_tw_open` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and `pre_tw_open` storage workflow/docs.
- [x] Inspect today's `pre_tw_open` analysis row, raw telemetry, market-calendar state, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-19: Started pre-open guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `pre_tw_open` storage row only.
- 2026-06-19: Loaded guard workflow, daily editorial template decision, and trust-gate rules. `pre_tw_open` delivery eligibility must continue to follow the existing calendar/trust-gate policy; `pushed` stays Java-owned.
- 2026-06-19: DB inspection confirmed there is no `analysis_date=2026-06-19 AND analysis_slot='pre_tw_open'` row, and there is also no earlier fallback `pre_tw_open` row to preserve.
- 2026-06-19: Calendar verification showed `2026-06-19` is a TWSE holiday (Dragon Boat Festival) while the relevant U.S. close session date `2026-06-18` was open, so the allowed slots are `us_close` only. A missing `pre_tw_open` row is therefore expected and should not be repaired.
- 2026-06-19: Verified same-day upstream context is healthy: repaired `us_close` row `164` exists with `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, `style_quality.ok=true`, and `external_provider_api_called=false`.
- 2026-06-19: No `pre_tw_open` row was created, no targeted trade-signal extraction was run for this slot, and Java delivery ownership/calendar policy remained unchanged.

## Current Verification
- [x] DB check for today's `pre_tw_open` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed with holiday no-op.
- Open risks: The automation prompt assumes a `pre_tw_open` row should exist, but on 2026-06-19 the calendar/router correctly suppresses that slot. If future guards should skip earlier, the automation copy should be updated to mention this holiday case explicitly.
