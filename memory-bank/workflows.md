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
2. Understand fetch limits
- `news_collector.sources.rss.OfficialRssSource` applies `--limit` per feed, not globally
- Example: 12 feeds with `--limit 5` can produce up to 60 RSS items before URL dedupe and bridge filters
3. Smoke fetch
- Run `python -m news_collector.main fetch --source rss --limit 5 --pretty`
4. Verify storage path
- Restart or wait for `news_collector.relay_bridge`
- Check bridge log for `Polling source=rss fetched=<count>`
- Query `t_relay_events` for recent RSS source rows

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
- Stage2 transmission may receive retrieved historical examples from `t_event_embeddings`; these are analogues only, not current evidence IDs
- OpenAI runs request web search by default; if unavailable, the prompt must label missing context instead of fabricating
3. Persist analysis output
- Generated text is upserted into `t_market_analyses` by `(analysis_date, analysis_slot)`
- Structured stock recommendations are extracted into `t_trade_signals`
- New signals use `status=pending_review`; stale pending signals for the same analysis are marked `superseded`
- Do not create orders here. Risk gate / review and outcomes stay in `t_signal_reviews` and `t_signal_outcomes`
- For existing rows, run `scripts/run_trade_signal_extraction.ps1 -EnvFile .env`
4. Keep Python storage-only
- `market_analysis` does not push directly or create delivery jobs
- Java owns user-facing delivery
5. Verify
- Check prompt snapshots under `runtime/prompts/`
- Query `t_market_analyses` for the current `analysis_date`
- Query `t_trade_signals` by `analysis_id` or `(analysis_date, analysis_slot)`
- Query `t_relay_events` for recent `source LIKE 'market_context:%'`
- Confirm `pushed=0`; Python does not contact LINE or create delivery jobs

## Workflow 4L: Historical-Case RAG Indexing
1. Build the local RAG index
- Run `scripts/run_rag_indexer.ps1 -EnvFile .env`
- The indexer writes recent relay-event vectors into `t_event_embeddings`
- The indexer writes generated-analysis vectors into `t_analysis_embeddings`
2. Embedding model
- Default is `local-hash-v1`, a deterministic lexical embedding that needs no external API key
- Keep `RAG_EMBEDDING_MODEL` stable unless intentionally rebuilding the index
3. Use in market analysis
- `MARKET_ANALYSIS_RAG_ENABLED=true` lets `market_analysis` retrieve similar historical events
- Retrieved examples are inserted into `runtime/prompts/market_analysis_<slot>_stage2_transmission_user.txt`
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
- If local events or web verification are insufficient, explicitly mark the data gap in the stored analysis
3. Store for downstream delivery
- Upsert into `t_market_analyses`
- Java owns user-facing LINE delivery
4. Mark the row as weekly scope
- Use `analysis_date=YYYY-MM-DD` for the target Sunday delivery date
- Use `analysis_slot=weekly_tw_preopen`
- Put `dimension=weekly` in `raw_json`
5. Verify
- Check scheduled task next run
- Query `t_market_analyses` by the target Sunday `analysis_date`

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
- TWSE official OpenAPI: index groups, tracked stocks, and margin balances
3. Persist as event-only facts
- Insert one stored-only event per context point into `t_relay_events`
- Add one `market_context:collector` summary event for point/failure counts
- Keep `raw_json.stored_only=true`, `raw_json.dimension=market_context`, and `raw_json.event_type` for traceability
4. Schedule before the AI brief
- Register through `scripts/register_market_analysis_tasks.ps1`; default is `07:20`, before `pre_tw_open` at `07:30`
5. Verify
- Query `t_relay_events` for today's `source LIKE 'market_context:%'`
- Confirm rows are marked `stored_only_context` / stored-only and inspect `raw_json.failures` on the collector event

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
