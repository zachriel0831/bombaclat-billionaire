# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair the calendar-guarded 2026-06-21 weekly market-analysis brief if needed.
- Requested by: automation
- Start date: 2026-06-20
- Scope: Inspect the target Sunday `weekly_tw_preopen` row, gather local weekly evidence from relay events and market context only, repair or create the row with the fixed three-section Traditional Chinese contract when needed, and verify final DB/delivery/garbled-text state without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, weekly guard rules, skills, lessons, and weekly three-section decision files.
- [x] Check the 2026-06-21 `weekly_tw_preopen` DB row and determine whether it is missing or contract-broken.
- [x] Gather the last 7 days of relay events, market context, and useful prior weekly/RAG context for a local weekly brief.
- [x] Write the repaired weekly row through `MySqlEventStore.upsert_market_analysis()` with the required raw_json contract and verify final DB state.

## Progress Notes
- 2026-06-20: Workspace already had many unrelated dirty files; this run stays scoped to `tasks/todo.md`, automation memory, and the target weekly analysis row.
- 2026-06-20: Prior automation memory shows the last healthy weekly guard created `analysis_id=144` for `analysis_date=2026-06-14` with the required `週總經 -> 下週台股配置 -> 下週觀察清單` contract and `external_provider_api_called=false`.
- 2026-06-20: The global CTO standards file is stored mojibake on disk, but the repo AGENTS rules already restate the required workflow; no conflicting actionable rule was found.
- 2026-06-20: `t_market_analyses` had no `analysis_date=2026-06-21` / `analysis_slot=weekly_tw_preopen` row, so the weekly guard had to create the Sunday delivery row rather than repair an existing one.
- 2026-06-20: Local evidence was sufficient from `market_context:scorecard`, `market_context:collector`, `market_context:fred`, `market_context:yahoo_chart`, `market_context:tw_close`, `market_context:twse_flow`, `market_context:taifex_flow`, `market_context:tpex_flow`, and selected relay news about Fed, PCE, AI packaging, and Hormuz risk.
- 2026-06-20: Wrote weekly row `id=170` through `MySqlEventStore.upsert_market_analysis()` with `prompt_version=codex-weekly-three-section-v1`, `scheduled_time_local=05:10`, `push_enabled=1`, `pushed=0`, `raw_json.dimension=weekly`, `delivery_owner=java`, `external_provider_api_called=false`, and matching three-section contract.
- 2026-06-20: UTF-8 local script-path write avoided the known PowerShell inline mojibake problem; post-write DB readback confirmed the visible text kept the required Traditional Chinese headings and no replacement-character markers.

## Current Verification
- [x] Repo rules and weekly guard workflow loaded.
- [x] Target Sunday row inspected.
- [x] Evidence set inspected.
- [x] Post-write DB verification completed.

## Current Review Summary
- Outcome: Completed with new weekly row `id=170`.
- Open risks: Hormuz / Lebanon headlines stayed noisy into Friday, so Monday oil-price reaction can still overturn the current “tail risk” framing; local weekly evidence also lacks Monday open follow-through in foreign cash and margin flows.
