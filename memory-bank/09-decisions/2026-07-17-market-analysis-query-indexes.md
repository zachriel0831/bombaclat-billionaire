# Decision: Add Market Analysis Query Indexes

## Context

The forced `pre_tw_open` analysis run hit MySQL `Out of sort memory` while reading recent market-analysis context. The query pattern sorts stored analyses by `analysis_slot`, `updated_at`, and `id`, and reads recent market snapshots by `created_at` / `id`.

## Decision

`MySqlEventStore` now ensures these indexes at startup:

- `t_market_analyses`: `idx_analysis_slot_updated (analysis_slot, updated_at, id)`
- `t_market_index_snapshots`: `idx_market_created_id (created_at, id)`

The DDL also includes the same keys for new local databases.

## Consequences

- Recent analysis lookups should avoid large filesorts and sort-buffer failures.
- Startup migration skips indexes that already exist and logs a warning instead of blocking service startup if an operator must add them manually.
- These indexes do not change the storage boundary: source facts remain in `t_relay_events` / snapshot tables, generated prose remains in `t_market_analyses`.
