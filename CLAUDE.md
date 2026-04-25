# CLAUDE.md

Project-specific guidance for Claude Code. Keep this short.

## Style
- Default to terse responses. Skip the closing summary table unless explicitly asked.
- State what you did in 1-3 lines, then stop.

## Don't pre-load
- Do NOT read all memory-bank files at session start. AGENTS.md lists them; read **only the one(s) the task touches**.
- Do NOT auto-update `tasks/todo.md` or `tasks/lessons.md` for small fixes. Only when the user asks, or when scope spans multiple sessions.
- Do NOT write a decision doc under `memory-bank/09-decisions/` for routine changes. Ask first.

## Environment
- Python: `.venv/Scripts/python.exe` (Python 3.13). `pytest` is NOT installed.
- Run tests: `PYTHONPATH=src .venv/Scripts/python.exe -m unittest discover -s tests`
- Source layout: `src/<package>/...`; tests in `tests/`. PYTHONPATH=src is required.
- Shell: bash on Windows. Use forward slashes; `/dev/null` not `NUL`.

## Verification
- Don't claim done without running tests when you changed code.
- `compileall` + `unittest discover` covers most of this repo.

## Out of scope
- LINE delivery — owned by `line-relay-service` (separate repo). This repo never re-introduces a linebot/webhook/push code path.
- Direct broker API calls — see [memory-bank/09-decisions/2026-04-25-auto-trading-system-boundaries.md](memory-bank/09-decisions/2026-04-25-auto-trading-system-boundaries.md). LLM never touches order intent submission.
