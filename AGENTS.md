# AGENTS.md

## Scope
These instructions apply to this repository.

## Context Loading
Do not preload the whole `memory-bank/`.
Read only the smallest useful set for the task.

Default:
1. `memory-bank/rules.md`
2. Related source files for the task

Add these only when relevant:
- `memory-bank/PROJECT_DOCUMENTATION.md`: architecture, schema, data flow, source mapping, scheduler, or service-boundary changes
- `memory-bank/workflows.md`: service operations, runbooks, or repeatable workflow changes
- `tasks/lessons.md`: user corrections, repeated mistakes, or task-start prevention checks
- `tasks/todo.md`: non-trivial work with 3+ steps or architecture decisions
- `memory-bank/09-decisions/`: decisions that explain existing behavior
- `memory-bank/archive/enterprise/`: agent platform, skills, MCP, enterprise readiness, or eval-governance work

## Working Rules
- Confirm `memory-bank/PROJECT_DOCUMENTATION.md` only before architecture, schema, data-flow, source-mapping, scheduler, or service-boundary code changes.
- Prefer official data-source docs and repository facts over assumptions.
- If required project information is missing, state the gap explicitly.
- Do not modify unrelated files.
- When data flow, source mapping, or alert behavior changes, update docs in `memory-bank/`.
- Record important architecture and workflow decisions under `memory-bank/09-decisions/`.
- For non-trivial tasks (3+ steps or architecture decisions), update `tasks/todo.md` before implementation and keep checkboxes in sync.
- If a user corrects your answer or approach, append a new entry to `tasks/lessons.md` using the defined pattern.
- If implementation goes sideways (failed assumption, repeated errors, broken verification), stop and re-plan in `tasks/todo.md` before continuing.
- Do not mark work complete without verification evidence (tests, logs, or runtime output).
- Prefer parallel execution for independent checks to keep task flow efficient.
- For agent/skills related changes, run readiness gate locally: `python scripts/validate_readiness.py`.

## Response Style
- Default response style is primitive-short: minimal words, direct meaning, no filler.
- Prefer 1-3 concise lines for routine answers.
- Avoid long summaries, tables, and repeated context unless the user explicitly asks.
- Keep enough technical detail to be correct; stop once the point is clear.

## PR Review Expectations
When asked to review code, prioritize:
1. Correctness and regression risk
2. Security / secret handling / token leakage
3. Data quality risk (duplicate events, wrong timestamps, wrong normalization)
4. Retry / timeout / failure handling
5. Rate-limit handling and vendor quota side effects
6. Test coverage gaps

Review output should list findings first with severity (P0/P1/P2), then open questions/assumptions, then a short summary.

## Documentation Maintenance
If new repeatable workflows are added, create/update focused markdown files under `memory-bank/` and reference them from `memory-bank/00-index.md`.
