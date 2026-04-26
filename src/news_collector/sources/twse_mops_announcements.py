"""Taiwan Stock Exchange / MOPS major-announcement source.

Pulls disclosures from the public TWSE MOPS endpoint, normalises the
Chinese disclosure fields, and emits ``NewsItem`` rows tagged with
company code + disclosure timestamp."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from news_collector.http_client import http_get_json
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import sort_timestamp, stable_id


logger = logging.getLogger(__name__)

TWSE_KEY_REPORT_DATE = "\u51fa\u8868\u65e5\u671f"
TWSE_KEY_SPOKEN_DATE = "\u767c\u8a00\u65e5\u671f"
TWSE_KEY_SPOKEN_TIME = "\u767c\u8a00\u6642\u9593"
TWSE_KEY_COMPANY_CODE = "\u516c\u53f8\u4ee3\u865f"
TWSE_KEY_COMPANY_NAME = "\u516c\u53f8\u540d\u7a31"
TWSE_KEY_SUBJECT = "\u4e3b\u65e8 "
TWSE_KEY_SUBJECT_ALT = "\u4e3b\u65e8"
TWSE_KEY_CLAUSE = "\u7b26\u5408\u689d\u6b3e"
TWSE_KEY_EVENT_DATE = "\u4e8b\u5be6\u767c\u751f\u65e5"
TWSE_KEY_EXPLANATION = "\u8aaa\u660e"


def _normalize_code(raw: str) -> str | None:
    """正規化 normalize code 對應的資料或結果。"""
    text = (raw or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d{4}", text):
        return None
    return text


def _parse_roc_datetime(date_text: str | None, time_text: str | None) -> datetime | None:
    """解析 parse roc datetime 對應的資料或結果。"""
    date_value = (date_text or "").strip()
    if not date_value:
        return None
    digits = "".join(ch for ch in date_value if ch.isdigit())
    if len(digits) != 7:
        return None
    roc_year = int(digits[:3])
    month = int(digits[3:5])
    day = int(digits[5:7])
    time_digits = "".join(ch for ch in (time_text or "") if ch.isdigit()).zfill(6)
    hour = int(time_digits[:2])
    minute = int(time_digits[2:4])
    second = int(time_digits[4:6])
    try:
        tw_tz = timezone(timedelta(hours=8))
        return datetime(roc_year + 1911, month, day, hour, minute, second, tzinfo=tw_tz)
    except ValueError:
        return None


class TwseMopsAnnouncementsSource(NewsSource):
    """封裝 Twse Mops Announcements Source 相關資料與行為。"""
    name = "twse_mops_announcements"
    endpoint = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"

    def __init__(self, tracked_codes: list[str], timeout_seconds: int = 15, max_items_per_company: int = 5) -> None:
        """初始化物件狀態與必要依賴。"""
        self._tracked_codes = tracked_codes
        self._timeout_seconds = timeout_seconds
        self._max_items_per_company = max(1, int(max_items_per_company))

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        """執行 fetch 方法的主要邏輯。"""
        rows = self._load_rows()
        if not isinstance(rows, list):
            return []

        tracked_codes = {_normalize_code(code) for code in self._tracked_codes}
        tracked_codes.discard(None)
        if not tracked_codes:
            return []

        per_code_count: dict[str, int] = {}
        items: list[NewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            code = _normalize_code(str(row.get(TWSE_KEY_COMPANY_CODE) or ""))
            if not code or code not in tracked_codes:
                continue
            current = per_code_count.get(code, 0)
            if current >= self._max_items_per_company:
                continue

            company_name = str(row.get(TWSE_KEY_COMPANY_NAME) or "").strip()
            subject = str(row.get(TWSE_KEY_SUBJECT) or row.get(TWSE_KEY_SUBJECT_ALT) or "").strip()
            clause = str(row.get(TWSE_KEY_CLAUSE) or "").strip()
            explanation = str(row.get(TWSE_KEY_EXPLANATION) or "").strip()
            spoken_date = str(row.get(TWSE_KEY_SPOKEN_DATE) or row.get(TWSE_KEY_REPORT_DATE) or "").strip()
            spoken_time = str(row.get(TWSE_KEY_SPOKEN_TIME) or "").strip()
            published_at = _parse_roc_datetime(spoken_date, spoken_time)
            if not subject:
                continue

            url = f"{self.endpoint}#code={code}&date={spoken_date}&time={spoken_time}"
            title = f"{code} {company_name}: {subject}"
            summary_parts = []
            if clause:
                summary_parts.append(f"\u7b26\u5408\u689d\u6b3e {clause}")
            if explanation:
                summary_parts.append(explanation.replace("\r", " ").replace("\n", " "))

            items.append(
                NewsItem(
                    id=stable_id("twse_mops", code, spoken_date, spoken_time, subject),
                    source=f"twse_mops:{code}",
                    title=title[:300],
                    url=url,
                    published_at=published_at,
                    summary=" ".join(summary_parts)[:1200] if summary_parts else None,
                    tags=sorted({"twse", "mops", f"code:{code}"}),
                    raw=row,
                )
            )
            per_code_count[code] = current + 1

        items.sort(key=lambda x: sort_timestamp(x.published_at), reverse=True)
        return items[: max(int(limit), 1)]

    def _load_rows(self) -> list[dict]:
        """載入 load rows 對應的資料或結果。"""
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                payload = http_get_json(self.endpoint, timeout=self._timeout_seconds)
                rows = payload.get("data", [])
                return rows if isinstance(rows, list) else []
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    logger.warning("TWSE/MOPS request failed attempt=1 error=%s retrying_once=true", exc)
                    time.sleep(1.0)
                    continue
                raise
        if last_error is not None:
            raise last_error
        return []
