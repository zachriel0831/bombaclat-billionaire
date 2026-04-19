import unittest
from datetime import date
from datetime import datetime, timezone
from unittest.mock import patch

from news_collector.config import Settings
from news_collector.models import NewsItem
from news_collector.relay_bridge import BridgeConfig, _build_us_index_event, _run_x_backfill
from news_collector.us_index_tracker import IndexQuote


class RelayBridgeBackfillTests(unittest.TestCase):
    def _settings(self, **overrides) -> Settings:
        base = dict(
            x_enabled=True,
            x_bearer_token="token",
            x_bearer_token_file=".secrets/x.dpapi",
            x_accounts=["https://x.com/elonmusk", "https://x.com/realdonaldtrump"],
            x_max_results_per_account=5,
            x_stop_on_429=True,
            x_auto_heal_too_many_connections=True,
            x_heal_cooldown_seconds=45,
            x_include_replies=False,
            x_include_retweets=False,
            x_backfill_enabled=True,
            x_backfill_max_results_per_account=10,
            official_rss_feeds=["https://example.com/rss.xml"],
            official_rss_first_per_feed=False,
            http_timeout_seconds=15,
        )
        base.update(overrides)
        return Settings(**base)

    def test_run_x_backfill_posts_recent_items(self) -> None:
        settings = self._settings()
        items = [
            NewsItem(
                id="x-1",
                source="x:elonmusk",
                title="recent one",
                url="https://x.com/elonmusk/status/1",
                published_at=datetime(2026, 4, 19, 7, 0, tzinfo=timezone.utc),
                summary="recent one",
                tags=["account:elonmusk"],
                raw={"tweet": {"id": "1"}},
            ),
            NewsItem(
                id="x-2",
                source="x:realdonaldtrump",
                title="recent two",
                url="https://x.com/realdonaldtrump/status/2",
                published_at=datetime(2026, 4, 19, 8, 0, tzinfo=timezone.utc),
                summary="recent two",
                tags=["account:realdonaldtrump"],
                raw={"tweet": {"id": "2"}},
            ),
        ]

        with patch("news_collector.relay_bridge.XAccountSource.fetch", return_value=items) as fetch_mock:
            with patch("news_collector.relay_bridge._post_event", return_value=True) as post_mock:
                result = _run_x_backfill("http://127.0.0.1:18090/events", settings, "token")

        fetch_mock.assert_called_once_with(limit=10)
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["pushed"], 2)
        self.assertEqual(result["dropped_by_date"], 0)
        self.assertEqual(result["dropped_by_topic"], 0)

    def test_run_x_backfill_skips_when_disabled(self) -> None:
        settings = self._settings(x_backfill_enabled=False)

        with patch("news_collector.relay_bridge.XAccountSource.fetch") as fetch_mock:
            result = _run_x_backfill("http://127.0.0.1:18090/events", settings, "token")

        fetch_mock.assert_not_called()
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["pushed"], 0)

    def test_build_us_index_event_uses_events_schema(self) -> None:
        quotes = {
            "DJIA": IndexQuote(
                symbol="DJIA",
                label="DJIA",
                url="https://finance.yahoo.com/quote/%5EDJI",
                trade_date=date(2026, 4, 19),
                regular_start_epoch=1,
                regular_end_epoch=2,
                open_price=40000.0,
                last_price=40123.45,
            ),
            "S&P 500": IndexQuote(
                symbol="S&P 500",
                label="S&P 500",
                url="https://finance.yahoo.com/quote/%5EGSPC",
                trade_date=date(2026, 4, 19),
                regular_start_epoch=1,
                regular_end_epoch=2,
                open_price=5000.0,
                last_price=5022.75,
            ),
        }

        payload = _build_us_index_event("close", "2026-04-19", "[US_INDEX_CLOSE]\nDJIA: 40123.45", quotes)

        self.assertEqual(payload["id"], "us_index_close_2026-04-19")
        self.assertEqual(payload["source"], "us_index_tracker")
        self.assertEqual(payload["title"], "US index close 2026-04-19")
        self.assertEqual(payload["url"], "https://finance.yahoo.com/quote/%5EDJI")
        self.assertIn("DJIA: 40123.45", payload["summary"])
        self.assertEqual(payload["market_snapshot"]["session"], "close")
        self.assertEqual(len(payload["market_snapshot"]["indexes"]), 2)


if __name__ == "__main__":
    unittest.main()
