# Archived Task: Taiwan Finance RSS Relay Events

- Task: Add Taiwan finance RSS feeds to relay-event ingestion.
- Requested by: user
- Start date: 2026-05-11
- Outcome: complete
- Evidence: `python -m news_collector.main fetch --source rss --limit 1 --title-url-only --pretty --log-level WARNING` returned CNA/LTN/ETtoday finance items; `python -m unittest tests.test_config tests.test_rss_source tests.test_relay_bridge` passed 12 tests; bridge log `source-bridge-20260511-120622.out.log` shows 15 RSS fetched and three Taiwan finance rows stored; DB query confirmed ids `79193`, `79194`, and `79195` in `t_relay_events`.

