# News Collector (MVP)

## Platform Role

`data-collecting` is the ingestion, enrichment, analysis, and decision-memory center of the financial news platform. It collects market/news/public-record data, stores normalized events, runs scheduled market-analysis and weekly-summary jobs, extracts trade-signal candidates, and maintains the platform's richest documentation set.

It also provides the context collection and Redis write helpers for the
Codex-generated four-hour cross-section news digest. Codex automation writes the
latest successful digest to Redis; this repo does not expose the public API.

It does not own LINE delivery, the public API runtime, frontend rendering, live quote WebSocket monitoring, or broker order placement. Those boundaries are handled by sibling services.

## Total Index

Start with [PROJECT_INDEX.md](PROJECT_INDEX.md) when you need to navigate this repo. It maps the README, specs, memory bank, skills, runbooks, scripts, and sibling-service boundaries in one place.

## Documentation Map

| Need | Start here |
|---|---|
| Whole-repo navigation | [PROJECT_INDEX.md](PROJECT_INDEX.md) |
| Codex/Claude operating rules | [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) |
| Architecture, data flow, source boundaries | [memory-bank/PROJECT_DOCUMENTATION.md](memory-bank/PROJECT_DOCUMENTATION.md) |
| Operational workflows and repeatable runbooks | [memory-bank/workflows.md](memory-bank/workflows.md) |
| Machine restart recovery | [memory-bank/restart-recovery-runbook.md](memory-bank/restart-recovery-runbook.md) |
| Historical-case RAG operations | [memory-bank/rag-operations.md](memory-bank/rag-operations.md) |
| Product/data contracts | [spec/](spec/) |
| Politics topic/thread technical plan | [spec/political-topic-thread-technical-plan.md](spec/political-topic-thread-technical-plan.md) |
| Architecture decision history | [memory-bank/09-decisions/](memory-bank/09-decisions/) |
| Agent and skill workspace | [skills/README.md](skills/README.md) |
| Task board and lessons | [tasks/todo.md](tasks/todo.md), [tasks/lessons.md](tasks/lessons.md) |

## Related Services

| Service | Relationship |
|---|---|
| `news-platform-api` | Reads event, article, analysis, trade-signal, public-record, and candle tables for public API access. |
| `news-display-frontend` | Displays public news, analyses, issue timelines, and market candles through the API. |
| `line-relay-service` | Delivers selected analyses and stock-query responses to LINE users. |
| `stock-monitor-service` | Consumes trade signals and produces live quote/candle/trigger data. |
| `order-dispatcher-service` | Future consumer of reviewed trigger/order intents; broker calls do not live here. |

## Current data sources

1. Official RSS (no API key)
- BBC / Reuters / Fox / NPR plus Taiwan finance feeds from `OFFICIAL_RSS_FEEDS`
- Active Taiwan finance/official RSS feeds include CNA finance, LTN business, ETtoday finance, Anue, Economic Daily News, Newtalk finance, Storm finance, MoneyDJ, CBC, TWSE, and FSC feeds
- RSS news rows are normalized by `news_collector` and written through the bridge into `t_relay_events`
- Reporter names for finance RSS rows can be enriched into short-retention `t_relay_events.raw_json.authors` with `scripts/backfill_relay_event_authors.py`; this is separate from the long-lived society/politics reporter relation tables.
- RSS `--limit` is applied per feed, not globally. Current `.env` uses `OFFICIAL_RSS_FIRST_PER_FEED=true`, so one polling cycle fetches one item per configured feed; if disabled, 27 feeds with `-Limit 5` can return up to 135 RSS items before URL dedupe and topic/date filters.

1a. Free Palestine English issue news (no API key)
- Module: `event_relay.palestine_news`
- Collects English RSS / Google News search rows for Palestine, Gaza, West Bank, and related issue terms
- Writes accepted rows to long-term `t_palestine_news_items`
- `news-platform-api` exposes these rows through `GET /api/timeline/news`; they do not belong in the general finance relay feed or the short-retention `t_relay_events` stream
- Legacy `source=palestine_watch:<source_id>` relay rows can be copied once with `scripts/run_palestine_news.ps1 -BackfillRelay -BackfillOnly`

2. SEC EDGAR tracked filings (no API key, declared User-Agent required)
- Track selected tickers through official SEC ticker mapping + submissions API
- Starter `.env` set watches `NVDA,TSM,AAPL,MSFT,AMD,TSLA`

3. TWSE / MOPS official listed-company announcements (no API key)
- Uses TWSE openapi dataset `上市公司每日重大訊息`
- Starter `.env` set watches the listed-stock side of the fixed market-analysis pool: `2330,2317,2454,2308,2881,2882,2485,3535,3715,2351`

4. X account stream (Bearer token required)
- Track selected accounts with X filtered stream (near real-time)

5. Market context facts (mostly no API key)
- Yahoo chart market proxies, U.S. Treasury yield curve, FRED public CSV macro-regime series, market breadth, SEC companyfacts AI capex proxy, FRED oil-price context, optional EIA inventory context, and TWSE official index/stock/margin context
- Written as stored-only `market_context:*` events into `t_relay_events`, including deterministic `market_context:scorecard`

6. Taiwan society/politics news platform (separate MySQL database)
- Module: `src/news_platform`
- Collects Taiwan society and politics RSS/sitemap/list feeds into `t_news_articles`
- RSS/Atom and sitemap ingestion stores reporter/author names in `authors_json` when the feed exposes explicit author metadata or a high-confidence byline. Reporter identities are also normalized into `t_news_authors` and linked through `t_news_article_authors`; missing byline states are tracked on `t_news_articles.author_extraction_status` and summarized in `t_news_author_coverage_daily`.
- Default source set: LTN, ETtoday, TVBS, CNA, PTS, EBC, Newtalk, and Storm Media for both society and politics
- `NEWSPF_CATEGORIES` or `--categories` controls collection scope; default is `society,politics`
- `KeywordWorker` writes `keywords_json`; `TopicWorker` writes deterministic issue classifications into `topics_json`; optional LLM fallback refines rule-fallback general rows
- Topic MVP uses deterministic `TopicSpec` rules. Existing social/policy topics stay unscoped; politics second-layer topics are scoped to `category=politics` so political terms do not classify unrelated society rows. Rule no-hit rows temporarily fall back by article category: `general_social_news` / 一般社會新聞 or `general_politics_news` / 一般政治新聞.
- Politics second-layer topic IDs are `elections`, `cross_strait_relations`, `foreign_affairs`, `legislative_policy`, `party_politics`, `political_accountability`, `defense_security`, and `public_budget`. Event-thread templates are specified in [spec/political-topic-thread-technical-plan.md](spec/political-topic-thread-technical-plan.md); persistent thread tables are deferred.

7. Four-hour Codex news digest
- `scripts/collect_four_hour_digest_context.py` reads compact context from
  finance relay rows, society/politics articles, celebrity relay rows, and Free
  Palestine long-term issue news.
- Codex automation generates the Traditional Chinese digest from that context.
- `scripts/store_four_hour_digest_to_redis.py` writes versioned digest keys with
  a 15,000 second TTL, then updates the non-expiring latest display key for
  `news-platform-api` to read.
- This digest is not stored in `t_market_analyses` and does not create LINE
  delivery jobs.

## API key requirements

- `X_ENABLED` (master switch for X source; default `false`)
- `SEC_ENABLED` (master switch for SEC tracked-filings source; default `false`)
- `SEC_USER_AGENT` (required when `SEC_ENABLED=true`; SEC asks automated clients to declare a user agent)
- `SEC_TRACKED_TICKERS` (comma-separated tickers, e.g. `NVDA,TSM,AAPL`)
- `SEC_ALLOWED_FORMS` (default high-signal filing set such as `8-K,10-Q,10-K,6-K,20-F`)
- `SEC_MAX_FILINGS_PER_COMPANY` (default `5`)
- `TWSE_MOPS_ENABLED` (master switch for TWSE listed-company major announcements)
- `TWSE_MOPS_TRACKED_CODES` (comma-separated listed company codes, e.g. `2330,2317,2454,2308,2881,2882,2485,3535,3715,2351`)
- `TWSE_MOPS_MAX_ITEMS_PER_COMPANY` (default `5`)
- `X_BEARER_TOKEN` (required only when `X_ENABLED=true`)
- `X_BEARER_TOKEN_FILE` (optional; encrypted local token file, default `.secrets/x_bearer_token.dpapi`)
- `X_ACCOUNTS` (comma-separated usernames or profile URLs)
- `X_MAX_RESULTS_PER_ACCOUNT` (used by one-shot/poll mode only)
- `X_STOP_ON_429` (stop X stream after first 429 in current process)
- `X_AUTO_HEAL_TOO_MANY_CONNECTIONS` (default `true`; when 429 is `TooManyConnections`, auto call `DELETE /2/connections/all` then retry)
- `X_HEAL_COOLDOWN_SECONDS` (default `45`; cooldown between auto-heal actions)
- `X_INCLUDE_REPLIES` / `X_INCLUDE_RETWEETS` (default `false`)
- `X_BACKFILL_ENABLED` (default `true`; replay recent tracked-account tweets into the event store once when bridge starts)
- `X_BACKFILL_MAX_RESULTS_PER_ACCOUNT` (default `10`; startup backfill size per tracked account)
- `TRUTH_SOCIAL_ENABLED` (master switch for Truth Social public account source; default `false`)
- `TRUTH_SOCIAL_ACCOUNTS` (comma-separated handles or profile URLs, e.g. `https://truthsocial.com/@realDonaldTrump`)
- `TRUTH_SOCIAL_MAX_RESULTS_PER_ACCOUNT` (default `10`)
- `TRUTH_SOCIAL_USER_AGENT` (optional browser-style user agent; the public endpoint may reject generic clients)
- No key required for RSS
- No key required for Truth Social public account pages
- No key required for Free Palestine English issue news RSS / Google News search
- No key required for FRED public CSV market-context series
- `SEC_USER_AGENT` is also required when `MARKET_CONTEXT_AI_CAPEX_ENABLED=true`
- `EIA_API_KEY` is optional; when set, oil context includes weekly U.S. crude stocks excluding SPR

## Quick start

```bash
PYTHONPATH=src python -m news_collector.main fetch --source rss --limit 20
PYTHONPATH=src python -m news_collector.main fetch --source sec --limit 20
PYTHONPATH=src python -m news_collector.main fetch --source twse --limit 20
PYTHONPATH=src python -m news_collector.main fetch --source x --limit 20
PYTHONPATH=src python -m news_collector.main fetch --source all --limit 20 --pretty
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source rss --limit 20
```

Safe first run (recommended):

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source rss --limit 3 --log-level INFO --pretty
```

## Taiwan Society/Politics News Platform

This path is separate from `event_relay`; it writes to `NEWSPF_MYSQL_DATABASE` and does not push LINE messages.

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --smoke
$env:PYTHONPATH='src'; python -m news_platform.main --smoke --categories politics
$env:PYTHONPATH='src'; python -m news_platform.main --once
$env:PYTHONPATH='src'; python -m news_platform.main --once --categories politics
$env:PYTHONPATH='src'; python -m news_platform.main --extract-keywords --classify-topics
$env:PYTHONPATH='src'; python -m news_platform.main --llm-topic-fallback
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources all
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources public_budget
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources healthcare
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources justice
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources housing
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources low_birthrate
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources drug_abuse
$env:PYTHONPATH='src'; python -m news_platform.main --public-records-smoke --public-sources cwa_weather
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources all
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources public_budget
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources healthcare
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources justice
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources housing
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources low_birthrate
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources drug_abuse
$env:PYTHONPATH='src'; python -m news_platform.main --collect-public-records --public-sources cwa_weather
$env:PYTHONPATH='src'; python -m news_platform.main --link-public-records
$env:PYTHONPATH='src'; python -m news_platform.main --loop
```

Loop mode collects the default public-record source set once per local day, then runs article-record linking each crawl cycle.

Storage:
- `t_news_sources`: source metadata
- `t_news_articles`: article rows, including `authors_json`, author extraction status fields, `keywords_json`, `topics_json`, `topic_classified_by`, and `topic_classified_at`
- `t_news_authors`: normalized source-scoped reporter/author identities
- `t_news_article_authors`: article-to-author relation rows
- `t_news_author_coverage_daily`: daily source/category reporter-name coverage metrics
- `t_public_records`: structured official records such as legislative bills, court judgments, fraud lists, accident rows, population indicators, or housing indicators
- `t_news_article_public_record_links`: many-to-many article-to-record links with `relation_type`, `confidence`, `matched_by`, and `evidence_json`
- `topics_json` is an ordered JSON array like `[{"topic_id":"fraud","label":"詐騙","score":1.3,"source":"rule"}]`
- Rule no-hit society rows use `[{"topic_id":"general_social_news","label":"一般社會新聞","score":0.0,"source":"rule_fallback"}]`
- Rule no-hit politics rows use `[{"topic_id":"general_politics_news","label":"一般政治新聞","score":0.0,"source":"rule_fallback"}]`
- LLM fallback results use `source:"llm"` plus `provider` and `model`; if LLM still finds no specific topic, the row stays in its category-specific general topic with `source:"llm_fallback"`
- Structured official datasets do not go into `t_news_articles`; they are upserted into `t_public_records` and linked back to related articles through `t_news_article_public_record_links`.
- Official public-record sources: Legislative Yuan legal proposals (`ly_bills`), budget/public-resource-filtered Legislative Yuan proposals (`ly_budget_bills`), healthcare-filtered Legislative Yuan proposals (`ly_healthcare_bills`), NPA 165 fraud-rumor open data (`npa_fraud_rumors`), NPA A1 traffic accident open data (`npa_traffic_a1`), NPA A2 traffic accident monthly statistics (`npa_traffic_a2_stats`), NPA drunk-driving annual statistics (`npa_drunk_driving_stats`), NPA fraud blocked-domain statistics (`npa_fraud_blocked_domain_stats`), NPA fraud enforcement dashboard statistics (`npa_fraud_enforcement_stats`), NPA drug-case statistics (`npa_drug_case_stats`), NHI healthcare capacity sources (`nhi_hospital_nursing_staff`, `nhi_hospital_bed_occupancy`), MOHW annual healthcare capacity sources (`mohw_hospital_workforce`, `mohw_clinic_workforce`, `mohw_hospital_beds`, `mohw_nursing_staff_stats`), MOJ prosecution disposition statistics (`moj_prosecution_disposition_stats`), Agency of Corrections daily custody statistics (`mojac_daily_custody`), Taipei housing price index (`taipei_housing_price_index`), RIS birth monthly statistics (`ris_birth_monthly_stats`), and CWA typhoon/earthquake reports (`cwa_typhoon_report`, `cwa_earthquake_report`). Use `--public-sources public_budget`, `--public-sources healthcare`, `--public-sources justice`, `--public-sources housing`, `--public-sources low_birthrate`, `--public-sources drug_abuse`, or `--public-sources cwa_weather` for focused subsets.
- CWA weather sources require `CWA_AUTHORIZATION` in local `.env`. Optional dataset overrides are `CWA_TYPHOON_DATASET_ID` and `CWA_EARTHQUAKE_DATASET_ID`.
- Article-record matching uses deterministic high-precision rules for Legislative Yuan bills, healthcare-filtered Legislative Yuan bills, and NPA 165 fraud-rumor records. Links are written with source-specific `matched_by` values and evidence in `evidence_json`.

Optional table-name env keys:
- `NEWSPF_MYSQL_PUBLIC_RECORD_TABLE=t_public_records`
- `NEWSPF_MYSQL_ARTICLE_RECORD_LINK_TABLE=t_news_article_public_record_links`

Optional reporter/detail-page enrichment env keys:
- `NEWSPF_AUTHOR_DETAIL_BACKFILL_ENABLED=true`
- `NEWSPF_AUTHOR_DETAIL_BACKFILL_BATCH_SIZE=30`
- `NEWSPF_AUTHOR_DETAIL_BACKFILL_SOURCES=cna,storm,newtalk,ltn,ettoday,tvbs,ebc,ctee,pts`
- `NEWSPF_AUTHOR_DETAIL_BACKFILL_SLEEP_SECONDS=0.05`

Optional LLM fallback env keys:
- `NEWSPF_TOPIC_LLM_ENABLED=false`
- `NEWSPF_TOPIC_LLM_PROVIDER_ORDER=openai,anthropic`
- `NEWSPF_TOPIC_OPENAI_MODEL=gpt-5-nano`
- `NEWSPF_TOPIC_ANTHROPIC_MODEL=claude-haiku-4-5-20251001`
- `NEWSPF_TOPIC_LLM_BATCH_SIZE=50`
- `NEWSPF_TOPIC_LLM_MIN_CONFIDENCE=0.55`
- `NEWSPF_TOPIC_OPENAI_API_KEY` / `OPENAI_API_KEY`
- `NEWSPF_TOPIC_ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY`

## Event Relay / Data Service

This repo now includes a Python data relay service:
- Receive compatibility/manual events via HTTP `POST /events`
- Persist events in MySQL event table
- Store X / Truth Social public-figure posts, market snapshots, and generated analyses
- Python does not own LINE webhook or LINE push delivery; those belong to the Java system
- `t_relay_events` is pure event storage; it has no LINE push queue/status columns
- Auto-create social post table:
  - `t_x_posts`
- Auto-create market snapshot table for US index analysis:
  - `t_market_index_snapshots`
- Auto-create stored market analysis table:
  - `t_market_analyses`

Run:

```powershell
pip install -e .
powershell -ExecutionPolicy Bypass -File .\scripts\run_event_relay.ps1
```

Run crawler bridge (`RSS + SEC + TWSE/MOPS + X stream + Truth Social poll + US index tracker`) and write normalized events directly to MySQL:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1 -PollIntervalSeconds 300 -Limit 5 -UsIndexPollIntervalSeconds 30
```

For RSS, `-Limit 5` means up to 5 items per configured feed. SEC/TWSE/X/Truth Social keep their existing per-source or per-account limit behavior.

Run the Free Palestine English issue-news collector once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 20
```

Register the recurring local crawler:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_market_analysis_tasks.ps1 -Force
```

This creates `NewsCollector-PalestineNews`, starting at 06:10 local/Taiwan time
and repeating every 3 hours. It writes only to `t_palestine_news_items`.

Backfill legacy relay rows into long-term storage once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -BackfillRelay -BackfillOnly
```

Safe dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 5 -DryRun
```

Optional feed override:

```text
PALESTINE_NEWS_RSS_FEEDS=google_news_en|https://news.google.com/rss/search?...;al_jazeera_en|https://www.aljazeera.com/xml/rss/all.xml
```

X source is now consumed by filtered stream (near real-time) with auto reconnect/backoff.
Bridge startup also runs a one-shot X backfill before connecting the filtered stream, so tweets published while the bridge was down can be replayed into `t_relay_events` and `t_x_posts` without the event relay API running.
When X returns `429` with `connection_issue=TooManyConnections`, bridge will auto-heal by terminating stale stream connections and retrying (configurable by `X_AUTO_HEAL_TOO_MANY_CONNECTIONS`).
Truth Social public account polling uses `source=truthsocial:<handle>` and writes both `t_relay_events` and the existing social-post table `t_x_posts` with `tweet_id=truthsocial-<status_id>`. Raw status JSON is preserved in `raw_json`; display text is converted from Truth Social HTML to plain text, with readable media-only fallbacks for image/video posts.
SEC tracked filings use the official SEC `company_tickers.json` mapping plus `data.sec.gov/submissions/CIK##########.json`, then write high-signal filings directly into `t_relay_events`.
TWSE/MOPS tracked announcements use the official TWSE openapi `t187ap04_L` dataset (`上市公司每日重大訊息`) and write tracked company disclosures directly into `t_relay_events`.
US index chain tracks DJIA and S&P 500 open/close, writes normalized stored-only events into `t_relay_events`, and stores structured quote rows in `t_market_index_snapshots` for same-day analysis.
All Python source events are stored-only. No LINE delivery is attempted from this repo.

MySQL defaults (editable in `.env`):
- `RELAY_MYSQL_ENABLED=true`
- `RELAY_MYSQL_HOST=127.0.0.1`
- `RELAY_MYSQL_PORT=3306`
- `RELAY_MYSQL_USER=root`
- `RELAY_MYSQL_PASSWORD=root`
- `RELAY_MYSQL_DATABASE=news_relay`
- `RELAY_MYSQL_EVENT_TABLE=t_relay_events`
- `RELAY_MYSQL_PALESTINE_NEWS_TABLE=t_palestine_news_items`
- `RELAY_MYSQL_X_TABLE=t_x_posts`
- `RELAY_MYSQL_MARKET_TABLE=t_market_index_snapshots`
- `RELAY_MYSQL_ANALYSIS_TABLE=t_market_analyses`
- `RELAY_RETENTION_ENABLED=true`
- `RELAY_RETENTION_KEEP_DAYS=7`
- `RELAY_DISPATCH_INTERVAL_SECONDS=300`

Heroku deploy notes:
- `Procfile` already runs web dyno: `python -m event_relay.main`
- Relay port supports Heroku `PORT` automatically (fallback from `RELAY_PORT`)

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:18090/healthz
```

Data-source freshness health:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_data_source_health.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_data_source_health.ps1 -EnvFile .env -Json
```

This read-only report checks MySQL freshness for finance/public RSS, international RSS, X, SEC, TWSE/MOPS, market-context facts, market analyses, society/politics article feeds, public records, article-record links, and local Python process counts. Use `-FailOnWarn` or `-FailOnStale` for scheduled monitoring.

Machine restart recovery:
- Use `memory-bank/restart-recovery-runbook.md` before rediscovering restart steps.
- It covers restarting relay/bridge/news-platform loops, scheduled-task checks, society/politics freshness, finance RSS freshness, and Taiwan pre-open analysis verification.

Retention cleanup:
- Deletes rows older than `RELAY_RETENTION_KEEP_DAYS` from `t_relay_events` and `t_x_posts`.
- The event-relay maintenance loop runs this cleanup once per local day.
- A fixed Windows scheduled task can run the same cleanup independently.

Run once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_retention_cleanup.ps1 -EnvFile .env
```

Register daily cleanup at `00:10` local time:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_retention_cleanup_task.ps1 -At "00:10" -Force
```

Post sample event:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\post_event_sample.ps1
```

Note:
- Payload with `test_only=true` (or `source=manual_test*`) is log-only and will not be inserted into MySQL tables.

Local console runner (recommended for daily use):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_console.ps1
```

Watch mode (polling, low risk defaults):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_local_console.ps1 -Watch -IntervalSeconds 180
```

Notes:
- Default `Source=rss` and `Limit=3` to reduce rate-limit risk on first runs.
- Combined output is saved to `runtime/logs/`.

## X account stream

Save X Bearer token in encrypted local file (Windows DPAPI):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\save_x_token.ps1
```

Or pass token directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\save_x_token.ps1 -BearerToken "YOUR_X_BEARER_TOKEN"
```

One-shot fetch (debug/poll mode, optional):

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source x --limit 10 --pretty
```

Required `.env` keys for X:
- `X_ENABLED=true`
- `X_BEARER_TOKEN_FILE=.secrets/x_bearer_token.dpapi` (or `X_BEARER_TOKEN`)
- `X_ACCOUNTS=https://x.com/elonmusk,https://x.com/realDonaldTrump,https://x.com/aleabitoreddit`
- `X_AUTO_HEAL_TOO_MANY_CONNECTIONS=true` (recommended)
- `X_HEAL_COOLDOWN_SECONDS=45`
- `X_BACKFILL_ENABLED=true`
- `X_BACKFILL_MAX_RESULTS_PER_ACCOUNT=10`

If you get `HTTP 402 Payment Required`, your X developer project/app does not currently have the required paid access for these read endpoints.

## Truth Social public account source

One-shot fetch:

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source truthsocial --limit 10 --pretty
```

Required `.env` keys:
- `TRUTH_SOCIAL_ENABLED=true`
- `TRUTH_SOCIAL_ACCOUNTS=https://truthsocial.com/@realDonaldTrump`

The bridge stores Truth Social rows with `source=truthsocial:realdonaldtrump` in `t_relay_events` and mirrors them into `t_x_posts` for the existing public-figure/social-post analysis path. This source does not require an API token, but the public endpoint is protected against non-browser clients, so keep a browser-style `TRUTH_SOCIAL_USER_AGENT` if fetches return `403`.

## SEC tracked filings

One-shot fetch:

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source sec --limit 10 --pretty
```

Required `.env` keys for SEC:
- `SEC_ENABLED=true`
- `SEC_USER_AGENT=news-collector/0.1 local-admin@example.com`
- `SEC_TRACKED_TICKERS=NVDA,TSM,AAPL,MSFT,AMD,TSLA`
- `SEC_ALLOWED_FORMS=8-K,8-K/A,10-Q,10-Q/A,10-K,10-K/A,6-K,6-K/A,20-F,20-F/A`
- `SEC_MAX_FILINGS_PER_COMPANY=5`

Notes:
- This source uses official SEC endpoints only.
- It does not need an API key.
- The current MVP tracks selected tickers and writes the latest high-signal forms directly into `t_relay_events` through the crawler bridge.

## TWSE / MOPS official announcements

One-shot fetch:

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source twse --limit 10 --pretty
```

Required `.env` keys for TWSE/MOPS:
- `TWSE_MOPS_ENABLED=true`
- `TWSE_MOPS_TRACKED_CODES=2330,2317,2454,2308,2881,2882,2485,3535,3715,2351`
- `TWSE_MOPS_MAX_ITEMS_PER_COMPANY=5`

Notes:
- This source uses the official TWSE openapi dataset `https://openapi.twse.com.tw/v1/opendata/t187ap04_L`.
- Current MVP covers TWSE listed-company daily material announcements.
- Events flow directly into `t_relay_events` through the crawler bridge.

## Weekly macro summary (AI, stored only)

Generate one weekly summary from `t_relay_events` and store it in `t_market_analyses`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_summary.ps1 -Force -DryRun
```

Or trigger it through the running relay service:

```powershell
'{"kind":"weekly","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"
```

Prompt pipeline:
- Read skill docs:
  - `skills/macro-weekly-summary-skill/SKILLS.md` (prompt-loader compatibility file; `SKILL.md` is the skill entry)
  - `skills/line-brief-format-skill/line-weekly-brief.md`
- Weekly output uses a weekly-specific three-section contract:
  - `週總經` -> `下週台股配置` -> `下週觀察清單`
  - Each section should connect evidence -> mechanism -> Taiwan implication.
  - Weekly reports are allocation/watchlist briefs and should not output intraday entry / take-profit / stop-loss prices.
- Compile as:
  - `runtime/prompts/weekly_summary_system_prompt.txt`
  - `runtime/prompts/weekly_summary_reusable_prompt.txt`
- Send to OpenAI Responses API.
- OpenAI calls request the Responses API `web_search` tool by default so the model can verify fresh gaps beyond `t_relay_events`; set `LLM_WEB_SEARCH_ENABLED=false` to disable. If the API/project does not support the tool, the caller retries once without web search.
- Store the weekly summary in `t_market_analyses` with:
  - `analysis_date=YYYY-MM-DD` for the target Sunday delivery date
  - `analysis_slot=weekly_tw_preopen`
  - `scheduled_time_local=05:10` (`HH:MM`, no weekday prefix)
  - `raw_json.section_contract=["週總經","下週台股配置","下週觀察清單"]`
  - `raw_json.token_usage` for provider/model/token telemetry

Weekly summary env keys:
- `LLM_PROVIDER` (`openai` or `anthropic`; weekly loads `.env` before resolving the provider)
- `WEEKLY_SUMMARY_OPENAI_API_KEY` (optional; fallback to `OPENAI_API_KEY`)
- `WEEKLY_SUMMARY_OPENAI_API_KEY_FILE` (default `.secrets/openai_api_key.dpapi`, Windows DPAPI encrypted key)
- `WEEKLY_SUMMARY_MODEL` (default `gpt-5`)
- `ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY_FILE` (used when `LLM_PROVIDER=anthropic` or weekly runtime failover switches to Claude)
- `WEEKLY_SUMMARY_RUNTIME_FAILOVER_ENABLED` (default `true`; OpenAI quota/rate/5xx failures retry once on Anthropic when configured)
- `WEEKLY_SUMMARY_LOOKBACK_DAYS` (default `7`)
- `WEEKLY_SUMMARY_MAX_EVENTS` (default `120`)
- `WEEKLY_SUMMARY_WEEKDAY` (0=Mon ... 6=Sun, default `5` - Saturday)
- `WEEKLY_SUMMARY_HOUR` (default `23`)
- `WEEKLY_SUMMARY_MINUTE` (default `0`)
- `WEEKLY_SUMMARY_WINDOW_MINUTES` (default `20`)
- `LLM_WEB_SEARCH_ENABLED` (default `true` for OpenAI; set `false` for local-only analysis)

Weekly schedule helper (Windows Task Scheduler):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_weekly_summary_task.ps1 -TaskName "NewsCollector-WeeklySummary" -DayOfWeek "Saturday" -At "23:00" -Force
```

## Scheduled market analysis (AI, stored only)

Generate market analysis at Taiwan-local checkpoints:
- `05:00` for U.S. close context; if TW is closed and that U.S. session was open, this row is Java-delivery eligible
- `07:30` for Taiwan pre-open context
- `15:30` for Taiwan close review context

Current behavior:
- Reads recent events from `t_relay_events`
- Reads recent DJIA / S&P 500 rows from `t_market_index_snapshots`
- Reads stored-only `market_context:*` source facts from the recent `t_relay_events` window
- Builds a quota-managed context pack before RAG/prompting so `market_context:scorecard`, market context, and important official rows are kept ahead of general news overflow
- Selects the analysis provider/model through `llm_quota_router`: OpenAI is primary by default, Claude is fallback, provider cost checks run when Admin API keys and monthly budgets are configured, then the router records its choice in `raw_json.model_router`
- Applies compact context automatically when Anthropic is selected, reducing event rows, market rows, RAG examples, and raw JSON detail while preserving scorecard / market_context / official / high-importance items
- Runs deterministic `stage0_thesis_selector` before LLM stages so the prompt answers 1-2 current core tensions first
- Optionally retrieves hybrid historical examples from `t_event_embeddings` and `t_analysis_embeddings` using metadata overlap, vector similarity, and stored outcome score; examples are analogues in the stage2 transmission prompt
- Calls OpenAI Responses API with web search enabled by default for missing/current fact verification
- Runs `claim_verifier` after generation and stores evidence coverage for numbers, dates, and tickers in `raw_json.claim_verifier`
- Applies `raw_json.trust_gate`: when `claim_verifier.ok=false`, the analysis is still stored for audit/debug but `push_enabled=false` and trade-signal extraction is skipped
- Stores the generated analysis in `t_market_analyses`
- Uses `push_enabled` as Java delivery eligibility: `pre_tw_open=1`, `macro_daily=1`, `us_close=1` only when TW is closed and the relevant U.S. close session was open, `tw_close=0`
- Runs a built-in 2026 TWSE / NYSE calendar guard before any LLM call:
  - TW closed + relevant U.S. close session open: only `us_close`
  - U.S. close session closed + TW open: only Taiwan analysis (`pre_tw_open` / `tw_close`); the pre-open prompt intentionally does not include stale `us_close`
  - both closed: `pre_tw_open` task writes `macro_daily` with `push_enabled=1`
  - Sunday: market analysis skips; weekly summary owns the day
- Keeps regular-day `us_close` analysis stored and injects it into the next Taiwan pre-open prompt only when that U.S. close session was open; TW-holiday `us_close` rows are eligible for Java LINE delivery
- Target direction: Codex should generate dynamic Taiwan intraday / short-swing trade candidates from collected `t_relay_events`, market context, quote evidence, historical/RAG context, and model judgment, then store reviewable rows in `t_trade_signals`.
- The old fixed ten-stock pool was only an observation/debugging aid and is superseded by `spec/market-analysis-dynamic-trade-candidates.md`.
- Runtime candidate generation is now dynamic: valid Taiwan candidates are normalized to four-digit stock codes, must be evidence-backed, and are not padded from the historical fixed pool.
- `stock-monitor-service` should monitor the top five ranked `t_trade_signals` candidates that pass the deterministic risk gate.
- Future `order-dispatcher-service` trading must cap concurrent traded symbols at three and must remain sandbox/paper until order, fill, position, PnL, reconciliation, and kill-switch state are implemented.
- Daily visible market-analysis text follows the author-style flow for readability: `今日主命題` -> `三個證據` -> `市場正在定價什麼` -> `台股傳導` -> `反證條件` -> `風險與資料缺口`; `三個證據` must contain exactly three bullets connecting source fact -> market mechanism -> why it matters now. The daily body should not expose entry/stop/target lists unless a separate trading UI asks for them.
- Daily visible text must translate internal labels such as `market scorecard`, `scorecard +4`, `market_context`, `07:20 market_context`, `analysis_slot`, `scheduled_time_local`, and `raw_json` into plain Chinese market implications.
- Does not push or create LINE delivery jobs; Java owns user-facing delivery
- Treats `t_relay_events` as primary local evidence, not as the only possible source of truth; prompts require explicit data-gap labeling when context is insufficient

Manual backfill through the running relay service:

```powershell
'{"kind":"market","slot":"pre_tw_open","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"
'{"kind":"market","slot":"us_close","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"
'{"kind":"market","slot":"tw_close","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"
'{"kind":"market","slot":"macro_daily","force":true}' | curl.exe -X POST http://127.0.0.1:18090/analysis/backfill -H "Content-Type: application/json" -d "@-"
```

Trade signal storage:
- `t_trade_signals` is the reviewable daily candidate table for Taiwan intraday / short-swing monitoring. The target design allows dynamic candidates, subject to evidence, ranking, validation, and review gates.
- `ticker` is the normalized tradable symbol. For Taiwan signals this is the 4-digit stock code such as `2330`; `.TW` / `.TWO` suffixes are stripped and market type is stored in `market`.
- Signals start as `status=pending_review`; they are not orders.
- Each signal carries `analysis_id`, `analysis_date`, `analysis_slot`, `ticker`, `strategy_type`, `direction`, optional entry/stop/target JSON, and `source_event_ids`.
- Each signal also stores deterministic `risk_reward_ratio`, `candidate_score`, and `avoid_reason`.
  `risk_reward_ratio` uses `entry_zone.high` for long signals and
  `entry_zone.low` for short signals, then compares against
  `invalidation.price` and `take_profit_zone.first`.
- `stock-monitor-service` enables monitoring only for complete long/short rows
  with `risk_reward_ratio >= 1.5` and no `avoid_reason`; lower-quality rows are
  still kept for audit and review.
- Deterministic quote/context fallback rows calibrate `take_profit_zone.first`
  from the generated entry/stop levels so their first target is at least 1.5R;
  structured LLM rows are not silently adjusted and remain gated when R is low.
- For Taiwan pre-open output, internal `direction=long` means buy-side / 做多, not long-term holding. `strategy_type=swing|medium` controls 波段/中線 wording. `entry_zone` is entry area, `take_profit_zone` is profit-taking exit area, and `invalidation` is shown as 停損.
- Fallback rows may enrich or fill monitor levels only when evidence exists. They still start as `pending_review` and are not orders.
- `idempotency_key` prevents duplicate signals for the same analysis/ticker/strategy.
- `t_signal_reviews` and `t_signal_outcomes` are separate follow-up tables for risk gate / human review and performance feedback.
- LLM output stops at signal creation. Order intents and broker calls must be created only after independent review/risk approval.

Pre-open market context collector:
- Module: `event_relay.market_context`
- Writes stored-only source facts into `t_relay_events` with `source=market_context:*`
- Sources currently included:
  - Yahoo chart snapshots for NASDAQ Composite, NASDAQ 100, SOX, VIX, DXY, WTI, Gold, key semiconductor ADR/stocks, and risk proxies such as KRE / XLF / HYG / LQD / TLT / QQQ / SPY / IWM
  - U.S. Treasury official daily yield curve XML for 2Y / 10Y / 30Y and 10Y-2Y spread
  - FRED public CSV series for Fed target range, SOFR, 2Y/10Y, Fed balance sheet, RRP, TGA, reserve balances, financial conditions, credit spreads, and VIX close
  - Market breadth proxies from RSP-SPY, QQEW-QQQ, and IWM-SPY relative daily/1M/3M return spreads
  - SEC companyfacts capex proxy for AI hyperscalers from `MARKET_CONTEXT_AI_CAPEX_TICKERS`
  - FRED oil context for WTI, Brent, and Brent-WTI spread; optional EIA inventory context for U.S. crude stocks excluding SPR
  - TWSE official OpenAPI for Taiwan index groups, tracked stocks, and margin balances
- Emits one deterministic `market_context:scorecard` event with `breadth_health`, `ai_capex_quality`, `energy_shock_risk`, `credit_stress`, and `liquidity_impulse` scores on a -2..+2 scale
- Optional FRED controls:
  - `MARKET_CONTEXT_FRED_ENABLED=false` disables FRED context
  - `MARKET_CONTEXT_FRED_SERIES_IDS=SOFR,DGS2,BAMLH0A0HYM2` limits FRED series
- Optional structural controls:
  - `MARKET_CONTEXT_BREADTH_ENABLED=false` disables market-breadth context
  - `MARKET_CONTEXT_AI_CAPEX_ENABLED=false` disables SEC companyfacts AI capex context
  - `MARKET_CONTEXT_AI_CAPEX_TICKERS=MSFT,GOOGL,META,AMZN` overrides the default hyperscaler set
  - `MARKET_CONTEXT_OIL_SUPPLY_ENABLED=false` disables oil price/inventory context
  - `MARKET_CONTEXT_SCORECARD_ENABLED=false` disables the deterministic scorecard event
  - `EIA_API_KEY` enables weekly U.S. crude stocks excluding SPR; without it, inventory is recorded as a data gap

Official Taiwan market-flow collector:
- Module: `event_relay.tw_market_flow`
- Writes stored-only source facts into `t_relay_events`
- Sources currently included:
  - TWSE official/RWD datasets for three major institutional trading, margin trading, foreign ownership, and SBL availability
  - TPEx official OpenAPI datasets for margin/SBL, institutional trading, and institutional summaries
  - TAIFEX official OpenAPI datasets for major institutional futures/options positioning and open interest

BLS macro collector:
- Module: `event_relay.bls_macro`
- Writes one stored-only source fact per latest monthly observation into `t_relay_events`
- Uses BLS Public Data API v2 with optional `BLS_API_KEY`

U.S. macro release-calendar collector:
- Module: `event_relay.macro_calendar`
- Writes future macro and watched-earnings release dates into long-lived `t_macro_release_calendar`
- Covers CPI, PPI, Employment Situation / nonfarm payrolls, and retail sales
- Also stores watched heavyweight earnings rows as `indicator_code=earnings_<symbol>` using Nasdaq daily earnings calendar plus optional manual JSON overrides
- LINE reminder delivery is owned by `line-relay-service`; Python does not push LINE

Run context collection once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_market_flow.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_bls_macro.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_macro_calendar.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_close_context.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_cwa_weather.ps1 -EnvFile .env
```

Run once manually:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot us_close -Force
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot pre_tw_open -Force
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot tw_close -Force
```

Backfill trade signals from existing structured analyses:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_trade_signal_extraction.ps1 -EnvFile .env -Days 14 -Limit 50
```

Prompt snapshots:
- `runtime/prompts/market_analysis_us_close_system_prompt.txt`
- `runtime/prompts/market_analysis_us_close_user_prompt.txt`
- `runtime/prompts/market_analysis_pre_tw_open_system_prompt.txt`
- `runtime/prompts/market_analysis_pre_tw_open_user_prompt.txt`
- `runtime/prompts/market_analysis_tw_close_system_prompt.txt`
- `runtime/prompts/market_analysis_tw_close_user_prompt.txt`

Market analysis env keys:
- `MARKET_ANALYSIS_MODEL` (default `gpt-5`)
- `MARKET_ANALYSIS_MODEL_ROUTER_ENABLED` (default `true`)
- `MARKET_ANALYSIS_PRIMARY_PROVIDER` (default `openai`; set `anthropic` only for manual Claude-first routing)
- `MARKET_ANALYSIS_PROVIDER_ORDER` (optional comma-separated order, e.g. `openai,anthropic`)
- `MARKET_ANALYSIS_OPENAI_MODELS` / `MARKET_ANALYSIS_ANTHROPIC_MODELS` (optional comma-separated fallback model order per provider)
- `MARKET_ANALYSIS_OPENAI_MONTHLY_BUDGET_USD` / `MARKET_ANALYSIS_ANTHROPIC_MONTHLY_BUDGET_USD` (optional; enables cost-based routing when paired with Admin API keys)
- `MARKET_ANALYSIS_OPENAI_ADMIN_KEY` / `MARKET_ANALYSIS_ANTHROPIC_ADMIN_KEY` (optional; used only for provider cost checks)
- `MARKET_ANALYSIS_LLM_MIN_REMAINING_USD` or provider-specific `MARKET_ANALYSIS_OPENAI_MIN_REMAINING_USD` / `MARKET_ANALYSIS_ANTHROPIC_MIN_REMAINING_USD` (default `0`)
- `MARKET_ANALYSIS_REQUIRE_QUOTA_CHECK` (default `false`; when `true`, configured budgets require a successful Admin API check)
- `MARKET_ANALYSIS_MODEL_ROUTER_TIMEOUT_SECONDS` (default `8`, clamped to `2-30`)
- `MARKET_ANALYSIS_ANTHROPIC_CONTEXT_MODE` (default `compact`; set `full` to send the normal OpenAI-sized context to Claude)
- `MARKET_ANALYSIS_ANTHROPIC_MAX_EVENTS` (default `55`; compact-mode prompt event limit)
- `MARKET_ANALYSIS_ANTHROPIC_MAX_MARKET_ROWS` (default `12`)
- `MARKET_ANALYSIS_ANTHROPIC_RAG_K` (default `2`)
- `MARKET_ANALYSIS_ANTHROPIC_EVENT_SUMMARY_CHARS` (default `500`)
- `MARKET_ANALYSIS_LOOKBACK_HOURS` (default `24`)
- `MARKET_ANALYSIS_MAX_EVENTS` (default `120`)
- `MARKET_ANALYSIS_CONTEXT_PACK_ENABLED` (default `true`)
- `MARKET_ANALYSIS_CONTEXT_PACK_CANDIDATE_LIMIT` (default `MARKET_ANALYSIS_MAX_EVENTS * 3`)
- `MARKET_ANALYSIS_MAX_MARKET_ROWS` (default `24`)
- `MARKET_ANALYSIS_WINDOW_MINUTES` (default `25`)
- `MARKET_ANALYSIS_RAG_ENABLED` (default `true`)
- `MARKET_ANALYSIS_RAG_K` (default `5`)
- `MARKET_ANALYSIS_RAG_MIN_SIMILARITY` (default `0.22`)
- `MARKET_ANALYSIS_RAG_CANDIDATE_LIMIT` (default `500`)
- `MARKET_ANALYSIS_RAG_VECTOR_WEIGHT` / `MARKET_ANALYSIS_RAG_METADATA_WEIGHT` / `MARKET_ANALYSIS_RAG_OUTCOME_WEIGHT` (defaults `0.62` / `0.25` / `0.13`)
- `MARKET_ANALYSIS_RAG_METADATA_FILTER_THRESHOLD` (default `0.10`)
- `MARKET_ANALYSIS_RAG_INCLUDE_ANALYSES` (default `true`)
- `RAG_EMBEDDING_MODEL` (default `local-hash-v1`)
- `RAG_EMBEDDING_DIMENSIONS` (default `128`)
- `RAG_INDEX_LOOKBACK_DAYS` (default `30`)
- `RAG_INDEX_EVENT_LIMIT` (default `500`)
- `RAG_INDEX_ANALYSIS_LIMIT` (default `100`)
- `LLM_WEB_SEARCH_ENABLED` (default `true` for OpenAI; set `false` for local-only analysis)
- `LLM_TIMEOUT_SECONDS` (default `120`, configured `.env` value `600`, shared OpenAI/Anthropic HTTP timeout; clamped to `15-600`)
- `MARKET_CONTEXT_TWSE_CODES` (optional; defaults to `TWSE_MOPS_TRACKED_CODES`)
- `MARKET_CONTEXT_TW_YAHOO_SYMBOLS` (optional Taiwan quote/context symbols used as a dynamic fallback preference list; it is not a fixed trading universe)
- `MARKET_ANALYSIS_EXCLUDED_TICKERS` (default `4749`; comma-separated tickers excluded from visible stock analysis)
- `MARKET_ANALYSIS_CLAIM_GATE_ENABLED` (default `true`; set `false` only for emergency debugging to bypass the `claim_verifier.ok=false` delivery/signal block)
- `MARKET_CONTEXT_ANALYSIS_SLOT` (default `market_context_pre_tw_open`)
- `MARKET_CONTEXT_SCHEDULED_TIME` (default `07:20`)
- `MARKET_CONTEXT_TIMEOUT_SECONDS` (default `15`)
- `MARKET_CONTEXT_BREADTH_ENABLED` (default `true`)
- `MARKET_CONTEXT_AI_CAPEX_ENABLED` (default `true`; requires `SEC_USER_AGENT`)
- `MARKET_CONTEXT_AI_CAPEX_TICKERS` (default `MSFT,GOOGL,META,AMZN`)
- `MARKET_CONTEXT_OIL_SUPPLY_ENABLED` (default `true`)
- `MARKET_CONTEXT_SCORECARD_ENABLED` (default `true`)
- `EIA_API_KEY` (optional; enables EIA weekly crude inventory context)
- `BLS_API_KEY` (optional)
- `BLS_SERIES_IDS` (optional comma-separated subset of the built-in BLS mapping)
- `BLS_TIMEOUT_SECONDS` (default inherited by script as `30`)
- `MACRO_CALENDAR_BLS_YEARS` (optional comma-separated BLS calendar years; defaults to current Taipei year and next year)
- `MACRO_CALENDAR_TIMEOUT_SECONDS` (default inherited by script as `30`)
- `MACRO_CALENDAR_EARNINGS_ENABLED` (default `true`; set `false` to collect only macro release dates)
- `MACRO_CALENDAR_EARNINGS_SYMBOLS` (optional; comma-separated `SYMBOL` or `SYMBOL:Display Name:Market:Importance`; defaults to calendar-tracking symbols `NVDA`, `AAPL`, `MSFT`, `AMZN`, `GOOGL`, `META`, `TSLA`, `AVGO`, `AMD`, `ASML`, `QCOM`, `MU`, `ORCL`, `ARM`, `TSM`, `2330`, `2317`, `2454`, `2308`, `2382`, `3711`, `3231`, `6669`, `2303`, `2881`, `2882`, `2891`)
- `MACRO_CALENDAR_EARNINGS_LOOKAHEAD_DAYS` (default `75`; Nasdaq earnings-calendar lookahead window)
- `MACRO_CALENDAR_EARNINGS_MANUAL_FILE` (optional JSON file for confirmed/manual earnings events such as Taiwan local heavyweight stocks)
- `RELAY_MYSQL_MACRO_CALENDAR_TABLE` (default `t_macro_release_calendar`)
- `TW_CLOSE_CONTEXT_SOURCE_PREFIXES` (optional comma-separated source prefixes)
- `TW_CLOSE_CONTEXT_LOOKBACK_DAYS` (default `2`)
- `TW_CLOSE_CONTEXT_MAX_EVENTS` (default `200`)
- `WEEKLY_SUMMARY_OPENAI_API_KEY_FILE` / `MARKET_ANALYSIS_OPENAI_API_KEY_FILE` for DPAPI secret fallback

Register daily tasks:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_market_analysis_tasks.ps1 -Force
```

Save OpenAI key to encrypted local file (recommended):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\save_openai_key.ps1
```

## Environment

Create `.env` in project root and fill values as needed.

## Project workflow and rules

- Agent instructions: `AGENTS.md`
- Project docs: `memory-bank/PROJECT_DOCUMENTATION.md`
- Rules: `memory-bank/rules.md`
- Workflows: `memory-bank/workflows.md`
- Restart recovery: `memory-bank/restart-recovery-runbook.md`
- Task board: `tasks/todo.md`
- Lessons log: `tasks/lessons.md`
- Archived enterprise docs: `memory-bank/archive/enterprise/`
- Skills workspace: `skills/`

## MCP servers

MCP server config is in `.mcp.json`.

Possible credentials you may need:
- `GITHUB_TOKEN` for GitHub MCP server
- No key required for filesystem/fetch/playwright servers

## CI and tests

- GitHub Actions workflow: `.github/workflows/build-test.yml`
- Readiness gate workflow: `.github/workflows/readiness-gate.yml`
- Local test command:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -p "test_*.py" -v
```

- Local readiness validation:

```powershell
python scripts/validate_readiness.py
```

## Output schema

Each item is normalized as:

- `id`
- `source`
- `title`
- `url`
- `published_at` (ISO-8601)
- `summary`
- `tags` (list)
- `raw` (original fields for debugging)
