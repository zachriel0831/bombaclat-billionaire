# Decision: Taiwan Close Event-First Analysis

## Date
2026-04-22

## Context
REQ-011 adds a Taiwan close report. The corrected boundary is that same-day source/context facts are stored in `t_relay_events` first, and only model-generated analysis is written to `t_market_analyses`.

## Decision
- Implement `event_relay.tw_close_context` to aggregate same-day Taiwan relay events into a stored-only `market_context:tw_close` event.
- Add `tw_close` to `event_relay.market_analysis` at the default `15:30` Asia/Taipei checkpoint.
- Store `tw_close` analysis output in `t_market_analyses` with `raw_json.dimension=daily_tw_close`.
- Keep Python storage-only; Python does not push to LINE or create delivery jobs.
- Default the new `tw_close` analysis row to `push_enabled=false` until Java-side delivery policy is explicitly enabled.

## Consequences
- Taiwan close reports can reuse the same evidence path as pre-open analysis.
- The close-report source package remains auditable in `t_relay_events`.
- Java can later decide whether and how to deliver `tw_close` rows without changing Python ingestion.
