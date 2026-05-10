# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Change weekly summary into `週總經 + 下週台股配置 + 下週觀察清單`.
- Requested by: User
- Start date: 2026-05-09
- Scope: Weekly prompt/output behavior, telemetry, docs, tests.

## Plan
- [x] Inspect current weekly output path and latest stored weekly row.
- [x] Patch weekly prompt to fixed three-section structure with deeper reasoning.
- [x] Store weekly token usage telemetry.
- [x] Update tests and documentation.
- [x] Run focused verification.

## Progress Notes
- 2026-05-09 - Latest weekly row id 32 uses `gpt-5`, length 1105, `structured_json=NULL`, no `t_trade_signals`, and no visible recommendation/observation section.
- 2026-05-09 - Root cause: weekly summary is single-call prose generation with 700-1200 char budget and old daily-regime section labels.
- 2026-05-09 - Patched weekly prompt to `週總經` -> `下週台股配置` -> `下週觀察清單`, raised budget to 1200-2200 Chinese characters, and persisted `raw_json.section_contract` plus `raw_json.token_usage`.

## Verification
- [x] Weekly prompt contains exact `週總經`, `下週台股配置`, `下週觀察清單` sections.
- [x] Unit tests pass.
- [x] Docs reflect weekly output contract.

## Review Summary
- Outcome: complete
- Evidence: `python -m unittest tests.test_weekly_summary` passed 19 tests; `git diff --check` passed with line-ending warnings only.
- Open risks: Current stored weekly row was not force-regenerated; next scheduled weekly run will use the new prompt.
