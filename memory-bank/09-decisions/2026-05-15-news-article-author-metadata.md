# News Article Author Metadata

Date: 2026-05-15

## Decision
Store reporter/author names for news-platform articles in `t_news_articles.authors_json`.

## Rationale
- Reporter-level aggregation needs a stable article-side field instead of parsing `raw_json` later.
- RSS/Atom feeds sometimes expose explicit `author`, `dc:creator`, or Atom `author/name` metadata.
- Some Taiwan feeds only expose reporters in high-confidence bylines such as `記者張文川／台北報導`; these can be extracted at ingest time.
- Google News sitemap usually has publication metadata but no reporter field, so sitemap rows only fill `authors_json` when optional `author` or `creator` metadata is present.

## Consequences
- New article inserts write `authors_json` as a JSON array; unavailable authors are stored as `[]`.
- Duplicate article fetches refresh `authors_json` only when the stored array is empty and the current fetch has author names; duplicate semantics still report as duplicate.
- Rows that are not recrawled still need a separate backfill/update job if old article author metadata is required.
- `raw_json.author_values` keeps the original feed author text when present for debugging.
