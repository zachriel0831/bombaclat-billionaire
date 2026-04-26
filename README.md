# News Collector (MVP)

This project starts from data ingestion for international finance breaking news.

## Current data sources

1. Official RSS (no API key)
- BBC / Reuters / Fox / NPR feeds from `OFFICIAL_RSS_FEEDS`
- RSS `--limit` is applied per feed, not globally. For example, 12 feeds with `-Limit 5` can return up to 60 RSS items before URL dedupe and topic/date filters.

2. SEC EDGAR tracked filings (no API key, declared User-Agent required)
- Track selected tickers through official SEC ticker mapping + submissions API
- Starter `.env` set watches `NVDA,TSM,AAPL,MSFT,AMD,TSLA`

3. TWSE / MOPS official listed-company announcements (no API key)
- Uses TWSE openapi dataset `銝??砍瘥?之閮`
- Starter `.env` set watches `2330,2317,2454,2308,2881,2882`

4. X account stream (Bearer token required)
- Track selected accounts with X filtered stream (near real-time)

## API key requirements

- `X_ENABLED` (master switch for X source; default `false`)
- `SEC_ENABLED` (master switch for SEC tracked-filings source; default `false`)
- `SEC_USER_AGENT` (required when `SEC_ENABLED=true`; SEC asks automated clients to declare a user agent)
- `SEC_TRACKED_TICKERS` (comma-separated tickers, e.g. `NVDA,TSM,AAPL`)
- `SEC_ALLOWED_FORMS` (default high-signal filing set such as `8-K,10-Q,10-K,6-K,20-F`)
- `SEC_MAX_FILINGS_PER_COMPANY` (default `5`)
- `TWSE_MOPS_ENABLED` (master switch for TWSE listed-company major announcements)
- `TWSE_MOPS_TRACKED_CODES` (comma-separated listed company codes, e.g. `2330,2317,2454`)
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
- No key required for RSS

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

## Event Relay / Data Service

This repo now includes a Python data relay service:
- Receive compatibility/manual events via HTTP `POST /events`
- Persist events in MySQL event table
- Store X posts, market snapshots, and generated analyses
- Python does not own LINE webhook or LINE push delivery; those belong to the Java system
- Auto-create X post table:
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

Run crawler bridge (`RSS + SEC + TWSE/MOPS + X stream + US index tracker`) and write normalized events directly to MySQL:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1 -PollIntervalSeconds 300 -Limit 5 -UsIndexPollIntervalSeconds 30
```

For RSS, `-Limit 5` means up to 5 items per configured feed. SEC/TWSE/X keep their existing per-source or per-account limit behavior.

X source is now consumed by filtered stream (near real-time) with auto reconnect/backoff.
Bridge startup also runs a one-shot X backfill before connecting the filtered stream, so tweets published while the bridge was down can be replayed into `t_relay_events` and `t_x_posts` without the event relay API running.
When X returns `429` with `connection_issue=TooManyConnections`, bridge will auto-heal by terminating stale stream connections and retrying (configurable by `X_AUTO_HEAL_TOO_MANY_CONNECTIONS`).
SEC tracked filings use the official SEC `company_tickers.json` mapping plus `data.sec.gov/submissions/CIK##########.json`, then write high-signal filings directly into `t_relay_events`.
TWSE/MOPS tracked announcements use the official TWSE openapi `t187ap04_L` dataset (`銝??砍瘥?之閮`) and write tracked company disclosures directly into `t_relay_events`.
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
- `X_ACCOUNTS=https://x.com/elonmusk,https://x.com/realDonaldTrump`
- `X_AUTO_HEAL_TOO_MANY_CONNECTIONS=true` (recommended)
- `X_HEAL_COOLDOWN_SECONDS=45`
- `X_BACKFILL_ENABLED=true`
- `X_BACKFILL_MAX_RESULTS_PER_ACCOUNT=10`

If you get `HTTP 402 Payment Required`, your X developer project/app does not currently have the required paid access for these read endpoints.

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
- `TWSE_MOPS_TRACKED_CODES=2330,2317,2454,2308,2881,2882`
- `TWSE_MOPS_MAX_ITEMS_PER_COMPANY=5`

Notes:
- This source uses the official TWSE openapi dataset `https://openapi.twse.com.tw/v1/opendata/t187ap04_L`.
- Current MVP covers `銝??砍瘥?之閮`.
- Events flow directly into `t_relay_events` through the crawler bridge.

## Weekly macro summary (AI, stored only)

Generate one weekly summary from `t_relay_events` and store it in `t_market_analyses`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_summary.ps1 -Force -DryRun
```

Prompt pipeline:
- Read skill docs:
  - `skills/macro-weekly-summary-skill/SKILLS.md`
  - `skills/line-brief-format-skill/line-weekly-brief.md`
- Compile as:
  - `runtime/prompts/weekly_summary_system_prompt.txt`
  - `runtime/prompts/weekly_summary_reusable_prompt.txt`
- Send to OpenAI Responses API.
- OpenAI calls request the Responses API `web_search` tool by default so the model can verify fresh gaps beyond `t_relay_events`; set `LLM_WEB_SEARCH_ENABLED=false` to disable. If the API/project does not support the tool, the caller retries once without web search.
- Store the weekly summary in `t_market_analyses` with:
  - `analysis_date=YYYY-MM-DD` for the target Sunday delivery date
  - `analysis_slot=weekly_tw_preopen`

Weekly summary env keys:
- `WEEKLY_SUMMARY_OPENAI_API_KEY` (optional; fallback to `OPENAI_API_KEY`)
- `WEEKLY_SUMMARY_OPENAI_API_KEY_FILE` (default `.secrets/openai_api_key.dpapi`, Windows DPAPI encrypted key)
- `WEEKLY_SUMMARY_MODEL` (default `gpt-5`)
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
- `05:00` for U.S. close context
- `07:30` for Taiwan pre-open context
- `15:30` for Taiwan close review context

Current behavior:
- Reads recent events from `t_relay_events`
- Reads recent DJIA / S&P 500 rows from `t_market_index_snapshots`
- Reads stored-only `market_context:*` source facts from the recent `t_relay_events` window
- Optionally retrieves similar historical relay events from `t_event_embeddings` and includes them as analogues in the stage2 transmission prompt
- Calls OpenAI Responses API with web search enabled by default for missing/current fact verification
- Stores the generated analysis in `t_market_analyses`
- Extracts Taiwan stock recommendations from `structured_json.stock_watch` into `t_trade_signals`
- Does not push or create LINE delivery jobs; Java owns user-facing delivery
- Treats `t_relay_events` as primary local evidence, not as the only possible source of truth; prompts require explicit data-gap labeling when context is insufficient

Trade signal storage:
- `t_trade_signals` stores one row per recommended Taiwan ticker from a market analysis.
- Signals start as `status=pending_review`; they are not orders.
- Each signal carries `analysis_id`, `analysis_date`, `analysis_slot`, `ticker`, `strategy_type`, `direction`, optional entry/stop/target JSON, and `source_event_ids`.
- `idempotency_key` prevents duplicate signals for the same analysis/ticker/strategy.
- `t_signal_reviews` and `t_signal_outcomes` are separate follow-up tables for risk gate / human review and performance feedback.
- LLM output stops at signal creation. Order intents and broker calls must be created only after independent review/risk approval.

Pre-open market context collector:
- Module: `event_relay.market_context`
- Writes stored-only source facts into `t_relay_events` with `source=market_context:*`
- Sources currently included:
  - Yahoo chart snapshots for NASDAQ Composite, NASDAQ 100, SOX, VIX, DXY, WTI, Gold, and key semiconductor ADR/stocks
  - U.S. Treasury official daily yield curve XML for 2Y / 10Y / 30Y and 10Y-2Y spread
  - TWSE official OpenAPI for Taiwan index groups, tracked stocks, and margin balances

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

Run context collection once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_market_flow.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_bls_macro.ps1 -EnvFile .env
powershell -ExecutionPolicy Bypass -File .\scripts\run_tw_close_context.ps1 -EnvFile .env
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
- `MARKET_ANALYSIS_LOOKBACK_HOURS` (default `24`)
- `MARKET_ANALYSIS_MAX_EVENTS` (default `120`)
- `MARKET_ANALYSIS_MAX_MARKET_ROWS` (default `24`)
- `MARKET_ANALYSIS_WINDOW_MINUTES` (default `25`)
- `MARKET_ANALYSIS_RAG_ENABLED` (default `true`)
- `MARKET_ANALYSIS_RAG_K` (default `5`)
- `MARKET_ANALYSIS_RAG_MIN_SIMILARITY` (default `0.22`)
- `MARKET_ANALYSIS_RAG_CANDIDATE_LIMIT` (default `500`)
- `RAG_EMBEDDING_MODEL` (default `local-hash-v1`)
- `RAG_EMBEDDING_DIMENSIONS` (default `128`)
- `RAG_INDEX_LOOKBACK_DAYS` (default `30`)
- `RAG_INDEX_EVENT_LIMIT` (default `500`)
- `RAG_INDEX_ANALYSIS_LIMIT` (default `100`)
- `LLM_WEB_SEARCH_ENABLED` (default `true` for OpenAI; set `false` for local-only analysis)
- `LLM_TIMEOUT_SECONDS` (default `120`, shared OpenAI/Anthropic HTTP timeout)
- `MARKET_CONTEXT_TWSE_CODES` (optional; defaults to `TWSE_MOPS_TRACKED_CODES`)
- `MARKET_CONTEXT_ANALYSIS_SLOT` (default `market_context_pre_tw_open`)
- `MARKET_CONTEXT_SCHEDULED_TIME` (default `07:20`)
- `MARKET_CONTEXT_TIMEOUT_SECONDS` (default `15`)
- `BLS_API_KEY` (optional)
- `BLS_SERIES_IDS` (optional comma-separated subset of the built-in BLS mapping)
- `BLS_TIMEOUT_SECONDS` (default inherited by script as `30`)
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
