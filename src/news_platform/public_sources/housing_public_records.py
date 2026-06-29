"""Housing public-record adapters for Taiwan official sources."""

from __future__ import annotations

import csv
import io
import logging
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any

from news_platform.http_client import http_get_bytes
from news_platform.models import PublicRecord
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))
HOUSING_TOPIC_ID = "housing_justice"

TAIPEI_HOUSING_PRICE_INDEX_DATASET_URL = "https://data.gov.tw/dataset/121381"
TAIPEI_HOUSING_PRICE_INDEX_DOWNLOAD_URL = (
    "https://data.taipei/api/dataset/ce4ea2c6-6334-44f8-945a-5705492b187d/"
    "resource/02c7bb70-2113-4daf-81d3-5c14b9ae26df/download"
)


class TaipeiHousingPriceIndexSource:
    source_id = "taipei_open_data"
    record_type = "taipei_housing_price_index"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "taipei:housing_price_index"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = http_get_bytes(TAIPEI_HOUSING_PRICE_INDEX_DOWNLOAD_URL, timeout=self.timeout_seconds).decode(
                "cp950",
                errors="replace",
            )
        except Exception as exc:
            logger.warning("Taipei housing price index fetch failed error=%s", exc)
            return []
        records = parse_taipei_housing_price_index_csv(payload)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        return records


def parse_taipei_housing_price_index_csv(payload: str) -> list[PublicRecord]:
    rows = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    records: list[PublicRecord] = []
    for row in rows:
        category = (row.get("住宅價格月指數類別") or "").strip()
        period = (row.get("期別") or "").strip()
        year_month = _parse_roc_year_month(period)
        if not category or year_month is None:
            continue

        year, month = year_month
        occurred_at = datetime(year, month, monthrange(year, month)[1], 23, 59, 59, tzinfo=_TAIPEI)
        index_value = _number(row.get("月指數"))
        total_price = _number(row.get("標準住宅總價（新台幣萬元）"))
        unit_price = _number(row.get("標準住宅單價（新台幣萬元每坪）"))
        title = f"{year}-{month:02d} 台北市{category}住宅價格月指數"
        if index_value is not None:
            title += f"，指數 {index_value:g}"
        if total_price is not None:
            title += f"，標準總價 {total_price:g} 萬元"

        records.append(
            PublicRecord(
                record_id=f"taipei:housing_price_index:{stable_id(category, period)}",
                source_id=TaipeiHousingPriceIndexSource.source_id,
                record_type=TaipeiHousingPriceIndexSource.record_type,
                country="TW",
                category=TaipeiHousingPriceIndexSource.category,
                title=title,
                url=TAIPEI_HOUSING_PRICE_INDEX_DATASET_URL,
                occurred_at=occurred_at,
                region="台北市",
                metrics={
                    "year": year,
                    "month": month,
                    "monthly_index": index_value,
                    "quarter_moving_average": _number(row.get("季移動平均數")),
                    "half_year_moving_average": _number(row.get("半年移動平均數")),
                    "monthly_index_change_rate": _percent(row.get("月指數變動率")),
                    "quarter_moving_average_change_rate": _percent(row.get("季移動平均數變動率")),
                    "half_year_moving_average_change_rate": _percent(row.get("半年移動平均數變動率")),
                    "standard_total_price_10k_twd": total_price,
                    "standard_unit_price_10k_twd_per_ping": unit_price,
                },
                tags=[HOUSING_TOPIC_ID, "housing_price_index", "taipei"],
                raw={
                    "download_url": TAIPEI_HOUSING_PRICE_INDEX_DOWNLOAD_URL,
                    "dataset_url": TAIPEI_HOUSING_PRICE_INDEX_DATASET_URL,
                    "category": category,
                    "period": period,
                    "row": row,
                },
            )
        )
    return records


def _parse_roc_year_month(value: str) -> tuple[int, int] | None:
    if "/" not in value:
        return None
    year_text, month_text = value.strip().split("/", 1)
    try:
        year = int(year_text) + 1911
        month = int(month_text)
    except ValueError:
        return None
    return (year, month) if 1 <= month <= 12 else None


def _number(value: str | None) -> float | None:
    text = (value or "").strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _percent(value: str | None) -> float | None:
    text = (value or "").strip()
    if text.endswith("%"):
        text = text[:-1]
    number = _number(text)
    return None if number is None else number / 100.0
