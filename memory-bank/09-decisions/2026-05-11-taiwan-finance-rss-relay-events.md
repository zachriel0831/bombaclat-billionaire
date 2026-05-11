# Taiwan Finance RSS Feeds Write to Relay Events

- Date: 2026-05-11
- Status: accepted

## Decision
Taiwan finance news is collected through `news_collector` RSS polling and stored in `t_relay_events`.

The first active Taiwan finance RSS feeds are:
- CNA finance: `https://feeds.feedburner.com/rsscna/finance`
- LTN business: `https://news.ltn.com.tw/rss/business.xml`
- ETtoday finance: `https://feeds.feedburner.com/ettoday/finance`

## Rationale
Finance news is source/event evidence for market analysis. It should share the same event window as foreign financial news, X posts, SEC filings, TWSE/MOPS announcements, and market-context facts.

`src/news_platform` remains a separate Taiwan society/politics product database and must not become the storage path for finance news.

## Operational Notes
The active feed list lives in `.env` as `OFFICIAL_RSS_FEEDS`. After editing it, restart `news_collector.relay_bridge`; the running Python process may already have the old env value loaded.

