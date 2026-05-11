# Task Plan Board

Use this file for the current non-trivial task only.
Move completed or stale task logs to `tasks/archive/`.

## Current Task
- Task: Add Taiwan finance RSS feeds to relay-event ingestion.
- Requested by: user
- Start date: 2026-05-11
- Scope: Active `news_collector` RSS feed config, relay-event source mapping docs, service restart, and storage verification.

## Plan
- [x] Confirm finance news storage boundary is `t_relay_events`.
- [x] Verify Taiwan finance RSS feeds are current and parseable.
- [x] Add active Taiwan finance feeds to `.env`.
- [x] Update docs and decision notes.
- [x] Restart bridge and verify rows enter `t_relay_events`.

## Progress Notes
- 2026-05-11: Finance/news source facts belong in `t_relay_events`; `news_platform` stays society/politics only.
- 2026-05-11: Verified live parse for CNA finance, LTN business, and ETtoday finance RSS; bridge topic/date filters accept all three latest items.
- 2026-05-11: Restarted `news_collector.relay_bridge`; latest log shows all three Taiwan finance feeds parsed and stored.

## Verification
- [x] RSS smoke fetch returns Taiwan finance items.
- [x] Bridge restart sees new `.env` and stores/duplicates RSS rows.
- [x] DB query confirms recent Taiwan finance RSS rows in `t_relay_events`.

## Review Summary
- Outcome: complete
- Evidence: `python -m news_collector.main fetch --source rss --limit 1 --title-url-only --pretty --log-level WARNING` returned CNA/LTN/ETtoday finance items; `python -m unittest tests.test_config tests.test_rss_source tests.test_relay_bridge` passed 12 tests; bridge log `source-bridge-20260511-120622.out.log` shows 15 RSS fetched and three Taiwan finance rows stored; DB query confirmed ids `79193`, `79194`, and `79195` in `t_relay_events`.
- Open risks: `OFFICIAL_RSS_FIRST_PER_FEED=true` means each poll only takes the newest item per feed unless changed.
