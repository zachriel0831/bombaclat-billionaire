"""news_platform.pipeline 單元測試。"""

import unittest
from datetime import datetime, timezone

from news_platform.models import NewsArticle
from news_platform.pipeline import dedupe, fetch_all, run_once
from news_platform.sources.base import NewsSource


def _make(article_id: str, source_id: str = "ltn", url: str = "https://example.com/a") -> NewsArticle:
    return NewsArticle(
        article_id=article_id,
        source_id=source_id,
        country="TW",
        category="society",
        title="t",
        url=url,
        published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        summary=None,
    )


class FakeSource(NewsSource):
    def __init__(self, name: str, items: list[NewsArticle], *, raises: bool = False) -> None:
        self.name = name
        self._items = items
        self._raises = raises

    def fetch(self, limit: int = 20) -> list[NewsArticle]:
        if self._raises:
            raise RuntimeError("boom")
        return list(self._items)[:limit]


class FakeStore:
    def __init__(self, *, fail_urls: set[str] | None = None, dup_urls: set[str] | None = None) -> None:
        self.upserts: list[NewsArticle] = []
        self._fail = fail_urls or set()
        self._dup = dup_urls or set()

    def upsert_article(self, article: NewsArticle) -> bool:
        if article.url in self._fail:
            raise RuntimeError("write fail")
        self.upserts.append(article)
        return article.url not in self._dup


class DedupeTests(unittest.TestCase):
    def test_drops_duplicate_article_ids(self):
        a = _make("id1", url="https://e.com/1")
        b = _make("id1", url="https://e.com/2")
        c = _make("id2", url="https://e.com/3")
        result = dedupe([a, b, c])
        self.assertEqual([x.article_id for x in result], ["id1", "id2"])

    def test_skips_blank_keys(self):
        bad = NewsArticle(
            article_id="",
            source_id="ltn",
            country="TW",
            category="society",
            title="t",
            url="",
            published_at=None,
            summary=None,
        )
        result = dedupe([bad, _make("ok")])
        self.assertEqual([x.article_id for x in result], ["ok"])


class FetchAllTests(unittest.TestCase):
    def test_aggregates_and_dedupes_across_sources(self):
        s1 = FakeSource("s1", [_make("id1", url="https://e.com/1"), _make("id2", url="https://e.com/2")])
        s2 = FakeSource("s2", [_make("id2", source_id="ettoday", url="https://e.com/2")])
        result = fetch_all([s1, s2], limit_per_source=10)
        self.assertEqual(sorted(a.article_id for a in result), ["id1", "id2"])

    def test_failing_source_does_not_break_others(self):
        ok = FakeSource("ok", [_make("id1")])
        bad = FakeSource("bad", [], raises=True)
        result = fetch_all([ok, bad], limit_per_source=10)
        self.assertEqual([a.article_id for a in result], ["id1"])

    def test_empty_sources(self):
        self.assertEqual(fetch_all([], limit_per_source=5), [])


class RunOnceTests(unittest.TestCase):
    def test_counts_stored_duplicates_and_failures(self):
        articles = [
            _make("id1", url="https://e.com/1"),
            _make("id2", url="https://e.com/2"),
            _make("id3", url="https://e.com/3"),
        ]
        s = FakeSource("s", articles)
        store = FakeStore(dup_urls={"https://e.com/2"}, fail_urls={"https://e.com/3"})
        result = run_once([s], store, limit_per_source=10)
        self.assertEqual(result.fetched, 3)
        self.assertEqual(result.stored, 1)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.failed, 1)


if __name__ == "__main__":
    unittest.main()
