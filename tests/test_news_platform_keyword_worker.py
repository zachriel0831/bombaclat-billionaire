"""news_platform.keyword_worker 測試 — 用 fake store 與 fake extractor。"""

import unittest

from news_platform.keyword_worker import KeywordWorker
from news_platform.store import StoredArticleHead


class FakeStore:
    def __init__(self, batches: list[list[StoredArticleHead]]) -> None:
        # batches 為一連串「每次 fetch 回傳什麼」；最後一輪通常是 [] 表示已抽完。
        self._batches = list(batches)
        self.updated: dict[int, list] = {}

    def fetch_articles_missing_keywords(self, limit: int = 100):
        if not self._batches:
            return []
        return self._batches.pop(0)

    def update_keywords(self, row_id: int, keywords) -> None:
        self.updated[row_id] = list(keywords)


class FakeExtractor:
    def __init__(self, *, raises_on: set[int] | None = None) -> None:
        self._raises_on = raises_on or set()
        self.calls = 0

    def extract(self, text: str, *, top_k: int = 5):
        self.calls += 1
        if self.calls in self._raises_on:
            raise RuntimeError("boom")
        # 簡單回傳兩個固定 token，不依賴 jieba
        return [("kw1", 0.5), ("kw2", 0.4)]


class KeywordWorkerTests(unittest.TestCase):
    def test_run_once_updates_each_row(self):
        rows = [
            StoredArticleHead(row_id=1, article_id="a", title="新聞一"),
            StoredArticleHead(row_id=2, article_id="b", title="新聞二"),
        ]
        store = FakeStore([rows])
        worker = KeywordWorker(store, FakeExtractor(), batch_size=10)
        result = worker.run_once()
        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.updated, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(set(store.updated.keys()), {1, 2})

    def test_run_once_handles_extractor_failure(self):
        rows = [
            StoredArticleHead(row_id=1, article_id="a", title="新聞一"),
            StoredArticleHead(row_id=2, article_id="b", title="新聞二"),
        ]
        store = FakeStore([rows])
        # 第一次 extract 拋例外，第二次成功
        worker = KeywordWorker(store, FakeExtractor(raises_on={1}), batch_size=10)
        result = worker.run_once()
        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 1)
        self.assertNotIn(1, store.updated)
        self.assertIn(2, store.updated)

    def test_run_until_drained_iterates_until_empty(self):
        batch1 = [StoredArticleHead(row_id=1, article_id="a", title="t1")]
        batch2 = [StoredArticleHead(row_id=2, article_id="b", title="t2")]
        store = FakeStore([batch1, batch2, []])
        worker = KeywordWorker(store, FakeExtractor(), batch_size=10)
        result = worker.run_until_drained()
        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.updated, 2)
        self.assertEqual(result.failed, 0)


if __name__ == "__main__":
    unittest.main()
