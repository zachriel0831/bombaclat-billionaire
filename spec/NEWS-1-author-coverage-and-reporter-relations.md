# NEWS-1 Reporter Identity Relations And Byline Coverage Tracking

## Metadata

| Field | Value |
|---|---|
| Requirement ID | `NEWS-1` |
| Status | `Done` |
| Created | 2026-05-15 |
| Repo | `D:/work_space/stock/data-collecting` |
| Area | `src/news_platform` ingestion, storage, and data-quality metrics |
| Primary user goal | Track reporters as a reusable analysis dimension and count missing reporter names per media source. |

## Summary

The current news-platform pipeline already captures reporter/author names into
`t_news_articles.authors_json` when RSS/Atom/sitemap metadata or high-confidence
byline text is available.

`NEWS-1` turns that raw JSON field into a measurable author system:

1. Keep `authors_json` as the raw article-level capture.
2. Add normalized reporter entities.
3. Add article-to-reporter relations for articles that have names.
4. Add explicit article-level extraction status for articles that do not have
   reporter names.
5. Add daily source/category coverage statistics so the platform can measure
   which media sources habitually publish, omit, or hide bylines.

Do not create fake `unknown` reporter rows. Missing reporter names are tracked
as article/source coverage state, not as people.

## Implementation Status

Implemented on 2026-05-15.

- `data-collecting` writes article-level author extraction status and author
  relations.
- Existing local data was backfilled into `t_news_authors`,
  `t_news_article_authors`, and `t_news_author_coverage_daily`.
- `news-platform-api` exposes middle-office read endpoints under
  `/api/middle-office/news/*`.
- Public frontend display remains unchanged.

## Current State

Observed implementation:

- `NewsArticle.authors` exists in `src/news_platform/models.py`.
- `author_extractor.py` normalizes explicit author metadata and common Taiwan
  byline patterns such as reporter/location text.
- RSS/Atom ingestion reads author-like fields and falls back to byline extraction
  from title/summary.
- Sitemap ingestion reads optional `author` / `creator` metadata.
- `NewsPlatformStore.upsert_article` writes `authors_json`.
- Duplicate article fetches can refresh `authors_json` only when the stored
  value is empty and the new fetch contains authors.

Observed local DB snapshot on 2026-05-15:

| Metric | Count |
|---|---:|
| `t_news_articles` total rows | 3802 |
| Rows with non-empty `authors_json` | 111 |

Top sources with captured names in the snapshot:

| source_id | category | total | with authors |
|---|---|---:|---:|
| `cna` | `politics` | 183 | 31 |
| `storm` | `politics` | 170 | 25 |
| `cna` | `society` | 179 | 23 |
| `storm` | `society` | 97 | 17 |
| `newtalk` | `society` | 102 | 12 |

This proves the field exists, but coverage is uneven. The next design must
distinguish media non-disclosure from crawler/parser limitations.

## Goals

- Make reporters queryable across articles, categories, topics, and sources.
- Preserve original article-level author text for audit/debugging.
- Track articles with no captured reporter names as first-class data-quality
  records.
- Support source-level byline transparency metrics, such as "CNA politics has
  17 percent named reporters in the latest day."
- Enable later product features:
  - reporter profile pages
  - reporter-topic concentration
  - source byline transparency dashboard
  - media-behavior analysis by topic, category, and event thread

## Non-Goals

- Do not remove `authors_json`.
- Do not require frontend/API changes in this requirement.
- Do not crawl every article detail page in the first implementation unless a
  source-specific parser is explicitly added.
- Do not infer a real person's identity across different media solely by name.
  `source_id + normalized_name` is the initial identity boundary.
- Do not treat missing names as a reporter entity.

## Proposed Data Model

### `t_news_articles` Additions

Keep `authors_json` and add extraction metadata:

| Column | Type | Meaning |
|---|---|---|
| `author_extraction_status` | `VARCHAR(32) NULL` | Article-level author capture result. |
| `author_extraction_method` | `VARCHAR(32) NULL` | Best method used for this article. |
| `author_extraction_confidence` | `DECIMAL(5,4) NULL` | Best confidence score for article-level extraction. |
| `author_raw_text` | `TEXT NULL` | Original byline/author text when available. |
| `author_extracted_at` | `DATETIME NULL` | UTC timestamp for extraction or status assignment. |

Recommended status values:

| Status | Meaning | Counts as without author? |
|---|---|---|
| `present` | At least one author was captured and normalized. | No |
| `no_author_metadata` | Checked available feed/detail fields and found no author-like metadata. | Yes |
| `no_detail_fetched` | Only feed/sitemap/list metadata was checked; article detail page was not fetched. | Yes |
| `parser_not_supported` | Source has no detail parser or unsupported markup. | Yes |
| `parse_failed` | Parser or fetch failed before author state could be trusted. | Yes, but should be reported separately |
| `low_confidence` | Candidate byline existed but failed confidence/cleaning rules. | Yes, but should be reviewed |

Recommended method values:

| Method | Meaning |
|---|---|
| `rss_metadata` | Explicit RSS/Atom author-like node. |
| `sitemap_metadata` | Explicit sitemap author/creator metadata. |
| `byline_regex` | High-confidence byline extracted from title/summary/body text. |
| `article_detail` | Source-specific article page parser. |
| `manual` | Human/manual correction. |
| `none` | No usable method or no author found. |

### `t_news_authors`

Normalized reporter/author dimension.

```sql
CREATE TABLE t_news_authors (
  id BIGINT NOT NULL AUTO_INCREMENT,
  author_key VARCHAR(96) NOT NULL,
  source_id VARCHAR(32) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  normalized_name VARCHAR(128) NOT NULL,
  author_type VARCHAR(32) NOT NULL DEFAULT 'reporter',
  aliases_json JSON NULL,
  profile_url TEXT NULL,
  first_seen_at DATETIME NULL,
  last_seen_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_author_key (author_key),
  UNIQUE KEY uq_source_author_name (source_id, normalized_name),
  KEY idx_source_id (source_id),
  KEY idx_normalized_name (normalized_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Initial `author_key` rule:

```text
sha256("news_author:" + source_id + ":" + normalized_name)
```

This intentionally treats `cna:陳俊華` and `storm:陳俊華` as different author
entities until a later identity-resolution feature exists.

### `t_news_article_authors`

Many-to-many article-author relation. Use the stable article string ID to match
existing link-table style in `t_news_article_public_record_links`.

```sql
CREATE TABLE t_news_article_authors (
  id BIGINT NOT NULL AUTO_INCREMENT,
  article_id VARCHAR(64) NOT NULL,
  author_id BIGINT NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'reporter',
  ordinal SMALLINT NOT NULL DEFAULT 1,
  extraction_method VARCHAR(32) NOT NULL,
  confidence DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
  raw_text TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_article_author_role (article_id, author_id, role),
  KEY idx_article_id (article_id),
  KEY idx_author_id (author_id),
  KEY idx_role (role),
  KEY idx_extraction_method (extraction_method)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### `t_news_author_coverage_daily`

Daily materialized stats for source/category transparency. This can be generated
by a daily job or refreshed during the source health report.

```sql
CREATE TABLE t_news_author_coverage_daily (
  id BIGINT NOT NULL AUTO_INCREMENT,
  stat_date DATE NOT NULL,
  source_id VARCHAR(32) NOT NULL,
  category VARCHAR(32) NOT NULL,
  article_count INT NOT NULL DEFAULT 0,
  with_author_count INT NOT NULL DEFAULT 0,
  without_author_count INT NOT NULL DEFAULT 0,
  no_author_metadata_count INT NOT NULL DEFAULT 0,
  no_detail_fetched_count INT NOT NULL DEFAULT 0,
  parser_not_supported_count INT NOT NULL DEFAULT 0,
  parse_failed_count INT NOT NULL DEFAULT 0,
  low_confidence_count INT NOT NULL DEFAULT 0,
  coverage_rate DECIMAL(6,5) NOT NULL DEFAULT 0.00000,
  generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_category_day (stat_date, source_id, category),
  KEY idx_source_date (source_id, stat_date),
  KEY idx_category_date (category, stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`coverage_rate`:

```text
with_author_count / article_count
```

The dashboard should also show the component missing states. A low coverage rate
with high `no_detail_fetched_count` means the crawler is incomplete; a low rate
with high `no_author_metadata_count` after detail parsing may indicate source
byline non-disclosure.

## Extraction Semantics

For each article:

1. Parse explicit metadata first.
2. If metadata has author values, normalize and set:
   - `author_extraction_status=present`
   - `author_extraction_method=rss_metadata` or `sitemap_metadata`
3. If metadata is absent, try high-confidence byline regex on available title
   and summary.
4. If regex succeeds, set:
   - `author_extraction_status=present`
   - `author_extraction_method=byline_regex`
5. If a source-specific detail parser exists, fetch detail page and try
   source-specific byline extraction.
6. If no name is found, set one of:
   - `no_author_metadata`
   - `no_detail_fetched`
   - `parser_not_supported`
   - `parse_failed`
   - `low_confidence`

Never infer "media does not disclose reporters" at article-write time. That is a
source-level analysis derived from coverage stats after parser support is known.

## Write Path

When `NewsPlatformStore.upsert_article()` receives an article:

1. Continue writing `authors_json`.
2. Write or refresh article-level extraction metadata.
3. If authors are present:
   - upsert each normalized author into `t_news_authors`
   - upsert each relation into `t_news_article_authors`
4. If authors are absent:
   - do not create any author row
   - preserve the article-level missing status for coverage aggregation

Duplicate article behavior:

- If stored `authors_json` is empty and the new fetch has authors, refresh
  `authors_json`, extraction metadata, author entities, and relations.
- If stored `author_extraction_status` is a weaker state such as
  `no_detail_fetched` and a later detail parser produces `present`, upgrade the
  article state.
- Do not downgrade `present` to a missing status unless manual correction or a
  verified parser fix requires it.

## Backfill Plan

Phase 1: relation backfill from existing `authors_json`

- Select articles where `JSON_LENGTH(authors_json) > 0`.
- Normalize each existing name using current author normalizer.
- Upsert `t_news_authors`.
- Upsert `t_news_article_authors`.
- Set `author_extraction_status=present` where NULL.
- Set `author_extraction_method` to `legacy_authors_json` or the best available
  method if raw metadata indicates it.

Phase 2: missing-state backfill for existing rows

- Select articles where `authors_json` is NULL or empty.
- If `raw_json.author_values` exists but normalization failed, mark
  `low_confidence`.
- If the source currently has no detail parser, mark `parser_not_supported` or
  `no_detail_fetched` depending on whether detail parsing is in scope.
- Avoid claiming `no_author_metadata` until a source-specific parser or verified
  upstream metadata check confirms that no byline is available.

Phase 3: source-specific detail parser expansion

Prioritize sources with high article volume and low author coverage:

1. `ltn`
2. `tvbs`
3. `ettoday`
4. `ebc`
5. `pts`
6. `ctee`

Each parser should have fixture tests before being enabled in loop mode.

## Coverage Queries

Source/category daily coverage:

```sql
SELECT
  DATE(CONVERT_TZ(published_at, '+00:00', '+08:00')) AS stat_date,
  source_id,
  category,
  COUNT(*) AS article_count,
  SUM(CASE WHEN author_extraction_status = 'present' THEN 1 ELSE 0 END) AS with_author_count,
  SUM(CASE WHEN author_extraction_status <> 'present' OR author_extraction_status IS NULL THEN 1 ELSE 0 END) AS without_author_count
FROM t_news_articles
WHERE published_at >= UTC_TIMESTAMP() - INTERVAL 14 DAY
GROUP BY stat_date, source_id, category
ORDER BY stat_date DESC, source_id, category;
```

Missing-state breakdown:

```sql
SELECT
  source_id,
  category,
  author_extraction_status,
  COUNT(*) AS count
FROM t_news_articles
WHERE published_at >= UTC_TIMESTAMP() - INTERVAL 14 DAY
GROUP BY source_id, category, author_extraction_status
ORDER BY source_id, category, count DESC;
```

Reporter-topic concentration:

```sql
SELECT
  a.source_id,
  au.display_name,
  JSON_UNQUOTE(JSON_EXTRACT(a.topics_json, '$[0].topic_id')) AS primary_topic_id,
  COUNT(*) AS article_count
FROM t_news_article_authors aa
JOIN t_news_authors au ON au.id = aa.author_id
JOIN t_news_articles a ON a.article_id = aa.article_id
WHERE a.published_at >= UTC_TIMESTAMP() - INTERVAL 30 DAY
GROUP BY a.source_id, au.display_name, primary_topic_id
ORDER BY article_count DESC;
```

## API Considerations

The data repo does not own the public API, but this design should support later
API fields:

```json
{
  "article_id": "cna-politics-abc",
  "authors": [
    {
      "id": 123,
      "name": "陳俊華",
      "source_id": "cna",
      "role": "reporter",
      "confidence": 1.0,
      "extraction_method": "rss_metadata"
    }
  ],
  "author_extraction": {
    "status": "present",
    "method": "rss_metadata",
    "confidence": 1.0
  }
}
```

For articles without reporter names:

```json
{
  "article_id": "tvbs-politics-abc",
  "authors": [],
  "author_extraction": {
    "status": "parser_not_supported",
    "method": "none",
    "confidence": null
  }
}
```

## Acceptance Criteria

- New article rows always receive an `author_extraction_status`.
- Articles with non-empty author names create normalized rows in
  `t_news_authors`.
- Articles with non-empty author names create rows in
  `t_news_article_authors`.
- Articles without names do not create fake `unknown` author rows.
- Existing rows with `authors_json` can be backfilled into the new relation
  tables.
- Coverage aggregation can report, per `stat_date + source_id + category`:
  - total article count
  - with-author count
  - without-author count
  - missing-state breakdown
  - coverage rate
- Unit tests cover:
  - author key generation
  - relation upsert idempotency
  - duplicate article author refresh
  - missing status assignment
  - coverage aggregation math

## Suggested Implementation Tasks

1. Add settings for author tables:
   - `NEWSPF_MYSQL_AUTHOR_TABLE=t_news_authors`
   - `NEWSPF_MYSQL_ARTICLE_AUTHOR_TABLE=t_news_article_authors`
   - `NEWSPF_MYSQL_AUTHOR_COVERAGE_DAILY_TABLE=t_news_author_coverage_daily`
2. Extend `NewsArticle` with extraction metadata.
3. Extend parser outputs to include extraction status/method/raw text.
4. Add store DDL and migrations.
5. Add author upsert and article-author relation upsert methods.
6. Update `upsert_article()` to write article metadata and relations.
7. Add backfill script:
   - `scripts/backfill_news_author_relations.py`
8. Add daily coverage script:
   - `scripts/build_news_author_coverage_daily.py`
9. Add focused unit tests.
10. Update README and `memory-bank/PROJECT_DOCUMENTATION.md` after
    implementation changes are complete.

## Open Questions

These are not blockers for the MVP. Use the suggested implementation tasks as
the default path unless the user chooses otherwise.

- Should the first implementation store daily coverage as a materialized table,
  or should `scripts/check_data_source_health.py` compute it live first?
- Should article detail fetching run in the main crawl loop or a separate
  enrichment worker to avoid slowing source polling?
- Should author identity eventually merge same-name reporters across sources, or
  stay source-scoped permanently?
- Should `author_raw_text` live only on `t_news_article_authors.raw_text`, or
  also remain on `t_news_articles` for missing/low-confidence cases?

## Implementation Guidance For Sub-Agents

- Treat this file as the product/data contract for `NEWS-1`.
- Keep `authors_json` backward compatible.
- Prefer additive schema changes and migrations.
- Do not remove or reinterpret existing article IDs.
- Do not write fake author entities for missing names.
- Preserve enough extraction status detail to distinguish source behavior from
  parser limitations.
