# Task History: NEWS-1 Author Relations

- Task: Write NEWS-1 spec for reporter/author relations and byline coverage tracking.
- Date: 2026-05-15
- Outcome: Done.
- Verification:
  - data-collecting focused tests passed.
  - news-platform-api Maven tests passed with JDK 21.
  - Live API smoke passed on port `8082`.
- Open risk: Rows marked `no_detail_fetched` still need source-specific detail parsers.
