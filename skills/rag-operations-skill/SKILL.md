---
name: rag-operations-skill
description: Maintain, debug, or extend historical-case RAG in data-collecting. Use when working on event_relay.rag, t_event_embeddings, t_analysis_embeddings, run_rag_indexer.ps1, MARKET_ANALYSIS_RAG_* settings, RAG telemetry in t_market_analyses.raw_json, stage2 historical analogues, or RAG failure handling.
---

# RAG Operations Skill

## Purpose

Use this skill for historical-case RAG work in the market-analysis pipeline.

## Start Here

1. Read [../../memory-bank/rag-operations.md](../../memory-bank/rag-operations.md).
2. Read [../../memory-bank/09-decisions/2026-04-25-historical-case-rag.md](../../memory-bank/09-decisions/2026-04-25-historical-case-rag.md) only when decision history matters.
3. Read [../../memory-bank/09-decisions/2026-05-07-hybrid-rag-stage0-claim-router.md](../../memory-bank/09-decisions/2026-05-07-hybrid-rag-stage0-claim-router.md) when changing hybrid ranking, stage0, claim verification, or provider compacting.
4. Inspect `src/event_relay/rag.py` and `src/event_relay/market_analysis.py` for implementation details.

## Rules

- RAG examples are historical analogues, not current evidence.
- Do not use historical example IDs as current evidence IDs or trigger IDs.
- RAG failure must degrade to zero examples and record telemetry; it must not block market-analysis storage.
- Keep default embeddings local (`local-hash-v1`) unless the user approves an external provider and cost model.
- Update [../../memory-bank/rag-operations.md](../../memory-bank/rag-operations.md) whenever tables, config, telemetry, commands, or fallback behavior change.

## Verification

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_rag tests.test_analysis_stages tests.test_market_analysis -v
python scripts/validate_readiness.py
```
