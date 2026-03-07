# Lessons Log

This file is append-only. Add a new entry after any user correction to prevent repeated mistakes.

## Entry Pattern

```md
## LESSON-YYYYMMDD-XX
- Date:
- Trigger (User correction):
- What was wrong:
- Root cause:
- New rule (always/never):
- Prevention checklist (before final response):
  - [ ] Check 1
  - [ ] Check 2
  - [ ] Check 3
- Repo updates made:
  - file/path
- Verification evidence:
  - command/output summary
- Status: active
```

## Active Lessons

<!-- Add new lessons below this line -->

## LESSON-20260305-01
- Date: 2026-03-05
- Trigger (User correction): User requested persistent correction memory and explicit pattern in `tasks/lessons.md`.
- What was wrong: Repository had no formal correction-capture loop, so repeated mistakes were not systematically prevented.
- Root cause: Process focused on implementation outputs, not explicit post-correction learning artifacts.
- New rule (always/never): Always append a structured lesson after user correction and reference it in future task start checks.
- Prevention checklist (before final response):
  - [ ] Re-check `tasks/lessons.md` for applicable active lessons
  - [ ] Confirm `tasks/todo.md` includes verification evidence
  - [ ] If user corrected current task, append a new lesson entry
- Repo updates made:
  - `tasks/lessons.md`
  - `tasks/todo.md`
  - `AGENTS.md`
  - `memory-bank/workflows.md`
- Verification evidence:
  - Added and linked workflow files
  - Ran compile and unit tests successfully
- Status: active

## LESSON-20260305-02
- Date: 2026-03-05
- Trigger (User correction): User asked to stop blocking Korean and requested stream output to keep only top-level `url`.
- What was wrong: Stream runner defaulted to English-only filter, and output shape stayed full JSON event even when user wanted URL-only feed.
- Root cause: Initial defaults optimized readability, not downstream URL-only integration use case.
- New rule (always/never): Always confirm output contract (full JSON vs selected fields) and avoid restrictive language defaults unless explicitly requested.
- Prevention checklist (before final response):
  - [ ] Confirm required output fields with the user request text
  - [ ] Check script defaults do not silently filter data
  - [ ] Run CLI help or sample run to verify new flags are wired
- Repo updates made:
  - `src/news_collector/main.py`
  - `scripts/run_benzinga_stream.ps1`
  - `README.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m compileall src` passed
  - `python -m news_collector.main stream --help` shows `--url-only`
  - Stream run executed with `-UrlOnly` (received 429 during test window)
- Status: active

## LESSON-20260305-03
- Date: 2026-03-05
- Trigger (User correction): User expected `.env.example` edits to affect runtime behavior and asked to remove the template file.
- What was wrong: Runtime read `.env` only, causing mismatch with user expectation after editing `.env.example`.
- Root cause: Environment file contract was implicit and not enforced with clear runtime messaging/documentation.
- New rule (always/never): Always make runtime env source explicit and keep file conventions unambiguous to avoid config drift.
- Prevention checklist (before final response):
  - [ ] Verify which env file is loaded by runtime command path
  - [ ] Ensure docs match actual runtime env behavior
  - [ ] Remove or rename misleading template files if requested
- Repo updates made:
  - `README.md`
  - `.env.example` (removed)
  - `src/news_collector/main.py`
  - `tasks/lessons.md`
- Verification evidence:
  - Confirmed `.env.example` no longer exists
  - Ran one-shot GDELT fetch with language/title-url filters
- Status: active

## LESSON-20260305-04
- Date: 2026-03-05
- Trigger (User correction): User requested GDELT 429 handling to be switchable and currently turned off.
- What was wrong: 429 cooldown behavior was hardcoded, reducing operational flexibility during live tuning.
- Root cause: Protective logic was implemented without an environment-level feature switch.
- New rule (always/never): Always expose rate-limit mitigation as explicit config switches with conservative defaults.
- Prevention checklist (before final response):
  - [ ] Verify 429 behavior is configurable through env
  - [ ] Confirm default value matches user-requested operational mode
  - [ ] Restart long-running service after config or source logic changes
- Repo updates made:
  - `src/news_collector/config.py`
  - `src/news_collector/collector.py`
  - `src/news_collector/sources/gdelt.py`
  - `.env`
  - `README.md`
  - `tests/test_config.py`
  - `tests/test_collector.py`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m compileall src tests` passed
  - `python -m unittest discover -s tests -p \"test_*.py\" -v` passed
  - runtime config shows `gdelt_cooldown_on_429=False`
- Status: active
