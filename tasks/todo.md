# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair the calendar-guarded 2026-06-21 `us_close` market-analysis row if needed.
- Requested by: automation
- Start date: 2026-06-21
- Scope: Inspect today's latest `t_market_analyses` `us_close` row plus raw telemetry, verify the Traditional Chinese readability and seven-section daily editorial contract, repair or create the row from local relay and market-context evidence only when needed, preserve Java delivery ownership, and verify final DB/trust-gate/signal state without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions plus Workflow 4C storage/guard and daily template decisions.
- [x] Inspect today's `us_close` row, `raw_json`, and visible text quality/template compliance.
- [x] If needed, gather supporting `t_relay_events` and market-context evidence, then repair/create the row through `MySqlEventStore.upsert_market_analysis()` or a targeted same-row update.
- [x] Verify final DB state, trust-gate/signal eligibility, and post-repair readability/style checks.

## Progress Notes
- 2026-06-21: Workspace already had many unrelated dirty files; this run stays scoped to `tasks/todo.md`, automation memory, and the target `us_close` analysis row.
- 2026-06-21: The global CTO standards file still renders as mojibake in this shell, but repo-local AGENTS and Workflow 4C decisions provide the actionable guard/storage rules and no conflicting instruction was found.
- 2026-06-21: `t_market_analyses` has no `analysis_date=2026-06-21` / `analysis_slot=us_close` row, but local calendar state at `2026-06-21 05:00 +08:00` allows no daily analysis slots because it is Sunday local and the relevant U.S. session date `2026-06-20` is also a weekend.
- 2026-06-21: The expected Sunday row exists as `weekly_tw_preopen id=170`, which confirms the scheduler followed the weekly-summary-only policy rather than silently dropping an eligible `us_close` job.
- 2026-06-21: The latest stored `us_close` row remains `id=164` for `analysis_date=2026-06-19`; it is readable Traditional Chinese text with the required daily sections visible, `claim_verifier.ok=true`, `push_enabled=true`, `pushed=false`, and `external_provider_api_called=false`.
- 2026-06-21: No DB write or signal extraction was performed because creating a `2026-06-21 us_close` row would violate the repo's market-calendar slot policy.

## Current Verification
- [x] Repo rules and guard workflow loaded.
- [x] Target `us_close` row inspected.
- [x] Evidence set inspected.
- [x] Post-write or healthy-row verification completed.

## Current Review Summary
- Outcome: Completed with no write; the missing `2026-06-21 us_close` row is calendar-correct.
- Open risks: The automation trigger appears misaligned with Sunday weekly-summary policy, so the same no-op could recur unless the scheduler skips this guard on Sundays.
