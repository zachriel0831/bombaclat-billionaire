# Engineering Workflows

## Workflow Orchestration (Default)
1. Plan first for non-trivial work
- If task has 3+ steps or architecture impact, start from `tasks/todo.md`.
- Write concrete checkable items before implementation.
2. Re-plan when things go sideways
- Stop when assumptions fail or repeated errors happen.
- Update plan and continue only after scope/approach is clear.
3. Verify before done
- Do not close task without evidence from tests/logs/runtime checks.
- Capture verification notes in `tasks/todo.md`.
4. Capture lessons after correction
- After user correction, append one entry to `tasks/lessons.md`.
- Add a prevention checklist that is specific and testable.

## Parallel Execution Strategy
1. Keep the main thread clean
- Offload independent checks/reads/tests in parallel when possible.
2. One sub-task per execution thread
- Avoid mixing unrelated concerns in one run.
3. Merge results into one concrete decision
- Record conclusions in `tasks/todo.md` progress notes.

## Self-Improvement Loop
1. After any user correction:
- add a lesson entry to `tasks/lessons.md`
2. Convert lesson into a rule:
- update `AGENTS.md` or `memory-bank/rules.md` when needed
3. Add prevention checks:
- use explicit pre-response checklist items
4. Revisit active lessons at task start:
- read `tasks/lessons.md` before major implementation

## Verification Before Done
1. Never mark done without proof
- tests, runtime output, or logs
2. Compare expected vs actual behavior
- especially when changing parsing, dedupe, or source mapping
3. Ask final quality question
- "Would a senior engineer approve this as production-safe?"

## Demand Elegance (Balanced)
1. For non-trivial changes:
- pause and choose the simplest robust solution
2. Avoid hacky local fixes if root-cause fix is clear
3. Skip over-engineering for trivial tasks

## Autonomous Bug Fixing
1. Reproduce first, then fix
2. Use failing evidence (errors/tests/logs) as entry point
3. Resolve without unnecessary user hand-holding when context is sufficient
4. Re-run relevant verification after fix

## Task Management Contract
1. Plan first in `tasks/todo.md`
2. Keep progress notes updated while executing
3. Mark checklist items as completed only with evidence
4. Record final review summary (outcome, evidence, risks)
5. Capture corrections in `tasks/lessons.md`

## Core Principles
- Simplicity first: minimal necessary changes
- No laziness: fix root causes over temporary patches
- Minimal impact: avoid touching unrelated code
- Evidence-driven completion: verify before closing

## Workflow 1: Add a New News Source
1. Define source contract
- auth type, endpoint, rate limits, fields, pagination
2. Implement adapter in `src/news_collector/sources/`
- convert to `NewsItem` normalized schema
3. Add source registration in `collector.py`
4. Update environment settings in:
- `.env.example`
- `config.py`
5. Add non-network unit tests (parsing/config behavior)
6. Update docs:
- `README.md`
- `memory-bank/PROJECT_DOCUMENTATION.md`

## Workflow 2: Fix Ingestion Bug
1. Reproduce issue with concrete CLI command
2. Identify root cause (timestamp parse, schema mismatch, network failure, dedupe key)
3. Apply minimal safe fix
4. Add regression test
5. Verify:
- run `python -m unittest discover -s tests -p "test_*.py"`
- run fetch command for impacted source
6. Document behavior change if external output changed

## Workflow 3: Prepare Release Baseline
1. Ensure CI passes (`build-test` workflow)
2. Validate required env vars and secret naming
3. Smoke check local commands:
- rss fetch
- x fetch
4. Confirm docs are aligned with behavior

## Workflow 4: Incident Handling (Source Outage / Rate Limit)
1. Confirm outage scope (single source vs all)
2. Keep collector running for healthy sources
3. Surface explicit error records
4. If issue persists, apply short-term fallback:
- lower request frequency
- reduce query breadth
- temporary source disable switch
5. Record decision in `memory-bank/09-decisions/`

## Workflow 4A: X Stream Recovery / Gap Backfill
1. Confirm bridge startup state
- Check bridge log for `X token preflight: resolved`, `Starting X account stream`, and `X filtered stream connected`
2. Confirm whether the gap is pre-connect only
- Compare missing tweet timestamps against the latest bridge start/connect time
3. Let startup backfill replay recent tracked-account tweets
- Bridge runs one-shot X backfill before attaching the live filtered stream
- Backfill replays into relay `/events`, so both `t_relay_events` and `t_x_posts` are updated through the normal path
4. Verify DB evidence
- Query `t_relay_events` by `event_id='x-<tweet_id>'`
- Query `t_x_posts` by `tweet_id`
5. If startup still says `missing X bearer token`
- run bridge through `scripts/run_source_bridge.ps1` so PowerShell preflight resolves DPAPI token into process env before Python starts

## Workflow 4B: US Index Stored-Only Event Flow
1. Send normalized relay events
- Post DJIA / S&P 500 open-close snapshots to relay `/events`
2. Attach structured market payload
- Include trade date, session (`open`/`close`), and per-index quote fields in `market_snapshot`
3. Persist on enqueue
- Relay writes the queue row into `t_relay_events` and snapshot rows into `t_market_index_snapshots`
4. Suppress user push
- Relay dispatch marks `source=us_index_tracker` as `stored_only_market`
5. Verify
- POST an `/events` payload with `market_snapshot`
- Query both `t_relay_events` and `t_market_index_snapshots` by `event_id`

## Workflow 5: Build a New Skill (Enterprise)
1. Create skill folder from templates:
- `skills/templates/SKILL_TEMPLATE.md`
- `skills/templates/EVALS_TEMPLATE.md`
- `skills/templates/CHANGELOG_TEMPLATE.md`
2. Register skill in `skills/registry.yaml`.
3. Define safety, failure handling, and eval thresholds.
4. Add regression cases for known incidents/lessons.
5. Run readiness validator:
- `python scripts/validate_readiness.py`
6. Update relevant docs and changelog before release.

## Workflow 6: Enterprise Readiness Review
1. Review baseline docs:
- `memory-bank/40-agent-enterprise-readiness.md`
- `memory-bank/42-agent-evals-and-release-gates.md`
- `memory-bank/43-agent-security-and-compliance.md`
- `memory-bank/44-mcp-server-governance.md`
2. Validate artifacts exist and are current.
3. Execute CI gates:
- `build-test`
- `readiness-gate`
4. Capture residual risks in `tasks/todo.md`.
