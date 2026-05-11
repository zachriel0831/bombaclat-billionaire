# 2026-05-11 - Public records linked to news articles

## Decision
Store structured official society/politics data in `t_public_records` and relate it to `t_news_articles` through `t_news_article_public_record_links`.

## Rationale
Official datasets such as Legislative Yuan bills, court judgments, 165 fraud lists, traffic accidents, population indicators, housing data, and health indicators are not articles. Mixing them into `t_news_articles` would weaken article queries, topic fallback behavior, and feed semantics.

A normalized public-record table plus a many-to-many link table lets one official record support many articles and one article cite many official facts. Link rows keep `relation_type`, `confidence`, `matched_by`, and `evidence_json` so downstream API/frontend work can show why a record is related.

## Storage Contract
- `t_public_records.record_id` is the stable dedupe key.
- `t_public_records.metrics_json` stores comparable numeric fields.
- `t_public_records.raw_json` preserves the original source payload.
- `t_news_article_public_record_links.article_id` references `t_news_articles.article_id` by contract.
- `t_news_article_public_record_links.public_record_id` references `t_public_records.record_id` by contract.

## Impact
- Adds `PublicRecord` model.
- Adds configurable table names:
  - `NEWSPF_MYSQL_PUBLIC_RECORD_TABLE`
  - `NEWSPF_MYSQL_ARTICLE_RECORD_LINK_TABLE`
- Adds store APIs for public-record upsert, article-record linking, and joined article link fetches.
- No source-specific official data adapter is added in this decision.
