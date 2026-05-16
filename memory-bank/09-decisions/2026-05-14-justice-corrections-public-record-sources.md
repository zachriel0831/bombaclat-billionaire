# Decision: Justice and Corrections Public-Record Sources

## Date
2026-05-14

## Context
News analysis needs official background data for judicial workload, case congestion, and corrections over-capacity discussions.

## Decision
Add two Taiwan official public-record sources to `news_platform`:

- `moj_prosecution_disposition_stats`
  - Official page: `https://data.gov.tw/dataset/39402`
  - Download: `https://www.rjsd.moj.gov.tw/rjsdweb/OpenData.ashx?code=CA0063`
  - Stored as `source_id=moj`, `record_type=moj_prosecution_disposition_stat`
  - Aggregates monthly prosecution-disposition people counts by ROC year/month.

- `mojac_daily_custody`
  - Official page: `https://data.gov.tw/dataset/101185`
  - Download: `https://prisonmuseum.moj.gov.tw/jqw_pub/today.xml`
  - Stored as `source_id=mojac`, `record_type=mojac_daily_custody_stat`
  - Stores daily actual custody, approved capacity, over-capacity rate, intake, and release counts.

Both sources are tagged with `judicial_burden` and `judicial_injustice` so they can support judicial-topic pages without implying a direct article citation.

## Operational Notes
- Use `--public-sources justice` to smoke or collect both sources.
- The MOJ prosecution source is monthly and currently has records through the latest upstream month.
- The Agency of Corrections source exposes the current daily row only; repeated daily collection builds local history.
- These statistic rows are background context and should not be auto-linked to articles until a precise matcher is added.
