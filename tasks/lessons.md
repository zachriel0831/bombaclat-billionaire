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


## LESSON-20260307-01
- Date: 2026-03-07
- Trigger (User correction): User asked to replace X polling with stream listening.
- What was wrong: Bridge still handled X by polling cycle, not continuous stream.
- Root cause: Earlier implementation prioritized simpler API flow over fastest-delivery requirement.
- New rule (always/never): Always prioritize streaming ingestion when user asks for latest/fastest social feed.
- Prevention checklist (before final response):
  - [ ] Confirm requirement is stream vs polling
  - [ ] Split polling sources and streaming sources in bridge threads
  - [ ] Add reconnect/backoff and 429 stop behavior for stream sources
- Repo updates made:
  - `src/news_collector/x_stream.py`
  - `src/news_collector/relay_bridge.py`
  - `scripts/run_source_bridge.ps1`
  - `README.md`
  - `tests/test_x_stream.py`
  - `tasks/lessons.md`
- Verification evidence:
  - `python -m unittest discover -s tests -p "test_*.py" -v` passed (16 tests)
  - `python -m news_collector.relay_bridge --help` shows X stream args
- Status: active

## LESSON-20260421-01
- Date: 2026-04-21
- Trigger (User correction): User clarified that LINE service has migrated to the Java system and Python is now purely the data collection and analysis service.
- What was wrong: I initially framed the local Python relay as a LINE service and moved toward webhook/ngrok setup before separating the current Python-vs-Java responsibilities.
- Root cause: Legacy script/module names still include `event_relay`, and I mirrored those names in user-facing language instead of describing the current operational boundary.
- New rule (always/never): Always refer to this Python repository as the data collection and analysis service; Java owns LINE delivery/webhook behavior.
- Prevention checklist (before final response):
  - [ ] Distinguish Python data ingestion/analysis from Java-owned LINE delivery/webhook behavior
  - [ ] Avoid starting ngrok, LINE webhook, or LINE push paths from this repo unless explicitly requested as legacy compatibility work
  - [ ] When using legacy-named scripts/modules, explain the current runtime role rather than repeating outdated service names
- Repo updates made:
  - `tasks/lessons.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `memory-bank/workflows.md`
- Verification evidence:
  - Started `python -m event_relay.main --env-file .env --log-level INFO`
  - Verified `http://127.0.0.1:18090/healthz` returned `{"ok": true}`
- Status: active

## LESSON-20260422-01
- Date: 2026-04-22
- Trigger (User correction): User clarified that `t_market_analyses` should be written only after aggregating same-day `t_relay_events` and asking the model; REQ-009, REQ-010, and REQ-011 source/context events should all write to `t_relay_events`.
- What was wrong: I described REQ-011 too much like a direct analysis write and did not emphasize that its source/context facts must first become relay events.
- Root cause: I collapsed the source/event layer and the model-analysis layer when discussing the task dependency graph.
- New rule (always/never): Always keep source/context ingestion and model analysis as separate layers: source collectors write `t_relay_events`; analysis jobs read event windows and write `t_market_analyses`.
- Prevention checklist (before final response):
  - [ ] Confirm whether the task is collecting facts/events or generating analysis text
  - [ ] If it is collecting facts/events, ensure the destination is `t_relay_events`
  - [ ] If it writes `t_market_analyses`, confirm it is a model analysis job that reads `t_relay_events`
- Repo updates made:
  - `requirements.yml`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `git diff --check -- requirements.yml memory-bank/PROJECT_DOCUMENTATION.md tasks/todo.md tasks/lessons.md` passed with CRLF warnings only
  - `rg` confirmed REQ-009, REQ-010, and REQ-011 describe source/context events writing to `t_relay_events`
- Status: active

## LESSON-20260425-01
- Date: 2026-04-25
- Trigger (User correction): User pointed out `REQ-001` should already be complete and asked to verify it before leaving it non-done.
- What was wrong: The requirement was left in `review` based on an old pending DB note instead of being re-verified against the current live environment.
- Root cause: I relied on stale task comments and the global interpreter first, instead of checking the repo's intended `.venv` runtime and rerunning the blocked acceptance step.
- New rule (always/never): Always verify requirement status against current acceptance criteria using the repo's intended runtime environment before leaving a task in `review` or `pending`.
- Prevention checklist (before final response):
  - [ ] Re-run any acceptance item whose blocker was previously "needs runtime recheck" instead of trusting old notes
  - [ ] Confirm whether the repo expects `.venv` rather than the global interpreter for optional dependencies
  - [ ] If runtime success is followed by a console-encoding-only crash, separate data-path success from logging-path failure and fix the logging bug
- Repo updates made:
  - `src/scrapers/yfinance_stocks.py`
  - `requirements.yml`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - `.venv\\Scripts\\python.exe -m unittest tests.test_yfinance_stocks -v` passed (4/4)
  - `.venv\\Scripts\\python.exe src\\scrapers\\yfinance_stocks.py` fetched 26 symbols and wrote `data/stocks/stocks_20260425_025225.json`
  - MySQL query confirmed 26 same-day `t_relay_events` rows with `source LIKE 'yfinance%'`
- Status: active

## LESSON-20260425-02
- Date: 2026-04-25
- Trigger (User correction): User pointed out `REQ-008` should already be executed and asked for REQ-009 to be implemented only if it was truly incomplete.
- What was wrong: Requirement status in `requirements.yml` lagged behind actual implementation and verification state, which made already-finished work still look pending/review.
- Root cause: I relied too much on stale requirement statuses instead of re-verifying the live code, tests, scheduler state, and database writes before deciding whether work was incomplete.
- New rule (always/never): Always verify a requirement's real completion state from code + runtime evidence before assuming a pending/review status is still accurate.
- Prevention checklist (before final response):
  - [ ] Re-check whether the requirement file status is stale relative to the current repo state
  - [ ] Use both static evidence and runtime evidence before saying a feature is incomplete
  - [ ] If implementation already exists, sync requirement status instead of re-implementing blindly
- Repo updates made:
  - `requirements.yml`
  - `tasks/todo.md`
  - `tasks/lessons.md`
- Verification evidence:
  - Static grep confirmed REQ-008 Python LINE touch paths are absent from active code
  - Task Scheduler scan confirmed no AnalysisPush / LINE / SummarySender jobs remain
  - `.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v` passed (140 tests)
  - `scripts/run_tw_market_flow.ps1 -EnvFile .env` stored 14 REQ-009 dataset events with 0 failures
  - MySQL query confirmed new REQ-009 rows `19634-19647` in `t_relay_events`
- Status: active
