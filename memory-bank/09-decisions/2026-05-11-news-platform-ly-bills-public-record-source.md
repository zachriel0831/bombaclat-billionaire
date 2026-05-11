# 2026-05-11 - Legislative Yuan bills as public records

## Decision
Connect the Legislative Yuan legal proposal API as the first official public-record source for the Taiwan society/politics news platform.

## Source
- API docs: `https://www.ly.gov.tw/Pages/List.aspx?nodeid=153`
- API endpoint: `https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx`
- CLI source name: `ly_bills`

## Mapping
- `source_id=ly`
- `record_type=legislative_bill`
- `category=politics`
- `title=billName`
- `occurred_at=date`, converted from upstream ROC date to Asia/Taipei midnight
- `metrics_json`: `term`, `session_period`, `session_times`, `cosignatory_count`
- `raw_json`: API URL/doc URL, request params, upstream fields, parsed proposers, parsed cosignatories

## Rationale
Legislative proposal rows are structured official facts, not news articles. They support politics articles as evidence/context and therefore belong in `t_public_records`; article linking remains through `t_news_article_public_record_links`.

## Operational Notes
- Run a no-write check with `python -m news_platform.main --public-records-smoke --public-sources ly_bills`.
- Run ingestion with `python -m news_platform.main --collect-public-records --public-sources ly_bills`.
- Date arguments use Western dates on the CLI (`YYYY-MM-DD`) and are converted to ROC `YYYMMDD` for the upstream API.
- On this Windows/OpenSSL environment the endpoint certificate can fail with Missing Subject Key Identifier, so the adapter uses a source-scoped SSL verification bypass for this public read-only official API.
