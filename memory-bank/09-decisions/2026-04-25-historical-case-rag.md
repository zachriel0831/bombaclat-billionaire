# Decision: Add Historical-Case RAG for Market Analysis

## Context
REQ-014 asks market analysis to learn from similar historical events rather than relying only on the current event window and model memory.

## Decision
- Add `t_event_embeddings` and `t_analysis_embeddings` as local retrieval indexes.
- Keep source facts in `t_relay_events` and generated analysis in `t_market_analyses`.
- Add `event_relay.rag` as the indexing and retrieval module.
- Start with deterministic local lexical embeddings named `local-hash-v1`.
- Feed retrieved examples into `stage2_transmission` only as historical analogues.
- If RAG is empty or fails, continue market analysis and record the condition in `t_market_analyses.raw_json.rag`.

## Rationale
- The local embedding avoids a new paid API dependency while the table contract remains compatible with future OpenAI, Voyage, or BGE embeddings.
- Stage2 is the right first integration point because it reasons about transmission chains, where historical analogues are useful without becoming direct evidence.
- Keeping historical examples out of `trigger_event_ids` preserves existing evidence traceability rules.

## Consequences
- `scripts/run_rag_indexer.ps1` should run before daily market analysis windows.
- `scripts/register_market_analysis_tasks.ps1` now registers `NewsCollector-RagIndexer` at `04:40`.
- Prompt snapshots for stage2 include `Historical retrieved examples JSON`.
- Retrieval quality is lexical in v1; a semantic embedding provider can be added later without changing the market-analysis prompt contract.
