# Project Documentation

## Project Goal
Collect and normalize international breaking news (politics/finance/technology), then deliver actionable alerts and summaries to LINE users/groups.

## Current Architecture
- Runtime: Python 3.10+
- Main packages:
  - `src/news_collector`: source ingestion + bridge
  - `src/line_event_relay`: relay API + queue + LINE delivery
- Main services:
  1. `news_collector.relay_bridge`
  2. `line_event_relay.main`
  3. `line_event_relay.weekly_summary` (single-shot, usually triggered by scheduler)

## Ingestion Sources
1. X filtered stream
- Requires X bearer token (supports DPAPI file fallback)
- Tracks allowlisted accounts
- Auto-heal for `429 TooManyConnections` by terminating stale connections and reconnecting
- Bridge startup performs a one-shot X backfill for tracked accounts before attaching the live stream, so recent gap tweets can still reach `t_relay_events` and `t_x_posts`

2. RSS polling
- BBC / Reuters / Fox / NPR feeds from `OFFICIAL_RSS_FEEDS`
- Reuters currently uses Google News RSS search as fallback because legacy Reuters RSS endpoints are unavailable from this environment
- CNN RSS is configurable in code, but the previously tested CNN feeds were removed from the active `.env` set after returning stale items from 2016-2024 during the 2026-04-19 verification

3. US index tracker
- Tracks DJIA and S&P 500 open/close
- Posts normalized events to relay `/events`
- Writes queue rows to `t_relay_events`
- Relay dispatch skips LINE delivery for `source=us_index_tracker` and marks rows as `stored_only_market`
- Stores structured quote rows in MySQL table `t_market_index_snapshots` for same-day analysis

## Relay & Delivery
- HTTP endpoints:
  - `POST /events`: enqueue normalized events
  - `POST /push/direct`: manual direct-push path for bypass use cases
  - `POST /line/webhook` (and `/callback`): LINE platform webhook
  - `GET /healthz`
- Storage: MySQL
  - `t_relay_events`
- `t_bot_group_info`
- `t_bot_user_info`
- `t_x_posts`
- `t_market_index_snapshots`
- Dispatch behavior:
  - Poll queued events every configured interval
  - Push to active groups/users
  - Retry one failed item periodically
  - Daily retention cleanup for old queue rows

## Weekly Summary
- Module: `src/line_event_relay/weekly_summary.py`
- Flow:
  1. Read last N days events from `t_relay_events`
  2. Build `system prompt` and `reusable prompt` from skill docs
  3. Call OpenAI Responses API
  4. Push summary to LINE targets
- Prompt snapshots:
  - `runtime/prompts/weekly_summary_system_prompt.txt`
  - `runtime/prompts/weekly_summary_reusable_prompt.txt`
- Key management:
  - Prefer env var `WEEKLY_SUMMARY_OPENAI_API_KEY` / `OPENAI_API_KEY`
  - Fallback to DPAPI file `WEEKLY_SUMMARY_OPENAI_API_KEY_FILE`

## Scheduler
- Windows helper script:
  - `scripts/register_weekly_summary_task.ps1`
- Current target schedule requirement:
  - Every Sunday 18:00 (Asia/Taipei, local machine timezone)

## Security & Secrets
- Secrets are stored locally with Windows DPAPI:
  - `.secrets/x_bearer_token.dpapi`
  - `.secrets/openai_api_key.dpapi`
  - `.secrets/openai_admin_key.dpapi` (admin use, high sensitivity)
- Never print full secret values in logs.

## Operations
- Start relay:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_line_event_relay.ps1`
- Start bridge:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1`
- Restart both:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\restart_live_services.ps1`
- Run weekly summary once:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_summary.ps1 -Force`

## Known Operational Notes
- X stream may return 429 when connection slots are occupied; auto-heal is enabled.
- OpenAI `insufficient_quota` can occur even with valid key if project billing/entitlement is not active.
