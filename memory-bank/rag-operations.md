# RAG Operations

## Purpose

Historical-case RAG gives Codex market analysis a small set of past event/analysis analogues. It is guidance for transmission reasoning, not current evidence. Current evidence still comes from source facts, market rows, and scorecard.

## Ownership

- Repo: `data-collecting`
- Module: `src/event_relay/rag.py`
- Indexer script: `scripts/run_rag_indexer.ps1`
- Analysis integration: Codex local automations read the RAG tables as needed.
- Scheduled task registration: `scripts/register_market_analysis_tasks.ps1` registers the RAG indexer and data/context tasks only.

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
- Outcome scoring is entry-first for strategy triggers: raw `target_hit` or `stop_hit` alone is neutral, because a target can occur before `entry_hit`. Only lifecycle metadata such as `entry_first_status=entry_then_target` or ordered `trigger_events` where entry comes first can raise/lower the prior.
- Event examples and generated-analysis examples can both be retrieved.
- Retrieved examples are sent to Codex as historical analogues only.
- Historical example IDs must not be treated as current `trigger_event_ids` or current evidence IDs.
- RAG failure must degrade to zero examples and record the error in `t_market_analyses.raw_json.rag`; it must not block analysis storage.

## Commands

Run the indexer once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env
```

Run with explicit limits:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env -Days 30 -EventLimit 500 -AnalysisLimit 100
```

Register scheduled data/context tasks, including the RAG indexer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_market_analysis_tasks.ps1 -Force
```

## Configuration

| Variable | Default | Notes |
|---|---:|---|
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
- `raw_json.claim_verifier`

## Tests

Use focused tests after RAG or analysis changes:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_rag -v
```

If local dependencies are missing, state that verification could not run and why.

## Agent Rules

- Do not add external paid embedding providers unless the user explicitly approves the provider and cost model.
- Do not let RAG examples override current source facts.
- Do not use RAG examples as claim evidence for numbers, dates, or tickers in final output.
- Keep `memory-bank/09-decisions/2026-04-25-historical-case-rag.md` and `memory-bank/09-decisions/2026-05-07-hybrid-rag-stage0-claim-router.md` as historical decision records; put current operations here.
- When retrieval behavior, tables, or telemetry change, update this file, [PROJECT_INDEX.md](../PROJECT_INDEX.md), and [memory-bank/00-index.md](00-index.md).
