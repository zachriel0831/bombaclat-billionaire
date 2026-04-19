# Remove Benzinga And GDELT

- Date: 2026-04-19
- Scope: ingestion source simplification

## Decision
- Remove Benzinga and GDELT from the collector, bridge, scripts, tests, and runtime configuration.
- Keep the active ingestion set limited to:
  - official RSS feeds
  - X tracked-account stream / startup backfill
  - US index stored-only events

## Why
- The project now prefers explicit and easier-to-audit upstreams over rate-limited aggregator or paid API sources.
- Benzinga and GDELT were adding operational noise, stale documentation, and maintenance cost without matching the desired source strategy.
- Simplifying the source set reduces startup complexity and makes failures easier to reason about.

## Verification Basis
- `news_collector.main fetch` only exposes `rss`, `x`, and `all`.
- `news_collector.relay_bridge` runs RSS polling, X stream/backfill, and US index tracking only.
- Benzinga/GDELT modules, scripts, and tests were removed from the repository.
