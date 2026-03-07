# News Collector (MVP)

This project starts from data ingestion for international finance breaking news.

## Current data sources

1. Official RSS (no API key)
- Federal Reserve press releases
- ECB press releases
- BIS announcements

2. GDELT DOC 2.0 (no API key)
- Global news coverage, near real-time batches

3. Benzinga News REST (API key required)
- Real-time market news feed

4. X account stream (Bearer token required)
- Track selected accounts with X filtered stream (near real-time)

## API key requirements

- `BENZINGA_ENABLED` (master switch; default `false`)
- `BENZINGA_API_KEY` (required only when `BENZINGA_ENABLED=true`)
- `BENZINGA_API_KEY_FILE` (optional; encrypted local key file, default `.secrets/benzinga_api_key.dpapi`)
- `BENZINGA_STOP_ON_429` (only effective when `BENZINGA_ENABLED=true`)
- `X_ENABLED` (master switch for X source; default `false`)
- `X_BEARER_TOKEN` (required only when `X_ENABLED=true`)
- `X_BEARER_TOKEN_FILE` (optional; encrypted local token file, default `.secrets/x_bearer_token.dpapi`)
- `X_ACCOUNTS` (comma-separated usernames or profile URLs)
- `X_MAX_RESULTS_PER_ACCOUNT` (used by one-shot/poll mode only)
- `X_STOP_ON_429` (stop X stream after first 429 in current process)
- `X_INCLUDE_REPLIES` / `X_INCLUDE_RETWEETS` (default `false`)
- No key required for RSS and GDELT

## Quick start

```bash
PYTHONPATH=src python -m news_collector.main fetch --source rss --limit 20
PYTHONPATH=src python -m news_collector.main fetch --source gdelt --limit 20
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

GDELT one-shot API (English + Chinese, title/url only):

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source gdelt --limit 10 --languages "en,zh" --title-url-only --log-level ERROR
```

GDELT 429 switch:
- `GDELT_COOLDOWN_ON_429=false` (default): no cooldown window, just skip current cycle on 429.
- `GDELT_COOLDOWN_ON_429=true`: enter cooldown window after 429.
- `GDELT_COOLDOWN_SECONDS=600`: cooldown duration when switch is on.
- GDELT source now enforces local filtering: only `English/Chinese`, and topic keywords focused on international politics, finance/economy, and technology (with entertainment/sports exclusions).

## LINE Event Relay Service

This repo now includes a standalone relay service:
- Receive incoming events via HTTP `POST /events`
- Receive LINE platform webhook via `POST /line/webhook` (HMAC signature verification)
- Receive direct push via `POST /push/direct` (bypass `t_relay_events` queue)
- Persist events in MySQL event queue table (auto create DB/table)
- Every 5 minutes, poll latest unpushed events (`is_pushed=0`) and dispatch
- Current default is dry-run: print push logs only (no real LINE push)
- `LINE_RELAY_DISPATCH_DRY_RUN` also applies to `/push/direct`
- LINE push message format is now strictly: `title` + `url`
- Auto-create LINE bot metadata tables (daily-kanji style):
  - `t_bot_group_info`
  - `t_bot_user_info`
- Auto-create X post table:
  - `t_x_posts`

Run:

```powershell
pip install -e .
powershell -ExecutionPolicy Bypass -File .\scripts\run_line_event_relay.ps1
```

Bridge all source links to relay (`BENZINGA stream + X stream + GDELT + RSS + US index direct push`):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1 -PollIntervalSeconds 300 -Limit 5 -UsIndexPollIntervalSeconds 30
```

Default bridge language filter for Benzinga stream is `en,cn` (internally maps `cn -> zh`).
X source is now consumed by filtered stream (near real-time) with auto reconnect/backoff.
US index chain tracks DJIA and S&P 500 open/close and sends direct push via `/push/direct` (no insert into `t_relay_events`).

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

## Benzinga Stream (latest/fastest)

1. Install dependencies:

```powershell
pip install -e .
```

2. Save API key in encrypted local file (Windows DPAPI):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\save_benzinga_key.ps1
```

You can also pass key directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\save_benzinga_key.ps1 -ApiKey "YOUR_KEY"
```

3. Run stream:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_benzinga_stream.ps1 -Tickers "AAPL,TSLA" -MaxMessages 20
```

Language filter:
- Script default is all languages (no filter)
- Example for Japanese only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_benzinga_stream.ps1 -Languages "ja"
```

- Example for multiple languages:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_benzinga_stream.ps1 -Languages "en,ja"
```

Top-level URL only output:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_benzinga_stream.ps1 -UrlOnly
```

Security notes:
- Key is stored in `.secrets/benzinga_api_key.dpapi` (gitignored).
- Logs and output never print API key.
- Stream has retry with exponential backoff to reduce lockout risk.
- Stream output event is emitted only when URL check returns HTTP 200 (timeout 3s).
- If you see `429 Too Many Requests`, reduce retries/polling and confirm your Benzinga plan quota.

429 stop switch:
- Default is off: `BENZINGA_STOP_ON_429=false`
- If set to `true`, stream will stop immediately after first 429 response.
- This applies only when `BENZINGA_ENABLED=true`.

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

If you get `HTTP 402 Payment Required`, your X developer project/app does not currently have the required paid access for these read endpoints.

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
- `BENZINGA_API_KEY` for Benzinga news source

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
