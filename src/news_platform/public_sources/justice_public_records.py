"""Justice and corrections public-record adapters for Taiwan official sources."""

from __future__ import annotations

import csv
import io
import logging
import re
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree as ET

from news_platform.http_client import http_get_bytes
from news_platform.models import PublicRecord
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))

JUDICIAL_BURDEN_TOPIC_ID = "judicial_burden"
JUDICIAL_TOPIC_ID = "judicial_injustice"

MOJ_PROSECUTION_DISPOSITION_DATASET_URL = "https://data.gov.tw/dataset/39402"
MOJ_PROSECUTION_DISPOSITION_DOWNLOAD_URL = (
    "https://www.rjsd.moj.gov.tw/rjsdweb/OpenData.ashx?code=CA0063"
)

MOJAC_DAILY_CUSTODY_DATASET_URL = "https://data.gov.tw/dataset/101185"
MOJAC_DAILY_CUSTODY_DOWNLOAD_URL = "https://prisonmuseum.moj.gov.tw/jqw_pub/today.xml"

_DISPOSITION_METRICS = {
    "起訴": "prosecution_person_count",
    "緩起訴處分": "deferred_prosecution_person_count",
    "不起訴處分": "non_prosecution_person_count",
    "其他": "other_person_count",
}

_GENDER_METRICS = {
    "男性": "male_person_count",
    "女性": "female_person_count",
    "法人": "legal_entity_count",
}


class MojProsecutionDispositionStatsSource:
    source_id = "moj"
    record_type = "moj_prosecution_disposition_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "moj:prosecution_disposition_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_bytes_with_ski_fallback(
                MOJ_PROSECUTION_DISPOSITION_DOWNLOAD_URL,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            logger.warning("MOJ prosecution disposition fetch failed error=%s", exc)
            return []
        records = parse_moj_prosecution_disposition_csv(payload)
        records.sort(key=_record_sort_key, reverse=True)
        return _limit(records, limit)


class MojacDailyCustodyStatsSource:
    source_id = "mojac"
    record_type = "mojac_daily_custody_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "mojac:daily_custody_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_bytes_with_ski_fallback(
                MOJAC_DAILY_CUSTODY_DOWNLOAD_URL,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            logger.warning("MOJAC daily custody fetch failed error=%s", exc)
            return []
        records = parse_mojac_daily_custody_xml(payload)
        records.sort(key=_record_sort_key, reverse=True)
        return _limit(records, limit)


def parse_moj_prosecution_disposition_csv(payload: str | bytes) -> list[PublicRecord]:
    buckets: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {"dispositions": Counter(), "genders": Counter(), "rows": 0}
    )
    for row in _read_csv_rows(payload):
        year = parse_roc_year_number(_get(row, "民國年"))
        month = _to_int(_get(row, "月份"))
        disposition = _clean(_get(row, "偵查終結情形"))
        gender = _clean(_get(row, "性別"))
        value = _to_int(_get(row, "人")) or 0
        if year is None or month is None or not 1 <= month <= 12 or not disposition:
            continue
        bucket = buckets[(year, month)]
        bucket["rows"] += 1
        bucket["dispositions"][disposition] += value
        if gender:
            bucket["genders"][gender] += value

    records: list[PublicRecord] = []
    for (year, month), bucket in buckets.items():
        disposition_counts: Counter[str] = bucket["dispositions"]
        gender_counts: Counter[str] = bucket["genders"]
        total = sum(disposition_counts.values())
        metrics: dict[str, Any] = {
            "year": year,
            "month": month,
            "terminated_person_count": total,
            "source_row_count": bucket["rows"],
        }
        for label, metric_name in _DISPOSITION_METRICS.items():
            metrics[metric_name] = disposition_counts.get(label, 0)
        for label, metric_name in _GENDER_METRICS.items():
            metrics[metric_name] = gender_counts.get(label, 0)
        if total:
            metrics["prosecution_share"] = round(metrics["prosecution_person_count"] / total, 6)
            metrics["non_prosecution_share"] = round(metrics["non_prosecution_person_count"] / total, 6)

        title = (
            f"{year}-{month:02d} 地檢署偵查終結人數 {total} 人："
            f"起訴 {metrics['prosecution_person_count']}、"
            f"緩起訴 {metrics['deferred_prosecution_person_count']}、"
            f"不起訴 {metrics['non_prosecution_person_count']}"
        )
        records.append(
            PublicRecord(
                record_id="moj:prosecution_disposition_stat:" + stable_id(str(year), str(month)),
                source_id="moj",
                record_type="moj_prosecution_disposition_stat",
                country="TW",
                category="society",
                title=title,
                url=MOJ_PROSECUTION_DISPOSITION_DATASET_URL,
                occurred_at=_month_end(year, month),
                region="TW",
                metrics=metrics,
                tags=[
                    JUDICIAL_BURDEN_TOPIC_ID,
                    JUDICIAL_TOPIC_ID,
                    "prosecution",
                    "case_load",
                    "monthly",
                    "moj",
                ],
                raw={
                    "dataset_url": MOJ_PROSECUTION_DISPOSITION_DATASET_URL,
                    "download_url": MOJ_PROSECUTION_DISPOSITION_DOWNLOAD_URL,
                    "disposition_counts": dict(disposition_counts),
                    "gender_counts": dict(gender_counts),
                },
            )
        )
    return records


def parse_mojac_daily_custody_xml(payload: str | bytes) -> list[PublicRecord]:
    text = _decode_bytes(payload) if isinstance(payload, bytes) else payload
    try:
        root = ET.fromstring(text.lstrip("\ufeff"))
    except ET.ParseError as exc:
        logger.warning("MOJAC daily custody XML parse failed error=%s", exc)
        return []

    records: list[PublicRecord] = []
    for item in root.findall(".//Table"):
        row = {child.tag: _clean(child.text) for child in list(item)}
        occurred_at = parse_roc_date(_get(row, "日期"))
        if occurred_at is None:
            continue
        actual = _to_int(_get(row, "實際收容")) or 0
        capacity = _to_int(_get(row, "核定容額")) or 0
        over_capacity_count = max(actual - capacity, 0) if actual and capacity else None
        metrics = {
            "actual_custody_count": actual,
            "male_count": _to_int(_get(row, "男")),
            "female_count": _to_int(_get(row, "女")),
            "approved_capacity_count": capacity,
            "over_capacity_rate": _to_rate(_get(row, "超收率")),
            "intake_count": _to_int(_get(row, "入監人數")),
            "release_count": _to_int(_get(row, "出監人數")),
            "over_capacity_count": over_capacity_count,
        }
        metrics = {key: value for key, value in metrics.items() if value is not None}
        date_key = occurred_at.date().isoformat()
        records.append(
            PublicRecord(
                record_id="mojac:daily_custody_stat:" + stable_id(date_key),
                source_id="mojac",
                record_type="mojac_daily_custody_stat",
                country="TW",
                category="society",
                title=(
                    f"{date_key} 矯正機關收容 {actual} 人、"
                    f"核定容額 {capacity} 人、超收率 {_clean(_get(row, '超收率')) or '0%'}"
                ),
                url=MOJAC_DAILY_CUSTODY_DATASET_URL,
                occurred_at=occurred_at,
                region="TW",
                metrics=metrics,
                tags=[
                    JUDICIAL_BURDEN_TOPIC_ID,
                    JUDICIAL_TOPIC_ID,
                    "corrections",
                    "custody",
                    "over_capacity",
                    "daily",
                    "mojac",
                ],
                raw={
                    "dataset_url": MOJAC_DAILY_CUSTODY_DATASET_URL,
                    "download_url": MOJAC_DAILY_CUSTODY_DOWNLOAD_URL,
                    "row": row,
                },
            )
        )
    return records


def parse_roc_year_number(value: Any) -> int | None:
    text = _clean(value)
    if not text.isdigit():
        return None
    year = int(text)
    return year + 1911 if year < 1911 else year


def parse_roc_date(value: Any) -> datetime | None:
    text = _clean(value)
    match = re.match(r"^(\d{2,4})[/-](\d{1,2})[/-](\d{1,2})$", text)
    if not match:
        return None
    year = parse_roc_year_number(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    if year is None:
        return None
    try:
        return datetime(year, month, day, 23, 59, 59, tzinfo=_TAIPEI)
    except ValueError:
        return None


def _read_csv_rows(payload: str | bytes) -> list[dict[str, Any]]:
    text = _decode_bytes(payload) if isinstance(payload, bytes) else payload
    return [row for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))) if isinstance(row, dict)]


def _decode_bytes(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _record_sort_key(record: PublicRecord) -> tuple[datetime, str]:
    return (record.occurred_at or datetime.min.replace(tzinfo=timezone.utc), record.record_id)


def _limit(records: list[PublicRecord], limit: int | None) -> list[PublicRecord]:
    if limit is None:
        return records
    return records[: max(1, int(limit))]


def _month_end(year: int, month: int) -> datetime:
    day = monthrange(year, month)[1]
    return datetime(year, month, day, 23, 59, 59, tzinfo=_TAIPEI)


def _to_int(value: Any) -> int | None:
    text = _clean(value).replace(",", "")
    if not text or text in {"－", "-", "...", "…"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    text = _clean(value).replace(",", "")
    if not text or text in {"－", "-", "...", "…"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_rate(value: Any) -> float | None:
    text = _clean(value).replace("%", "")
    number = _to_float(text)
    if number is None:
        return None
    return round(number / 100.0, 6)


def _get(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _http_get_bytes_with_ski_fallback(url: str, *, timeout: int) -> bytes:
    try:
        return http_get_bytes(url, timeout=timeout, verify_ssl=True)
    except Exception as exc:
        if "missing subject key identifier" not in str(exc).lower():
            raise
        logger.info("Justice source retry without SSL verification url=%s reason=missing_ski", url)
        return http_get_bytes(url, timeout=timeout, verify_ssl=False)
