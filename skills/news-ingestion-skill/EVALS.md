# EVALS: news-ingestion-skill

## Eval Scope
- Schema correctness
- Source selection behavior
- Error surfacing behavior

## Offline Cases
| Case ID | Scenario | Expected Result | Category |
|---|---|---|---|
| OFF-001 | Missing Benzinga key with `--source benzinga` | Config error is raised | edge-case |
| OFF-002 | `--source all` with no Benzinga key | RSS and GDELT still run | happy-path |
| OFF-003 | Duplicate URLs from sources | Deduped output | regression |

## Online Monitoring
- Invalid-tool-call threshold: N/A (no LLM tool call in current phase)
- Source fetch error rate threshold: < 5% daily per source
- Latency p95 threshold: < 10s per source call

## Pass/Fail Gates
- Must pass local unit tests.
- Must include source-level error handling evidence.
