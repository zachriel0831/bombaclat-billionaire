# Decision: Trade-focused market-analysis pipeline

Date: 2026-05-16

## Context
The core daily objective is not to produce a full research note for every slot. The product goal is:

- use crawled finance news and U.S. close data
- produce a Taiwan pre-open decision brief
- surface fixed-pool medium/short-term stock setups for review

The previous default made `us_close` and `pre_tw_open` both capable of running the full multi-stage pipeline, which duplicated reasoning and raised LLM cost.

## Decision
- Add slot-specific pipeline overrides through `MARKET_ANALYSIS_<SLOT>_PIPELINE`.
- Add `digest` pipeline mode for compact upstream context.
- Configure `MARKET_ANALYSIS_US_CLOSE_PIPELINE=digest` so the U.S. close job writes a concise upstream digest instead of a full trade brief.
- Keep `MARKET_ANALYSIS_PRE_TW_OPEN_PIPELINE=multi_stage` so Taiwan pre-open remains the main trade-decision output.
- Suppress trade-signal recommendation appends when `us_close` runs in `digest` mode.

## Consequences
- `us_close` cost drops because it uses one compact LLM call and smaller prompt context.
- The later `pre_tw_open` analysis still receives latest stored `us_close` context through the existing upstream-context path.
- Final stock setups remain concentrated in `pre_tw_open`.
- Existing table schema is unchanged; telemetry is stored in `raw_json.requested_pipeline_mode`, `raw_json.pipeline_mode`, and `raw_json.analysis_intent`.
