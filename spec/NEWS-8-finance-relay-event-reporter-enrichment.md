# NEWS-8 Finance Relay Event Reporter Enrichment

## Status
Done

## Goal
Show reporter names on the public finance news cards when Taiwan finance RSS
items have an identifiable byline on the source article page.

## Context
The finance column is backed by `news_relay.t_relay_events` through
`GET /api/events?region=TW`. It does not read the long-lived
`news_platform.t_news_articles` tables used by society and politics pages, so it
does not currently benefit from `NEWS-1` reporter relations or `NEWS-2` article
detail author backfill.

Most Taiwan finance RSS feeds do not publish `<author>` or `dc:creator`
metadata. Reporter enrichment therefore needs a bounded detail-page pass that
fetches the already-known article URL and extracts only byline metadata. It must
not store article body content.

## MVP Design
- Preserve RSS author metadata in `NewsItem.raw.author_values` when a feed
  exposes it.
- Add `scripts/backfill_relay_event_authors.py` for manual or scheduled repair.
- Candidate scope:
  - Reads recent `t_relay_events` rows ordered newest first.
  - Only processes allowlisted public news domains with known article pages.
  - Skips rows that already have `raw_json.authors` or an
    `raw_json.author_extraction.status`, unless `--retry-failed` is used.
- Extraction:
  - Reuses `news_platform.article_detail_author_extractor.ArticleDetailAuthorExtractor`.
  - Fetches article detail HTML only to read JSON-LD, meta author tags, or
    short visible byline text.
- Storage:
  - Writes reporter names to `raw_json.authors`.
  - Writes metadata to `raw_json.author_extraction` with `status`, `method`,
    `confidence`, `raw_text`, and `extracted_at`.
  - Does not add new columns or normalized relation tables in this MVP.
- Frontend:
  - Finance event cards render `authors[]` if the API later adds it.
  - Until then, cards parse `rawJson.authors` or nested RSS raw author hints.

## Non-Goals
- Do not create finance reporter profile pages yet.
- Do not normalize finance relay reporters into `t_news_authors` yet.
- Do not store article body content.
- Do not scrape unrelated official market-data rows such as TWSE/CBC/FSC
  release pages unless their domain is explicitly supported.

## Verification
- `python -m unittest tests.test_rss_source tests.test_relay_event_author_backfill -v`
- `python -m py_compile scripts/backfill_relay_event_authors.py src/news_collector/sources/rss.py`
- `npm run lint -- src/lib/content-api.ts src/components/news-platform-dashboard.tsx src/components/infinite-news-feed.tsx`
- Dry-run confirmed known site slug values such as `edn` are rejected as low-confidence non-authors.
- Backfilled latest 50 eligible relay-event rows: `present=37`, `low_confidence=13`, `parse_failed=0`, `updated=50`.
- API and frontend proxy smoke checks returned `rawJson.authors` for recent finance rows.
- Home page smoke confirmed rendered HTML contains `記者`, `江明晏`, and `李靚慧`.

## Future Upgrade Path
If finance reporter analytics or reporter pages become required, add a formal
schema migration with a long-lived finance article table or normalized
`t_relay_event_authors` relation. The current `raw_json` path is intentionally
short-retention and display-oriented.
