# NEWS-2 Article Detail Author Backfill

## Status

Done

## Goal

Backfill missing reporter names for existing Taiwan news articles when RSS,
sitemap, or list sources already provided article URL/title/time/category but did
not provide usable byline metadata.

## Scope

- Supported media list: `cna`, `storm`, `newtalk`, `ltn`, `ettoday`,
  `tvbs`, `ebc`, `ctee`, and `pts`.
- Only process rows whose `authors_json` is empty and whose
  `author_extraction_status` is not `present`.
- Fetch public article detail HTML only to extract reporter/byline metadata.
- Do not store article body HTML or article body text.
- Write only author metadata fields and normalized author relations.

## Implementation

- Utility class:
  - `src/news_platform/article_detail_author_extractor.py`
  - Reads JSON-LD `author`/`creator`, author meta tags, and short visible byline
    windows around common reporter markers.
- Loop worker:
  - `src/news_platform/author_detail_worker.py`
  - Runs a bounded batch from `news_platform.main --loop` when
    `NEWSPF_AUTHOR_DETAIL_BACKFILL_ENABLED=true`.
  - Default loop retry statuses are `NULL`, `no_detail_fetched`, and
    `parser_not_supported`; `low_confidence` is left for manual repair to avoid
    repeatedly fetching pages that already failed extraction.
- Backfill script:
  - `scripts/backfill_news_author_detail_pages.py`
  - Supports `--dry-run`, `--sources`, `--limit`, `--sleep-seconds`,
    `--retry-failed`, and `--quiet`.
- Existing helpers reused:
  - `news_platform.author_extractor.normalize_authors`
  - `news_platform.store.NewsPlatformStore.upsert_article_author_relations`

## First Run

Executed on 2026-05-15 for the first-pass media list.

Commands:

```powershell
$env:PYTHONPATH='D:\work_space\stock\data-collecting\src'
.\.venv\Scripts\python.exe scripts\backfill_news_author_detail_pages.py --env-file .env --limit 300 --sleep-seconds 0.2 --quiet
.\.venv\Scripts\python.exe scripts\backfill_news_author_detail_pages.py --env-file .env --limit 3000 --sleep-seconds 0.2 --quiet
.\.venv\Scripts\python.exe scripts\backfill_news_author_status.py --env-file .env
.\.venv\Scripts\python.exe scripts\build_news_author_coverage_daily.py --env-file .env --days 30
```

Backfill summary:

- First batch: `present=289`, `low_confidence=11`, `relations=330`.
- Full batch: `present=2284`, `low_confidence=104`, `parse_failed=4`,
  `relations=2804`.
- Total normalized author rows after run: `567`.
- Total article-author relation rows after run: `3262`.

Post-run first-pass source status:

| Source | Total | Present | Low Confidence | Parse Failed | No Detail Fetched | Parser Not Supported |
|---|---:|---:|---:|---:|---:|---:|
| `cna` | 378 | 378 | 0 | 0 | 0 | 0 |
| `ettoday` | 669 | 665 | 0 | 3 | 0 | 1 |
| `ltn` | 1154 | 1043 | 104 | 1 | 6 | 0 |
| `newtalk` | 356 | 353 | 0 | 0 | 3 | 0 |
| `storm` | 282 | 282 | 0 | 0 | 0 | 0 |

## Verification

- `python -m unittest tests.test_news_platform_article_detail_author_extractor tests.test_news_platform_author_extractor`
- `scripts/build_news_author_coverage_daily.py --days 30`

## Follow-Up

- Review LTN and EBC low-confidence rows and decide whether to add
  source-specific selectors.
- Keep loop batch size small enough to avoid delaying keyword/topic/public-record
  work or overloading source sites.
