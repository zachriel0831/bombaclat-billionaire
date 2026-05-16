# News Public Records Data Contract

## Purpose
`t_news_articles` stores news-like articles and official press releases. Structured official datasets are stored separately in `t_public_records` and linked to related articles through `t_news_article_public_record_links`.

This keeps article feeds simple while allowing fact-backed article pages, timeline joins, and later source-specific ingestion for Legislative Yuan, judicial, police, fraud, traffic, housing, population, and health datasets.

## Tables

### `t_public_records`
One row per official structured fact or record.

Key fields:
- `record_id`: stable dedupe key, source-prefixed, e.g. `ly:legislative_bill:<hash>` or `npa:fraud_rumor:<hash>`.
- `source_id`: official source family, e.g. `ly`, `npa`, `judicial`, `moi_population`, `moi_real_price`, `nhi`.
- `record_type`: domain type, e.g. `legislative_bill`, `fraud_rumor`, `traffic_accident_a1`, `court_judgment`, `population_indicator`, `housing_transaction`.
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
- `matched_by`: matching method, e.g. `manual`, `url`, `title_keyword`, `entity_date_region`, `ly_bill_rule`, `npa_fraud_rumor_rule`.
- `evidence_json`: match terms, shared entities, URLs, dates, or operator notes.

## Rules
- Do not store structured official rows as articles unless the source item is itself a readable article or press release.
- Preserve source timestamps and raw payloads.
- Use stable source-prefixed `record_id` values for dedupe.
- Link records to articles through the link table instead of embedding record IDs into `raw_json`.
- Deterministic linkers should prefer precision over recall; when evidence is weak, leave the article unlinked rather than creating a noisy relation.

## Current Matching

### Legislative Yuan legal proposals
- CLI: `python -m news_platform.main --link-public-records`
- Worker: `news_platform.public_record_matcher.PublicRecordLinkWorker`
- Method: `matched_by=ly_bill_rule`
- Evidence fields:
  - `record_title`
  - `article_title`
  - `matched_title`
  - `matched_laws`
  - `matched_title_terms`
  - `matched_people`
  - `days_between`
- Current confidence signals:
  - full bill title mention
  - law name mention, with higher weight for long/specific law names
  - proposer/cosignatory name mention
  - article date close to official record date

### NPA 165 fraud-rumor records
- CLI: `python -m news_platform.main --link-public-records`
- Worker: `news_platform.public_record_matcher.PublicRecordLinkWorker`
- Method: `matched_by=npa_fraud_rumor_rule`
- Evidence fields:
  - `record_title`
  - `article_title`
  - `matched_title`
  - `matched_terms`
  - `fraud_context`
  - `days_between`
  - `dataset_url`
- Current confidence signals:
  - full official title mention
  - fraud-context article text plus specific title-term overlap
  - article date close to official record date
- NPA A1 traffic records are ingested but not auto-linked yet; location/date matching needs higher precision to avoid noisy same-region links.

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

### NPA 165 fraud-rumor open data
- CLI source name: `npa_fraud_rumors`
- Data.gov page: `https://data.gov.tw/dataset/38262`
- Storage mapping:
  - `source_id=npa`
  - `record_type=fraud_rumor`
  - `category=society`
  - `title=標題`
  - `occurred_at=發佈時間` normalized as Asia/Taipei
  - `metrics_json.content_length`
  - `raw_json` keeps dataset URL, download URL, serial number, original published text, and content

### NPA A1 traffic accident open data
- CLI source name: `npa_traffic_a1`
- Data.gov page: `https://data.gov.tw/dataset/57023`
- Storage mapping:
  - `source_id=npa`
  - `record_type=traffic_accident_a1`
  - `category=society`
  - party rows are grouped by date/time/location/type into one accident record
  - `title=A1 traffic accident: <location> (<casualties>)`
  - `occurred_at=發生日期 + 發生時間` normalized as Asia/Taipei
  - `region` is parsed from the location county/city prefix when present
  - `metrics_json.death_count/injury_count/party_count/latitude/longitude`
  - `raw_json` keeps dataset URL, download URL, official rows, location, cause, and casualty text
