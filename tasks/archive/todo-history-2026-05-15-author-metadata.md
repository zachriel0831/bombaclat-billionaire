# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Capture reporter/author metadata from new news-platform RSS/sitemap articles.
- Requested by: user
- Start date: 2026-05-15
- Scope: `NewsArticle` model, RSS/sitemap parsers, MySQL article schema, tests, and schema docs.

## Plan
- [x] Record the task before implementation.
- [x] Inspect article model, RSS/sitemap parsers, store schema, and docs.
- [x] Add optional author/reporter extraction for RSS/Atom/sitemap rows.
- [x] Persist author metadata on `t_news_articles`.
- [x] Update focused parser/model/store tests.
- [x] Update schema/data-flow docs.
- [x] Run focused tests and readiness validation.

## Progress Notes
- 2026-05-15: Existing `NewsArticle` rows store `tags_json` and `raw_json`, but no dedicated author/reporter field.
- 2026-05-15: RSS/Atom parsers can access author-like XML nodes; Google News sitemap usually has no reporter field, but parser can preserve optional `author`/`creator` metadata when present.
- 2026-05-15: Added `authors_json` migration, parser extraction, and source raw trace field `raw_json.author_values`.
- 2026-05-15: Duplicate article fetches now refresh empty `authors_json` when the current parse has author names, while still counting as duplicates.
- 2026-05-15: Live DB migration was initially blocked by a long-open `news_platform.main --loop` MySQL transaction. Cancelled the waiting ALTER, killed only that MySQL connection, then added `authors_json` successfully.

## Verification
- [x] `python -m py_compile src/news_platform/author_extractor.py src/news_platform/models.py src/news_platform/sources/rss_feed.py src/news_platform/sources/sitemap_news.py src/news_platform/store.py`
- [x] `$env:PYTHONPATH='src'; python -m unittest tests.test_news_platform_author_extractor tests.test_news_platform_models tests.test_news_platform_rss tests.test_news_platform_sitemap tests.test_news_platform_store_topics -v`
- [x] `python scripts/validate_readiness.py`
- [x] Live DB: `authors_json_exists_after=1`
- [x] Live DB: `store_initialize_ok`
- [x] Restarted `news_platform.main --loop`; latest cycle fetched 324, stored 3, duplicates 321, failed 0.
- [x] Live DB: `rows_with_authors=87`
- [x] Process check: `root_loop_instances=1`

## Review Summary
- Outcome: Done.
- Evidence: Focused tests passed (33 tests), readiness validation passed, live `news_platform.t_news_articles.authors_json` exists, and restarted loop is running as one root instance.
- Open risks: Old rows only get author metadata if they are recrawled with author/byline text; deep historical backfill still needs a separate job.
