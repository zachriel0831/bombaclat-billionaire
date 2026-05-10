"""news_platform.models 單元測試。"""

import unittest
from datetime import datetime, timezone

from news_platform.models import NewsArticle


class NewsArticleTests(unittest.TestCase):
    def test_to_dict_serialises_published_at(self):
        article = NewsArticle(
            article_id="abc123",
            source_id="ltn",
            country="TW",
            category="society",
            title="某事件",
            url="https://example.com/a",
            published_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            summary="摘要",
            tags=["社會"],
            raw={"feed": "x"},
        )
        data = article.to_dict()
        self.assertEqual(data["article_id"], "abc123")
        self.assertEqual(data["country"], "TW")
        self.assertEqual(data["category"], "society")
        self.assertEqual(data["published_at"], "2026-05-08T12:00:00+00:00")
        self.assertEqual(data["tags"], ["社會"])

    def test_to_dict_handles_none_published(self):
        article = NewsArticle(
            article_id="x",
            source_id="tvbs",
            country="TW",
            category="society",
            title="t",
            url="https://example.com/x",
            published_at=None,
            summary=None,
        )
        data = article.to_dict()
        self.assertIsNone(data["published_at"])
        self.assertEqual(data["tags"], [])
        self.assertEqual(data["raw"], {})


if __name__ == "__main__":
    unittest.main()
