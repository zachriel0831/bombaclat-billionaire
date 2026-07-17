"""Deterministic claim-coverage verifier for generated market analysis.

The verifier does not prove semantic truth. It checks whether concrete tokens
that are easy to hallucinate (numbers, dates, tickers) appear in the evidence
corpus used for the prompt.
"""

from __future__ import annotations

import json
import re
from typing import Any


CLAIM_VERIFIER_VERSION = "claim-verifier-v3"
_NUMBER_UNITS = r"%|bp|pp|元|美元|億|萬|兆|B|M"
_NUMBER_RE = re.compile(rf"(?<![\w.%])[-+]?\d+(?:,\d{{3}})*(?:\.\d+)?\s*(?:{_NUMBER_UNITS})?")
_NUMBER_UNIT_SPACE_RE = re.compile(rf"(\d(?:\.\d+)?)\s+(?=(?:{_NUMBER_UNITS}))")
_INTERNAL_EVIDENCE_CITATION_RE = re.compile(
    r"[（(]\s*\d{5,}(?:\s*[,、，]\s*\d{5,})*\s*[）)]"
)
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
    allowed_tickers: set[str] | None = None,
) -> dict[str, Any]:
    """Check numbers, dates, and tickers against prompt evidence."""
    evidence_docs = _build_evidence_docs(events_payload, market_payload)
    evidence_text = "\n".join(doc["text"] for doc in evidence_docs)
    evidence_text_norm = _normalize_text(evidence_text)
    evidence_number_values = _extract_number_values(evidence_text_norm)
    summary = _strip_internal_evidence_citations(summary_text or "")
    allowed_ticker_set = _normalize_ticker_set(allowed_tickers)
    extracted = {
        "numbers": sorted(_extract_numbers(summary)),
        "dates": sorted(_extract_dates(summary)),
        "tickers": sorted(_extract_tickers(summary, structured_payload, evidence_text)),
    }
    unsupported = {
        kind: [
            item
            for item in items
            if not _has_support(kind, item, evidence_text_norm, allowed_ticker_set, evidence_number_values)
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


def _strip_internal_evidence_citations(text: str) -> str:
    return _INTERNAL_EVIDENCE_CITATION_RE.sub("", text or "")


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


def _has_support(
    kind: str,
    item: str,
    evidence_text_norm: str,
    allowed_tickers: set[str],
    evidence_number_values: list[float],
) -> bool:
    if kind == "dates":
        return item in evidence_text_norm or item.replace("-", "/") in evidence_text_norm
    if kind == "numbers":
        variants = _number_variants(item)
        if any(variant and variant in evidence_text_norm for variant in variants):
            return True
        claim_value = _parse_number_value(item)
        return claim_value is not None and any(
            _numbers_close(claim_value, evidence_value)
            for evidence_value in evidence_number_values
        )
    if kind == "tickers":
        normalized = _normalize_ticker(item)
        bare = normalized.split(".", 1)[0]
        if normalized in allowed_tickers or bare in allowed_tickers:
            return True
        evidence_upper = evidence_text_norm.upper()
        return normalized in evidence_upper or bare in evidence_upper
    return False


def _normalize_text(text: str) -> str:
    normalized = str(text or "").replace(",", "").replace("，", "").replace("％", "%")
    return _NUMBER_UNIT_SPACE_RE.sub(r"\1", normalized)


def _normalize_number(text: str) -> str:
    normalized = str(text or "").replace(",", "").replace("，", "").replace("％", "%").strip()
    return _NUMBER_UNIT_SPACE_RE.sub(r"\1", normalized)


def _normalize_date(text: str) -> str:
    parts = re.split(r"[-/]", text)
    if len(parts) != 3:
        return text
    return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _number_variants(item: str) -> set[str]:
    compact = _normalize_number(item)
    variants = {compact, compact.replace(" ", "")}
    unitless = re.sub(rf"\s*(?:{_NUMBER_UNITS})$", "", compact)
    if unitless:
        variants.add(unitless)
    return variants


def _extract_number_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _NUMBER_RE.findall(text or ""):
        value = _parse_number_value(match)
        if value is not None:
            values.append(value)
    return values


def _parse_number_value(text: str) -> float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", _normalize_number(text))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _numbers_close(claim_value: float, evidence_value: float) -> bool:
    tolerance = max(0.005, max(abs(claim_value), abs(evidence_value), 1.0) * 0.00001)
    return abs(claim_value - evidence_value) <= tolerance


def _normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_ticker_set(values: set[str] | None) -> set[str]:
    result: set[str] = set()
    for value in values or set():
        ticker = _normalize_ticker(value)
        if not ticker:
            continue
        result.add(ticker)
        result.add(ticker.split(".", 1)[0])
    return result
