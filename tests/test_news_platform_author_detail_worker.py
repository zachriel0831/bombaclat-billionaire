"""news_platform.author_detail_worker tests."""

from __future__ import annotations

import json
import threading
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from news_platform.article_detail_author_extractor import ArticleDetailAuthorResult
from news_platform.author_detail_worker import ArticleDetailAuthorWorker
from news_platform.author_metadata import AUTHOR_METHOD_ARTICLE_DETAIL, AUTHOR_STATUS_PRESENT


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


class FakeStore:
    def __init__(self, cursors: list[FakeCursor]) -> None:
        self._settings = SimpleNamespace(mysql_article_table="t_news_articles")
        self._conn = FakeConnection()
        self._lock = threading.RLock()
        self._cursors = list(cursors)
        self.relation_calls: list[dict[str, object]] = []

    def _cursor(self):
        if self._cursors:
            return self._cursors.pop(0)
        return FakeCursor()

    def upsert_article_author_relations(self, **kwargs) -> int:
        self.relation_calls.append(kwargs)
        return len(kwargs.get("authors") or [])


class FakeExtractor:
    def extract(self, payload, *, source_id: str = "", url: str = "") -> ArticleDetailAuthorResult:
        return ArticleDetailAuthorResult(
            authors=["王小明"],
            status=AUTHOR_STATUS_PRESENT,
            method=AUTHOR_METHOD_ARTICLE_DETAIL,
            confidence=0.95,
            raw_text="記者王小明／台北報導",
        )


class ArticleDetailAuthorWorkerTests(unittest.TestCase):
    def test_fetch_candidates_uses_bounded_sources_and_loop_statuses(self):
        cursor = FakeCursor()
        store = FakeStore([cursor])
        worker = ArticleDetailAuthorWorker(
            store,
            sources=("tvbs", "ebc"),
            batch_size=7,
            sleep_seconds=0,
        )

        candidates = worker.fetch_candidates()

        self.assertEqual(candidates, [])
        sql, params = cursor.executed[0]
        self.assertIn("source_id IN (%s,%s)", sql)
        self.assertIn("author_extraction_status IS NULL", sql)
        self.assertNotIn("low_confidence", params)
        self.assertEqual(params, ("tvbs", "ebc", "no_detail_fetched", "parser_not_supported", 7))

    def test_run_once_updates_present_authors_and_relations(self):
        published = datetime(2026, 5, 18, 12, 0)
        candidate_cursor = FakeCursor(rows=[(9, "article-9", "tvbs", "https://example.com/a", published)])
        update_cursor = FakeCursor(rowcount=1)
        store = FakeStore([candidate_cursor, update_cursor])
        worker = ArticleDetailAuthorWorker(
            store,
            extractor=FakeExtractor(),
            sources=("tvbs",),
            batch_size=1,
            sleep_seconds=0,
        )

        with patch("news_platform.author_detail_worker.http_get_bytes", return_value=b"<html></html>"):
            result = worker.run_once()

        self.assertEqual(result.candidates, 1)
        self.assertEqual(result.present, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.relations, 1)
        self.assertEqual(store._conn.commits, 1)
        update_sql, update_params = update_cursor.executed[0]
        self.assertIn("SET authors_json=%s", update_sql)
        self.assertEqual(json.loads(update_params[0]), ["王小明"])
        self.assertEqual(update_params[1], AUTHOR_STATUS_PRESENT)
        self.assertEqual(store.relation_calls[0]["article_id"], "article-9")
        self.assertEqual(store.relation_calls[0]["authors"], ["王小明"])


if __name__ == "__main__":
    unittest.main()
