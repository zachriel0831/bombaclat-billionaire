# News Collector (MVP)

This project starts from data ingestion for international finance breaking news.

## Current data sources

1. Official RSS (no API key)
- BBC / Reuters / Fox / NPR feeds from `OFFICIAL_RSS_FEEDS`

2. X account stream (Bearer token required)
- Track selected accounts with X filtered stream (near real-time)

## API key requirements

- `X_ENABLED` (master switch for X source; default `false`)
- `X_BEARER_TOKEN` (required only when `X_ENABLED=true`)
- `X_BEARER_TOKEN_FILE` (optional; encrypted local token file, default `.secrets/x_bearer_token.dpapi`)
- `X_ACCOUNTS` (comma-separated usernames or profile URLs)
- `X_MAX_RESULTS_PER_ACCOUNT` (used by one-shot/poll mode only)
- `X_STOP_ON_429` (stop X stream after first 429 in current process)
- `X_AUTO_HEAL_TOO_MANY_CONNECTIONS` (default `true`; when 429 is `TooManyConnections`, auto call `DELETE /2/connections/all` then retry)
- `X_HEAL_COOLDOWN_SECONDS` (default `45`; cooldown between auto-heal actions)
- `X_INCLUDE_REPLIES` / `X_INCLUDE_RETWEETS` (default `false`)
- `X_BACKFILL_ENABLED` (default `true`; replay recent tracked-account tweets into `/events` once when bridge starts)
- `X_BACKFILL_MAX_RESULTS_PER_ACCOUNT` (default `10`; startup backfill size per tracked account)
- No key required for RSS

## Quick start

```bash
PYTHONPATH=src python -m news_collector.main fetch --source rss --limit 20
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

## LINE Event Relay Service

This repo now includes a standalone relay service:
- Receive incoming events via HTTP `POST /events`
- Receive LINE platform webhook via `POST /line/webhook` (HMAC signature verification)
- Receive direct push via `POST /push/direct` (manual bypass path; US index no longer uses it)
- Persist events in MySQL event queue table (auto create DB/table)
- Every 5 minutes, poll latest unpushed events (`is_pushed=0`) and dispatch
- Code default is dry-run; if `.env` sets `LINE_RELAY_DISPATCH_DRY_RUN=false`, it will push to real LINE targets
- `LINE_RELAY_DISPATCH_DRY_RUN` also applies to `/push/direct`
- LINE push message format is now strictly: `title` + `url`
- Auto-create LINE bot metadata tables (daily-kanji style):
  - `t_bot_group_info`
  - `t_bot_user_info`
- Auto-create X post table:
  - `t_x_posts`
- Auto-create market snapshot table for US index analysis:
  - `t_market_index_snapshots`

Run:

```powershell
pip install -e .
powershell -ExecutionPolicy Bypass -File .\scripts\run_line_event_relay.ps1
```

Bridge all source links to relay (`X stream + RSS + US index tracker`):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1 -PollIntervalSeconds 300 -Limit 5 -UsIndexPollIntervalSeconds 30
```

X source is now consumed by filtered stream (near real-time) with auto reconnect/backoff.
Bridge startup also runs a one-shot X backfill before connecting the filtered stream, so tweets published while the bridge was down can be replayed into `/events` and `t_x_posts`.
When X returns `429` with `connection_issue=TooManyConnections`, bridge will auto-heal by terminating stale stream connections and retrying (configurable by `X_AUTO_HEAL_TOO_MANY_CONNECTIONS`).
US index chain tracks DJIA and S&P 500 open/close, posts normalized events to relay `/events`, writes `t_relay_events`, and stores structured quote rows in `t_market_index_snapshots` for same-day analysis.
Relay dispatch marks `source=us_index_tracker` rows as `stored_only_market`, so they stay queryable in MySQL but are not pushed to LINE.

Required `.env` values:
- `LINE_CHANNEL_ACCESS_TOKEN` (required only when `LINE_RELAY_DISPATCH_DRY_RUN=false`)
- `LINE_CHANNEL_SECRET` (required for `/line/webhook` signature verification)
- `LINE_WEBHOOK_PATH=/line/webhook` (optional, defaults to this path)
- `LINE_DIRECT_TARGET_USER_IDS=Uxxxxxxxx,...` (direct push target users; if empty, fallback to active `test_account=1` users)

MySQL defaults (editable in `.env`):
- `LINE_RELAY_MYSQL_ENABLED=true`
- `LINE_RELAY_MYSQL_HOST=127.0.0.1`
- `LINE_RELAY_MYSQL_PORT=3306`
- `LINE_RELAY_MYSQL_USER=root`
- `LINE_RELAY_MYSQL_PASSWORD=root`
- `LINE_RELAY_MYSQL_DATABASE=news_relay`
- `LINE_RELAY_MYSQL_EVENT_TABLE=t_relay_events`
- `LINE_RELAY_MYSQL_GROUP_TABLE=t_bot_group_info`
- `LINE_RELAY_MYSQL_USER_TABLE=t_bot_user_info`
- `LINE_RELAY_MYSQL_X_TABLE=t_x_posts`
- `LINE_RELAY_MYSQL_MARKET_TABLE=t_market_index_snapshots`
- `LINE_RELAY_DISPATCH_INTERVAL_SECONDS=300`
- `LINE_RELAY_DISPATCH_BATCH_SIZE=1`
- `LINE_RELAY_DISPATCH_DRY_RUN=true`

Heroku deploy notes:
- `Procfile` already runs web dyno: `python -m line_event_relay.main`
- Relay port supports Heroku `PORT` automatically (fallback from `LINE_RELAY_PORT`)
- Recommended LINE webhook URL:
  - `https://<your-heroku-app>.herokuapp.com/callback`

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:18090/healthz
```

Verify LINE Messaging API token locally (no push):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_line_messaging_api.ps1 -EnvFile .env
```

Post sample event:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\post_event_sample.ps1
```

Post sample LINE webhook (with valid signature):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\post_line_webhook_sample.ps1
```

Post sample direct push (bypass queue table):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\post_direct_push_sample.ps1
```

Webhook local test (collector and LINE bot as separate services):

1. Start relay service only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_line_event_relay.ps1
```

2. Expose local webhook with ngrok (if installed):

```powershell
ngrok http 18090
```

3. In LINE Developers Console, set Webhook URL to:
- `https://<your-ngrok-domain>/line/webhook`

4. Keep webhook verification enabled in LINE console. This service validates `x-line-signature` using `LINE_CHANNEL_SECRET`.
5. When bot is invited into a group, relay logs `[LINE_GROUP_JOIN] ... group_id=...` for quick copy.

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
- Keep `LINE_RELAY_DISPATCH_DRY_RUN=true` for local test mode (no real push).

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

## Weekly macro summary (AI + LINE)

Generate one weekly summary from `t_relay_events` and push to active LINE targets:

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
- Send to OpenAI Responses API and push generated text to LINE.

Weekly summary env keys:
- `WEEKLY_SUMMARY_OPENAI_API_KEY` (optional; fallback to `OPENAI_API_KEY`)
- `WEEKLY_SUMMARY__FILE` (default `.secrets/openai_api_key.dpapi`, Windows DPAPI encrypted key)
- `WEEKLY_SUMMARY_MODEL` (default `gpt-4.1-mini`)
- `WEEKLY_SUMMARY_LOOKBACK_DAYS` (default `7`)
- `WEEKLY_SUMMARY_MAX_EVENTS` (default `120`)
- `WEEKLY_SUMMARY_WEEKDAY` (0=Mon ... 6=Sun, default `6`)
- `WEEKLY_SUMMARY_HOUR` (default `10`)
- `WEEKLY_SUMMARY_MINUTE` (default `0`)
- `WEEKLY_SUMMARY_WINDOW_MINUTES` (default `20`)
- `WEEKLY_SUMMARY_DRY_RUN` (default follows `LINE_RELAY_DISPATCH_DRY_RUN`)

Weekly schedule helper (Windows Task Scheduler):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_weekly_summary_task.ps1 -TaskName "NewsCollector-WeeklySummary" -At "18:00" -Force
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
- Enterprise readiness baseline: `memory-bank/40-agent-enterprise-readiness.md`
- Skills engineering standard: `memory-bank/41-skills-engineering-standard.md`
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
