from __future__ import annotations

import json
import logging
import time

from news_collector.http_client import http_get_text
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import parse_datetime, stable_id


logger = logging.getLogger(__name__)
GDELT_MIN_REQUEST_INTERVAL_SECONDS = 5.0
_LAST_GDELT_REQUEST_TS = 0.0
_GDELT_COOLDOWN_UNTIL_TS = 0.0

GDELT_ALLOWED_LANGUAGE_TOKENS = ("english", "chinese")

GDELT_TOPIC_INCLUDE_KEYWORDS = (
    # Politics / international affairs
    "politics",
    "political",
    "election",
    "government",
    "diplomacy",
    "diplomatic",
    "sanction",
    "tariff",
    "war",
    "conflict",
    "summit",
    "geopolit",
    "foreign policy",
    "parliament",
    "congress",
    "international",
    "global",
    # Economy / finance
    "finance",
    "financial",
    "economy",
    "economic",
    "market",
    "stocks",
    "bond",
    "yield",
    "inflation",
    "recession",
    "central bank",
    "interest rate",
    "gdp",
    "banking",
    "currency",
    "forex",
    "treasury",
    "commodity",
    # Technology
    "technology",
    "tech",
    "ai",
    "artificial intelligence",
    "semiconductor",
    "chip",
    "software",
    "cloud",
    "cybersecurity",
    "data center",
    # Chinese terms (politics/economy/tech)
    "\u653f\u6cbb",  # ?踵祥
    "\u570b\u969b",  # ??
    "\u56fd\u9645",  # ?賡?
    "\u5916\u4ea4",  # 憭漱
    "\u5236\u88c1",  # ?嗉?
    "\u6230\u722d",  # ?啁
    "\u6218\u4e89",  # ??
    "\u885d\u7a81",  # 銵?
    "\u51b2\u7a81",  # ?脩?
    "\u5cf0\u6703",  # 撜唳?
    "\u5cf0\u4f1a",  # 撜唬?
    "\u5927\u9078",  # 憭折
    "\u5927\u9009",  # 憭折?    "\u8ca1\u7d93",  # 鞎∠?
    "\u8d22\u7ecf",  # 韐Ｙ?
    "\u7d93\u6fdf",  # 蝬?
    "\u7ecf\u6d4e",  # 蝏?
    "\u5e02\u5834",  # 撣
    "\u5e02\u573a",  # 撣
    "\u80a1\u5e02",  # ?∪?
    "\u901a\u81a8",  # ?
    "\u592e\u884c",  # 憭株?
    "\u5229\u7387",  # ?拍?
    "\u79d1\u6280",  # 蝘?
    "\u534a\u5c0e\u9ad4",  # ??擃?    "\u534a\u5bfc\u4f53",  # ?紡雿?    "\u6676\u7247",  # ?嗥?
    "\u82af\u7247",  # ?舐?
    "\u4eba\u5de5\u667a\u6167",  # 鈭箏極?箸
    "\u4eba\u5de5\u667a\u80fd",  # 鈭箏極?箄
)

GDELT_TOPIC_EXCLUDE_KEYWORDS = (
    "entertainment",
    "celebrity",
    "movie",
    "film",
    "music",
    "tv",
    "showbiz",
    "sports",
    "football",
    "soccer",
    "basketball",
    "baseball",
    "tennis",
    "nfl",
    "nba",
    "nhl",
    "mlb",
    "fifa",
    "hollywood",
    "anime",
    "wrestling",
    # Chinese entertainment/sports terms
    "\u5a1b\u6a02",  # 憡?
    "\u5a31\u4e50",  # 憡曹?
    "\u5f71\u8996",  # 敶梯?
    "\u5f71\u89c6",  # 敶梯?
    "\u96fb\u5f71",  # ?餃蔣
    "\u7535\u5f71",  # ?萄蔣
    "\u97f3\u6a02",  # ?單?
    "\u97f3\u4e50",  # ?喃?
    "\u9ad4\u80b2",  # 擃
    "\u4f53\u80b2",  # 雿
    "\u8db3\u7403",  # 頞喟?
    "\u7c43\u7403",  # 蝐?
    "\u7bee\u7403",  # 蝭桃?
    "\u68d2\u7403",  # 璉?
    "\u7d9c\u85dd",  # 蝬?
    "\u7efc\u827a",  # 蝏潸
    "\u516b\u5366",  # ?怠
    "\u660e\u661f",  # ??
)


def _throttle_gdelt_requests() -> None:
    global _LAST_GDELT_REQUEST_TS

    now = time.monotonic()
    wait_seconds = GDELT_MIN_REQUEST_INTERVAL_SECONDS - (now - _LAST_GDELT_REQUEST_TS)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _LAST_GDELT_REQUEST_TS = time.monotonic()


def _is_gdelt_in_cooldown() -> bool:
    return time.monotonic() < _GDELT_COOLDOWN_UNTIL_TS


def _set_gdelt_cooldown(seconds: float) -> None:
    global _GDELT_COOLDOWN_UNTIL_TS
    now = time.monotonic()
    _GDELT_COOLDOWN_UNTIL_TS = max(_GDELT_COOLDOWN_UNTIL_TS, now + seconds)


class GdeltSource(NewsSource):
    name = "gdelt"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(
        self,
        query: str,
        max_records: int = 50,
        timeout_seconds: int = 15,
        cooldown_on_429: bool = False,
        cooldown_seconds: int = 600,
    ) -> None:
        self.query = query
        self.max_records = max_records
        self.timeout_seconds = timeout_seconds
        self.cooldown_on_429 = cooldown_on_429
        self.cooldown_seconds = max(int(cooldown_seconds), 1)

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        # If cooldown mode is enabled and we're cooling down, skip this cycle.
        if self.cooldown_on_429 and _is_gdelt_in_cooldown():
            remaining = int(_GDELT_COOLDOWN_UNTIL_TS - time.monotonic())
            logger.warning("GDELT in cooldown, skip request (remaining=%ss)", max(remaining, 1))
            return []

        # Fetch extra rows then apply strict local filters for language/topic.
        max_records = min(max(limit * 4, limit, 1), self.max_records)
        params = {
            "query": self.query,
            "mode": "ArtList",
            "format": "json",
            "sort": "datedesc",
            "maxrecords": max_records,
        }

        payload: dict = {}
        for attempt in range(3):
            try:
                _throttle_gdelt_requests()
                raw_text = http_get_text(self.endpoint, params=params, timeout=self.timeout_seconds)
                payload = _parse_gdelt_payload(raw_text)
                break
            except Exception as exc:
                message = str(exc)
                if "429" in message:
                    if self.cooldown_on_429:
                        _set_gdelt_cooldown(float(self.cooldown_seconds))
                        logger.warning(
                            "GDELT rate-limited (429), enter cooldown for %ss and skip this cycle",
                            self.cooldown_seconds,
                        )
                    else:
                        logger.warning("GDELT rate-limited (429), cooldown switch is OFF, skip this cycle")
                    return []

                if attempt < 2:
                    sleep_seconds = GDELT_MIN_REQUEST_INTERVAL_SECONDS * (attempt + 1)
                    logger.warning("GDELT request failed, retry in %.1fs: %s", sleep_seconds, message)
                    time.sleep(sleep_seconds)
                    continue
                raise

        articles = payload.get("articles", [])
        raw_count = len(articles)
        language_pass_count = 0
        topic_pass_count = 0

        items: list[NewsItem] = []
        for article in articles:
            if not _is_allowed_language(article):
                continue
            language_pass_count += 1

            if not _is_allowed_topic(article):
                continue
            topic_pass_count += 1

            title = article.get("title") or "(untitled)"
            url = article.get("url") or ""
            published = parse_datetime(article.get("seendate"))

            tags: list[str] = []
            for key in ("domain", "language", "sourcecountry"):
                value = article.get(key)
                if value:
                    tags.append(str(value))

            items.append(
                NewsItem(
                    id=stable_id("gdelt", str(article.get("url")), str(article.get("seendate"))),
                    source="gdelt",
                    title=title,
                    url=url,
                    published_at=published,
                    summary=article.get("snippet") or None,
                    tags=sorted(set(tags)),
                    raw=article,
                )
            )

        logger.info(
            "GDELT filtered raw=%d language_pass=%d topic_pass=%d output=%d",
            raw_count,
            language_pass_count,
            topic_pass_count,
            len(items[:limit]),
        )
        return items[:limit]


def _parse_gdelt_payload(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise RuntimeError("GDELT returned empty response body")

    lower = text.lower()
    # GDELT 常見限頻文字回覆（非 JSON）。
    if "please limit requests to one every 5 seconds" in lower or "too many requests" in lower:
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        snippet = " ".join(text.split())[:200]
        raise RuntimeError(f"GDELT returned non-JSON body: {snippet}") from exc

    if isinstance(payload, dict):
        return payload
    raise RuntimeError("GDELT returned non-object JSON payload")


def _is_allowed_language(article: dict) -> bool:
    language = str(article.get("language") or "").strip().lower()
    return any(token in language for token in GDELT_ALLOWED_LANGUAGE_TOKENS)


def _is_allowed_topic(article: dict) -> bool:
    title = str(article.get("title") or "")
    snippet = str(article.get("snippet") or "")
    url = str(article.get("url") or "")
    domain = str(article.get("domain") or "")
    text = f"{title} {snippet} {url} {domain}".lower()

    # Exclude entertainment/sports first, then require one relevant policy/econ/tech keyword.
    if any(keyword in text for keyword in GDELT_TOPIC_EXCLUDE_KEYWORDS):
        return False
    return any(keyword in text for keyword in GDELT_TOPIC_INCLUDE_KEYWORDS)

