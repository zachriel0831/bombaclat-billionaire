"""news_platform.topic_llm_worker tests."""

import unittest

from news_platform.store import StoredArticleLlmTopicInput
from news_platform.topic_llm import TopicLlmResult
from news_platform.topic_llm_worker import TopicLlmFallbackWorker


class FakeStore:
    def __init__(self, batches: list[list[StoredArticleLlmTopicInput]]) -> None:
        self._batches = list(batches)
        self.updated: dict[int, list[dict[str, object]]] = {}
        self.classified_by: dict[int, str] = {}

    def fetch_articles_empty_topics(self, limit: int = 50):
        if not self._batches:
            return []
        return self._batches.pop(0)

    def update_article_topics(self, row_id: int, topics, *, classified_by: str = "rule") -> None:
        self.updated[row_id] = list(topics)
        self.classified_by[row_id] = classified_by


class FakeClassifier:
    def __init__(self, *, raises: bool = False, topics=None) -> None:
        self.raises = raises
        self.topics = topics if topics is not None else [{"topic_id": "fraud", "source": "llm"}]
        self.calls = 0

    def classify(self, *, title: str, summary: str | None):
        self.calls += 1
        if self.raises:
            raise RuntimeError("boom")
        return TopicLlmResult(
            topics=list(self.topics),
            provider="openai",
            model="gpt-5-nano",
            raw_topic_id="fraud",
            confidence=0.8,
            reason="matched",
        )


class TopicLlmFallbackWorkerTests(unittest.TestCase):
    def test_run_once_writes_general_social_when_llm_has_no_match(self):
        rows = [StoredArticleLlmTopicInput(row_id=1, article_id="a", title="後續", summary="證據不足")]
        store = FakeStore([rows])
        worker = TopicLlmFallbackWorker(store, FakeClassifier(topics=[]), batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(store.updated[1][0]["topic_id"], "general_social_news")
        self.assertEqual(store.updated[1][0]["label"], "一般社會新聞")
        self.assertEqual(store.updated[1][0]["source"], "llm_fallback")
        self.assertEqual(store.updated[1][0]["provider"], "openai")
        self.assertEqual(store.classified_by[1], "llm")

    def test_run_once_counts_classifier_failure(self):
        rows = [StoredArticleLlmTopicInput(row_id=1, article_id="a", title="後續", summary=None)]
        store = FakeStore([rows])
        worker = TopicLlmFallbackWorker(store, FakeClassifier(raises=True), batch_size=10)

        result = worker.run_once()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.failed, 1)


if __name__ == "__main__":
    unittest.main()
