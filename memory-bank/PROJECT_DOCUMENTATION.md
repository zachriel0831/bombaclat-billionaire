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

1a. Truth Social public account polling
- Module: `src/news_collector/sources/truth_social.py`
- No token required; uses Truth Social public Mastodon-compatible account lookup/status endpoints with a browser-style `TRUTH_SOCIAL_USER_AGENT`
- Tracks allowlisted handles or profile URLs from `TRUTH_SOCIAL_ACCOUNTS`, starting with `https://truthsocial.com/@realDonaldTrump`
- Writes normalized rows with `source=truthsocial:<handle>` into `t_relay_events`
- Mirrors rows into the existing social-post table `t_x_posts` with `tweet_id=truthsocial-<status_id>` so the public-figure feed and social-post analysis path can reuse the Elon/X storage design
- Raw status JSON is preserved in `raw_json`; display text is derived from Truth Social HTML content as plain text

2. RSS polling
- BBC / Reuters / Fox / NPR plus Taiwan finance and official finance/macro feeds from `OFFICIAL_RSS_FEEDS`
- Active Taiwan finance/official RSS feeds include CNA finance, LTN business, ETtoday finance, Anue, Economic Daily News, Newtalk finance, Storm finance, MoneyDJ, CBC, TWSE, and FSC; these finance/news rows stay in `t_relay_events`, not `news_platform.t_news_articles`
- Finance/news relay rows may carry short-retention reporter metadata in `raw_json.authors` after `scripts/backfill_relay_event_authors.py` runs. This is display enrichment for `/api/events` and is separate from the long-lived society/politics `t_news_authors` relation model.
- RSS bridge `--limit` is applied per configured feed, then all feed items are merged, deduped, and sorted. Current `.env` uses `OFFICIAL_RSS_FIRST_PER_FEED=true`, so one polling cycle considers one item per feed; if disabled, 27 active feeds and `--limit 5` can consider up to 135 RSS items before filters.
- Reuters currently uses Google News RSS search as fallback because legacy Reuters RSS endpoints are unavailable from this environment
- CNN RSS is configurable in code, but the previously tested CNN feeds were removed from the active `.env` set after returning stale items from 2016-2024 during the 2026-04-19 verification

2a. Free Palestine English issue-news collector
- Module: `src/event_relay/palestine_news.py`
- Uses English RSS / Google News search feeds only; default sources are Google News English search, Al Jazeera English RSS, BBC Middle East RSS, and Guardian Palestine RSS
- Filters to Palestine/Gaza/West Bank issue terms and rejects likely non-English titles before writing
- Writes normalized rows directly to long-term `t_palestine_news_items` with `source_id=<source_id>`, `topic=free_palestine`, and `language=en`
- Scheduled task: `NewsCollector-PalestineNews`, starting at 06:10 local/Taiwan time and repeating every 3 hours
- Public read path: `news-platform-api` exposes `GET /api/timeline/news`, and `news-display-frontend` renders it as the `/timeline` table news column

3. SEC tracked filings
- Uses official SEC `company_tickers.json` plus `data.sec.gov/submissions/CIK##########.json`
- Tracks allowlisted tickers from `SEC_TRACKED_TICKERS`
- Current MVP filters to high-signal forms from `SEC_ALLOWED_FORMS`
- Writes normalized filing events directly into `t_relay_events` through the crawler bridge

4. TWSE / MOPS listed-company announcements
- Uses official TWSE openapi dataset `t187ap04_L` (`上市公司每日重大訊息`)
- Tracks allowlisted listed-company codes from `TWSE_MOPS_TRACKED_CODES`
- Market analysis target direction is Codex-generated dynamic Taiwan intraday / short-swing candidates stored in `t_trade_signals`; the old fixed ten-stock pool was an observation/debugging aid and remains only as a runtime migration gap.
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

7a. Market release calendar
- Module: `src/event_relay/macro_calendar.py`
- Uses official macro release-calendar pages:
  - BLS annual release calendar `https://www.bls.gov/schedule/<year>/home.htm`
  - U.S. Census Retail Trade release schedule `https://www.census.gov/retail/release_schedule.html`
- Tracks CPI, PPI, Employment Situation / nonfarm payrolls, and Advance Monthly Retail Trade / retail sales
- Also tracks watched heavyweight earnings rows from Nasdaq daily earnings calendar `https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`
- Earnings rows use `indicator_code=earnings_<symbol>` and keep raw source fields plus `event_type=earnings_release`, `symbol`, `market`, `time_type`, and `date_status` in `raw_json`
- Optional `MACRO_CALENDAR_EARNINGS_MANUAL_FILE` supports confirmed/manual Taiwan local heavyweight dates until a dedicated MOPS adapter is added
- Interprets official release times as U.S. Eastern time and stores both UTC and Asia/Taipei timestamps
- Writes long-lived rows to `t_macro_release_calendar`, not `t_relay_events` and not `t_market_analyses`
- `reminder_date_taipei` is always the Taiwan date before `release_at_taipei`
- LINE delivery state fields (`reminder_pushed`, `reminder_pushed_at`, `reminder_push_status`, `reminder_push_error`) are updated by `line-relay-service`; Python only upserts official calendar facts

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
- Default society/politics source set is LTN, ETtoday, TVBS, CNA, PTS, EBC, Newtalk, Storm Media, and Commercial Times (`ctee`)
- Commercial Times uses `https://www.ctee.com.tw/sitemaps/sitemap_newstoday.xml`; URL tail category code `-431401` is mapped to `society`, and `-430104` is mapped to `politics`. These are source-category filters only; issue topics are still assigned later by the normal deterministic/LLM topic workers.
- Category scope defaults to `society,politics` and can be limited by `NEWSPF_CATEGORIES` or CLI `--categories`
- Writes article rows to independent MySQL tables controlled by `NEWSPF_MYSQL_*`
- Storage contract:
  - `t_news_sources`: source metadata
  - `t_news_articles`: article rows with `article_id`, `source_id`, title/url/summary, timestamps, `authors_json`, `author_extraction_status`, `author_extraction_method`, `author_extraction_confidence`, `author_raw_text`, `author_extracted_at`, `tags_json`, `raw_json`, `keywords_json`, `topics_json`, `topic_classified_by`, `topic_classified_at`, `ttl_at`
  - `t_news_authors`: normalized source-scoped reporter/author identities
  - `t_news_article_authors`: many-to-many article-to-author links with role, ordinal, extraction method, confidence, and raw byline text
  - `t_news_author_coverage_daily`: materialized daily source/category byline coverage with missing-author status breakdown
  - `t_public_records`: structured official records with `record_id`, `source_id`, `record_type`, `country`, optional article category, title/url, `occurred_at`, `region`, `metrics_json`, `tags_json`, and `raw_json`
  - `t_news_article_public_record_links`: many-to-many article-to-record links with `article_id`, `public_record_id`, `relation_type`, `confidence`, `matched_by`, and `evidence_json`
  - `keywords_json`: output of `KeywordWorker` as `[{kw, score}, ...]`
  - `topics_json`: ordered `[{topic_id, label, score, source, ...}, ...]`; `source` is `rule`, `llm`, `rule_fallback`, or `llm_fallback`
  - `topic_classified_by`: `rule` after deterministic classification, `llm` after LLM fallback, NULL before topic classification
  - `topic_classified_at`: UTC timestamp for the latest topic classification write
- Middle-office/frontend read contract:
  - Society category: `GET /api/society/topics`, `GET /api/society/articles`, `GET /api/society/articles/{id}`
  - Politics category: `GET /api/politics/topics`, `GET /api/politics/articles`, `GET /api/politics/articles/{id}`
  - Government public records: `GET /api/public-records`, `GET /api/public-records/{id}`
  - Article-linked public records: `GET /api/society/articles/{id}/public-records`, `GET /api/politics/articles/{id}/public-records`
  - The route category normally maps to `t_news_articles.category`; frontend topic pages pass `topic=<topicId>` instead of parsing `topics_json` directly
  - `low_birthrate` is a cross-category issue view: `GET /api/society/topics`, `GET /api/society/articles?topic=low_birthrate`, and `GET /api/society/timeline?topic=low_birthrate` aggregate matching rows from all `t_news_articles.category` values while preserving each article's original `category`
  - Finance feed: `news-display-frontend` calls `GET /api/events` through `/api/content/events` with the public source allowlist in `news-platform-api/docs/API_SPEC.md`; the allowlist must include active Taiwan finance/public market RSS source names such as Economic Daily News, LTN finance, MoneyDJ, Anue, CNA finance, ETtoday finance, Newtalk finance, Storm, TWSE, and CBC. The API source filter matches both normal UTF-8 source names and legacy mojibake DB values before returning repaired display text. Reporter names on finance event cards are read from optional event `authors[]` or `rawJson.authors`; current enrichment writes the latter in `t_relay_events.raw_json`.
  - Free Palestine issue news: `/timeline` calls `GET /api/timeline/news`, which reads long-term `t_palestine_news_items`; do not add this issue-news storage to the general finance public feed or `t_relay_events` retention stream.
- Data flow:
  1. crawler writes raw article rows; RSS/Atom and sitemap sources also fill `authors_json` when explicit author metadata or a high-confidence reporter byline is available; all new article rows also receive `author_extraction_status`
     - Articles with authors upsert normalized rows into `t_news_authors` and `t_news_article_authors`
     - Articles without authors keep article-level missing states such as `no_detail_fetched`, `parser_not_supported`, `low_confidence`, or `parse_failed`; no fake `unknown` author row is created
     - In loop mode, `ArticleDetailAuthorWorker` runs a bounded article-detail byline pass after keyword/topic work so recent `no_detail_fetched` or `parser_not_supported` rows can be enriched without a separate always-on process
     - `scripts/backfill_news_author_status.py`, `scripts/backfill_news_author_detail_pages.py`, `scripts/backfill_news_author_relations.py`, and `scripts/build_news_author_coverage_daily.py` remain available for manual repair, broader backfills, author relations, and daily coverage aggregates
  2. `KeywordWorker` fills `keywords_json`
  3. `TopicWorker` reads rows where `topics_json IS NULL AND keywords_json IS NOT NULL`
  4. deterministic classifier writes up to three specific topic hits into `topics_json`; `TopicSpec.categories` scopes category-specific rules such as politics L2 topics to `category=politics`; no-hit rows become category-specific general topics (`general_social_news` / 一般社會新聞 or `general_politics_news` / 一般政治新聞) with `source=rule_fallback`, `topic_classified_by=rule`
      - `low_birthrate` includes common policy variants such as `少子女化`, `0到6歲國家一起養`, and `兒少TISA`
      - Related-link sections in summaries (`延伸閱讀`, `相關新聞`, `更多新聞`) are ignored before deterministic matching to avoid misclassifying unrelated articles
      - Politics second-layer topics are `elections`, `cross_strait_relations`, `foreign_affairs`, `legislative_policy`, `party_politics`, `political_accountability`, `defense_security`, and `public_budget`; persistent thread tables remain deferred
  5. Optional `TopicLlmFallbackWorker` can refine rule fallback rows where the first topic is a general fallback topic and `topic_classified_by` is NULL or `rule`
  6. LLM fallback calls OpenAI first (`gpt-5-nano` by default), then Anthropic Claude Haiku if OpenAI is unavailable; it writes either one `source=llm` topic or keeps the category-specific general topic with `source=llm_fallback`, `topic_classified_by=llm`
  7. Official structured datasets such as Legislative Yuan records, judicial records, fraud lists, accident rows, population indicators, or housing indicators are stored in `t_public_records`, not `t_news_articles`
  8. In loop mode, default public-record sources are collected once per local day
  9. In loop mode, article-detail author enrichment defaults to enabled with a small batch (`NEWSPF_AUTHOR_DETAIL_BACKFILL_BATCH_SIZE`, default `30`) and source allowlist (`NEWSPF_AUTHOR_DETAIL_BACKFILL_SOURCES`)
  10. `PublicRecordLinkWorker` matches recent articles to recent public records and writes one row per relation to `t_news_article_public_record_links`, preserving match evidence and confidence for downstream ranking/explanations
- Current public-record sources:
  - Legislative Yuan legal proposals (`ly_bills`): `https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx`, stored as `source_id=ly`, `record_type=legislative_bill`, `category=politics`; upstream ROC dates are normalized to Asia/Taipei timestamps
  - Legislative Yuan healthcare proposals (`ly_healthcare_bills`, included in CLI alias `healthcare`): same official LY legal proposal API, filtered by healthcare terms such as `醫療法`, `護理人員法`, `全民健康保險法`, `長期照顧服務法`, `護病比`, `護理待遇`, and `護理津貼`; stored as `source_id=ly`, `record_type=healthcare_legislative_bill`, `category=society`, tagged `healthcare_burden`
  - NPA 165 fraud-rumor open data (`npa_fraud_rumors`): `https://data.gov.tw/dataset/38262`, stored as `source_id=npa`, `record_type=fraud_rumor`, `category=society`
  - NPA A1 traffic accident open data (`npa_traffic_a1`): `https://data.gov.tw/dataset/57023`, stored as `source_id=npa`, `record_type=traffic_accident_a1`, `category=society`; party rows are grouped into one accident record by date/time/location/type
  - NPA A2 traffic accident monthly statistics (`npa_traffic_a2_stats`): `https://data.gov.tw/dataset/57024`, stored as `source_id=npa`, `record_type=traffic_accident_a2_stat`, `category=society`; rows are grouped by accident/month/region, then aggregated into monthly casualty/count metrics
  - NPA drunk-driving annual statistics (`npa_drunk_driving_stats`): `https://data.gov.tw/dataset/9018`, stored as `source_id=npa`, `record_type=traffic_drunk_driving_stat`, `category=society`; this official dataset is low-frequency and may lag recent traffic news
  - NPA fraud blocked-domain statistics (`npa_fraud_blocked_domain_stats`): `https://data.gov.tw/en/datasets/176455`, stored as `source_id=npa`, `record_type=fraud_blocked_domain_stat`, `category=society`; rows are aggregated by ROC year-month and website nature
  - NPA fraud enforcement dashboard (`npa_fraud_enforcement_stats`): `https://data.gov.tw/dataset/172159`, stored as `source_id=npa`, `record_type=fraud_enforcement_stat`, `category=society`; rows track monthly enforcement groups, suspects, seized proceeds, and blocked amounts
  - NHI contracted-hospital nursing staff monthly data (`nhi_hospital_nursing_staff`, included in `healthcare`): `https://data.gov.tw/dataset/174661`, stored as `source_id=nhi`, `record_type=nhi_hospital_nursing_staff_stat`, `category=society`; rows are aggregated by Gregorian year/month and county/city with practicing and support nurse counts
  - NHI hospital bed occupancy (`nhi_hospital_bed_occupancy`, included in `healthcare`): `https://data.gov.tw/dataset/79622`, stored as `source_id=nhi`, `record_type=nhi_hospital_bed_occupancy_stat`, `category=society`; ODS rows are stored per hospital with four bed-type occupancy rates
  - MOHW annual healthcare capacity sources (`mohw_hospital_workforce`, `mohw_clinic_workforce`, `mohw_hospital_beds`, included in `healthcare`): `https://data.gov.tw/dataset/6474`, `https://data.gov.tw/dataset/6476`, and `https://data.gov.tw/dataset/6473`; ZIP/CSV township rows are aggregated by year and county/city into `mohw_hospital_workforce_stat`, `mohw_clinic_workforce_stat`, and `mohw_hospital_bed_stat`
  - MOHW nursing staff annual statistic (`mohw_nursing_staff_stats`, included in `healthcare`): `https://data.gov.tw/dataset/118549`, stored as `source_id=mohw`, `record_type=mohw_nursing_staff_stat`, `category=society`; source CSV is CP950 and currently contains the upstream years present in the official file
  - MOJ prosecution disposition statistics (`moj_prosecution_disposition_stats`, included in `justice`): `https://data.gov.tw/dataset/39402`, stored as `source_id=moj`, `record_type=moj_prosecution_disposition_stat`, `category=society`; rows are aggregated by Gregorian year/month into prosecution, deferred-prosecution, non-prosecution, and other disposition people counts
  - Agency of Corrections daily custody dynamics (`mojac_daily_custody`, included in `justice`): `https://data.gov.tw/dataset/101185`, stored as `source_id=mojac`, `record_type=mojac_daily_custody_stat`, `category=society`; current daily XML row stores actual custody, approved capacity, over-capacity rate, intake, and release counts
- Current article-record matchers:
  - Legislative Yuan bills and healthcare-filtered bills: deterministic `ly_bill_rule`, using full bill title, law names, proposer/cosignatory names, and date distance; CLI `--link-public-records`
  - NPA 165 fraud rumors: deterministic `npa_fraud_rumor_rule`, using full title or fraud-context title terms plus date distance; A1 traffic records, NPA statistic records, healthcare capacity records, and justice/corrections statistics are ingested but not auto-linked until higher-precision location/event/stat-context matching is available
- MVP keeps topic classifications embedded on `t_news_articles`; a normalized article-topic relation table is deferred until timeline/query workloads require it. Public records are normalized immediately because one record can support many articles and one article can cite many records.

11. Data-source health tracking
- `scripts/run_data_source_health.ps1` / `scripts/check_data_source_health.py` produce a read-only freshness report for news-analysis inputs.
- `scripts/run_four_hour_digest_context.ps1` collects compact context for the
  Codex-generated four-hour cross-section news digest. Codex automation writes
  the final JSON to Redis through `scripts/store_four_hour_digest_to_redis.ps1`
  with a 15,000 second TTL; public API reads are owned by `news-platform-api`.
- The report checks relay-side finance/public RSS, international RSS, X, Truth Social, SEC, TWSE/MOPS, US index tracker, market-context facts, BLS macro facts, Taiwan market-flow facts, and stored market analyses.
- It also checks news-platform society/politics article freshness per category and per source, article enrichment gaps, public-record refresh freshness based on `updated_at`, article-record link freshness, and local Python process counts.
- Status semantics: `OK` within expected cadence, `WARN` outside warn threshold, `STALE` outside stale threshold, `MISSING` no rows, and `ERROR` for query/connect failures.
- Public-record sources are lower cadence than news feeds; current guardrails warn after 48 hours and stale after 96 hours.

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
  - `t_macro_release_calendar`
- Current behavior:
  - Crawler bridge owns normal source ingestion and writes event rows directly
  - `t_relay_events` is treated as event-only storage
  - `t_relay_events` does not keep LINE delivery columns (`is_pushed`, `line_pushed_at`, `line_push_status`, `line_push_error`); Java owns delivery state outside this Python event table
  - Source/context facts must land in `t_relay_events` first; `t_market_analyses` is only for model-generated analysis after reading event windows
  - `t_trade_signals` is derived from `t_market_analyses.structured_json`; it is not a direct source-ingestion table
  - `t_trade_signals` includes deterministic `risk_reward_ratio`, `candidate_score`, and `avoid_reason` fields for downstream watchlist gating and review
  - Signal review/risk gate and signal outcomes are independent from analysis generation
  - Python should not be considered the LINE delivery service; Java is responsible for user-facing LINE push/webhook behavior
  - Python contains no LINE push/webhook/direct-push contact path
  - Daily retention cleanup for old event rows

### Four-hour cross-section digest
- Context source tables:
  - `t_relay_events` for Taiwan finance/public news and celebrity/public-figure rows
  - `news_platform.t_news_articles` for society and politics articles
  - `t_palestine_news_items` for Free Palestine English issue news
- Generated digest storage:
  - Redis `news:digest:four-hour:latest` stores the non-expiring latest display payload
  - Redis `news:digest:four-hour:current-key` stores the non-expiring current version pointer
  - Versioned Redis keys under `news:digest:four-hour:*` expire after 15,000 seconds
- The digest is Redis product state and is not persisted to
  `t_market_analyses`.
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
  4a. Resolve the slot-aware pipeline mode. `MARKET_ANALYSIS_<SLOT>_PIPELINE` overrides `MARKET_ANALYSIS_PIPELINE`; current default keeps `pre_tw_open=multi_stage` and uses `us_close=digest` so the U.S. close job becomes compact upstream context instead of a full trade brief.
  5. Retrieve hybrid historical examples from `t_event_embeddings` and `t_analysis_embeddings` for stage2 transmission analogues when available; metadata filter, vector similarity, and outcome score are all part of ranking
  6. Run deterministic `stage0_thesis_selector` to choose 1-2 core tensions that all LLM stages must answer when the effective pipeline is `multi_stage`
  7. Build Traditional Chinese prompts from existing macro + mobile-chat formatting skills for full analysis; `digest` mode uses a compact U.S. close prompt and does not load the full stage chain
  8. Call OpenAI Responses API or Anthropic Messages API according to the selected route; OpenAI web search is enabled by default for current-fact verification
  8a. If the selected provider is Anthropic, apply `provider-context-policy-v1` compact context before prompting to reduce event rows, market rows, RAG examples, and raw JSON detail while preserving scorecard, market context, official sources, and high-importance events
  8b. Run `claim_verifier` on the final output to check whether numbers, dates, and tickers have supporting evidence in the prompt context
      - For dynamic trade-candidate slots, candidate tickers must be supported by evidence or explicitly marked as model-selected candidates with traceable local context.
      - This allowance must not hide unsupported numeric/date claims or unrelated ticker claims.
  8c. Apply `market-analysis-trust-gate-v1`: when `claim_verifier.ok=false`, store the analysis for audit/debug but set final `push_enabled=0` and skip trade-signal extraction; `MARKET_ANALYSIS_CLAIM_GATE_ENABLED=false` is an emergency debug override only
  8d. Store generated text in `t_market_analyses`; `raw_json.model_router`, `raw_json.provider_context_policy`, `raw_json.rag`, `raw_json.pipeline_stages`, `raw_json.requested_pipeline_mode`, `raw_json.pipeline_mode`, `raw_json.analysis_intent`, `raw_json.claim_verifier`, and `raw_json.trust_gate` hold routing/retrieval/stage/evidence/trust telemetry
  9. Set base delivery eligibility in `push_enabled`: `pre_tw_open=1`, `macro_daily=1`, `us_close=1` only when TW is closed and the relevant U.S. close session was open, `tw_close=0`; the trust gate may lower the final stored value to `0`
  10. Inject the latest stored `us_close` digest/analysis as upstream context only when the relevant U.S. close session was open; if U.S. was closed, the Taiwan pre-open prompt intentionally has no `us_close` block
  11. Target design: extract Codex-generated dynamic Taiwan intraday / short-swing candidates into `t_trade_signals` as `pending_review` rows for full analysis modes.
  12. The old fixed ten-stock pool was an observation/debugging aid. Current runtime code still contains fixed-pool paths, so migration work is required before dynamic candidate generation is fully live.
  13. Fill missing signal reference levels from deterministic quote/context rows only when evidence exists. Daily visible reports must not append `## 今日個股觀察`; trading candidates remain machine-readable downstream context unless a separate trading UI explicitly asks for them.
  14. For `macro_daily`, write macro-only analysis into `t_market_analyses` and do not create trade signals.
- Daily text formatting:
  - `raw_json.display_title` is date-only (`YYYY-MM-DD`) for downstream delivery titles
  - Daily analysis uses the product-editor flow: `今日一句話` -> `三個檢查點` -> `總經與流動性` -> `景氣循環` -> `國際新聞傳導` -> `產業板塊解析` -> `風險與資料缺口`
  - Do not write a dedicated `台股配置` section or append `## 今日個股觀察` in daily visible reports.
  - Individual companies may appear only as macro/sector transmission examples, such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭; daily visible reports should not include entry, stop-loss, or target-price language.
  - `三個檢查點` must contain exactly three observable checks, and `總經與流動性` should use bullets for dense market facts
  - `國際新聞傳導` should show `事件 -> 影響變數 -> 台股族群 -> 確認/失效` when evidence supports a chain
  - Fallback stock rationales keep only `需開盤量價確認` as the repeated warning
- Tracked-stock context:
  - `MARKET_CONTEXT_TWSE_CODES` reads official TWSE close/margin rows for tracked listed stocks
  - `MARKET_CONTEXT_TW_YAHOO_SYMBOLS` historically provided Yahoo Taiwan quote/context rows for the fixed pool; dynamic-candidate migration should generalize this into a broader evidence universe and ranking input.
  - `MARKET_ANALYSIS_EXCLUDED_TICKERS` defaults to `4749`, so 新應材 is excluded from visible individual-stock analysis even if old quote/context rows remain in storage
  - Official TWSE context is preferred when both sources produce the same ticker; Yahoo context fills gaps such as TPEx `.TWO` symbols
- Trade-signal boundary:
  - Target design: `t_trade_signals` stores dynamic daily Taiwan intraday / short-swing candidates. Current implementation still has fixed-pool restrictions that must be migrated.
  - `ticker` is the normalized tradable symbol; Taiwan signals use the 4-digit code without `.TW` / `.TWO`
  - Every signal keeps `analysis_id`, slot/date, ticker, strategy/direction, optional entry/stop/target JSON, and `source_event_ids`
  - Every signal gets `risk_reward_ratio`, `candidate_score`, and `avoid_reason`; downstream monitoring currently requires complete long/short levels, `risk_reward_ratio >= 1.5`, and empty `avoid_reason`
  - Internal `direction=long` means buy-side / 做多, not long-term holding; `entry_zone` is the entry area, `take_profit_zone` is the profit-taking exit area, and `invalidation` is rendered as 停損
  - `quote_fallback_stock_watch` / `context_fallback_stock_watch` may enrich or fill monitor levels only when evidence exists; they must not invent tickers.
  - Deterministic quote/context fallback levels calibrate `take_profit_zone.first` from entry/stop so the first target is at least 1.5R. Structured LLM rows are not silently rewritten; low-R structured rows remain stored with `avoid_reason`.
  - `prior_signal_stock_watch` may fill a missing same-ticker row from recent `t_trade_signals` history. It is downgraded to `confidence=low`, labelled as prior reference, and must require same-day price, volume, and news confirmation before any action.
  - Targeted signal repair for an existing analysis row uses `scripts/run_trade_signal_extraction.ps1 -EnvFile .env -AnalysisId <id> -FixedPoolFallback`; it may combine structured rows, recent quote/context fallback, and prior same-ticker references, while still respecting `raw_json.trust_gate.signals_allowed=false`.
  - `idempotency_key` suppresses duplicate signals for the same analysis/ticker/strategy
  - `t_signal_reviews` is reserved for risk gate / human / model-review decisions
  - `t_signal_outcomes` is reserved for later performance feedback; any strategy report/outcome JSON must use entry-first attribution: ignore target/stop hits before the first entry, then count the first target after entry as win and first stop after entry as loss
  - Order, fill, position state, realized PnL, and unrealized PnL are not implemented here; they belong to future `order-dispatcher-service` state tables.
  - LLM analysis never creates order intents or broker calls directly
- Historical-case RAG:
  - Module: `src/event_relay/rag.py`
  - Current retrieval is hybrid: metadata overlap filters candidates, deterministic local lexical/vector similarity ranks semantic fit, and stored `outcome_json` scores successful past analyses higher. Raw `target_hit` / `stop_hit` statuses alone are neutral unless lifecycle metadata proves they occurred after entry.
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
  - Every day 06:00 (Asia/Taipei, local machine timezone) for U.S. macro release-calendar collection
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
- Repair one existing analysis row that has no stock-monitor signals:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_trade_signal_extraction.ps1 -EnvFile .env -AnalysisId <id> -FixedPoolFallback -EventDays 1 -PriorDays 30`
- Run market context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env`
- Run Taiwan official market-flow context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_market_flow.ps1 -EnvFile .env`
- Run BLS macro context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_bls_macro.ps1 -EnvFile .env`
- Run U.S. macro release calendar once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_macro_calendar.ps1 -EnvFile .env`
- Run Taiwan close context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_close_context.ps1 -EnvFile .env`
- Run retention cleanup once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_retention_cleanup.ps1 -EnvFile .env`

## Known Operational Notes
- X stream may return 429 when connection slots are occupied; auto-heal is enabled.
- OpenAI `insufficient_quota` can occur even with valid key if project billing/entitlement is not active.
- On this Windows workstation, `run_source_bridge.ps1` prefers `Python 3.12` for the bridge because local `Python 3.13` fails TLS verification against `openapi.twse.com.tw`.
