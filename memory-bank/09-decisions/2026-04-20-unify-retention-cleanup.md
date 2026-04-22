# Decision: Unify MySQL retention cleanup at 7 days

- Date: 2026-04-20
- Status: accepted

## Context
- Relay previously had an internal daily cleanup that deleted only `t_relay_events` with a hardcoded 3-day retention.
- `t_x_posts` was not cleaned, so older X post rows accumulated even after relay queue rows were removed.
- The desired operating model is a clear fixed retention window for both relay events and X posts.

## Decision
- Use `RELAY_RETENTION_KEEP_DAYS=7` as the default retention window.
- Keep the existing relay-internal daily cleanup hook, but make it call the unified retention cleanup.
- Delete from both `t_relay_events` and `t_x_posts` using `created_at` date boundaries.
- Add a standalone cleanup runner and Windows Task Scheduler registration script so cleanup can run even if the relay service is not continuously alive.

## Consequences
- Retention behavior is explicit, configurable, and covers both primary event tables.
- The old hardcoded 3-day queue cleanup is replaced by the shared 7-day cleanup.
- Backfilled X posts are retained for 7 days from ingestion time because retention is based on `created_at`.
