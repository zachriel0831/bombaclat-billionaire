# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's TW close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-18
- Scope: Inspect today's `t_market_analyses` `tw_close` row and telemetry, repair a missing or unreadable/template-broken row from local evidence only when needed, verify DB state plus trust-gate/style status, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and `tw_close` storage workflow/docs.
- [x] Inspect today's `tw_close` analysis row, raw telemetry, market-calendar state, and available local evidence.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, signal-extraction eligibility, and record the run result.

## Progress Notes
- 2026-06-18: Started TW close guard run. Workspace has many unrelated dirty changes; this run stays scoped to today's `tw_close` storage row only.
- 2026-06-18: Loaded guard workflow, daily editorial template decision, and trust-gate rules. `tw_close` remains stored-only by policy with `push_enabled=0` unless trust-gate blocks it further.
- 2026-06-18: `t_market_analyses` had no `analysis_date=2026-06-18 AND analysis_slot='tw_close'` row even though the local market calendar allowed `tw_close`, so this run switched from inspection to local repair.
- 2026-06-18: Local repair used the same-day `market_context:tw_close` bundle, Taiwan close / sector transmission headlines, and recent U.S. index snapshot rows only; no external provider API was called.
- 2026-06-18: First upsert wrote mojibake because the inline shell-to-Python path was not UTF-8 safe; the same row was immediately re-upserted through `MySqlEventStore.upsert_market_analysis` using a UTF-8 temp script, preserving row id `162`.
- 2026-06-18: Final stored row `162` has readable Chinese text, exact seven-section daily template compliance, `claim_verifier.ok=true`, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- 2026-06-18: Trade-signal extraction was skipped by policy because `tw_close` remains storage-only (`push_enabled=0`) and the guard telemetry records that skip reason.

## Current Verification
- [x] DB check for today's `tw_close` row and nearby local evidence.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed with local repair.
- Open risks: The stored row is healthy and readable, but same-day official close context was still thin on TWSE-only post-close flow rows, so the commentary is stronger on broad rotation and holiday-gap framing than on full TWSE+TPEx+TAIFEX attribution.
