# Project Documentation

## Project Goal
Collect and normalize international breaking news, market data, and official disclosures, then generate stored market analyses for downstream systems.

LINE delivery and LINE webhook handling have migrated to the Java system. This Python repository is the data collection, event storage, and analysis service. It does not contact LINE in any form.

## Current Architecture
- Runtime: Python 3.10+
- Main packages:
  - `src/news_collector`: source ingestion + bridge
  - `src/event_relay`: event storage API (`/events`), MySQL persistence, retention cleanup, weekly summary, market analysis, and market context modules
- Main services:
  1. `news_collector.relay_bridge`
  2. `event_relay.main` (event relay API for `/events`)
  3. `event_relay.weekly_summary` (single-shot, usually triggered by scheduler)
  4. `event_relay.market_analysis` (single-shot, usually triggered twice daily by scheduler)

## Ingestion Sources
1. X filtered stream
- Requires X bearer token (supports DPAPI file fallback)
- Tracks allowlisted accounts
- Auto-heal for `429 TooManyConnections` by terminating stale connections and reconnecting
- Bridge startup performs a one-shot X backfill for tracked accounts before attaching the live stream, so recent gap tweets can still be written directly to `t_relay_events` and `t_x_posts`

2. RSS polling
- BBC / Reuters / Fox / NPR feeds from `OFFICIAL_RSS_FEEDS`
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
- Writes normalized announcement events directly into `t_relay_events` through the crawler bridge

5. US index tracker
- Tracks DJIA and S&P 500 open/close
- Writes normalized stored-only events directly into `t_relay_events`
- Marks rows as `stored_only_market`
- Stores structured quote rows in MySQL table `t_market_index_snapshots` for same-day analysis

## Event Storage & Analysis Boundary
- HTTP endpoints:
  - `POST /events`: compatibility/manual normalized event ingestion
  - `GET /healthz`
- Storage: MySQL
  - `t_relay_events`
- `t_x_posts`
- `t_market_index_snapshots`
- `t_market_analyses`
- Current behavior:
  - Crawler bridge owns normal source ingestion and writes event rows directly
  - `t_relay_events` is treated as event-only storage
  - Source/context facts must land in `t_relay_events` first; `t_market_analyses` is only for model-generated analysis after reading event windows
  - Python should not be considered the LINE delivery service; Java is responsible for user-facing LINE push/webhook behavior
  - Python contains no LINE push/webhook/direct-push contact path
  - Daily retention cleanup for old event rows
- Retention cleanup:
  - Default `RELAY_RETENTION_KEEP_DAYS=7`
  - Deletes old rows from both `t_relay_events` and `t_x_posts`
  - Event-relay maintenance loop runs cleanup once per local day
  - `scripts/register_retention_cleanup_task.ps1` can register the same cleanup as a fixed daily Windows task

## Analysis Context Policy
- `t_relay_events` is the primary local event/fact context for weekly and twice-daily analyses, but it is not treated as the complete universe of relevant market information.
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
- Storage contract:
  - `analysis_date` uses ISO week key like `2026-W17`
  - `analysis_slot=weekly_tw_preopen`
  - `raw_json.dimension=weekly`
- Prompt snapshots:
  - `runtime/prompts/weekly_summary_system_prompt.txt`
  - `runtime/prompts/weekly_summary_reusable_prompt.txt`
- Key management:
  - Prefer env var `WEEKLY_SUMMARY_OPENAI_API_KEY` / `OPENAI_API_KEY`
  - Fallback to DPAPI file `WEEKLY_SUMMARY_OPENAI_API_KEY_FILE`

## Twice-daily Market Analysis
- Module: `src/event_relay/market_analysis.py`
- Pre-open context module: `src/event_relay/market_context.py`
- Schedule intent:
  - `05:00` Asia/Taipei: U.S. close summary for Taiwan next-session context
  - `07:20` Asia/Taipei: collect pre-open market context as stored-only events into `t_relay_events`
  - `07:30` Asia/Taipei: Taiwan pre-open summary
- Flow:
  1. Read latest event context from `t_relay_events`
  2. Read latest DJIA / S&P 500 rows from `t_market_index_snapshots`
  3. Include stored-only `market_context:*` raw event payloads in the prompt event window
  4. Build Traditional Chinese prompts from existing macro + mobile-chat formatting skills
  5. Call OpenAI Responses API with web search enabled by default for current-fact verification
  6. Store generated text in `t_market_analyses`
- Market context storage contract:
  - `source` starts with `market_context:`
  - `raw_json.stored_only=true`
  - `raw_json.dimension=market_context`
  - `raw_json.event_type` is `market_context_point` or `market_context_collection`
  - current source families: Yahoo chart market snapshots, U.S. Treasury official yield curve XML, TWSE official OpenAPI index/stock/margin data
- Prompt snapshots:
  - `runtime/prompts/market_analysis_<slot>_system_prompt.txt`
  - `runtime/prompts/market_analysis_<slot>_user_prompt.txt`

## Scheduler
- Windows helper script:
  - `scripts/register_weekly_summary_task.ps1`
  - `scripts/register_market_analysis_tasks.ps1`
  - `scripts/register_retention_cleanup_task.ps1`
- Current target schedule requirement:
  - Every Sunday 23:00 (Asia/Taipei, local machine timezone) for weekly summary (Java pushes it at Monday 05:10)
  - Every day 05:00 and 07:30 (Asia/Taipei, local machine timezone) for market analysis
  - Every day 07:20 (Asia/Taipei, local machine timezone) for pre-open market context collection
  - Every day 00:10 (Asia/Taipei, local machine timezone) for retention cleanup

## Source Expansion Backlog
1. SEC EDGAR tracked filings
- started 2026-04-19 as first official-source expansion
2. Taiwan official company announcements
- started 2026-04-19 with TWSE `t187ap04_L` daily major information
- next likely additions: shareholder meeting / board meeting / investor conference datasets
3. Fed / macro official releases
- FOMC / Federal Reserve, then BLS / FRED class datasets

## Security & Secrets
- Secrets are stored locally with Windows DPAPI:
  - `.secrets/x_bearer_token.dpapi`
  - `.secrets/openai_api_key.dpapi`
  - `.secrets/openai_admin_key.dpapi` (admin use, high sensitivity)
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
- Run market analysis once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot us_close -Force`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot pre_tw_open -Force`
- Run market context once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env`
- Run retention cleanup once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_retention_cleanup.ps1 -EnvFile .env`

## Known Operational Notes
- X stream may return 429 when connection slots are occupied; auto-heal is enabled.
- OpenAI `insufficient_quota` can occur even with valid key if project billing/entitlement is not active.
- On this Windows workstation, `run_source_bridge.ps1` prefers `Python 3.12` for the bridge because local `Python 3.13` fails TLS verification against `openapi.twse.com.tw`.
