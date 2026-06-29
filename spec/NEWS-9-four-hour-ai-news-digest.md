# NEWS-9 Four-Hour AI News Digest

## Status
In Progress

## Goal

Every four hours, generate a concise Traditional Chinese digest explaining what
happened across the platform during the previous four hours, covering:

- Taiwan finance / public market news from `news_relay.t_relay_events`
- Taiwan society news from `news_platform.t_news_articles`
- Taiwan politics news from `news_platform.t_news_articles`
- Celebrity/public-figure updates from `x:*` and `truthsocial:*` relay events
- Free Palestine English issue news from long-term `t_palestine_news_items`

The visible prose is produced by a Codex automation, not by paid OpenAI API
calls from `data-collecting`.

## Non-Goals

- Do not push this digest to LINE.
- Do not store the generated digest in `t_market_analyses`.
- Do not create trade signals, order intents, or broker actions.
- Do not move Free Palestine issue news back into short-retention relay events.
- Do not expose internal labels such as raw table names, `market_context`, or
  model/prompt telemetry in the user-facing digest text.

## Data Flow

1. `scripts/collect_four_hour_digest_context.py` reads compact recent context:
   - Finance/public news: recent relay rows, excluding `market_context:*`,
     X/Truth Social, SEC, MOPS, yfinance, and Palestine legacy rows.
   - Society/politics: recent rows by category from `t_news_articles`.
   - Celebrity: recent `x:*` and `truthsocial:*` relay rows.
   - Free Palestine: recent long-term English issue-news rows.
   - Rows with obvious mojibake markers are skipped before summarization.
2. The Codex scheduled task summarizes the context into plain Traditional
   Chinese, sectioned by product area.
3. `scripts/store_four_hour_digest_to_redis.py` writes the generated JSON to
   Redis: versioned keys expire, while the latest display key persists until a
   newer valid digest replaces it.
4. `news-platform-api` reads only the latest Redis key via:
   - `GET /api/digest/four-hour`

## Redis Contract

Default keys:

- Latest API value: `news:digest:four-hour:latest`
- Current version pointer: `news:digest:four-hour:current-key`
- Versioned digest key prefix: `news:digest:four-hour:`

Replacement behavior:

1. Write the new versioned key with TTL.
2. Write `latest` with the same payload and no TTL.
3. Write `current-key` with the new version key and no TTL.
4. Delete the previous version key only after the new writes succeed.

TTL:

- Versioned digest keys use `15000` seconds, equal to 4 hours and 10 minutes.
- `latest` and `current-key` intentionally do not expire, so the homepage keeps
  showing the last successful digest if one automation run is missed.

## Digest JSON Shape

```json
{
  "summaryId": "four-hour-2026-06-28T12-00-00+08-00",
  "windowStart": "2026-06-28T08:00:00+08:00",
  "windowEnd": "2026-06-28T12:00:00+08:00",
  "generatedAt": "2026-06-28T12:02:00+08:00",
  "ttlSeconds": 15000,
  "sourceCounts": {
    "finance": 12,
    "society": 18,
    "politics": 9,
    "celebrity": 4,
    "free_palestine": 3
  },
  "headline": "過去四小時，台股消息集中在權值股與資金面，社會與政治新聞則以即時突發與政策攻防為主。",
  "sections": [
    {
      "key": "finance",
      "title": "財經",
      "summary": "權值股與產業新聞仍是主要焦點，市場等待下一批總經與企業財報訊號。",
      "items": [
        {
          "title": "台股權值股盤中震盪，市場關注外資與電子族群動向",
          "source": "公開財經新聞來源",
          "publishedAt": "2026-06-28 10:30:00",
          "url": "https://example.com"
        }
      ]
    }
  ],
  "notes": []
}
```

Required top-level fields for Redis storage:

- `windowStart`
- `windowEnd`
- `generatedAt`
- `sections`

## API Contract

`news-platform-api` endpoint:

```http
GET /api/digest/four-hour
```

Healthy response:

```json
{
  "available": true,
  "key": "news:digest:four-hour:latest",
  "digest": {
    "summaryId": "four-hour-2026-06-28T12-00-00+08-00"
  },
  "servedAt": "2026-06-28T04:03:00Z"
}
```

`ttlSeconds` is optional; the API may omit it when the latest key has no Redis
expiry.

Missing/unavailable Redis response:

```json
{
  "available": false,
  "key": "news:digest:four-hour:latest",
  "message": "digest_not_ready",
  "servedAt": "2026-06-28T04:03:00Z"
}
```

The API must not return `503` merely because the digest key is absent or Redis is
temporarily unavailable.

## Codex Automation Prompt Rules

- Automation id: `four-hour-cross-section-news-digest`
- Read `AGENTS.md`, this spec, and the context JSON.
- Do not call paid external LLM APIs.
- Produce concise Traditional Chinese that sounds like a human editor.
- Convert internal table/source labels into plain descriptions.
- Mention data gaps only when a section is empty or query failed.
- Reject or repair mojibake, replacement characters, and repeated question-mark
  blocks before Redis storage.
- Store to Redis only after JSON validates.

## Verification

- `python -m unittest tests.test_four_hour_digest_scripts -v`
- `python -m py_compile scripts/collect_four_hour_digest_context.py scripts/store_four_hour_digest_to_redis.py`
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_four_hour_digest_context.ps1 -EnvFile .env -Hours 4 -OutFile runtime\four-hour-digest\context.json`
- `powershell -ExecutionPolicy Bypass -File .\scripts\store_four_hour_digest_to_redis.ps1 -InputFile <generated-json> -TtlSeconds 15000`
- `GET http://localhost:8081/api/digest/four-hour`
