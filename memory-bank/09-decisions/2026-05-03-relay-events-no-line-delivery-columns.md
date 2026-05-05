# 2026-05-03 Relay Events Are Not A LINE Queue

## Decision
`t_relay_events` is pure source/event storage. Remove legacy LINE delivery columns:

- `is_pushed`
- `line_pushed_at`
- `line_push_status`
- `line_push_error`

Python no longer owns LINE delivery, webhook handling, or push-state tracking.

## Rationale
Keeping delivery-status columns in `t_relay_events` makes the table look like a push queue. That conflicts with the current service boundary: Python collects data and writes analyses; Java owns LINE delivery and delivery records.

## Consequences
- Event ingestion inserts only event fields and `raw_json`.
- Existing deployments drop the old columns during `MySqlEventStore.initialize()`.
- A `created_at` index replaces the old `idx_push_queue` index for event recency queries.
