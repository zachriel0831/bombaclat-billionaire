from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, RelayEvent


logger = logging.getLogger(__name__)

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SOURCE = "market_context:bls_macro"
SOURCE_FAMILY = "bls_macro"
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class BlsSeriesSpec:
    slug: str
    series_id: str
    name: str
    category: str
    unit: str
    seasonal_adjustment: str
    frequency: str = "monthly"
    notes: str = ""


@dataclass(frozen=True)
class BlsMacroConfig:
    env_file: str
    api_key: str | None
    timeout_seconds: int
    series_ids: list[str]
    dry_run: bool = False


@dataclass(frozen=True)
class BlsObservation:
    series_id: str
    year: str
    period: str
    period_name: str
    value: str
    value_float: float | None
    footnotes: list[dict[str, Any]]
    latest: bool
    raw: dict[str, Any]


@dataclass(frozen=True)
class BlsMacroPoint:
    spec: BlsSeriesSpec
    observation: BlsObservation
    previous_observation: BlsObservation | None
    year_ago_observation: BlsObservation | None
    normalized_metrics: dict[str, Any]


class BlsApiError(RuntimeError):
    """Raised when the BLS API returns a non-success response."""


BLS_SERIES: tuple[BlsSeriesSpec, ...] = (
    BlsSeriesSpec(
        slug="cpi_headline",
        series_id="CUSR0000SA0",
        name="CPI-U all items, U.S. city average",
        category="cpi_headline",
        unit="index 1982-84=100",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="cpi_core",
        series_id="CUSR0000SA0L1E",
        name="CPI-U all items less food and energy, U.S. city average",
        category="cpi_core",
        unit="index 1982-84=100",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="ppi_headline_all_commodities",
        series_id="WPU00000000",
        name="PPI all commodities",
        category="ppi_headline",
        unit="index 1982=100",
        seasonal_adjustment="not_seasonally_adjusted",
        notes="Broad PPI commodity headline series.",
    ),
    BlsSeriesSpec(
        slug="ppi_final_demand",
        series_id="WPSFD4",
        name="PPI final demand",
        category="ppi_final_demand",
        unit="index Nov 2009=100",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="ppi_core_final_demand",
        series_id="WPSFD49116",
        name="PPI final demand less foods, energy, and trade services",
        category="ppi_core",
        unit="index Aug 2013=100",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="nonfarm_payrolls",
        series_id="CES0000000001",
        name="All employees, total nonfarm",
        category="employment",
        unit="thousands of persons",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="unemployment_rate",
        series_id="LNS14000000",
        name="Civilian unemployment rate",
        category="employment_rate",
        unit="percent",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="labor_force_participation",
        series_id="LNS11300000",
        name="Labor force participation rate",
        category="labor_force",
        unit="percent",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="average_hourly_earnings",
        series_id="CES0500000003",
        name="Average hourly earnings of all employees, total private",
        category="earnings",
        unit="USD per hour",
        seasonal_adjustment="seasonally_adjusted",
    ),
    BlsSeriesSpec(
        slug="average_weekly_hours",
        series_id="CES0500000002",
        name="Average weekly hours of all employees, total private",
        category="hours",
        unit="hours",
        seasonal_adjustment="seasonally_adjusted",
    ),
)

BLS_SERIES_BY_ID: dict[str, BlsSeriesSpec] = {spec.series_id: spec for spec in BLS_SERIES}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect BLS macro data and store it as event-only facts in t_relay_events")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="BLS API timeout")
    parser.add_argument(
        "--series",
        default="",
        help="Optional comma-separated BLS series ids. Defaults to the first-batch mapping in this module.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and build events without writing MySQL")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_config(args: argparse.Namespace) -> BlsMacroConfig:
    load_settings(args.env_file)
    requested = str(os.getenv("BLS_SERIES_IDS") or args.series or "").strip()
    if requested:
        series_ids = [item.strip().upper() for item in requested.split(",") if item.strip()]
    else:
        series_ids = [spec.series_id for spec in BLS_SERIES]
    unknown = [series_id for series_id in series_ids if series_id not in BLS_SERIES_BY_ID]
    if unknown:
        raise ValueError(f"Unknown BLS series id(s): {', '.join(unknown)}")

    api_key = (os.getenv("BLS_API_KEY") or "").strip() or None
    return BlsMacroConfig(
        env_file=args.env_file,
        api_key=api_key,
        timeout_seconds=max(5, int(os.getenv("BLS_TIMEOUT_SECONDS") or args.timeout_seconds)),
        series_ids=series_ids,
        dry_run=bool(args.dry_run),
    )


def _build_bls_payload(series_ids: list[str], api_key: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"seriesid": list(series_ids)}
    if api_key:
        payload["registrationkey"] = api_key
    return payload


def _post_bls_payload(payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        BLS_API_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "news-collector/0.1 bls-macro",
        },
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise BlsApiError(f"BLS API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise BlsApiError(f"BLS API request failed: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BlsApiError(f"BLS API returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BlsApiError("BLS API returned a non-object JSON payload")
    return data


def fetch_bls_response(config: BlsMacroConfig) -> dict[str, Any]:
    payload = _build_bls_payload(config.series_ids, config.api_key)
    logger.info(
        "Fetching BLS macro series: count=%d api_key_configured=%s",
        len(config.series_ids),
        bool(config.api_key),
    )
    return _post_bls_payload(payload, config.timeout_seconds)


def parse_bls_response(payload: dict[str, Any], specs: dict[str, BlsSeriesSpec] | None = None) -> list[BlsMacroPoint]:
    _raise_for_bls_error(payload)
    spec_map = specs or BLS_SERIES_BY_ID
    points: list[BlsMacroPoint] = []
    # BLS 一次回多條 series；每條先挑最新月資料，再回推上月與去年同月，
    # 把分析最常用的 MoM / YoY 指標先算好。
    for series in _extract_series(payload):
        series_id = str(series.get("seriesID") or series.get("series_id") or "").strip().upper()
        if not series_id:
            continue
        spec = spec_map.get(series_id)
        if spec is None:
            continue
        observations = _parse_observations(series_id, series.get("data"))
        latest = select_latest_observation(observations)
        if latest is None:
            logger.warning("BLS series has no monthly observations: %s", series_id)
            continue
        previous = _previous_observation(observations, latest)
        year_ago = _year_ago_observation(observations, latest)
        metrics = _normalized_metrics(latest, previous, year_ago, spec)
        points.append(
            BlsMacroPoint(
                spec=spec,
                observation=latest,
                previous_observation=previous,
                year_ago_observation=year_ago,
                normalized_metrics=metrics,
            )
        )
    return points


def _raise_for_bls_error(payload: dict[str, Any]) -> None:
    status = str(payload.get("status") or "").strip()
    if not status or status == "REQUEST_SUCCEEDED":
        return
    messages = payload.get("message")
    if isinstance(messages, list):
        detail = "; ".join(str(item) for item in messages if str(item).strip())
    else:
        detail = str(messages or "").strip()
    raise BlsApiError(f"BLS API status={status}: {detail or 'no message'}")


def _extract_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("Results")
    series_entries: list[Any] = []
    if isinstance(results, dict):
        series_entries.extend(results.get("series") or [])
    elif isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                series_entries.extend(item.get("series") or [])

    return [entry for entry in series_entries if isinstance(entry, dict)]


def _parse_observations(series_id: str, data: Any) -> list[BlsObservation]:
    observations: list[BlsObservation] = []
    if not isinstance(data, list):
        return observations
    for row in data:
        if not isinstance(row, dict):
            continue
        year = str(row.get("year") or "").strip()
        period = str(row.get("period") or "").strip().upper()
        if _monthly_period_index(period) is None:
            continue
        value = str(row.get("value") or "").strip()
        footnotes = row.get("footnotes") if isinstance(row.get("footnotes"), list) else []
        observations.append(
            BlsObservation(
                series_id=series_id,
                year=year,
                period=period,
                period_name=str(row.get("periodName") or row.get("period_name") or "").strip(),
                value=value,
                value_float=_to_float(value),
                footnotes=[item for item in footnotes if isinstance(item, dict)],
                latest=str(row.get("latest") or "").strip().lower() == "true",
                raw=dict(row),
            )
        )
    return observations


def select_latest_observation(observations: list[BlsObservation]) -> BlsObservation | None:
    valid = [obs for obs in observations if _period_sort_key(obs) is not None]
    if not valid:
        return None
    # BLS 有時會標 latest=true，有時沒有；先優先吃 latest 標記，
    # 沒標記時再退回按年月排序最大的那筆。
    flagged = [obs for obs in valid if obs.latest]
    candidates = flagged or valid
    return max(candidates, key=lambda obs: _period_sort_key(obs) or (0, 0))


def _previous_observation(observations: list[BlsObservation], latest: BlsObservation) -> BlsObservation | None:
    sorted_obs = sorted(
        [obs for obs in observations if _period_sort_key(obs) is not None],
        key=lambda obs: _period_sort_key(obs) or (0, 0),
    )
    latest_key = _period_sort_key(latest)
    if latest_key is None:
        return None
    previous = [obs for obs in sorted_obs if (_period_sort_key(obs) or (0, 0)) < latest_key]
    return previous[-1] if previous else None


def _year_ago_observation(observations: list[BlsObservation], latest: BlsObservation) -> BlsObservation | None:
    try:
        target_year = str(int(latest.year) - 1)
    except ValueError:
        return None
    for obs in observations:
        if obs.year == target_year and obs.period == latest.period:
            return obs
    return None


def _normalized_metrics(
    latest: BlsObservation,
    previous: BlsObservation | None,
    year_ago: BlsObservation | None,
    spec: BlsSeriesSpec,
) -> dict[str, Any]:
    # 這裡把 period / year-over-year 指標預先算成結構化欄位，
    # 後面 market_analysis 就不必再用 prompt 重新做數學。
    value = latest.value_float
    previous_value = previous.value_float if previous else None
    year_ago_value = year_ago.value_float if year_ago else None
    period_change = _difference(value, previous_value)
    year_over_year_change = _difference(value, year_ago_value)
    return {
        "series_id": latest.series_id,
        "slug": spec.slug,
        "category": spec.category,
        "unit": spec.unit,
        "seasonal_adjustment": spec.seasonal_adjustment,
        "frequency": spec.frequency,
        "period_start": _period_start_iso(latest.year, latest.period),
        "value": value,
        "previous_period": _period_label(previous) if previous else None,
        "previous_value": previous_value,
        "period_change": period_change,
        "period_change_percent": _percent_change(value, previous_value),
        "year_ago_period": _period_label(year_ago) if year_ago else None,
        "year_ago_value": year_ago_value,
        "year_over_year_change": year_over_year_change,
        "year_over_year_percent": _percent_change(value, year_ago_value),
        "footnote_codes": _footnote_codes(latest.footnotes),
        "is_preliminary": _has_footnote_code(latest.footnotes, "P"),
    }


def build_bls_macro_events(points: list[BlsMacroPoint], generated_at: str) -> list[RelayEvent]:
    return [_point_to_event(point, generated_at) for point in points]


def _point_to_event(point: BlsMacroPoint, generated_at: str) -> RelayEvent:
    obs = point.observation
    spec = point.spec
    return RelayEvent(
        event_id=build_event_id(obs.series_id, obs.year, obs.period),
        source=SOURCE,
        title=_event_title(point),
        url=f"https://data.bls.gov/timeseries/{obs.series_id}",
        summary=_event_summary(point),
        published_at=point.normalized_metrics.get("period_start") or generated_at,
        log_only=False,
        raw={
            "stored_only": True,
            "dimension": "market_context",
            "event_type": "market_context_point",
            "source_family": SOURCE_FAMILY,
            "api_url": BLS_API_URL,
            "generated_at": generated_at,
            "series_id": obs.series_id,
            "series": asdict(spec),
            "year": obs.year,
            "period": obs.period,
            "periodName": obs.period_name,
            "value": obs.value,
            "footnotes": obs.footnotes,
            "latest": obs.latest,
            "normalized_metrics": point.normalized_metrics,
            "raw_observation": obs.raw,
        },
    )


def build_event_id(series_id: str, year: str, period: str) -> str:
    return f"market-context-{SOURCE_FAMILY}-{series_id.lower()}-{year}-{period.lower()}"


def _event_title(point: BlsMacroPoint) -> str:
    obs = point.observation
    return f"BLS {point.spec.name}: {obs.value} {point.spec.unit} ({obs.year}-{obs.period})"


def _event_summary(point: BlsMacroPoint) -> str:
    metrics = point.normalized_metrics
    parts = [
        f"category={point.spec.category}",
        f"series_id={point.observation.series_id}",
        f"period={point.observation.year}-{point.observation.period}",
        f"value={point.observation.value}",
        f"unit={point.spec.unit}",
    ]
    if metrics.get("period_change") is not None:
        parts.append(f"period_change={_format_number(metrics.get('period_change'))}")
    if metrics.get("year_over_year_percent") is not None:
        parts.append(f"yoy={metrics['year_over_year_percent']:+.2f}%")
    if metrics.get("is_preliminary"):
        parts.append("preliminary=true")
    return "; ".join(parts)


def collect_bls_macro(config: BlsMacroConfig) -> list[BlsMacroPoint]:
    payload = fetch_bls_response(config)
    return parse_bls_response(payload)


def run_once(config: BlsMacroConfig) -> dict[str, Any]:
    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled and not config.dry_run:
        raise RuntimeError("BLS macro collection requires RELAY_MYSQL_ENABLED=true")

    generated_at = datetime.now(timezone.utc).astimezone().isoformat()
    points = collect_bls_macro(config)
    events = build_bls_macro_events(points, generated_at)

    stored = 0
    duplicates = 0
    if not config.dry_run:
        store = MySqlEventStore(relay_settings)
        store.initialize()
        for event in events:
            if store.enqueue_event_if_new(event):
                stored += 1
            else:
                duplicates += 1

    missing_series = sorted(set(config.series_ids) - {point.observation.series_id for point in points})
    result = {
        "ok": True,
        "source": SOURCE,
        "series_requested": len(config.series_ids),
        "points": len(points),
        "events": len(events),
        "stored": stored,
        "duplicates": duplicates,
        "missing_series": missing_series,
        "dry_run": config.dry_run,
        "api_key_configured": bool(config.api_key),
    }
    logger.info(
        "BLS macro events built: points=%d events=%d stored=%d duplicates=%d missing=%d dry_run=%s",
        len(points),
        len(events),
        stored,
        duplicates,
        len(missing_series),
        config.dry_run,
    )
    return result


def _period_sort_key(obs: BlsObservation) -> tuple[int, int] | None:
    try:
        year = int(obs.year)
    except ValueError:
        return None
    month = _monthly_period_index(obs.period)
    if month is None:
        return None
    return year, month


def _monthly_period_index(period: str) -> int | None:
    if len(period) != 3 or not period.startswith("M"):
        return None
    try:
        month = int(period[1:])
    except ValueError:
        return None
    if 1 <= month <= 12:
        return month
    return None


def _period_start_iso(year: str, period: str) -> str | None:
    month = _monthly_period_index(period)
    if month is None:
        return None
    try:
        date_value = datetime(int(year), month, 1, tzinfo=timezone.utc)
    except ValueError:
        return None
    return date_value.isoformat()


def _period_label(obs: BlsObservation | None) -> str | None:
    if obs is None:
        return None
    return f"{obs.year}-{obs.period}"


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _difference(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in {None, 0}:
        return None
    return (current - previous) / previous * 100.0


def _format_number(value: Any) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:.4f}".rstrip("0").rstrip(".")


def _footnote_codes(footnotes: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("code") or "").strip() for item in footnotes if str(item.get("code") or "").strip()]


def _has_footnote_code(footnotes: list[dict[str, Any]], code: str) -> bool:
    target = code.strip().upper()
    return any(str(item.get("code") or "").strip().upper() == target for item in footnotes)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    try:
        config = _load_config(args)
        result = run_once(config)
        logger.info("BLS macro result: %s", result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        logger.error("BLS macro failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
