# X Stream Startup Backfill Decision

- Date: 2026-04-19
- Scope: X account ingestion recovery after bridge downtime or startup failures

## Decision
- Keep X filtered stream as the primary near-real-time ingestion path.
- Add a one-shot X startup backfill before the live stream connects.
- Resolve `X_BEARER_TOKEN` in `scripts/run_source_bridge.ps1` before launching Python, using inline env values first and DPAPI file fallback second.

## Why
- X filtered stream only delivers tweets created after the connection is established.
- If bridge startup is delayed or token resolution fails, tweets created during that gap never reach `/events` or `t_x_posts`.
- The startup backfill replays recent tracked-account tweets through the same relay path, preserving existing dedupe and DB write behavior.

## Verification Basis
- Standard bridge startup log now shows X token preflight resolved, startup backfill sent X events, and X stream connected.
- Missing Elon tweets from 2026-04-18/19 were inserted into both `t_relay_events` and `t_x_posts`.
