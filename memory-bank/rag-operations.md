# RAG Operations

## Purpose

Historical-case RAG gives market analysis a small set of past event/analysis analogues. It is guidance for transmission reasoning, not current evidence. Current evidence still comes from the prompt context, source facts, market rows, and scorecard.

## Ownership

- Repo: `data-collecting`
- Module: `src/event_relay/rag.py`
- Indexer script: `scripts/run_rag_indexer.ps1`
- Analysis integration: `src/event_relay/market_analysis.py`
- Scheduled task registration: `scripts/register_market_analysis_tasks.ps1`

## Tables

| Table | Purpose |
|---|---|
| `t_event_embeddings` | Embeddings and metadata for recent `t_relay_events` rows. |
| `t_analysis_embeddings` | Embeddings and outcome priors for generated `t_market_analyses` rows. |

RAG does not write delivery rows, LINE rows, order rows, or frontend rows.

## Current Retrieval Contract

- Default embedding model is deterministic local lexical embedding: `local-hash-v1`.
- Default dimension is `128`.
- Retrieval is hybrid:
  - vector similarity from local embeddings
  - metadata overlap for source family, category, ticker, topic, and slot
  - stored outcome score as a prior
- Event examples and generated-analysis examples can both be retrieved.
- Retrieved examples are sent to stage2 as historical analogues only.
- Historical example IDs must not be treated as current `trigger_event_ids` or current evidence IDs.
- RAG failure must degrade to zero examples and record the error in `t_market_analyses.raw_json.rag`; it must not block market-analysis storage.

## Commands

Run the indexer once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env
```

Run with explicit limits:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env -Days 30 -EventLimit 500 -AnalysisLimit 100
```

Register scheduled market-analysis tasks, including the RAG indexer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_market_analysis_tasks.ps1 -Force
```

## Configuration

| Variable | Default | Notes |
|---|---:|---|
| `MARKET_ANALYSIS_RAG_ENABLED` | `true` | Enables retrieval during market analysis. |
| `MARKET_ANALYSIS_RAG_K` | `5` | Max examples passed to analysis. |
| `MARKET_ANALYSIS_RAG_MIN_SIMILARITY` | `0.22` | Vector similarity floor. |
| `MARKET_ANALYSIS_RAG_CANDIDATE_LIMIT` | `500` | Candidate pool size. |
| `MARKET_ANALYSIS_RAG_VECTOR_WEIGHT` | `0.62` | Hybrid vector component. |
| `MARKET_ANALYSIS_RAG_METADATA_WEIGHT` | `0.25` | Hybrid metadata component. |
| `MARKET_ANALYSIS_RAG_OUTCOME_WEIGHT` | `0.13` | Hybrid outcome component. |
| `MARKET_ANALYSIS_RAG_METADATA_FILTER_THRESHOLD` | `0.10` | Metadata filter floor when query metadata exists. |
| `MARKET_ANALYSIS_RAG_INCLUDE_ANALYSES` | `true` | Include previous generated analyses as examples. |
| `RAG_EMBEDDING_MODEL` | `local-hash-v1` | Keep stable unless intentionally rebuilding. |
| `RAG_EMBEDDING_DIMENSIONS` | `128` | Keep aligned with stored vectors. |
| `RAG_INDEX_LOOKBACK_DAYS` | `30` | Indexer lookback window. |
| `RAG_INDEX_EVENT_LIMIT` | `500` | Max events indexed per run. |
| `RAG_INDEX_ANALYSIS_LIMIT` | `100` | Max analyses indexed per run. |

## Telemetry To Inspect

In `t_market_analyses.raw_json`:

- `raw_json.rag.examples_count`
- `raw_json.rag.error`
- `raw_json.rag.score_components`
- `raw_json.provider_context_policy` when Anthropic/Claude compact mode is selected
- `raw_json.pipeline_stages.core_tensions`
- `raw_json.claim_verifier`

## Tests

Use focused tests after RAG or analysis changes:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_rag tests.test_analysis_stages tests.test_market_analysis -v
```

If local dependencies are missing, state that verification could not run and why.

## Agent Rules

- Do not add external paid embedding providers unless the user explicitly approves the provider and cost model.
- Do not let RAG examples override current source facts.
- Do not use RAG examples as claim evidence for numbers, dates, or tickers in final output.
- Keep `memory-bank/09-decisions/2026-04-25-historical-case-rag.md` and `memory-bank/09-decisions/2026-05-07-hybrid-rag-stage0-claim-router.md` as historical decision records; put current operations here.
- When retrieval behavior, tables, or telemetry change, update this file, [PROJECT_INDEX.md](../PROJECT_INDEX.md), and [memory-bank/00-index.md](00-index.md).
