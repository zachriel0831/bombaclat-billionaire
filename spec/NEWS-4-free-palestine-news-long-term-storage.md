# NEWS-4 Free Palestine Issue News Long-Term Storage

## Status

Done

## Context

The `/timeline` Free Palestine module has two data classes:

- Curated historical/legal timeline events, which are long-lived reference data.
- Current English issue-news sources, which support ongoing verification and follow-up.

The English issue-news rows were first stored as `t_relay_events.source=palestine_watch:*`. That made the feature work quickly, but it tied long-lived issue context to the short-retention relay stream used for finance and market facts.

## Requirement

Normalize Free Palestine English issue news into a dedicated long-term table. It must not depend on `t_relay_events` for normal writes or reads.

## Data Contract

Primary table: `t_palestine_news_items`

Required columns:

- `news_id`
- `source_id`
- `source_name`
- `title`
- `url`
- `url_hash`
- `summary`
- `published_at`
- `language`
- `topic`
- `source_url`
- `original_source`
- `original_id`
- `tags_json`
- `raw_json`
- `first_seen_at`
- `last_seen_at`

Unique identity is `url_hash`. Rows are upserted so repeated RSS observations refresh `last_seen_at` without creating duplicates.

## API Contract

`news-platform-api` keeps `GET /api/timeline/news` stable and returns the existing `PublicEvent` response shape.

Implementation detail:

- Read from `t_palestine_news_items`
- Filter `topic='free_palestine'` and `language='en'`
- Sort by `published_at DESC, first_seen_at DESC, id DESC`
- Present `source=palestine_watch:<source_id>` only as an API compatibility display value

## Migration

Legacy rows in `t_relay_events` where `source LIKE 'palestine_watch:%'` can be copied once:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -BackfillRelay -BackfillOnly
```

The migration must not delete legacy relay rows.

## DoD

- Collector writes new accepted rows to `t_palestine_news_items`
- Legacy backfill path exists and is idempotent
- `GET /api/timeline/news` reads the dedicated table
- README, workflow, memory-bank, API spec, and OpenAPI docs name the dedicated table
- Focused Python and Java tests pass
- Local API smoke returns rows from the dedicated table
