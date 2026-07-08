# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
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
