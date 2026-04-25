"""Event pre-processing layer (REQ-013).

Given a stored relay event (title + summary + source), produce a structured
annotation that the market-analysis pipeline can feed to stage1 without asking
the LLM to re-derive it. Provides a deterministic rule-based path so the
pipeline can run even when no annotation worker is active; the LLM path is
reserved as a future opt-in.

Annotation shape (see ``EventAnnotation``):
* ``entities``  — list of ``{kind, value}`` (company / ticker / country /
  policy / macro_indicator / person).
* ``category``  — one of the fixed event categories.
* ``importance``— 0.0 to 1.0.
* ``sentiment`` — bullish / bearish / neutral (global risk-on perspective).

The rule-based annotator is kept intentionally small: it favours precision on
well-known trigger words (FOMC, CPI, TSMC, Powell …) over coverage. Events
without a strong signal fall back to ``other`` / ``neutral`` / 0.3 importance,
which the pipeline still treats as usable context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Iterable


ANNOTATOR_RULE_VERSION = "rule-v1"

CATEGORY_VALUES: tuple[str, ...] = (
    "rate_decision",
    "earnings",
    "geopolitics",
    "supply_chain",
    "regulation",
    "macro_release",
    "corporate_action",
    "other",
)

SENTIMENT_VALUES: tuple[str, ...] = ("bullish", "bearish", "neutral")

ENTITY_KINDS: tuple[str, ...] = (
    "company",
    "ticker",
    "country",
    "policy",
    "macro_indicator",
    "person",
)


@dataclass(frozen=True)
class EventAnnotation:
    entities: tuple[dict[str, str], ...]
    category: str
    importance: float
    sentiment: str
    annotator: str
    annotator_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [dict(entity) for entity in self.entities],
            "category": self.category,
            "importance": round(float(self.importance), 3),
            "sentiment": self.sentiment,
            "annotator": self.annotator,
            "annotator_version": self.annotator_version,
        }


# ---------- entity extraction ----------


_COMPANY_KEYWORDS: tuple[tuple[str, str], ...] = (
    # display name, canonical id
    ("TSMC", "TSMC"),
    ("台積電", "TSMC"),
    ("Hon Hai", "Hon Hai"),
    ("鴻海", "Hon Hai"),
    ("Foxconn", "Hon Hai"),
    ("MediaTek", "MediaTek"),
    ("聯發科", "MediaTek"),
    ("NVIDIA", "NVIDIA"),
    ("Nvidia", "NVIDIA"),
    ("輝達", "NVIDIA"),
    ("AMD", "AMD"),
    ("Intel", "Intel"),
    ("Apple", "Apple"),
    ("蘋果", "Apple"),
    ("Microsoft", "Microsoft"),
    ("Amazon", "Amazon"),
    ("Tesla", "Tesla"),
    ("特斯拉", "Tesla"),
    ("Meta", "Meta"),
    ("Google", "Google"),
    ("Alphabet", "Google"),
)

_COUNTRY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("United States", "US"),
    ("U.S.", "US"),
    ("US ", "US"),
    ("美國", "US"),
    ("Taiwan", "TW"),
    ("台灣", "TW"),
    ("台股", "TW"),
    ("China", "CN"),
    ("中國", "CN"),
    ("陸股", "CN"),
    ("Japan", "JP"),
    ("日本", "JP"),
    ("Korea", "KR"),
    ("南韓", "KR"),
    ("韓國", "KR"),
    ("Germany", "DE"),
    ("德國", "DE"),
    ("Europe", "EU"),
    ("歐洲", "EU"),
    ("歐盟", "EU"),
)

_POLICY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("FOMC", "FOMC"),
    ("Federal Reserve", "Fed"),
    (" Fed ", "Fed"),
    ("美聯儲", "Fed"),
    ("聯準會", "Fed"),
    ("rate hike", "rate_policy"),
    ("rate cut", "rate_policy"),
    ("basis point", "rate_policy"),
    ("升息", "rate_policy"),
    ("降息", "rate_policy"),
    ("ECB", "ECB"),
    ("European Central Bank", "ECB"),
    ("BOJ", "BOJ"),
    ("Bank of Japan", "BOJ"),
    ("日銀", "BOJ"),
    ("PBOC", "PBOC"),
    ("人行", "PBOC"),
    ("tariff", "tariff"),
    ("關稅", "tariff"),
    ("sanction", "sanction"),
    ("制裁", "sanction"),
    ("export control", "export_control"),
    ("出口管制", "export_control"),
)

_MACRO_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("CPI", "CPI"),
    ("消費者物價", "CPI"),
    ("PPI", "PPI"),
    ("生產者物價", "PPI"),
    ("PCE", "PCE"),
    ("nonfarm", "NFP"),
    ("non-farm", "NFP"),
    ("非農", "NFP"),
    ("jobless", "JoblessClaims"),
    ("unemployment", "Unemployment"),
    ("失業率", "Unemployment"),
    ("GDP", "GDP"),
    ("PMI", "PMI"),
    ("ISM", "ISM"),
    ("retail sales", "RetailSales"),
    ("零售銷售", "RetailSales"),
    ("housing starts", "HousingStarts"),
    ("出口訂單", "ExportOrders"),
)

_PERSON_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("Powell", "Jerome Powell"),
    ("鮑爾", "Jerome Powell"),
    ("Lagarde", "Christine Lagarde"),
    ("Yellen", "Janet Yellen"),
    ("Trump", "Donald Trump"),
    ("川普", "Donald Trump"),
    ("Biden", "Joe Biden"),
    ("Xi Jinping", "Xi Jinping"),
    ("習近平", "Xi Jinping"),
)

_US_TICKER_RE = re.compile(r"(?<![A-Z])\$([A-Z]{1,5})\b")
_TW_TICKER_RE = re.compile(r"(?<![0-9a-zA-Z])(\d{4})(?![0-9a-zA-Z])")


def _extract_keyword_entities(
    text: str,
    keywords: Iterable[tuple[str, str]],
    kind: str,
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    lower = text.lower()
    for display, canonical in keywords:
        needle = display.lower()
        if needle.strip() == "":
            continue
        if needle in lower and canonical not in seen:
            hits.append({"kind": kind, "value": canonical})
            seen.add(canonical)
    return hits


def _extract_ticker_entities(text: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _US_TICKER_RE.findall(text):
        key = f"US:{match}"
        if key in seen:
            continue
        seen.add(key)
        hits.append({"kind": "ticker", "value": match})
    for match in _TW_TICKER_RE.findall(text):
        key = f"TW:{match}"
        if key in seen:
            continue
        seen.add(key)
        hits.append({"kind": "ticker", "value": match})
    return hits


def _extract_entities(text: str) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    entities.extend(_extract_keyword_entities(text, _COMPANY_KEYWORDS, "company"))
    entities.extend(_extract_ticker_entities(text))
    entities.extend(_extract_keyword_entities(text, _COUNTRY_KEYWORDS, "country"))
    entities.extend(_extract_keyword_entities(text, _POLICY_KEYWORDS, "policy"))
    entities.extend(_extract_keyword_entities(text, _MACRO_KEYWORDS, "macro_indicator"))
    entities.extend(_extract_keyword_entities(text, _PERSON_KEYWORDS, "person"))
    return entities


# ---------- category classification ----------


_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "rate_decision",
        (
            "fomc", "rate hike", "rate cut", "basis point", "bps",
            "升息", "降息", "利率決議", "ecb meeting",
        ),
    ),
    (
        "earnings",
        (
            "earnings", "revenue", "eps", "guidance", "quarterly",
            "財報", "營收", "獲利", "法說",
        ),
    ),
    (
        "geopolitics",
        (
            "war", "sanction", "strike", "missile", "conflict",
            "戰爭", "制裁", "衝突", "軍事", "襲擊",
        ),
    ),
    (
        "supply_chain",
        (
            "supply chain", "shortage", "capacity", "fab ",
            "供應鏈", "產能", "缺貨", "晶圓",
        ),
    ),
    (
        "regulation",
        (
            "regulation", "antitrust", "probe", "lawsuit", "tariff",
            "export control", "sec charges",
            "監管", "罰款", "訴訟", "關稅", "反壟斷",
        ),
    ),
    (
        "macro_release",
        (
            "cpi", "ppi", "pce", "nonfarm", "non-farm", "gdp", "pmi",
            "jobless", "retail sales", "ism",
            "非農", "消費者物價", "生產者物價", "失業率", "零售銷售",
        ),
    ),
    (
        "corporate_action",
        (
            "dividend", "buyback", "spin-off", "merger", "acquires",
            "acquisition", "split",
            "股利", "庫藏股", "合併", "收購", "分拆",
        ),
    ),
)


def _classify_category(text: str) -> str:
    lower = text.lower()
    for category, keywords in _CATEGORY_RULES:
        for needle in keywords:
            if needle in lower:
                return category
    return "other"


# ---------- importance scoring ----------


_HIGH_WEIGHT_SOURCE_PREFIXES: tuple[str, ...] = (
    "market_context:",
    "bloomberg",
    "reuters",
    "wsj",
    "ft",
    "cnbc",
    "nikkei",
    "federal reserve",
    "bls",
    "yfinance",
)

_BREAKING_MARKERS: tuple[str, ...] = (
    "breaking",
    "flash",
    "urgent",
    "快訊",
    "突發",
    "速報",
)

_NUMBER_PATTERNS: tuple[str, ...] = (
    r"\d+\.\d+%",
    r"\b\d+\s?(?:bps|bp|basis point)",
    r"\b\d+(?:\.\d+)?\s?(?:億|兆|千萬|百萬|萬)",
    r"\$\d+(?:\.\d+)?\s?(?:billion|bn|million|mn|trillion|tn)?",
    r"\b\d+(?:\.\d+)?%",
)

_NUMBER_RE = re.compile("|".join(_NUMBER_PATTERNS), re.IGNORECASE)

_HIGH_IMPACT_CATEGORIES: frozenset[str] = frozenset(
    {"rate_decision", "geopolitics", "macro_release"}
)


def _score_importance(
    source: str,
    title: str,
    summary: str,
    category: str,
) -> float:
    # importance 只做便宜且可預期的 heuristic，故意不要太聰明；
    # 真正的因果與權重交給 stage pipeline，這裡只提供穩定先驗。
    score = 0.3
    text = f"{title}\n{summary}"
    lower = text.lower()
    source_lower = (source or "").lower()

    if any(source_lower.startswith(prefix) for prefix in _HIGH_WEIGHT_SOURCE_PREFIXES):
        score += 0.2
    if _NUMBER_RE.search(text):
        score += 0.2
    if any(marker in lower for marker in _BREAKING_MARKERS):
        score += 0.15
    if category in _HIGH_IMPACT_CATEGORIES:
        score += 0.2
    if category == "earnings":
        score += 0.1

    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return round(score, 3)


# ---------- sentiment ----------


_BULLISH_TERMS: tuple[str, ...] = (
    "beat", "beats", "surge", "rally", "strong", "upgrade",
    "outperform", "bullish", "record high", "breakthrough",
    "上漲", "走強", "強勁", "看多", "創新高", "超預期",
    "利多", "擴張",
)

_BEARISH_TERMS: tuple[str, ...] = (
    "miss", "misses", "plunge", "slump", "weak", "downgrade",
    "underperform", "bearish", "sell-off", "selloff", "tumble",
    "recession", "warning",
    "下跌", "走弱", "疲弱", "看空", "不如預期", "利空", "衰退",
)


def _score_sentiment(title: str, summary: str) -> str:
    text = f"{title}\n{summary}".lower()
    bull = sum(1 for term in _BULLISH_TERMS if term.lower() in text)
    bear = sum(1 for term in _BEARISH_TERMS if term.lower() in text)
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"


# ---------- public API ----------


def annotate(
    *,
    source: str,
    title: str,
    summary: str | None,
    raw_json: str | None = None,
) -> EventAnnotation:
    """Rule-based annotation. Deterministic and cheap to run in-process."""
    title_str = title or ""
    summary_str = summary or ""
    # market_context 類事件很多重要訊號藏在 raw_json，不在 title/summary；
    # 先抽一小段可讀 hint 併進規則判斷，避免 context 類資料全部被打成 other。
    extra_text = _extract_market_context_hint(raw_json)
    text = "\n".join(filter(None, [title_str, summary_str, extra_text]))

    entities = tuple(_extract_entities(text))
    category = _classify_category(text)
    importance = _score_importance(source, title_str, summary_str, category)
    sentiment = _score_sentiment(title_str, summary_str)

    return EventAnnotation(
        entities=entities,
        category=category,
        importance=importance,
        sentiment=sentiment,
        annotator="rule",
        annotator_version=ANNOTATOR_RULE_VERSION,
    )


def _extract_market_context_hint(raw_json: str | None) -> str:
    """For market_context:* rows the human-readable signal lives in the payload.

    Only a few known string fields are surfaced so that the cheap annotator can
    see them; large nested structures are ignored to keep the rules local.
    """
    if not raw_json:
        return ""
    try:
        payload = json.loads(raw_json)
    except (ValueError, TypeError):
        return ""
    if not isinstance(payload, dict):
        return ""

    parts: list[str] = []
    for key in ("dataset_title", "event_type", "series_id", "periodName"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            parts.append(value)

    point = payload.get("point")
    if isinstance(point, dict):
        label = point.get("label")
        if isinstance(label, str):
            parts.append(label)

    events = payload.get("events")
    if isinstance(events, list):
        for ev in events[:5]:
            if isinstance(ev, dict):
                title = ev.get("title") or ev.get("headline")
                if isinstance(title, str):
                    parts.append(title)

    return " ".join(parts)
