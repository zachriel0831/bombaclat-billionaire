# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Route rule-unclassified news articles to `general_social_news` / 一般社會新聞.
- Requested by: user
- Start date: 2026-05-11
- Scope: Code fallback behavior, docs/spec updates, tests, and live DB update for existing `topics_json=[]` rows.

## Plan
- [x] Inspect current topic worker, LLM fallback worker, store SQL, docs, and tests.
- [x] Add reusable general-social fallback topic.
- [x] Update rule and LLM fallback workers to write general-social when no topic matches.
- [x] Keep LLM fallback eligible for rule fallback rows if enabled later.
- [x] Update docs/specs/tests.
- [x] Run tests and update live DB rows.
- [x] Verify live counts.

## Progress Notes
- 2026-05-11: Existing empty rows are `topics_json=[]` with `topic_classified_by='rule'`; target is no visible unclassified bucket.
- 2026-05-11: Live DB update converted 498 empty-topic rows to `general_social_news`.

## Verification
- [x] news_platform topic tests pass.
- [x] live DB no longer has `JSON_LENGTH(topics_json)=0`.
- [x] live DB has `general_social_news` rows for previous no-hit articles.
- [x] `git diff --check -- <changed news_platform/docs/spec/task files>`

## Review Summary
- Outcome: complete
- Evidence: 67 news_platform tests OK; compileall OK; diff check OK with CRLF warnings only; live DB updated 498 rows; counts now total=575, missing_topics=0, empty_topics=0, general_social_news=498, specific_topics=77.
- Open risks: LLM refinement remains disabled unless `NEWSPF_TOPIC_LLM_ENABLED=true` or manual `--llm-topic-fallback` is run.
