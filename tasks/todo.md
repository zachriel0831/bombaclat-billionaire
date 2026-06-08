# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Schedule Free Palestine English issue-news crawler.
- Requested by: user
- Start date: 2026-06-08
- Scope: Promote the existing `event_relay.palestine_news` long-term crawler into a recurring Windows Scheduled Task that refreshes `t_palestine_news_items` for `/timeline` without writing normal rows to `t_relay_events`.

## Plan
- [x] Load repo boundaries, source contract, NEWS-4 context, and scheduler workflow.
- [x] Add `NewsCollector-PalestineNews` registration support.
- [x] Update NEWS/spec/docs/runbook for the scheduled crawler.
- [x] Register the local scheduled task.
- [x] Verify focused tests, dry-run output, live write, and DB state.

## Progress Notes
- 2026-06-08: Existing crawler already writes accepted English Palestine/Gaza/West Bank issue rows to `t_palestine_news_items` and keeps legacy `t_relay_events` as backfill-only input.
- 2026-06-08: Chosen schedule: every 3 hours, starting at 06:10 Taiwan/local time, with idempotent upsert by `url_hash`.
- 2026-06-08: Added `NewsCollector-PalestineNews` registration support to `scripts/register_market_analysis_tasks.ps1`; repetition uses a Once trigger because Windows ScheduledTasks only supports `-RepetitionInterval` on that trigger type.
- 2026-06-08: Focused unit tests passed: `tests.test_palestine_news` ran 4 tests.
- 2026-06-08: Dry-run RSS fetch returned fetched=20, accepted=11, skipped=9, errors=0.
- 2026-06-08: Live RSS write returned fetched=80, accepted=44, skipped=36, errors=0, inserted=28, duplicate=16.
- 2026-06-08: DB verification found 70 `topic=free_palestine AND language=en` rows, latest `last_seen_at=2026-06-08 11:49:28`.
- 2026-06-08: Registered Windows Scheduled Task `NewsCollector-PalestineNews`; next run is `2026-06-09 06:10`, repetition interval is `PT3H`.

## Current Verification
- [x] Python unit tests for Palestine news filtering/storage shape.
- [x] Dry-run RSS fetch.
- [x] Live collector write and DB count check.
- [x] Scheduled task registration check.

## Current Review Summary
- Outcome: Implemented and smoke-tested.
- Open risks: RSS / Google News markup or rate limits can change; crawler records explicit fetch errors and preserves existing rows through idempotent upsert.
