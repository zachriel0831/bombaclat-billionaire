# Archived Task: Legislative Yuan Official Bill API

- Task: Connect Legislative Yuan official bill API into news-platform public records.
- Requested by: user
- Start date: 2026-05-11
- Outcome: complete
- Evidence: `python -m unittest tests.test_news_platform_ly_legislative_bill tests.test_news_platform_main tests.test_news_platform_public_records tests.test_news_platform_config` passed 13 tests; `python -m compileall -q src/news_platform` passed; `--public-records-smoke --public-sources ly_bills --public-record-from 2026-05-01 --public-record-to 2026-05-11 --public-record-limit 5` fetched 5; `--collect-public-records --public-sources ly_bills --public-record-from 2026-05-01 --public-record-to 2026-05-11` fetched/stored 116; DB query confirmed `ly_count=116`.

