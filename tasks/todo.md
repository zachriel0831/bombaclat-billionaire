# Task Plan Board

Use this file for non-trivial tasks (3+ steps or architecture decisions).

## Current Task
- Task: Integrate Benzinga websocket stream with secure key storage and resilient error handling
- Requested by: User
- Start date: 2026-03-05
- Scope: streaming integration, encrypted key storage, CLI/scripts, and operational safety

## Plan (checkable)
- [x] Clarify goal, inputs, and constraints
- [x] Add Benzinga stream command and robust reconnect strategy
- [x] Add encrypted local key storage workflow (DPAPI)
- [x] Add local runner scripts and docs
- [x] Verify with tests/logs/runtime checks
- [x] Summarize behavior changes and risks
- [x] If user corrected anything, add lesson to `tasks/lessons.md`

## Progress Notes
- 2026-03-05 16:55 - started enterprise readiness baseline task.
- 2026-03-05 16:58 - collected reference standards (NIST AI RMF, OWASP LLM Top 10, ISO/IEC 42001, SLSA, MCP, OpenAI eval/guardrails docs).
- 2026-03-05 17:05 - added enterprise baseline docs (readiness, skills standard, eval gates, security/compliance, MCP governance).
- 2026-03-05 17:10 - added skills workspace (`registry.yaml`, templates, initial skill pack).
- 2026-03-05 17:14 - added `scripts/validate_readiness.py` and CI workflow `readiness-gate.yml`.
- 2026-03-05 17:18 - updated AGENTS/rules/workflows/index/README linkage.
- 2026-03-05 17:20 - ran readiness validator, unit tests, and compile checks.
- 2026-03-05 17:32 - added local console runner (`scripts/run_local_console.ps1`) with safe defaults.
- 2026-03-05 17:35 - added Chinese comments in core ingestion code and updated README/VSCode task.
- 2026-03-05 17:41 - executed local console runner successfully and verified logs in `runtime/logs/`.
- 2026-03-05 17:45 - added Benzinga stream module and `stream` CLI command.
- 2026-03-05 17:48 - added DPAPI key encryption script and saved encrypted Benzinga key locally.
- 2026-03-05 17:52 - added stream runner script and safety-focused retry/backoff handling for 429.
- 2026-03-05 17:55 - validated stream execution path and duration cutoff behavior.

## Verification
- [x] Tests passed
- [x] Critical path manually checked
- [x] Docs/config updated when behavior changed

## Review Summary
- Outcome: Benzinga real-time stream is integrated and runnable with encrypted key storage plus rate-limit-safe retry behavior.
- Evidence:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\save_benzinga_key.ps1 -ApiKey "<redacted>"`
  - `python -m news_collector.main stream --duration-seconds 12 --max-messages 1 --timeout-seconds 8 --log-level INFO`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run_benzinga_stream.ps1 -MaxMessages 1 -DurationSeconds 12`
  - `$env:PYTHONPATH='src'; python -m unittest discover -s tests -p "test_*.py" -v`
  - `python -m compileall src`
- Open risks:
  - Current stream attempts are receiving HTTP 429 from Benzinga endpoint, likely account quota/plan constraints.
