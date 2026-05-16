# EVALS: news-ingestion-skill

## Eval Scope
- Schema correctness
- Source selection behavior
- Error surfacing behavior

## Offline Cases
| Case ID | Scenario | Expected Result | Category |
|---|---|---|---|
| OFF-001 | RSS source has one failing feed | Other feeds still return normalized items and the failure is surfaced | edge-case |
| OFF-002 | `--source all` with optional paid sources disabled | Enabled no-key sources still run | happy-path |
| OFF-003 | Duplicate URLs from sources | Deduped output | regression |
| OFF-004 | Public-record collection receives duplicate official rows | Upsert keeps stable records and links | regression |
| OFF-005 | Topic classifier sees a rule no-hit row | Category-specific general topic fallback is stored | edge-case |

## Online Monitoring
- Invalid-tool-call threshold: N/A (no LLM tool call in current phase)
- Source fetch error rate threshold: < 5% daily per source
- Latency p95 threshold: < 10s per source call

## Pass/Fail Gates
- Must pass local unit tests.
- Must include source-level error handling evidence.
- Must not reintroduce LINE delivery, public API serving, live quote monitoring, or broker calls into this repo.
