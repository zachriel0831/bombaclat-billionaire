# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair the 2026-06-21 `pre_tw_open` market-analysis row if needed.
- Requested by: automation
- Start date: 2026-06-21
- Scope: Inspect today's `t_market_analyses` `pre_tw_open` row plus raw telemetry, verify the Traditional Chinese readability and seven-section daily editorial contract, repair or create the row from local relay and market-context evidence only when needed, preserve Java delivery ownership, and verify final DB/trust-gate/signal state without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions plus Workflow 4C storage/guard and daily template decisions.
- [x] Inspect today's `pre_tw_open` row, `raw_json`, and visible text quality/template compliance.
- [x] If needed, gather supporting `t_relay_events` and market-context evidence, then repair/create the row through `MySqlEventStore.upsert_market_analysis()` or a targeted same-row update.
- [x] Verify final DB state, trust-gate/signal eligibility, and post-repair readability/style checks.

## Progress Notes
- 2026-06-21: Workspace already had many unrelated dirty files; this run stays scoped to `tasks/todo.md`, automation memory, and the target `pre_tw_open` analysis row.
- 2026-06-21: The global CTO standards file still renders as mojibake in this shell, but repo-local AGENTS and Workflow 4C decisions provide the actionable guard/storage rules and no conflicting instruction was found.
- 2026-06-21: `t_market_analyses` has no `analysis_date=2026-06-21` / `analysis_slot=pre_tw_open` row. Same-day rows in the daily family are `weekly_tw_preopen id=170`; the latest calendar-guarded daily prose row is `macro_daily id=168` on `2026-06-20`.
- 2026-06-21: Repo calendar code confirms `resolve_market_calendar_state(datetime(2026, 6, 21, 08:00))` returns `is_sunday_local=true`, both TW and the relevant U.S. session as weekend-closed, and `allowed_analysis_slots=[]`, so there is no eligible `pre_tw_open` slot to repair or synthesize today.
- 2026-06-21: `macro_daily id=168` remains healthy for the latest daily brief: readable Traditional Chinese text, required editorial flow visible, `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `structured_json` present, and `external_provider_api_called=false`.
- 2026-06-21: No DB write or signal extraction was performed because creating a `2026-06-21 pre_tw_open` row would violate the repo's Sunday market-calendar policy and overwrite weekly-summary ownership.

## Current Verification
- [x] Repo rules and guard workflow loaded.
- [x] Target `pre_tw_open` row inspected.
- [x] Evidence set inspected.
- [x] Post-write or healthy-row verification completed.

## Current Review Summary
- Outcome: Completed with no write; missing `2026-06-21 pre_tw_open` is calendar-correct.
- Open risks: The automation still fires on a Sunday with no eligible daily slot, so the same no-op will recur unless the schedule skips weekly-summary days.
