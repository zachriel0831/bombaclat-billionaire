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

## Workflow 0B: Codex Observer Telemetry
Use this when adding or auditing local scheduler entry scripts.

1. Emit job telemetry
- PowerShell run scripts should dot-source `scripts/codex_observer.ps1`.
- Wrap the real command with `Invoke-CodexObservedCommand`.
- Use categories: `crawler`, `analysis`, `article`, `rag`, `service`, or `maintenance`.
2. Emit Codex automation telemetry
- Codex automation runs should write `automation_started` at run start.
- Before final response, write `automation_succeeded` or `automation_failed`.
- Use `session_id=codex-automations`, `agent_name=codex-automation`, and safe metadata such as `source=codex_automation`, `job`, `status`, and `cwd`.
3. Preserve privacy and uptime
- The helper posts to `http://127.0.0.1:8765/events` by default.
- Set `CODEX_OBSERVER_URL` to change the target, `CODEX_OBSERVER_SESSION_ID` to group runs, or `CODEX_OBSERVER_DISABLED=true` to skip observer writes.
- Observer failures must not fail the data job.
- Do not send prompts, article bodies, secrets, tokens, API keys, `.env` values, or credentials in metadata.
4. Verify
- Check the Observer dashboard Recent Events table for Role and Meta values such as `job=cwa_weather`, `status=succeeded`, and `duration_seconds=<n>`.
- Expected event names are `<category>_started`, `<category>_succeeded`, and `<category>_failed`.

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
- Refresh the public finance page; cards should show `閮?<name>` when author data exists.
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

## Workflow 3A-2: International Homepage Headlines
Use this when the public site needs low-frequency English homepage/news-front
headlines for the International News view.

1. Smoke fetch without DB writes
- `$env:PYTHONPATH='src'; python -m news_collector.main fetch --source homepage --limit 5 --languages english --title-url-only --log-level INFO`
2. Store a controlled batch through the existing relay bridge filters
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_international_homepage_headlines.ps1 -EnvFile .env -Limit 3`
3. Register recurring local crawl
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_international_homepage_headlines_task.ps1 -Force -StartNow`
- This creates `NewsCollector-InternationalHomepageHeadlines` as an
  interactive-logon fixed window. It must not be a repeating popup-and-exit
  task.
4. Verify downstream reads
- Query `t_relay_events` for recent `source LIKE 'Homepage:%'`.
- Smoke `news-platform-api` endpoint `GET /api/events?region=INTL&page=1&pageSize=5`.
- Homepage pages normally do not expose reliable publish times; `published_at`
  is crawl time and `raw_json.raw.published_at_source` records that fallback.

## Workflow 3A-3: Four-Hour Codex News Digest
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
- Low-frequency supplements only: `$env:PYTHONPATH='src'; python -m news_platform.main --smoke --categories society,politics --source-ids tvbs,udn,setn`
2. Collect one batch into `t_news_articles`
- `$env:PYTHONPATH='src'; python -m news_platform.main --once`
- Politics only: `$env:PYTHONPATH='src'; python -m news_platform.main --once --categories politics`
- TVBS/UDN/SETN low-frequency run: `powershell -ExecutionPolicy Bypass -File .\scripts\run_news_platform_low_frequency_sources.ps1 -EnvFile .env -SourceIds "tvbs,udn,setn"`
3. Backfill keywords and topics
- `$env:PYTHONPATH='src'; python -m news_platform.main --extract-keywords --classify-topics`
4. Optional LLM fallback for category-specific general fallback rows
- Set `NEWSPF_TOPIC_LLM_ENABLED=true` for loop mode, or run manually:
- `$env:PYTHONPATH='src'; python -m news_platform.main --llm-topic-fallback`
5. Run continuous collection
- `$env:PYTHONPATH='src'; python -m news_platform.main --loop`
6. Reporter/byline enrichment in loop mode
- The loop runs `ArticleDetailAuthorWorker` after keyword/topic work when `NEWSPF_AUTHOR_DETAIL_BACKFILL_ENABLED=true` (default)
- Defaults: `NEWSPF_AUTHOR_DETAIL_BACKFILL_BATCH_SIZE=30`, `NEWSPF_AUTHOR_DETAIL_BACKFILL_SLEEP_SECONDS=0.05`, and sources `cna,storm,newtalk,ltn,ettoday,tvbs,udn,setn,ebc,ctee,pts`
- The loop only retries rows still in early missing states (`NULL`, `no_detail_fetched`, `parser_not_supported`); use `scripts/backfill_news_author_detail_pages.py --retry-failed` manually for parse failures or broad repair
7. Register low-frequency supplements when needed
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_news_platform_low_frequency_sources_task.ps1 -Force -StartNow`
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_international_homepage_headlines_task.ps1 -Force -StartNow`
- The main scheduler registration script also registers `NewsCollector-NewsPlatformLowFrequencySources` and `NewsCollector-InternationalHomepageHeadlines` as interactive-logon fixed windows. They must not be repeating popup-and-exit tasks.
- `scripts/register_market_analysis_tasks.ps1` registers data/context tasks only and unregisters the retired Python LLM prose tasks if they still exist.
- CTEE stays disabled until a public allowed endpoint returns usable data; do not bypass 403 protections.
8. Audit official-list coverage and compensate gaps
- Manual run: `powershell -ExecutionPolicy Bypass -File .\scripts\run_news_source_accuracy_audit.ps1 -EnvFile .env -Compensate -FailOnWarn`
- Register schedule: `powershell -ExecutionPolicy Bypass -File .\scripts\register_news_source_accuracy_audit_task.ps1 -Force`
- The scheduled task is `NewsCollector-NewsSourceAccuracyAudit`, every 2 hours by default. It should run with `-WindowStyle Hidden`; if a short PowerShell window flashes, inspect recent Task Scheduler `LastRunTime` and `Actions` first.
- Default audit scope is active sources plus TVBS/UDN/SETN; CTEE is skipped by default because local public endpoints return 403.
- Reports: `runtime/news-source-accuracy/latest.json` and `runtime/news-source-accuracy/latest.txt`
- Compensation runs a bounded crawl for low-coverage sources, then deterministic keyword/topic enrichment.
- If official-list coverage stays below `MinCoverage` after compensation, the task exits non-zero and Observer marks `news_source_accuracy_audit` failed.
9. Verify DB evidence
- Confirm recent rows have `keywords_json IS NOT NULL`
- Confirm classified rows have `topics_json IS NOT NULL`
- Confirm recent rows have `author_extraction_status IS NOT NULL`
- Check logs for `Author detail pass candidates=<n> present=<n> ... updated=<n>`
- Treat `topics_json[0].topic_id IN ('general_social_news','general_politics_news') AND topic_classified_by='rule'` as eligible for optional LLM refinement
- Treat category-specific general topics with `topic_classified_by='llm'` as processed by both layers but still general news
- Review `general_social_news` and `general_politics_news` rows when tuning `news_platform.topics`
10. After adding or tuning deterministic `TopicSpec` rules, reclassify existing rule-fallback rows for the affected category; `TopicWorker` only processes `topics_json IS NULL`, so old `general_social_news` / `general_politics_news` rows will not update unless explicitly re-run through `topic_classifier.classify` and written back only when a specific topic matches.
11. After changing worker/topic/author-detail code, restart any existing `news_platform.main --loop` process
- Verify the new loop log shows current source scope and, when new rows exist, `Topic pass scanned=<n>`
- Check live DB has `SUM(topics_json IS NULL)=0` for active categories after backfill

## Workflow 3B-1: Low-Frequency News Source Fixed Window
Use this when TVBS/UDN/SETN low-frequency society/politics collection should
stay in one visible PowerShell window instead of opening short-lived task
windows.

1. Verify the scheduler change without applying it
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_news_platform_low_frequency_sources_task.ps1 -PlanOnly`
2. Install and start the fixed window
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_news_platform_low_frequency_sources_task.ps1 -Force -StartNow`
- This replaces `NewsCollector-NewsPlatformLowFrequencySources` with an
  interactive-logon fixed window.
3. Verify
- `Get-ScheduledTask -TaskName NewsCollector-NewsPlatformLowFrequencySources | Select-Object TaskName,State`
- The fixed window title is `NewsCollector low-frequency news sources`.
- Read `runtime/status/news-platform-low-frequency-window-status.json` for the
  fixed-window PID, last exit code, next run, source ids, categories, and log.
- Daily fixed-window logs are written to
  `runtime/logs/news-platform-low-frequency-window-YYYYMMDD.log`.

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

## Workflow 3C-1: CWA Earthquake High-Frequency Collection
Use this when the weather page needs faster earthquake updates than the
combined CWA weather task.

1. Understand the sources
- `cwa_earthquake_report` reads CWA significant felt earthquakes
  (`E-A0015-001`) and small-area felt earthquakes (`E-A0016-001`) by default.
- CWA publishes these datasets irregularly; the local schedule controls polling
  frequency, not upstream publication frequency.
2. Smoke fetch without DB writes
- `$env:PYTHONPATH='src'; python -m news_platform.main --env-file .env --public-records-smoke --public-sources cwa_earthquake_report --public-record-limit 5`
3. Store a controlled batch
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_cwa_earthquake.ps1 -EnvFile .env -Limit 50`
4. Register high-frequency polling
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_cwa_earthquake_task.ps1 -Force`
- Default cadence is every 5 minutes; use `-EveryMinutes 1` only if operationally needed.
5. Verify
- `Get-ScheduledTask -TaskName NewsCollector-CwaEarthquake`
- `Get-ScheduledTaskInfo -TaskName NewsCollector-CwaEarthquake`
- Query recent `t_public_records` rows where `source_id='cwa'` and
  `record_type='cwa_earthquake_report'`; `raw_json.dataset_id` should include
  `E-A0015-001` or `E-A0016-001`.

## Workflow 3C-2: CWA Fixed Collector Window
Use this when CWA typhoon/earthquake scheduled polling should stay in one
visible PowerShell window instead of opening short-lived task windows.

1. Verify the scheduler change without applying it
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_cwa_fixed_window_task.ps1 -PlanOnly`
2. Install and start the fixed window
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_cwa_fixed_window_task.ps1 -StartNow`
- This disables the legacy popup tasks `NewsCollector-CwaWeather` and
  `NewsCollector-CwaEarthquake`, registers `NewsCollector-CwaFixedWindow` for
  the interactive logon user, and opens the visible window now.
3. Verify
- `Get-ScheduledTask -TaskName NewsCollector-CwaFixedWindow,NewsCollector-CwaWeather,NewsCollector-CwaEarthquake | Select-Object TaskName,State`
- The fixed window title is `NewsCollector CWA fixed window`.
- Read `runtime/status/cwa-fixed-window-status.json` for the latest fixed-window PID, last job, exit code, next weather run, next earthquake run, and current log file.
- Daily fixed-window logs are written to `runtime/logs/cwa-fixed-window-YYYYMMDD.log`.
- Weather/typhoon keeps the 30-minute cadence; earthquake keeps the 5-minute
  cadence. When both are due, the weather run wins because it already includes
  earthquake records, then the next earthquake-only poll is delayed 5 minutes.
4. Roll back to the old popup-style tasks only if explicitly needed
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_cwa_weather_task.ps1 -Force`
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_cwa_earthquake_task.ps1 -Force`

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
- news platform society/politics category probes plus active per-source article probes; category freshness stays strict, while per-source row freshness uses a wider window for naturally quiet feeds
- news platform public records and article-public-record link probes; link freshness only alerts when recent deterministic article/record candidate matches exist but link rows are not current
- process counts: exactly one root Python service instance for `event_relay.main`, `news_collector.relay_bridge`, and `news_platform.main --loop`
3. Interpret WARNs
- Public records use `updated_at` as refresh freshness because duplicate official records are upserted; WARN means last refresh is over 48 hours old, STALE means over 96 hours old.
- Article enrichment ignores newly fetched rows for 5 minutes and reports them as `pending_recent_*`; WARN means rows older than that grace window still lack `keywords_json` or `topics_json`.
- Duplicate `news_platform.main --loop` is WARN because it can double-fetch and hide restart mistakes.
- Event-driven SEC/TWSE-MOPS sources can be quiet; age-only row staleness is informational unless fetch logs or source-specific evidence show failures.
- U.S. index/snapshot and stored-analysis probes are market-calendar and due-time aware; weekend, holiday, and not-yet-due slots should be `SKIPPED`, not incidents.
4. Remediation
- For stale finance/international RSS, inspect bridge logs and rerun Workflow 3A.
- For stale society/politics articles, inspect `news_platform` logs and rerun Workflow 3B.
- For stale public records, run Workflow 3C collection/link commands.
- For duplicate loops, stop only the extra `news_platform.main --loop` PID, then rerun the health report.
- For empty worker wrapper windows, rerun `scripts/restart_live_services.ps1`; it closes stale `run_event_relay.ps1`, `run_source_bridge.ps1`, and `run_news_platform_loop.ps1` wrappers before starting the three fresh windows.

## Workflow 3D-1: Live Service Monitor Fixed Window
Use this when the live worker monitor should stay in one visible PowerShell
window instead of opening a short-lived task window every few minutes. The same
fixed window now also runs the service auto-repair watcher every cycle.

1. Verify the scheduler change without applying it
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_live_service_monitor_task.ps1 -PlanOnly`
2. Install and start the fixed window
- `powershell -ExecutionPolicy Bypass -File .\scripts\register_live_service_monitor_task.ps1 -StartNow`
- This replaces the old repeating popup-style `NewsCollector-LiveServiceMonitor`
  action with an interactive-logon fixed window.
3. Verify
- `Get-ScheduledTask -TaskName NewsCollector-LiveServiceMonitor | Select-Object TaskName,State`
- The fixed window title is `NewsCollector live service monitor`.
- Read `runtime/status/live-service-monitor-window-status.json` for the latest
  fixed-window PID, last job, live-monitor exit code, auto-repair exit code,
  next run, and current log file.
- Daily fixed-window logs are written to
  `runtime/logs/live-service-monitor-window-YYYYMMDD.log`.

4. Service auto-repair behavior
- Manual dry-run:
  `powershell -ExecutionPolicy Bypass -File .\scripts\run_service_auto_repair_watch.ps1 -EnvFile .env -DryRun`
- Active run:
  `powershell -ExecutionPolicy Bypass -File .\scripts\run_service_auto_repair_watch.ps1 -EnvFile .env -LaunchAgent`
- Warn/stale/missing/error probes across frontend, API, LINE relay, stock
  monitor, Redis, event relay, frontend ngrok, Observer, enabled
  `NewsCollector-*` tasks, data-source health, and the latest source-accuracy
  report write an incident to `runtime/service-auto-repair/incidents/`.
- The frontend liveness probe uses the dedicated Next.js `/health` endpoint,
  not the homepage route, so slow page rendering does not create false
  `news_display_frontend` missing incidents.
- When `-LaunchAgent` is set, the watcher starts a background `codex exec`
  repair agent from the incident prompt. It now launches from the repo root
  instead of the shared workspace root so default `git` and relative-path
  commands resolve inside the affected repository. Identical incident
  fingerprints are suppressed for 60 minutes by default.
- The incident prompt must keep Windows path-space safety explicit: use quoted
  paths or `-LiteralPath` for locations such as `C:\Users\Zack Ou\...`.
- Repair agents must not push, touch order-dispatcher/broker flows, send LINE or
  external messages, deploy production changes, run destructive data repair, or
  touch Liuli/Ollama/llama-server unless the user explicitly names those targets.

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
2. Generate prose through Codex automation
- Python LLM daily/weekly analysis scripts are retired and must not be used as a fallback.
- Codex local automations own `us_close`, `pre_tw_open`, `tw_close`, and `macro_daily` prose rows.
- Treat `t_relay_events` as primary local evidence, not exhaustive truth.
- `pre_tw_open` is the main market-decision brief. It must discuss macro/sector transmission, not stock recommendations.
- RAG examples from `t_event_embeddings` / `t_analysis_embeddings` are analogues only, not current evidence IDs.
3. Persist analysis output
- Generated text is upserted into `t_market_analyses` by `(analysis_date, analysis_slot)`
- `push_enabled` means Java delivery eligibility, not Python push execution
- Daily delivery policy starts from `pre_tw_open=1`, `macro_daily=1`, `us_close=1` only when TW is closed and the relevant U.S. close session was open, `tw_close=0`; `raw_json.trust_gate` may force final `push_enabled=0`
- If `claim_verifier.ok=false`, `market-analysis-trust-gate-v1` stores the row for audit/debug but blocks Java delivery eligibility
- `claim-verifier-v2` ignores internal parenthesized evidence/source ID lists; visible `summary_text` must keep internal IDs out and leave evidence links in telemetry/structured fields
- `claim_verifier` still verifies ticker references when the visible analysis mentions companies as macro/sector examples. Unsupported numbers, dates, and unrelated tickers must still block delivery.
- `us_close` remains stored as context only when the relevant U.S. session was open; if U.S. was closed, Codex must not use stale `us_close` context.
- Stock recommendation generation is retired. Visible reports must not output `stock_watch`, and Python must not write `t_trade_signals`.
- Daily formatting uses date-only `raw_json.display_title` and a flexible briefing-memo shape, not a fixed six-title template. Required visible content is opening thesis, evidence chain, Taiwan transmission, repricing/invalidation, and a reader-facing caveat only when useful. Evidence should use the strongest 2-4 facts available; bullets are optional and must not be forced to exactly three. Invalidation means thesis-invalidation evidence, not buy/sell triggers. Do not write a dedicated `台股配置` section or append `今日個股觀察`.
- Individual company mentions in daily visible reports are limited to macro/sector transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 蝢銝楊?? do not write stock recommendations, buy/watchlist candidates, entry, stop-loss, or target-price language in the daily body.
- Strategy performance must use entry-first attribution: ignore `target_hit` / `stop_hit` before the first `entry_hit`; after entry, the first `target_hit` is a win and the first `stop_hit` is a loss. Rows without entry are `not_entered` and must not inflate win rate.
4. Keep Python storage-only
- Python does not generate daily/weekly LLM prose, push directly, or create delivery jobs
- Java owns user-facing delivery
5. Verify
- Query `t_market_analyses` for the current `analysis_date`
- Query `t_relay_events` for recent `source LIKE 'market_context:%'`
- Inspect `t_market_analyses.raw_json.rag` and `raw_json.claim_verifier`
- Confirm rows exist as event/context facts only; Python does not contact LINE or create delivery jobs

### Workflow 4C-G: Codex Market-Analysis Guard Automations

Codex guard automations run after the market-analysis windows. They are agent
jobs that create or repair the prose row from local evidence. The old scheduled
Python LLM prose generators are retired and are not a fallback.

Configured Codex automations:
- `market-analysis-codex-guard-us-close`: runs after the 05:00 `us_close` window.
- `market-analysis-codex-guard-pre-open`: runs after the 07:30 `pre_tw_open` window.
- `market-analysis-codex-guard-tw-close`: runs after the 15:30 `tw_close` window.

Current cost-control schedule policy:
- Keep data collection, context, and preprocessing tasks enabled:
  `NewsCollector-RagIndexer`, `NewsCollector-BlsMacro`,
  `NewsCollector-MarketContext-PreTwOpen`, `NewsCollector-TwMarketFlow`,
  `NewsCollector-TwCloseContext`, and retention cleanup.
- Retired scheduled LLM prose-generation tasks must not exist:
  `NewsCollector-MarketAnalysis-UsClose`,
  `NewsCollector-MarketAnalysis-PreTwOpen`,
  `NewsCollector-MarketAnalysis-TwClose`, and
  `NewsCollector-WeeklySummary`.

Guard responsibilities:
- Inspect the matching `t_market_analyses` row and raw telemetry.
- If the row is healthy, do nothing.
- If the row is missing or blocked by fixable `claim_verifier` token issues,
  repair it from local `t_relay_events`,
  market-context rows, repo skills/templates, and deterministic verification.
- Do not call OpenAI API, Anthropic API, or any paid external LLM API.
- Write repaired rows only through `MySqlEventStore.upsert_market_analysis`.
- Preserve Java delivery ownership: set `push_enabled` only according to
  existing slot/calendar/trust-gate policy and keep `pushed=false`.
- Verify final DB state: `claim_verifier.ok`, trust-gate reason,
  `push_enabled`, `pushed`, and `structured_json`.
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
3. Use in Codex market analysis
- Codex can read hybrid-ranked historical events and generated analyses from the RAG tables.
- Retrieved examples are analogues only; do not treat them as current evidence.
- `raw_json.rag.score_components` may record vector / metadata / outcome components for selected examples.
- RAG failure must degrade to an empty example set and never block analysis storage.
4. Verify
- Run `python -m unittest tests.test_rag -v`
- Inspect `t_market_analyses.raw_json.rag` for `examples_count` or an `error`

## Workflow 4D: Retired Python LLM Analysis Backfill
1. Current boundary
- The old Python daily market-analysis and weekly-summary generators are retired.
- Do not use Python as fallback for missing daily/weekly stock or market-analysis prose.
- `POST /market-analysis/run` and `POST /analysis/backfill` return `410 analysis_generation_retired`.
2. Verify storage
- Query `t_market_analyses` by `analysis_slot`.
- Codex local automations own new analysis rows.
- Daily market analysis must not extract stock recommendation candidates; the old fixed-pool and dynamic `t_trade_signals` flows are retired.

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
- Query TWSE openapi dataset `t187ap04_L` (`銝??砍瘥?之閮`)
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
- Taiwan Yahoo context from `MARKET_CONTEXT_TW_YAHOO_SYMBOLS` is an optional tracked evidence input and fallback preference list. It must not be treated as a fixed trading universe.
- Visible stock-analysis exclusions are controlled by `MARKET_ANALYSIS_EXCLUDED_TICKERS`; default excludes `4749` / ?唳???3. Persist as event-only facts
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
- Codex local automation owns the `tw_close` prose row.
- Python provides `market_context:tw_close` facts and storage helpers only.
3. Persist boundaries
- Source/context facts remain in `t_relay_events`
- `t_market_analyses.raw_json.dimension=daily_tw_close`
- Python does not push or create LINE delivery jobs
4. Verify
- Query `t_relay_events` for `source='market_context:tw_close'`
- Query `t_market_analyses` for `analysis_slot='tw_close'`

## Workflow 4L: Market Calendar Guard
1. Calendar source
- `src/event_relay/market_calendar.py` contains built-in 2026 TWSE / NYSE full-closure dates.
- The relevant U.S. close session date is Taiwan local date minus one day.
2. Routing rules
- Sunday: no Python LLM analysis runs.
- TW closed + relevant U.S. session open: only `us_close` runs.
- Relevant U.S. session closed + TW open: only `pre_tw_open` / `tw_close` run, and `pre_tw_open` does not include stale `us_close`.
- TW and relevant U.S. session both closed: Codex may write `macro_daily` with `push_enabled=1`.
3. Verify
- Run `python -m unittest tests.test_market_calendar -v`
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
