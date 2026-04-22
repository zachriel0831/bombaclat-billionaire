# Decision: Twice-daily market analysis storage

- Date: 2026-04-19
- Status: accepted

## Context
- Taiwan users need two high-value checkpoints from overnight U.S. market data:
  - `05:00`
  - `07:30`
- Immediate LINE delivery is not desired yet, but the generated analysis should still be queryable and reviewable.

## Decision
- Add a new stored-only analysis flow in `event_relay.market_analysis`.
- Persist outputs into MySQL table `t_market_analyses`.
- Register two daily Windows scheduled tasks:
  - `us_close` at `05:00`
  - `pre_tw_open` at `07:30`
- Keep Python storage-only; downstream Java can decide whether and how to deliver the stored analysis.

## Consequences
- The system gains a reviewable analysis history without introducing user-facing push noise.
- User-facing delivery can evolve downstream without redesigning the Python storage path.
- Model usage and prompt snapshots become auditable per run.
