# Engineering Workflows

## Workflow Orchestration (Default)
1. Plan first for non-trivial work
- If task has 3+ steps or architecture impact, start from `tasks/todo.md`.
- Write concrete checkable items before implementation.
2. Re-plan when things go sideways
- Stop when assumptions fail or repeated errors happen.
- Update plan and continue only after scope/approach is clear.
3. Verify before done
- Do not close task without evidence from tests/logs/runtime checks.
- Capture verification notes in `tasks/todo.md`.
4. Capture lessons after correction
- After user correction, append one entry to `tasks/lessons.md`.
- Add a prevention checklist that is specific and testable.

## Parallel Execution Strategy
1. Keep the main thread clean
- Offload independent checks/reads/tests in parallel when possible.
2. One sub-task per execution thread
- Avoid mixing unrelated concerns in one run.
3. Merge results into one concrete decision
- Record conclusions in `tasks/todo.md` progress notes.

## Self-Improvement Loop
1. After any user correction:
- add a lesson entry to `tasks/lessons.md`
2. Convert lesson into a rule:
- update `AGENTS.md` or `memory-bank/rules.md` when needed
3. Add prevention checks:
- use explicit pre-response checklist items
4. Revisit active lessons at task start:
- read `tasks/lessons.md` before major implementation

## Verification Before Done
1. Never mark done without proof
- tests, runtime output, or logs
2. Compare expected vs actual behavior
- especially when changing parsing, dedupe, or source mapping
3. Ask final quality question
- "Would a senior engineer approve this as production-safe?"

## Workflow 0A: Machine Restart Recovery
Use this first when Windows/the machine was rebooted, live collectors stopped,
or the user asks whether society/politics news, finance RSS, market context, or
Taiwan pre-open analysis ran after restart.

Primary runbook:
- `memory-bank/restart-recovery-runbook.md`

Minimum evidence before reporting recovery complete:
- `event_relay.main`, `news_collector.relay_bridge`, and `news_platform.main --loop` are running
- `http://127.0.0.1:18090/healthz` returns `{"ok": true}`
- source bridge log shows recent `Polling source=rss fetched=<n>`
- if enabled, X has current backfill/stream evidence or a current health row
- if enabled, Truth Social has `Polling source=truthsocial` evidence or a current health row
- `news_platform` log shows a recent crawl/keyword/topic cycle
- DB checks show same-day society/politics rows in `news_platform.t_news_articles`
- DB checks show same-day finance RSS rows in `news_relay.t_relay_events`
- today's `pre_tw_open` or calendar-guarded `macro_daily` row exists in `t_market_analyses`

## Demand Elegance (Balanced)
1. For non-trivial changes:
- pause and choose the simplest robust solution
2. Avoid hacky local fixes if root-cause fix is clear
3. Skip over-engineering for trivial tasks

## Autonomous Bug Fixing
1. Reproduce first, then fix
2. Use failing evidence (errors/tests/logs) as entry point
3. Resolve without unnecessary user hand-holding when context is sufficient
4. Re-run relevant verification after fix

## Task Management Contract
1. Plan first in `tasks/todo.md`
2. Keep progress notes updated while executing
3. Mark checklist items as completed only with evidence
4. Record final review summary (outcome, evidence, risks)
5. Capture corrections in `tasks/lessons.md`

## Core Principles
- Simplicity first: minimal necessary changes
- No laziness: fix root causes over temporary patches
- Minimal impact: avoid touching unrelated code
- Evidence-driven completion: verify before closing

## Workflow 1: Add a New News Source
1. Define source contract
- auth type, endpoint, rate limits, fields, pagination
2. Implement adapter in `src/news_collector/sources/`
- convert to `NewsItem` normalized schema
3. Add source registration in `collector.py`
4. Update environment settings in:
- `.env.example`
- `config.py`
5. Add non-network unit tests (parsing/config behavior)
6. Update docs:
- `README.md`
- `memory-bank/PROJECT_DOCUMENTATION.md`

## Workflow 2: Fix Ingestion Bug
1. Reproduce issue with concrete CLI command
2. Identify root cause (timestamp parse, schema mismatch, network failure, dedupe key)
3. Apply minimal safe fix
4. Add regression test
5. Verify:
- run `python -m unittest discover -s tests -p "test_*.py"`
- run fetch command for impacted source
6. Document behavior change if external output changed

## Workflow 3: Prepare Release Baseline
1. Ensure CI passes (`build-test` workflow)
2. Validate required env vars and secret naming
3. Smoke check local commands:
- rss fetch
- x fetch
4. Confirm docs are aligned with behavior

## Workflow 3A: RSS Feed Coverage Check
1. Confirm active feeds
- Inspect `OFFICIAL_RSS_FEEDS` in `.env`
- Taiwan finance/official feed additions currently include CNA finance, LTN business, ETtoday finance, Anue, Economic Daily News, Newtalk finance, Storm finance, MoneyDJ, CBC, TWSE, and FSC RSS URLs
2. Understand fetch limits
- `news_collector.sources.rss.OfficialRssSource` applies `--limit` per feed, not globally
- Current `.env` has `OFFICIAL_RSS_FIRST_PER_FEED=true`, so the bridge fetches one item per configured feed
- If `OFFICIAL_RSS_FIRST_PER_FEED=false`, 27 feeds with `--limit 5` can produce up to 135 RSS items before URL dedupe and bridge filters
3. Smoke fetch
- Run `python -m news_collector.main fetch --source rss --limit 5 --pretty`
4. Verify storage path
- Restart `news_collector.relay_bridge` after `.env` source-list changes so the running process sees the new feed set
- Check bridge log for `Polling source=rss fetched=<count>`
- Query `t_relay_events` for recent RSS source rows

## Workflow 3A-0: Finance Relay Reporter Enrichment
1. Understand storage scope
- Finance RSS rows live in short-retention `t_relay_events`, not `t_news_articles`.
- Reporter names for finance cards are display metadata in `raw_json.authors`; they are not normalized reporter identities yet.
2. Dry-run a small batch
- `python scripts/backfill_relay_event_authors.py --env-file .env --limit 10 --dry-run`
3. Backfill recent rows
- `python scripts/backfill_relay_event_authors.py --env-file .env --limit 200 --days 14 --sleep-seconds 0.2`
4. Verify
- Check summary counters for `present`, `updated`, `no_author_metadata`, and `parse_failed`.
- Query recent `t_relay_events.raw_json` rows for `$.authors`.
- Refresh the public finance page; cards should show `記者 <name>` when author data exists.
5. Boundaries
- The script fetches article detail pages only to extract byline metadata.
- Do not use this workflow to store article body content.
- Do not treat missing bylines as fake `unknown` reporters.

## Workflow 3A-1: Free Palestine English Issue News
1. Smoke fetch without DB writes
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 5 -DryRun`
2. Check source contract
- Accepted rows must be likely English and match Palestine/Gaza/West Bank issue terms
- Stored rows go to `t_palestine_news_items` with `source_id=<source_id>`, `topic=free_palestine`, and `language=en`
3. Store a controlled batch
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 20`
4. Register recurring local crawl
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_market_analysis_tasks.ps1 -Force`
- This registers `NewsCollector-PalestineNews` at 06:10 local/Taiwan time with a 3-hour repetition interval.
5. Backfill legacy relay rows only when migrating old data
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -BackfillRelay -BackfillOnly`
6. Verify downstream reads
- Query `t_palestine_news_items` for `topic='free_palestine' AND language='en'`
- Smoke `news-platform-api` endpoint `GET /api/timeline/news?page=1&pageSize=5`
- Confirm `/timeline` table shows the English-news column without adding these sources to the finance feed

## Workflow 3A-2: Four-Hour Codex News Digest
Use this when refreshing the short-lived cross-section digest shown by
`news-platform-api`.

Codex automation id: `four-hour-cross-section-news-digest`.

1. Collect context
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_four_hour_digest_context.ps1 -EnvFile .env -Hours 4 -OutFile runtime\four-hour-digest\context.json`
- Confirm `sourceCounts` includes finance, society, politics, celebrity, and
  Free Palestine keys.
2. Generate digest
- A Codex automation reads the context JSON and writes a concise Traditional
  Chinese digest following `spec/NEWS-9-four-hour-ai-news-digest.md`.
- Do not call paid OpenAI API from this repo.
- Repair mojibake or replacement characters before storage.
3. Store to Redis
- `powershell -ExecutionPolicy Bypass -File .\scripts\store_four_hour_digest_to_redis.ps1 -InputFile runtime\four-hour-digest\digest.json -TtlSeconds 15000`
- The store helper repairs obvious UTF-8/Latin-1 mojibake and rejects payloads
  that still contain replacement characters, private-use glyphs, or repeated
  question-mark blocks.
- It also rejects internal quality-control copy about encoding failures,
  unreliable identification, or intentionally omitting concrete details.
- New version writes must complete before deleting the old version key.
- Versioned keys expire after the TTL; `latest` and `current-key` do not expire,
  so the public homepage keeps the last successful digest between automation
  runs.
4. Verify API
- `GET http://localhost:8081/api/digest/four-hour`
- `available=true` when Redis has a valid digest; `available=false` is acceptable
  only when no digest is ready or Redis is unavailable.

## Workflow 3B: Taiwan Society/Politics News Topic Classification
1. Smoke check feeds without DB writes
- `$env:PYTHONPATH='src'; python -m news_platform.main --smoke`
- Politics only: `$env:PYTHONPATH='src'; python -m news_platform.main --smoke --categories politics`
2. Collect one batch into `t_news_articles`
- `$env:PYTHONPATH='src'; python -m news_platform.main --once`
- Politics only: `$env:PYTHONPATH='src'; python -m news_platform.main --once --categories politics`
3. Backfill keywords and topics
- `$env:PYTHONPATH='src'; python -m news_platform.main --extract-keywords --classify-topics`
4. Optional LLM fallback for category-specific general fallback rows
- Set `NEWSPF_TOPIC_LLM_ENABLED=true` for loop mode, or run manually:
- `$env:PYTHONPATH='src'; python -m news_platform.main --llm-topic-fallback`
5. Run continuous collection
- `$env:PYTHONPATH='src'; python -m news_platform.main --loop`
6. Reporter/byline enrichment in loop mode
- The loop runs `ArticleDetailAuthorWorker` after keyword/topic work when `NEWSPF_AUTHOR_DETAIL_BACKFILL_ENABLED=true` (default)
- Defaults: `NEWSPF_AUTHOR_DETAIL_BACKFILL_BATCH_SIZE=30`, `NEWSPF_AUTHOR_DETAIL_BACKFILL_SLEEP_SECONDS=0.05`, and sources `cna,storm,newtalk,ltn,ettoday,tvbs,ebc,ctee,pts`
- The loop only retries rows still in early missing states (`NULL`, `no_detail_fetched`, `parser_not_supported`); use `scripts/backfill_news_author_detail_pages.py --retry-failed` manually for parse failures or broad repair
7. Verify DB evidence
- Confirm recent rows have `keywords_json IS NOT NULL`
- Confirm classified rows have `topics_json IS NOT NULL`
- Confirm recent rows have `author_extraction_status IS NOT NULL`
- Check logs for `Author detail pass candidates=<n> present=<n> ... updated=<n>`
- Treat `topics_json[0].topic_id IN ('general_social_news','general_politics_news') AND topic_classified_by='rule'` as eligible for optional LLM refinement
- Treat category-specific general topics with `topic_classified_by='llm'` as processed by both layers but still general news
- Review `general_social_news` and `general_politics_news` rows when tuning `news_platform.topics`
8. After adding or tuning deterministic `TopicSpec` rules, reclassify existing rule-fallback rows for the affected category; `TopicWorker` only processes `topics_json IS NULL`, so old `general_social_news` / `general_politics_news` rows will not update unless explicitly re-run through `topic_classifier.classify` and written back only when a specific topic matches.
9. After changing worker/topic/author-detail code, restart any existing `news_platform.main --loop` process
- Verify the new loop log shows current source scope and, when new rows exist, `Topic pass scanned=<n>`
- Check live DB has `SUM(topics_json IS NULL)=0` for active categories after backfill

## Workflow 3C: Taiwan Official Public Records
1. Smoke check official public-record sources without DB writes
- `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources all`
- Budget/public-resource public records: `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources public_budget`
- Healthcare-only public records: `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources healthcare`
- Justice/corrections public records: `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources justice`
- Housing public records: `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources housing`
- Low-birthrate public records: `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources low_birthrate`
- Drug-abuse public records: `$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources drug_abuse`
- Date window override: add `--public-record-from YYYY-MM-DD --public-record-to YYYY-MM-DD`
2. Collect one batch into `t_public_records`
- `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources all`
- Budget/public-resource public records: `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources public_budget`
- Healthcare-only public records: `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources healthcare`
- Justice/corrections public records: `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources justice`
- Housing public records: `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources housing`
- Low-birthrate public records: `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources low_birthrate`
- Drug-abuse public records: `$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources drug_abuse`
- Use `--public-record-limit N` for controlled smoke writes
3. Link articles to public records
- `$env:PYTHONPATH='src'; python -m news_platform.main --link-public-records`
- Optional tuning: `--public-record-link-batch-size N`, `--public-record-link-lookback-days N`, `--public-record-link-min-confidence 0.68`
- In loop mode, public-record sources are collected once per local day, then `PublicRecordLinkWorker` runs after crawl, keyword, topic, and optional LLM passes
4. Storage boundary
- Structured official rows must go into `t_public_records`, not `t_news_articles`
- Related article links go through `t_news_article_public_record_links`
5. Verify DB evidence
- Query `t_public_records` by `source_id='ly' AND record_type='legislative_bill'`
- Query `t_public_records` by `source_id='npa' AND record_type IN ('fraud_rumor','traffic_accident_a1','traffic_accident_a2_stat','traffic_drunk_driving_stat','fraud_blocked_domain_stat','fraud_enforcement_stat')`
- Query healthcare public records by:
  - `source_id='ly' AND record_type='healthcare_legislative_bill'`
  - `source_id='nhi' AND record_type IN ('nhi_hospital_nursing_staff_stat','nhi_hospital_bed_occupancy_stat')`
  - `source_id='mohw' AND record_type IN ('mohw_hospital_workforce_stat','mohw_clinic_workforce_stat','mohw_hospital_bed_stat','mohw_nursing_staff_stat')`
- Query justice/corrections public records by:
  - `source_id='moj' AND record_type='moj_prosecution_disposition_stat'`
  - `source_id='mojac' AND record_type='mojac_daily_custody_stat'`
- Query housing public records by:
  - `source_id='taipei_open_data' AND record_type='taipei_housing_price_index'`
- Confirm `raw_json` keeps upstream API params and source fields
- Confirm `metrics_json` includes term/session fields and `cosignatory_count` for Legislative Yuan records, content length for NPA 165 records, casualty/party/geolocation fields for A1 traffic records, monthly/yearly aggregate count fields for NPA statistic records, nurse/staff/bed counts for healthcare capacity records, bed occupancy rates for NHI occupancy records, prosecution-disposition counts for MOJ records, and custody/capacity/over-capacity fields for corrections records
- Query `t_news_article_public_record_links` joined with article/record tables; inspect `confidence`, `matched_by`, and `evidence_json`

## Workflow 3D: News Data-Source Health Check
Use this when news analysis quality depends on fresh source rows, after a
machine restart, or when the user asks whether source data has caught up.

1. Run the combined read-only health report
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_data_source_health.ps1 -EnvFile .env`
- JSON output for automation: add `-Json`
- Scheduled gate options: add `-FailOnWarn` or `-FailOnStale`
2. Expected healthy probes
- relay finance/public RSS: recent Taiwan finance/official RSS rows in `news_relay.t_relay_events`
- relay international RSS: BBC/Reuters/Fox/NPR public RSS rows
- relay X/Truth Social/SEC/TWSE-MOPS/US-index probes when enabled in `.env`
- relay market-context, BLS macro, Taiwan market-flow, and stored analysis probes
- news platform society/politics category and per-source article probes
- news platform public records and article-public-record link probes
- process counts: exactly one root Python service instance for `event_relay.main`, `news_collector.relay_bridge`, and `news_platform.main --loop`
3. Interpret WARNs
- Public records use `updated_at` as refresh freshness because duplicate official records are upserted; WARN means last refresh is over 48 hours old, STALE means over 96 hours old.
- Duplicate `news_platform.main --loop` is WARN because it can double-fetch and hide restart mistakes.
- Event-driven SEC/TWSE-MOPS sources can be quiet; use the probe age and source cadence before calling it a source outage.
4. Remediation
- For stale finance/international RSS, inspect bridge logs and rerun Workflow 3A.
- For stale society/politics articles, inspect `news_platform` logs and rerun Workflow 3B.
- For stale public records, run Workflow 3C collection/link commands.
- For duplicate loops, stop only the extra `news_platform.main --loop` PID, then rerun the health report.

## Workflow 4: Incident Handling (Source Outage / Rate Limit)
1. Confirm outage scope (single source vs all)
2. Keep collector running for healthy sources
3. Surface explicit error records
4. If issue persists, apply short-term fallback:
- lower request frequency
- reduce query breadth
- temporary source disable switch
5. Record decision in `memory-bank/09-decisions/`

## Workflow 4A: X Stream Recovery / Gap Backfill
1. Confirm bridge startup state
- Check bridge log for `X token preflight: resolved`, `Starting X account stream`, and `X filtered stream connected`
2. Confirm whether the gap is pre-connect only
- Compare missing tweet timestamps against the latest bridge start/connect time
3. Let startup backfill replay recent tracked-account tweets
- Bridge runs one-shot X backfill before attaching the live filtered stream
- Backfill writes through the crawler bridge direct DB sink, so both `t_relay_events` and `t_x_posts` are updated without requiring the event relay API
4. Verify DB evidence
- Query `t_relay_events` by `event_id='x-<tweet_id>'`
- Query `t_x_posts` by `tweet_id`
5. If startup still says `missing X bearer token`
- run bridge through `scripts/run_source_bridge.ps1` so PowerShell preflight resolves DPAPI token into process env before Python starts

## Workflow 4A-1: Truth Social Public-Figure Polling
1. Confirm settings
- `TRUTH_SOCIAL_ENABLED=true`
- `TRUTH_SOCIAL_ACCOUNTS=https://truthsocial.com/@realDonaldTrump`
- Keep a browser-style `TRUTH_SOCIAL_USER_AGENT` if the public endpoint returns `403`
2. Smoke fetch without DB writes
- `$env:PYTHONPATH='src'; python -m news_collector.main fetch --source truthsocial --limit 5 --pretty`
3. Verify bridge storage
- Restart or wait for `news_collector.relay_bridge` poll loop
- Check bridge log for `Polling source=truthsocial fetched=<n>`
- Query `t_relay_events` by `source LIKE 'truthsocial:%'`
- Query `t_x_posts` by `tweet_id LIKE 'truthsocial-%'`
4. Public read path
- `news-platform-api` exposes these rows through `GET /api/celebrity-events`
- Omit `handle` to read both `x:*` and `truthsocial:*`, or pass `handle=truthsocial:realdonaldtrump`

## Workflow 4B: US Index Stored-Only Event Flow
1. Write normalized stored-only events
- Let the crawler bridge write DJIA / S&P 500 open-close snapshots directly to MySQL
2. Attach structured market payload
- Include trade date, session (`open`/`close`), and per-index quote fields in `market_snapshot`
3. Persist through the bridge DB sink
- The bridge writes the queue row into `t_relay_events` and snapshot rows into `t_market_index_snapshots`
4. Suppress user delivery
- Event storage marks `source=us_index_tracker` as `stored_only_market`
- Java owns user-facing LINE delivery; Python keeps the data stored for analysis
5. Verify
- Confirm the bridge logs `[US_INDEX_OPEN_STORED]` or `[US_INDEX_CLOSE_STORED]`
- Query both `t_relay_events` and `t_market_index_snapshots` by `event_id`

## Workflow 4C: Scheduled Market Analysis Storage
1. Keep source inputs current
- Ensure RSS, X, and US index tracker are writing to `t_relay_events` / `t_market_index_snapshots`
- Run `scripts/run_rag_indexer.ps1` before the first daily analysis window when refreshing historical-case examples
- Run `scripts/run_bls_macro.ps1` before the U.S. close analysis window when refreshing official U.S. macro facts
- Run `scripts/run_market_context.ps1` before the Taiwan pre-open analysis window so `market_context:*` event facts are fresh
- Run `scripts/run_tw_market_flow.ps1` and `scripts/run_tw_close_context.ps1` before the Taiwan close analysis window
2. Run the single-shot analysis generator
- Use `scripts/run_market_analysis.ps1 -Slot us_close` at `05:00`
- Use `scripts/run_market_analysis.ps1 -Slot pre_tw_open` at `07:30`
- Use `scripts/run_market_analysis.ps1 -Slot tw_close` at `15:30`
- Treat `t_relay_events` as primary local evidence, not exhaustive truth
- `MARKET_ANALYSIS_<SLOT>_PIPELINE` overrides the global `MARKET_ANALYSIS_PIPELINE`; current cost-aware default is `MARKET_ANALYSIS_US_CLOSE_PIPELINE=digest` and `MARKET_ANALYSIS_PRE_TW_OPEN_PIPELINE=multi_stage`
- `us_close` digest mode is upstream context only: one compact call, smaller prompt context, no trading-candidate append in visible text
- `pre_tw_open` is the main trade-decision brief. Target design: Codex generates dynamic Taiwan intraday / short-swing candidates from relay events, market context, quote evidence, historical/RAG context, and model judgment.
- If `MARKET_ANALYSIS_MODEL_ROUTER_ENABLED=true`, OpenAI is the default primary and Claude is fallback; configure budgets/Admin API keys before relying on provider fallback, and inspect `raw_json.model_router` to confirm the selected route
- When the selected provider is Anthropic, compact context mode is applied by default to reduce rate-limit risk; inspect `raw_json.provider_context_policy` for event/RAG/market-row reductions
- Market analysis builds a quota-managed context pack before RAG/prompting; `market_context:scorecard`, market-context rows, and important official data must remain selected even when general news volume is high
- Stage0 selects 1-2 deterministic core tensions before LLM stages; later stage prompts should answer those tensions directly
- Stage2 transmission may receive hybrid retrieved historical examples from `t_event_embeddings` / `t_analysis_embeddings`; these are analogues only, not current evidence IDs
- OpenAI runs request web search by default; if unavailable, the prompt must lower confidence and describe observation limits in reader-facing language instead of fabricating
3. Persist analysis output
- Generated text is upserted into `t_market_analyses` by `(analysis_date, analysis_slot)`
- `push_enabled` means Java delivery eligibility, not Python push execution
- Daily delivery policy starts from `pre_tw_open=1`, `macro_daily=1`, `us_close=1` only when TW is closed and the relevant U.S. close session was open, `tw_close=0`; `raw_json.trust_gate` may force final `push_enabled=0`
- If `claim_verifier.ok=false`, `market-analysis-trust-gate-v1` stores the row for audit/debug but blocks Java delivery eligibility and skips trade-signal extraction
- `claim-verifier-v2` ignores internal parenthesized evidence/source ID lists such as `（128610,128539）`; Stage4 must keep internal IDs out of visible `summary_text` and leave evidence links in telemetry/structured fields
- For dynamic candidate slots, `claim_verifier` must verify ticker references against local evidence or explicit candidate telemetry. Unsupported numbers, dates, and unrelated tickers must still block delivery.
- `us_close` remains stored as a digest/analysis and is injected into the next Taiwan pre-open analysis context only when the relevant U.S. session was open; if U.S. was closed, the pre-open prompt has no `us_close` context
- Target design: dynamic `structured_json.stock_watch` rows are extracted into `t_trade_signals`.
- Current implementation gap: code still contains fixed-pool paths. Do not claim dynamic candidates are live until those code paths are migrated and tested.
- New signals use `status=pending_review`; stale pending signals for the same analysis are marked `superseded`
- `ticker` is normalized symbol text; Taiwan signals use 4-digit codes without `.TW` / `.TWO`
- Daily visible reports no longer append `## 今日個股觀察`; `t_trade_signals` may still be maintained as machine-readable downstream context, but it is not rendered into the market-analysis body.
- If today's structured/quote context misses a ticker, the pipeline may copy only same-ticker recent `t_trade_signals` as `prior_signal_stock_watch` for downstream signal context. Treat it as stale reference only: keep `confidence=low`, show the prior date, and require same-day price, volume, and news confirmation.
- Daily formatting uses date-only `raw_json.display_title` and the author-style flow `今日主命題` -> `三個證據` -> `市場正在定價什麼` -> `台股傳導` -> `反證條件` -> `風險與觀察限制`; `三個證據` must contain exactly three bullets connecting source fact -> market mechanism -> why it matters now. Do not write a dedicated `台股配置` section.
- Individual company mentions in daily visible reports are limited to macro/sector transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭; do not write entry, stop-loss, or target-price language in the daily body.
- In that section, `direction=long` is rendered as `可做/建議觀察` plus the strategy label; `entry_zone` means entry area, `take_profit_zone` means profit-taking/exit area, and `invalidation` is rendered as `停損`
- Do not create orders here. Risk gate / review and outcomes stay in `t_signal_reviews` and `t_signal_outcomes`
- For existing structured rows, run `scripts/run_trade_signal_extraction.ps1 -EnvFile .env`
- For a specific analysis row that exists but has no monitor signals, run targeted repair: `scripts/run_trade_signal_extraction.ps1 -EnvFile .env -AnalysisId <id> -FixedPoolFallback -EventDays 1 -PriorDays 30`. This may use recent quote/context events and prior same-ticker signal references, but it still honors `raw_json.trust_gate.signals_allowed=false`.
- Strategy performance must use entry-first attribution: ignore `target_hit` / `stop_hit` before the first `entry_hit`; after entry, the first `target_hit` is a win and the first `stop_hit` is a loss. Rows without entry are `not_entered` and must not inflate win rate.
4. Keep Python storage-only
- `market_analysis` does not push directly or create delivery jobs
- Java owns user-facing delivery
5. Verify
- Check prompt snapshots under `runtime/prompts/`
- Query `t_market_analyses` for the current `analysis_date`
- Query `t_trade_signals` by `analysis_id` or `(analysis_date, analysis_slot)`
- Query `t_relay_events` for recent `source LIKE 'market_context:%'`
- Inspect `t_market_analyses.raw_json.context_pack` for selected counts and guaranteed bucket status
- Inspect `t_market_analyses.raw_json.model_router`, `raw_json.provider_context_policy`, `raw_json.pipeline_stages.core_tensions`, `raw_json.rag`, and `raw_json.claim_verifier`
- Confirm rows exist as event/context facts only; Python does not contact LINE or create delivery jobs

### Workflow 4C-G: Codex Market-Analysis Guard Automations

Codex guard automations run after the market-analysis windows. They are agent
jobs that can repair a failed row or create the missing prose row from local
evidence when scheduled Python LLM prose generation is disabled.

Configured Codex automations:
- `market-analysis-codex-guard-us-close`: runs after the 05:00 `us_close` window.
- `market-analysis-codex-guard-pre-open`: runs after the 07:30 `pre_tw_open` window.
- `market-analysis-codex-guard-tw-close`: runs after the 15:30 `tw_close` window.

Current cost-control schedule policy:
- Keep data collection, context, and preprocessing tasks enabled:
  `NewsCollector-RagIndexer`, `NewsCollector-BlsMacro`,
  `NewsCollector-MarketContext-PreTwOpen`, `NewsCollector-TwMarketFlow`,
  `NewsCollector-TwCloseContext`, and retention cleanup.
- Disable scheduled LLM prose-generation tasks:
  `NewsCollector-MarketAnalysis-UsClose`,
  `NewsCollector-MarketAnalysis-PreTwOpen`,
  `NewsCollector-MarketAnalysis-TwClose`, and
  `NewsCollector-WeeklySummary`.

Guard responsibilities:
- Inspect the matching `t_market_analyses` row and raw telemetry.
- If the row is healthy, do nothing.
- If the row is missing, quota-failed, schema-failed, or blocked by fixable
  `claim_verifier` token issues, repair it from local `t_relay_events`,
  market-context rows, repo skills/templates, and deterministic verification.
- Do not call OpenAI API, Anthropic API, or any paid external LLM API.
- Write repaired rows only through `MySqlEventStore.upsert_market_analysis`.
- Preserve Java delivery ownership: set `push_enabled` only according to
  existing slot/calendar/trust-gate policy and keep `pushed=false`.
- For repaired delivery/signal-eligible rows, rebuild internal
  monitor signals with `scripts/run_trade_signal_extraction.ps1 -AnalysisId
  <id> -FixedPoolFallback`.
- Verify final DB state: `claim_verifier.ok`, trust-gate reason,
  `push_enabled`, `pushed`, `structured_json`, and `t_trade_signals` count.
- Store telemetry indicating `external_provider_api_called=false` for repaired
  rows.

## Workflow 4L: Historical-Case RAG Indexing
1. Build the local RAG index
- Run `scripts/run_rag_indexer.ps1 -EnvFile .env`
- The indexer writes recent relay-event vectors into `t_event_embeddings`
- The indexer writes generated-analysis vectors into `t_analysis_embeddings`
2. Embedding model
- Default is `local-hash-v1`, a deterministic lexical embedding that needs no external API key
- Keep `RAG_EMBEDDING_MODEL` stable unless intentionally rebuilding the index
3. Use in market analysis
- `MARKET_ANALYSIS_RAG_ENABLED=true` lets `market_analysis` retrieve hybrid-ranked historical events and generated analyses
- Retrieved examples are inserted into `runtime/prompts/market_analysis_<slot>_stage2_transmission_user.txt`
- `raw_json.rag.score_components` records vector / metadata / outcome components for selected examples
- RAG failure must degrade to an empty example set and never block analysis
4. Verify
- Run `python -m unittest tests.test_rag tests.test_analysis_stages tests.test_market_analysis -v`
- Check `runtime/prompts/market_analysis_<slot>_stage2_transmission_user.txt` for `Historical retrieved examples JSON`
- Inspect `t_market_analyses.raw_json.rag` for `examples_count` or an `error`

## Workflow 4D: Weekly Summary Storage
1. Schedule for Taiwan pre-open usage
- Run `weekly_summary` every Saturday `23:00` local time (Java pushes it at Sunday `05:10`)
2. Generate the weekly brief
- Read the last 7 days from `t_relay_events`
- Call OpenAI Responses API with weekly summary prompts and web search enabled by default for current-fact verification
- If local events or web verification are insufficient, lower confidence and describe observation limits in reader-facing language; do not surface internal missing-data notes
3. Store for downstream delivery
- Upsert into `t_market_analyses`
- Java owns user-facing LINE delivery
4. Mark the row as weekly scope
- Use `analysis_date=YYYY-MM-DD` for the target Sunday delivery date
- Use `analysis_slot=weekly_tw_preopen`
- Use `scheduled_time_local=05:10`; do not include weekday text in this column
- Put `dimension=weekly` in `raw_json`
5. Verify
- Check scheduled task next run
- Query `t_market_analyses` by the target Sunday `analysis_date`
6. Manual backfill
- Call the running relay service:
  `'{"kind":"weekly","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"`
- The call is synchronous and may wait for the LLM response.

## Workflow 4D-1: Manual Analysis Backfill API
1. Ensure relay service is running
- `GET /healthz` should return `{"ok": true}`
2. Backfill daily market analysis
- `'{"kind":"market","slot":"pre_tw_open","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"`
- Allowed slots: `auto`, `us_close`, `pre_tw_open`, `tw_close`, `macro_daily`
3. Backfill weekly analysis
- `'{"kind":"weekly","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"`
4. Verify storage
- Query `t_market_analyses` by `analysis_slot`
- Weekly uses `analysis_slot=weekly_tw_preopen`
- Target design: daily market analysis extracts dynamic trade candidates to `t_trade_signals`; current code still needs fixed-pool migration.

## Workflow 4E: SEC Tracked Filings Flow
1. Define tracked universe
- Set `SEC_TRACKED_TICKERS` to the companies you care about
2. Respect SEC access rules
- Use declared `SEC_USER_AGENT`
- Keep polling modest; current bridge cadence is already conservative
3. Resolve ticker to CIK
- Fetch official SEC ticker mapping from `company_tickers.json`
4. Pull recent filings
- Query `data.sec.gov/submissions/CIK##########.json`
- Filter to `SEC_ALLOWED_FORMS`
5. Write normalized events
- Build filing index URL under `sec.gov/Archives/edgar/data/...`
- Let the crawler bridge direct DB sink write the event
6. Verify
- Run `python -m news_collector.main fetch --source sec --limit 10 --pretty`
- Confirm `source=sec:<TICKER>` rows enter `t_relay_events`

## Workflow 4F: TWSE / MOPS Major Announcements Flow
1. Define tracked universe
- Set `TWSE_MOPS_TRACKED_CODES` to the listed companies you care about
2. Pull official announcement feed
- Query TWSE openapi dataset `t187ap04_L` (`上市公司每日重大訊息`)
3. Filter and normalize
- Keep only tracked company codes
- Convert ROC date/time into timezone-aware timestamps
4. Write normalized events
- Let the crawler bridge direct DB sink write rows with `source=twse_mops:<CODE>`
5. Verify
- Run `python -m news_collector.main fetch --source twse --limit 10 --pretty`
- Confirm `source=twse_mops:<CODE>` rows enter `t_relay_events`
- If the default tracked list has no same-day disclosures, temporarily override `TWSE_MOPS_TRACKED_CODES` with codes that appear in the current official feed for a controlled smoke test

## Workflow 4G: MySQL Retention Cleanup
1. Keep the retention window explicit
- Default `RELAY_RETENTION_KEEP_DAYS=7`
- Keep `RELAY_RETENTION_ENABLED=true` unless investigating a cleanup issue
2. Use the shared cleanup path
- Relay dispatch runs cleanup once per local day
- `scripts/run_retention_cleanup.ps1` runs the same cleanup on demand
3. Register a fixed daily window
- Use `scripts/register_retention_cleanup_task.ps1 -At "00:10" -Force`
4. Verify
- Query `t_relay_events` and `t_x_posts` for rows older than 7 days before and after cleanup
- Confirm task `NewsCollector-RetentionCleanup` has a valid `NextRunTime`

## Workflow 4H: Pre-open Market Context Pack
1. Collect market/macro context
- Run `scripts/run_market_context.ps1 -EnvFile .env`
2. Source families
- Yahoo chart snapshots: NASDAQ Composite, NASDAQ 100, SOX, VIX, DXY, WTI, Gold, and key semiconductor ADR/stocks
- U.S. Treasury official daily yield curve XML: 2Y, 10Y, 30Y, and 10Y-2Y spread
- FRED public CSV: Fed path, liquidity, financial conditions, credit stress, and VIX close
- Market breadth: `RSP-SPY`, `QQEW-QQQ`, and `IWM-SPY` relative return spreads
- SEC companyfacts AI capex proxy: default `MSFT,GOOGL,META,AMZN`; requires `SEC_USER_AGENT`
- FRED oil context: WTI, Brent, and Brent-WTI spread; optional EIA inventory context for U.S. crude stocks excluding SPR when `EIA_API_KEY` is set
- Deterministic scorecard: `breadth_health`, `ai_capex_quality`, `energy_shock_risk`, `credit_stress`, and `liquidity_impulse` on a -2..+2 scale
- TWSE official OpenAPI: index groups, tracked stocks, and margin balances
- Taiwan Yahoo context from `MARKET_CONTEXT_TW_YAHOO_SYMBOLS` is currently a tracked evidence input. It historically mirrored the fixed pool and should be generalized during dynamic-candidate migration.
- Visible stock-analysis exclusions are controlled by `MARKET_ANALYSIS_EXCLUDED_TICKERS`; default excludes `4749` / 新應材
3. Persist as event-only facts
- Insert one stored-only event per context point into `t_relay_events`
- Insert one `market_context:scorecard` event when `MARKET_CONTEXT_SCORECARD_ENABLED=true`
- Add one `market_context:collector` summary event for point/failure counts
- Keep `raw_json.stored_only=true`, `raw_json.dimension=market_context`, and `raw_json.event_type` for traceability
4. Schedule before the AI brief
- Register through `scripts/register_market_analysis_tasks.ps1`; default is `07:20`, before `pre_tw_open` at `07:30`
5. Verify
- Query `t_relay_events` for today's `source LIKE 'market_context:%'`
- Confirm rows are marked `stored_only_context` / stored-only and inspect `raw_json.failures` on the collector event
- Confirm sources include `market_context:scorecard`, `market_context:market_breadth`, `market_context:sec_companyfacts`, `market_context:fred_energy`, and optionally `market_context:eia` when the modules are enabled

## Workflow 4I: Taiwan Official Market-Flow Context
1. Collect official Taiwan flow datasets
- Run `scripts/run_tw_market_flow.ps1 -EnvFile .env`
2. Source families
- TWSE official/RWD: `T86_ALLBUT0999`, `MI_MARGN`, `MI_QFIIS_cat`, `MI_QFIIS_sort_20`, and `SBL_TWT96U`
- TPEx OpenAPI: margin balance, margin/SBL short-sale balance, three-major-institution daily/summary, foreign investor trading, and dealer trading datasets
- TAIFEX OpenAPI: major institutional trader general, futures/options split, and futures contract detail datasets
3. Persist as event-only facts
- Insert one stored-only dataset event into `t_relay_events` for each collected dataset
- Use `source=market_context:twse_flow`, `source=market_context:tpex_flow`, or `source=market_context:taifex_flow`
- Keep `raw_json.stored_only=true`, `raw_json.dimension=market_context`, `raw_json.event_type=tw_market_flow_dataset`, `raw_json.trade_date`, `raw_json.dataset`, official rows, and normalized metrics
4. Verify
- Run `python -m unittest tests.test_tw_market_flow -v`
- Query `t_relay_events` by `source IN ('market_context:twse_flow','market_context:tpex_flow','market_context:taifex_flow')`

## Workflow 4J: BLS Macro Stored-Only Event Flow
1. Collect BLS official macro series
- Run `scripts/run_bls_macro.ps1 -EnvFile .env`
- Optionally set `BLS_API_KEY`; without it, the collector sends the same low-frequency JSON POST without `registrationkey`
2. Source families
- BLS Public Data API v2 endpoint: `https://api.bls.gov/publicAPI/v2/timeseries/data/`
- First batch: CPI headline/core, PPI headline/final demand/core, nonfarm payrolls, unemployment rate, labor force participation, average hourly earnings, and average weekly hours
3. Persist as event-only facts
- Insert one stored-only relay event per latest monthly observation into `t_relay_events`
- Use `source=market_context:bls_macro`
- Keep `raw_json.stored_only=true`, `raw_json.dimension=market_context`, `raw_json.event_type=market_context_point`, `raw_json.series_id`, `raw_json.year`, `raw_json.period`, `raw_json.value`, `raw_json.footnotes`, and normalized metrics
- Dedupe by event hash derived from `event_id`, where `event_id` includes `bls_macro`, `series_id`, `year`, and `period`
4. Verify
- Run `python -m unittest tests.test_bls_macro -v`
- Query `t_relay_events` by `source='market_context:bls_macro'`

## Workflow 4J-1: U.S. Macro Release Calendar
1. Collect official release dates
- Dry run:
  `powershell -ExecutionPolicy Bypass -File .\scripts\run_macro_calendar.ps1 -EnvFile .env -DryRun`
- Store rows:
  `powershell -ExecutionPolicy Bypass -File .\scripts\run_macro_calendar.ps1 -EnvFile .env`
2. Source families
- BLS annual release calendar for CPI, PPI, and Employment Situation / nonfarm payrolls
- U.S. Census Retail Trade release schedule for Advance Monthly Retail Trade / retail sales
- Nasdaq daily earnings calendar for configured heavyweight symbols; rows are stored as `indicator_code=earnings_<symbol>`
- Optional manual earnings JSON file for confirmed Taiwan local heavyweight dates or corrections to estimated earnings dates
3. Persist as long-lived calendar facts
- Write rows to `t_macro_release_calendar`
- Do not write these reminders to `t_relay_events`; release-calendar rows need to survive relay retention
- Do not write them to `t_market_analyses`; they are official schedule facts, not generated prose
- Earnings calendar dates from Nasdaq can be estimated; keep `raw_json.date_status` and prefer manual confirmed rows when the same symbol/period exists
4. Delivery boundary
- `line-relay-service` reads `reminder_date_taipei = today AND reminder_pushed = 0`
- Java sends one aggregated LINE reminder, grouping macro releases and heavyweight earnings, and updates `reminder_pushed` only after at least one target receives it
- Python does not contact LINE
5. Verify
- Run `python -m unittest tests.test_macro_calendar -v`
- Query `t_macro_release_calendar` for upcoming `release_at_taipei >= NOW()`
- Confirm `reminder_date_taipei` is the date before the Taiwan release date

## Workflow 4K: Taiwan Close Context and Analysis
1. Build close context from relay events
- Run `scripts/run_tw_market_flow.ps1 -EnvFile .env` after Taiwan close data is available
- Run `scripts/run_tw_close_context.ps1 -EnvFile .env` to aggregate same-day Taiwan flow/disclosure events into one `market_context:tw_close` stored-only event
2. Generate the close report
- Run `scripts/run_market_analysis.ps1 -Slot tw_close -Force`
- The analysis job reads `t_relay_events` and writes model output to `t_market_analyses`
3. Persist boundaries
- Source/context facts remain in `t_relay_events`
- `t_market_analyses.raw_json.dimension=daily_tw_close`
- Python does not push or create LINE delivery jobs
4. Verify
- Check `runtime/prompts/market_analysis_tw_close_*`
- Query `t_relay_events` for `source='market_context:tw_close'`
- Query `t_market_analyses` for `analysis_slot='tw_close'`

## Workflow 4L: Market Calendar Guard
1. Calendar source
- `src/event_relay/market_calendar.py` contains built-in 2026 TWSE / NYSE full-closure dates.
- The relevant U.S. close session date is Taiwan local date minus one day.
2. Routing rules
- Sunday: skip daily market analysis; weekly summary owns the day.
- TW closed + relevant U.S. session open: only `us_close` runs.
- Relevant U.S. session closed + TW open: only `pre_tw_open` / `tw_close` run, and `pre_tw_open` does not include stale `us_close`.
- TW and relevant U.S. session both closed: `pre_tw_open` writes `macro_daily` with `push_enabled=1`.
3. Verify
- Run `python -m unittest tests.test_market_calendar tests.test_market_analysis -v`
- Check `t_market_analyses.analysis_slot` for `macro_daily` on both-closed days.

## Workflow 5: Build a New Skill (Enterprise)
1. Create skill folder from templates:
- `skills/templates/SKILL_TEMPLATE.md`
- `skills/templates/EVALS_TEMPLATE.md`
- `skills/templates/CHANGELOG_TEMPLATE.md`
2. Register skill in `skills/registry.yaml`.
3. Define safety, failure handling, and eval thresholds.
4. Add regression cases for known incidents/lessons.
5. Run readiness validator:
- `python scripts/validate_readiness.py`
6. Update relevant docs and changelog before release.

## Workflow 6: Enterprise Readiness Review
1. Review baseline docs:
- `memory-bank/archive/enterprise/40-agent-enterprise-readiness.md`
- `memory-bank/archive/enterprise/42-agent-evals-and-release-gates.md`
- `memory-bank/archive/enterprise/43-agent-security-and-compliance.md`
- `memory-bank/archive/enterprise/44-mcp-server-governance.md`
2. Validate artifacts exist and are current.
3. Execute CI gates:
- `build-test`
- `readiness-gate`
4. Capture residual risks in `tasks/todo.md`.
