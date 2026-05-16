"""news_platform public-record storage tests."""

from __future__ import annotations

import json
import threading
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from news_platform.models import PublicRecord
from news_platform.store import NewsPlatformStore


class FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


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

    def close(self) -> None:
        self.closed = True


def _store_with_cursor(cursor: FakeCursor):
    store = NewsPlatformStore.__new__(NewsPlatformStore)
    store._conn = FakeConnection()
    store._lock = threading.RLock()
    store._article_table = "t_news_articles"
    store._public_record_table = "t_public_records"
    store._article_record_link_table = "t_news_article_public_record_links"
    store._cursor = lambda: cursor
    return store


class NewsPlatformPublicRecordTests(unittest.TestCase):
    def test_upsert_public_record_serializes_payloads(self):
        cursor = FakeCursor(rowcount=1)
        store = _store_with_cursor(cursor)
        record = PublicRecord(
            record_id="ly:bill:123",
            source_id="ly",
            record_type="legislative_bill",
            country="TW",
            category="politics",
            title="Test bill",
            url="https://data.ly.gov.tw/",
            occurred_at=datetime(2026, 5, 11, 3, 0, tzinfo=timezone.utc),
            region="TW",
            metrics={"proposal_count": 1},
            tags=["budget"],
            raw={"billNo": "123"},
        )

        inserted = store.upsert_public_record(record)

        sql, params = cursor.executed[0]
        self.assertTrue(inserted)
        self.assertIn("INSERT INTO `t_public_records`", sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)
        self.assertEqual(params[0], "ly:bill:123")
        self.assertEqual(params[7], "2026-05-11 03:00:00")
        self.assertEqual(json.loads(params[9]), {"proposal_count": 1})
        self.assertEqual(json.loads(params[10]), ["budget"])
        self.assertEqual(json.loads(params[11]), {"billNo": "123"})
        self.assertEqual(store._conn.commits, 1)

    def test_link_article_public_record_clamps_confidence(self):
        cursor = FakeCursor(rowcount=1)
        store = _store_with_cursor(cursor)

        inserted = store.link_article_public_record(
            article_id="article-1",
            public_record_id="ly:bill:123",
            relation_type="mentions",
            confidence=1.7,
            matched_by="title_keyword",
            evidence={"terms": ["budget"]},
        )

        sql, params = cursor.executed[0]
        self.assertTrue(inserted)
        self.assertIn("INSERT INTO `t_news_article_public_record_links`", sql)
        self.assertEqual(params[:5], ("article-1", "ly:bill:123", "mentions", 1.0, "title_keyword"))
        self.assertEqual(json.loads(params[5]), {"terms": ["budget"]})
        self.assertEqual(store._conn.commits, 1)

    def test_fetch_public_record_links_for_article_joins_record_table(self):
        cursor = FakeCursor(
            rows=[
                (
                    "article-1",
                    "ly:bill:123",
                    "mentions",
                    Decimal("0.8500"),
                    "title_keyword",
                    "legislative_bill",
                    "ly",
                    "Test bill",
                    "https://data.ly.gov.tw/",
                    datetime(2026, 5, 11, 3, 0),
                    "TW",
                    '{"proposal_count":1}',
                )
            ]
        )
        store = _store_with_cursor(cursor)

        rows = store.fetch_public_record_links_for_article("article-1", limit=20)

        sql, params = cursor.executed[0]
        self.assertIn("JOIN `t_public_records`", sql)
        self.assertIn("WHERE l.article_id = %s", sql)
        self.assertEqual(params, ("article-1", 20))
        self.assertEqual(rows[0].public_record_id, "ly:bill:123")
        self.assertEqual(rows[0].confidence, 0.85)
        self.assertEqual(rows[0].record_type, "legislative_bill")
        self.assertEqual(rows[0].metrics_json, '{"proposal_count":1}')

    def test_fetch_articles_for_public_record_matching_filters_recent_categories(self):
        cursor = FakeCursor(
            rows=[
                (
                    10,
                    "article-1",
                    "politics",
                    "Title",
                    "Summary",
                    datetime(2026, 5, 12, 1, 0),
                    '[{"kw":"法案","score":1}]',
                    '[{"topic_id":"general_politics_news"}]',
                )
            ]
        )
        store = _store_with_cursor(cursor)

        rows = store.fetch_articles_for_public_record_matching(
            limit=25,
            lookback_days=9,
            categories=("politics",),
        )

        sql, params = cursor.executed[0]
        self.assertIn("FROM `t_news_articles`", sql)
        self.assertIn("category IN (%s)", sql)
        self.assertIn("DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)", sql)
        self.assertEqual(params, ("politics", 9, 25))
        self.assertEqual(rows[0].article_id, "article-1")
        self.assertEqual(rows[0].topics_json, '[{"topic_id":"general_politics_news"}]')

    def test_fetch_public_records_for_matching_filters_recent_types(self):
        cursor = FakeCursor(
            rows=[
                (
                    "ly:bill:123",
                    "ly",
                    "legislative_bill",
                    "politics",
                    "大學法部分條文修正草案",
                    "https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx",
                    datetime(2026, 5, 8, 0, 0),
                    "TW",
                    '{"term":11}',
                    '["大學法"]',
                    '{"proposers":["吳思瑤"]}',
                )
            ]
        )
        store = _store_with_cursor(cursor)

        rows = store.fetch_public_records_for_matching(
            limit=10,
            lookback_days=45,
            categories=("politics",),
            record_types=("legislative_bill",),
        )

        sql, params = cursor.executed[0]
        self.assertIn("FROM `t_public_records`", sql)
        self.assertIn("(category IS NULL OR category IN (%s))", sql)
        self.assertIn("record_type IN (%s)", sql)
        self.assertEqual(params, (45, "politics", "legislative_bill", 10))
        self.assertEqual(rows[0].record_id, "ly:bill:123")
        self.assertEqual(rows[0].raw_json, '{"proposers":["吳思瑤"]}')


if __name__ == "__main__":
    unittest.main()
