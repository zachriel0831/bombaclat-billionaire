"""Quota-managed prompt context pack builder for scheduled market analysis.

The relay event window can be noisy. This module keeps prompt inputs balanced
by reserving room for deterministic scorecards, market context, and important
official data before filling the remaining budget with news and other events.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


CONTEXT_PACK_VERSION = "context-pack-v1"
BUCKET_ORDER = (
    "scorecard",
    "market_context",
    "official_data",
    "upstream_analysis",
    "market_snapshot",
    "news",
    "social",
    "other",
)
GUARANTEED_BUCKETS = ("scorecard", "market_context", "official_data")
OFFICIAL_SOURCE_PREFIXES = (
    "sec:",
    "twse_mops:",
    "fed:",
    "federal_reserve:",
    "treasury:",
    "bls:",
    "eia:",
    "twse:",
    "tpex:",
    "taifex:",
)
NEWS_SOURCE_HINTS = (
    "rss",
    "reuters",
    "bloomberg",
    "bbc",
    "cnbc",
    "wsj",
    "financial_times",
    "fox",
    "npr",
    "google_news",
)
SOCIAL_SOURCE_PREFIXES = ("x:", "twitter:", "tweet:", "truthsocial:")


def default_source_quotas(max_events: int) -> dict[str, int]:
    """Return source-family quota caps for one context pack."""
    limit = max(1, int(max_events))
    return {
        "scorecard": min(2, max(1, limit // 60)),
        "market_context": max(3, int(limit * 0.35)),
        "official_data": max(2, int(limit * 0.20)),
        "upstream_analysis": max(1, int(limit * 0.05)),
        "market_snapshot": max(1, int(limit * 0.05)),
        "news": max(1, int(limit * 0.25)),
        "social": max(0, int(limit * 0.05)),
        "other": max(1, int(limit * 0.05)),
    }


def classify_event_source(event: dict[str, Any]) -> str:
    """Classify one event into a context-pack source bucket."""
    source = str(event.get("source") or "").strip().lower()
    raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}
    event_type = str(raw.get("event_type") or "").strip().lower() if isinstance(raw, dict) else ""

    if source == "market_context:scorecard" or event_type == "market_context_scorecard":
        return "scorecard"
    if source.startswith("market_context:"):
        return "market_context"
    if source.startswith("market_analysis:"):
        return "upstream_analysis"
    if source == "us_index_tracker" or source.startswith("yfinance_"):
        return "market_snapshot"
    if source.startswith(SOCIAL_SOURCE_PREFIXES) or source in {"x", "twitter"}:
        return "social"
    if source.startswith(OFFICIAL_SOURCE_PREFIXES):
        return "official_data"
    if any(hint in source for hint in NEWS_SOURCE_HINTS):
        return "news"
    return "other"


def build_context_pack(
    events: list[dict[str, Any]],
    *,
    max_events: int,
    source_quotas: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a quota-balanced event pack for market-analysis prompts."""
    limit = max(1, int(max_events))
    quotas = {**default_source_quotas(limit), **(source_quotas or {})}
    candidates = _dedupe_events(events)
    bucketed: dict[str, list[tuple[int, dict[str, Any]]]] = {bucket: [] for bucket in BUCKET_ORDER}
    for index, event in enumerate(candidates):
        bucket = classify_event_source(event)
        bucketed.setdefault(bucket, []).append((index, event))

    selected: list[tuple[int, str, dict[str, Any]]] = []
    selected_keys: set[tuple[str, str]] = set()

    def add_bucket(bucket: str) -> None:
        quota = max(0, int(quotas.get(bucket, 0)))
        if quota <= 0 or len(selected) >= limit:
            return
        added = 0
        for index, event in _ranked(bucketed.get(bucket, [])):
            if added >= quota or len(selected) >= limit:
                break
            key = _event_key(event)
            if key in selected_keys:
                continue
            selected.append((index, bucket, event))
            selected_keys.add(key)
            added += 1

    for bucket in BUCKET_ORDER:
        add_bucket(bucket)

    if len(selected) < limit:
        remaining: list[tuple[int, dict[str, Any]]] = []
        for items in bucketed.values():
            remaining.extend(items)
        for index, event in _ranked(remaining):
            if len(selected) >= limit:
                break
            key = _event_key(event)
            if key in selected_keys:
                continue
            selected.append((index, classify_event_source(event), event))
            selected_keys.add(key)

    selected.sort(key=lambda item: (BUCKET_ORDER.index(item[1]) if item[1] in BUCKET_ORDER else len(BUCKET_ORDER), item[0]))
    packed = [_with_context_bucket(event, bucket) for _index, bucket, event in selected]
    candidate_counts = Counter(classify_event_source(event) for event in candidates)
    selected_counts = Counter(event.get("context_bucket") or classify_event_source(event) for event in packed)
    dropped_counts = {
        bucket: max(0, int(candidate_counts.get(bucket, 0)) - int(selected_counts.get(bucket, 0)))
        for bucket in sorted(set(candidate_counts) | set(selected_counts))
    }
    telemetry = {
        "version": CONTEXT_PACK_VERSION,
        "enabled": True,
        "input_count": len(events),
        "candidate_count": len(candidates),
        "output_count": len(packed),
        "max_events": limit,
        "quotas": {bucket: int(quotas.get(bucket, 0)) for bucket in BUCKET_ORDER},
        "candidate_counts": dict(candidate_counts),
        "selected_counts": dict(selected_counts),
        "dropped_counts": dropped_counts,
        "guaranteed_buckets": {
            bucket: {
                "candidate_count": int(candidate_counts.get(bucket, 0)),
                "selected_count": int(selected_counts.get(bucket, 0)),
                "satisfied": int(candidate_counts.get(bucket, 0)) == 0
                or int(selected_counts.get(bucket, 0)) > 0,
            }
            for bucket in GUARANTEED_BUCKETS
        },
    }
    return packed, telemetry


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate events while preserving first-seen order."""
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        key = _event_key(event)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def _event_key(event: dict[str, Any]) -> tuple[str, str]:
    """Return a stable key for one prompt event."""
    event_id = event.get("id") or event.get("event_id")
    if event_id is not None:
        return ("id", str(event_id))
    return (
        "fingerprint",
        "|".join(
            str(event.get(key) or "")
            for key in ("source", "title", "url", "published_at", "created_at")
        ),
    )


def _ranked(items: list[tuple[int, dict[str, Any]]]) -> list[tuple[int, dict[str, Any]]]:
    """Rank by rule annotation importance, then keep original recency order."""
    return sorted(items, key=lambda item: (-_importance(item[1]), item[0]))


def _importance(event: dict[str, Any]) -> float:
    """Read rule/LLM annotation importance defensively."""
    annotation = event.get("annotation") if isinstance(event.get("annotation"), dict) else {}
    try:
        return float(annotation.get("importance") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _with_context_bucket(event: dict[str, Any], bucket: str) -> dict[str, Any]:
    """Copy the event and attach pack metadata used by prompts/telemetry."""
    copy = dict(event)
    copy["context_bucket"] = bucket
    return copy
