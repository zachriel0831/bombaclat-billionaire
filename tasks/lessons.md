# Lessons Log

This file is append-only. Add a new entry after any user correction to prevent repeated mistakes.

## Entry Pattern

```md
## LESSON-YYYYMMDD-XX
- Date:
- Trigger (User correction):
- What was wrong:
- Root cause:
- New rule (always/never):
- Prevention checklist (before final response):
  - [ ] Check 1
  - [ ] Check 2
  - [ ] Check 3
- Repo updates made:
  - file/path
- Verification evidence:
  - command/output summary
- Status: active

```

## Active Lessons

<!-- Add new lessons below this line -->

## LESSON-20260511-06
- Date: 2026-05-11
- Trigger (User correction): User clarified Taiwan finance news should enter `relay_event`, not the Taiwan `news_article` pipeline.
- What was wrong: The finance-news storage boundary could be confused with the newly added Taiwan society/politics `news_platform` tables.
- Root cause: Both tasks involve Taiwan news sources, but market-analysis finance news and society/politics article browsing use different storage contracts.
- New rule (always/never): Always route finance/market news into `news_collector` -> `t_relay_events`; never put it into `news_platform.t_news_articles` unless the user explicitly creates a finance news-platform product.
- Prevention checklist (before final response):
  - [ ] Confirm source category is market/finance vs society/politics
  - [ ] Confirm storage destination is `t_relay_events` for market evidence
  - [ ] Restart bridge after `.env` source-list changes and verify DB rows
- Repo updates made:
  - `.env`
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
  - `memory-bank/09-decisions/2026-05-11-taiwan-finance-rss-relay-events.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - RSS smoke fetch returned Taiwan finance rows from LTN, CNA, and ETtoday
  - Bridge log `source-bridge-20260511-120622.out.log` showed the three Taiwan finance feeds parsed and stored
  - DB query confirmed ids `79193`, `79194`, and `79195` in `t_relay_events`
- Status: active

## LESSON-20260511-05
- Date: 2026-05-11
- Trigger (User correction): User saw the society page still showing many vehicle-accident articles as pending/mixed in the all-society view.
- What was wrong: The live `news_platform.main --loop` processes were still old instances that crawled and ran keyword extraction but did not run topic classification, leaving fresh rows with `topics_json IS NULL`.
- Root cause: Code/backfill had been updated, but existing long-running worker processes were not restarted and verified after the topic-worker change.
- New rule (always/never): Always restart and verify long-running `news_platform` loops after worker/topic code changes; live DB verification must include `topics_json IS NULL` counts for active categories.
- Prevention checklist (before final response):
  - [ ] Check live rows with `topics_json IS NULL`
  - [ ] Inspect loop logs for `Topic pass scanned=<n>` after restart or after new rows arrive
  - [ ] Reclassify targeted fallback rows when topic rules are expanded
- Repo updates made:
  - `src/news_platform/topics.py`
  - `tests/test_news_platform_topic_classifier.py`
  - `memory-bank/workflows.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - Backfill output: `Topic classification done: scanned=73 updated=73 failed=0`
  - Live DB counts: `politics|127|0|0`, `society|634|0|0`
  - Full news-platform tests: `81 tests OK`
- Status: active

## LESSON-20260511-04
- Date: 2026-05-11
- Trigger (User correction): User ordered two iron rules: never operate outside `D:\work_space`; never charge a credit card.
- What was wrong: These absolute safety boundaries were not yet persisted in repo rules.
- Root cause: Prior rules covered secrets and destructive operations but did not define workspace and payment hard stops.
- New rule (always/never): Never operate on files outside `D:\work_space`; never charge, authorize, submit, test, save, or use any credit card/payment method.
- Prevention checklist (before final response):
  - [ ] Confirm every filesystem path is under `D:\work_space`
  - [ ] Refuse any operation involving credit-card/payment submission
  - [ ] Keep these rules visible in `AGENTS.md` and `memory-bank/rules.md`
- Repo updates made:
  - `AGENTS.md`
  - `memory-bank/rules.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `rg` confirmed both iron rules in `AGENTS.md`, `memory-bank/rules.md`, `tasks/todo.md`, and this lesson
  - `git diff --check -- AGENTS.md memory-bank/rules.md tasks/todo.md tasks/lessons.md` passed with CRLF warnings only
- Status: active

## LESSON-20260511-03
- Date: 2026-05-11
- Trigger (User correction): User asked to temporarily classify unclassified news as general society news.
- What was wrong: Rule no-hit rows were stored as `topics_json=[]`, creating a visible unclassified bucket.
- Root cause: The first implementation optimized for later LLM fallback review, not frontend/category completeness.
- New rule (always/never): Always provide a visible fallback topic for processed news rows; use `general_social_news` / 一般社會新聞 when no specific topic matches.
- Prevention checklist (before final response):
  - [ ] Confirm processed rows have non-empty `topics_json`
  - [ ] Keep fallback rows distinguishable with `source=rule_fallback` or `source=llm_fallback`
  - [ ] Verify live DB counts after backfill
- Repo updates made:
  - `src/news_platform/topics.py`
  - `src/news_platform/topic_worker.py`
  - `src/news_platform/topic_llm_worker.py`
  - `src/news_platform/store.py`
  - `tests/test_news_platform_topic_worker.py`
  - `tests/test_news_platform_topic_llm_worker.py`
  - `tests/test_news_platform_store_topics.py`
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
  - `memory-bank/09-decisions/2026-05-11-news-platform-topic-classification.md`
  - `memory-bank/09-decisions/2026-05-11-news-platform-llm-topic-fallback.md`
  - `spec/news-topic-classification-*.md`
  - `tasks/todo.md`
- Verification evidence:
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_news_platform_*.py" -v` passed
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m compileall -q src/news_platform tests/test_news_platform_topic_worker.py tests/test_news_platform_topic_llm_worker.py tests/test_news_platform_store_topics.py` passed
  - `git diff --check -- <changed news_platform/docs/spec/task files>` passed with CRLF warnings only
  - Live DB update converted 498 rows; count query shows empty_topics=0 and general_social_news=498
- Status: active

## LESSON-20260511-02
- Date: 2026-05-11
- Trigger (User correction): User noticed `t_news_articles` did not appear to have the topic column and asked to execute SQL/backfill old rows.
- What was wrong: I had implemented migration/backfill code but had not verified the live MySQL schema or run the historical backfill.
- Root cause: Verification stopped at local tests and docs instead of checking the runtime DB after a schema/data-flow change.
- New rule (always/never): Always verify live schema and run required historical backfill after adding DB columns/workers when the user expects deployed data to be visible.
- Prevention checklist (before final response):
  - [ ] Query `INFORMATION_SCHEMA.COLUMNS` for new DB columns
  - [ ] Run worker/backfill against live rows when requested
  - [ ] Report processed/unprocessed counts from the live table
- Repo updates made:
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - Live DB columns include `topics_json`, `topic_classified_by`, `topic_classified_at`
  - Topic worker output: scanned=575 updated=575 failed=0
  - Live count query: 575 classified rows, 0 missing topics, 77 rule hits, 498 rule no-hit rows
- Status: active

## LESSON-20260511-01
- Date: 2026-05-11
- Trigger (User correction): User clarified `market_analysis` should fixed-connect five Taiwan stocks and should not let the model recommend tickers.
- What was wrong: Existing specs still described free-form recommendations, candidate top-up, and generic fallback ticker selection.
- Root cause: `stock_watch` and `t_trade_signals` were documented as recommendation discovery instead of a fixed monitoring pool.
- New rule (always/never): Always treat `market_analysis` stock output as the fixed pool `2330`, `2603`, `2882`, `1605`, `4956`; never present it as model-selected recommendations.
- Prevention checklist (before final response):
  - [ ] Check README / memory-bank / requirements / spec wording says fixed watch pool
  - [ ] Confirm old tracked fallback tickers are absent from specs
  - [ ] Explicitly separate fixed watch rows from stock monitor triggers and orders
- Repo updates made:
  - `README.md`
  - `requirements.yml`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
  - `memory-bank/09-decisions/`
  - `spec/market-analysis-fixed-watchlist-*.md`
  - `src/event_relay/analysis_stages/`
  - `src/event_relay/trade_signals.py`
  - `src/event_relay/market_analysis.py`
  - `src/event_relay/service.py`
  - `tests/test_trade_signals.py`
  - `tests/test_market_analysis.py`
  - `tasks/todo.md`
- Verification evidence:
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m unittest tests.test_trade_signals tests.test_analysis_stages tests.test_market_analysis -v` passed
  - `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m compileall -q src/event_relay tests/test_trade_signals.py tests/test_analysis_stages.py tests/test_market_analysis.py` passed
  - `rg` old tracked tickers / old free-form recommendation phrases returned no matches in active specs/docs
  - `git diff --check -- <changed docs/spec files>` passed with CRLF warnings only
- Status: active

## LESSON-20260305-01
- Date: 2026-03-05
- Trigger (User correction): User requested persistent correction memory and explicit pattern in `tasks/lessons.md`.
- What was wrong: Repository had no formal correction-capture loop, so repeated mistakes were not systematically prevented.
- Root cause: Process focused on implementation outputs, not explicit post-correction learning artifacts.
- New rule (always/never): Always append a structured lesson after user correction and reference it in future task start checks.
- Prevention checklist (before final response):
  - [ ] Re-check `tasks/lessons.md` for applicable active lessons
  - [ ] Confirm `tasks/todo.md` includes verification evidence
  - [ ] If user corrected current task, append a new lesson entry
- Repo updates made:
  - `tasks/lessons.md`
  - `tasks/todo.md`
  - `AGENTS.md`
  - `memory-bank/workflows.md`
- Verification evidence:
  - Added and linked workflow files
  - Ran compile and unit tests successfully
- Status: active

## LESSON-20260305-02
- Date: 2026-03-05
- Trigger (User correction): User asked to stop blocking Korean and requested stream output to keep only top-level `url`.
- What was wrong: Stream runner defaulted to English-only filter, and output shape stayed full JSON event even when user wanted URL-only feed.
- Root cause: Initial defaults optimized readability, not downstream URL-only integration use case.
- New rule (always/never): Always confirm output contract (full JSON vs selected fields) and avoid restrictive language defaults unless explicitly requested.
- Prevention checklist (before final response):
  - [ ] Confirm required output fields with the user request text
  - [ ] Check script defaults do not silently filter data
  - [ ] Run CLI help or sample run to verify new flags are wired
- Repo updates made:
  - `src/news_collector/main.py`
  - `scripts/run_benzinga_stream.ps1`
  - `README.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m compileall src` passed
  - `python -m news_collector.main stream --help` shows `--url-only`
  - Stream run executed with `-UrlOnly` (received 429 during test window)
- Status: active

## LESSON-20260305-03
- Date: 2026-03-05
- Trigger (User correction): User expected `.env.example` edits to affect runtime behavior and asked to remove the template file.
- What was wrong: Runtime read `.env` only, causing mismatch with user expectation after editing `.env.example`.
- Root cause: Environment file contract was implicit and not enforced with clear runtime messaging/documentation.
- New rule (always/never): Always make runtime env source explicit and keep file conventions unambiguous to avoid config drift.
- Prevention checklist (before final response):
  - [ ] Verify which env file is loaded by runtime command path
  - [ ] Ensure docs match actual runtime env behavior
  - [ ] Remove or rename misleading template files if requested
- Repo updates made:
  - `README.md`
  - `.env.example` (removed)
  - `src/news_collector/main.py`
  - `tasks/lessons.md`
- Verification evidence:
  - Confirmed `.env.example` no longer exists
  - Ran one-shot GDELT fetch with language/title-url filters
- Status: active

## LESSON-20260305-04
- Date: 2026-03-05
- Trigger (User correction): User requested GDELT 429 handling to be switchable and currently turned off.
- What was wrong: 429 cooldown behavior was hardcoded, reducing operational flexibility during live tuning.
- Root cause: Protective logic was implemented without an environment-level feature switch.
- New rule (always/never): Always expose rate-limit mitigation as explicit config switches with conservative defaults.
- Prevention checklist (before final response):
  - [ ] Verify 429 behavior is configurable through env
  - [ ] Confirm default value matches user-requested operational mode
  - [ ] Restart long-running service after config or source logic changes
- Repo updates made:
  - `src/news_collector/config.py`
  - `src/news_collector/collector.py`
  - `src/news_collector/sources/gdelt.py`
  - `.env`
  - `README.md`
  - `tests/test_config.py`
  - `tests/test_collector.py`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m compileall src tests` passed
  - `python -m unittest discover -s tests -p \"test_*.py\" -v` passed
  - runtime config shows `gdelt_cooldown_on_429=False`
- Status: active


## LESSON-20260307-01
- Date: 2026-03-07
- Trigger (User correction): User asked to replace X polling with stream listening.
- What was wrong: Bridge still handled X by polling cycle, not continuous stream.
- Root cause: Earlier implementation prioritized simpler API flow over fastest-delivery requirement.
- New rule (always/never): Always prioritize streaming ingestion when user asks for latest/fastest social feed.
- Prevention checklist (before final response):
  - [ ] Confirm requirement is stream vs polling
  - [ ] Split polling sources and streaming sources in bridge threads
  - [ ] Add reconnect/backoff and 429 stop behavior for stream sources
- Repo updates made:
  - `src/news_collector/x_stream.py`
  - `src/news_collector/relay_bridge.py`
  - `scripts/run_source_bridge.ps1`
  - `README.md`
  - `tests/test_x_stream.py`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m unittest discover -s tests -p "test_*.py" -v` passed (16 tests)
  - `python -m news_collector.relay_bridge --help` shows X stream args
- Status: active

## LESSON-20260421-01
- Date: 2026-04-21
- Trigger (User correction): User clarified that LINE service has migrated to the Java system and Python is now purely the data collection and analysis service.
- What was wrong: I initially framed the local Python relay as a LINE service and moved toward webhook/ngrok setup before separating the current Python-vs-Java responsibilities.
- Root cause: Legacy script/module names still include `event_relay`, and I mirrored those names in user-facing language instead of describing the current operational boundary.
- New rule (always/never): Always refer to this Python repository as the data collection and analysis service; Java owns LINE delivery/webhook behavior.
- Prevention checklist (before final response):
  - [ ] Distinguish Python data ingestion/analysis from Java-owned LINE delivery/webhook behavior
  - [ ] Avoid starting ngrok, LINE webhook, or LINE push paths from this repo unless explicitly requested as legacy compatibility work
  - [ ] When using legacy-named scripts/modules, explain the current runtime role rather than repeating outdated service names
- Repo updates made:
  - `tasks/lessons.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
- Verification evidence:
  - Started `python -m event_relay.main --env-file .env --log-level INFO`
  - Verified `http://127.0.0.1:18090/healthz` returned `{"ok": true}`
- Status: active

## LESSON-20260422-01
- Date: 2026-04-22
- Trigger (User correction): User clarified that `t_market_analyses` should be written only after aggregating same-day `t_relay_events` and asking the model; REQ-009, REQ-010, and REQ-011 source/context events should all write to `t_relay_events`.
- What was wrong: I described REQ-011 too much like a direct analysis write and did not emphasize that its source/context facts must first become relay events.
- Root cause: I collapsed the source/event layer and the model-analysis layer when discussing the task dependency graph.
- New rule (always/never): Always keep source/context ingestion and model analysis as separate layers: source collectors write `t_relay_events`; analysis jobs read event windows and write `t_market_analyses`.
- Prevention checklist (before final response):
  - [ ] Confirm whether the task is collecting facts/events or generating analysis text
  - [ ] If it is collecting facts/events, ensure the destination is `t_relay_events`
  - [ ] If it writes `t_market_analyses`, confirm it is a model analysis job that reads `t_relay_events`
- Repo updates made:
  - `requirements.yml`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `git diff --check -- requirements.yml memory-bank/PROJECT_DOCUMENTATION.md tasks/todo.md tasks/lessons.md` passed with CRLF warnings only
  - `rg` confirmed REQ-009, REQ-010, and REQ-011 describe source/context events writing to `t_relay_events`
- Status: active

## LESSON-20260425-01
- Date: 2026-04-25
- Trigger (User correction): User pointed out `REQ-001` should already be complete and asked to verify it before leaving it non-done.
- What was wrong: The requirement was left in `review` based on an old pending DB note instead of being re-verified against the current live environment.
- Root cause: I relied on stale task comments and the global interpreter first, instead of checking the repo's intended `.venv` runtime and rerunning the blocked acceptance step.
- New rule (always/never): Always verify requirement status against current acceptance criteria using the repo's intended runtime environment before leaving a task in `review` or `pending`.
- Prevention checklist (before final response):
  - [ ] Re-run any acceptance item whose blocker was previously "needs runtime recheck" instead of trusting old notes
  - [ ] Confirm whether the repo expects `.venv` rather than the global interpreter for optional dependencies
  - [ ] If runtime success is followed by a console-encoding-only crash, separate data-path success from logging-path failure and fix the logging bug
- Repo updates made:
  - `src/scrapers/yfinance_stocks.py`
  - `requirements.yml`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_yfinance_stocks -v` passed (4/4)
  - `.venv\\Scripts\\python.exe src\\scrapers\\yfinance_stocks.py` fetched 26 symbols and wrote `data/stocks/stocks_20260425_025225.json`
  - MySQL query confirmed 26 same-day `t_relay_events` rows with `source LIKE 'yfinance%'`
- Status: active

## LESSON-20260425-02
- Date: 2026-04-25
- Trigger (User correction): User pointed out `REQ-008` should already be executed and asked for REQ-009 to be implemented only if it was truly incomplete.
- What was wrong: Requirement status in `requirements.yml` lagged behind actual implementation and verification state, which made already-finished work still look pending/review.
- Root cause: I relied too much on stale requirement statuses instead of re-verifying the live code, tests, scheduler state, and database writes before deciding whether work was incomplete.
- New rule (always/never): Always verify a requirement's real completion state from code + runtime evidence before assuming a pending/review status is still accurate.
- Prevention checklist (before final response):
  - [ ] Re-check whether the requirement file status is stale relative to the current repo state
  - [ ] Use both static evidence and runtime evidence before saying a feature is incomplete
  - [ ] If implementation already exists, sync requirement status instead of re-implementing blindly
- Repo updates made:
  - `requirements.yml`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - Static grep confirmed REQ-008 Python LINE touch paths are absent from active code
  - Task Scheduler scan confirmed no AnalysisPush / LINE / SummarySender jobs remain
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v` passed (140 tests)
  - `scripts/run_tw_market_flow.ps1 -EnvFile .env` stored 14 REQ-009 dataset events with 0 failures
  - MySQL query confirmed new REQ-009 rows `19634-19647` in `t_relay_events`
- Status: active

## LESSON-20260426-01
- Date: 2026-04-26
- Trigger (User correction): User asked to write the "primitive-short" response style into global rules.
- What was wrong: Replies were still too verbose for the user's preferred low-token working style.
- Root cause: The preference was active in conversation but not persisted in repository rules.
- New rule (always/never): Always default to primitive-short replies: few words, clear meaning, no filler, unless depth is requested or needed for safety.
- Prevention checklist (before final response):
  - [ ] Can this be answered in 1-3 concise lines?
  - [ ] Remove repeated context and unnecessary tables
  - [ ] Keep only blockers, verification, and essential technical detail
- Repo updates made:
  - `AGENTS.md`
  - `memory-bank/rules.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `rg` confirmed primitive-short rules are present in global/project rule files
- Status: active

## LESSON-20260426-02
- Date: 2026-04-26
- Trigger (User correction): User pointed out `weekly_tw_preopen.scheduled_time_local` used `Sun 05:10` and should be unified.
- What was wrong: Weekly analysis stored weekday text in `scheduled_time_local`, while daily analyses use `HH:MM`.
- Root cause: I mixed delivery-day semantics into a time-only column instead of keeping weekday/date in `analysis_date`, `analysis_slot`, and `raw_json`.
- New rule (always/never): Always store `t_market_analyses.scheduled_time_local` as `HH:MM` only; never include weekday prefixes.
- Prevention checklist (before final response):
  - [ ] Check existing column format before adding special-case values
  - [ ] Keep date/day semantics in date or metadata fields
  - [ ] Add a regression test for storage contracts the user corrects
- Repo updates made:
  - `src/event_relay/weekly_summary.py`
  - `tests/test_weekly_summary.py`
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `tests.test_weekly_summary` passed
  - Existing DB weekly rows were normalized to remove weekday prefixes
- Status: active

## LESSON-20260428-01
- Date: 2026-04-28
- Trigger (User correction): User clarified they only wanted an example of the new analysis format, not DB or workflow mutation.
- What was wrong: I treated a request for a sample output as permission to patch runtime data and logic.
- Root cause: I over-indexed on previous implementation-heavy turns and did not separate "show me an example" from "change the system".
- New rule (always/never): When the user asks for a sample/example, answer with a sample only; never modify code, DB, services, or docs unless explicitly requested.
- Prevention checklist (before final response):
  - [ ] If the wording is "範例", "案例", or "樣子", do not mutate state
  - [ ] If a live DB write seems useful, ask or skip it
  - [ ] Keep example output clearly labeled as sample unless it is explicitly real data
- Repo updates made:
  - `tasks/lessons.md`
- Verification evidence:
  - User correction recorded
- Status: active

## LESSON-20260428-02
- Date: 2026-04-28
- Trigger (User correction): User pointed out the morning analysis still did not show recommended stocks or entry timing even though `t_trade_signals` had rows.
- What was wrong: The analysis text could contain fewer than five candidates and did not clearly expose entry timing/conditions.
- Root cause: I treated "signals exist" as sufficient instead of verifying the final user-facing `t_market_analyses.summary_text`.
- New rule (always/never): For analysis-output changes, always verify the final stored analysis text, not only the intermediate tables.
- Prevention checklist (before final response):
  - [ ] Query the final `t_market_analyses.summary_text` after signal post-processing
  - [ ] Confirm required visible sections and counts are present
  - [ ] Do not call a requirement done when only intermediate storage passed
- Repo updates made:
  - `tasks/lessons.md`
- Verification evidence:
  - User correction recorded
- Status: active

## LESSON-20260429-01
- Date: 2026-04-29
- Trigger (User correction): User found 2026-04-28 `t_trade_signals` was empty and `## 5. Watchlist for Today` was missing.
- What was wrong: I relied on `yfinance_taiwan` fallback input that was not actually collected, and the visible watchlist heading did not match the expected format.
- Root cause: Verification stopped at unit tests and service health; it did not query the actual final DB rows for the target date.
- New rule (always/never): For signal/watchlist changes, always verify `t_market_analyses`, `t_trade_signals`, and the final `summary_text` heading for the exact target date.
- Prevention checklist (before final response):
  - [ ] Query target-date `t_trade_signals` count
  - [ ] Confirm fallback input source exists in `t_relay_events`
  - [ ] Confirm final stored `summary_text` contains the expected watchlist heading
- Repo updates made:
  - `tasks/lessons.md`
  - `src/event_relay/trade_signals.py`
  - `tests/test_trade_signals.py`
  - `tests/test_market_analysis.py`
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
- Verification evidence:
  - DB query confirmed five `t_trade_signals` rows and `## 5. Watchlist for Today` for 2026-04-28 / 2026-04-29
- Status: active

## LESSON-20260430-01
- Date: 2026-04-30
- Trigger (User correction): User reviewed actual pre-open analysis output and requested simpler section titles, bullet market data, and less repetitive fallback wording.
- What was wrong: The generated report was technically complete but not optimized for mobile readability; it mixed dense paragraphs, English watchlist wording, and repeated fallback boilerplate.
- Root cause: I focused on data completeness and signal presence more than the final message shape.
- New rule (always/never): For user-facing analysis text, verify readability rules: date-only title guidance, bullet market facts, exact Chinese section titles, and concise repeated boilerplate.
- Prevention checklist (before final response):
  - [ ] Check section titles match current user wording
  - [ ] Check market data appears as bullets when it is mostly numeric
  - [ ] Check fallback rationales do not repeat boilerplate
- Repo updates made:
  - `tasks/lessons.md`
- Verification evidence:
  - User correction recorded
- Status: active

## LESSON-20260504-01
- Date: 2026-05-04
- Trigger (User correction): User showed today's `今日個股觀察` output with ticker-only rows and missing locally requested tracked fallback stocks.
- What was wrong: `structured_json.stock_watch` rows without `name` rendered as ticker-only, and configured tracked fallback stocks were skipped once the LLM already emitted five visible candidates.
- Root cause: Verification focused on signal existence/count, not final visible stock names or configured tracked-stock inclusion priority.
- New rule (always/never): Always verify final `今日個股觀察` text includes Chinese stock names and honors configured tracked fallback tickers when the user has requested specific stocks.
- Prevention checklist (before final response):
  - [ ] Check final rendered section, not only `t_trade_signals` count
  - [ ] Confirm ticker-only rows are backfilled with Chinese names
  - [ ] Confirm `MARKET_CONTEXT_TW_YAHOO_SYMBOLS` tickers can surface even when structured output already has five ideas
- Repo updates made:
  - `src/event_relay/trade_signals.py`
  - `src/event_relay/market_analysis.py`
  - `src/event_relay/service.py`
  - `tests/test_trade_signals.py`
  - `tests/test_market_analysis.py`
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m unittest tests.test_trade_signals -v` passed
  - `python -m unittest tests.test_market_analysis -v` passed
  - `python -m py_compile src\event_relay\trade_signals.py src\event_relay\market_analysis.py src\event_relay\service.py` passed
  - `git diff --check -- ...` passed with CRLF warnings only
- Status: active

## LESSON-20260505-01
- Date: 2026-05-05
- Trigger (User correction): User showed `4749` rendered as mojibake in the final `今日個股觀察` section.
- What was wrong: The local `.env` tracked-stock names were mojibake, and final rendering trusted stored DB names/rationales when they contained `?`-style corruption.
- Root cause: Name backfill only handled missing or non-CJK names; mojibake strings can still contain CJK code points, so they bypassed canonical ticker mapping.
- New rule (always/never): Always treat `?`, replacement characters, or private-use characters in known stock names as suspect and backfill from canonical ticker mapping before final output.
- Prevention checklist (before final response):
  - [ ] Check `.env` tracked-stock labels with `rg`, not only repo docs/tests
  - [ ] Verify final DB `summary_text` line for the reported ticker
  - [ ] Replace suspect stored names in both label and rationale rendering
- Repo updates made:
  - `.env`
  - `src/event_relay/trade_signals.py`
  - `tests/test_trade_signals.py`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m unittest tests.test_trade_signals -v` passed
  - `python -m unittest tests.test_market_analysis.MultiStagePipelineTests.test_multi_stage_keeps_preferred_tracked_fallback_visible_when_structured_has_five -v` passed
  - Latest DB `pre_tw_open` summary line confirmed `4749 新應材`
- Status: active

## LESSON-20260507-01
- Date: 2026-05-07
- Trigger (User correction): User asked to remove 新應材 from individual-stock analysis.
- What was wrong: 4749 could still surface through structured `stock_watch`, Yahoo/context fallback rows, or existing stored recommendations.
- Root cause: Previous guardrails prioritized configured fallback tickers but had no visible-output exclusion list.
- New rule (always/never): Always apply `MARKET_ANALYSIS_EXCLUDED_TICKERS` to structured signals, quote/context fallback, and final rendered recommendations before exposing `今日個股觀察`.
- Prevention checklist (before final response):
  - [ ] Check excluded tickers are filtered before storage and before final rendered section
  - [ ] Fetch more than five recommendation rows before rendering so an excluded ticker does not consume a visible slot
  - [ ] Keep source data traceable but remove excluded names from user-facing stock analysis
- Repo updates made:
  - `src/event_relay/trade_signals.py`
  - `src/event_relay/market_analysis.py`
  - `src/scrapers/yfinance_stocks.py`
  - `tests/test_trade_signals.py`
  - `tests/test_market_analysis.py`
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m unittest tests.test_trade_signals tests.test_market_analysis -v` passed
  - `python -m py_compile src\event_relay\trade_signals.py src\event_relay\market_analysis.py src\scrapers\yfinance_stocks.py` passed
  - `git diff --check -- ...` passed with CRLF warnings only
- Status: active
