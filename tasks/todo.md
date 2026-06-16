# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair today's TW close market-analysis storage row if needed.
- Requested by: automation
- Start date: 2026-06-16
- Scope: Inspect today's `t_market_analyses` `tw_close` row and telemetry, verify market-calendar skip vs unexpected failure, repair readable/template-compliant stored text only when needed, verify DB state, and report residual risk without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, guard rules, and TW close storage workflow/docs.
- [x] Inspect today's `tw_close` analysis row, raw telemetry, claim-verifier status, and market-calendar context.
- [x] Repair the stored row only if it is missing or fails quota/schema/verifier/garbled/template checks.
- [x] Verify final DB state, eligible signal extraction status, and record the run result.

## Progress Notes
- 2026-06-16: Started TW close guard run. Workspace has many unrelated dirty changes; this run stays scoped to inspection/repair for today's stored-only `tw_close` analysis row.
- 2026-06-16: Calendar check showed `tw_close` was allowed for 2026-06-16 and today's row was unexpectedly missing; latest existing `tw_close` row was 2026-06-15 `id=149`.
- 2026-06-16: Rebuilt the missing row from local `market_context:tw_close` plus same-day close/news evidence and upserted `t_market_analyses.id=153` with `model=codex-market-analysis-guard-tw-close`.
- 2026-06-16: First write used a shell path that collapsed non-ASCII to `?`; reran the same upsert through explicit UTF-8/base64 transport so the stored `summary_text` is readable and the telemetry checks are accurate.

## Current Verification
- [x] DB check for today's `tw_close` row, telemetry, and market-calendar status.
- [x] Garbled-text and visible-template contract check.
- [x] Post-write DB verification, including `push_enabled`, `pushed`, claim verifier, and external-provider flag.

## Current Review Summary
- Outcome: Completed.
- Open risks: Guard rebuild used local evidence only and intentionally stored no `structured_json`, so internal signal extraction was not eligible on this row.
