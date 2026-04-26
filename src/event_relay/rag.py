from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import logging
import math
import os
import re
import sys
from typing import Any, Iterable, Protocol

from event_relay.config import load_settings, parse_bool
from event_relay.service import (
    AnalysisEmbeddingSource,
    MySqlEventStore,
    StoredEventEmbedding,
    SummaryEvent,
)


logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "local-hash-v1"
DEFAULT_EMBEDDING_DIMENSIONS = 128
DEFAULT_MIN_SIMILARITY = 0.22
DEFAULT_RAG_K = 5
DEFAULT_CANDIDATE_LIMIT = 500


class EventEmbeddingStore(Protocol):
    """封裝 Event Embedding Store 相關資料與行為。"""
    def fetch_event_embedding_candidates(
        self,
        *,
        embedding_model: str,
        limit: int,
    ) -> list[StoredEventEmbedding]:
        """抓取 fetch event embedding candidates 對應的資料或結果。"""
        ...


@dataclass(frozen=True)
class RagExample:
    """封裝 Rag Example 相關資料與行為。"""
    event_row_id: int
    event_id: str | None
    source: str
    title: str
    summary: str
    url: str
    published_at: str | None
    created_at: str
    similarity: float

    def to_prompt_dict(self) -> dict[str, Any]:
        """轉換 to prompt dict 對應的資料或結果。"""
        return {
            "event_id": self.event_row_id,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "published_at": self.published_at,
            "created_at": self.created_at,
            "similarity": round(float(self.similarity), 4),
        }


def text_hash(text: str) -> str:
    """執行 text hash 的主要流程。"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _cjk_ngrams(value: str) -> Iterable[str]:
    """執行 cjk ngrams 的主要流程。"""
    cjk_chars = [char for char in value if "\u4e00" <= char <= "\u9fff"]
    for idx, char in enumerate(cjk_chars):
        yield char
        if idx + 1 < len(cjk_chars):
            yield char + cjk_chars[idx + 1]


def tokenize(text: str) -> list[str]:
    """執行 tokenize 的主要流程。"""
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_.$%-]+", lowered)
    tokens.extend(_cjk_ngrams(lowered))
    return [token for token in tokens if token.strip()]


def embed_text(
    text: str,
    *,
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> list[float]:
    """Return a deterministic lexical embedding.

    This first production-safe version avoids adding a new paid API dependency
    while keeping the table contract ready for OpenAI/Voyage/BGE embeddings.
    """
    safe_dimensions = max(16, int(dimensions))
    vector = [0.0] * safe_dimensions
    for token in tokenize(text):
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % safe_dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [round(value / norm, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """執行 cosine similarity 的主要流程。"""
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    if length <= 0:
        return 0.0
    dot = sum(float(left[idx]) * float(right[idx]) for idx in range(length))
    left_norm = math.sqrt(sum(float(left[idx]) * float(left[idx]) for idx in range(length)))
    right_norm = math.sqrt(sum(float(right[idx]) * float(right[idx]) for idx in range(length)))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def build_event_text(event: SummaryEvent | dict[str, Any] | StoredEventEmbedding) -> str:
    """建立 build event text 對應的資料或結果。"""
    if isinstance(event, dict):
        annotation = event.get("annotation") if isinstance(event.get("annotation"), dict) else {}
        impact = event.get("impact") if isinstance(event.get("impact"), dict) else {}
        parts = [
            str(event.get("source") or ""),
            str(event.get("title") or ""),
            str(event.get("summary") or ""),
            str(annotation.get("category") or ""),
            str(annotation.get("sentiment") or ""),
            json.dumps(impact, ensure_ascii=False, sort_keys=True) if impact else "",
        ]
    else:
        parts = [
            event.source,
            event.title,
            event.summary,
            event.published_at or "",
        ]
    return "\n".join(part for part in parts if part).strip()


def build_analysis_text(analysis: AnalysisEmbeddingSource) -> str:
    """建立 build analysis text 對應的資料或結果。"""
    parts = [
        analysis.analysis_date,
        analysis.analysis_slot,
        analysis.summary_text,
    ]
    if analysis.raw_json:
        try:
            raw = json.loads(analysis.raw_json)
        except (TypeError, ValueError):
            raw = None
        if isinstance(raw, dict):
            structured = raw.get("structured")
            if structured is not None:
                parts.append(json.dumps(structured, ensure_ascii=False, sort_keys=True))
    return "\n".join(part for part in parts if part).strip()


def build_query_text(query_events: list[dict[str, Any]]) -> str:
    """建立 build query text 對應的資料或結果。"""
    return "\n\n".join(build_event_text(event) for event in query_events[:30]).strip()


def retrieve_similar_events(
    store: EventEmbeddingStore,
    query_events: list[dict[str, Any]],
    *,
    k: int = DEFAULT_RAG_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> list[RagExample]:
    """檢索 retrieve similar events 對應的資料或結果。"""
    query_text = build_query_text(query_events)
    if not query_text:
        return []

    excluded_ids = {
        int(event["id"])
        for event in query_events
        if isinstance(event, dict) and str(event.get("id") or "").isdigit()
    }
    query_embedding = embed_text(query_text, dimensions=dimensions)
    candidates = store.fetch_event_embedding_candidates(
        embedding_model=embedding_model,
        limit=max(int(candidate_limit), int(k), 1),
    )

    scored: list[RagExample] = []
    for candidate in candidates:
        if candidate.event_row_id in excluded_ids:
            continue
        score = cosine_similarity(query_embedding, candidate.embedding)
        if score < float(min_similarity):
            continue
        scored.append(
            RagExample(
                event_row_id=candidate.event_row_id,
                event_id=candidate.event_id,
                source=candidate.source,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published_at=candidate.published_at,
                created_at=candidate.created_at,
                similarity=score,
            )
        )

    scored.sort(key=lambda item: (item.similarity, item.event_row_id), reverse=True)
    return scored[: max(int(k), 0)]


def index_recent_documents(
    store: MySqlEventStore,
    *,
    days: int = 30,
    event_limit: int = 500,
    analysis_limit: int = 100,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> dict[str, int]:
    """建立索引 index recent documents 對應的資料或結果。"""
    events = store.fetch_events_missing_embeddings(
        days=days,
        limit=event_limit,
        embedding_model=embedding_model,
    )
    events_indexed = 0
    for event in events:
        text = build_event_text(event)
        if not text:
            continue
        store.upsert_event_embedding(
            event=event,
            embedding_model=embedding_model,
            embedding=embed_text(text, dimensions=dimensions),
            text_hash=text_hash(text),
        )
        events_indexed += 1

    analyses = store.fetch_analyses_missing_embeddings(
        limit=analysis_limit,
        embedding_model=embedding_model,
    )
    analyses_indexed = 0
    for analysis in analyses:
        text = build_analysis_text(analysis)
        if not text:
            continue
        store.upsert_analysis_embedding(
            analysis=analysis,
            embedding_model=embedding_model,
            embedding=embed_text(text, dimensions=dimensions),
            text_hash=text_hash(text),
            outcome_json={"status": "unlabeled"},
        )
        analyses_indexed += 1

    return {
        "events_seen": len(events),
        "events_indexed": events_indexed,
        "analyses_seen": len(analyses),
        "analyses_indexed": analyses_indexed,
    }


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Index recent events and analyses for historical-case RAG")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--days", type=int, default=int(os.getenv("RAG_INDEX_LOOKBACK_DAYS", "30")))
    parser.add_argument("--event-limit", type=int, default=int(os.getenv("RAG_INDEX_EVENT_LIMIT", "500")))
    parser.add_argument("--analysis-limit", type=int, default=int(os.getenv("RAG_INDEX_ANALYSIS_LIMIT", "100")))
    parser.add_argument("--embedding-model", default=os.getenv("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL))
    parser.add_argument("--dimensions", type=int, default=int(os.getenv("RAG_EMBEDDING_DIMENSIONS", str(DEFAULT_EMBEDDING_DIMENSIONS))))
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main() -> int:
    """程式入口，負責執行此模組的主要流程。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    settings = load_settings(args.env_file)
    if not settings.mysql_enabled:
        raise RuntimeError("RAG indexing requires RELAY_MYSQL_ENABLED=true")

    store = MySqlEventStore(settings)
    store.initialize()
    result = index_recent_documents(
        store,
        days=args.days,
        event_limit=args.event_limit,
        analysis_limit=args.analysis_limit,
        embedding_model=args.embedding_model,
        dimensions=args.dimensions,
    )
    logger.info("RAG indexing result: %s", result)
    return 0


def rag_enabled_from_env() -> bool:
    """執行 rag enabled from env 的主要流程。"""
    return parse_bool(os.getenv("MARKET_ANALYSIS_RAG_ENABLED", "true"), default=True)


if __name__ == "__main__":
    raise SystemExit(main())
