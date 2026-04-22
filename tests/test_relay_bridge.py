import unittest
from datetime import date
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from news_collector.config import Settings
from news_collector.models import NewsItem
from news_collector.relay_bridge import (
    _allow_event_topic,
    _build_us_index_event,
    _event_to_relay_event,
    _run_x_backfill,
    DirectDbEventSink,
)
from news_collector.us_index_tracker import IndexQuote


class _FakeDirectStore:
    def __init__(self, inserted: bool = True) -> None:
        self.inserted = inserted
        self.events = []

    def enqueue_event_if_new(self, event) -> bool:
        self.events.append(event)
        return self.inserted


class RelayBridgeBackfillTests(unittest.TestCase):
    def _settings(self, **overrides) -> Settings:
        base = dict(
            sec_enabled=False,
            sec_user_agent="news-collector/0.1 local-admin@example.com",
            sec_tracked_tickers=[],
            sec_allowed_forms=["8-K", "10-Q", "10-K", "6-K", "20-F"],
            sec_max_filings_per_company=5,
            twse_mops_enabled=False,
            twse_mops_tracked_codes=[],
            twse_mops_max_items_per_company=5,
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
        recent_base = datetime.now(timezone.utc) - timedelta(hours=2)
        items = [
            NewsItem(
                id="x-1",
                source="x:elonmusk",
                title="recent one",
                url="https://x.com/elonmusk/status/1",
                published_at=recent_base,
                summary="recent one",
                tags=["account:elonmusk"],
                raw={"tweet": {"id": "1"}},
            ),
            NewsItem(
                id="x-2",
                source="x:realdonaldtrump",
                title="recent two",
                url="https://x.com/realdonaldtrump/status/2",
                published_at=recent_base + timedelta(minutes=5),
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

    def test_event_to_relay_event_preserves_raw_payload(self) -> None:
        event = {
            "id": "x-123",
            "source": "x:elonmusk",
            "title": "  New   post  ",
            "url": "https://x.com/elonmusk/status/123",
            "summary": "<p>Hello&nbsp;world</p>",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "raw": {"tweet": {"id": "123", "text": "Hello world"}},
        }

        relay_event = _event_to_relay_event(event)

        self.assertIsNotNone(relay_event)
        assert relay_event is not None
        self.assertEqual(relay_event.event_id, "x-123")
        self.assertEqual(relay_event.source, "x:elonmusk")
        self.assertEqual(relay_event.title, "New post")
        self.assertEqual(relay_event.summary, "Hello world")
        self.assertIs(relay_event.raw, event)

    def test_direct_db_event_sink_writes_store(self) -> None:
        store = _FakeDirectStore(inserted=True)
        sink = DirectDbEventSink(store)  # type: ignore[arg-type]
        event = {
            "id": "rss-1",
            "source": "rss",
            "title": "Market news",
            "url": "https://example.com/market",
            "summary": "Finance update",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

        result = sink.submit(event)

        self.assertTrue(result.accepted)
        self.assertTrue(result.stored)
        self.assertEqual(result.status, "stored")
        self.assertEqual(len(store.events), 1)
        self.assertEqual(store.events[0].event_id, "rss-1")

    def test_direct_db_event_sink_treats_duplicates_as_accepted(self) -> None:
        store = _FakeDirectStore(inserted=False)
        sink = DirectDbEventSink(store)  # type: ignore[arg-type]
        event = {
            "id": "rss-1",
            "source": "rss",
            "title": "Market news",
            "url": "https://example.com/market",
            "summary": "Finance update",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

        result = sink.submit(event)

        self.assertTrue(result.accepted)
        self.assertFalse(result.stored)
        self.assertEqual(result.status, "duplicate")

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

    def test_allow_event_topic_bypasses_sec_allowlist(self) -> None:
        event = {
            "source": "sec:NVDA",
            "title": "NVDA filed 8-K",
            "summary": "NVIDIA filed 8-K on 2026-03-06",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/x-index.htm",
        }

        self.assertTrue(_allow_event_topic(event))

    def test_allow_event_topic_bypasses_twse_allowlist(self) -> None:
        event = {
            "source": "twse_mops:2330",
            "title": "2330 台積電: 董事會通過財報",
            "summary": "符合條款 第31款",
            "url": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L#code=2330",
        }

        self.assertTrue(_allow_event_topic(event))


if __name__ == "__main__":
    unittest.main()
