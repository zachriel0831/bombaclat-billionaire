# NEWS-3 Second-Pass Article Detail Author Backfill

## Status

Done

## Goal

Run the article-detail author backfill against the second-pass media list after
the first-pass sources reached acceptable coverage.

## Scope

- Second-pass media list: `tvbs`, `ebc`, `pts`, `ctee`.
- Reuse `scripts/backfill_news_author_detail_pages.py`.
- Keep the same data boundary as NEWS-2: only enrich reporter/byline metadata;
  do not persist article body HTML or article body text.

## Implementation Notes

- Tightened visible-text fallback after dry-run found EBC interview text such as
  `vs.記者：「...」` could be mistaken as a byline.
- Added editor-prefix cleanup for values like `實習編輯林瑜`.
- Added stdout UTF-8 reconfiguration so dry-run logs can print uncommon CJK
  characters on Windows.

## Run

Executed on 2026-05-15.

Commands:

```powershell
$env:PYTHONPATH='D:\work_space\stock\data-collecting\src'
.\.venv\Scripts\python.exe scripts\backfill_news_author_detail_pages.py --env-file .env --sources tvbs ebc pts ctee --limit 30 --sleep-seconds 0 --dry-run
.\.venv\Scripts\python.exe scripts\backfill_news_author_detail_pages.py --env-file .env --sources tvbs ebc pts ctee --limit 2000 --sleep-seconds 0.2 --quiet
.\.venv\Scripts\python.exe scripts\backfill_news_author_status.py --env-file .env
.\.venv\Scripts\python.exe scripts\build_news_author_coverage_daily.py --env-file .env --days 30
```

Backfill summary:

- Candidates: `1164`
- Present: `971`
- Low confidence: `190`
- Parse failed: `3`
- Relations added/refreshed: `1202`

Post-run second-pass source status:

| Source | Total | Present | Low Confidence | Parse Failed | No Detail Fetched | Parser Not Supported |
|---|---:|---:|---:|---:|---:|---:|
| `ctee` | 84 | 78 | 5 | 1 | 0 | 0 |
| `ebc` | 338 | 151 | 185 | 1 | 1 | 0 |
| `pts` | 87 | 85 | 0 | 0 | 0 | 2 |
| `tvbs` | 662 | 657 | 0 | 1 | 4 | 0 |

Global author state after NEWS-3:

- Article-detail present rows: `3544`
- Normalized author rows: `784`
- Article-author relation rows: `4464`
- Coverage rows affected by rebuild: `222`

## Verification

- `python -m unittest tests.test_news_platform_article_detail_author_extractor tests.test_news_platform_author_extractor`
- `scripts/build_news_author_coverage_daily.py --days 30`

## Follow-Up

- EBC remains the main low-confidence source. Sample those rows and add
  source-specific selectors only when false positive risk is lower than missed
  byline risk.
