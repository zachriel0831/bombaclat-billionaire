# Archived Task: News Platform Public Record Matching

- Task: Add article-to-public-record matching for news-platform.
- Requested by: user
- Start date: 2026-05-12
- Outcome: complete
- Evidence: `.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_news_platform_*.py"` passed 100 tests; `.venv\\Scripts\\python.exe -m compileall -q src/news_platform ...` passed; `python -m news_platform.main --link-public-records --public-record-link-batch-size 500 --public-record-link-lookback-days 45` produced `matched=3 linked=3 failed=0`; DB confirmed `ly_bill_rule_total=3 today=3`; loop log showed public-record link pass running.

