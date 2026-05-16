"""National Police Agency public-record adapters."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import zipfile
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from news_platform.http_client import http_get_bytes, http_get_text
from news_platform.models import PublicRecord
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))

FRAUD_RUMOR_DATASET_URL = "https://data.gov.tw/dataset/38262"
FRAUD_RUMOR_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "4F4DF9A5-DF4C-4EE8-A50D-869347D38D9E/resource/"
    "3FD6EC97-D1AC-4B50-82AF-66AECE6A756F/download"
)

TRAFFIC_A1_DATASET_URL = "https://data.gov.tw/dataset/57023"
TRAFFIC_A1_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "F4077949-50CC-4640-8114-79958CC8BBEA/resource/"
    "5D5EFC6C-BFC2-4727-AFBC-A4EE0825D3FF/download"
)
TRAFFIC_A2_DATASET_URL = "https://data.gov.tw/dataset/57024"
TRAFFIC_A2_DOWNLOAD_URLS = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "F713DBFE-7432-4401-B5C0-1C07A8F5B1FB/resource/"
    "12676819-B43E-405F-B4ED-580BF77036D0/download",
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "F713DBFE-7432-4401-B5C0-1C07A8F5B1FB/resource/"
    "1B0A2667-C932-4EB7-8AC1-68B30AC602C0/download",
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "F713DBFE-7432-4401-B5C0-1C07A8F5B1FB/resource/"
    "1CFFE5C9-51BD-49DE-A6FC-9F9BBF4698C6/download",
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "F713DBFE-7432-4401-B5C0-1C07A8F5B1FB/resource/"
    "A16927F0-88B0-474E-81F9-0016D55EFAC6/download",
)

DRUNK_DRIVING_DATASET_URL = "https://data.gov.tw/dataset/9018"
DRUNK_DRIVING_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "9E413113-EA49-41DF-822C-E89D94A78807/resource/"
    "000F1CF6-FED1-4C08-B405-4A5B7A7E2BC2/download"
)

FRAUD_BLOCKED_DOMAIN_DATASET_URL = "https://data.gov.tw/en/datasets/176455"
FRAUD_BLOCKED_DOMAIN_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "29E8E643-88ED-4952-B21E-BD42A3B7108C/resource/"
    "E5465CB7-2482-4988-AD9A-6B39D82AC5B6/download"
)

FRAUD_ENFORCEMENT_DATASET_URL = "https://data.gov.tw/dataset/172159"
FRAUD_ENFORCEMENT_DOWNLOAD_URL = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "7F7EEF1C-0946-4A09-87E5-EC34C14C3A80/resource/"
    "7615153E-E5C5-4D89-84DF-C51C95FCCE4D/download"
)


@dataclass(frozen=True)
class TrafficAccidentGroup:
    key: tuple[str, str, str, str]
    rows: list[dict[str, Any]]


class NpaFraudRumorSource:
    source_id = "npa"
    record_type = "fraud_rumor"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "npa:fraud_rumor"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_text_with_ski_fallback(FRAUD_RUMOR_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("NPA fraud rumor fetch failed error=%s", exc)
            return []
        records = parse_fraud_rumor_csv(payload)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("NPA fraud rumor source returned no records")
        return records


class NpaTrafficAccidentA1Source:
    source_id = "npa"
    record_type = "traffic_accident_a1"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "npa:traffic_accident_a1"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_text_with_ski_fallback(TRAFFIC_A1_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("NPA traffic A1 fetch failed error=%s", exc)
            return []
        records = parse_traffic_a1_payload(payload)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("NPA traffic A1 source returned no records")
        return records


class NpaTrafficAccidentA2StatsSource:
    source_id = "npa"
    record_type = "traffic_accident_a2_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 45) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "npa:traffic_accident_a2_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        records_by_id: dict[str, PublicRecord] = {}
        for url in TRAFFIC_A2_DOWNLOAD_URLS:
            try:
                payload = _http_get_bytes_with_ski_fallback(url, timeout=self.timeout_seconds)
            except Exception as exc:
                logger.warning("NPA traffic A2 stats fetch failed url=%s error=%s", url, exc)
                continue
            for record in parse_traffic_a2_zip_stats(payload, download_url=url):
                existing = records_by_id.get(record.record_id)
                if existing is None:
                    records_by_id[record.record_id] = record
                else:
                    records_by_id[record.record_id] = merge_traffic_stat_records(existing, record)
        records = sorted(
            records_by_id.values(),
            key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("NPA traffic A2 stats source returned no records")
        return records


class NpaDrunkDrivingStatsSource:
    source_id = "npa"
    record_type = "traffic_drunk_driving_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "npa:traffic_drunk_driving_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_text_with_ski_fallback(DRUNK_DRIVING_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("NPA drunk-driving stats fetch failed error=%s", exc)
            return []
        records = parse_drunk_driving_stats_csv(payload)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("NPA drunk-driving stats source returned no records")
        return records


class NpaFraudBlockedDomainStatsSource:
    source_id = "npa"
    record_type = "fraud_blocked_domain_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "npa:fraud_blocked_domain_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_text_with_ski_fallback(
                FRAUD_BLOCKED_DOMAIN_DOWNLOAD_URL,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            logger.warning("NPA blocked-domain stats fetch failed error=%s", exc)
            return []
        records = parse_fraud_blocked_domain_stats_csv(payload)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("NPA blocked-domain stats source returned no records")
        return records


class NpaFraudEnforcementStatsSource:
    source_id = "npa"
    record_type = "fraud_enforcement_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "npa:fraud_enforcement_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_text_with_ski_fallback(FRAUD_ENFORCEMENT_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("NPA fraud enforcement stats fetch failed error=%s", exc)
            return []
        records = parse_fraud_enforcement_stats_csv(payload)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("NPA fraud enforcement stats source returned no records")
        return records


def parse_fraud_rumor_csv(payload: str | bytes) -> list[PublicRecord]:
    text = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, bytes) else payload
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    records: list[PublicRecord] = []
    for row in reader:
        record = fraud_rumor_row_to_record(row)
        if record is not None:
            records.append(record)
    return records


def fraud_rumor_row_to_record(row: dict[str, Any]) -> PublicRecord | None:
    serial = _clean(row.get("編號"))
    title = _clean(row.get("標題"))
    if not title:
        return None
    published_text = _clean(row.get("發佈時間"))
    content = _clean(row.get("發佈內容"))
    occurred_at = parse_npa_datetime(published_text)
    record_id = "npa:fraud_rumor:" + stable_id(serial, title, published_text)
    return PublicRecord(
        record_id=record_id,
        source_id="npa",
        record_type="fraud_rumor",
        country="TW",
        category="society",
        title=title,
        url=FRAUD_RUMOR_DATASET_URL,
        occurred_at=occurred_at,
        region="TW",
        metrics={"content_length": len(content)} if content else {},
        tags=["165", "fraud"],
        raw={
            "dataset_url": FRAUD_RUMOR_DATASET_URL,
            "download_url": FRAUD_RUMOR_DOWNLOAD_URL,
            "serial": serial,
            "published_at_text": published_text,
            "content": content,
        },
    )


def parse_traffic_a1_payload(payload: str | bytes) -> list[PublicRecord]:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("NPA traffic A1 JSON parse failed prefix=%r", text[:80])
        return []
    result = data.get("result") if isinstance(data, dict) else None
    rows = result.get("records") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        return []
    return [
        record
        for group in group_traffic_accident_rows([row for row in rows if isinstance(row, dict)])
        for record in [traffic_accident_group_to_record(group)]
        if record is not None
    ]


def parse_traffic_a2_zip_stats(payload: bytes, *, download_url: str | None = None) -> list[PublicRecord]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        rows: list[dict[str, Any]] = []
        for name in archive.namelist():
            if not name.lower().endswith(".json"):
                continue
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("NPA traffic A2 JSON parse failed file=%s prefix=%r", name, text[:80])
                continue
            result = parsed.get("result") if isinstance(parsed, dict) else None
            items = result.get("records") if isinstance(result, dict) else None
            if isinstance(items, list):
                rows.extend(row for row in items if isinstance(row, dict))
    return traffic_rows_to_monthly_stats(
        rows,
        record_type="traffic_accident_a2_stat",
        dataset_url=TRAFFIC_A2_DATASET_URL,
        download_url=download_url,
        accident_class="A2",
    )


def traffic_rows_to_monthly_stats(
    rows: list[dict[str, Any]],
    *,
    record_type: str,
    dataset_url: str,
    download_url: str | None = None,
    accident_class: str,
) -> list[PublicRecord]:
    stats: dict[tuple[int, int, str], dict[str, Any]] = defaultdict(
        lambda: {
            "accident_count": 0,
            "death_count": 0,
            "injury_count": 0,
            "party_count": 0,
            "cause_counts": Counter(),
        }
    )
    for group in group_traffic_accident_rows(rows):
        first = group.rows[0] if group.rows else {}
        occurred = parse_traffic_datetime(_clean(first.get("發生日期")), _clean(first.get("發生時間")))
        if occurred is None:
            continue
        region = region_from_location(_clean(first.get("發生地點"))) or "TW"
        deaths, injuries = parse_casualties(_clean(first.get("死亡受傷人數")))
        cause = _clean(first.get("肇因研判子類別名稱-主要")) or "未分類"
        key = (occurred.year, occurred.month, region)
        bucket = stats[key]
        bucket["accident_count"] += 1
        bucket["death_count"] += deaths or 0
        bucket["injury_count"] += injuries or 0
        bucket["party_count"] += len(group.rows)
        bucket["cause_counts"][cause] += 1

    records: list[PublicRecord] = []
    for (year, month, region), bucket in stats.items():
        occurred_at = _month_end(year, month)
        top_causes = [
            {"cause": cause, "count": count}
            for cause, count in bucket["cause_counts"].most_common(5)
        ]
        metrics = {
            "year": year,
            "month": month,
            "accident_count": bucket["accident_count"],
            "death_count": bucket["death_count"],
            "injury_count": bucket["injury_count"],
            "party_count": bucket["party_count"],
        }
        title = (
            f"{year}-{month:02d} {region} {accident_class}交通事故統計："
            f"{bucket['accident_count']}件、死亡{bucket['death_count']}人、受傷{bucket['injury_count']}人"
        )
        records.append(
            PublicRecord(
                record_id="npa:" + record_type + ":" + stable_id(str(year), str(month), region),
                source_id="npa",
                record_type=record_type,
                country="TW",
                category="society",
                title=title,
                url=dataset_url,
                occurred_at=occurred_at,
                region=region,
                metrics=metrics,
                tags=["traffic_accident", accident_class, "stats"],
                raw={
                    "dataset_url": dataset_url,
                    "download_url": download_url,
                    "accident_class": accident_class,
                    "top_causes": top_causes,
                },
            )
        )
    return records


def merge_traffic_stat_records(left: PublicRecord, right: PublicRecord) -> PublicRecord:
    metrics = dict(left.metrics)
    for key in ("accident_count", "death_count", "injury_count", "party_count"):
        metrics[key] = int(metrics.get(key) or 0) + int(right.metrics.get(key) or 0)
    title = (
        f"{metrics.get('year')}-{int(metrics.get('month') or 0):02d} {left.region} A2交通事故統計："
        f"{metrics['accident_count']}件、死亡{metrics['death_count']}人、受傷{metrics['injury_count']}人"
    )
    raw = dict(left.raw)
    raw["merged_download_urls"] = [
        url
        for url in [
            left.raw.get("download_url"),
            right.raw.get("download_url"),
        ]
        if url
    ]
    return PublicRecord(
        record_id=left.record_id,
        source_id=left.source_id,
        record_type=left.record_type,
        country=left.country,
        category=left.category,
        title=title,
        url=left.url,
        occurred_at=left.occurred_at,
        region=left.region,
        metrics=metrics,
        tags=left.tags,
        raw=raw,
    )


def parse_drunk_driving_stats_csv(payload: str | bytes) -> list[PublicRecord]:
    text = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, bytes) else payload
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    records: list[PublicRecord] = []
    for row in rows:
        year = parse_roc_year_label(_clean(row.get("year")))
        if year is None:
            continue
        a1_count = _to_int(row.get("A1-count"))
        a2_count = _to_int(row.get("A2-count"))
        dead = _to_int(row.get("dead"))
        a1_hurt = _to_int(row.get("A1-hurt"))
        a2_hurt = _to_int(row.get("A2-hurt"))
        metrics = {
            "year": year,
            "a1_count": a1_count,
            "a2_count": a2_count,
            "dead_count": dead,
            "a1_injury_count": a1_hurt,
            "a2_injury_count": a2_hurt,
            "total_accident_count": (a1_count or 0) + (a2_count or 0),
            "total_injury_count": (a1_hurt or 0) + (a2_hurt or 0),
        }
        records.append(
            PublicRecord(
                record_id="npa:traffic_drunk_driving_stat:" + stable_id(str(year)),
                source_id="npa",
                record_type="traffic_drunk_driving_stat",
                country="TW",
                category="society",
                title=(
                    f"{year}年酒駕肇事統計：A1 {a1_count or 0}件、"
                    f"A2 {a2_count or 0}件、死亡{dead or 0}人"
                ),
                url=DRUNK_DRIVING_DATASET_URL,
                occurred_at=_month_end(year, 12),
                region="TW",
                metrics={key: value for key, value in metrics.items() if value is not None},
                tags=["traffic_accident", "drunk_driving", "stats"],
                raw={
                    "dataset_url": DRUNK_DRIVING_DATASET_URL,
                    "download_url": DRUNK_DRIVING_DOWNLOAD_URL,
                    "row": row,
                },
            )
        )
    return records


def parse_fraud_enforcement_stats_csv(payload: str | bytes) -> list[PublicRecord]:
    text = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, bytes) else payload
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    records: list[PublicRecord] = []
    for row in rows:
        year = parse_roc_year_number(_clean(row.get("年度")))
        month = _to_int(row.get("月"))
        if year is None or month is None or not 1 <= month <= 12:
            continue
        group_count = _to_int(row.get("查緝不法犯罪集團團數")) or 0
        suspect_count = _to_int(row.get("查緝不法犯罪集團人數")) or 0
        seized_amount = _to_int(row.get("查扣不法所得金額")) or 0
        blocked_amount = _to_int(row.get("攔阻金額")) or 0
        records.append(
            PublicRecord(
                record_id="npa:fraud_enforcement_stat:" + stable_id(str(year), str(month)),
                source_id="npa",
                record_type="fraud_enforcement_stat",
                country="TW",
                category="society",
                title=(
                    f"{year}-{month:02d} 打詐執行成效："
                    f"查緝{group_count}團、{suspect_count}人、攔阻{blocked_amount}元"
                ),
                url=FRAUD_ENFORCEMENT_DATASET_URL,
                occurred_at=_month_end(year, month),
                region="TW",
                metrics={
                    "year": year,
                    "month": month,
                    "criminal_group_count": group_count,
                    "suspect_count": suspect_count,
                    "seized_illegal_proceeds": seized_amount,
                    "blocked_amount": blocked_amount,
                },
                tags=["fraud", "anti_fraud", "stats"],
                raw={
                    "dataset_url": FRAUD_ENFORCEMENT_DATASET_URL,
                    "download_url": FRAUD_ENFORCEMENT_DOWNLOAD_URL,
                    "row": row,
                },
            )
        )
    return records


def parse_fraud_blocked_domain_stats_csv(payload: str | bytes) -> list[PublicRecord]:
    text = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, bytes) else payload
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    buckets: dict[tuple[int, int, str], dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "domains": [], "law_basis": Counter(), "request_units": Counter()}
    )
    for row in rows:
        year_month = parse_roc_year_month(_clean(row.get("民國年月")))
        domain = _clean(row.get("網域"))
        nature = _clean(row.get("網站性質")) or "未分類"
        if year_month is None or not domain:
            continue
        year, month = year_month
        bucket = buckets[(year, month, nature)]
        bucket["count"] += 1
        if len(bucket["domains"]) < 10:
            bucket["domains"].append(domain)
        law = _clean(row.get("法律依據"))
        unit = _clean(row.get("聲請單位"))
        if law:
            bucket["law_basis"][law] += 1
        if unit:
            bucket["request_units"][unit] += 1

    records: list[PublicRecord] = []
    for (year, month, nature), bucket in buckets.items():
        records.append(
            PublicRecord(
                record_id="npa:fraud_blocked_domain_stat:" + stable_id(str(year), str(month), nature),
                source_id="npa",
                record_type="fraud_blocked_domain_stat",
                country="TW",
                category="society",
                title=f"{year}-{month:02d} 涉詐網站停止解析統計：{nature} {bucket['count']}個網域",
                url=FRAUD_BLOCKED_DOMAIN_DATASET_URL,
                occurred_at=_month_end(year, month),
                region="TW",
                metrics={
                    "year": year,
                    "month": month,
                    "blocked_domain_count": bucket["count"],
                },
                tags=["fraud", "blocked_domain", "stats", nature],
                raw={
                    "dataset_url": FRAUD_BLOCKED_DOMAIN_DATASET_URL,
                    "download_url": FRAUD_BLOCKED_DOMAIN_DOWNLOAD_URL,
                    "sample_domains": bucket["domains"],
                    "law_basis": dict(bucket["law_basis"]),
                    "request_units": dict(bucket["request_units"]),
                },
            )
        )
    return records


def group_traffic_accident_rows(rows: list[dict[str, Any]]) -> list[TrafficAccidentGroup]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            _clean(row.get("發生日期")),
            _clean(row.get("發生時間")),
            _clean(row.get("發生地點")),
            _clean(row.get("事故類別名稱")),
        )
        if not key[0] or not key[2]:
            continue
        grouped.setdefault(key, []).append(row)
    return [TrafficAccidentGroup(key=key, rows=value) for key, value in grouped.items()]


def traffic_accident_group_to_record(group: TrafficAccidentGroup) -> PublicRecord | None:
    first = group.rows[0] if group.rows else {}
    date_text, time_text, location, accident_type = group.key
    occurred_at = parse_traffic_datetime(date_text, time_text)
    region = region_from_location(location)
    casualties = _clean(first.get("死亡受傷人數"))
    deaths, injuries = parse_casualties(casualties)
    latitude = _to_float(first.get("緯度"))
    longitude = _to_float(first.get("經度"))
    record_id = "npa:traffic_accident_a1:" + stable_id(date_text, time_text, location, accident_type)
    metrics: dict[str, Any] = {
        "death_count": deaths,
        "injury_count": injuries,
        "party_count": len(group.rows),
    }
    if latitude is not None:
        metrics["latitude"] = latitude
    if longitude is not None:
        metrics["longitude"] = longitude

    title_suffix = f" ({casualties})" if casualties else ""
    return PublicRecord(
        record_id=record_id,
        source_id="npa",
        record_type="traffic_accident_a1",
        country="TW",
        category="society",
        title=f"A1 traffic accident: {location}{title_suffix}",
        url=TRAFFIC_A1_DATASET_URL,
        occurred_at=occurred_at,
        region=region,
        metrics={key: value for key, value in metrics.items() if value is not None},
        tags=["traffic_accident", "A1"],
        raw={
            "dataset_url": TRAFFIC_A1_DATASET_URL,
            "download_url": TRAFFIC_A1_DOWNLOAD_URL,
            "date": date_text,
            "time": time_text,
            "location": location,
            "accident_type": accident_type,
            "casualties": casualties,
            "main_cause": _clean(first.get("肇因研判子類別名稱-主要")),
            "rows": group.rows,
        },
    )


def parse_npa_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=_TAIPEI)
        except ValueError:
            continue
    return None


def parse_traffic_datetime(date_text: str, time_text: str) -> datetime | None:
    if not date_text or not date_text.isdigit():
        return None
    text = date_text + (time_text or "000000").zfill(6)[:6]
    try:
        return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=_TAIPEI)
    except ValueError:
        return None


def parse_casualties(value: str) -> tuple[int | None, int | None]:
    deaths = _extract_count(value, "死亡")
    injuries = _extract_count(value, "受傷")
    return deaths, injuries


def region_from_location(value: str) -> str | None:
    text = _clean(value)
    match = re.match(r"([\u4e00-\u9fff]{2,3}[縣市])", text)
    return match.group(1) if match else None


def parse_roc_year_label(value: str) -> int | None:
    match = re.search(r"(\d{2,3})", value or "")
    return parse_roc_year_number(match.group(1)) if match else None


def parse_roc_year_number(value: str) -> int | None:
    text = _clean(value)
    if not text.isdigit():
        return None
    year = int(text)
    return year + 1911 if year < 1911 else year


def parse_roc_year_month(value: str) -> tuple[int, int] | None:
    text = re.sub(r"\D", "", value or "")
    if len(text) < 4:
        return None
    roc_year = int(text[:-2])
    month = int(text[-2:])
    if not 1 <= month <= 12:
        return None
    year = parse_roc_year_number(str(roc_year))
    if year is None:
        return None
    return year, month


def _extract_count(value: str, label: str) -> int | None:
    match = re.search(label + r"\s*(\d+)", value or "")
    return int(match.group(1)) if match else None


def _to_float(value: Any) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _month_end(year: int, month: int) -> datetime:
    day = monthrange(year, month)[1]
    return datetime(year, month, day, 23, 59, 59, tzinfo=_TAIPEI)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _http_get_text_with_ski_fallback(url: str, *, timeout: int) -> str:
    try:
        return http_get_text(url, timeout=timeout, verify_ssl=True)
    except Exception as exc:
        if "missing subject key identifier" not in str(exc).lower():
            raise
        logger.info("NPA source retry without SSL verification url=%s reason=missing_ski", url)
        return http_get_text(url, timeout=timeout, verify_ssl=False)


def _http_get_bytes_with_ski_fallback(url: str, *, timeout: int) -> bytes:
    try:
        return http_get_bytes(url, timeout=timeout, verify_ssl=True)
    except Exception as exc:
        if "missing subject key identifier" not in str(exc).lower():
            raise
        logger.info("NPA source retry without SSL verification url=%s reason=missing_ski", url)
        return http_get_bytes(url, timeout=timeout, verify_ssl=False)
