# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Guard and repair the 2026-07-23 `tw_close` market-analysis row from local evidence only.
- Requested by: automation
- Start date: 2026-07-23
- Scope: Create the missing storage-only `tw_close` row, preserve Java delivery policy, and use no paid external LLM APIs.

## Plan
- [x] Read repo instructions, Workflow 4C guard rules, automation memory, and active lessons.
- [x] Inspect calendar eligibility and today's target row.
- [x] Gather local relay and market-context evidence with index-friendly queries.
- [x] Repair through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run targeted signal extraction only if eligible; verify DB/style/provider state.

## 2026-07-23 TW Close Guard Run
- [x] Taiwan was a regular trading day and `tw_close` was eligible; the target row was missing while fresh close context existed.
- [x] Created `t_market_analyses.id=278` through `MySqlEventStore.upsert_market_analysis()` using five local relay events only.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, structured data present, six requested headings in order, exactly three evidence bullets, garbled/style/template checks passed, and `external_provider_api_called=false`.
- [x] Signal extraction skipped because `tw_close` is storage-only, `trust_gate.signals_allowed=false`, and `structured_json.stock_watch` is empty.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-23 Pre-Open Guard Run
- [x] Taiwan and the relevant 2026-07-22 U.S. session are regular trading days; `pre_tw_open` is eligible and the target row is missing.
- [x] Re-plan: the broad event query hit known MySQL `Out of sort memory`; use the indexed recent-id path and filter the bounded result locally.
- [x] Re-plan: the first upsert was rejected because `scheduled_time_local` accepts the existing short time format; preserve the schema and retry with `07:30`.
- [x] Created `t_market_analyses.id=277` through `MySqlEventStore.upsert_market_analysis()` using three local relay events only.
- [x] Ran targeted extraction with `-AnalysisId 277 -FixedPoolFallback`; stored 10 prior-signal monitor references and no quote fallback rows.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, structured data present, six requested headings in order, exactly three evidence bullets, garbled/style/template checks passed, 10 trade signals, and `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-23 US Close Guard Run
- [x] Taiwan and the relevant 2026-07-22 U.S. session were regular trading days; `us_close` was eligible but the target row was missing.
- [x] Created `t_market_analyses.id=276` through `MySqlEventStore.upsert_market_analysis()` using three local relay events and two local market-index rows only.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, structured data present, six headings in order, exactly three evidence bullets, garbled/style/template checks passed, and `external_provider_api_called=false`.
- [x] Ran targeted signal extraction because the trust gate allowed it; no dynamic candidate was present, so zero signals were stored and no fixed-pool padding was added.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-22 Pre-Open Guard Run
- [x] Taiwan and the relevant 2026-07-21 U.S. session were regular trading days; `pre_tw_open` is eligible and the target row is missing.
- [x] Re-plan: the first read-only evidence query used obsolete `t_relay_events.content`; inspected the live schema and used canonical payload columns before writing.
- [x] Re-plan: MySQL rejected a Traditional-Chinese `REGEXP`; switched to source filters and parameterized `LIKE` predicates.
- [x] Re-plan: the first pre-write draft passed claim/trust checks but broad text checks false-positive blocked storage; narrowed them to repeated ASCII question blocks and exact forbidden reader terms.
- [x] Re-plan: PowerShell stdin converted Traditional Chinese literals before Python validation; ran repair and verification from UTF-8 workspace scripts.
- [x] Repaired missing row as `t_market_analyses.id=274` through `MySqlEventStore.upsert_market_analysis()` using six local evidence events only.
- [x] Ran targeted extraction with `-AnalysisId 274 -FixedPoolFallback`; stored 10 prior-signal monitor references and no quote fallback rows.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, structured data present, exactly three evidence bullets, garbled/style/template checks passed, 10 trade signals, and `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-22 US Close Guard Run
- [x] Taiwan and the relevant 2026-07-21 U.S. session were regular trading days; `us_close` was eligible but remained storage/upstream-only, and the target row was missing.
- [x] Repaired `t_market_analyses.id=273` through `MySqlEventStore.upsert_market_analysis()` using six local evidence events only.
- [x] Final verification: required six-section order, exactly three evidence bullets, readable Traditional Chinese, no forbidden internal/trading terms, `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, structured data present, and `external_provider_api_called=false`.
- [x] Ran targeted signal extraction because the trust gate allowed it; stored 10 `pending_review` prior-signal references under the existing repo policy.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-21 TW Close Guard Run
- [x] Taiwan was a regular trading day and `tw_close` was eligible; the target row was missing while fresh close context existed.
- [x] Repaired `t_market_analyses.id=272` through `MySqlEventStore.upsert_market_analysis()` using seven local evidence events only.
- [x] Final verification: required six-section order, exactly three evidence bullets, readable Traditional Chinese, no forbidden internal/trading terms, `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, structured data present, and `external_provider_api_called=false`.
- [x] Signal extraction skipped because `tw_close` is storage-only, `trust_gate.signals_allowed=false`, and `structured_json.stock_watch` is empty; existing signal count is zero.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-20 Dynamic Daily Candidate Migration
- [x] Removed the historical fixed ten-stock pool from daily strategy candidate generation.
- [x] Stage3 / Stage4 prompts now request evidence-backed dynamic Taiwan four-digit tickers.
- [x] Trade-signal extraction no longer pads empty or thin candidate lists with neutral fixed-pool rows.
- [x] Legacy `fixed_pool` function and CLI names remain compatibility aliases only.
- [x] Updated specs, memory-bank docs, and lessons to prevent reintroducing fixed-pool padding.
- [x] Verified with compileall, targeted unit tests, stale-text scan, and readiness validation.

## 2026-07-20 Pre-Open Guard Run
- [x] Found no `analysis_date=2026-07-20` / `analysis_slot=pre_tw_open` row.
- [x] Calendar allows `pre_tw_open`: Taiwan is a regular trading day and the relevant U.S. session is weekend-closed.
- [x] Repaired the missing row as `t_market_analyses.id=266` through `MySqlEventStore.upsert_market_analysis()` using local evidence only.
- [x] Ran targeted fixed-pool extraction; stored 10 internal `pending_review` monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, six headings in order, exactly three evidence bullets, garbled/internal-label/trade-language checks passed, and `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, paid external LLM API, or LINE delivery call occurred.

## 2026-07-20 US-Close Guard Run
- [x] Found no `analysis_date=2026-07-20` / `analysis_slot=us_close` row.
- [x] Used the 2026-07-17 U.S. close plus local rates, liquidity, energy, geopolitical, and Taiwan-transmission evidence only.
- [x] Repaired the missing row as `t_market_analyses.id=265` through `MySqlEventStore.upsert_market_analysis()`.
- [x] Ran targeted signal extraction; stored 10 internal `pending_review` monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, `structured_json` present, six headings in order, exactly three evidence bullets, garbled/internal-label/trade-language checks passed, and `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, paid external LLM API, or LINE delivery call occurred.

## 2026-07-19 TW-Close Guard Run
- [x] Re-planned after the first read-only check exposed missing Windows `tzdata`; use the repo-compatible fixed UTC+8 timezone.
- [x] Re-planned after the second read-only check used nonexistent flattened status columns; verify claim/trust status from `raw_json`.
- [x] Confirmed Taiwan and U.S. sessions are weekend-closed and `allowed_analysis_slots=[]`.
- [x] Confirmed today's `tw_close` row is absent, which is intentional under calendar policy.
- [x] Confirmed one same-day `market_context:tw_close` event exists; no analysis write or signal extraction is eligible.
- [x] No OpenAI, Anthropic, paid external LLM API, or LINE contact occurred.

## 2026-07-19 US-Close Guard Run
- [x] Found no `analysis_date=2026-07-19` / `analysis_slot=us_close` row.
- [x] Confirmed local 2026-07-17 U.S. close snapshots and recent macro/geopolitical/AI evidence are available.
- [x] Re-planned after the first dry verification exposed non-JSON database datetime values; normalize verifier inputs before writing.
- [x] Second dry verification stopped on a combined style assertion before DB write; split assertions to identify the exact failed condition.
- [x] Repaired the missing row as `t_market_analyses.id=263` using local evidence only.
- [x] Ran targeted signal extraction; stored 10 `pending_review` rows.
- [x] Final verification passed: claim/trust/style/garbled checks, delivery flags, structured data, and external-provider telemetry.

## 2026-07-19 Weekly Guard Run
- [x] Found no `analysis_date=2026-07-19` / `analysis_slot=weekly_tw_preopen` row.
- [x] Repaired the missing weekly row as `t_market_analyses.id=262` through `MySqlEventStore.upsert_market_analysis()` using local relay, market-context, and indexed-history availability only.
- [x] Final verification: section order `週總經` -> `下週台股配置` -> `下週觀察清單`, exactly 3 headings, garbled/mojibake and forbidden trade-language checks passed, `push_enabled=1`, `pushed=0`, `raw_json.dimension=weekly`, `raw_json.delivery_owner=java`, `raw_json.external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-18 Pre-Open Guard Run
- [x] Today's `pre_tw_open` row is absent.
- [x] Calendar guard allows only `us_close`: Taiwan is weekend-closed and the relevant 2026-07-17 U.S. session was open.
- [x] Left the absent `pre_tw_open` row unchanged; no LINE-eligible row or trade signals were created.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-18 US-Close Guard Run
- [x] Found missing `analysis_date=2026-07-18` / `analysis_slot=us_close` row.
- [x] Calendar allows `us_close`: Taiwan is weekend-closed and the relevant 2026-07-17 U.S. session was open.
- [x] Confirmed fresh local U.S. close snapshots and relay evidence are available.
- [x] Repaired missing row as `t_market_analyses.id=261` through `MySqlEventStore.upsert_market_analysis()` using local evidence only.
- [x] Ran targeted fixed-pool signal extraction; stored 10 internal `pending_review` monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, author-style heading order and exactly three evidence bullets passed, garbled/internal-label checks passed, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-16 US-Close Guard Run
- [x] Found missing `analysis_date=2026-07-16` / `analysis_slot=us_close` row.
- [x] Calendar allows `us_close`: Taiwan local date 2026-07-16 and U.S. close session date 2026-07-15 are regular trading days.
- [x] Confirmed local evidence gap: no 2026-07-15 U.S. index-close snapshot was present at guard time; repair must not invent closing prices.
- [x] Repaired missing row as `t_market_analyses.id=250` through `MySqlEventStore.upsert_market_analysis()` using local BLS and Taiwan flow evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 250 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, seven headings in order, exactly 3 checkpoint bullets, garbled/LINE excerpt checks passed, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-15 Pre-Open Guard Run
- [x] Found missing `analysis_date=2026-07-15` / `analysis_slot=pre_tw_open` row.
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day and relevant U.S. close session date 2026-07-14 was a regular trading day.
- [x] Repaired missing row as `t_market_analyses.id=248` through `MySqlEventStore.upsert_market_analysis()` using local relay/context evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 248 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-14 Pre-Open Guard Run
- [x] Found missing `analysis_date=2026-07-14` / `analysis_slot=pre_tw_open` row.
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day and relevant U.S. close session date 2026-07-13 was a regular trading day.
- [x] Repaired missing row as `t_market_analyses.id=241` through `MySqlEventStore.upsert_market_analysis()` using local relay/context evidence only.
- [x] Rewrote the same row through a UTF-8 helper path after PowerShell stdin mangled the first Chinese write, then removed the helper.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 241 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-13 Pre-Open Guard Run
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day; relevant U.S. close session date 2026-07-12 was weekend-closed.
- [x] Found missing `analysis_date=2026-07-13` / `analysis_slot=pre_tw_open` row.
- [x] Repaired missing row as `t_market_analyses.id=235` through `MySqlEventStore.upsert_market_analysis()` using local relay/context evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 235 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-12 Pre-Open Guard Run
- [x] Calendar disallows daily `pre_tw_open`: Taiwan local date 2026-07-12 is Sunday and `allowed_analysis_slots=[]`.
- [x] Found no `analysis_date=2026-07-12` / `analysis_slot IN ('pre_tw_open','macro_daily')` row; no repair performed because creating one would violate market-calendar policy.
- [x] Confirmed Sunday owner row exists: `t_market_analyses.id=232`, `analysis_slot=weekly_tw_preopen`, `push_enabled=1`, `pushed=1`, `structured_json` present, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-12 Weekly Guard Run
- [x] Found no `analysis_date=2026-07-12` / `analysis_slot=weekly_tw_preopen` row.
- [x] Repaired missing weekly row as `t_market_analyses.id=232` through `MySqlEventStore.upsert_market_analysis()` using local relay events, market-context rows, market snapshots, recent analysis history, and local RAG availability only.
- [x] Final verification: section order `週總經` -> `下週台股配置` -> `下週觀察清單`, exactly 3 headings, garbled/mojibake check passed, no entry/stop-loss/target-price wording, `push_enabled=1`, `pushed=0`, `raw_json.dimension=weekly`, `raw_json.delivery_owner=java`, `raw_json.external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-11 US-Close Guard Run
- [x] Found no `analysis_date=2026-07-11` / `analysis_slot=us_close` row.
- [x] Found local `us_index_close_2026-07-10` and supporting relay/market snapshot evidence.
- [x] Repaired missing row as `t_market_analyses.id=231` through `MySqlEventStore.upsert_market_analysis()` using local U.S. close, BLS macro, Reuters/NPR, and market snapshot evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 231 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification by Unicode codepoint: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, LINE excerpt check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-10 Pre-Open Guard Run
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day and relevant U.S. close session date 2026-07-09 was a regular trading day.
- [x] Found no `analysis_date=2026-07-10` / `analysis_slot=pre_tw_open` row.
- [x] Repaired missing row as `t_market_analyses.id=228` through `MySqlEventStore.upsert_market_analysis()` using local relay, same-day U.S. close, and market snapshot evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 228 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-09 Pre-Open Guard Run
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day and relevant U.S. close session date 2026-07-08 was a regular trading day.
- [x] Found no `analysis_date=2026-07-09` / `analysis_slot=pre_tw_open` row.
- [x] Repaired missing row as `t_market_analyses.id=223` through `MySqlEventStore.upsert_market_analysis()` using local market-context, U.S. close, and index snapshot evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 223 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## Previous Task
- Task: Guard and repair the 2026-07-09 US-close market-analysis row if needed.
- Requested by: automation
- Start date: 2026-07-09
- Scope: Inspect today's latest `us_close` row, repair missing/unhealthy storage from local relay and market-context evidence only, preserve Java delivery ownership, run fixed-pool monitor extraction after repair only when eligible, and verify DB state without paid external LLM APIs.

## Plan
- [x] Read repo instructions, automation memory, and Workflow 4C guard rules.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Repair/create the row from local evidence only if missing or unhealthy.
- [x] Run targeted internal trade-signal extraction only if a repaired row is eligible.
- [x] Verify final DB state, visible template, garbled text, and provider telemetry.

## 2026-07-09 US-Close Guard Run
- [x] Calendar allows `us_close`: Taiwan local date 2026-07-09 and U.S. close session date 2026-07-08 are both regular trading days.
- [x] Found no `analysis_date=2026-07-09` / `analysis_slot=us_close` row; latest existing `us_close` row was 2026-07-08.
- [x] Repaired missing row as `t_market_analyses.id=222` through `MySqlEventStore.upsert_market_analysis()` using local U.S. index close, BLS macro, and Taiwan flow evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 222 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=0`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, LINE excerpt check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-08 Pre-Open Guard Run
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day and relevant U.S. close session date 2026-07-07 was a regular trading day.
- [x] Found no `analysis_date=2026-07-08` / `analysis_slot=pre_tw_open` row.
- [x] Repaired missing row as `t_market_analyses.id=219` through `MySqlEventStore.upsert_market_analysis()` using local relay and market-context evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 219 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## Previous Task
- Task: Guard and repair the 2026-07-07 pre-open market-analysis row if needed.
- Requested by: automation
- Start date: 2026-07-07
- Scope: Inspect today's `pre_tw_open` row, repair missing/unhealthy storage from local relay and market-context evidence only, preserve Java delivery ownership, run fixed-pool monitor extraction after repair, and verify DB state without paid external LLM APIs.

## Plan
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirm calendar eligibility and inspect today's daily analysis row.
- [x] Repair/create the row from local evidence only if missing or unhealthy.
- [x] Run targeted internal trade-signal extraction after repair.
- [x] Verify final DB state, visible template, garbled text, and provider telemetry.

## 2026-07-07 Pre-Open Guard Run
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day and relevant U.S. close session date 2026-07-06 was a regular trading day.
- [x] Found no `analysis_date=2026-07-07` / `analysis_slot IN ('pre_tw_open','macro_daily')` row.
- [x] Repaired missing row as `t_market_analyses.id=215` through `MySqlEventStore.upsert_market_analysis()` using local relay and market-context evidence only.
- [x] Rewrote the same row through a UTF-8 helper path after PowerShell stdin mangled the first Chinese write, then removed the helper.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 215 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## Previous Task
- Task: Produce the 2026-W27 Free Palestine weekly editorial.
- Requested by: automation
- Start date: 2026-07-05
- Scope: Read local `t_palestine_news_items` rows for 2026-06-28 through 2026-07-05 exclusive Asia/Taipei, draft one Traditional Chinese editorial from sourced facts only, upsert `t_palestine_editorials`, validate the saved row, and avoid paid external LLM APIs.

## Plan
- [x] Read repo instructions and prior automation memory.
- [x] Extract and review matching Palestine issue-news rows.
- [x] Upsert the weekly editorial row.
- [x] Read back and validate the saved editorial.
- [x] Update automation memory and report result.

## 2026-07-05 Free Palestine Weekly Editorial Run
- [x] Source window: 2026-06-28 through 2026-07-05 exclusive, Asia/Taipei.
- [x] Reviewed 102 local `t_palestine_news_items` rows: google_news_en 49, al_jazeera_en 45, bbc_middle_east_en 3, guardian_palestine_en 5.
- [x] Upserted `t_palestine_editorials.editorial_id=palestine-weekly-2026-W27` with `status=published`.
- [x] Validation passed: readable Traditional Chinese, no mojibake/question-mark block, source count matches saved source IDs, no raw JSON dump in body, no fabricated URL citations in body.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## Previous Task
- Task: Guard and repair the 2026-07-06 pre-open market-analysis row if needed.
- Requested by: automation
- Start date: 2026-07-06
- Scope: Inspect today's `pre_tw_open` row, repair missing/unhealthy storage from local relay and market-context evidence only, preserve Java delivery ownership, run fixed-pool monitor extraction after repair, and verify DB state without paid external LLM APIs.

## Plan
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirm calendar eligibility and inspect today's daily analysis row.
- [x] Repair/create the row from local evidence only if missing or unhealthy.
- [x] Run targeted internal trade-signal extraction after repair.
- [x] Verify final DB state, visible template, garbled text, and provider telemetry.

## 2026-07-06 Pre-Open Guard Run
- [x] Calendar allows `pre_tw_open`: Taiwan regular trading day, relevant U.S. close session date 2026-07-05 was weekend-closed.
- [x] Found no `analysis_date=2026-07-06` / `analysis_slot IN ('pre_tw_open','macro_daily')` row.
- [x] Repaired missing row as `t_market_analyses.id=209` through `MySqlEventStore.upsert_market_analysis()` using local relay, market-context, and market-snapshot evidence only.
- [x] Rewrote the same row through a UTF-8 helper path after PowerShell stdin mangled the first Chinese write, then removed the helper.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 209 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=true`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 10, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## Previous Task
- Task: Guard and repair the 2026-07-05 weekly pre-open market-analysis row if needed.
- Requested by: automation
- Start date: 2026-07-04
- Scope: Inspect target Sunday `t_market_analyses` `weekly_tw_preopen` row, verify the three-section Traditional Chinese weekly contract, repair or create the row from local relay, market-context, and history/RAG evidence only when needed, preserve Java delivery ownership, and verify final DB state without calling paid external LLM APIs.

## Plan
- [x] Read repo instructions, automation memory, Workflow 4C/4D weekly storage rules, weekly contract decision, and active lessons.
- [x] Inspect target Sunday `weekly_tw_preopen` row, raw telemetry, garbled text, and section compliance.
- [x] Repair/create the row from local evidence only if missing or unhealthy.
- [x] Verify final DB state, section order, garbled-text checks, delivery flags, evidence counts, and external-provider telemetry.

## 2026-07-05 Weekly Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C/4D weekly storage rules, weekly contract decision, and active lessons.
- [x] Found no `analysis_date=2026-07-05` / `analysis_slot=weekly_tw_preopen` row.
- [x] Repaired missing weekly row as `t_market_analyses.id=208` through `MySqlEventStore.upsert_market_analysis()` using local relay events, market-context rows, recent analysis history, and local RAG availability only.
- [x] Final verification: section order `週總經` -> `下週台股配置` -> `下週觀察清單`, exactly 3 headings, garbled/mojibake check passed, no entry/stop-loss/target-price wording, `push_enabled=1`, `pushed=0`, `raw_json.dimension=weekly`, `raw_json.delivery_owner=java`, `raw_json.external_provider_api_called=false`.
- [x] Evidence counts: `events_used=4159`, `market_rows_used=418`, local RAG available with `t_event_embeddings=26969` and `t_analysis_embeddings=153`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-04 Pre-Open Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirmed calendar allows only `macro_daily` for 2026-07-04 because Taiwan is weekend-closed and the relevant U.S. session is the NYSE Independence Day observed holiday.
- [x] Found no `analysis_date=2026-07-04` / `analysis_slot IN ('pre_tw_open','macro_daily')` row.
- [x] Repaired missing row as `t_market_analyses.id=206` / `analysis_slot=macro_daily` through `MySqlEventStore.upsert_market_analysis()` using local relay, market-context, and market-snapshot evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 206 -FixedPoolFallback`; macro row produced 0 internal monitor rows as expected.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `t_trade_signals` count 0, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-03 Pre-Open Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirmed calendar allows `pre_tw_open` for 2026-07-03.
- [x] Found missing `analysis_date=2026-07-03` / `analysis_slot=pre_tw_open` row.
- [x] Repaired missing row as `t_market_analyses.id=204` through `MySqlEventStore.upsert_market_analysis()` using local relay, market-context, and market-snapshot evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 204 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-07-02 TW Close Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and daily template decisions.
- [x] Confirmed calendar allows `tw_close` for 2026-07-02.
- [x] Found missing `analysis_date=2026-07-02` / `analysis_slot=tw_close` row.
- [x] Repaired missing row as `t_market_analyses.id=201` through `MySqlEventStore.upsert_market_analysis()` using local `market_context:tw_close` evidence only.
- [x] Rewrote the same row through a UTF-8 Python helper path after PowerShell stdin mangled the first Chinese write, then removed the helper.
- [x] Final verification: readable Traditional Chinese text, required seven-section daily editorial flow, exactly three `三個檢查點` bullets, no `台股配置`, no `今日個股觀察`, no entry/stop/target-price language.
- [x] Final DB state: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=false`, `push_enabled=0`, `pushed=0`, `structured_json` present, `external_provider_api_called=false`.
- [x] Internal signal extraction skipped because current `tw_close` repair policy keeps the row storage-only with `trust_gate.signals_allowed=false`; `t_trade_signals` count for analysis id 201 is 0.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-06-28 Four-Hour Digest Progress Notes
- The digest should be generated by Codex automation, not by paid OpenAI API calls.
- Source facts stay in existing stores: finance/public events and celebrity posts in `news_relay.t_relay_events`, society/politics in `news_platform.t_news_articles`, and Free Palestine issue news in long-term `t_palestine_news_items`.
- Redis keys use `news:digest:four-hour:latest` for API reads and a versioned key plus `news:digest:four-hour:current-key` for controlled replacement. Versioned keys use a 15,000 second TTL; `latest` and `current-key` persist until the next successful digest write.
- Created Codex automation `four-hour-cross-section-news-digest` with schedule `FREQ=HOURLY;INTERVAL=4`.
- Added collector-side mojibake filtering and Redis-side validation for replacement characters, repeated question-mark blocks, and UTF-8 BOM input.
- Removed an accidental local test digest from Redis after detecting garbled generated prose; the API now returns `digest_not_ready` until the next valid automation output is written.

## 2026-06-28 Four-Hour Digest Verification
- [x] `python -m unittest tests.test_four_hour_digest_scripts -v` passed: 9 tests.
- [x] `python -m py_compile scripts\collect_four_hour_digest_context.py scripts\store_four_hour_digest_to_redis.py` passed.
- [x] Context extraction wrote `runtime/four-hour-digest/context.json`; Python JSON parse passed with counts `finance=51`, `society=28`, `politics=30`, `celebrity=0`, `free_palestine=45`.
- [x] `store_four_hour_digest_to_redis.py --dry-run` accepted a valid sample digest with TTL 15000.
- [x] `GET http://localhost:8081/health` returned `status=ok`.
- [x] `GET http://localhost:8081/api/digest/four-hour` returned `available=false`, `message=digest_not_ready` after the bad local test digest was removed.

## 2026-06-27 Relay Finance Reporter Progress Notes
- Finance cards read `GET /api/events?region=TW`, which maps to short-retention `t_relay_events`, not the Taiwan society/politics `t_news_articles` tables that already have normalized reporter relations.
- Sampling recent Taiwan finance RSS rows showed most feed payloads do not include `<author>` / `dc:creator`, so reporter names require the same conservative article-detail byline extraction used by `NEWS-2`.
- Chosen MVP path: keep the API shape stable and write enrichment into `t_relay_events.raw_json.authors` plus `raw_json.author_extraction`; do not add a schema migration unless finance reporter pages need long-lived identity relations later.
- Implemented `scripts/backfill_relay_event_authors.py`, updated RSS raw metadata preservation, and added frontend card rendering through `relayEventReporterNames()`.
- Added a relay-specific author sanitizer after dry-run found MoneyUDN site slug `edn`; it is now treated as low confidence instead of a reporter.
- Backfilled latest 50 eligible relay-event rows: `present=37`, `low_confidence=13`, `parse_failed=0`, `updated=50`.

## 2026-06-27 Relay Finance Reporter Verification
- [x] `python -m unittest tests.test_rss_source tests.test_relay_event_author_backfill -v` passed: 10 tests.
- [x] `python -m py_compile scripts/backfill_relay_event_authors.py src/news_collector/sources/rss.py` passed.
- [x] `npm run lint -- src/lib/content-api.ts src/components/news-platform-dashboard.tsx src/components/infinite-news-feed.tsx` passed.
- [x] Dry-run sanity check: 5 eligible rows produced `present=3`, `low_confidence=2`, and no parse failures after slug filtering.
- [x] API smoke: `GET http://localhost:8081/api/events?page=1&pageSize=8&region=TW` returns `rawJson.authors` for recent finance rows.
- [x] Frontend proxy smoke: `GET http://localhost:3000/api/content/events?page=1&pageSize=5&region=TW` returns authors such as `江明晏` and `李靚慧`.
- [x] Frontend page smoke: `GET http://localhost:3000/` rendered HTML contains `記者`, `江明晏`, and `李靚慧`.

## 2026-06-27 Truth Social Progress Notes
- Added `TRUTH_SOCIAL_ENABLED`, `TRUTH_SOCIAL_ACCOUNTS`, `TRUTH_SOCIAL_MAX_RESULTS_PER_ACCOUNT`, and `TRUTH_SOCIAL_USER_AGENT` settings. Local `.env` now enables `https://truthsocial.com/@realDonaldTrump` without adding secrets.
- Added `TruthSocialAccountSource`, wired it into `news_collector.main --source truthsocial`, `build_sources()`, relay polling, direct DB backfill helper, source-health probes, RAG/context source family, and the social-post upsert path.
- Truth Social posts use `source=truthsocial:<handle>` in `t_relay_events` and mirror into the existing `t_x_posts` table with `tweet_id=truthsocial-<status_id>`, `username=<handle>`, and Truth Social metrics in `metrics_json`.
- `news-platform-api` now defaults `GET /api/celebrity-events` to both `x:*` and `truthsocial:*`, and accepts `handle=truthsocial:realdonaldtrump` or a Truth Social profile URL.
- `news-display-frontend` no longer hardcodes the home celebrity fetch to Elon only; source labels render `truthsocial:realdonaldtrump` as `Donald Trump`.
- Ran a one-shot direct DB backfill: fetched 10 Trump Truth Social posts, stored 10 `t_relay_events` rows and 10 mirrored `t_x_posts` rows, with 0 duplicates and 0 failures.

## 2026-06-27 Truth Social Verification
- [x] `python -m unittest tests.test_truth_social tests.test_config tests.test_collector tests.test_relay_bridge tests.test_event_relay tests.test_context_pack_builder -v` passed: 38 tests.
- [x] `python -m news_collector.main fetch --source truthsocial --limit 3 --title-url-only` fetched 3 recent Trump Truth Social items and respected the local limit guard.
- [x] `mvnw.cmd -Dtest=ContentControllerCelebrityEventsTest test` passed with `JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot`.
- [x] `npm run lint -- src/app/page.tsx src/lib/content-api.ts src/components/event-list.tsx src/components/infinite-news-feed.tsx src/components/news-platform-dashboard.tsx` passed.
- [x] Restarted `news-platform-api` with `scripts/start_local_stack.ps1 -RestartApi -Check`.
- [x] Verified `http://localhost:8081/api/celebrity-events?handle=truthsocial:realdonaldtrump&page=1&pageSize=3` returns Trump Truth Social rows.
- [x] Verified `http://localhost:3000/api/content/celebrity-events?page=1&pageSize=3` returns Trump Truth Social rows through the frontend proxy.

## Previous Automation Task
- Task: Guard and repair the 2026-06-27 `pre_tw_open` market-analysis row if needed.
- Requested by: automation
- Start date: 2026-06-27
- Scope: Inspect today's `t_market_analyses` `pre_tw_open` row plus raw telemetry, verify the Traditional Chinese readability and seven-section daily editorial contract, repair or create the row from local relay and market-context evidence only when needed, preserve Java delivery ownership, and verify final DB/trust-gate/signal state without calling paid external LLM APIs.

## 2026-07-01 Pre-Open Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirmed calendar allows `pre_tw_open` for 2026-07-01.
- [x] Found missing `analysis_date=2026-07-01` / `analysis_slot=pre_tw_open` row.
- [x] Repaired missing row as `t_market_analyses.id=198` through `MySqlEventStore.upsert_market_analysis()` using local relay, market-context, and market-snapshot evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 198 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed with 3 checkpoint bullets, garbled-text check passed, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-06-30 Pre-Open Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Inspect today's `pre_tw_open` row, raw telemetry, garbled text, and visible style/template compliance.
- [x] Repair only if missing or unhealthy, using local evidence only.
- [x] Verify final DB state, trade-signal count, and external-provider telemetry.

### 2026-06-30 Progress Notes
- Missing `analysis_date=2026-06-30` / `analysis_slot=pre_tw_open` row found; calendar allows `pre_tw_open` because Taiwan and relevant U.S. session are regular trading days.
- Repaired missing row as `t_market_analyses.id=195` through `MySqlEventStore.upsert_market_analysis()` using local relay, market-context, and market-snapshot evidence only.
- Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 195 -FixedPoolFallback`; stored 10 internal monitor rows.
- Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed, garbled-text check passed, `external_provider_api_called=false`.
- No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-06-27 Pre-Open Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirmed calendar state for `2026-06-27 08:00` Taiwan time: Taiwan market is weekend-closed; relevant U.S. session date `2026-06-26` is open; allowed slots are `us_close` only.
- [x] Confirmed no `analysis_date=2026-06-27` / `analysis_slot=pre_tw_open` row exists in `t_market_analyses`.
- [x] No repair performed because creating a `pre_tw_open` row on a Taiwan weekend would violate market-calendar policy.
- [x] No trade-signal extraction run; no repaired analysis id exists.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-06-29 Pre-Open Guard Run
- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirmed calendar state for `2026-06-29 08:00` Taiwan time: Taiwan market open; relevant U.S. session date `2026-06-28` weekend-closed; `pre_tw_open` is eligible without fresh U.S. close context.
- [x] Found missing `analysis_date=2026-06-29` / `analysis_slot=pre_tw_open` row and repaired it as `t_market_analyses.id=191` through `MySqlEventStore.upsert_market_analysis()` using local relay and market-context evidence only.
- [x] Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 191 -FixedPoolFallback`; stored 10 internal monitor rows.
- [x] Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed, garbled-text check passed, `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, or paid external LLM API was called.

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

## 2026-06-22 Run
- [x] Read repo instructions plus Workflow 4C storage/guard and daily template decisions.
- [x] Inspect today's `pre_tw_open` row, raw telemetry, garbled text, and visible style/template compliance.
- [x] If needed, repair/create the row from local evidence only and preserve Java delivery ownership.
- [x] Verify final DB state, trade-signal count, and external-provider telemetry.

### 2026-06-22 Progress Notes
- Missing `analysis_date=2026-06-22` / `analysis_slot=pre_tw_open` row repaired as `t_market_analyses.id=172` using local evidence only.
- Calendar state allowed `pre_tw_open`: Taiwan regular trading day, relevant U.S. session weekend-closed; repaired prose labels the missing fresh pre-open context gap.
- Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed, garbled-text check passed, `external_provider_api_called=false`.
- Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 172 -FixedPoolFallback`; stored 10 internal `t_trade_signals` monitor rows.

## Current Review Summary
- Outcome: Completed with no write; missing `2026-06-21 pre_tw_open` is calendar-correct.
- Open risks: The automation still fires on a Sunday with no eligible daily slot, so the same no-op will recur unless the schedule skips weekly-summary days.

## 2026-07-12 Free Palestine Weekly Editorial Run
- [x] Extract and review 2026-W28 local `t_palestine_news_items` rows.
- [x] Upsert the weekly editorial row.
- [x] Read back and validate the saved editorial.

### 2026-07-12 Progress Notes
- Generated and upserted `t_palestine_editorials.editorial_id=palestine-weekly-2026-W28`.
- Source window: 2026-07-05 through 2026-07-12 exclusive; 129 rows from `t_palestine_news_items`.
- Validation passed: readable Traditional Chinese, no mojibake/question blocks, source count matched saved IDs, no raw JSON body, no fabricated Markdown URLs.
- No OpenAI, Anthropic, or paid external LLM API was called.

## 2026-06-23 Run
- [x] Read repo instructions plus Workflow 4C storage/guard and daily template decisions.
- [x] Inspect today's `pre_tw_open` row, raw telemetry, garbled text, and visible style/template compliance.
- [x] Repair/create the missing row from local evidence only and preserve Java delivery ownership.
- [x] Verify final DB state, trade-signal count, and external-provider telemetry.

### 2026-06-23 Progress Notes
- Missing `analysis_date=2026-06-23` / `analysis_slot=pre_tw_open` row found; calendar allows `pre_tw_open` because Taiwan and the relevant U.S. session are regular trading days.
- Repaired missing row as `t_market_analyses.id=174` through `MySqlEventStore.upsert_market_analysis()` using local relay/market-context evidence only.
- Ran `scripts/run_trade_signal_extraction.ps1 -AnalysisId 174 -FixedPoolFallback`; stored 10 internal `t_trade_signals` monitor rows.
- Final verification: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, `structured_json` present, style/template check passed, garbled-text check passed, `external_provider_api_called=false`.

## 2026-06-23 TW Close Guard Run
- [x] Read repo instructions plus Workflow 4C storage/guard and daily template decisions.
- [x] Found missing `analysis_date=2026-06-23` / `analysis_slot=tw_close` row while calendar allowed `tw_close`.
- [x] Repaired missing row as `t_market_analyses.id=175` through `MySqlEventStore.upsert_market_analysis()` using local `market_context:tw_close` evidence only.
- [x] Corrected an initial PowerShell stdin encoding write by rewriting the same row through a UTF-8 Python helper path, then removed the helper.
- [x] Final verification: readable Traditional Chinese text, required seven-section daily editorial flow, exactly three `三個檢查點` bullets, no `台股配置`, no `今日個股觀察`, no entry/stop/target-price language.
- [x] Final DB state: `claim_verifier.ok=true`, `trust_gate.reason=claim_verifier_ok`, `trust_gate.signals_allowed=false`, `push_enabled=0`, `pushed=0`, `structured_json` present, `external_provider_api_called=false`.
- [x] Internal signal extraction skipped because current policy keeps `tw_close` storage-only and `trust_gate.signals_allowed=false`; `t_trade_signals` count for analysis id 175 is 0.

## 2026-07-17 Pre-Open Guard Run
- [x] Read automation memory, repo rules, Workflow 4C guard rules, prompt skill, and active lessons.
- [x] Confirm today's `pre_tw_open` row is missing and inspect local evidence.
- [x] Repair through `MySqlEventStore.upsert_market_analysis`, extract internal monitor signals, and verify final DB state.

### 2026-07-17 Re-plan
- Initial helper stopped before DB write because Windows Python lacked IANA timezone data.
- Use the standard-library fixed UTC+8 offset, then rerun the same calendar, claim, style, and garbled-text gates.
- Repaired the missing row as analysis `255` from nine local evidence rows; no external provider API was called.
- Stored 10 fixed-pool internal monitor signals.
- Final verification: claim verifier and style/garbled checks passed; trust gate reason is `claim_verifier_ok`; `push_enabled=1`, `pushed=0`, structured JSON present.

## 2026-07-17 Client-Visible Template Audit
- [x] Scan frontend analysis pages, market-analysis prompt templates, LINE/weekly skills, and memory docs for raw internal labels that could leak to client-visible text.
- [x] Replace prompt and skill wording with generic reader-facing rules: no source labels, table names, snake_case fields, scheduled task names, provider names, guard names, custom score labels, or missing-data implementation notes in visible prose.
- [x] Align daily analysis wording with `風險與觀察限制` and `主要反向觀點`.
## 2026-07-22 TW Close Guard Run
- [x] Read repo instructions, Workflow 4C guard rules, automation memory status, and active lessons.
- [x] Confirm today's `tw_close` row is missing and inspect local close/context evidence.
- [x] Repair through `MySqlEventStore.upsert_market_analysis` using local evidence only.
- [x] Verify DB state, visible-text gates, signal eligibility, and external-provider telemetry.

### 2026-07-22 TW Close Result
- Repaired the missing row as analysis `275` from four local evidence events; no external provider API was called.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, six headings, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, and `pushed=0`.
- Signal extraction skipped: the storage-only row has `trust_gate.signals_allowed=false`; signal count remains zero.
