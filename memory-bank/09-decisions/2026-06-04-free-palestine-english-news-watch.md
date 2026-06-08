# 2026-06-04 Free Palestine English News Watch

## Decision

Create a dedicated Free Palestine English issue-news collector in
`event_relay.palestine_news` and store accepted rows in the long-term
`t_palestine_news_items` table.

Earlier same-day relay-event storage using `source=palestine_watch:*` is
superseded. Those rows are treated as legacy migration input only.

## Rationale

- The `/timeline` page needs recent English information sources next to the
  curated historical/legal timeline.
- These rows should not enter the general finance/public feed source allowlist.
- These rows should also not be tied to `t_relay_events` retention because the
  Free Palestine issue module is long-lived context, not a short-lived event
  relay stream.
- A dedicated table preserves URL-level dedupe, raw JSON traceability, source
  metadata, and API pagination without mixing product boundaries.

## Contract

- Default feeds are Google News English search, Al Jazeera English, BBC Middle
  East, and Guardian Palestine RSS.
- Accepted rows must match Palestine/Gaza/West Bank issue terms and pass a
  likely-English filter.
- Rows use `source_id=<source_id>`, `topic=free_palestine`, `language=en`, and
  `raw_json.collector=palestine_news`.
- Legacy relay rows with `source=palestine_watch:<source_id>` can be copied
  once with `scripts/run_palestine_news.ps1 -BackfillRelay -BackfillOnly`.
- `news-platform-api` reads `t_palestine_news_items` through
  `GET /api/timeline/news`; API responses still present
  `source=palestine_watch:<source_id>` for frontend compatibility.
- `news-display-frontend` renders the rows in the `/timeline` table news column.

## Verification

- Unit tests: `python -m unittest tests.test_palestine_news -v`
- Dry run: `scripts/run_palestine_news.ps1 -EnvFile .env -Limit 5 -DryRun`
- API smoke: `GET /api/timeline/news?page=1&pageSize=5`
