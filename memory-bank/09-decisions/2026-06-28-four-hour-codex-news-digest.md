# 2026-06-28 Four-Hour Codex News Digest

## Decision

Create a Codex-owned four-hour cross-section news digest that reads existing
platform facts and publishes only the latest generated digest to Redis.

## Rationale

- The user wants a near-current summary without paying extra OpenAI API quota.
- `data-collecting` already owns source context, but public API rendering belongs
  to `news-platform-api`.
- The digest is short-lived product state, not an audited market-analysis row;
  Redis with a 4h10m TTL matches the intended freshness window.

## Boundaries

- `data-collecting` collects compact context and provides the Redis write helper.
- Codex automation generates the prose from that context.
- `news-platform-api` exposes `GET /api/digest/four-hour` by reading Redis.
- No LINE push is created here.
- No rows are written to `t_market_analyses`.
- Free Palestine source news remains in long-term `t_palestine_news_items`.

## Replacement Rule

The writer stores a versioned digest key first, then replaces
`news:digest:four-hour:latest`, then deletes the previous version key. If the new
write fails, the previous latest value remains available until its TTL expires.
