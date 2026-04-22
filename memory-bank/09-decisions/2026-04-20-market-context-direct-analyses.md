# Decision: Store Pre-open Market Context Directly in t_market_analyses

Status: superseded by `2026-04-20-event-analysis-push-pipeline.md`.

## Context
- Taiwan pre-open analysis needs more than news events: U.S. technology/risk indicators, Treasury yields, FX/commodities, and Taiwan local market factors.
- These inputs are market context snapshots, not alertable news events, so writing them into `t_relay_events` would mix time-series context with the event queue.
- The requested direction is to persist the missing data sources directly into `t_market_analyses`.

## Decision
- Add `event_relay.market_context` as a single-shot collector.
- Upsert one context row per local date using:
  - `analysis_slot=market_context_pre_tw_open`
  - `model=data-collector`
  - `prompt_version=market-context-v1`
  - `raw_json.dimension=market_context`
- Include these source families:
  - Yahoo chart snapshots for U.S. risk, semiconductors, FX, commodities, and key ADR/stocks
  - U.S. Treasury official daily yield curve XML
  - TWSE official OpenAPI index, tracked-stock, and margin data
- Update `market_analysis` so generated briefs read the latest context row and include it in prompts.

## Consequences
- `t_relay_events` remains a normalized news/event queue.
- `t_market_analyses` now contains both generated AI analyses and deterministic pre-open context packs, separated by `analysis_slot`.
- The default schedule runs the context collector at `07:20`, before `pre_tw_open` analysis at `07:30`.

## Verification
- `python -m compileall src tests`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_market_context tests.test_market_analysis -v`
- `scripts/run_market_context.ps1 -EnvFile .env` inserted `market_context_pre_tw_open` with 32 data points and 0 source failures on 2026-04-20.
