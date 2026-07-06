"""Central Weather Administration public-record adapters."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from news_platform.http_client import http_get_text
from news_platform.models import PublicRecord
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))
_CWA_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}"
_CWA_PORTAL_URL = "https://opendata.cwa.gov.tw/"
_DEFAULT_EARTHQUAKE_DATASET_ID = "E-A0015-001"
_DEFAULT_TYPHOON_DATASET_ID = "W-C0034-005"


class CwaEarthquakeReportSource:
    source_id = "cwa"
    record_type = "cwa_earthquake_report"
    category = "society"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        dataset_id: str | None = None,
        authorization: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.dataset_id = dataset_id or os.getenv("CWA_EARTHQUAKE_DATASET_ID", _DEFAULT_EARTHQUAKE_DATASET_ID)
        self.authorization = authorization or _cwa_authorization()
        self.name = "cwa:earthquake_report"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        payload = _fetch_cwa_json(
            self.dataset_id,
            authorization=self.authorization,
            timeout=self.timeout_seconds,
        )
        records = parse_earthquake_payload(payload, dataset_id=self.dataset_id)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return records[: max(1, int(limit))] if limit is not None else records


class CwaTyphoonReportSource:
    source_id = "cwa"
    record_type = "cwa_typhoon_report"
    category = "society"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        dataset_id: str | None = None,
        authorization: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.dataset_id = dataset_id or os.getenv("CWA_TYPHOON_DATASET_ID", _DEFAULT_TYPHOON_DATASET_ID)
        self.authorization = authorization or _cwa_authorization()
        self.name = "cwa:typhoon_report"

    def fetch(self, *, limit: int | None = None, **_: Any) -> list[PublicRecord]:
        payload = _fetch_cwa_json(
            self.dataset_id,
            authorization=self.authorization,
            timeout=self.timeout_seconds,
        )
        records = parse_typhoon_payload(payload, dataset_id=self.dataset_id)
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return records[: max(1, int(limit))] if limit is not None else records


def parse_earthquake_payload(payload: dict[str, Any], *, dataset_id: str) -> list[PublicRecord]:
    output: list[PublicRecord] = []
    for event in _collect_dicts(payload.get("records", payload), _looks_like_earthquake):
        info = _dict_value(event, "EarthquakeInfo", "earthquakeInfo")
        epicenter = _dict_value(info, "Epicenter", "epicenter")
        magnitude = _dict_value(info, "EarthquakeMagnitude", "earthquakeMagnitude")
        report_content = _text_value(event, "ReportContent", "reportContent", "Content", "content")
        origin_time = _text_value(info, "OriginTime", "originTime") or _text_value(event, "OriginTime", "originTime")
        title = report_content or _earthquake_title(event, info, epicenter, magnitude)
        occurred_at = _parse_taipei_datetime(origin_time) or _first_datetime(event)
        earthquake_no = _text_value(event, "EarthquakeNo", "earthquakeNo")
        report_url = _text_value(event, "Web", "web", "ReportImageURI", "reportImageURI")
        region = _text_value(epicenter, "Location", "location") or _text_value(event, "Location", "location")

        output.append(
            PublicRecord(
                record_id="cwa:earthquake:" + (earthquake_no or stable_id(dataset_id, title, origin_time)),
                source_id="cwa",
                record_type="cwa_earthquake_report",
                country="TW",
                title=_clean_text(title) or "中央氣象署地震報告",
                url=report_url or _CWA_PORTAL_URL,
                occurred_at=occurred_at,
                category="society",
                region=_clean_text(region),
                metrics={
                    "magnitude": _number_value(magnitude, "MagnitudeValue", "magnitudeValue"),
                    "depth_km": _number_value(info, "FocalDepth", "focalDepth"),
                    "latitude": _number_value(epicenter, "EpicenterLatitude", "epicenterLatitude"),
                    "longitude": _number_value(epicenter, "EpicenterLongitude", "epicenterLongitude"),
                },
                tags=["weather", "earthquake"],
                raw={"dataset_id": dataset_id, "source": "cwa", "event": event},
            )
        )
    return _dedupe(output)


def parse_typhoon_payload(payload: dict[str, Any], *, dataset_id: str) -> list[PublicRecord]:
    output: list[PublicRecord] = []
    for event in _collect_dicts(payload.get("records", payload), _looks_like_typhoon):
        cwa_name = _text_value(event, "CwaTyphoonName", "cwaTyphoonName")
        english_name = _text_value(event, "TyphoonName", "typhoonName")
        title = _text_value(
            event,
            "ReportContent",
            "reportContent",
            "Content",
            "content",
            "cwaTyphoonName",
            "CwaTyphoonName",
            "TyphoonName",
            "typhoonName",
            "Name",
            "name",
            "Title",
            "title",
        )
        occurred_text = _text_value(
            event,
            "ReportTime",
            "reportTime",
            "IssueTime",
            "issueTime",
            "ValidTime",
            "validTime",
            "UpdateTime",
            "updateTime",
            "StartTime",
            "startTime",
        )
        occurred_at = _parse_taipei_datetime(occurred_text) or _first_datetime(event)
        report_url = _text_value(event, "Web", "web", "URL", "url", "ReportImageURI", "reportImageURI")
        region = _text_value(event, "Location", "location", "Area", "area", "SeaArea", "seaArea")
        clean_title = _clean_text(title) or "中央氣象署颱風資訊"
        if cwa_name and english_name and cwa_name != english_name:
            clean_title = f"{cwa_name}（{english_name}）"

        output.append(
            PublicRecord(
                record_id="cwa:typhoon:" + stable_id(dataset_id, clean_title, occurred_text),
                source_id="cwa",
                record_type="cwa_typhoon_report",
                country="TW",
                title=clean_title,
                url=report_url or _CWA_PORTAL_URL,
                occurred_at=occurred_at,
                category="society",
                region=_clean_text(region),
                metrics={},
                tags=["weather", "typhoon"],
                raw={"dataset_id": dataset_id, "source": "cwa", "event": event},
            )
        )
    return _dedupe(output)


def _fetch_cwa_json(dataset_id: str, *, authorization: str | None, timeout: int) -> dict[str, Any]:
    if not authorization:
        logger.warning("CWA authorization is not configured")
        return {}
    try:
        text = http_get_text(
            _CWA_API_URL.format(dataset_id=dataset_id),
            params={"Authorization": authorization, "format": "JSON"},
            timeout=timeout,
        )
        data = json.loads(text)
    except Exception as exc:
        logger.warning("CWA fetch failed dataset_id=%s error=%s", dataset_id, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _cwa_authorization() -> str:
    return os.getenv("CWA_AUTHORIZATION") or os.getenv("CWA_API_KEY") or ""


def _collect_dicts(value: Any, predicate) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if predicate(value):
            found.append(value)
        for child in value.values():
            found.extend(_collect_dicts(child, predicate))
    elif isinstance(value, list):
        for child in value:
            found.extend(_collect_dicts(child, predicate))
    return found


def _looks_like_earthquake(value: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in value}
    return "earthquakeno" in keys or ("reportcontent" in keys and "earthquakeinfo" in keys)


def _looks_like_typhoon(value: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in value}
    if {"dataid", "note"}.issubset(keys):
        return False
    if {"typhoonname", "cwatyphoonname"} & keys:
        return True
    if {"reportcontent", "content", "title", "name"} & keys:
        return any(isinstance(item, str) and "颱風" in item for item in value.values())
    return False


def _dict_value(value: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for key in keys:
        child = value.get(key)
        if isinstance(child, dict):
            return child
    return {}


def _text_value(value: Any, *keys: str) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        child = value.get(key)
        if isinstance(child, (str, int, float)):
            text = str(child).strip()
            if text:
                return text
    return ""


def _number_value(value: Any, *keys: str) -> float | None:
    text = _text_value(value, *keys)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_datetime(value: Any) -> datetime | None:
    if isinstance(value, dict):
        for child in value.values():
            dt = _first_datetime(child)
            if dt:
                return dt
    elif isinstance(value, list):
        for child in value:
            dt = _first_datetime(child)
            if dt:
                return dt
    elif isinstance(value, str):
        return _parse_taipei_datetime(value)
    return None


def _parse_taipei_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_TAIPEI).astimezone(timezone.utc)
        except ValueError:
            pass
    match = re.search(r"(\d{2,4})[-/年](\d{1,2})[-/月](\d{1,2}).{0,3}(\d{1,2})[:時](\d{1,2})", text)
    if not match:
        return None
    year_text, month, day, hour, minute = match.groups()
    year = int(year_text)
    if year < 100:
        year += 1911 if year > 30 else 2000
    try:
        return datetime(year, int(month), int(day), int(hour), int(minute), tzinfo=_TAIPEI).astimezone(timezone.utc)
    except ValueError:
        return None


def _earthquake_title(
    event: dict[str, Any],
    info: dict[str, Any],
    epicenter: dict[str, Any],
    magnitude: dict[str, Any],
) -> str:
    magnitude_value = _text_value(magnitude, "MagnitudeValue", "magnitudeValue")
    location = _text_value(epicenter, "Location", "location")
    origin_time = _text_value(info, "OriginTime", "originTime")
    parts = ["中央氣象署地震報告"]
    if magnitude_value:
        parts.append(f"規模 {magnitude_value}")
    if location:
        parts.append(location)
    if origin_time:
        parts.append(origin_time)
    report_type = _text_value(event, "ReportType", "reportType")
    if report_type:
        parts.append(report_type)
    return " | ".join(parts)


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _dedupe(records: list[PublicRecord]) -> list[PublicRecord]:
    seen: set[str] = set()
    output: list[PublicRecord] = []
    for record in records:
        if record.record_id in seen:
            continue
        seen.add(record.record_id)
        output.append(record)
    return output
