# Task Plan Board

Use this file for non-trivial tasks (3+ steps or architecture decisions).

## Current Task
- Task: Remove Benzinga and GDELT sources and simplify ingestion to RSS + X + US index only
- Requested by: User
- Start date: 2026-04-19
- Scope: collector, bridge, scripts, config, tests, docs, runtime startup

## Plan (checkable)
- [x] Remove Benzinga and GDELT code paths from collector and CLI
- [x] Remove Benzinga and GDELT bridge/runtime script logic
- [x] Delete obsolete source modules/scripts/tests and update config/dependencies
- [x] Update README and memory-bank docs to reflect simplified sources
- [x] Verify tests and live services still work with RSS + X + US index only

## Progress Notes
- 2026-04-19 15:30 - read AGENTS and required memory-bank docs, then confirmed current `.env` RSS feed list and RSS parser behavior.
- 2026-04-19 15:31 - ran `python -m news_collector.main fetch --source rss --env-file .env --log-level INFO --pretty`; BBC/Fox/NPR and Reuters-via-Google-News responded, CNN feeds returned stale items.
- 2026-04-19 15:33 - started tracing relay write path from `news_collector.relay_bridge` to `/events` and `t_relay_events`.
- 2026-04-19 15:35 - replaced active `.env` RSS set to BBC + Reuters-via-Google + Fox/Fox Business + NPR and documented the source-mapping decision in `memory-bank/`.
- 2026-04-19 15:36 - confirmed relay health at `http://127.0.0.1:18090/healthz` and MySQL availability before smoke run.
- 2026-04-19 15:32 - executed short bridge smoke run; `runtime/logs/rss-bridge-smoke-20260419-153207.out.log` shows `Polling cycle complete pushed=4`.
- 2026-04-19 15:37 - queried `t_relay_events` and confirmed four new RSS rows created at `2026-04-19 15:32:13`.
- 2026-04-19 15:49 - investigated X stream gap for `elonmusk`: current bridge process started at `2026-04-19 15:32:09 +08:00`, current one-shot X fetch shows latest Elon tweets before the active stream connected.
- 2026-04-19 15:50 - confirmed earlier bridge run `runtime/logs/source-bridge-20260419-122912.out.log` skipped X entirely with `missing X bearer token`, while the later manual bridge run `runtime/logs/rss-bridge-smoke-20260419-153207.out.log` successfully logged `X stream rule synced` and `X filtered stream connected`.
- 2026-04-19 15:54 - switched active task focus to X startup reliability and backfill gap repair.
- 2026-04-19 15:56 - added startup X backfill in `relay_bridge.py`, new X backfill config keys, and PowerShell preflight secret resolution in `scripts/run_source_bridge.ps1`.
- 2026-04-19 15:57 - reproduced standard startup under `run_source_bridge.ps1`; X token now resolves, but Benzinga optional dependency error was surfacing on stderr and destabilizing the script path.
- 2026-04-19 15:58 - downgraded Benzinga startup failures to warnings, re-ran standard script, and confirmed bridge stayed alive with startup backfill plus X stream connection.
- 2026-04-19 15:58 - verified missing Elon tweet ids `2045603644159283436`, `2045647384831799510`, and `2045764832373449112` now exist in both `t_relay_events` and `t_x_posts`.
- 2026-04-19 16:20 - added `t_market_index_snapshots` support in relay config/service and attached structured `market_snapshot` payloads to US index direct push events.
- 2026-04-19 16:21 - added tests for direct-push market snapshot recording and quote payload conversion; compile and full unit suite passed.
- 2026-04-19 16:23 - restarted relay to load new schema/service code; log confirms `market_table=t_market_index_snapshots`.
- 2026-04-19 16:25 - posted a local `/push/direct` sample with DJIA/S&P 500 structured payload and verified two rows inserted into `t_market_index_snapshots`.
- 2026-04-19 16:18 - live GDELT fetch returned `429` and entered configured cooldown, so GDELT is currently reachable but rate-limited rather than delivering items.
- 2026-04-19 16:31 - rerouted US index bridge payloads from `/push/direct` to `/events`, added stored-only dispatch handling, and updated README / memory-bank docs.
- 2026-04-19 16:32 - live bridge log exposed a regression (`open_window` undefined) caused by a malformed comment line in `relay_bridge.py`; fixed and revalidated targeted tests.
- 2026-04-19 16:34 - live dispatch exposed `line_push_status VARCHAR(24)` overflow for `stored_only_market_snapshot`; shortened status to `stored_only_market` and revalidated.
- 2026-04-19 16:35 - posted `/events` sample `manual_us_index_event_2026-04-19`; verified one row inserted into `t_relay_events` and two rows inserted into `t_market_index_snapshots`.
- 2026-04-19 16:36 - executed relay dispatch against the queued sample and confirmed `line_push_status=stored_only_market`, `is_pushed=1`, with no LINE push path used.
- 2026-04-19 16:35 - restarted source bridge successfully; latest log `runtime/logs/source-bridge-20260419-163535.out.log` shows bridge alive, RSS polling complete, and `X filtered stream connected`.
- 2026-04-19 16:43 - started source simplification pass to remove Benzinga and GDELT entirely from code paths, scripts, and docs because those vendors are no longer desired.
- 2026-04-19 16:45 - removed Benzinga/GDELT from `config.py`, `collector.py`, `main.py`, `relay_bridge.py`, runtime scripts, dependency list, and deleted obsolete source modules/scripts/tests.
- 2026-04-19 16:47 - updated `.env`, README, project documentation, workflows, and added decision note `2026-04-19-remove-benzinga-gdelt.md`.
- 2026-04-19 16:48 - restarted live relay/bridge; latest bridge log shows RSS polling, X startup backfill, and no Benzinga/GDELT startup path.

## Verification
- [x] Tests passed
- [x] Critical path manually checked
- [x] Docs/config updated when behavior changed

## Review Summary
- Outcome: Benzinga and GDELT were fully removed; active ingestion is now RSS + X + US index only.
- Evidence:
  - `python -m compileall src tests`
  - `$env:PYTHONPATH='src'; python -m unittest discover -s tests -p "test_*.py" -v`
  - `runtime/logs/source-bridge-20260419-164802.out.log` shows bridge startup with RSS polling and X backfill only
  - `Invoke-RestMethod http://127.0.0.1:18090/healthz`
- Open risks:
  - Reuters still depends on Google News RSS fallback instead of a direct Reuters-owned feed.
