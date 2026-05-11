# Archived Task - 2026-05-11 public-record foundation

## Outcome
Added official public-record storage and article linkage for Taiwan society/politics data.

## Evidence
- `python -m unittest tests.test_news_platform_public_records tests.test_news_platform_config tests.test_news_platform_store_topics tests.test_news_platform_topic_llm` passed 12 tests.
- `python -m compileall -q src/news_platform` passed.
- Local schema initialization verified `t_public_records` exists with 15 columns and `t_news_article_public_record_links` exists with 8 columns.

## Open Risks
Initial implementation is storage/linking foundation; individual source adapters still need follow-up ingestion tasks.
