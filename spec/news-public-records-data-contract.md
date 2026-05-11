# News Public Records Data Contract

## Purpose
`t_news_articles` stores news-like articles and official press releases. Structured official datasets are stored separately in `t_public_records` and linked to related articles through `t_news_article_public_record_links`.

This keeps article feeds simple while allowing fact-backed article pages, timeline joins, and later source-specific ingestion for Legislative Yuan, judicial, police, fraud, traffic, housing, population, and health datasets.

## Tables

### `t_public_records`
One row per official structured fact or record.

Key fields:
- `record_id`: stable dedupe key, source-prefixed, e.g. `ly:bill:<id>` or `npa165:blocked_site:<hash>`.
- `source_id`: official source family, e.g. `ly`, `judicial`, `npa_165`, `motc_accident`, `moi_population`, `moi_real_price`, `nhi`.
- `record_type`: domain type, e.g. `legislative_bill`, `court_judgment`, `fraud_site`, `traffic_accident`, `population_indicator`, `housing_transaction`.
- `category`: optional article category affinity such as `politics` or `society`.
- `occurred_at`: official event/record timestamp normalized to UTC when source time is available.
- `region`: normalized place label when available.
- `metrics_json`: structured comparable numbers.
- `tags_json`: source tags or normalized labels.
- `raw_json`: source payload for traceability.

### `t_news_article_public_record_links`
Many-to-many relation between articles and records.

Key fields:
- `article_id`: `t_news_articles.article_id`.
- `public_record_id`: `t_public_records.record_id`.
- `relation_type`: `mentions`, `supports`, `same_event`, `context`, or `manual`.
- `confidence`: 0.0 to 1.0.
- `matched_by`: matching method, e.g. `manual`, `url`, `title_keyword`, `entity_date_region`.
- `evidence_json`: match terms, shared entities, URLs, dates, or operator notes.

## Rules
- Do not store structured official rows as articles unless the source item is itself a readable article or press release.
- Preserve source timestamps and raw payloads.
- Use stable source-prefixed `record_id` values for dedupe.
- Link records to articles through the link table instead of embedding record IDs into `raw_json`.

## Current Sources

### Legislative Yuan legal proposals
- CLI source name: `ly_bills`
- API docs: `https://www.ly.gov.tw/Pages/List.aspx?nodeid=153`
- API endpoint: `https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx`
- Required upstream params: `from`, `to`, and `mode=json`
- Upstream date format: ROC calendar `YYYMMDD`, e.g. `1150511` for `2026-05-11`
- Storage mapping:
  - `source_id=ly`
  - `record_type=legislative_bill`
  - `category=politics`
  - `title=billName`
  - `occurred_at=date` normalized as Asia/Taipei midnight
  - `metrics_json.term/session_period/session_times/cosignatory_count`
  - `raw_json` keeps upstream date, term/session, proposer, cosignatory, status, API params, and API doc URL
