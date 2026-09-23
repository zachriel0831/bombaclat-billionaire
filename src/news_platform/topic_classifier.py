"""Deterministic Taiwan news topic classifier."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from news_platform.topics import TOPIC_REGISTRY, TopicSpec


def classify(
    *,
    title: str,
    summary: str | None,
    keywords: list[dict[str, Any]],
    category: str | None = None,
    topics: Iterable[TopicSpec] = TOPIC_REGISTRY,
    max_topics: int = 3,
) -> list[dict[str, object]]:
    """Return matching topics sorted by descending score."""
    text_blob = f"{title or ''}\n{_strip_related_sections(summary or '')}"
    kw_set = _keyword_set(keywords)
    normalized_category = _normalize_category(category)
    topic_limit = max(1, int(max_topics))

    results: list[dict[str, object]] = []
    for spec in topics:
        if spec.categories and normalized_category not in _normalize_categories(spec.categories):
            continue

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


def _normalize_categories(categories: tuple[str, ...]) -> set[str]:
    return {_normalize_category(category) for category in categories}


def _normalize_category(category: str | None) -> str:
    return (category or "").strip().lower()


def _contains(word: str, text_blob: str, kw_set: set[str]) -> bool:
    if word == "中共" and word in text_blob:
        # Counts such as "當中共11案" do not refer to the CCP.
        return re.search(r"(?<![其當当之])中共", text_blob) is not None
    return word in text_blob or word in kw_set


def classify_category(*, title: str, category: str) -> str:
    """Route clear housing contract inspections out of publisher politics feeds."""
    if _normalize_category(category) != "politics":
        return category
    # ponytail: title-only inspection rule; extend only with reviewed category errors.
    if not all(word in title for word in ("預售屋", "契約", "查核")):
        return category
    if any(
        _contains(word, title, set())
        for spec in TOPIC_REGISTRY
        if "politics" in spec.categories
        for word in spec.primary
        if word not in {"行政院", "政策"}
    ):
        return category
    return "society"


def _strip_related_sections(text: str) -> str:
    """Remove publisher related-link blocks that can pollute article summaries."""
    output = text
    for marker in ("延伸閱讀：", "延伸閱讀:", "相關新聞：", "相關新聞:", "更多新聞：", "更多新聞:"):
        if marker in output:
            output = output.split(marker, 1)[0]
    return output


def _keyword_set(keywords: list[dict[str, Any]]) -> set[str]:
    output: set[str] = set()
    for item in keywords:
        if not isinstance(item, dict):
            continue
        kw = item.get("kw")
        if isinstance(kw, str) and kw:
            output.add(kw)
    return output
