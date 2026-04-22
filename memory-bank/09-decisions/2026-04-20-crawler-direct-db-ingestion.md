# Decision: Move Source Ingestion Storage Into Crawler Bridge

## Context
- The crawler bridge previously posted normalized source events to the legacy event relay `/events`.
- If `event_relay.main` was not running, RSS / X / SEC / TWSE / US index events could be fetched but failed to persist.
- The desired operating model is to run the crawler service without starting the event relay API, while still writing `t_relay_events`, `t_x_posts`, and market snapshot rows.

## Decision
- Make `news_collector.relay_bridge` use a direct MySQL event sink by default.
- Reuse `event_relay.service.MySqlEventStore` so dedupe, X post upsert, and market snapshot persistence remain identical to the `/events` path.
- Keep `/events` as a compatibility/manual ingestion endpoint, but remove it from the normal crawler ingestion dependency.
- Keep an explicit `--event-sink relay` fallback for manual compatibility tests.

## Consequences
- Starting `scripts/run_source_bridge.ps1` now writes source data to MySQL even when the event relay API is stopped.
- Python LINE dispatch was later removed by `2026-04-21-remove-python-line-touch.md`; downstream Java owns user-facing delivery.
- US index rows continue to be stored-only and remain available for same-day analysis.

## Verification
- `python -m compileall src tests`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_relay_bridge -v`
