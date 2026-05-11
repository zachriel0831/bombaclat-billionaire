# Project Documentation

## Project Goal
Collect and normalize international breaking news, market data, and official disclosures, then generate stored market analyses for downstream systems.

LINE delivery and LINE webhook handling have migrated to the Java system. This Python repository is the data collection, event storage, and analysis service. It does not contact LINE in any form.

## Current Architecture
- Runtime: Python 3.10+
- Main packages:
  - `src/news_collector`: source ingestion + bridge
  - `src/event_relay`: event storage API (`/events`), MySQL persistence, retention cleanup, weekly summary, market analysis, and market context modules
  - `src/news_platform`: separate Taiwan society/politics news collection pipeline with keyword extraction and deterministic issue classification
- Main services:
  1. `news_collector.relay_bridge`
  2. `event_relay.main` (event relay API for `/events`)
  3. `event_relay.weekly_summary` (single-shot, usually triggered by scheduler)
  4. `event_relay.market_analysis` (single-shot, usually triggered by scheduler)

## Ingestion Sources
1. X filtered stream
- Requires X bearer token (supports DPAPI file fallback)
- Tracks allowlisted accounts
- Auto-heal for `429 TooManyConnections` by terminating stale connections and reconnecting
- Bridge startup performs a one-shot X backfill for tracked accounts before attaching the live stream, so recent gap tweets can still be written directly to `t_relay_events` and `t_x_posts`

2. RSS polling
- BBC / Reuters / Fox / NPR plus Taiwan finance feeds from `OFFICIAL_RSS_FEEDS`
- Active Taiwan finance RSS feeds are CNA finance, LTN business, and ETtoday finance; these finance news rows stay in `t_relay_events`, not `news_platform.t_news_articles`
- RSS bridge `--limit` is applied per configured feed, then all feed items are merged, deduped, and sorted. With 15 active feeds and `--limit 5`, one polling cycle can consider up to 75 RSS items before filters.
- Reuters currently uses Google News RSS search as fallback because legacy Reuters RSS endpoints are unavailable from this environment
- CNN RSS is configurable in code, but the previously tested CNN feeds were removed from the active `.env` set after returning stale items from 2016-2024 during the 2026-04-19 verification

3. SEC tracked filings
- Uses official SEC `company_tickers.json` plus `data.sec.gov/submissions/CIK##########.json`
- Tracks allowlisted tickers from `SEC_TRACKED_TICKERS`
- Current MVP filters to high-signal forms from `SEC_ALLOWED_FORMS`
- Writes normalized filing events directly into `t_relay_events` through the crawler bridge

4. TWSE / MOPS listed-company announcements
- Uses official TWSE openapi dataset `t187ap04_L` (`上市公司每日重大訊息`)
- Tracks allowlisted listed-company codes from `TWSE_MOPS_TRACKED_CODES`
- Market analysis uses a fixed five-stock watch pool: `2330` 台積電, `2603` 長榮, `2882` 國泰金, `1605` 華新, and TPEx `4956` 光鋐.
- Writes normalized announcement events directly into `t_relay_events` through the crawler bridge

5. US index tracker
- Tracks DJIA and S&P 500 open/close
- Writes normalized stored-only events directly into `t_relay_events`
- Marks rows as `stored_only_market`
- Stores structured quote rows in MySQL table `t_market_index_snapshots` for same-day analysis

6. Taiwan official market-flow data
- Uses TWSE official/RWD datasets for three major institutional trading, margin trading, foreign ownership, and SBL availability
- Uses TPEx official OpenAPI datasets for margin/SBL, institutional trading, and institutional summaries
- Uses TAIFEX official OpenAPI datasets for major institutional futures/options positioning and open interest
- Writes one stored-only dataset event per official dataset directly into `t_relay_events`
- Uses `source=market_context:twse_flow`, `source=market_context:tpex_flow`, or `source=market_context:taifex_flow`
- Raw event JSON keeps `trade_date`, `dataset`, official rows, and compact normalized metrics for downstream analysis

7. BLS official U.S. macro data
- Uses BLS Public Data API v2 endpoint `https://api.bls.gov/publicAPI/v2/timeseries/data/`
- Supports optional `BLS_API_KEY`; without a key it still sends a low-frequency JSON POST without `registrationkey`
- Writes one stored-only relay event per latest monthly observation directly into `t_relay_events`
- Uses `source=market_context:bls_macro`
- First-batch monthly series mapping:
  - CPI headline `CUSR0000SA0`, CPI core `CUSR0000SA0L1E`
  - PPI headline all commodities `WPU00000000`, PPI final demand `WPSFD4`, PPI core final demand `WPSFD49116`
  - Nonfarm payrolls `CES0000000001`, unemployment rate `LNS14000000`, labor force participation `LNS11300000`
  - Average hourly earnings `CES0500000003`, average weekly hours `CES0500000002`
- Raw event JSON keeps `series_id`, `year`, `period`, `periodName`, `value`, `footnotes`, and normalized period / year-over-year metrics for traceability
- BLS data is monthly and may be preliminary or revised; footnote codes are preserved in `raw_json.footnotes` and `raw_json.normalized_metrics.footnote_codes`

8. FRED / Fed public macro-regime context
- Uses FRED public CSV endpoint `https://fred.stlouisfed.org/graph/fredgraph.csv`
- Runs inside `event_relay.market_context` and writes stored-only rows with `source=market_context:fred`
- No API key is required
- Default series cover:
  - Fed path: `DFEDTARU`, `DFEDTARL`, `SOFR`, `DGS2`, `DGS10`, `T10Y2Y`
  - Liquidity: `WALCL`, `RRPONTSYD`, `WTREGEN`, `WRESBAL`
  - Financial conditions / stress: `NFCI`, `STLFSI4`
  - Credit stress: `BAMLH0A0HYM2`, `BAMLC0A0CM`, `BAA10Y`
  - Sentiment proxy: `VIXCLS`
- Optional controls:
  - `MARKET_CONTEXT_FRED_ENABLED=false`
  - `MARKET_CONTEXT_FRED_SERIES_IDS=SOFR,DGS2,BAMLH0A0HYM2`

9. Structural market context modules
- Runs inside `event_relay.market_context` and writes stored-only rows into `t_relay_events`
- Market breadth:
  - Uses Yahoo daily chart ETF proxies for `RSP-SPY`, `QQEW-QQQ`, and `IWM-SPY`
  - Stores daily spread as `value`, one-month spread as `previous_value`, and three-month spread as `change`
  - Uses `source=market_context:market_breadth`
- AI capex:
  - Uses official SEC ticker mapping and `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
  - Default tickers: `MSFT,GOOGL,META,AMZN`; override with `MARKET_CONTEXT_AI_CAPEX_TICKERS`
  - Requires `SEC_USER_AGENT`; missing user agent is recorded as an explicit source failure
  - Stores capex as a companyfacts proxy, not a pure AI-only capex split, with `source=market_context:sec_companyfacts`
- Oil supply/demand:
  - Uses FRED series for WTI `DCOILWTICO` and Brent `DCOILBRENTEU`
  - Uses EIA v2 weekly petroleum stocks API for U.S. crude stocks excluding SPR `WCESTUS1` when `EIA_API_KEY` is configured
  - Adds derived `BRENT-WTI` spread point
  - Uses `source=market_context:fred_energy` for prices/spread and `source=market_context:eia` for inventory
- Scorecard:
  - Uses the collected market-context points to emit one deterministic `source=market_context:scorecard` row
  - Stores `breadth_health`, `ai_capex_quality`, `energy_shock_risk`, `credit_stress`, and `liquidity_impulse` on a -2..+2 scale
  - Raw JSON includes score, evidence, counter-evidence, missing data, and freshness per dimension
- Optional controls:
  - `MARKET_CONTEXT_BREADTH_ENABLED=false`
  - `MARKET_CONTEXT_AI_CAPEX_ENABLED=false`
  - `MARKET_CONTEXT_OIL_SUPPLY_ENABLED=false`
  - `MARKET_CONTEXT_SCORECARD_ENABLED=false`

10. Taiwan society/politics news platform
- Runs in `src/news_platform` and is separate from `event_relay`
- Reads Taiwan society/politics RSS, sitemap, ETtoday category-list, and PTS category-page sources defined in `news_platform.registry`
- Default society/politics source set is LTN, ETtoday, TVBS, CNA, PTS, and EBC
- Category scope defaults to `society,politics` and can be limited by `NEWSPF_CATEGORIES` or CLI `--categories`
- Writes article rows to independent MySQL tables controlled by `NEWSPF_MYSQL_*`
- Storage contract:
  - `t_news_sources`: source metadata
  - `t_news_articles`: article rows with `article_id`, `source_id`, title/url/summary, timestamps, `tags_json`, `raw_json`, `keywords_json`, `topics_json`, `topic_classified_by`, `topic_classified_at`, `ttl_at`
  - `t_public_records`: structured official records with `record_id`, `source_id`, `record_type`, `country`, optional article category, title/url, `occurred_at`, `region`, `metrics_json`, `tags_json`, and `raw_json`
  - `t_news_article_public_record_links`: many-to-many article-to-record links with `article_id`, `public_record_id`, `relation_type`, `confidence`, `matched_by`, and `evidence_json`
  - `keywords_json`: output of `KeywordWorker` as `[{kw, score}, ...]`
  - `topics_json`: ordered `[{topic_id, label, score, source, ...}, ...]`; `source` is `rule`, `llm`, `rule_fallback`, or `llm_fallback`
  - `topic_classified_by`: `rule` after deterministic classification, `llm` after LLM fallback, NULL before topic classification
  - `topic_classified_at`: UTC timestamp for the latest topic classification write
- Middle-office/frontend read contract:
  - Society category: `GET /api/society/topics`, `GET /api/society/articles`, `GET /api/society/articles/{id}`
  - Politics category: `GET /api/politics/topics`, `GET /api/politics/articles`, `GET /api/politics/articles/{id}`
  - The route category maps to `t_news_articles.category`; frontend topic pages pass `topic=<topicId>` instead of parsing `topics_json` directly
- Data flow:
  1. crawler writes raw article rows
  2. `KeywordWorker` fills `keywords_json`
  3. `TopicWorker` reads rows where `topics_json IS NULL AND keywords_json IS NOT NULL`
  4. deterministic classifier writes up to three specific topic hits into `topics_json`; no-hit rows become category-specific general topics (`general_social_news` / 一般社會新聞 or `general_politics_news` / 一般政治新聞) with `source=rule_fallback`, `topic_classified_by=rule`
  5. Optional `TopicLlmFallbackWorker` can refine rule fallback rows where the first topic is a general fallback topic and `topic_classified_by` is NULL or `rule`
  6. LLM fallback calls OpenAI first (`gpt-5-nano` by default), then Anthropic Claude Haiku if OpenAI is unavailable; it writes either one `source=llm` topic or keeps the category-specific general topic with `source=llm_fallback`, `topic_classified_by=llm`
  7. Official structured datasets such as Legislative Yuan records, judicial records, fraud lists, accident rows, population indicators, or housing indicators are stored in `t_public_records`, not `t_news_articles`
  8. Article-to-record matching writes one row per relation to `t_news_article_public_record_links`, preserving match evidence and confidence for downstream ranking/explanations
- Current public-record sources:
  - Legislative Yuan legal proposals (`ly_bills`): `https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx`, stored as `source_id=ly`, `record_type=legislative_bill`, `category=politics`; upstream ROC dates are normalized to Asia/Taipei timestamps
- MVP keeps topic classifications embedded on `t_news_articles`; a normalized article-topic relation table is deferred until timeline/query workloads require it. Public records are normalized immediately because one record can support many articles and one article can cite many records.

## Event Storage & Analysis Boundary
- HTTP endpoints:
  - `POST /events`: compatibility/manual normalized event ingestion
  - `POST /analysis/backfill`: operator-triggered stored analysis backfill
  - `GET /healthz`
- Storage: MySQL
  - `t_relay_events`
- `t_x_posts`
- `t_market_index_snapshots`
- `t_market_analyses`
- `t_event_embeddings`
- `t_analysis_embeddings`
- `t_trade_signals`
- `t_signal_reviews`
- `t_signal_outcomes`
- Current behavior:
  - Crawler bridge owns normal source ingestion and writes event rows directly
  - `t_relay_events` is treated as event-only storage
  - `t_relay_events` does not keep LINE delivery columns (`is_pushed`, `line_pushed_at`, `line_push_status`, `line_push_error`); Java owns delivery state outside this Python event table
  - Source/context facts must land in `t_relay_events` first; `t_market_analyses` is only for model-generated analysis after reading event windows
  - `t_trade_signals` is derived from `t_market_analyses.structured_json`; it is not a direct source-ingestion table
  - Signal review/risk gate and signal outcomes are independent from analysis generation
  - Python should not be considered the LINE delivery service; Java is responsible for user-facing LINE push/webhook behavior
  - Python contains no LINE push/webhook/direct-push contact path
  - Daily retention cleanup for old event rows
- Retention cleanup:
  - Default `RELAY_RETENTION_KEEP_DAYS=7`
  - Deletes old rows from both `t_relay_events` and `t_x_posts`
  - Event-relay maintenance loop runs cleanup once per local day
  - `scripts/register_retention_cleanup_task.ps1` can register the same cleanup as a fixed daily Windows task

## Analysis Context Policy
- `t_relay_events` is the primary local event/fact context for weekly and scheduled daily analyses, but it is not treated as the complete universe of relevant market information.
- OpenAI analysis calls request the Responses API `web_search` tool by default so the model can verify missing, stale, or fast-moving facts beyond local rows.
- If web search is unavailable or returns insufficient evidence, prompts require the model to label the data gap and lower confidence instead of fabricating certainty.
- Skill docs are retained as prompt assets for macro reasoning and mobile-chat readability; they do not create any Python-owned LINE delivery behavior.

## Weekly Summary
- Module: `src/event_relay/weekly_summary.py`
- Flow:
  1. Read last N days events from `t_relay_events`
  2. Build `system prompt` and `reusable prompt` from skill docs
  3. Call OpenAI Responses API with web search enabled by default for current-fact verification
  4. Store the weekly text into `t_market_analyses`
  5. Leave user-facing delivery to the Java system
- Output format:
  - Weekly uses the section contract `週總經` -> `下週台股配置` -> `下週觀察清單`
  - Each section should connect evidence -> mechanism -> Taiwan implication
  - Weekly reports are allocation/watchlist briefs and should not output intraday entry / take-profit / stop-loss prices
- Storage contract:
  - `analysis_date` uses the target Sunday delivery date like `2026-04-26`
  - `analysis_slot=weekly_tw_preopen`
  - `scheduled_time_local=05:10` using the same `HH:MM` format as daily analyses
  - `raw_json.dimension=weekly`
  - `raw_json.section_contract=["週總經","下週台股配置","下週觀察清單"]`
  - `raw_json.token_usage` records provider/model/token telemetry when an LLM call completes
- Prompt snapshots:
  - `runtime/prompts/weekly_summary_system_prompt.txt`
  - `runtime/prompts/weekly_summary_reusable_prompt.txt`
- Key management:
  - Prefer env var `WEEKLY_SUMMARY_OPENAI_API_KEY` / `OPENAI_API_KEY`
  - Fallback to DPAPI file `WEEKLY_SUMMARY_OPENAI_API_KEY_FILE`

## Scheduled Market Analysis
- Module: `src/event_relay/market_analysis.py`
- Pre-open context module: `src/event_relay/market_context.py`
- Schedule intent:
  - `04:50` Asia/Taipei: collect BLS official macro facts as stored-only events into `t_relay_events`
  - `05:00` Asia/Taipei: U.S. close summary for Taiwan next-session context
  - `07:20` Asia/Taipei: collect pre-open market context as stored-only events into `t_relay_events`
  - `07:30` Asia/Taipei: Taiwan pre-open summary
  - `15:10` Asia/Taipei: collect Taiwan official market-flow facts as stored-only events into `t_relay_events`
  - `15:20` Asia/Taipei: collect Taiwan close context from same-day relay events into `t_relay_events`
  - `15:30` Asia/Taipei: Taiwan close review analysis
- Calendar guard:
  - Module: `src/event_relay/market_calendar.py`
  - Built-in 2026 TWSE / NYSE closed dates are checked before any market-analysis LLM call.
  - TW closed + relevant U.S. close session open: only `us_close` may run.
  - Relevant U.S. close session closed + TW open: only `pre_tw_open` / `tw_close` may run; `pre_tw_open` must not receive stale `us_close` context.
  - TW and relevant U.S. close session both closed: the `pre_tw_open` task is converted into `macro_daily` and remains Java-delivery eligible.
  - Sunday: daily market analysis skips; weekly summary owns the day.
- Flow:
  1. Read latest event context from `t_relay_events`
  2. Read latest DJIA / S&P 500 rows from `t_market_index_snapshots`
  3. Include stored-only `market_context:*` raw event payloads in the prompt event window
  3a. Select provider/model with `src/event_relay/llm_quota_router.py`; scheduled market analysis is OpenAI-primary by default and Anthropic/Claude fallback second, with Admin API month-to-date cost checks used when keys and monthly budgets are configured
  4. Build a quota-managed context pack in `src/event_relay/context_pack_builder.py`; scorecard, market context, and important official data are selected before general news/social rows
  5. Retrieve hybrid historical examples from `t_event_embeddings` and `t_analysis_embeddings` for stage2 transmission analogues when available; metadata filter, vector similarity, and outcome score are all part of ranking
  6. Run deterministic `stage0_thesis_selector` to choose 1-2 core tensions that all LLM stages must answer
  7. Build Traditional Chinese prompts from existing macro + mobile-chat formatting skills
  8. Call OpenAI Responses API or Anthropic Messages API according to the selected route; OpenAI web search is enabled by default for current-fact verification
  8a. If the selected provider is Anthropic, apply `provider-context-policy-v1` compact context before prompting to reduce event rows, market rows, RAG examples, and raw JSON detail while preserving scorecard, market context, official sources, and high-importance events
  8b. Run `claim_verifier` on the final output to check whether numbers, dates, and tickers have supporting evidence in the prompt context
  8c. Store generated text in `t_market_analyses`; `raw_json.model_router`, `raw_json.provider_context_policy`, `raw_json.rag`, `raw_json.pipeline_stages`, and `raw_json.claim_verifier` hold routing/retrieval/stage/evidence telemetry
  9. Set delivery eligibility in `push_enabled`: `pre_tw_open=1`, `macro_daily=1`, `us_close=1` only when TW is closed and the relevant U.S. close session was open, `tw_close=0`
  10. Inject the latest stored `us_close` analysis as upstream context only when the relevant U.S. close session was open; if U.S. was closed, the Taiwan pre-open prompt intentionally has no `us_close` block
  11. Extract fixed-pool `structured_json.stock_watch` rows into `t_trade_signals` as `pending_review` rows
  12. For delivery-visible `pre_tw_open` and TW-holiday `us_close`, use only the fixed market-analysis pool: `2330`, `2603`, `2882`, `1605`, `4956`. The model must not introduce substitute Taiwan tickers.
  13. Fill missing fixed-pool signal reference levels from deterministic quote/context rows when evidence exists, then append a deterministic `## 今日個股觀察` section as a watch/monitor view, not a free-form recommendation list.
  14. For `macro_daily`, write macro-only analysis into `t_market_analyses` and do not create trade signals.
- Pre-open text formatting:
  - `raw_json.display_title` is date-only (`YYYY-MM-DD`) for downstream delivery titles
  - Daily analysis uses the fixed macro flow: `總經 Regime` -> `利率與流動性` -> `景氣循環` -> `市場情緒` -> `台股配置` -> `風險與資料缺口`
  - `利率與流動性` should use bullets for dense market facts
  - Fallback stock rationales keep only `需開盤量價確認` as the repeated warning
- Tracked-stock context:
  - `MARKET_CONTEXT_TWSE_CODES` reads official TWSE close/margin rows for tracked listed stocks
  - `MARKET_CONTEXT_TW_YAHOO_SYMBOLS` provides Yahoo Taiwan quote/context rows for the fixed pool: `2330.TW:台積電`, `2603.TW:長榮`, `2882.TW:國泰金`, `1605.TW:華新`, and `4956.TWO:光鋐`
  - `MARKET_ANALYSIS_EXCLUDED_TICKERS` defaults to `4749`, so 新應材 is excluded from visible individual-stock analysis even if old quote/context rows remain in storage
  - Official TWSE context is preferred when both sources produce the same ticker; Yahoo context fills gaps such as TPEx `.TWO` symbols
- Trade-signal boundary:
  - `t_trade_signals` stores fixed-pool Taiwan watch items only
  - `ticker` is the normalized tradable symbol; Taiwan signals use the 4-digit code without `.TW` / `.TWO`
  - Every signal keeps `analysis_id`, slot/date, ticker, strategy/direction, optional entry/stop/target JSON, and `source_event_ids`
  - Internal `direction=long` means buy-side / 做多, not long-term holding; `entry_zone` is the entry area, `take_profit_zone` is the profit-taking exit area, and `invalidation` is rendered as 停損
  - `quote_fallback_stock_watch` / `context_fallback_stock_watch` are fixed-pool evidence sources only; they enrich or fill monitor levels and must not add tickers outside `2330`, `2603`, `2882`, `1605`, `4956`
  - `idempotency_key` suppresses duplicate signals for the same analysis/ticker/strategy
  - `t_signal_reviews` is reserved for risk gate / human / model-review decisions
  - `t_signal_outcomes` is reserved for later performance feedback
  - LLM analysis never creates order intents or broker calls directly
- Historical-case RAG:
  - Module: `src/event_relay/rag.py`
  - Current retrieval is hybrid: metadata overlap filters candidates, deterministic local lexical/vector similarity ranks semantic fit, and stored `outcome_json` scores successful past analyses higher
  - Default embeddings still use deterministic local lexical embeddings (`local-hash-v1`) to avoid a new paid API dependency
  - `scripts/run_rag_indexer.ps1` incrementally indexes recent `t_relay_events` into `t_event_embeddings` and `t_market_analyses` into `t_analysis_embeddings`
  - `stage2_transmission` receives retrieved examples as analogues only; historical event IDs are not valid current evidence IDs
  - If RAG retrieval fails or has no candidates, market analysis continues without historical examples and records the gap in `raw_json.rag`
- Market context storage contract:
  - `source` starts with `market_context:`
  - `raw_json.stored_only=true`
  - `raw_json.dimension=market_context`
  - `raw_json.event_type` is `market_context_point`, `market_context_collection`, `market_context_scorecard`, or `tw_market_flow_dataset`
  - current source families: deterministic scorecard, Yahoo chart market snapshots, U.S. Treasury official yield curve XML, FRED public CSV macro-regime series, market-breadth ETF spreads, SEC companyfacts AI capex proxy, FRED oil price context, optional EIA oil inventory context, TWSE official OpenAPI index/stock/margin data, Taiwan official flow datasets from TWSE / TPEx / TAIFEX, and BLS official macro series
- Prompt snapshots:
  - `runtime/prompts/market_analysis_<slot>_system_prompt.txt`
  - `runtime/prompts/market_analysis_<slot>_user_prompt.txt`

## Scheduler
- Windows helper script:
  - `scripts/register_weekly_summary_task.ps1`
  - `scripts/register_market_analysis_tasks.ps1`
  - `scripts/register_retention_cleanup_task.ps1`
- Current target schedule requirement:
  - Every Saturday 23:00 (Asia/Taipei, local machine timezone) for weekly summary (Java pushes it at Sunday 05:10)
  - Every day 05:00, 07:30, and 15:30 (Asia/Taipei, local machine timezone) for market analysis
  - Every day 04:40 (Asia/Taipei, local machine timezone) for historical-case RAG indexing
  - Every day 04:50 (Asia/Taipei, local machine timezone) for BLS macro event collection
  - Every day 07:20 (Asia/Taipei, local machine timezone) for pre-open market context collection
  - Every day 15:10 (Asia/Taipei, local machine timezone) for Taiwan official market-flow collection
  - Every day 15:20 (Asia/Taipei, local machine timezone) for Taiwan close context collection
  - Every day 00:10 (Asia/Taipei, local machine timezone) for retention cleanup
  - Daily market-analysis tasks are still registered daily, but `market_calendar.py` may skip them or convert `pre_tw_open` into `macro_daily` on TW/US closed days.

## Source Expansion Backlog
1. SEC EDGAR tracked filings
- started 2026-04-19 as first official-source expansion
2. Taiwan official company announcements
- started 2026-04-19 with TWSE `t187ap04_L` daily major information
- next likely additions: shareholder meeting / board meeting / investor conference datasets
3. Fed / macro official releases
- BLS macro official data started 2026-04-22
- next likely additions: FOMC / Federal Reserve and FRED class datasets

## Security & Secrets
- Secrets are stored locally with Windows DPAPI:
  - `.secrets/x_bearer_token.dpapi`
  - `.secrets/openai_api_key.dpapi`
  - `.secrets/openai_admin_key.dpapi` (admin use, high sensitivity)
  - Anthropic Admin API keys are read from env only (`MARKET_ANALYSIS_ANTHROPIC_ADMIN_KEY` / `ANTHROPIC_ADMIN_KEY` / `ANTHROPIC_ADMIN_API_KEY`) and must not be logged
- Never print full secret values in logs.

## Operations
- Start legacy-named event relay API:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_event_relay.ps1`
- Start bridge:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1`
- Restart both:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\restart_live_services.ps1`
- Run weekly summary once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_summary.ps1 -Force`
- Run weekly summary through HTTP:
  - `'{"kind":"weekly","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"`
- Run market analysis once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot us_close -Force`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot pre_tw_open -Force`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot tw_close -Force`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot macro_daily -Force`
- Run market analysis through HTTP:
  - `'{"kind":"market","slot":"pre_tw_open","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"`
- Extract trade signals from existing structured analyses:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_trade_signal_extraction.ps1 -EnvFile .env -Days 14 -Limit 50`
- Run market context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env`
- Run Taiwan official market-flow context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_market_flow.ps1 -EnvFile .env`
- Run BLS macro context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_bls_macro.ps1 -EnvFile .env`
- Run Taiwan close context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_close_context.ps1 -EnvFile .env`
- Run retention cleanup once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_retention_cleanup.ps1 -EnvFile .env`

## Known Operational Notes
- X stream may return 429 when connection slots are occupied; auto-heal is enabled.
- OpenAI `insufficient_quota` can occur even with valid key if project billing/entitlement is not active.
- On this Windows workstation, `run_source_bridge.ps1` prefers `Python 3.12` for the bridge because local `Python 3.13` fails TLS verification against `openapi.twse.com.tw`.
