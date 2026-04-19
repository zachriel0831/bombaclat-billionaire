# RSS Feed Set Decision

- Date: 2026-04-19
- Scope: active `.env` RSS source mapping for relay ingestion

## Decision
- Removed CNN feeds from the active `OFFICIAL_RSS_FEEDS` set.
- Kept BBC, Fox/Fox Business, and NPR feeds.
- Kept Reuters coverage via Google News RSS search queries targeted at Reuters pages.

## Why
- The tested CNN feeds returned stale top items dated between 2016 and 2024, so relay date filtering would drop them and no fresh events would reach `t_relay_events`.
- Legacy Reuters feed hostnames were not reachable from this environment, while Google News RSS queries for Reuters returned current items.

## Verification Basis
- Runtime RSS fetch on 2026-04-19 showed recent items for BBC, Reuters-via-Google, Fox, and NPR.
- Runtime RSS fetch on 2026-04-19 showed stale items for the tested CNN feeds.
