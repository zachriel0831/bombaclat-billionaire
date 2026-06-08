from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from event_relay.palestine_news import (
    PalestineNewsFeed,
    collect_palestine_news,
    is_palestine_issue_item,
    is_probably_english,
    news_item_to_palestine_news_item,
)
from news_collector.models import NewsItem


def _item(title: str, summary: str = "", source: str = "Test Feed") -> NewsItem:
    return NewsItem(
        id="test-id",
        source=source,
        title=title,
        url="https://example.com/article",
        published_at=datetime(2026, 6, 4, 8, 0, tzinfo=timezone.utc),
        summary=summary,
        tags=[],
        raw={"feed": "https://example.com/rss"},
    )


class _FakeRssSource:
    items: list[NewsItem] = []

    def __init__(self, *_args, **_kwargs) -> None:
        return None

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        return self.items[:limit]


class PalestineNewsTest(unittest.TestCase):
    def test_english_filter_rejects_cjk_text(self) -> None:
        self.assertTrue(is_probably_english("Gaza ceasefire talks continue"))
        self.assertFalse(is_probably_english("加薩停火談判持續"))

    def test_topic_filter_keeps_palestine_issue_news_only(self) -> None:
        self.assertTrue(is_palestine_issue_item(_item("Gaza ceasefire talks continue")))
        self.assertFalse(is_palestine_issue_item(_item("Markets rise as yields ease")))
        self.assertFalse(is_palestine_issue_item(_item("加薩停火談判持續")))

    def test_news_item_to_palestine_news_item_uses_long_term_shape(self) -> None:
        item = news_item_to_palestine_news_item(
            _item("Gaza hospitals face renewed pressure", "<p>Palestinian officials reported shortages.</p>"),
            PalestineNewsFeed("google_news_en", "https://news.google.com/rss"),
        )

        self.assertTrue(item.news_id.startswith("palestine-watch-"))
        self.assertEqual(item.source_id, "google_news_en")
        self.assertEqual(item.api_source, "palestine_watch:google_news_en")
        self.assertEqual(item.summary, "Palestinian officials reported shortages.")
        self.assertEqual(item.topic, "free_palestine")
        self.assertEqual(item.language, "en")
        self.assertEqual(item.raw["collector"], "palestine_news")

    def test_collect_palestine_news_filters_and_dedupes(self) -> None:
        _FakeRssSource.items = [
            _item("Gaza hospitals face renewed pressure"),
            _item("Gaza hospitals face renewed pressure"),
            _item("Markets rise as yields ease"),
            _item("Failed to fetch RSS", source="official_rss:error"),
        ]

        with patch("event_relay.palestine_news.OfficialRssSource", _FakeRssSource):
            collection = collect_palestine_news(
                feeds=[PalestineNewsFeed("google_news_en", "https://news.google.com/rss")],
                limit_per_feed=10,
            )

        self.assertEqual(len(collection.items), 1)
        self.assertEqual(collection.fetched_count, 4)
        self.assertEqual(collection.skipped_count, 1)
        self.assertEqual(collection.error_count, 1)


if __name__ == "__main__":
    unittest.main()
