# Four Track Source Expansion

- Date: 2026-05-12
- Status: accepted

## Decision
Expand source coverage across four tracks:
- Taiwan society/politics articles: add Newtalk and Storm Media to `news_platform.registry`.
- Taiwan finance/news relay events: add Anue, Economic Daily News, Newtalk finance, Storm finance, and MoneyDJ RSS feeds to `OFFICIAL_RSS_FEEDS`.
- Taiwan official finance/macro relay events: add CBC, TWSE, and FSC RSS feeds to `OFFICIAL_RSS_FEEDS`.
- Taiwan official public records: add NPA 165 fraud-rumor and NPA A1 traffic accident open-data adapters to `t_public_records`.

Finance and official market/news RSS stay on the `news_collector` -> `t_relay_events` path. Taiwan society/politics articles stay on the `news_platform` -> `t_news_articles` path. Structured official datasets stay on `t_public_records` and link back to articles through `t_news_article_public_record_links`.

## Rationale
The four tracks have different storage semantics. RSS news is event context for market analysis, society/politics articles feed the middle-office topic UI, and structured official datasets need normalized public-record rows for many-to-many matching.

UDN society/politics RSS is not enabled because its tested feed publishes `pubDate=Thu, 01 Jan 1970 08:00:00 +0800`, which the recent-article filter correctly treats as stale. Money UDN finance RSS is enabled because its tested dates are current.

Some public official endpoints on this Windows/Python environment fail TLS validation with `Missing Subject Key Identifier`. The fallback is source-scoped and retries only those public read-only endpoints without SSL verification.

## Operations
- Society/politics smoke: `python -m news_platform.main --smoke --categories society,politics`
- RSS smoke: `python -m news_collector.main fetch --source rss --limit 1 --title-url-only --pretty`
- Public-record smoke: `python -m news_platform.main --public-records-smoke --public-sources all --public-record-limit 2`
- Restart `news_collector.relay_bridge` after `.env` RSS changes.
- Restart `news_platform.main --loop` after registry/matcher changes.
