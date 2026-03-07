# PR Review Standards

## P0 (Must Fix)
- Secret leakage (API keys in code/logs/docs)
- Incorrect source parsing causing wrong article URLs/timestamps
- Breaking schema output contract
- Crash paths that stop all sources

## P1 (Should Fix Before Merge)
- Missing error handling for source-specific failures
- Weak dedupe key leading to repeated spam
- Missing tests for changed non-network logic
- Docs not updated after behavior or schema changes

## P2 (Follow-up)
- Naming/readability issues without behavior impact
- Minor observability improvements
- Refactors not required for current scope

## Review Checklist
- Correctness: output fields and timestamp parsing
- Reliability: retry/timeout behavior and partial failure handling
- Security: secrets and sensitive output
- Maintainability: adapter boundaries and shared utility usage
- Testing: regression tests for changed logic
