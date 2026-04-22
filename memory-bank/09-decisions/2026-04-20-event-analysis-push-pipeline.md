# Decision: Split Market Source Events, AI Analyses, and LINE Push Jobs

Status: delivery-job portion superseded by `2026-04-21-remove-python-line-touch.md`; the fact-to-analysis storage flow remains accepted.

## Context
- The pre-open market context collector was previously writing deterministic source data directly into `t_market_analyses`.
- That made `t_market_analyses` contain both source facts and generated AI analysis rows.
- The preferred flow is clearer: facts first, analysis second, delivery third.

## Decision
- Treat `t_relay_events` as the normalized fact/event table.
- Write pre-open market context points as stored-only `market_context:*` rows in `t_relay_events`.
- Deduplicate `market_context:*` by stable event id instead of only `title+url`, because same-URL market facts can remain numerically unchanged across days while still being a new as-of observation.
- Generate `t_market_analyses` rows from the recent event window plus structured market snapshot rows.
- Python delivery-job creation and LINE push execution were removed after the migration to Java-owned delivery.
- Keep the storage side: source facts go to `t_relay_events`, generated analysis goes to `t_market_analyses`, and downstream systems can decide how to deliver.

## Consequences
- `t_market_analyses` is reserved for generated or human-facing analysis artifacts.
- `t_relay_events` remains traceable and queryable for source facts, including non-alert market context.
- Python no longer owns push history or LINE delivery.
- Legacy `/events` remains available for compatibility/manual event ingestion; `/push/direct` was removed with Python LINE contact paths.

## Verification
- `python -m compileall src tests`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_market_context tests.test_market_analysis tests.test_event_relay -v`
