# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's US close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-20
- Scope: Inspect today's `t_market_analyses` `us_close` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, editorial template, and trust-gate docs.
- [x] Inspect today's `us_close` analysis row, calendar gate, raw telemetry, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-20: Started US close guard run. Workspace already has many unrelated dirty changes; this run stays scoped to today's `us_close` storage row only.
- 2026-06-20: Loaded Workflow 4C-G, the daily editorial template decision, and the claim-verifier trust-gate rules.
- 2026-06-20: Direct DB and calendar checks confirmed `analysis_date=2026-06-20` has no `us_close` row, while `resolve_market_calendar_state()` marks the relevant U.S. session date `2026-06-19` as NYSE Juneteenth. Allowed slots today are `macro_daily` only, so the missing `us_close` row is expected and must not be repaired.
- 2026-06-20: Latest stored `us_close` row remains `id=164` for `analysis_date=2026-06-19`; it is already pushed by Java, has `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `external_provider_api_called=false`, zero garbled-text density, all required editorial sections, and exactly three `三個檢查點` bullets.
- 2026-06-20: Because no `us_close` row is allowed today, this guard made no DB writes, did not rerun signal extraction, and left delivery ownership unchanged.

## Current Verification
- [x] DB check for today's `us_close` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed with calendar-blocked no-op.
- Open risks: The guard depends on the hard-coded 2026 market-holiday tables in [`D:\work_space\stock\data-collecting\src\event_relay\market_calendar.py`](D:\work_space\stock\data-collecting\src\event_relay\market_calendar.py). If that calendar drifts, future no-op decisions could be wrong.
