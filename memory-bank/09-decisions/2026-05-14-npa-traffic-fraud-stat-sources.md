# 2026-05-14 NPA Traffic And Fraud Statistic Sources

## Decision
Add NPA official traffic/fraud statistic datasets to the default public-record source set:

- `npa_traffic_a2_stats`: A2 traffic accident monthly region statistics from `https://data.gov.tw/dataset/57024`
- `npa_drunk_driving_stats`: annual drunk-driving accident statistics from `https://data.gov.tw/dataset/9018`
- `npa_fraud_blocked_domain_stats`: blocked fraud-domain monthly statistics from `https://data.gov.tw/en/datasets/176455`
- `npa_fraud_enforcement_stats`: monthly fraud enforcement dashboard from `https://data.gov.tw/dataset/172159`

## Rationale
News analysis needs official context for traffic accidents and fraud beyond article text. These sources provide aggregate counts, casualty numbers, blocked domains, enforcement groups, suspects, seized proceeds, and blocked amounts.

## Boundaries
- Store these rows in `t_public_records`, not `t_news_articles`.
- Use `source_id=npa`, `category=society`, and source-specific `record_type` values.
- Aggregate raw rows into stable monthly/yearly records with metric fields and raw source evidence.
- Do not auto-link statistic records to articles until a higher-precision stat-context matcher is added. Existing article-record linking remains focused on LY bills and NPA 165 fraud rumors.
- The drunk-driving official dataset is low-frequency and currently lags recent news; treat it as historical context unless the upstream file updates.

## Verification
- 2026-05-14 unit tests: `python -m unittest tests.test_news_platform_npa_public_records tests.test_news_platform_main tests.test_news_platform_public_records tests.test_news_platform_public_record_matcher -v`
- 2026-05-14 smoke fetch returned 4/4 new sources with samples up to 2026-04 for A2 traffic, fraud blocked domains, and fraud enforcement.
- 2026-05-14 live collection stored 158 records across the four new source types.
