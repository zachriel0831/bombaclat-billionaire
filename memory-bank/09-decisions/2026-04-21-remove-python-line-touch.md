# Decision: Remove Python LINE Contact Paths

Date: 2026-04-21

## Context
- LINE webhook and user-facing delivery have migrated to the Java system.
- This Python repository should only collect data, store normalized events, and generate market analyses.
- Legacy Python paths still included LINE webhook, direct push, LINE API client, and analysis push-job logic.

## Decision
- Remove Python-owned LINE webhook and direct-push HTTP endpoints.
- Remove the Python LINE API client and analysis push runner.
- Remove push-job scheduled tasks and scripts.
- Keep `/events`, MySQL event storage, X post storage, market snapshots, retention cleanup, weekly summary, market context, and market analysis.

## Consequences
- Python can no longer contact LINE users or process LINE webhook callbacks.
- Analyses are stored in `t_market_analyses` for downstream systems.
- Java owns all user-facing LINE delivery and webhook behavior.
