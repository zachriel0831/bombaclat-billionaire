"""REQ-014 retrieval-augmented context for the analysis pipeline.

Computes / stores embedding vectors for events and past analyses, and
retrieves the top-K similar items to feed stage1 / stage4 as historical
context. Pure-Python cosine similarity over MySQL-stored vectors so the
pipeline does not depend on an external vector DB."""

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
    StoredAnalysisEmbedding,
    StoredEventEmbedding,
    SummaryEvent,
)


logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "local-hash-v1"
DEFAULT_EMBEDDING_DIMENSIONS = 128
DEFAULT_MIN_SIMILARITY = 0.22
DEFAULT_RAG_K = 5
DEFAULT_CANDIDATE_LIMIT = 500
DEFAULT_METADATA_FILTER_THRESHOLD = 0.10
DEFAULT_VECTOR_WEIGHT = 0.62
DEFAULT_METADATA_WEIGHT = 0.25
DEFAULT_OUTCOME_WEIGHT = 0.13
DOMAIN_TOPICS = {
    "ai",
    "bank",
    "brent",
    "capex",
    "chip",
    "cpi",
    "credit",
    "earnings",
    "energy",
    "fed",
    "inflation",
    "jobs",
    "labor",
    "liquidity",
    "nvidia",
    "oil",
    "ppi",
    "rate",
    "rates",
    "semiconductor",
    "tariff",
    "treasury",
    "tsm",
    "wti",
    "yield",
    "yields",
}


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
    kind: str = "event"
    metadata_score: float = 0.0
    outcome_score: float = 0.5
    hybrid_score: float = 0.0
    analysis_id: int | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        """轉換 to prompt dict 對應的資料或結果。"""
        payload = {
            "kind": self.kind,
            "event_id": self.event_row_id,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "published_at": self.published_at,
            "created_at": self.created_at,
            "similarity": round(float(self.similarity), 4),
            "metadata_score": round(float(self.metadata_score), 4),
            "outcome_score": round(float(self.outcome_score), 4),
            "hybrid_score": round(float(self.hybrid_score), 4),
        }
        if self.analysis_id is not None:
            payload["analysis_id"] = self.analysis_id
        return payload


@dataclass(frozen=True)
class MetadataProfile:
    """Small metadata fingerprint used for hybrid RAG filtering."""
    source_families: frozenset[str]
    categories: frozenset[str]
    tickers: frozenset[str]
    topics: frozenset[str]
    slots: frozenset[str]

    def has_filter_terms(self) -> bool:
        return bool(self.categories or self.tickers or self.topics or self.slots)


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


def metadata_profile_from_event(event: dict[str, Any] | StoredEventEmbedding | StoredAnalysisEmbedding) -> MetadataProfile:
    """Extract a compact metadata profile for hybrid RAG ranking."""
    if isinstance(event, dict):
        source = str(event.get("source") or "")
        title = str(event.get("title") or "")
        summary = str(event.get("summary") or "")
        annotation = event.get("annotation") if isinstance(event.get("annotation"), dict) else {}
        raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
        categories = {
            str(annotation.get("category") or "").strip().lower(),
            str(raw.get("event_type") or "").strip().lower(),
            str(raw.get("dimension") or "").strip().lower(),
        }
        slots = {str(raw.get("slot") or "").strip().lower()}
    elif isinstance(event, StoredAnalysisEmbedding):
        source = f"market_analysis:{event.analysis_slot}"
        title = event.analysis_slot
        summary = event.summary_text
        categories = {"analysis"}
        slots = {event.analysis_slot.lower()}
    else:
        source = event.source
        title = event.title
        summary = event.summary
        categories = set()
        slots = set()

    text = f"{source}\n{title}\n{summary}"
    return MetadataProfile(
        source_families=frozenset(filter(None, {_source_family(source)})),
        categories=frozenset(item for item in categories if item),
        tickers=frozenset(_extract_tickers(text)),
        topics=frozenset(token for token in tokenize(text) if token in DOMAIN_TOPICS),
        slots=frozenset(item for item in slots if item),
    )


def build_query_metadata(query_events: list[dict[str, Any]]) -> MetadataProfile:
    """Merge metadata profiles from the current prompt context."""
    families: set[str] = set()
    categories: set[str] = set()
    tickers: set[str] = set()
    topics: set[str] = set()
    slots: set[str] = set()
    for event in query_events[:60]:
        profile = metadata_profile_from_event(event)
        families.update(profile.source_families)
        categories.update(profile.categories)
        tickers.update(profile.tickers)
        topics.update(profile.topics)
        slots.update(profile.slots)
    return MetadataProfile(
        source_families=frozenset(families),
        categories=frozenset(categories),
        tickers=frozenset(tickers),
        topics=frozenset(topics),
        slots=frozenset(slots),
    )


def metadata_match_score(query: MetadataProfile, candidate: MetadataProfile) -> float:
    """Score metadata overlap on a 0..1 scale."""
    score = 0.0
    score += 0.10 if query.source_families & candidate.source_families else 0.0
    score += 0.25 if query.categories & candidate.categories else 0.0
    score += 0.30 if query.tickers & candidate.tickers else 0.0
    score += min(0.25, 0.10 * len(query.topics & candidate.topics))
    score += 0.10 if query.slots & candidate.slots else 0.0
    return max(0.0, min(1.0, score))


def outcome_score_from_json(outcome_json: dict[str, Any] | None) -> float:
    """Map stored outcome metadata to a 0..1 retrieval prior."""
    if not isinstance(outcome_json, dict):
        return 0.5
    for key in ("outcome_score", "score"):
        raw_score = _to_float(outcome_json.get(key))
        if raw_score is not None:
            return max(0.0, min(1.0, raw_score if raw_score <= 1 else raw_score / 100.0))
    status = str(outcome_json.get("status") or "").strip().lower()
    if status in {"success", "win", "won", "profitable", "target_hit", "good"}:
        return 0.9
    if status in {"failed", "failure", "loss", "lost", "stop_hit", "bad"}:
        return 0.1
    if outcome_json.get("target_hit") is True:
        return 0.9
    if outcome_json.get("stop_hit") is True:
        return 0.1
    realized = _to_float(outcome_json.get("realized_return_pct"))
    if realized is not None:
        if realized >= 8:
            return 0.9
        if realized >= 2:
            return 0.75
        if realized > 0:
            return 0.60
        if realized > -2:
            return 0.40
        return 0.20
    return 0.5


def _source_family(source: str) -> str:
    """Coarsen source names for metadata matching."""
    text = source.strip().lower()
    if text.startswith("market_context:"):
        return "market_context"
    if text.startswith("market_analysis:"):
        return "market_analysis"
    if text.startswith(("sec:", "twse_mops:", "fed:", "bls:", "eia:", "treasury:")):
        return "official"
    if text.startswith(("x:", "twitter:", "tweet:")):
        return "social"
    if any(name in text for name in ("reuters", "bloomberg", "bbc", "cnbc", "rss", "news")):
        return "news"
    return text.split(":", 1)[0] if text else ""


def _extract_tickers(text: str) -> set[str]:
    """Extract common US/TW ticker-like tokens for metadata filtering."""
    tickers = {match.upper() for match in re.findall(r"\b\d{4}(?:\.TW|\.TWO)?\b", text, flags=re.IGNORECASE)}
    tickers.update(
        match.upper()
        for match in re.findall(r"\b[A-Z]{2,5}\b", text)
        if match.upper() not in {"THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT"}
    )
    return tickers


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def retrieve_similar_events(
    store: EventEmbeddingStore,
    query_events: list[dict[str, Any]],
    *,
    k: int = DEFAULT_RAG_K,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
    metadata_filter_threshold: float = DEFAULT_METADATA_FILTER_THRESHOLD,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
    metadata_weight: float = DEFAULT_METADATA_WEIGHT,
    outcome_weight: float = DEFAULT_OUTCOME_WEIGHT,
    include_analysis_examples: bool = True,
    analysis_slot: str | None = None,
) -> list[RagExample]:
    """Retrieve hybrid-ranked historical event/analysis examples."""
    query_text = build_query_text(query_events)
    if not query_text:
        return []

    excluded_ids = {
        int(event["id"])
        for event in query_events
        if isinstance(event, dict) and str(event.get("id") or "").isdigit()
    }
    query_embedding = embed_text(query_text, dimensions=dimensions)
    query_metadata = build_query_metadata(query_events)
    event_candidates = store.fetch_event_embedding_candidates(
        embedding_model=embedding_model,
        limit=max(int(candidate_limit), int(k), 1),
    )

    scored: list[RagExample] = []
    for candidate in event_candidates:
        if candidate.event_row_id in excluded_ids:
            continue
        example = _score_event_candidate(
            candidate,
            query_embedding=query_embedding,
            query_metadata=query_metadata,
            min_similarity=min_similarity,
            metadata_filter_threshold=metadata_filter_threshold,
            vector_weight=vector_weight,
            metadata_weight=metadata_weight,
            outcome_weight=outcome_weight,
        )
        if example is not None:
            scored.append(example)

    if include_analysis_examples:
        fetch_analyses = getattr(store, "fetch_analysis_embedding_candidates", None)
        if callable(fetch_analyses):
            analysis_candidates = fetch_analyses(
                embedding_model=embedding_model,
                limit=max(int(candidate_limit // 4), int(k), 1),
            )
            for candidate in analysis_candidates:
                if analysis_slot and candidate.analysis_slot and candidate.analysis_slot != analysis_slot:
                    continue
                example = _score_analysis_candidate(
                    candidate,
                    query_embedding=query_embedding,
                    query_metadata=query_metadata,
                    min_similarity=min_similarity,
                    metadata_filter_threshold=metadata_filter_threshold,
                    vector_weight=vector_weight,
                    metadata_weight=metadata_weight,
                    outcome_weight=outcome_weight,
                )
                if example is not None:
                    scored.append(example)

    scored.sort(key=lambda item: (item.hybrid_score, item.similarity, item.outcome_score, item.event_row_id), reverse=True)
    return scored[: max(int(k), 0)]


def _score_event_candidate(
    candidate: StoredEventEmbedding,
    *,
    query_embedding: list[float],
    query_metadata: MetadataProfile,
    min_similarity: float,
    metadata_filter_threshold: float,
    vector_weight: float,
    metadata_weight: float,
    outcome_weight: float,
) -> RagExample | None:
    semantic_score = cosine_similarity(query_embedding, candidate.embedding)
    if semantic_score < float(min_similarity):
        return None
    metadata_score = metadata_match_score(query_metadata, metadata_profile_from_event(candidate))
    if query_metadata.has_filter_terms() and metadata_score < float(metadata_filter_threshold):
        return None
    outcome_score = outcome_score_from_json(candidate.outcome_json)
    hybrid_score = _hybrid_score(
        semantic_score,
        metadata_score,
        outcome_score,
        vector_weight=vector_weight,
        metadata_weight=metadata_weight,
        outcome_weight=outcome_weight,
    )
    return RagExample(
        event_row_id=candidate.event_row_id,
        event_id=candidate.event_id,
        source=candidate.source,
        title=candidate.title,
        summary=candidate.summary,
        url=candidate.url,
        published_at=candidate.published_at,
        created_at=candidate.created_at,
        similarity=semantic_score,
        metadata_score=metadata_score,
        outcome_score=outcome_score,
        hybrid_score=hybrid_score,
    )


def _score_analysis_candidate(
    candidate: StoredAnalysisEmbedding,
    *,
    query_embedding: list[float],
    query_metadata: MetadataProfile,
    min_similarity: float,
    metadata_filter_threshold: float,
    vector_weight: float,
    metadata_weight: float,
    outcome_weight: float,
) -> RagExample | None:
    semantic_score = cosine_similarity(query_embedding, candidate.embedding)
    if semantic_score < float(min_similarity):
        return None
    metadata_score = metadata_match_score(query_metadata, metadata_profile_from_event(candidate))
    if query_metadata.has_filter_terms() and metadata_score < float(metadata_filter_threshold):
        return None
    outcome_score = outcome_score_from_json(candidate.outcome_json)
    hybrid_score = _hybrid_score(
        semantic_score,
        metadata_score,
        outcome_score,
        vector_weight=vector_weight,
        metadata_weight=metadata_weight,
        outcome_weight=outcome_weight,
    )
    return RagExample(
        event_row_id=candidate.analysis_id,
        event_id=f"analysis-{candidate.analysis_id}",
        source=f"market_analysis:{candidate.analysis_slot}",
        title=f"Historical {candidate.analysis_slot} analysis {candidate.analysis_date}",
        summary=candidate.summary_text[:1200],
        url=f"internal://market_analysis/{candidate.analysis_id}",
        published_at=candidate.analysis_date,
        created_at=candidate.updated_at,
        similarity=semantic_score,
        kind="analysis",
        metadata_score=metadata_score,
        outcome_score=outcome_score,
        hybrid_score=hybrid_score,
        analysis_id=candidate.analysis_id,
    )


def _hybrid_score(
    semantic_score: float,
    metadata_score: float,
    outcome_score: float,
    *,
    vector_weight: float,
    metadata_weight: float,
    outcome_weight: float,
) -> float:
    total_weight = max(0.0001, float(vector_weight) + float(metadata_weight) + float(outcome_weight))
    semantic_component = max(0.0, min(1.0, (float(semantic_score) + 1.0) / 2.0))
    return (
        semantic_component * float(vector_weight)
        + max(0.0, min(1.0, float(metadata_score))) * float(metadata_weight)
        + max(0.0, min(1.0, float(outcome_score))) * float(outcome_weight)
    ) / total_weight


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
