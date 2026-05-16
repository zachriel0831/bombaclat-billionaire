"""news_platform.store topic SQL tests."""

import json
import threading
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from news_platform.models import NewsArticle
from news_platform.store import NewsPlatformStore


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeConnector:
    IntegrityError = RuntimeError


class FakeCursor:
    def __init__(self, rows=None, rowcount: int = 1) -> None:
        self.rows = rows or []
        self.rowcount = rowcount
        self.executed: list[tuple[str, tuple]] = []
        self.closed = False

    def execute(self, sql: str, params=()) -> None:
        self.executed.append((sql, tuple(params)))

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        if self.rows:
            return self.rows[0]
        return (101,)

    def close(self) -> None:
        self.closed = True


def _store_with_cursor(cursor: FakeCursor):
    store = NewsPlatformStore.__new__(NewsPlatformStore)
    store._conn = FakeConnection()
    store._lock = threading.RLock()
    store._article_table = "t_news_articles"
    store._author_table = "t_news_authors"
    store._article_author_table = "t_news_article_authors"
    store._author_coverage_daily_table = "t_news_author_coverage_daily"
    store._settings = SimpleNamespace(article_ttl_days=30)
    store._connector = FakeConnector
    store._cursor = lambda: cursor
    return store


class NewsPlatformStoreTopicTests(unittest.TestCase):
    def test_upsert_article_writes_authors_json(self):
        cursor = FakeCursor()
        store = _store_with_cursor(cursor)
        article = NewsArticle(
            article_id="article-author",
            source_id="ltn",
            country="TW",
            category="society",
            title="author row",
            url="https://example.com/author-row",
            published_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            summary=None,
            authors=["張文川"],
            tags=["society"],
            raw={"feed": "x"},
        )

        inserted = store.upsert_article(article)

        sql, params = cursor.executed[0]
        self.assertTrue(inserted)
        self.assertIn("authors_json", sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)
        self.assertEqual(json.loads(params[8]), ["張文川"])
        self.assertEqual(params[9], "present")
        self.assertEqual(params[10], "legacy_authors_json")
        self.assertEqual(json.loads(params[14]), ["society"])
        self.assertTrue(
            any("INSERT INTO `t_news_authors`" in executed_sql for executed_sql, _ in cursor.executed)
        )
        self.assertTrue(
            any("INSERT INTO `t_news_article_authors`" in executed_sql for executed_sql, _ in cursor.executed)
        )
        self.assertEqual(store._conn.commits, 1)

    def test_upsert_article_treats_duplicate_author_refresh_as_duplicate(self):
        cursor = FakeCursor(rowcount=2)
        store = _store_with_cursor(cursor)
        article = NewsArticle(
            article_id="article-author",
            source_id="ltn",
            country="TW",
            category="society",
            title="author row",
            url="https://example.com/author-row",
            published_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            summary=None,
            authors=["張文川"],
        )

        inserted = store.upsert_article(article)

        self.assertFalse(inserted)
        self.assertEqual(store._conn.commits, 1)

    def test_fetch_articles_missing_topics_queries_keywords_ready_rows(self):
        cursor = FakeCursor(
            rows=[
                (
                    7,
                    "article-7",
                    "society",
                    "酒駕撞死行人",
                    "法官輕判",
                    '[{"kw":"酒駕","score":1.0}]',
                )
            ]
        )
        store = _store_with_cursor(cursor)

        rows = store.fetch_articles_missing_topics(limit=50)

        sql, params = cursor.executed[0]
        self.assertIn("topics_json IS NULL", sql)
        self.assertIn("keywords_json IS NOT NULL", sql)
        self.assertEqual(params, (50,))
        self.assertEqual(rows[0].row_id, 7)
        self.assertEqual(rows[0].category, "society")
        self.assertEqual(rows[0].summary, "法官輕判")
        self.assertEqual(rows[0].keywords_json, '[{"kw":"酒駕","score":1.0}]')

    def test_update_article_topics_serializes_json(self):
        cursor = FakeCursor()
        store = _store_with_cursor(cursor)
        topics = [{"topic_id": "fraud", "label": "詐騙", "score": 1.3}]

        store.update_article_topics(9, topics)

        sql, params = cursor.executed[0]
        self.assertIn("SET topics_json = %s, topic_classified_by = %s", sql)
        self.assertIn("topic_classified_at = UTC_TIMESTAMP()", sql)
        self.assertEqual(params[1], "rule")
        self.assertEqual(params[2], 9)
        self.assertEqual(json.loads(params[0]), topics)
        self.assertEqual(store._conn.commits, 1)

    def test_fetch_articles_empty_topics_queries_rule_unmatched_rows(self):
        cursor = FakeCursor(rows=[(8, "article-8", "politics", "後續報導", "府院回應")])
        store = _store_with_cursor(cursor)

        rows = store.fetch_articles_empty_topics(limit=25)

        sql, params = cursor.executed[0]
        self.assertIn("JSON_LENGTH(topics_json) = 0", sql)
        self.assertIn("general_social_news", sql)
        self.assertIn("general_politics_news", sql)
        self.assertIn("topic_classified_by IS NULL OR topic_classified_by = 'rule'", sql)
        self.assertEqual(params, (25,))
        self.assertEqual(rows[0].row_id, 8)
        self.assertEqual(rows[0].category, "politics")
        self.assertEqual(rows[0].summary, "府院回應")


if __name__ == "__main__":
    unittest.main()
