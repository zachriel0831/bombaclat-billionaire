"""Deterministic claim-coverage verifier for generated market analysis.

The verifier does not prove semantic truth. It checks whether concrete tokens
that are easy to hallucinate (numbers, dates, tickers) appear in the evidence
corpus used for the prompt.
"""

from __future__ import annotations

import json
import re
from typing import Any


CLAIM_VERIFIER_VERSION = "claim-verifier-v1"
_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|bp|pp|元|美元|億|萬|B|M)?")
_DATE_RE = re.compile(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b")
_TW_TICKER_RE = re.compile(r"\b\d{4}(?:\.TW|\.TWO)?\b", re.IGNORECASE)
_US_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")
_STOP_WORD_TICKERS = {
    "AI",
    "API",
    "CEO",
    "CFO",
    "CPI",
    "ETF",
    "FCF",
    "FOMC",
    "GDP",
    "JSON",
    "LLM",
    "PMI",
    "RAG",
    "SEC",
    "TGA",
    "USD",
    "VIX",
}


def verify_claim_coverage(
    *,
    summary_text: str,
    structured_payload: dict[str, Any] | None,
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check numbers, dates, and tickers against prompt evidence."""
    evidence_docs = _build_evidence_docs(events_payload, market_payload)
    evidence_text = "\n".join(doc["text"] for doc in evidence_docs)
    evidence_text_norm = _normalize_text(evidence_text)
    summary = summary_text or ""
    extracted = {
        "numbers": sorted(_extract_numbers(summary)),
        "dates": sorted(_extract_dates(summary)),
        "tickers": sorted(_extract_tickers(summary, structured_payload, evidence_text)),
    }
    unsupported = {
        kind: [
            item
            for item in items
            if not _has_support(kind, item, evidence_text_norm, evidence_docs)
        ]
        for kind, items in extracted.items()
    }
    checked = sum(len(items) for items in extracted.values())
    unsupported_count = sum(len(items) for items in unsupported.values())
    support_rate = 1.0 if checked == 0 else (checked - unsupported_count) / checked
    return {
        "version": CLAIM_VERIFIER_VERSION,
        "ok": unsupported_count == 0,
        "support_rate": round(support_rate, 4),
        "checked_counts": {kind: len(items) for kind, items in extracted.items()},
        "unsupported_counts": {kind: len(items) for kind, items in unsupported.items()},
        "unsupported": {kind: items[:20] for kind, items in unsupported.items()},
        "evidence_doc_count": len(evidence_docs),
    }


def _build_evidence_docs(
    events_payload: list[dict[str, Any]],
    market_payload: list[dict[str, Any]],
) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    for event in events_payload:
        if not isinstance(event, dict):
            continue
        raw = event.get("raw")
        raw_text = json.dumps(raw, ensure_ascii=False, sort_keys=True) if isinstance(raw, dict) else ""
        docs.append(
            {
                "id": str(event.get("id") or ""),
                "text": "\n".join(
                    str(part or "")
                    for part in (
                        event.get("id"),
                        event.get("source"),
                        event.get("title"),
                        event.get("summary"),
                        event.get("published_at"),
                        event.get("created_at"),
                        raw_text,
                    )
                ),
            }
        )
    for row in market_payload:
        if not isinstance(row, dict):
            continue
        docs.append(
            {
                "id": str(row.get("event_id") or row.get("symbol") or ""),
                "text": json.dumps(row, ensure_ascii=False, sort_keys=True),
            }
        )
    return docs


def _extract_numbers(text: str) -> set[str]:
    result: set[str] = set()
    for match in _NUMBER_RE.findall(text or ""):
        normalized = _normalize_number(match)
        if not normalized:
            continue
        # Four-digit stock codes are checked as tickers, not numeric claims.
        if re.fullmatch(r"\d{4}", normalized):
            continue
        result.add(normalized)
    return result


def _extract_dates(text: str) -> set[str]:
    return {_normalize_date(match) for match in _DATE_RE.findall(text or "")}


def _extract_tickers(text: str, structured_payload: dict[str, Any] | None, evidence_text: str) -> set[str]:
    result = {match.upper() for match in _TW_TICKER_RE.findall(text or "")}
    evidence_upper = evidence_text.upper()
    for match in _US_TICKER_RE.findall(text or ""):
        token = match.upper()
        if token in _STOP_WORD_TICKERS:
            continue
        # Avoid treating ordinary English words as tickers unless the token
        # also appears in the evidence corpus.
        if token in evidence_upper:
            result.add(token)
    if isinstance(structured_payload, dict):
        for row in structured_payload.get("stock_watch") or []:
            if isinstance(row, dict) and row.get("ticker"):
                result.add(str(row["ticker"]).upper())
    return result


def _has_support(kind: str, item: str, evidence_text_norm: str, evidence_docs: list[dict[str, str]]) -> bool:
    if kind == "dates":
        return item in evidence_text_norm or item.replace("-", "/") in evidence_text_norm
    if kind == "numbers":
        variants = _number_variants(item)
        return any(variant and variant in evidence_text_norm for variant in variants)
    if kind == "tickers":
        normalized = item.upper()
        bare = normalized.split(".", 1)[0]
        return normalized in evidence_text_norm.upper() or bare in evidence_text_norm.upper()
    return False


def _normalize_text(text: str) -> str:
    return str(text or "").replace(",", "").replace("％", "%")


def _normalize_number(text: str) -> str:
    return str(text or "").replace(",", "").replace("％", "%").strip()


def _normalize_date(text: str) -> str:
    parts = re.split(r"[-/]", text)
    if len(parts) != 3:
        return text
    return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _number_variants(item: str) -> set[str]:
    compact = _normalize_number(item)
    variants = {compact}
    unitless = re.sub(r"\s*(%|bp|pp|元|美元|億|萬|B|M)$", "", compact)
    if unitless:
        variants.add(unitless)
    return variants
