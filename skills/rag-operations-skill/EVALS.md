# EVALS: rag-operations-skill

## Eval Scope

- RAG indexing commands and table ownership are discoverable.
- RAG examples remain analogues, not current evidence.
- RAG failure behavior remains non-blocking.
- Telemetry fields are documented.

## Offline Cases

| Case ID | Scenario | Expected Result | Category |
|---|---|---|---|
| RAG-001 | RAG retrieval throws during market analysis | Analysis continues and records `raw_json.rag.error` | regression |
| RAG-002 | Historical example is selected | Prompt treats it as an analogue only | safety |
| RAG-003 | RAG config changes | `memory-bank/rag-operations.md` is updated | governance |
| RAG-004 | External embedding provider is proposed | User approval and cost model are required first | safety |

## Pass/Fail Gates

- Focused RAG/analysis tests pass when code changes.
- `python scripts/validate_readiness.py` passes after skill metadata changes.
