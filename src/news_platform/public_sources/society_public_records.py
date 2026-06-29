"""Society issue public-record adapters."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from news_platform.http_client import http_get_text
from news_platform.models import PublicRecord
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))

BIRTH_TOPIC_ID = "low_birthrate"
DRUG_TOPIC_ID = "drug_abuse"

RIS_BIRTH_MONTHLY_DATASET_URL = "https://data.gov.tw/dataset/77140"
RIS_BIRTH_MONTHLY_API_URL = "https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP010/{roc_year_month}"

NPA_DRUG_CASE_DATASET_URL = "https://data.gov.tw/dataset/57268"
NPA_DRUG_CASE_FALLBACK_DOWNLOAD_URLS = (
    "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
    "6333357F-4AC9-48F5-B723-6B1CF5586E79/resource/"
    "1E037B19-C735-4397-864C-C1AAEA4BAF32/download",
)


class RisBirthMonthlyStatsSource:
    source_id = "ris"
    record_type = "ris_birth_monthly_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20, months: int = 18) -> None:
        self.timeout_seconds = timeout_seconds
        self.months = months
        self.name = "ris:birth_monthly_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        records: list[PublicRecord] = []
        for roc_year_month in _recent_roc_year_months(self.months):
            rows = self._fetch_month_rows(roc_year_month)
            records.extend(birth_month_rows_to_records(rows, dataset_url=RIS_BIRTH_MONTHLY_DATASET_URL))
            if limit is not None and len(records) >= limit:
                return records[: max(1, int(limit))]
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return records

    def _fetch_month_rows(self, roc_year_month: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                payload = http_get_text(
                    RIS_BIRTH_MONTHLY_API_URL.format(roc_year_month=roc_year_month),
                    params={"page": page},
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:
                logger.info("RIS birth monthly fetch skipped month=%s page=%s error=%s", roc_year_month, page, exc)
                return rows
            data = json.loads(payload)
            if data.get("responseCode") != "OD-0101-S":
                return rows
            rows.extend(data.get("responseData") or [])
            if page >= int(data.get("totalPage") or 1):
                return rows
            page += 1


class NpaDrugCaseStatsSource:
    source_id = "npa"
    record_type = "npa_drug_case_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 20, max_files: int = 4) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_files = max_files
        self.name = "npa:drug_case_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        records_by_id: dict[str, PublicRecord] = {}
        effective_files = 0
        for url in self._download_urls():
            try:
                payload = http_get_text(url, timeout=self.timeout_seconds)
            except Exception as exc:
                logger.warning("NPA drug case fetch failed url=%s error=%s", url, exc)
                continue
            records = parse_npa_drug_case_csv(payload, download_url=url)
            if not records:
                continue
            effective_files += 1
            for record in records:
                records_by_id[record.record_id] = record
            if effective_files >= self.max_files:
                break
        records = sorted(
            records_by_id.values(),
            key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return records[: max(1, int(limit))] if limit is not None else records

    def _download_urls(self) -> list[str]:
        try:
            page = http_get_text(NPA_DRUG_CASE_DATASET_URL, timeout=self.timeout_seconds)
        except Exception:
            return list(NPA_DRUG_CASE_FALLBACK_DOWNLOAD_URLS)
        urls = re.findall(r"https://opdadm\.moi\.gov\.tw[^\"'<> ]+/download", page)
        return list(dict.fromkeys([*NPA_DRUG_CASE_FALLBACK_DOWNLOAD_URLS, *urls]))


def birth_month_rows_to_records(rows: list[dict[str, Any]], *, dataset_url: str) -> list[PublicRecord]:
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        region = _region_from_site(row.get("site_id"))
        if not region:
            continue
        values = {
            "birth_total": _int(row.get("birth_total")),
            "birth_total_m": _int(row.get("birth_total_m")),
            "birth_total_f": _int(row.get("birth_total_f")),
            "death_total": _int(row.get("death_total")),
            "death_m": _int(row.get("death_m")),
            "death_f": _int(row.get("death_f")),
            "marry_pair": _int(row.get("marry_pair")),
            "divorce_pair": _int(row.get("divorce_pair")),
        }
        for key, value in values.items():
            groups[region][key] += value
            groups["全國"][key] += value

    roc_year_month = _clean(rows[0].get("statistic_yyymm")) if rows else ""
    year_month = _parse_roc_year_month(roc_year_month)
    if year_month is None:
        return []
    year, month = year_month
    occurred_at = _month_end(year, month)

    return [
        PublicRecord(
            record_id=f"ris:birth_monthly_stat:{stable_id(str(year), str(month), region)}",
            source_id=RisBirthMonthlyStatsSource.source_id,
            record_type=RisBirthMonthlyStatsSource.record_type,
            country="TW",
            category=RisBirthMonthlyStatsSource.category,
            title=f"{year}-{month:02d} {region}戶籍出生數 {metrics['birth_total']} 人，死亡 {metrics['death_total']} 人",
            url=dataset_url,
            occurred_at=occurred_at,
            region=region,
            metrics=dict(metrics),
            tags=[BIRTH_TOPIC_ID, "birth_statistics", "population"],
            raw={"dataset_url": dataset_url, "roc_year_month": roc_year_month},
        )
        for region, metrics in groups.items()
    ]


def parse_npa_drug_case_csv(payload: str | bytes, *, download_url: str) -> list[PublicRecord]:
    text = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, bytes) else payload
    groups: dict[tuple[int, int, str], dict[str, Any]] = defaultdict(
        lambda: {"case_ids": set(), "suspects": 0, "weight_g": 0.0, "school_cases": 0, "kinds": Counter()}
    )
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        parsed_date = _parse_drug_case_date(_clean(row.get("oc_dt")))
        if parsed_date is None:
            continue
        year, month = parsed_date
        region = _region_from_location(row.get("oc_addr")) or "未知"
        group = groups[(year, month, region)]
        group["case_ids"].add(_clean(row.get("no")) or stable_id(str(year), str(month), _clean(row.get("oc_addr"))))
        group["suspects"] += _int(row.get("proc_no"))
        group["weight_g"] += _float(row.get("weight_g"))
        kind = _clean(row.get("kind")) or "未知品項"
        group["kinds"][kind] += 1
        if "學校" in " ".join(_clean(row.get(key)) for key in ("oc_p1", "oc_p2", "oc_p3", "oc_addr")):
            group["school_cases"] += 1

    records: list[PublicRecord] = []
    for (year, month, region), metrics in groups.items():
        top_kinds = metrics["kinds"].most_common(5)
        top_kind = top_kinds[0][0] if top_kinds else "未知品項"
        case_count = len(metrics["case_ids"])
        records.append(
            PublicRecord(
                record_id=f"npa:drug_case_stat:{stable_id(str(year), str(month), region)}",
                source_id=NpaDrugCaseStatsSource.source_id,
                record_type=NpaDrugCaseStatsSource.record_type,
                country="TW",
                category=NpaDrugCaseStatsSource.category,
                title=f"{year}-{month:02d} {region}毒品案件統計：{case_count} 件，主要品項 {top_kind}",
                url=NPA_DRUG_CASE_DATASET_URL,
                occurred_at=_month_end(year, month),
                region=region,
                metrics={
                    "case_count": case_count,
                    "suspect_count": metrics["suspects"],
                    "net_weight_g": round(metrics["weight_g"], 4),
                    "school_case_count": metrics["school_cases"],
                    "top_kinds": [{"kind": kind, "count": count} for kind, count in top_kinds],
                },
                tags=[DRUG_TOPIC_ID, "drug_case", "campus_drug"],
                raw={"dataset_url": NPA_DRUG_CASE_DATASET_URL, "download_url": download_url},
            )
        )
    return records


def _recent_roc_year_months(months: int) -> list[str]:
    today = datetime.now(_TAIPEI).date().replace(day=1)
    values = []
    for offset in range(months):
        year = today.year
        month = today.month - offset
        while month <= 0:
            year -= 1
            month += 12
        values.append(f"{year - 1911:03d}{month:02d}")
    return values


def _parse_roc_year_month(value: str) -> tuple[int, int] | None:
    if not re.fullmatch(r"\d{5}", value):
        return None
    year, month = int(value[:3]) + 1911, int(value[3:5])
    return (year, month) if 1 <= month <= 12 else None


def _parse_drug_case_date(value: str) -> tuple[int, int] | None:
    if re.fullmatch(r"\d{8}", value):
        year, month = int(value[:4]), int(value[4:6])
    elif re.fullmatch(r"\d{7}", value):
        year, month = int(value[:3]) + 1911, int(value[3:5])
    else:
        return None
    return (year, month) if 1 <= month <= 12 else None


def _month_end(year: int, month: int) -> datetime:
    return datetime(year, month, monthrange(year, month)[1], 23, 59, 59, tzinfo=_TAIPEI)


def _region_from_site(value: Any) -> str | None:
    return _region_from_location(value)


def _region_from_location(value: Any) -> str | None:
    match = re.match(r"([\u4e00-\u9fff]{2,3}[市縣])", _clean(value))
    return match.group(1) if match else None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").replace("\xa0", " ").split()).strip()


def _int(value: Any) -> int:
    try:
        return int(float(_clean(value).replace(",", "") or 0))
    except ValueError:
        return 0


def _float(value: Any) -> float:
    try:
        return float(_clean(value).replace(",", "") or 0)
    except ValueError:
        return 0.0
