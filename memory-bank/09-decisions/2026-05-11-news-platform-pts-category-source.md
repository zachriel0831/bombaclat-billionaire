# 2026-05-11 - PTS category pages for society/politics crawler

## Decision
Add PTS/Public Television (`source_id=pts`) to the Taiwan society/politics crawler by using PTS category pages:

- Politics: `https://news.pts.org.tw/category/1`
- Society: `https://news.pts.org.tw/category/7`

## Rationale
PTS provides a general Atom/RSS feed, but it does not expose a stable society/politics category field in each feed entry. Using the general feed for both categories would duplicate articles across `society` and `politics` and would push unrelated general-news rows into category fallback topics.

The category pages expose article URLs, titles, and timestamps directly, so the crawler can preserve the existing `t_news_articles.category` contract without schema changes.

## Impact
- Adds a `pts_category` source adapter.
- Adds `pts` source metadata to `t_news_sources`.
- Adds one PTS feed spec per supported category.
- No DB schema or scheduler change.
