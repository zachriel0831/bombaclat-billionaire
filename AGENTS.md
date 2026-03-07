# AGENTS.md

## Scope
These instructions apply to this repository.

## Primary Knowledge Sources
Before making changes, reviewing code, or answering project-specific questions, read relevant files in this order:
1. `memory-bank/00-index.md`
2. `memory-bank/PROJECT_DOCUMENTATION.md`
3. `memory-bank/rules.md`
4. `memory-bank/workflows.md`
5. `memory-bank/40-agent-enterprise-readiness.md` (for agent/skills planning)
6. `tasks/lessons.md` (active lessons and prevention rules)
7. Related source files for the task

## Working Rules
- Confirm `memory-bank/PROJECT_DOCUMENTATION.md` before generating or changing code.
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
