"""Legislative Yuan legal proposal API adapter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from news_platform.http_client import http_get_text
from news_platform.models import PublicRecord
from news_platform.utils import stable_id


logger = logging.getLogger(__name__)

API_URL = "https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx"
API_DOC_URL = "https://www.ly.gov.tw/Pages/List.aspx?nodeid=153"
_TAIPEI = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class LegislativeBillWindow:
    from_date: date
    to_date: date
    proposer: str = ""


class LegislativeBillSource:
    source_id = "ly"
    record_type = "legislative_bill"
    category = "politics"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        lookback_days: int = 14,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.lookback_days = max(1, int(lookback_days))
        self.name = "ly:legislative_bill"

    def default_window(self, today: date | None = None) -> LegislativeBillWindow:
        end = today or datetime.now(_TAIPEI).date()
        start = end - timedelta(days=self.lookback_days - 1)
        return LegislativeBillWindow(from_date=start, to_date=end)

    def fetch(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        proposer: str = "",
        limit: int | None = None,
    ) -> list[PublicRecord]:
        if from_date is None and to_date is None:
            window = self.default_window()
        else:
            end = to_date or datetime.now(_TAIPEI).date()
            start = from_date or (end - timedelta(days=self.lookback_days - 1))
            window = LegislativeBillWindow(from_date=start, to_date=end, proposer=proposer)
        params: dict[str, str] = {
            "from": to_roc_date(window.from_date),
            "to": to_roc_date(window.to_date),
            "mode": "json",
        }
        if proposer.strip():
            params["proposer"] = proposer.strip()

        try:
            # Public read-only official API. Some local Windows/OpenSSL builds
            # reject this certificate because the SKI extension is absent.
            payload = http_get_text(
                API_URL,
                params=params,
                timeout=self.timeout_seconds,
                verify_ssl=False,
            )
        except Exception as exc:
            logger.warning("Legislative bill fetch failed params=%s error=%s", params, exc)
            return []

        rows = parse_legislative_bill_payload(payload)
        records = [row_to_public_record(row, API_URL, params) for row in rows]
        records = [record for record in records if record is not None]
        records.sort(key=lambda r: r.occurred_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if limit is not None:
            records = records[: max(1, int(limit))]
        if not records:
            logger.warning("Legislative bill API returned no records params=%s", params)
        return records


def parse_legislative_bill_payload(payload: str | bytes) -> list[dict[str, Any]]:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    stripped = text.strip()
    if not stripped or stripped.startswith("日期錯誤"):
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        logger.warning("Legislative bill JSON parse failed prefix=%r", stripped[:80])
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("dataList")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def row_to_public_record(
    row: dict[str, Any],
    source_url: str = API_URL,
    params: dict[str, str] | None = None,
) -> PublicRecord | None:
    bill_name = _clean(row.get("billName"))
    proposal_date = _clean(row.get("date"))
    if not bill_name or not proposal_date:
        return None

    term = _clean(row.get("term"))
    session_period = _clean(row.get("sessionPeriod"))
    session_times = _clean(row.get("sessionTimes"))
    proposer = _clean(row.get("billProposer"))
    cosignatory = _clean(row.get("billCosignatory"))
    status = _clean(row.get("billStatus"))
    occurred_at = parse_roc_date(proposal_date)

    record_id = "ly:legislative_bill:" + stable_id(
        proposal_date,
        term,
        session_period,
        session_times,
        bill_name,
        proposer,
    )
    tags = [value for value in ["法律提案", f"第{term}屆" if term else "", proposer] if value]
    metrics = {
        "term": _to_int(term),
        "session_period": _to_int(session_period),
        "session_times": _to_int(session_times),
        "cosignatory_count": len(split_names(cosignatory)),
    }

    return PublicRecord(
        record_id=record_id,
        source_id="ly",
        record_type="legislative_bill",
        country="TW",
        category="politics",
        title=bill_name,
        url=source_url,
        occurred_at=occurred_at,
        region="TW",
        metrics={key: value for key, value in metrics.items() if value is not None},
        tags=tags,
        raw={
            "api_url": source_url,
            "api_doc_url": API_DOC_URL,
            "params": params or {},
            "date": proposal_date,
            "term": term,
            "sessionPeriod": session_period,
            "sessionTimes": session_times,
            "billName": bill_name,
            "billProposer": proposer,
            "billCosignatory": cosignatory,
            "billStatus": status,
            "proposers": split_names(proposer),
            "cosignatories": split_names(cosignatory),
        },
    )


def to_roc_date(value: date) -> str:
    return f"{value.year - 1911:03d}{value.month:02d}{value.day:02d}"


def parse_roc_date(value: str) -> datetime | None:
    text = _clean(value)
    if len(text) != 7 or not text.isdigit():
        return None
    year = int(text[:3]) + 1911
    month = int(text[3:5])
    day = int(text[5:7])
    try:
        return datetime(year, month, day, tzinfo=_TAIPEI)
    except ValueError:
        return None


def split_names(value: str) -> list[str]:
    return [part.strip() for part in _clean(value).split(";") if part.strip()]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _to_int(value: str) -> int | None:
    if not value or not value.isdigit():
        return None
    return int(value)
