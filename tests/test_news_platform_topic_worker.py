"""news_platform.topic_worker tests."""

import json
import unittest

from news_platform.store import StoredArticleTopicInput
from news_platform.topic_worker import TopicWorker


class FakeStore:
    def __init__(self, batches: list[list[StoredArticleTopicInput]], *, fail_on: set[int] | None = None) -> None:
        self._batches = list(batches)
        self._fail_on = fail_on or set()
        self.updated: dict[int, list[dict[str, object]]] = {}
        self.classified_by: dict[int, str] = {}

    def fetch_articles_missing_topics(self, limit: int = 200):
        if not self._batches:
            return []
        return self._batches.pop(0)

    def update_article_topics(self, row_id: int, topics, *, classified_by: str = "rule") -> None:
        if row_id in self._fail_on:
            raise RuntimeError("write fail")
        self.updated[row_id] = list(topics)
        self.classified_by[row_id] = classified_by


class TopicWorkerTests(unittest.TestCase):
    def test_run_once_updates_each_row(self):
        rows = [
            StoredArticleTopicInput(
                row_id=1,
                article_id="a",
                category="society",
                title="酒駕撞死行人",
                summary=None,
                keywords_json=json.dumps([{"kw": "酒駕", "score": 1.0}], ensure_ascii=False),
            ),
            StoredArticleTopicInput(
                row_id=2,
                article_id="b",
                category="society",
                title="詐騙集團車手落網",
                summary=None,
                keywords_json="[]",
            ),
        ]
        store = FakeStore([rows])
        worker = TopicWorker(store, batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.updated, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(store.updated[1][0]["topic_id"], "drunk_driving_accident")
        self.assertEqual(store.updated[2][0]["topic_id"], "fraud")
        self.assertEqual(store.classified_by[1], "rule")

    def test_run_once_writes_general_social_topic_for_no_match(self):
        rows = [
            StoredArticleTopicInput(
                row_id=1,
                article_id="a",
                category="society",
                title="天氣晴朗活動登場",
                summary=None,
                keywords_json="not json",
            )
        ]
        store = FakeStore([rows])
        worker = TopicWorker(store, batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(store.updated[1][0]["topic_id"], "general_social_news")
        self.assertEqual(store.updated[1][0]["label"], "一般社會新聞")
        self.assertEqual(store.updated[1][0]["source"], "rule_fallback")

    def test_run_once_writes_general_politics_topic_for_politics_no_match(self):
        rows = [
            StoredArticleTopicInput(
                row_id=1,
                article_id="a",
                category="politics",
                title="總統府回應今日行程",
                summary=None,
                keywords_json="[]",
            )
        ]
        store = FakeStore([rows])
        worker = TopicWorker(store, batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(store.updated[1][0]["topic_id"], "general_politics_news")
        self.assertEqual(store.updated[1][0]["label"], "一般政治新聞")

    def test_run_once_passes_category_to_politics_classifier(self):
        rows = [
            StoredArticleTopicInput(
                row_id=1,
                article_id="a",
                category="politics",
                title="總統大選民調出爐 候選人展開競選造勢",
                summary=None,
                keywords_json="[]",
            )
        ]
        store = FakeStore([rows])
        worker = TopicWorker(store, batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(store.updated[1][0]["topic_id"], "elections")

    def test_run_once_counts_store_failure(self):
        rows = [
            StoredArticleTopicInput(
                row_id=1,
                article_id="a",
                category="society",
                title="少子化衝擊幼兒園",
                summary=None,
                keywords_json="[]",
            )
        ]
        store = FakeStore([rows], fail_on={1})
        worker = TopicWorker(store, batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.failed, 1)

    def test_run_until_drained_iterates_until_empty(self):
        batch1 = [
            StoredArticleTopicInput(
                row_id=1,
                article_id="a",
                category="society",
                title="高房價青年買不起房",
                summary=None,
                keywords_json="[]",
            )
        ]
        batch2 = [
            StoredArticleTopicInput(
                row_id=2,
                article_id="b",
                category="society",
                title="醫護過勞急診壅塞",
                summary=None,
                keywords_json="[]",
            )
        ]
        store = FakeStore([batch1, batch2, []])
        worker = TopicWorker(store, batch_size=10)

        result = worker.run_until_drained()

        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.updated, 2)
        self.assertEqual(result.failed, 0)


if __name__ == "__main__":
    unittest.main()
