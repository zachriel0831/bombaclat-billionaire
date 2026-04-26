# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Slim memory-bank and reduce token-heavy default context loading
- Requested by: User
- Start date: 2026-04-26
- Scope: keep only useful memory-bank entrypoints active, archive enterprise-heavy docs, and make AGENTS load context on demand.

## Plan
- [x] Archive stale `tasks/todo.md` history.
- [x] Move enterprise-only memory-bank docs out of the default path.
- [x] Update indexes, AGENTS, workflows, README, and readiness references.
- [x] Verify references and diff hygiene.

## Progress Notes
- 2026-04-26 - Archived old task log to `tasks/archive/todo-history-2026-04-26.md`.
- 2026-04-26 - Moved enterprise docs to `memory-bank/archive/enterprise/` and made AGENTS load memory-bank on demand only.

## Verification
- [x] Reference scan passes
- [x] `git diff --check` passes for touched docs

## Review Summary
- Outcome: completed
- Evidence:
  - `rg -n "memory-bank/(40-agent|41-skills|42-agent|43-agent|44-mcp)" .` returned no matches
  - `.venv\Scripts\python.exe scripts\validate_readiness.py` passed
  - `git diff --check -- AGENTS.md README.md memory-bank tasks scripts/validate_readiness.py` passed
- Open risks: existing unrelated dirty source files are not part of this task.
