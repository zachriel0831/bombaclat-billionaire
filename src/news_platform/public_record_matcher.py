"""Deterministic article-to-public-record matching."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublicRecordMatch:
    article_id: str
    public_record_id: str
    relation_type: str
    confidence: float
    matched_by: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicRecordLinkRunResult:
    scanned_articles: int
    candidate_records: int
    matched: int
    linked: int
    duplicates: int
    failed: int


class ArticlePublicRecordMatcher:
    """High-precision matcher for article rows and structured official records."""

    def __init__(self, *, min_confidence: float = 0.68, max_per_article: int = 3) -> None:
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.max_per_article = max(1, int(max_per_article))

    def match_article(self, article: Any, records: Iterable[Any]) -> list[PublicRecordMatch]:
        matches: list[PublicRecordMatch] = []
        for record in records:
            match = self._match_one(article, record)
            if match is not None:
                matches.append(match)
        matches.sort(key=lambda item: item.confidence, reverse=True)
        return matches[: self.max_per_article]

    def _match_one(self, article: Any, record: Any) -> PublicRecordMatch | None:
        article_category = str(getattr(article, "category", "") or "").strip()
        record_category = str(getattr(record, "category", "") or "").strip()
        if record_category and article_category and record_category != article_category:
            return None

        record_type = str(getattr(record, "record_type", "") or "")
        if record_type in {"legislative_bill", "healthcare_legislative_bill"}:
            return self._match_legislative_bill(article, record)
        if record_type == "fraud_rumor":
            return self._match_fraud_rumor(article, record)
        return None

    def _match_legislative_bill(self, article: Any, record: Any) -> PublicRecordMatch | None:
        article_text = _normalize_text(
            f"{getattr(article, 'title', '')} {getattr(article, 'summary', '') or ''}"
        )
        record_title = _normalize_text(getattr(record, "title", "") or "")
        if not article_text or not record_title:
            return None

        raw = _loads_json(getattr(record, "raw_json", None))
        law_names = _law_names(record_title)
        title_bases = _title_bases(record_title)
        people = _record_people(raw)

        matched_title = record_title in article_text
        matched_laws = [name for name in law_names if name and name in article_text]
        matched_bases = [term for term in title_bases if term and term in article_text]
        matched_people = [name for name in people if name and name in article_text]

        subject_hit = matched_title or matched_laws or matched_bases
        if not subject_hit:
            return None

        score = 0.0
        if matched_title:
            score += 0.92
        if matched_laws:
            longest = max(len(name) for name in matched_laws)
            score += 0.62 if longest >= 8 else 0.50
        non_law_bases = [term for term in matched_bases if term not in matched_laws]
        if non_law_bases:
            score += min(0.24, 0.08 * len(non_law_bases))
        if matched_people:
            score += min(0.28, 0.12 + 0.04 * (len(matched_people) - 1))

        days_between = _days_between(getattr(article, "published_at", None), getattr(record, "occurred_at", None))
        if days_between is not None:
            if days_between <= 3:
                score += 0.12
            elif days_between <= 7:
                score += 0.08
            elif days_between <= 30:
                score += 0.04

        confidence = round(min(score, 0.99), 4)
        if confidence < self.min_confidence:
            return None

        relation_type = "cites" if matched_title else "mentions"
        evidence = {
            "record_type": str(getattr(record, "record_type", "") or "legislative_bill"),
            "record_title": record_title,
            "article_title": str(getattr(article, "title", "") or ""),
            "matched_title": matched_title,
            "matched_laws": matched_laws,
            "matched_title_terms": matched_bases,
            "matched_people": matched_people,
            "days_between": days_between,
        }
        return PublicRecordMatch(
            article_id=str(getattr(article, "article_id", "")),
            public_record_id=str(getattr(record, "record_id", "")),
            relation_type=relation_type,
            confidence=confidence,
            matched_by="ly_bill_rule",
            evidence=evidence,
        )

    def _match_fraud_rumor(self, article: Any, record: Any) -> PublicRecordMatch | None:
        article_text = _normalize_text(
            f"{getattr(article, 'title', '')} {getattr(article, 'summary', '') or ''}"
        )
        record_title = _normalize_text(getattr(record, "title", "") or "")
        if not article_text or not record_title:
            return None

        raw = _loads_json(getattr(record, "raw_json", None))
        matched_title = record_title in article_text
        title_terms = _fraud_title_terms(record_title)
        matched_terms = [term for term in title_terms if term in article_text]
        fraud_context = any(term in article_text for term in ("詐騙", "假投資", "違法投資", "165", "刑事警察局"))

        score = 0.0
        if matched_title:
            score += 0.92
        elif fraud_context and len(matched_terms) >= 2:
            score += 0.64 + min(0.12, 0.04 * (len(matched_terms) - 2))
        elif fraud_context and matched_terms and len(max(matched_terms, key=len)) >= 6:
            score += 0.66
        else:
            return None

        days_between = _days_between(getattr(article, "published_at", None), getattr(record, "occurred_at", None))
        if days_between is not None:
            if days_between <= 7:
                score += 0.10
            elif days_between <= 30:
                score += 0.05

        confidence = round(min(score, 0.97), 4)
        if confidence < self.min_confidence:
            return None

        evidence = {
            "record_type": "fraud_rumor",
            "record_title": record_title,
            "article_title": str(getattr(article, "title", "") or ""),
            "matched_title": matched_title,
            "matched_terms": matched_terms,
            "fraud_context": fraud_context,
            "days_between": days_between,
            "dataset_url": raw.get("dataset_url"),
        }
        return PublicRecordMatch(
            article_id=str(getattr(article, "article_id", "")),
            public_record_id=str(getattr(record, "record_id", "")),
            relation_type="mentions",
            confidence=confidence,
            matched_by="npa_fraud_rumor_rule",
            evidence=evidence,
        )


class PublicRecordLinkWorker:
    def __init__(
        self,
        store,
        *,
        batch_size: int = 200,
        record_limit: int = 1000,
        lookback_days: int = 45,
        min_confidence: float = 0.68,
        max_per_article: int = 3,
    ) -> None:
        self._store = store
        self._batch_size = max(1, int(batch_size))
        self._record_limit = max(1, int(record_limit))
        self._lookback_days = max(1, int(lookback_days))
        self._matcher = ArticlePublicRecordMatcher(
            min_confidence=min_confidence,
            max_per_article=max_per_article,
        )

    def run_once(self) -> PublicRecordLinkRunResult:
        articles = self._store.fetch_articles_for_public_record_matching(
            limit=self._batch_size,
            lookback_days=self._lookback_days,
            categories=("politics", "society"),
        )
        records = self._store.fetch_public_records_for_matching(
            limit=self._record_limit,
            lookback_days=self._lookback_days,
            categories=("politics", "society"),
        )
        linked = 0
        duplicates = 0
        failed = 0
        matched = 0
        for article in articles:
            matches = self._matcher.match_article(article, records)
            matched += len(matches)
            for match in matches:
                try:
                    inserted = self._store.link_article_public_record(
                        article_id=match.article_id,
                        public_record_id=match.public_record_id,
                        relation_type=match.relation_type,
                        confidence=match.confidence,
                        matched_by=match.matched_by,
                        evidence=match.evidence,
                    )
                except Exception as exc:
                    logger.warning(
                        "Article-record link failed article_id=%s record_id=%s error=%s",
                        match.article_id,
                        match.public_record_id,
                        exc,
                    )
                    failed += 1
                    continue
                if inserted:
                    linked += 1
                else:
                    duplicates += 1
        return PublicRecordLinkRunResult(
            scanned_articles=len(articles),
            candidate_records=len(records),
            matched=matched,
            linked=linked,
            duplicates=duplicates,
            failed=failed,
        )


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _law_names(record_title: str) -> list[str]:
    names = re.findall(r"[\u4e00-\u9fff]{2,32}(?:法|條例)", record_title)
    return _dedupe([_normalize_text(name) for name in names if len(name) >= 3])


def _title_bases(record_title: str) -> list[str]:
    text = record_title
    text = re.sub(r"第[\d零〇○一二三四五六七八九十百千萬]+(?:條(?:之一)?|項|款)?", " ", text)
    for token in (
        "部分條文修正草案",
        "條文修正草案",
        "修正草案",
        "增訂",
        "草案",
        "部分",
        "條文",
        "施行",
        "及",
    ):
        text = text.replace(token, " ")
    chunks = re.findall(r"[\u4e00-\u9fff]{2,32}", text)
    terms = [chunk for chunk in chunks if chunk not in {"修正", "增訂"}]
    return _dedupe(_law_names(record_title) + terms)


def _record_people(raw: dict[str, Any]) -> list[str]:
    people: list[str] = []
    for key in ("proposers", "cosignatories"):
        value = raw.get(key)
        if isinstance(value, list):
            people.extend(str(item).strip() for item in value if str(item).strip())
    for key in ("billProposer", "billCosignatory"):
        value = raw.get(key)
        if isinstance(value, str):
            people.extend(part.strip() for part in value.split(";") if part.strip())
    return _dedupe([name for name in people if len(name) >= 2])


def _fraud_title_terms(title: str) -> list[str]:
    text = re.sub(r"\d+年第[一二三四1-4]季", " ", title)
    stop_terms = {
        "注意",
        "詐騙",
        "詐騙集團",
        "假冒",
        "公布",
        "業者",
        "刊登",
        "態樣",
    }
    for term in stop_terms:
        text = text.replace(term, " ")
    chunks = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,32}", text)
    return _dedupe([chunk for chunk in chunks if len(chunk) >= 2 and chunk not in stop_terms])


def _days_between(left: datetime | None, right: datetime | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left.date() - right.date()).days)


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
