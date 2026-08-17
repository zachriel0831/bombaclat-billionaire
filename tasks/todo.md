# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## 2026-08-17 Service Auto-Repair Data-Source Health
- [x] Read workspace/repo rules, CTO standards, workflow docs, and ingestion skill.
- [x] Reproduce the incident report and inspect live service, scheduler, log, and DB state.
- [x] Repair false-positive data-source health probes without touching LINE/order/AI services.
- [x] Run focused health/unit verification and the service auto-repair watcher dry run.
- [x] Record Observer completion and commit only related hunks.

### 2026-08-17 Service Auto-Repair Data-Source Health Result
- Root cause was health semantics, not stopped services: live workers, scheduled tasks, HTTP probes, source accuracy, and category ingestion were healthy, while the report treated expected quiet/event-driven data as repair-worthy.
- Updated data-source health to skip event-driven age-only TWSE/MOPS warnings, skip U.S. index/analysis checks on closed U.S. sessions, skip not-yet-due analysis slots, widen per-source article row windows, and only alert on public-record link freshness when deterministic recent article/record matches exist.
- Verification passed: `tests.test_data_source_health`, live `run_data_source_health.ps1 -Json` returned `overall_status=ok`, and `run_service_auto_repair_watch.ps1 -DryRun -Json` returned `overall_status=ok`, `failing_count=0`.

## 2026-08-15 US Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's missing `us_close` row plus local evidence.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Confirm retired signal extraction remains ineligible and record Observer completion.

### 2026-08-15 US Close Guard Result
- Created analysis `336` from three local consumer, rates/credit/market, and AI-financing evidence events; no external provider API, web search, LINE contact, or delivery action occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction was skipped because stock-recommendation extraction is retired. Calendar and claim-verifier tests passed (12 tests).

## 2026-08-14 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus local close context.
- [x] Create or repair the row from local evidence through `MySqlEventStore.upsert_market_analysis()` when required.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Confirm retired signal extraction remains a no-op with zero stored signals.

### 2026-08-14 TW Close Guard Result
- Created missing analysis `335` from four local close, flow, rates, credit, and technology-risk evidence events; no external provider API, web search, LINE contact, or delivery action occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Compatibility extraction reported stock recommendations retired; empty `stock_watch` produced zero trade signals. Calendar and claim-verifier tests passed (12 tests).

## 2026-08-14 Pre-Open Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `pre_tw_open` row plus local evidence.
- [x] Create or repair the row from local evidence through `MySqlEventStore.upsert_market_analysis()` when required.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Run the compatibility extraction entry point and verify no candidates are synthesized from an empty `stock_watch`.

### 2026-08-14 Pre-Open Guard Result
- Created missing analysis `334` from fourteen local market-context evidence rows; no external provider API, web search, LINE contact, or delivery action occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- Compatibility extraction reported the stock-recommendation workflow retired; empty `structured_json.stock_watch` produced zero trade signals. Calendar and claim-verifier tests passed (12 tests).

## 2026-08-14 US Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row plus local evidence.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Confirm retired signal extraction remains ineligible and record Observer completion.

### 2026-08-14 US Close Guard Result
- Created missing analysis `333` from four local index, producer-price, oil-demand, and rates evidence events plus two U.S. close snapshots; no external provider API, web search, LINE contact, or delivery action occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction was skipped because stock-recommendation extraction is retired and this context-only `us_close` row is not delivery-eligible; DB verification found zero trade signals.

## 2026-08-13 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus local close context.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Confirm retired signal extraction remains a no-op with zero stored signals.

### 2026-08-13 TW Close Guard Result
- Created missing analysis `332` from four local close, flow, rates, credit, volatility, and liquidity evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction reported the stock-recommendation workflow retired; DB verification found zero trade signals. Calendar tests passed.

## 2026-08-13 US Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row plus local evidence.
- [x] Create or repair the row from local evidence through `MySqlEventStore.upsert_market_analysis()` when required.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Confirm retired signal extraction remains ineligible and record Observer completion.

### 2026-08-13 US Close Guard Result
- Created missing analysis `329` from four local semiconductor, rates, credit, and volatility evidence events plus two U.S. close snapshots; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction reported the stock-recommendation workflow retired; DB verification found zero trade signals.

## 2026-08-12 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus local close context.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Confirm retired signal extraction remains a no-op with zero stored signals.

### 2026-08-12 TW Close Guard Result
- Created missing analysis `328` from five local close, flow, inflation, and policy-rate evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction reported the stock-recommendation workflow retired; DB verification found zero trade signals.

## 2026-08-12 US Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row plus local evidence.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-12 US Close Guard Result
- Created missing analysis `326` from five local inflation, AI-financing, and oil/geopolitics evidence events plus two U.S. open snapshots; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- The report explicitly records that the 2026-08-11 U.S. close snapshot was missing and does not substitute open prices. Signal extraction was skipped because stock-recommendation extraction is retired.

## 2026-08-11 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus local close context.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-11 TW Close Guard Result
- Created missing analysis `325` from four local close, flow, AI-infrastructure-financing, and oil/geopolitics evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction was skipped because the repo compatibility script declares stock-recommendation extraction retired; DB verification found zero trade signals.

## 2026-08-11 Pre-Open Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `pre_tw_open` row plus local context.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run policy-eligible signal extraction and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-11 Pre-Open Guard Result
- Created missing analysis `324` from five local market-context evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three checkpoint bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted extraction ran through the retired compatibility entry point; empty `stock_watch` correctly produced zero current trade signals.

## 2026-08-10 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus local close context.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply deterministic claim/trust/style checks and verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-10 TW Close Guard Result
- Created missing analysis `321` from five local close, flow, Asian-tech, semiconductor-revenue, and rate evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Independent numeric-token audit matched all visible figures to the selected local evidence. Signal extraction was skipped because the compatibility script declares stock-recommendation extraction retired and stores no signals.

## 2026-08-10 Pre-Open Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `pre_tw_open` row plus local context.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run policy-eligible signal extraction and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-10 Pre-Open Guard Result
- Created missing analysis `320` from three fresh local market-context evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three checkpoint bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted extraction ran through the retired compatibility entry point; empty `stock_watch` correctly produced zero current trade signals.

## 2026-08-10 News Source Accuracy Audit Schedule
- [x] Trace existing source health and news-platform collection paths.
- [x] Add official-list coverage audit for active plus low-frequency sources.
- [x] Add bounded compensation for sources below coverage threshold.
- [x] Register the scheduled task and verify local run output.
- [x] Update docs, run tests, and commit scoped changes.

## 2026-08-10 Low-Frequency News Source Expansion
- [x] Trace existing `news_platform` source adapters and author enrichment path.
- [x] Add low-frequency HTML list ingestion for verified public category pages.
- [x] Keep CTEE disabled unless an allowed public endpoint returns usable data.
- [x] Update source/docs/decision notes for the new low-frequency source behavior.
- [x] Run focused tests, diff checks, and commit scoped changes.

## 2026-08-09 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus local close context.
- [x] Apply the existing calendar policy and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-09 TW Close Guard Result
- Calendar guard returned no allowed daily analysis slots because both Taiwan and the relevant U.S. session are weekend-closed on local Sunday.
- Confirmed the 2026-08-09 `tw_close` row is absent as required. A scheduled `market_context:tw_close` event exists, but it does not override the weekend guard; no database write was made.
- Row-level claim/trust/style/structured/provider checks are not applicable. Trade-signal count is zero, and extraction was skipped because no eligible analysis exists and stock-recommendation extraction is retired.
- No external provider API, web search, LINE contact, or delivery action occurred.

## 2026-08-09 US Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, reasoning/audit guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Apply the existing calendar policy and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-09 US Close Guard Result
- Calendar guard excluded all daily analysis slots: local Sunday maps `us_close` to the 2026-08-08 U.S. weekend session, so no `us_close` row should be created.
- Confirmed the 2026-08-09 `us_close` row is absent. Claim/trust/style/structured/provider flags are therefore not applicable; no database write, external provider API, web search, LINE contact, or delivery action occurred.
- Signal extraction was skipped because no eligible analysis exists and stock-recommendation extraction is retired.

## 2026-08-06 Retire Stock Recommendations And Monitor Live Workers
- [x] Trace stock recommendation flow: `market_analysis` structured `stock_watch` -> `t_trade_signals` -> stock-monitor daily review; LINE stock query had dormant `StockQueryService`/platform client.
- [x] Retire market-analysis stock recommendation generation and make trade-signal extraction a no-op.
- [x] Add data-collecting live-worker monitor scripts for relay, source bridge, and news-platform loop.
- [x] Update workspace service-control skill so "all services" includes data live workers and the live-service monitor task, while Liuli/Ollama remain explicit-only.
- [x] Run focused tests, register monitor task, and commit scoped changes.

## 2026-08-06 Pre-Open Guard
- [x] Read repo rules, Workflow 4C, automation memory, skills, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `pre_tw_open` row.
- [x] Select fresh local relay/context evidence and write through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run eligible signal extraction and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-06 Pre-Open Guard Result
- Created missing analysis `314` from five local market-context evidence events; no external provider API, web search, or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three checkpoint bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted extraction ran; empty `stock_watch` correctly produced zero current trade signals.

## 2026-08-05 TW Close Guard
- [x] Read repo rules, Workflow 4C, automation memory, skills, and active lessons.
- [x] Confirm the slot is calendar-eligible, missing, and has same-day local close context.
- [x] Write the review-ready row through `MySqlEventStore.upsert_market_analysis`.
- [x] Run policy-eligible signal extraction and independently verify final DB state.
- [x] Record Observer completion, commit, and push the scoped run log.

### 2026-08-05 TW Close Guard Result
- Created `t_market_analyses.id=312` through `MySqlEventStore.upsert_market_analysis()` from four local evidence rows.
- Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, structured data present, exact six-section flow, exactly three evidence bullets, garbled/style/template checks passed, and `external_provider_api_called=false`.
- Targeted extraction completed; `structured_json.stock_watch` is empty, so zero current trade signals were stored.
- No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-08-05 Service Stack Cleanup
- [x] Update the workspace service skill so `liuli-social-ai-service`, Ollama, and llama-server are explicit-only village/AI targets, not part of the news/finance "all services" stack.
- [x] Stop noisy or misleading source health: X quota exhaustion, TVBS/CTEE broken endpoints, and CWA freshness semantics.
- [x] Align stock-monitor local port defaults and handoff docs to `8089`.
- [x] Remove raw inbound LINE message text/full IDs from webhook logs.
- [x] Run focused tests, smoke health checks, and commit only scoped repo changes.

### 2026-08-05 Result
- Liuli/Ollama/llama-server are explicit-only in the local service skill; the news/finance all-services stack excludes them.
- X quota exhaustion now stops in-process retries, local `.env` has X disabled, TVBS/CTEE are disabled by default, and CWA public-record freshness checks use refreshed timestamps.
- The CWA fixed-window task writes a status file plus daily log, and the live-service restart script now restarts `event_relay`, `source_bridge`, and `news_platform.main --loop` together.
- Verification passed: focused Python tests, `validate_readiness.py`, stock-monitor Maven tests, line-relay Maven tests with Java 21, CWA fixed-window smoke, data-source health, and service health checks.

## 2026-07-31 Daily Analysis Template Refresh
- [x] Confirm clean worktree and start observer telemetry.
- [x] Replace the fixed daily visible section contract in legacy and Stage4 prompts.
- [x] Sync prompt skills/docs with the new daily flow.
- [x] Run focused verification, commit, and push the scoped change.

### 2026-07-31 Result
- Daily `market_analysis` now uses `今日一句話` -> `三個檢查點` -> `市場押注與預期差` -> `國際消息到台股的傳導` -> `看錯的條件` -> `備註`.
- Synced legacy prompt, Stage4 prompt, prompt skills, README, memory-bank docs, and focused tests.
- Verification passed: `python -m unittest tests.test_market_analysis tests.test_analysis_stages -v`, `python scripts/validate_readiness.py`, `git diff --check`, and direct prompt smoke.

## 2026-07-27 Finance Expert Voice Learning
- [x] Confirm clean worktree and start observer telemetry.
- [x] Web-check high-recognition macro/market writers and Taiwan-facing finance sources.
- [x] Add blended analyst voice patterns to the existing macro prompt asset.
- [x] Verify prompt loading and readiness.
- [x] Commit and push the scoped change.

### 2026-07-27 Result
- Added blended analyst voice patterns to `skills/macro-weekly-summary-skill/SKILLS.md`.
- Synced `SKILL.md` and project documentation.
- Verification passed: `python scripts/validate_readiness.py`, `git diff --check`, and prompt smoke showing `analyst-voice-loaded=daily+weekly`.

## 2026-07-27 Weekly RAG Confirmation
- [x] Confirm daily `market_analysis` already loads macro skill and historical RAG.
- [x] Confirm weekly `weekly_summary` loaded macro skill but did not yet retrieve RAG.
- [x] Wire weekly summary to reuse historical RAG examples as analogues in the weekly prompt.
- [x] Update docs and run focused verification.
- [x] Commit and push the scoped change.

### 2026-07-27 Result
- Daily path confirmed: `market_analysis` loads `skills/macro-weekly-summary-skill/SKILLS.md` and retrieves historical RAG when enabled.
- Weekly path changed: `weekly_summary` now retrieves historical RAG examples, injects them into the weekly prompt, and stores telemetry in `raw_json.rag`.
- Verification passed: `python -m unittest tests.test_weekly_summary tests.test_rag tests.test_market_analysis -v`, `python scripts/validate_readiness.py`, `git diff --check`, and direct prompt/RAG smoke.

## 2026-07-27 Finance/Geopolitical Knowledge Sources Load
- [x] Read repo instructions, CTO rules pointer, project index, source/skill docs, and current dirty state.
- [x] Web-check reputable macro, market, trade, energy, uncertainty, and geopolitical data/analysis sources.
- [x] Load the selected source hierarchy and analysis method into the existing market-analysis prompt asset.
- [x] Verify skill/readiness checks and prompt loading.
- [x] Commit and push the scoped change.

### 2026-07-27 Result
- Added the source hierarchy to `skills/macro-weekly-summary-skill/SKILLS.md`, which is the file loaded by market-analysis and weekly-summary prompt builders.
- Synced the human-facing skill entry and project documentation.
- Verification passed: `python scripts/validate_readiness.py`, `git diff --check`, and a direct `_build_prompts()` smoke check that found the new knowledge-base text in the system prompt.

## 2026-07-26 CWA Earthquake High-Frequency Collection
- [x] Confirmed existing CWA weather task is healthy but only runs every 30 minutes.
- [x] Confirmed CWA official datasets: `E-A0015-001` significant felt earthquakes and `E-A0016-001` small-area felt earthquakes.
- [x] Add `E-A0016-001` to earthquake public-record collection without changing existing `E-A0015-001` record IDs.
- [x] Add a dedicated earthquake run script and 5-minute scheduled-task registration helper.
- [x] Update README and memory-bank workflow/source docs.
- [x] Verify parser tests, focused smoke collection, and scheduled-task registration.
- [x] Commit the scoped change.

## 2026-07-26 Codex Observer Data-Collecting Telemetry
- [x] Confirmed Observer previously recorded Codex turn-end skill/RAG events, not data-collecting job execution.
- [x] Added a non-blocking PowerShell telemetry helper for local job start/success/fail events.
- [x] Wrapped crawler, analysis, article digest, RAG, service, and maintenance entry scripts.
- [x] Updated README and memory-bank workflow documentation.
- [x] Verified PowerShell syntax, observer API writes, and dashboard display.
- [x] Commit the data-collecting instrumentation.

## Current Task
- Task: Guard the 2026-08-05 `us_close` market-analysis row from local evidence only.
- Requested by: automation
- Start date: 2026-08-05
- Scope: Create the missing stored analysis row, preserve Java delivery ownership, and use no paid external LLM APIs.

## Plan
- [x] Read repo rules, Workflow 4C, automation memory, skills, and active lessons.
- [x] Confirm the slot is calendar-eligible, missing, and has local evidence.
- [x] Write the review-ready row through `MySqlEventStore.upsert_market_analysis`.
- [x] Run eligible signal extraction and verify final DB state.
- [x] Record Observer completion, commit, and push the run log.

### 2026-08-05 US Close Guard Result
- Created `t_market_analyses.id=310` through `MySqlEventStore.upsert_market_analysis()` from five local evidence rows and two local market-index rows.
- Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=0`, `pushed=0`, structured data present, exact requested six-section flow, exactly three evidence bullets, garbled/style/template checks passed, and `external_provider_api_called=false`.
- Targeted extraction completed; `structured_json.stock_watch` is empty, so zero current trade signals were stored.
- No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

### 2026-08-04 Replan
- The first evidence query used nonexistent `event_time`; use the actual `published_at` column and keep the indexed recent-ID path.
- The first independent verifier embedded Chinese literals through PowerShell stdin, so its delimiter lookup was mis-encoded; rerun with Unicode escapes against the unchanged stored row.

### 2026-08-04 Pre-Open Guard Result
- Created `t_market_analyses.id=306` through `MySqlEventStore.upsert_market_analysis()` from four local market-context evidence rows.
- Final verification: claim support rate `1.0`, trust gate allowed delivery/signals, `push_enabled=1`, `pushed=0`, structured JSON present, six headings and exactly three evidence bullets passed, garbled/style/template checks passed, and `external_provider_api_called=false`.
- Targeted extraction completed; `structured_json.stock_watch` is empty, so zero current trade signals were stored.
- No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

### 2026-08-03 Replan
- The first diagnostic used the wrong settings attribute (`mysql_table`) after confirming the row was missing; switch to the existing `mysql_event_table` setting and keep the repair path unchanged.

### 2026-08-03 Pre-Open Guard Result
- Created `t_market_analyses.id=302` through `MySqlEventStore.upsert_market_analysis()` from three local market-context evidence rows.
- Final verification: claim support rate `1.0`, trust gate allowed delivery/signals, `push_enabled=1`, `pushed=0`, structured JSON present, six headings and exactly three evidence bullets passed, garbled/style/template checks passed, and `external_provider_api_called=false`.
- Targeted extraction completed; `structured_json.stock_watch` is empty, so zero current trade signals were stored.
- No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

### 2026-07-31 Replan
- Initial write was rejected before commit because `prompt_version` exceeded the existing column length.
- Replan: shorten only that metadata value, rerun the same validated payload, then query the stored row independently.

### 2026-07-31 Pre-Open Guard Result
- Created `t_market_analyses.id=298` from three same-day local BLS evidence events through `MySqlEventStore.upsert_market_analysis()`.
- Final verification: claim support rate `1.0`, trust gate allowed delivery/signals, `push_enabled=1`, `pushed=0`, structured JSON present, six headings and exactly three evidence bullets passed, garbled/style/template checks passed, and `external_provider_api_called=false`.
- Targeted extraction completed; `structured_json.stock_watch` is empty, so the correct current signal count is zero.
- No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-30 Pre-Open Guard Run
- [x] Taiwan and the relevant 2026-07-29 U.S. session are regular trading days; `pre_tw_open` was eligible and missing.
- [x] Created `t_market_analyses.id=295` through `MySqlEventStore.upsert_market_analysis()` using three local relay/context events only.
- [x] Final verification: claim support rate `1.0`, trust gate allowed delivery/signals, `push_enabled=1`, `pushed=0`, structured JSON present, six headings and exactly three evidence bullets passed, readable Traditional Chinese passed, and `external_provider_api_called=false`.
- [x] Targeted fixed-pool extraction stored 10 internal monitor signals.
- [x] No paid external LLM API, web search, or LINE contact occurred.

## 2026-07-28 US Close Guard Run
- [x] Taiwan and the relevant 2026-07-27 U.S. session were regular trading days; `us_close` was eligible and the target row was missing.
- [x] Created `t_market_analyses.id=286` through `MySqlEventStore.upsert_market_analysis()` using three local relay events and two local market-index rows.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, trust reason `claim_verifier_ok`, six required headings in order, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- [x] Ran internal dynamic signal extraction; `structured_json.stock_watch` was empty, so zero signals were stored and no fixed-pool padding was added.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-27 TW Close Guard Run
- [x] Taiwan was a regular trading day and `tw_close` was eligible; the target row was missing while fresh close context existed.
- [x] Created `t_market_analyses.id=285` through `MySqlEventStore.upsert_market_analysis()` using four local relay events only.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, trust reason `claim_verifier_ok`, six required headings in order, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- [x] Signal extraction skipped because `tw_close` is storage-only, `trust_gate.signals_allowed=false`, and `structured_json.stock_watch` is empty; signal count is zero.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-27 US Close Guard Run
- [x] Calendar guard excluded `us_close`: Taiwan is open, but the relevant 2026-07-26 U.S. session was weekend-closed; allowed slots are `pre_tw_open` and `tw_close`.
- [x] Confirmed no `analysis_date=2026-07-27` / `analysis_slot=us_close` row exists.
- [x] Per calendar policy, performed no DB write and no trade-signal extraction; row-level review fields are not applicable.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-26 Pre-Open Guard Run
- [x] Calendar guard returned no allowed daily slots because Taiwan local date is Sunday; Workflow 4L assigns the day to the weekly summary.
- [x] Confirmed no `analysis_date=2026-07-26` / `analysis_slot=pre_tw_open` row exists.
- [x] Confirmed the Sunday owner row exists as `analysis_date=2026-07-26` / `analysis_slot=weekly_tw_preopen`.
- [x] Per calendar policy, performed no daily write and no trade-signal extraction; daily delivery/style/provider fields are not applicable.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

## 2026-07-26 Weekly Guard Run
- [x] Found no `analysis_date=2026-07-26` / `analysis_slot=weekly_tw_preopen` row.
- [x] Created `t_market_analyses.id=282` through `MySqlEventStore.upsert_market_analysis()` using 17 selected local events, 429 recent market-context rows, and local indexed history availability.
- [x] Final verification: exact section order `週總經` -> `下週台股配置` -> `下週觀察清單`, exactly three top-level headings, garbled/mojibake and forbidden trade-language checks passed, `push_enabled=1`, `pushed=0`, `dimension=weekly`, `delivery_owner=java`, and `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

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
# 2026-07-25 US Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, Ponytail guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Gather local relay and market-index evidence without paid external APIs.
- [x] Created missing `t_market_analyses.id=280` through `MySqlEventStore.upsert_market_analysis()` from four local relay events and two local market-index rows.
- [x] Re-ran internal signal extraction without obsolete fixed-pool fallback; zero current dynamic signals were stored and the ten fallback rows were superseded.
- [x] Final verification: `claim_verifier.ok=true`, support rate `1.0`, `trust_gate.reason=claim_verifier_ok`, `push_enabled=1`, `pushed=0`, structured data present, six requested headings in order, exactly three evidence bullets, garbled/style/template checks passed, and `external_provider_api_called=false`.
- [x] No OpenAI, Anthropic, paid external LLM API, web search, or LINE contact occurred.

# 2026-07-26 US Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, Ponytail guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Verified calendar-correct no-op: Taiwan local Sunday and the relevant 2026-07-25 U.S. session are both weekend-closed, so `allowed_slots=[]`.
- [x] Confirmed no `2026-07-26 us_close` row exists; no DB write, signal extraction, external provider API, web search, or LINE contact was performed.

# 2026-07-26 Free Palestine Weekly Editorial Run

- [x] Read and review all 140 English source rows from 2026-07-19 through 2026-07-26 exclusive.
- [x] Draft and idempotently upsert `palestine-weekly-2026-W30` without paid LLM APIs.
- [x] Read back and validate encoding, source IDs/count, body format, and citations.

## 2026-07-26 Free Palestine Weekly Editorial Result

- Published `palestine-weekly-2026-W30`, titled `停火若只留下新的邊界，和平就只是另一種佔領`.
- Validation passed: readable Traditional Chinese, no mojibake/question blocks, 140 unique saved IDs matched `source_count`, no raw JSON in the body, and every Markdown citation matched a reviewed source URL.
- No OpenAI, Anthropic, or other paid external LLM API was called.

# 2026-07-28 Pre-Open Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, Ponytail guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `pre_tw_open` row.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run targeted internal signal extraction and verify the final delivery-ready DB state.

## 2026-07-28 Pre-Open Guard Result

- Repaired the missing row as analysis `287` from three local evidence events; no external provider API was called.
- Corrected PowerShell stdin encoding by rewriting the same row through a temporary UTF-8 Python helper, then removed the helper.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, six headings, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and 10 internal monitor signals.

# 2026-08-02 Free Palestine Weekly Editorial Run

- [x] Reviewed all 135 English source rows from 2026-07-26 through 2026-08-02 exclusive, including raw metadata.
- [x] Upserted `palestine-weekly-2026-W31` without a paid external LLM API.
- [x] Read back and validated Traditional Chinese text, source IDs/count, body format, and citations.

## 2026-08-02 Free Palestine Weekly Editorial Result

- Published `palestine-weekly-2026-W31`, titled `和平不能只要求巴勒斯坦人先放下武器`.
- Validation passed with 135 unique source IDs and seven citations to reviewed source URLs.

# 2026-07-29 US Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, Ponytail guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run eligible internal signal extraction and verify the final DB state.

## 2026-07-29 US Close Guard Result

- Repaired the missing row as analysis `290` from three local evidence events and two U.S. close index rows; no external provider API was called.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, six requested headings, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Dynamic signal extraction ran; empty `stock_watch` produced zero signals without fixed-pool padding.

# 2026-07-30 TW Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, Ponytail guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus same-day local close evidence.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply existing signal policy and verify the final DB state.

## 2026-07-30 TW Close Guard Result

- Repaired the missing row as analysis `296` from four same-day local evidence events; no external provider API was called.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, six requested headings, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted signal extraction ran; empty `stock_watch` produced zero signals without fixed-pool padding.

# 2026-07-31 TW Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, skills, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus same-day local evidence.
- [x] Create or repair the row from local evidence only when required.
- [x] Apply signal policy, verify final DB state, and record the result.

## 2026-07-31 TW Close Guard Result

- Created missing analysis `299` through `MySqlEventStore.upsert_market_analysis()` from four local evidence rows; no external provider API or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, required six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted signal extraction ran; empty `stock_watch` produced zero signals.

# 2026-07-31 US Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory status, Ponytail guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Apply existing signal policy and verify the final DB state.

## 2026-07-31 US Close Guard Result

- Repaired the missing row as analysis `297` from three local BLS evidence events; no external provider API was called.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, six requested headings, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted signal extraction ran; empty `stock_watch` produced zero signals without fixed-pool padding.

# 2026-08-02 Weekly Codex Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C weekly storage rules, weekly contract, skills, and active lessons.
- [x] Inspect target Sunday `weekly_tw_preopen` row and current local evidence/history availability.
- [x] Create or repair the row through `MySqlEventStore.upsert_market_analysis()` using local evidence only when required.
- [x] Verify final DB state, text contract, delivery flags, provenance, and record the result.

## 2026-08-02 Weekly Codex Guard Result

- Created missing analysis `300` from 10 selected local evidence events, 432 market-context rows, and local indexed history availability; no external provider API or LINE contact occurred.
- Corrected PowerShell stdin mojibake by rewriting the same row through a temporary UTF-8 helper, then removed the helper.
- Final checks passed: exact three-section order, readable Traditional Chinese, no forbidden trade/internal terms, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.

# 2026-08-03 TW Close Guard Run

- [x] Read repo instructions, Workflow 4C guard rules, automation memory, skills, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `tw_close` row plus same-day local evidence.
- [x] Create the missing row from local evidence through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run eligible internal signal extraction and verify the final DB state.

## 2026-08-03 TW Close Guard Result

- Created analysis `303` from ten local Taiwan flow evidence rows; no external provider API or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted signal extraction ran; empty `stock_watch` correctly produced zero signals without fixed-pool padding.

# 2026-08-04 US Close Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C guard rules, skills, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row plus local U.S. close evidence.
- [x] Create the missing row through `MySqlEventStore.upsert_market_analysis()` using local evidence only.
- [x] Run eligible internal signal extraction and verify the final DB state.

## 2026-08-04 US Close Guard Result

- Created analysis `305` from five local evidence events and two U.S. close index rows; no external provider API or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted signal extraction ran; empty `stock_watch` correctly produced zero signals without fixed-pool padding.

# 2026-08-05 Pre-Open Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C guard rules, skills, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `pre_tw_open` row plus local evidence.
- [x] Create or repair the row through `MySqlEventStore.upsert_market_analysis()` only if required.
- [x] Run eligible signal extraction, verify final DB state, and record the result.

## 2026-08-05 Pre-Open Guard Result

- Created missing analysis `311` from four local market-context evidence events; no external provider API or LINE contact occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact requested six-section flow, exactly three checkpoint bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, and `external_provider_api_called=false`.
- Targeted extraction ran; empty `stock_watch` correctly produced zero current trade signals.
# 2026-08-09 Free Palestine Weekly Editorial Run

- [x] Review every English source row from 2026-08-02 through 2026-08-09 exclusive, including raw metadata.
- [x] Draft and idempotently upsert `palestine-weekly-2026-W32` without paid external LLM APIs.
- [x] Read back and validate Traditional Chinese text, source IDs/count, body format, and citations.

## 2026-08-09 Free Palestine Weekly Editorial Result

- Published `palestine-weekly-2026-W32`, titled `停火若不能讓人活下來，就只是暴力換了名字`.
- Validation passed with 99 unique source IDs and seven citations to reviewed source URLs.
- A first stdin-encoded write was rejected by mojibake validation and replaced with a verified UTF-8 rewrite.

# 2026-08-09 Live Service Monitor Fixed Window

- [x] Read repo instructions, CTO standards, service-control skill, and operational workflow docs.
- [x] Confirm `NewsCollector-LiveServiceMonitor` is the remaining repeating popup task.
- [x] Add a persistent visible monitor window that reuses `monitor_live_services.ps1`.
- [x] Register and start the monitor as a fixed window, then verify task action, process, logs, and status file.
- [x] Commit and push only task-related files.

# 2026-08-10 Service Auto-Repair Watcher

- [x] Add a full local service watcher for frontend, API, LINE relay, stock monitor, Redis, event relay, frontend ngrok, Observer, enabled `NewsCollector-*` tasks, data-source health, and source-accuracy reports.
- [x] Generate deduped warn+ incidents under `runtime/service-auto-repair/`.
- [x] Launch a constrained background `codex exec` repair agent when `-LaunchAgent` is set.
- [x] Wire the watcher into the existing fixed live-service monitor window.
- [x] Register the updated `NewsCollector-LiveServiceMonitor` scheduled task action and verify dry-run behavior.
# 2026-08-10 US Close Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row.
- [x] Verify the policy-valid no-row outcome and skip ineligible signal extraction.

## 2026-08-10 US Close Guard Result

- Calendar mapped the local run to the 2026-08-09 U.S. weekend session, so allowed slots are `pre_tw_open` and `tw_close` only.
- Confirmed no `2026-08-10 us_close` row exists; no DB write, external provider API, web search, LINE contact, or delivery action occurred.
- Claim/trust/push/structured/style checks are not applicable without an eligible analysis; signal extraction was skipped because no eligible row exists and stock recommendation extraction is retired.

# 2026-08-10 Short Scheduled Task Popup Fix

- [x] Identify the popup source from recent Task Scheduler runs.
- [x] Add hidden-window PowerShell actions for short-lived scheduled jobs.
- [x] Fix repeating task registration so re-registering during the day schedules the next future run.
- [x] Re-register affected tasks and verify action arguments.
- [x] Commit only task-related files.

# 2026-08-11 US Close Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirm calendar eligibility and inspect today's `us_close` row plus local evidence.
- [x] Create the missing row through `MySqlEventStore.upsert_market_analysis()` and verify final DB state.

## 2026-08-11 US Close Guard Result

- Created analysis `323` from four local evidence events and two U.S. index-close rows; no external provider API, web search, LINE contact, or delivery action occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three evidence bullets, readable Traditional Chinese, structured data present, `push_enabled=0`, `pushed=0`, and `external_provider_api_called=false`.
- Signal extraction was skipped because stock recommendation extraction is retired.

# 2026-08-11 Low-Frequency Source Fixed Window

- [x] Stop the existing short-lived popup task before it can run again.
- [x] Add a persistent visible window runner for TVBS/UDN/SETN low-frequency collection.
- [x] Register `NewsCollector-NewsPlatformLowFrequencySources` as an interactive-logon fixed window.
- [x] Update runbooks and ingestion skill so future business schedulers avoid popup-and-exit consoles.
- [x] Verify task action, parser checks, fixed-window startup, and local commit.

# 2026-08-12 CI Unit Test Failure

- [x] Confirm screenshot failures against local tests and config.
- [x] Add the missing package dependency used by `relay_client.py`.
- [x] Update the public-source `all` test to include CWA supported sources.
- [x] Run targeted tests and full unittest discovery.
- [x] Commit only CI/test related files.

# 2026-08-12 Pre-Open Codex Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C guard rules, and active lessons.
- [x] Confirm calendar eligibility and inspect today's missing `pre_tw_open` row plus local evidence.
- [x] Create the missing row through `MySqlEventStore.upsert_market_analysis()`.
- [x] Run targeted trade-signal extraction and verify the final delivery-ready DB state.

## 2026-08-12 Pre-Open Codex Guard Result

- Created analysis `327` from eight fresh local market-context events; no external provider API, web search, LINE contact, or delivery action occurred.
- Final checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, exact six-section flow, exactly three checkpoint bullets, readable Traditional Chinese, structured data present, `push_enabled=1`, `pushed=0`, zero trade signals, and `external_provider_api_called=false`.

# 2026-08-12 Live Service Wrapper Cleanup

- [x] Disable `NewsCollector-LiveServiceMonitor` and close stale empty worker wrappers.
- [x] Reproduce why `source_bridge` is marked missing.
- [x] Fix `run_source_bridge.ps1` startup compatibility.
- [x] Fix `restart_live_services.ps1` so old worker wrappers are closed before restart.
- [x] Update runbooks/lessons and verify live-service restart health.
- [x] Commit and push only task-related files.

# 2026-08-17 TW Close Codex Guard Run

- [x] Read repo instructions, automation memory, Workflow 4C, writing skills, reasoning guidance, and active lessons.
- [x] Confirm calendar eligibility and inspect today's missing `tw_close` row plus local close evidence.
- [x] Create the missing row through `MySqlEventStore.upsert_market_analysis()` using local evidence only.
- [x] Verify claim/trust, push, structured data, encoding, style, provider flags, and zero trade signals.

## 2026-08-17 TW Close Codex Guard Result

- Created analysis `340` from six local Taiwan flow, credit, and semiconductor-context events; no external provider API, web search, LINE contact, delivery action, or stock recommendation flow occurred.
- Final DB checks passed: claim support `1.0`, trust reason `claim_verifier_ok`, readable flexible briefing memo, structured data present, `push_enabled=0`, `pushed=0`, zero trade signals, and `external_provider_api_called=false`.
- Calendar and claim-verifier tests passed (12 tests). The close-data caveat is that complete index transaction structure and a valid institutional net-flow aggregate were unavailable.
