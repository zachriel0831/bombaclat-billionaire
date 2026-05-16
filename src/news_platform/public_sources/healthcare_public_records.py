"""Healthcare public-record adapters for Taiwan official sources."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import zipfile
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from news_platform.http_client import http_get_bytes, http_get_text
from news_platform.models import PublicRecord
from news_platform.public_sources.ly_legislative_bill import LegislativeBillSource
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))

HEALTHCARE_TOPIC_ID = "healthcare_burden"

NHI_NURSING_DATASET_URL = "https://data.gov.tw/dataset/174661"
NHI_NURSING_DOWNLOAD_URL = "https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D2100J-001"
NHI_NURSING_METADATA_URL = "https://info.nhi.gov.tw/api/iode0010/v1/rest/dataset/A21030000I-D2100J"

NHI_BED_OCCUPANCY_DATASET_URL = "https://data.gov.tw/dataset/79622"
NHI_BED_OCCUPANCY_DOWNLOAD_URL = "https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D21008-003"
NHI_BED_OCCUPANCY_METADATA_URL = "https://info.nhi.gov.tw/api/iode0010/v1/rest/dataset/A21030000I-D21008"

MOHW_HOSPITAL_WORKFORCE_DATASET_URL = "https://data.gov.tw/dataset/6474"
MOHW_CLINIC_WORKFORCE_DATASET_URL = "https://data.gov.tw/dataset/6476"
MOHW_HOSPITAL_BEDS_DATASET_URL = "https://data.gov.tw/dataset/6473"

MOHW_NURSING_STAFF_DATASET_URL = "https://data.gov.tw/dataset/118549"
MOHW_NURSING_STAFF_DOWNLOAD_URL = (
    "https://www.opendata.mohw.gov.tw/dataset/opendata/nh/118549/"
    "%E8%BF%915%E5%B9%B4%E8%AD%B7%E7%90%86%E4%BA%BA%E5%93%A1%E7%B5%B1%E8%A8%88.csv"
)

HEALTHCARE_BILL_KEYWORDS = (
    "醫療法",
    "護理人員法",
    "全民健康保險法",
    "長期照顧服務法",
    "長照服務法",
    "醫療事故預防及爭議處理法",
    "醫師法",
    "護病比",
    "護理待遇",
    "護理津貼",
    "護理人員待遇",
    "夜班獎勵",
    "急診",
    "醫護",
    "醫事人員",
    "護理人力",
)


@dataclass(frozen=True)
class MohwAnnualSpec:
    name: str
    source_id: str
    record_type: str
    dataset_url: str
    data_file_prefix: str
    facility_field: str
    title_label: str
    metric_fields: tuple[tuple[str, str], ...]
    tags: tuple[str, ...]


HOSPITAL_WORKFORCE_SPEC = MohwAnnualSpec(
    name="mohw:hospital_workforce_stat",
    source_id="mohw",
    record_type="mohw_hospital_workforce_stat",
    dataset_url=MOHW_HOSPITAL_WORKFORCE_DATASET_URL,
    data_file_prefix="hos_personnel_",
    facility_field="醫院家數",
    title_label="醫院人力",
    metric_fields=(
        ("醫事人員總計", "medical_staff_count"),
        ("西醫師", "western_physician_count"),
        ("中醫師", "chinese_medicine_physician_count"),
        ("牙醫師", "dentist_count"),
        ("護理師", "registered_nurse_count"),
        ("護士", "licensed_practical_nurse_count"),
        ("藥師", "pharmacist_count"),
    ),
    tags=("hospital_workforce", "medical_staff"),
)

CLINIC_WORKFORCE_SPEC = MohwAnnualSpec(
    name="mohw:clinic_workforce_stat",
    source_id="mohw",
    record_type="mohw_clinic_workforce_stat",
    dataset_url=MOHW_CLINIC_WORKFORCE_DATASET_URL,
    data_file_prefix="clinic_personnel_",
    facility_field="診所家數",
    title_label="診所人力",
    metric_fields=HOSPITAL_WORKFORCE_SPEC.metric_fields,
    tags=("clinic_workforce", "medical_staff"),
)

HOSPITAL_BEDS_SPEC = MohwAnnualSpec(
    name="mohw:hospital_bed_stat",
    source_id="mohw",
    record_type="mohw_hospital_bed_stat",
    dataset_url=MOHW_HOSPITAL_BEDS_DATASET_URL,
    data_file_prefix="hos_bed",
    facility_field="醫院家數",
    title_label="醫院病床",
    metric_fields=(
        ("病床總計", "bed_count"),
        ("急性一般病床", "acute_general_bed_count"),
        ("精神急性一般病床", "acute_psychiatric_bed_count"),
        ("慢性一般病床", "chronic_general_bed_count"),
        ("精神慢性一般病床", "chronic_psychiatric_bed_count"),
        ("加護病床", "icu_bed_count"),
        ("急診觀察床", "emergency_observation_bed_count"),
        ("負壓隔離病床", "negative_pressure_isolation_bed_count"),
    ),
    tags=("hospital_beds", "medical_capacity"),
)


class NhiHospitalNursingStaffSource:
    source_id = "nhi"
    record_type = "nhi_hospital_nursing_staff_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "nhi:hospital_nursing_staff_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_bytes_with_ski_fallback(NHI_NURSING_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("NHI nursing staff fetch failed error=%s", exc)
            return []
        records = parse_nhi_hospital_nursing_staff_csv(payload)
        records.sort(key=_record_sort_key, reverse=True)
        return _limit(records, limit)


class NhiHospitalBedOccupancySource:
    source_id = "nhi"
    record_type = "nhi_hospital_bed_occupancy_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "nhi:hospital_bed_occupancy_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_bytes_with_ski_fallback(NHI_BED_OCCUPANCY_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("NHI bed occupancy fetch failed error=%s", exc)
            return []
        records = parse_nhi_bed_occupancy_ods(payload)
        records.sort(key=_record_sort_key, reverse=True)
        return _limit(records, limit)


class MohwAnnualHealthcareStatsSource:
    category = "society"

    def __init__(self, spec: MohwAnnualSpec, *, timeout_seconds: int = 30) -> None:
        self.spec = spec
        self.source_id = spec.source_id
        self.record_type = spec.record_type
        self.timeout_seconds = timeout_seconds
        self.name = spec.name

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            html = _http_get_text_with_ski_fallback(self.spec.dataset_url, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("MOHW healthcare page fetch failed source=%s error=%s", self.name, exc)
            return []
        urls = extract_mohw_download_urls(html, self.spec.dataset_url)
        records: list[PublicRecord] = []
        for url in urls:
            try:
                payload = _http_get_bytes_with_ski_fallback(url, timeout=self.timeout_seconds)
            except Exception as exc:
                logger.warning("MOHW healthcare download failed source=%s url=%s error=%s", self.name, url, exc)
                continue
            records.extend(parse_mohw_annual_zip(payload, self.spec, download_url=url))
        records.sort(key=_record_sort_key, reverse=True)
        return _limit(records, limit)


class MohwHospitalWorkforceSource(MohwAnnualHealthcareStatsSource):
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        super().__init__(HOSPITAL_WORKFORCE_SPEC, timeout_seconds=timeout_seconds)


class MohwClinicWorkforceSource(MohwAnnualHealthcareStatsSource):
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        super().__init__(CLINIC_WORKFORCE_SPEC, timeout_seconds=timeout_seconds)


class MohwHospitalBedsSource(MohwAnnualHealthcareStatsSource):
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        super().__init__(HOSPITAL_BEDS_SPEC, timeout_seconds=timeout_seconds)


class MohwNursingStaffStatsSource:
    source_id = "mohw"
    record_type = "mohw_nursing_staff_stat"
    category = "society"

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds
        self.name = "mohw:nursing_staff_stat"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        try:
            payload = _http_get_bytes_with_ski_fallback(MOHW_NURSING_STAFF_DOWNLOAD_URL, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("MOHW nursing staff stats fetch failed error=%s", exc)
            return []
        records = parse_mohw_nursing_staff_csv(payload)
        records.sort(key=_record_sort_key, reverse=True)
        return _limit(records, limit)


class HealthcareLegislativeBillSource:
    source_id = "ly"
    record_type = "healthcare_legislative_bill"
    category = "society"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        lookback_days: int = 365,
        keywords: tuple[str, ...] = HEALTHCARE_BILL_KEYWORDS,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.lookback_days = max(1, int(lookback_days))
        self.keywords = keywords
        self.name = "ly:healthcare_legislative_bill"
        self._base = LegislativeBillSource(
            timeout_seconds=timeout_seconds,
            lookback_days=self.lookback_days,
        )

    def fetch(self, *, limit: int | None = None, **kwargs: Any) -> list[PublicRecord]:
        records = self._base.fetch(limit=None, **kwargs)
        filtered = []
        for record in records:
            terms = matched_healthcare_bill_terms(record, self.keywords)
            if terms:
                filtered.append(healthcare_bill_record_from_base(record, terms))
        filtered.sort(key=_record_sort_key, reverse=True)
        return _limit(filtered, limit)


def parse_nhi_hospital_nursing_staff_csv(payload: str | bytes) -> list[PublicRecord]:
    rows = _read_csv_rows(payload)
    buckets: dict[tuple[int, int, str], dict[str, Any]] = defaultdict(
        lambda: {
            "hospital_count": 0,
            "practicing_nurse_count": 0,
            "support_nurse_count": 0,
            "sample_hospitals": [],
        }
    )
    for row in rows:
        year_month = parse_roc_year_month(_get(row, "統計年月", "STS_YM"))
        area = _clean(_get(row, "縣市別", "AREA_NAME"))
        if year_month is None or not area:
            continue
        year, month = year_month
        practicing = _to_int(_get(row, "當月執業登記人數", "PRSN_QTY")) or 0
        support = _to_int(_get(row, "當月報備支援人數", "PRSN_PT_QTY")) or 0
        hospital_id = _clean(_get(row, "醫事機構代碼", "HOSP_ID"))
        hospital_name = _clean(_get(row, "醫事機構簡稱", "HOSP_ABBR"))
        bucket = buckets[(year, month, area)]
        bucket["hospital_count"] += 1
        bucket["practicing_nurse_count"] += practicing
        bucket["support_nurse_count"] += support
        if len(bucket["sample_hospitals"]) < 10:
            bucket["sample_hospitals"].append(
                {
                    "hospital_id": hospital_id,
                    "hospital_name": hospital_name,
                    "practicing_nurse_count": practicing,
                    "support_nurse_count": support,
                }
            )

    records: list[PublicRecord] = []
    for (year, month, area), bucket in buckets.items():
        metrics = {
            "year": year,
            "month": month,
            "hospital_count": bucket["hospital_count"],
            "practicing_nurse_count": bucket["practicing_nurse_count"],
            "support_nurse_count": bucket["support_nurse_count"],
        }
        records.append(
            PublicRecord(
                record_id="nhi:hospital_nursing_staff_stat:" + stable_id(str(year), str(month), area),
                source_id="nhi",
                record_type="nhi_hospital_nursing_staff_stat",
                country="TW",
                category="society",
                title=(
                    f"{year}-{month:02d} {area} 特約醫院護理人力："
                    f"執業登記 {metrics['practicing_nurse_count']} 人、"
                    f"報備支援 {metrics['support_nurse_count']} 人"
                ),
                url=NHI_NURSING_DATASET_URL,
                occurred_at=_month_end(year, month),
                region=area,
                metrics=metrics,
                tags=[HEALTHCARE_TOPIC_ID, "nursing_staff", "monthly", "nhi"],
                raw={
                    "dataset_url": NHI_NURSING_DATASET_URL,
                    "metadata_url": NHI_NURSING_METADATA_URL,
                    "download_url": NHI_NURSING_DOWNLOAD_URL,
                    "sample_hospitals": bucket["sample_hospitals"],
                },
            )
        )
    return records


def parse_nhi_bed_occupancy_ods(payload: bytes) -> list[PublicRecord]:
    rows = _read_ods_rows(payload)
    if not rows:
        return []
    year = _extract_year_from_text(" ".join(" ".join(row) for row in rows[:3])) or datetime.now(_TAIPEI).year
    records: list[PublicRecord] = []
    current_contract_type = ""
    for row in rows:
        cells = [_clean(cell) for cell in row]
        if not cells or cells[0] in {"", "特約類別"}:
            continue
        first = cells[0]
        if first.endswith("醫院") or first == "醫學中心":
            current_contract_type = first
            hospital_id = cells[1] if len(cells) > 1 else ""
            hospital_name = cells[2] if len(cells) > 2 else ""
            rate_cells = cells[3:7]
        elif first.isdigit():
            hospital_id = first
            hospital_name = cells[1] if len(cells) > 1 else ""
            rate_cells = cells[2:6]
        else:
            continue
        if not hospital_id or not hospital_name:
            continue
        rates = [_to_rate(value) for value in rate_cells]
        metrics = {
            "year": year,
            "contract_type": current_contract_type,
            "acute_general_bed_occupancy_rate": rates[0] if len(rates) > 0 else None,
            "acute_psychiatric_bed_occupancy_rate": rates[1] if len(rates) > 1 else None,
            "chronic_general_bed_occupancy_rate": rates[2] if len(rates) > 2 else None,
            "chronic_psychiatric_bed_occupancy_rate": rates[3] if len(rates) > 3 else None,
        }
        metrics = {key: value for key, value in metrics.items() if value not in (None, "")}
        records.append(
            PublicRecord(
                record_id="nhi:hospital_bed_occupancy_stat:" + stable_id(str(year), hospital_id),
                source_id="nhi",
                record_type="nhi_hospital_bed_occupancy_stat",
                country="TW",
                category="society",
                title=f"{year} {hospital_name} 四類病床平均占床率",
                url=NHI_BED_OCCUPANCY_DATASET_URL,
                occurred_at=_month_end(year, 12),
                region="TW",
                metrics=metrics,
                tags=[HEALTHCARE_TOPIC_ID, "bed_occupancy", "nhi"],
                raw={
                    "dataset_url": NHI_BED_OCCUPANCY_DATASET_URL,
                    "metadata_url": NHI_BED_OCCUPANCY_METADATA_URL,
                    "download_url": NHI_BED_OCCUPANCY_DOWNLOAD_URL,
                    "hospital_id": hospital_id,
                    "hospital_name": hospital_name,
                    "contract_type": current_contract_type,
                },
            )
        )
    return records


def extract_mohw_download_urls(html: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for match in re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.IGNORECASE):
        url = urljoin(base_url, match)
        if "mohw.gov.tw/dl-" not in url:
            continue
        if url not in urls:
            urls.append(url)
    return urls


def parse_mohw_annual_zip(payload: bytes, spec: MohwAnnualSpec, *, download_url: str) -> list[PublicRecord]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        logger.warning("MOHW annual stats payload is not zip source=%s url=%s", spec.name, download_url)
        return []
    with archive:
        data_name = _find_zip_entry(archive.namelist(), spec.data_file_prefix)
        mapping_name = _find_mapping_entry(archive.namelist())
        if not data_name:
            return []
        data_text = _decode_bytes(archive.read(data_name))
        mapping = parse_township_mapping_csv(_decode_bytes(archive.read(mapping_name))) if mapping_name else {}
    roc_year = _extract_roc_year(data_name)
    year = parse_roc_year_number(str(roc_year)) if roc_year is not None else None
    if year is None:
        return []
    rows = list(csv.DictReader(io.StringIO(data_text.lstrip("\ufeff"))))
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"rows": 0, "metrics": defaultdict(int)})
    for row in rows:
        code = _clean(row.get("鄉鎮市區碼"))
        town_name = mapping.get(code, {}).get("old" if roc_year and roc_year <= 102 else "new", "")
        region = county_from_township(town_name) or "TW"
        bucket = buckets[region]
        bucket["rows"] += 1
        bucket["metrics"]["facility_count"] += _to_int(row.get(spec.facility_field)) or 0
        for source_field, metric_name in spec.metric_fields:
            bucket["metrics"][metric_name] += _to_int(row.get(source_field)) or 0

    records: list[PublicRecord] = []
    for region, bucket in buckets.items():
        metrics = {"year": year, "township_count": bucket["rows"], **dict(bucket["metrics"])}
        nurse_total = (metrics.get("registered_nurse_count") or 0) + (
            metrics.get("licensed_practical_nurse_count") or 0
        )
        if nurse_total:
            metrics["nursing_staff_count"] = nurse_total
        main_value = metrics.get("bed_count") or metrics.get("medical_staff_count") or metrics.get("facility_count") or 0
        records.append(
            PublicRecord(
                record_id=f"{spec.source_id}:{spec.record_type}:" + stable_id(str(year), region),
                source_id=spec.source_id,
                record_type=spec.record_type,
                country="TW",
                category="society",
                title=f"{year} {region} {spec.title_label}統計：{main_value}",
                url=spec.dataset_url,
                occurred_at=_month_end(year, 12),
                region=region,
                metrics=metrics,
                tags=[HEALTHCARE_TOPIC_ID, *spec.tags, "mohw", "annual"],
                raw={
                    "dataset_url": spec.dataset_url,
                    "download_url": download_url,
                    "data_file": data_name,
                    "township_mapping_file": mapping_name,
                    "roc_year": roc_year,
                },
            )
        )
    return records


def parse_township_mapping_csv(text: str) -> dict[str, dict[str, str]]:
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    output: dict[str, dict[str, str]] = {}
    for row in rows:
        code = _clean(row.get("鄉鎮市區碼"))
        if not code:
            continue
        output[code] = {
            "old": _clean(row.get("鄉鎮市區名稱(101、102年適用)")),
            "new": _clean(row.get("鄉鎮市區名稱(103年以後適用)")),
        }
    return output


def parse_mohw_nursing_staff_csv(payload: str | bytes) -> list[PublicRecord]:
    records: list[PublicRecord] = []
    for row in _read_csv_rows(payload):
        year = _to_int(_get(row, "年度"))
        if year is None:
            continue
        metrics = {
            "year": year,
            "licensed_nursing_staff_count": _to_int(_get(row, "護理人員領證人數(累計)")),
            "licensed_male_count": _to_int(_get(row, "護理人員領證人數(累計)男性")),
            "licensed_female_count": _to_int(_get(row, "護理人員領證人數(累計)女性")),
            "nursing_staff_per_10000_population": _to_float(_get(row, "每萬人口護理人員數(人)")),
        }
        metrics = {key: value for key, value in metrics.items() if value is not None}
        records.append(
            PublicRecord(
                record_id="mohw:nursing_staff_stat:" + stable_id(str(year)),
                source_id="mohw",
                record_type="mohw_nursing_staff_stat",
                country="TW",
                category="society",
                title=f"{year} 全國護理人員領證統計：{metrics.get('licensed_nursing_staff_count', 0)} 人",
                url=MOHW_NURSING_STAFF_DATASET_URL,
                occurred_at=_month_end(year, 12),
                region="TW",
                metrics=metrics,
                tags=[HEALTHCARE_TOPIC_ID, "nursing_staff", "mohw", "annual"],
                raw={
                    "dataset_url": MOHW_NURSING_STAFF_DATASET_URL,
                    "download_url": MOHW_NURSING_STAFF_DOWNLOAD_URL,
                    "row": row,
                },
            )
        )
    return records


def matched_healthcare_bill_terms(record: PublicRecord, keywords: tuple[str, ...] = HEALTHCARE_BILL_KEYWORDS) -> list[str]:
    raw_text = json.dumps(record.raw, ensure_ascii=False)
    text = f"{record.title} {raw_text}"
    return [keyword for keyword in keywords if keyword in text]


def healthcare_bill_record_from_base(record: PublicRecord, matched_terms: list[str]) -> PublicRecord:
    raw = dict(record.raw)
    raw["base_record_type"] = record.record_type
    raw["topic_ids"] = [HEALTHCARE_TOPIC_ID]
    raw["matched_healthcare_terms"] = matched_terms
    tags = _dedupe([HEALTHCARE_TOPIC_ID, "healthcare_bill", *record.tags, *matched_terms])
    return PublicRecord(
        record_id="ly:healthcare_legislative_bill:" + stable_id(record.record_id),
        source_id="ly",
        record_type="healthcare_legislative_bill",
        country=record.country,
        category="society",
        title=record.title,
        url=record.url,
        occurred_at=record.occurred_at,
        region=record.region,
        metrics={**record.metrics, "matched_healthcare_term_count": len(matched_terms)},
        tags=tags,
        raw=raw,
    )


def parse_roc_year_month(value: Any) -> tuple[int, int] | None:
    text = re.sub(r"\D", "", _clean(value))
    if len(text) < 4:
        return None
    roc_year = int(text[:-2])
    month = int(text[-2:])
    if not 1 <= month <= 12:
        return None
    year = parse_roc_year_number(str(roc_year))
    return (year, month) if year is not None else None


def parse_roc_year_number(value: str) -> int | None:
    text = _clean(value)
    if not text.isdigit():
        return None
    year = int(text)
    return year + 1911 if year < 1911 else year


def county_from_township(value: str) -> str | None:
    text = _clean(value)
    return text[:3] if len(text) >= 3 else None


def _read_csv_rows(payload: str | bytes) -> list[dict[str, Any]]:
    text = _decode_bytes(payload) if isinstance(payload, bytes) else payload
    return [row for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))) if isinstance(row, dict)]


def _read_ods_rows(payload: bytes) -> list[list[str]]:
    table_ns = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            xml_payload = archive.read("content.xml")
    except Exception as exc:
        logger.warning("ODS parse failed: %s", exc)
        return []
    root = ET.fromstring(xml_payload)
    rows: list[list[str]] = []
    ns = {"table": table_ns}
    for row in root.findall(".//table:table-row", ns):
        values: list[str] = []
        for cell in row.findall("table:table-cell", ns):
            repeat = int(cell.attrib.get(f"{{{table_ns}}}number-columns-repeated", "1") or "1")
            text = _clean("".join(cell.itertext()))
            values.extend([text] * min(repeat, 20))
        if any(values):
            rows.append(values)
    return rows


def _decode_bytes(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _find_zip_entry(names: list[str], prefix: str) -> str | None:
    for name in names:
        base = name.rsplit("/", 1)[-1]
        if base.startswith(prefix) and base.lower().endswith(".csv"):
            return name
    return None


def _find_mapping_entry(names: list[str]) -> str | None:
    for name in names:
        if "欄位" in name and name.lower().endswith(".csv"):
            return name
    return None


def _extract_roc_year(value: str) -> int | None:
    match = re.search(r"(\d{3})", value or "")
    return int(match.group(1)) if match else None


def _extract_year_from_text(value: str) -> int | None:
    match = re.search(r"(\d{2,4})年", value or "")
    if not match:
        return None
    return parse_roc_year_number(match.group(1))


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
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    text = _clean(value).replace(",", "")
    if not text:
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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = _clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _http_get_text_with_ski_fallback(url: str, *, timeout: int) -> str:
    try:
        return http_get_text(url, timeout=timeout, verify_ssl=True)
    except Exception as exc:
        if "missing subject key identifier" not in str(exc).lower():
            raise
        logger.info("Healthcare source retry without SSL verification url=%s reason=missing_ski", url)
        return http_get_text(url, timeout=timeout, verify_ssl=False)


def _http_get_bytes_with_ski_fallback(url: str, *, timeout: int) -> bytes:
    try:
        return http_get_bytes(url, timeout=timeout, verify_ssl=True)
    except Exception as exc:
        if "missing subject key identifier" not in str(exc).lower():
            raise
        logger.info("Healthcare source retry without SSL verification url=%s reason=missing_ski", url)
        return http_get_bytes(url, timeout=timeout, verify_ssl=False)
