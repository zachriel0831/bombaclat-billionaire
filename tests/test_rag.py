from __future__ import annotations

import unittest

from event_relay.rag import (
    build_event_text,
    embed_text,
    index_recent_documents,
    retrieve_similar_events,
)
from event_relay.service import (
    AnalysisEmbeddingSource,
    StoredEventEmbedding,
    SummaryEvent,
)


class _CandidateStore:
    """封裝 Candidate Store 相關資料與行為。"""
    def __init__(self, candidates: list[StoredEventEmbedding]) -> None:
        """初始化物件狀態與必要依賴。"""
        self._candidates = candidates

    def fetch_event_embedding_candidates(self, *, embedding_model: str, limit: int) -> list[StoredEventEmbedding]:
        """抓取 fetch event embedding candidates 對應的資料或結果。"""
        return self._candidates[:limit]


def _candidate(row_id: int, title: str, summary: str = "") -> StoredEventEmbedding:
    """執行 candidate 的主要流程。"""
    text = "\n".join(["reuters", title, summary])
    return StoredEventEmbedding(
        event_row_id=row_id,
        event_id=f"event-{row_id}",
        source="reuters",
        title=title,
        url=f"https://example.test/{row_id}",
        summary=summary,
        published_at="2026-04-20T00:00:00+08:00",
        created_at="2026-04-20 00:00:00",
        embedding_model="local-hash-v1",
        embedding_dim=128,
        embedding=embed_text(text),
        text_hash="hash",
    )


class RagRetrievalTests(unittest.TestCase):
    """封裝 Rag Retrieval Tests 相關資料與行為。"""
    def test_retrieve_similar_events_empty_store(self) -> None:
        """測試 test retrieve similar events empty store 的預期行為。"""
        examples = retrieve_similar_events(
            _CandidateStore([]),
            [{"id": 1, "source": "reuters", "title": "Fed cuts rates", "summary": "Treasury yields fall"}],
        )

        self.assertEqual(examples, [])

    def test_retrieve_similar_events_respects_k_limit(self) -> None:
        """測試 test retrieve similar events respects k limit 的預期行為。"""
        candidates = [
            _candidate(10, "Fed cuts rates and semiconductor stocks rise", "Treasury yields fall"),
            _candidate(11, "Fed rate cut supports AI chip demand", "Tech stocks rally"),
            _candidate(12, "Oil prices rise on supply shock", "Energy leads"),
        ]

        examples = retrieve_similar_events(
            _CandidateStore(candidates),
            [{"id": 1, "source": "reuters", "title": "Fed cuts rates", "summary": "Semiconductor stocks rally"}],
            k=2,
            min_similarity=-1.0,
        )

        self.assertEqual(len(examples), 2)

    def test_retrieve_similar_events_respects_similarity_threshold(self) -> None:
        """測試 test retrieve similar events respects similarity threshold 的預期行為。"""
        candidates = [
            _candidate(10, "Oil prices rise on supply shock", "Energy leads"),
        ]

        examples = retrieve_similar_events(
            _CandidateStore(candidates),
            [{"id": 1, "source": "reuters", "title": "Fed cuts rates", "summary": "Semiconductors rally"}],
            k=5,
            min_similarity=0.99,
        )

        self.assertEqual(examples, [])

    def test_retrieve_similar_events_excludes_current_event_ids(self) -> None:
        """測試 test retrieve similar events excludes current event ids 的預期行為。"""
        candidates = [
            _candidate(1, "Fed cuts rates and semiconductor stocks rise", "Treasury yields fall"),
            _candidate(10, "Fed cuts rates and semiconductor stocks rise", "Treasury yields fall"),
        ]

        examples = retrieve_similar_events(
            _CandidateStore(candidates),
            [{"id": 1, "source": "reuters", "title": "Fed cuts rates", "summary": "Semiconductor stocks rally"}],
            k=5,
            min_similarity=-1.0,
        )

        self.assertTrue(all(example.event_row_id != 1 for example in examples))


class _IndexStore:
    """封裝 Index Store 相關資料與行為。"""
    def __init__(self) -> None:
        """初始化物件狀態與必要依賴。"""
        self.event_embeddings = []
        self.analysis_embeddings = []

    def fetch_events_missing_embeddings(self, *, days: int, limit: int, embedding_model: str):
        """抓取 fetch events missing embeddings 對應的資料或結果。"""
        return [
            SummaryEvent(
                row_id=101,
                event_id="evt-101",
                source="reuters",
                title="Fed cuts rates",
                url="https://example.test/fed",
                summary="Treasury yields fall and tech rallies",
                published_at=None,
                created_at="2026-04-20 00:00:00",
                raw_json=None,
            )
        ]

    def upsert_event_embedding(self, **kwargs) -> None:
        """新增或更新 upsert event embedding 對應的資料或結果。"""
        self.event_embeddings.append(kwargs)

    def fetch_analyses_missing_embeddings(self, *, limit: int, embedding_model: str):
        """抓取 fetch analyses missing embeddings 對應的資料或結果。"""
        return [
            AnalysisEmbeddingSource(
                row_id=201,
                analysis_date="2026-04-20",
                analysis_slot="pre_tw_open",
                summary_text="Fed rate cut supports Taiwan semiconductors.",
                raw_json=None,
                updated_at="2026-04-20 08:00:00",
            )
        ]

    def upsert_analysis_embedding(self, **kwargs) -> None:
        """新增或更新 upsert analysis embedding 對應的資料或結果。"""
        self.analysis_embeddings.append(kwargs)


class RagIndexTests(unittest.TestCase):
    """封裝 Rag Index Tests 相關資料與行為。"""
    def test_index_recent_documents_indexes_events_and_analyses(self) -> None:
        """測試 test index recent documents indexes events and analyses 的預期行為。"""
        store = _IndexStore()

        result = index_recent_documents(store, days=30, event_limit=10, analysis_limit=10)

        self.assertEqual(result["events_indexed"], 1)
        self.assertEqual(result["analyses_indexed"], 1)
        self.assertEqual(len(store.event_embeddings[0]["embedding"]), 128)
        self.assertEqual(len(store.analysis_embeddings[0]["embedding"]), 128)

    def test_build_event_text_uses_annotation_and_impact(self) -> None:
        """測試 test build event text uses annotation and impact 的預期行為。"""
        text = build_event_text(
            {
                "source": "reuters",
                "title": "Nvidia rises",
                "summary": "AI demand",
                "annotation": {"category": "semiconductor", "sentiment": "bullish"},
                "impact": {"impact_scope": "sector"},
            }
        )

        self.assertIn("semiconductor", text)
        self.assertIn("sector", text)


if __name__ == "__main__":
    unittest.main()
