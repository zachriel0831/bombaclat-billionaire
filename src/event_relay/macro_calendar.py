"""Collect official U.S. macro release dates for LINE reminder delivery.

This module fetches official release calendars for the high-impact U.S. macro
events that drive the platform's market briefs:

* BLS CPI
* BLS PPI
* BLS Employment Situation / nonfarm payrolls
* Census Advance Monthly Retail Trade

The rows are stored in ``t_macro_release_calendar`` as long-lived calendar
facts. They are not relay events and are not market-analysis prose. The Java
``line-relay-service`` reads this table and owns LINE delivery state.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import json
import logging
import os
import re
import sys
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from event_relay.config import load_env_file, load_settings


logger = logging.getLogger(__name__)

BLS_YEAR_URL_TEMPLATE = "https://www.bls.gov/schedule/{year}/home.htm"
CENSUS_RETAIL_URL = "https://www.census.gov/retail/release_schedule.html"
TAIPEI_TIMEZONE = timezone(timedelta(hours=8), "Asia/Taipei")
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_TABLE = "t_macro_release_calendar"

DATE_LINE_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
    r"([A-Za-z]+) (\d{1,2}), (\d{4})$"
)
TIME_LINE_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.IGNORECASE)
MONTH_YEAR_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"
)
RETAIL_COMBINED_ROW_RE = re.compile(
    r"^((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}) "
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})$"
)
DATE_SHORT_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}$"
)


@dataclass(frozen=True)
class MacroIndicatorSpec:
    indicator_code: str
    indicator_name: str
    source_id: str
    source_name: str
    importance: int
    release_prefixes: tuple[str, ...]
    focus: str
    higher_than_expected: str
    lower_than_expected: str


@dataclass(frozen=True)
class MacroRelease:
    source_id: str
    source_name: str
    indicator_code: str
    indicator_name: str
    period_label: str
    release_title: str
    release_at_utc: datetime
    release_at_taipei: datetime
    release_timezone: str
    importance: int
    source_url: str
    raw: dict[str, Any]

    @property
    def event_key(self) -> str:
        key = "|".join(
            [
                self.source_id.strip().lower(),
                self.indicator_code.strip().lower(),
                self.period_label.strip().lower(),
                self.release_at_utc.isoformat(),
            ]
        )
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    @property
    def reminder_date_taipei(self) -> date:
        return self.release_at_taipei.date() - timedelta(days=1)


@dataclass(frozen=True)
class MacroCalendarConfig:
    env_file: str
    bls_years: list[int]
    timeout_seconds: int
    dry_run: bool = False


@dataclass(frozen=True)
class MacroCalendarCollection:
    releases: list[MacroRelease]
    errors: list[str]


BLS_INDICATORS: tuple[MacroIndicatorSpec, ...] = (
    MacroIndicatorSpec(
        indicator_code="us_cpi",
        indicator_name="U.S. CPI",
        source_id="bls",
        source_name="U.S. Bureau of Labor Statistics",
        importance=5,
        release_prefixes=("Consumer Price Index for ",),
        focus="是否改變 Fed 降息預期與科技股估值壓力",
        higher_than_expected="AI / 科技股估值可能承壓",
        lower_than_expected="AI / 科技股偏利多，利率壓力下降",
    ),
    MacroIndicatorSpec(
        indicator_code="us_ppi",
        indicator_name="U.S. PPI",
        source_id="bls",
        source_name="U.S. Bureau of Labor Statistics",
        importance=4,
        release_prefixes=("Producer Price Index for ",),
        focus="企業成本壓力與後續 CPI 傳導",
        higher_than_expected="成本壓力升溫，利率預期偏鷹",
        lower_than_expected="成本壓力降溫，風險資產壓力下降",
    ),
    MacroIndicatorSpec(
        indicator_code="us_nonfarm_payrolls",
        indicator_name="U.S. Nonfarm Payrolls / Employment Situation",
        source_id="bls",
        source_name="U.S. Bureau of Labor Statistics",
        importance=5,
        release_prefixes=("Employment Situation for ",),
        focus="就業是否過熱、薪資壓力與 Fed 降息路徑",
        higher_than_expected="降息預期可能降溫，科技估值承壓",
        lower_than_expected="利率壓力下降，但需同步檢查衰退風險",
    ),
)

RETAIL_SPEC = MacroIndicatorSpec(
    indicator_code="us_retail_sales",
    indicator_name="U.S. Retail Sales",
    source_id="census_retail",
    source_name="U.S. Census Bureau",
    importance=4,
    release_prefixes=(),
    focus="美國消費力與企業營收動能",
    higher_than_expected="消費韌性強，利率可能維持偏高",
    lower_than_expected="消費降溫，利率壓力下降但需留意景氣放緩",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect official U.S. macro release calendar rows")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument(
        "--years",
        default="",
        help="Optional comma-separated BLS years. Defaults to current Taipei year and next year.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print rows without writing MySQL")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def load_config(args: argparse.Namespace) -> MacroCalendarConfig:
    load_env_file(args.env_file)
    raw_years = (os.getenv("MACRO_CALENDAR_BLS_YEARS") or args.years or "").strip()
    if raw_years:
        years = [int(part.strip()) for part in raw_years.split(",") if part.strip()]
    else:
        current_year = datetime.now(TAIPEI_TIMEZONE).year
        years = [current_year, current_year + 1]
    return MacroCalendarConfig(
        env_file=args.env_file,
        bls_years=sorted(set(years)),
        timeout_seconds=max(5, int(os.getenv("MACRO_CALENDAR_TIMEOUT_SECONDS") or args.timeout_seconds)),
        dry_run=bool(args.dry_run),
    )


def collect_macro_release_calendar(config: MacroCalendarConfig) -> MacroCalendarCollection:
    releases: list[MacroRelease] = []
    errors: list[str] = []

    for year in config.bls_years:
        source_url = BLS_YEAR_URL_TEMPLATE.format(year=year)
        try:
            html_text = fetch_text(source_url, timeout_seconds=config.timeout_seconds)
            releases.extend(parse_bls_schedule_html(html_text, source_url=source_url))
        except Exception as exc:  # noqa: BLE001
            message = f"BLS schedule fetch failed year={year}: {exc}"
            logger.warning(message)
            errors.append(message)

    try:
        html_text = fetch_text(CENSUS_RETAIL_URL, timeout_seconds=config.timeout_seconds)
        releases.extend(parse_census_retail_schedule_html(html_text, source_url=CENSUS_RETAIL_URL))
    except Exception as exc:  # noqa: BLE001
        message = f"Census retail schedule fetch failed: {exc}"
        logger.warning(message)
        errors.append(message)

    return MacroCalendarCollection(releases=dedupe_releases(releases), errors=errors)


def fetch_text(url: str, timeout_seconds: int) -> str:
    req = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "news-collector/0.1 macro-calendar",
        },
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc


def parse_bls_schedule_html(html_text: str, source_url: str) -> list[MacroRelease]:
    lines = html_text_lines(html_text)
    releases: list[MacroRelease] = []
    index = 0
    while index < len(lines):
        date_text = lines[index]
        if not DATE_LINE_RE.match(date_text):
            index += 1
            continue
        time_index = index + 1
        if time_index >= len(lines) or not TIME_LINE_RE.match(lines[time_index]):
            index += 1
            continue
        release_index = time_index + 1
        while release_index < len(lines) and lines[release_index] in {"Date", "Time", "Release"}:
            release_index += 1
        if release_index >= len(lines):
            break

        release_text = lines[release_index]
        consumed_index = release_index
        if release_index + 1 < len(lines) and lines[release_index + 1].startswith("for "):
            release_text = f"{release_text} {lines[release_index + 1]}"
            consumed_index = release_index + 1
        spec = match_bls_indicator(release_text)
        if spec is not None:
            release_dt = parse_source_datetime(date_text, lines[time_index])
            period_label = extract_period_label(release_text, spec)
            releases.append(
                build_release(
                    spec=spec,
                    period_label=period_label,
                    release_title=release_text,
                    release_dt=release_dt,
                    source_url=source_url,
                    raw_source="bls_annual_schedule",
                )
            )
        index = consumed_index + 1
    return releases


def parse_census_retail_schedule_html(html_text: str, source_url: str) -> list[MacroRelease]:
    lines = html_text_lines(html_text)
    section = extract_retail_section(lines)
    releases: list[MacroRelease] = []
    index = 0
    while index < len(section):
        line = section[index]
        combined = RETAIL_COMBINED_ROW_RE.match(line)
        if combined:
            period_label = combined.group(1)
            release_date_text = combined.group(2)
            releases.append(build_retail_release(period_label, release_date_text, source_url))
            index += 1
            continue

        if MONTH_YEAR_RE.match(line) and index + 1 < len(section) and DATE_SHORT_RE.match(section[index + 1]):
            releases.append(build_retail_release(line, section[index + 1], source_url))
            index += 2
            continue
        index += 1
    return releases


def build_retail_release(period_label: str, release_date_text: str, source_url: str) -> MacroRelease:
    release_date = datetime.strptime(release_date_text, "%B %d, %Y").date()
    release_dt = datetime.combine(release_date, time(8, 30), tzinfo=eastern_timezone_for_date(release_date))
    release_title = f"Advance Monthly Retail Trade Report for {period_label}"
    return build_release(
        spec=RETAIL_SPEC,
        period_label=period_label,
        release_title=release_title,
        release_dt=release_dt,
        source_url=source_url,
        raw_source="census_retail_release_schedule",
    )


def build_release(
    spec: MacroIndicatorSpec,
    period_label: str,
    release_title: str,
    release_dt: datetime,
    source_url: str,
    raw_source: str,
) -> MacroRelease:
    release_at_utc = release_dt.astimezone(timezone.utc)
    release_at_taipei = release_dt.astimezone(TAIPEI_TIMEZONE)
    return MacroRelease(
        source_id=spec.source_id,
        source_name=spec.source_name,
        indicator_code=spec.indicator_code,
        indicator_name=spec.indicator_name,
        period_label=period_label,
        release_title=release_title,
        release_at_utc=release_at_utc,
        release_at_taipei=release_at_taipei,
        release_timezone="America/New_York",
        importance=spec.importance,
        source_url=source_url,
        raw={
            "collector": "macro_calendar",
            "source": raw_source,
            "source_url": source_url,
            "source_timezone": "America/New_York",
            "indicator_code": spec.indicator_code,
            "focus": spec.focus,
            "higher_than_expected": spec.higher_than_expected,
            "lower_than_expected": spec.lower_than_expected,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def match_bls_indicator(release_text: str) -> MacroIndicatorSpec | None:
    for spec in BLS_INDICATORS:
        if any(release_text.startswith(prefix) for prefix in spec.release_prefixes):
            return spec
    return None


def extract_period_label(release_text: str, spec: MacroIndicatorSpec) -> str:
    for prefix in spec.release_prefixes:
        if release_text.startswith(prefix):
            return release_text[len(prefix):].strip()
    return ""


def parse_source_datetime(date_text: str, time_text: str) -> datetime:
    parsed_date = datetime.strptime(date_text, "%A, %B %d, %Y").date()
    parsed_time = datetime.strptime(time_text.upper(), "%I:%M %p").time()
    return datetime.combine(parsed_date, parsed_time, tzinfo=eastern_timezone_for_date(parsed_date))


def eastern_timezone_for_date(day: date) -> timezone:
    """Return U.S. Eastern offset for a release date using current DST rules."""
    dst_start = nth_weekday_of_month(day.year, 3, 6, 2)
    dst_end = nth_weekday_of_month(day.year, 11, 6, 1)
    if dst_start <= day < dst_end:
        return timezone(timedelta(hours=-4), "America/New_York")
    return timezone(timedelta(hours=-5), "America/New_York")


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    days_until_weekday = (weekday - first.weekday()) % 7
    return first + timedelta(days=days_until_weekday + 7 * (n - 1))


def dedupe_releases(releases: list[MacroRelease]) -> list[MacroRelease]:
    result: list[MacroRelease] = []
    seen: set[str] = set()
    for release in sorted(releases, key=lambda item: (item.release_at_utc, item.indicator_code)):
        if release.event_key in seen:
            continue
        seen.add(release.event_key)
        result.append(release)
    return result


def html_text_lines(html_text: str) -> list[str]:
    parser = _TextExtractor()
    parser.feed(html_text)
    return [line for line in (normalize_space(part) for part in parser.parts) if line]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data and data.strip():
            self.parts.append(data)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_retail_section(lines: list[str]) -> list[str]:
    try:
        start = lines.index("Advance Monthly Retail Trade Report") + 1
    except ValueError:
        return lines

    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i] in {"Monthly Retail Trade Report", "Historical Release Dates in Excel"}:
            end = i
            break
    return lines[start:end]


class MacroReleaseCalendarStore:
    def __init__(self, env_file: str) -> None:
        self._settings = load_settings(env_file)
        self._table = safe_identifier(self._settings.mysql_macro_calendar_table)
        self._connector = self._import_mysql_connector()
        self._conn = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._create_database_if_needed()
        self._connect_database()
        self._create_table_if_needed()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def upsert_release(self, release: MacroRelease) -> int:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO `{self._table}` "
            "(event_key, source_id, source_name, indicator_code, indicator_name, period_label, release_title, "
            "release_at_utc, release_at_taipei, release_timezone, importance, reminder_date_taipei, source_url, raw_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "source_name=VALUES(source_name), "
            "indicator_name=VALUES(indicator_name), "
            "period_label=VALUES(period_label), "
            "release_title=VALUES(release_title), "
            "release_at_utc=VALUES(release_at_utc), "
            "release_at_taipei=VALUES(release_at_taipei), "
            "release_timezone=VALUES(release_timezone), "
            "importance=VALUES(importance), "
            "reminder_date_taipei=VALUES(reminder_date_taipei), "
            "source_url=VALUES(source_url), "
            "raw_json=VALUES(raw_json), "
            "updated_at=CURRENT_TIMESTAMP"
        )
        values = (
            release.event_key,
            release.source_id,
            release.source_name,
            release.indicator_code,
            release.indicator_name,
            release.period_label,
            release.release_title,
            release.release_at_utc.strftime("%Y-%m-%d %H:%M:%S"),
            release.release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"),
            release.release_timezone,
            release.importance,
            release.reminder_date_taipei.isoformat(),
            release.source_url,
            json.dumps(release.raw, ensure_ascii=False),
        )
        with self._lock:
            cur = self._cursor()
            try:
                cur.execute(sql, values)
                self._conn.commit()
                return int(cur.rowcount or 0)
            finally:
                cur.close()

    def upsert_releases(self, releases: list[MacroRelease]) -> int:
        affected = 0
        for release in releases:
            affected += self.upsert_release(release)
        return affected

    def _cursor(self):
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")
        return self._conn.cursor()

    def _create_database_if_needed(self) -> None:
        conn = self._connector.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            connection_timeout=self._settings.mysql_connect_timeout_seconds,
            autocommit=True,
        )
        try:
            cur = conn.cursor()
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self._settings.mysql_database}` CHARACTER SET utf8mb4")
            cur.close()
        finally:
            conn.close()

    def _connect_database(self) -> None:
        self._conn = self._connector.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            database=self._settings.mysql_database,
            connection_timeout=self._settings.mysql_connect_timeout_seconds,
            autocommit=False,
        )

    def _create_table_if_needed(self) -> None:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self._table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          event_key CHAR(40) NOT NULL,
          source_id VARCHAR(64) NOT NULL,
          source_name VARCHAR(128) NOT NULL,
          indicator_code VARCHAR(64) NOT NULL,
          indicator_name VARCHAR(128) NOT NULL,
          period_label VARCHAR(64) NOT NULL,
          release_title TEXT NOT NULL,
          release_at_utc DATETIME NOT NULL,
          release_at_taipei DATETIME NOT NULL,
          release_timezone VARCHAR(64) NOT NULL DEFAULT 'America/New_York',
          importance TINYINT NOT NULL DEFAULT 3,
          reminder_date_taipei DATE NOT NULL,
          reminder_pushed TINYINT(1) NOT NULL DEFAULT 0,
          reminder_pushed_at DATETIME NULL,
          reminder_push_status VARCHAR(32) NULL,
          reminder_push_error TEXT NULL,
          source_url TEXT NOT NULL,
          raw_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_macro_release_event_key (event_key),
          KEY idx_macro_release_reminder (reminder_date_taipei, reminder_pushed),
          KEY idx_macro_release_time (release_at_taipei),
          KEY idx_macro_release_indicator (indicator_code, release_at_taipei)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        cur = self._cursor()
        try:
            cur.execute(ddl)
            self._conn.commit()
        finally:
            cur.close()

    @staticmethod
    def _import_mysql_connector():
        try:
            import mysql.connector  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mysql-connector-python is required. Run: pip install -e .") from exc
        return mysql.connector


def safe_identifier(value: str | None) -> str:
    candidate = (value or DEFAULT_TABLE).strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", candidate):
        raise ValueError(f"Unsafe SQL table identifier: {candidate}")
    return candidate


def run_once(config: MacroCalendarConfig) -> dict[str, Any]:
    settings = load_settings(config.env_file)
    if not settings.mysql_enabled and not config.dry_run:
        raise RuntimeError("Macro release calendar collection requires RELAY_MYSQL_ENABLED=true")

    collection = collect_macro_release_calendar(config)
    affected = 0
    if not config.dry_run:
        store = MacroReleaseCalendarStore(config.env_file)
        store.initialize()
        try:
            affected = store.upsert_releases(collection.releases)
        finally:
            store.close()

    result = {
        "ok": len(collection.releases) > 0,
        "releases": len(collection.releases),
        "affected_rows": affected,
        "errors": collection.errors,
        "dry_run": config.dry_run,
        "bls_years": config.bls_years,
        "table": settings.mysql_macro_calendar_table,
        "items": [release_preview(release) for release in collection.releases[:50]],
    }
    logger.info(
        "Macro release calendar complete releases=%d affected_rows=%d errors=%d dry_run=%s",
        len(collection.releases),
        affected,
        len(collection.errors),
        config.dry_run,
    )
    return result


def release_preview(release: MacroRelease) -> dict[str, Any]:
    return {
        "event_key": release.event_key,
        "indicator_code": release.indicator_code,
        "indicator_name": release.indicator_name,
        "period_label": release.period_label,
        "release_at_taipei": release.release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"),
        "reminder_date_taipei": release.reminder_date_taipei.isoformat(),
        "source_url": release.source_url,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    try:
        result = run_once(load_config(args))
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    except Exception as exc:
        logger.error("Macro release calendar failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
