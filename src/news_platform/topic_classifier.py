"""Deterministic Taiwan society topic classifier."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from news_platform.topics import TOPIC_REGISTRY, TopicSpec


def classify(
    *,
    title: str,
    summary: str | None,
    keywords: list[dict[str, Any]],
    topics: Iterable[TopicSpec] = TOPIC_REGISTRY,
    max_topics: int = 3,
) -> list[dict[str, object]]:
    """Return matching topics sorted by descending score."""
    text_blob = f"{title or ''}\n{summary or ''}"
    kw_set = _keyword_set(keywords)
    topic_limit = max(1, int(max_topics))

    results: list[dict[str, object]] = []
    for spec in topics:
        score = 0.0

        for word in spec.primary:
            if _contains(word, text_blob, kw_set):
                score += 1.0

        for word in spec.supporting:
            if _contains(word, text_blob, kw_set):
                score += 0.3

        for word in spec.exclude:
            if _contains(word, text_blob, kw_set):
                score -= 0.5

        if score >= spec.min_score:
            results.append(
                {
                    "topic_id": spec.topic_id,
                    "label": spec.label,
                    "score": round(score, 2),
                    "source": "rule",
                }
            )

    results.sort(key=lambda item: float(item["score"]), reverse=True)
    return results[:topic_limit]


def _contains(word: str, text_blob: str, kw_set: set[str]) -> bool:
    return word in text_blob or word in kw_set


def _keyword_set(keywords: list[dict[str, Any]]) -> set[str]:
    output: set[str] = set()
    for item in keywords:
        if not isinstance(item, dict):
            continue
        kw = item.get("kw")
        if isinstance(kw, str) and kw:
            output.add(kw)
    return output
