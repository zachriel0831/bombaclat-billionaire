"""Data-source freshness report for news-analysis inputs.

The report is intentionally read-only: it checks MySQL freshness and local
collector process counts, but never fetches upstream URLs or writes rows.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Iterable, Sequence

from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.config import RelaySettings, load_settings as load_relay_settings
from news_collector.config import Settings as CollectorSettings
from news_collector.config import load_settings as load_collector_settings
from news_platform.config import NewsPlatformSettings
from news_platform.config import load_settings as load_news_platform_settings
from news_platform.public_record_matcher import ArticlePublicRecordMatcher
from news_platform.registry import active_source_ids


STATUS_ORDER = {
    "ok": 0,
    "skipped": 0,
    "warn": 1,
    "stale": 2,
    "missing": 3,
    "error": 4,
}

FINANCE_RSS_SOURCES = (
    "經濟日報：不僅新聞速度 更有脈絡深度",
    "財經新聞 - 自由時報",
    "財經知識庫－財經新聞",
    "Anue鉅亨",
    "新頭殼要聞 - 財經",
    "中央社即時新聞 財經新聞",
    "ETtoday 財經新聞",
    "Storm Media Group RSS",
    "TSEC FEED",
    "新聞稿 - 中央銀行-中文版",
    "Latest Market News Today on Fox Business",
)

FINANCE_URL_PATTERNS = (
    "%money.udn.com/%",
    "%ec.ltn.com.tw/%",
    "%moneydj.com/%",
    "%cnyes.com/%",
    "%feeds.feedburner.com/rsscna/finance%",
    "%ettoday.net/%finance%",
    "%newtalk.tw/%",
    "%storm.mg/%",
    "%cbc.gov.tw/%",
    "%twse.com.tw/%",
    "%fsc.gov.tw/%",
)

INTERNATIONAL_RSS_PATTERNS = (
    "%BBC%",
    "%Reuters%",
    "%Fox%",
    "%NPR%",
)

INTERNATIONAL_URL_PATTERNS = (
    "%bbc.co%",
    "%reuters.com%",
    "%foxnews.com%",
    "%foxbusiness.com%",
    "%npr.org%",
)

NEWS_PLATFORM_SOURCE_IDS = active_source_ids()

PUBLIC_RECORD_GROUPS = (
    ("ly", "legislative_bill"),
    ("ly", "healthcare_legislative_bill"),
    ("npa", "fraud_rumor"),
    ("npa", "traffic_accident_a1"),
    ("npa", "traffic_accident_a2_stat"),
    ("npa", "traffic_drunk_driving_stat"),
    ("npa", "fraud_blocked_domain_stat"),
    ("npa", "fraud_enforcement_stat"),
    ("nhi", "nhi_hospital_nursing_staff_stat"),
    ("nhi", "nhi_hospital_bed_occupancy_stat"),
    ("mohw", "mohw_hospital_workforce_stat"),
    ("mohw", "mohw_clinic_workforce_stat"),
    ("mohw", "mohw_hospital_bed_stat"),
    ("mohw", "mohw_nursing_staff_stat"),
    ("moj", "moj_prosecution_disposition_stat"),
    ("mojac", "mojac_daily_custody_stat"),
    ("cwa", "cwa_typhoon_report"),
    ("cwa", "cwa_earthquake_report"),
)

PUBLIC_RECORD_MATCHABLE_TYPES = (
    "legislative_bill",
    "healthcare_legislative_bill",
    "fraud_rumor",
)

TAIPEI_TIMEZONE = timezone(timedelta(hours=8), "Asia/Taipei")
PRE_TW_OPEN_DUE_TIME = time(7, 45)
TW_CLOSE_DUE_TIME = time(15, 45)
US_CLOSE_DUE_TIME = time(5, 15)
NEWS_PLATFORM_CATEGORY_WARN_MINUTES = 180
NEWS_PLATFORM_CATEGORY_STALE_MINUTES = 720
NEWS_PLATFORM_SOURCE_WARN_MINUTES = 1440
NEWS_PLATFORM_SOURCE_STALE_MINUTES = 2880
NEWS_PLATFORM_ENRICHMENT_GRACE_MINUTES = 5

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    connect_timeout: int


@dataclass(frozen=True)
class ProbeResult:
    name: str
    status: str
    latest_utc: str | None = None
    age_minutes: int | None = None
    row_count: int | None = None
    recent_count: int | None = None
    warn_minutes: int | None = None
    stale_minutes: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class HealthReport:
    generated_at_utc: str
    overall_status: str
    probes: list[ProbeResult]
    config: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "overall_status": self.overall_status,
            "config": self.config,
            "probes": [asdict(probe) for probe in self.probes],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def classify_freshness(
    *,
    row_count: int | None,
    age_minutes: int | None,
    warn_minutes: int,
    stale_minutes: int,
) -> str:
    if row_count is None or row_count <= 0 or age_minutes is None:
        return "missing"
    if age_minutes > stale_minutes:
        return "stale"
    if age_minutes > warn_minutes:
        return "warn"
    return "ok"


def overall_status(probes: Iterable[ProbeResult]) -> str:
    worst = "ok"
    for probe in probes:
        if probe.status == "skipped":
            continue
        if STATUS_ORDER.get(probe.status, 4) > STATUS_ORDER.get(worst, 0):
            worst = probe.status
    return worst


def render_text(report: HealthReport) -> str:
    lines = [
        f"Data source health: {report.overall_status.upper()}",
        f"Generated UTC: {report.generated_at_utc}",
        (
            "Config: rss_feeds={rss_feeds_count}, x={x_enabled}, "
            "sec={sec_enabled}, twse_mops={twse_mops_enabled}"
        ).format(**report.config),
        "",
    ]
    for probe in report.probes:
        age = _format_age(probe.age_minutes)
        latest = probe.latest_utc or "-"
        count = "-" if probe.row_count is None else str(probe.row_count)
        recent = "-" if probe.recent_count is None else str(probe.recent_count)
        detail = f" | {probe.detail}" if probe.detail else ""
        lines.append(
            f"[{probe.status.upper():7}] {probe.name}: latest={latest} "
            f"age={age} rows={count} recent={recent}{detail}"
        )
    return "\n".join(lines)


def build_report(env_file: str = ".env", *, include_processes: bool = True) -> HealthReport:
    collector_settings = load_collector_settings(env_file)
    relay_settings = load_relay_settings(env_file)
    news_settings = load_news_platform_settings(env_file)
    probes: list[ProbeResult] = []

    if relay_settings.mysql_enabled:
        probes.extend(_collect_relay_probes(relay_settings, collector_settings))
    else:
        probes.append(
            ProbeResult(
                name="relay_mysql",
                status="skipped",
                detail="RELAY_MYSQL_ENABLED=false",
            )
        )

    if news_settings.mysql_enabled:
        probes.extend(_collect_news_platform_probes(news_settings))
    else:
        probes.append(
            ProbeResult(
                name="news_platform_mysql",
                status="skipped",
                detail="NEWSPF_MYSQL_ENABLED=false",
            )
        )

    if include_processes:
        probes.extend(_collect_process_probes())

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    config = {
        "rss_feeds_count": len(collector_settings.official_rss_feeds),
        "rss_first_per_feed": collector_settings.official_rss_first_per_feed,
        "x_enabled": collector_settings.x_enabled,
        "sec_enabled": collector_settings.sec_enabled,
        "twse_mops_enabled": collector_settings.twse_mops_enabled,
        "news_platform_sources": list(active_source_ids()),
    }
    return HealthReport(
        generated_at_utc=generated_at,
        overall_status=overall_status(probes),
        probes=probes,
        config=config,
    )


def _collect_relay_probes(
    settings: RelaySettings,
    collector_settings: CollectorSettings,
) -> list[ProbeResult]:
    config = DbConfig(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        connect_timeout=settings.mysql_connect_timeout_seconds,
    )
    probes: list[ProbeResult] = []
    try:
        import mysql.connector  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local env
        return [ProbeResult(name="relay_mysql_import", status="error", detail=str(exc))]

    try:
        conn = _connect_mysql(mysql.connector, config)
    except Exception as exc:
        return [ProbeResult(name="relay_mysql_connect", status="error", detail=str(exc))]

    try:
        event_table = _quote_identifier(settings.mysql_event_table)
        analysis_table = _quote_identifier(settings.mysql_analysis_table)
        market_table = _quote_identifier(settings.mysql_market_table)
        now_local = _taipei_now()
        calendar_state = resolve_market_calendar_state(now_local)
        expected_slots = allowed_analysis_slots(calendar_state)

        probes.append(
            _latest_probe(
                conn,
                name="relay_finance_public_rss",
                table=event_table,
                timestamp_col="created_at",
                where=_finance_where_clause(),
                params=_finance_params(),
                warn_minutes=120,
                stale_minutes=360,
                recent_minutes=360,
                detail="Taiwan finance/public RSS rows used by market/news analysis.",
            )
        )
        probes.append(
            _latest_probe(
                conn,
                name="relay_international_rss",
                table=event_table,
                timestamp_col="created_at",
                where=_international_where_clause(),
                params=_international_params(),
                warn_minutes=360,
                stale_minutes=1440,
                recent_minutes=1440,
                detail="BBC/Reuters/Fox/NPR style public RSS rows.",
            )
        )
        probes.append(
            _latest_probe(
                conn,
                name="relay_rss_all",
                table=event_table,
                timestamp_col="created_at",
                where=(
                    "source NOT LIKE 'market_context:%' AND source NOT LIKE 'x:%' "
                    "AND source NOT LIKE 'truthsocial:%' "
                    "AND source NOT LIKE 'sec:%' AND source NOT LIKE 'twse_mops:%' "
                    "AND source <> 'us_index_tracker'"
                ),
                params=(),
                warn_minutes=120,
                stale_minutes=360,
                recent_minutes=360,
                detail="All stored public RSS/news events.",
            )
        )
        probes.append(
            _maybe_enabled_probe(
                enabled=collector_settings.x_enabled,
                disabled_name="relay_x_stream",
                disabled_detail="X_ENABLED=false",
                factory=lambda: _latest_probe(
                    conn,
                    name="relay_x_stream",
                    table=event_table,
                    timestamp_col="created_at",
                    where="source LIKE 'x:%'",
                    params=(),
                    warn_minutes=720,
                    stale_minutes=1440,
                    recent_minutes=1440,
                    detail="Tracked X account events; quiet accounts can naturally produce fewer rows.",
                ),
            )
        )
        probes.append(
            _maybe_enabled_probe(
                enabled=collector_settings.truth_social_enabled,
                disabled_name="relay_truth_social",
                disabled_detail="TRUTH_SOCIAL_ENABLED=false",
                factory=lambda: _latest_probe(
                    conn,
                    name="relay_truth_social",
                    table=event_table,
                    timestamp_col="created_at",
                    where="source LIKE 'truthsocial:%'",
                    params=(),
                    warn_minutes=720,
                    stale_minutes=1440,
                    recent_minutes=1440,
                    detail="Tracked Truth Social public-figure events; quiet accounts can naturally produce fewer rows.",
                ),
            )
        )
        probes.append(
            _maybe_enabled_probe(
                enabled=collector_settings.sec_enabled,
                disabled_name="relay_sec_filings",
                disabled_detail="SEC_ENABLED=false",
                factory=lambda: _event_driven_probe(_latest_probe(
                    conn,
                    name="relay_sec_filings",
                    table=event_table,
                    timestamp_col="created_at",
                    where="source LIKE 'sec:%'",
                    params=(),
                    warn_minutes=4320,
                    stale_minutes=10080,
                    recent_minutes=10080,
                    detail="Official SEC tracked filings; event-driven.",
                )),
            )
        )
        probes.append(
            _maybe_enabled_probe(
                enabled=collector_settings.twse_mops_enabled,
                disabled_name="relay_twse_mops",
                disabled_detail="TWSE_MOPS_ENABLED=false",
                factory=lambda: _event_driven_probe(_latest_probe(
                    conn,
                    name="relay_twse_mops",
                    table=event_table,
                    timestamp_col="created_at",
                    where="source LIKE 'twse_mops:%'",
                    params=(),
                    warn_minutes=1440,
                    stale_minutes=4320,
                    recent_minutes=4320,
                    detail="Official TWSE/MOPS major announcements; event-driven.",
                )),
            )
        )
        probes.append(
            _us_session_probe(
                _latest_probe(
                    conn,
                    name="relay_us_index_tracker",
                    table=event_table,
                    timestamp_col="created_at",
                    where="source='us_index_tracker'",
                    params=(),
                    warn_minutes=1440,
                    stale_minutes=4320,
                    recent_minutes=4320,
                    detail="Stored-only DJIA/S&P 500 open-close event flow.",
                ),
                calendar_state=calendar_state,
            )
        )
        probes.append(
            _us_session_probe(
                _latest_probe(
                    conn,
                    name="relay_market_index_snapshots",
                    table=market_table,
                    timestamp_col="created_at",
                    where="1=1",
                    params=(),
                    warn_minutes=1440,
                    stale_minutes=4320,
                    recent_minutes=4320,
                    detail="Structured index snapshot rows for market analysis.",
                ),
                calendar_state=calendar_state,
            )
        )

        market_context_sources = (
            "market_context:collector",
            "market_context:scorecard",
            "market_context:yahoo_chart",
            "market_context:twse_openapi",
            "market_context:fred",
            "market_context:us_treasury",
            "market_context:market_breadth",
            "market_context:fred_energy",
            "market_context:sec_companyfacts",
        )
        probes.append(
            _latest_probe(
                conn,
                name="relay_market_context_preopen",
                table=event_table,
                timestamp_col="created_at",
                where=_in_clause("source", len(market_context_sources)),
                params=market_context_sources,
                warn_minutes=1800,
                stale_minutes=3240,
                recent_minutes=3240,
                detail="Pre-open market context facts and scorecard.",
            )
        )
        probes.append(
            _latest_probe(
                conn,
                name="relay_bls_macro",
                table=event_table,
                timestamp_col="created_at",
                where="source='market_context:bls_macro'",
                params=(),
                warn_minutes=43200,
                stale_minutes=64800,
                recent_minutes=64800,
                detail="BLS macro facts; monthly source cadence.",
            )
        )
        probes.append(
            _latest_probe(
                conn,
                name="relay_tw_market_flow",
                table=event_table,
                timestamp_col="created_at",
                where=_in_clause("source", 3),
                params=("market_context:twse_flow", "market_context:tpex_flow", "market_context:taifex_flow"),
                warn_minutes=2160,
                stale_minutes=4320,
                recent_minutes=4320,
                detail="TWSE/TPEx/TAIFEX official market-flow facts.",
            )
        )
        probes.append(
            _latest_probe(
                conn,
                name="relay_tw_close_context",
                table=event_table,
                timestamp_col="created_at",
                where="source='market_context:tw_close'",
                params=(),
                warn_minutes=2160,
                stale_minutes=4320,
                recent_minutes=4320,
                detail="Taiwan close context aggregate.",
            )
        )
        probes.append(
            _scheduled_slot_probe(
                _latest_probe(
                    conn,
                    name="analysis_pre_tw_open",
                    table=analysis_table,
                    timestamp_col="updated_at",
                    where="analysis_slot='pre_tw_open'",
                    params=(),
                    warn_minutes=1800,
                    stale_minutes=3240,
                    recent_minutes=3240,
                    detail="Latest stored Taiwan pre-open analysis.",
                ),
                now_local=now_local,
                expected_slots=expected_slots,
                slot="pre_tw_open",
                due_time=PRE_TW_OPEN_DUE_TIME,
            )
        )
        probes.append(
            _scheduled_slot_probe(
                _latest_probe(
                    conn,
                    name="analysis_us_close",
                    table=analysis_table,
                    timestamp_col="updated_at",
                    where="analysis_slot='us_close'",
                    params=(),
                    warn_minutes=1800,
                    stale_minutes=4320,
                    recent_minutes=4320,
                    detail="Latest stored U.S. close analysis.",
                ),
                now_local=now_local,
                expected_slots=expected_slots,
                slot="us_close",
                due_time=US_CLOSE_DUE_TIME,
            )
        )
        probes.append(
            _scheduled_slot_probe(
                _latest_probe(
                    conn,
                    name="analysis_tw_close",
                    table=analysis_table,
                    timestamp_col="updated_at",
                    where="analysis_slot='tw_close'",
                    params=(),
                    warn_minutes=2160,
                    stale_minutes=4320,
                    recent_minutes=4320,
                    detail="Latest stored Taiwan close analysis.",
                ),
                now_local=now_local,
                expected_slots=expected_slots,
                slot="tw_close",
                due_time=TW_CLOSE_DUE_TIME,
            )
        )
    finally:
        conn.close()

    return probes


def _collect_news_platform_probes(settings: NewsPlatformSettings) -> list[ProbeResult]:
    config = DbConfig(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        connect_timeout=settings.mysql_connect_timeout_seconds,
    )
    try:
        import mysql.connector  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local env
        return [ProbeResult(name="news_platform_mysql_import", status="error", detail=str(exc))]

    try:
        conn = _connect_mysql(mysql.connector, config)
    except Exception as exc:
        return [ProbeResult(name="news_platform_mysql_connect", status="error", detail=str(exc))]

    probes: list[ProbeResult] = []
    try:
        article_table = _quote_identifier(settings.mysql_article_table)
        record_table = _quote_identifier(settings.mysql_public_record_table)
        link_table = _quote_identifier(settings.mysql_article_record_link_table)

        for category in ("society", "politics"):
            probes.append(
                _latest_probe(
                    conn,
                    name=f"news_platform_{category}_articles",
                    table=article_table,
                    timestamp_col="fetched_at",
                    where="category=%s",
                    params=(category,),
                    warn_minutes=NEWS_PLATFORM_CATEGORY_WARN_MINUTES,
                    stale_minutes=NEWS_PLATFORM_CATEGORY_STALE_MINUTES,
                    recent_minutes=NEWS_PLATFORM_CATEGORY_STALE_MINUTES,
                    detail="Category-level article ingestion freshness.",
                )
            )
            for source_id in active_source_ids():
                probes.append(
                    _latest_probe(
                        conn,
                        name=f"news_platform_{category}_{source_id}",
                        table=article_table,
                        timestamp_col="fetched_at",
                        where="category=%s AND source_id=%s",
                        params=(category, source_id),
                        warn_minutes=NEWS_PLATFORM_SOURCE_WARN_MINUTES,
                        stale_minutes=NEWS_PLATFORM_SOURCE_STALE_MINUTES,
                        recent_minutes=NEWS_PLATFORM_SOURCE_STALE_MINUTES,
                        detail=(
                            "Per-source article ingestion freshness; wider window accounts "
                            "for naturally quiet feeds."
                        ),
                    )
                )

        probes.append(_article_enrichment_probe(conn, article_table))

        for source_id, record_type in PUBLIC_RECORD_GROUPS:
            probes.append(
                _latest_probe(
                    conn,
                    name=f"public_records_{source_id}_{record_type}",
                    table=record_table,
                    timestamp_col="updated_at",
                    where="source_id=%s AND record_type=%s",
                    params=(source_id, record_type),
                    warn_minutes=2880,
                    stale_minutes=5760,
                    recent_minutes=5760,
                    detail="Structured official public-record refresh freshness.",
                )
            )
        probes.append(
            _public_record_links_probe(
                conn,
                article_table=article_table,
                record_table=record_table,
                link_table=link_table,
            )
        )
    finally:
        conn.close()
    return probes


def _collect_process_probes() -> list[ProbeResult]:
    if os.name != "nt":
        return [
            ProbeResult(
                name="local_process_counts",
                status="skipped",
                detail="process count probe currently supports Windows only",
            )
        ]

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { $_.CommandLine } | "
                    "Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
                    "ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=15,
        )
    except Exception as exc:
        return [ProbeResult(name="local_process_counts", status="warn", detail=str(exc))]

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "PowerShell process query failed"
        return [ProbeResult(name="local_process_counts", status="warn", detail=detail)]

    records = _parse_process_records(completed.stdout or "")
    return [
        _process_count_probe(
            records,
            name="process_event_relay",
            pattern=r"event_relay\.main",
            expected_min=1,
            expected_max=1,
        ),
        _process_count_probe(
            records,
            name="process_source_bridge",
            pattern=r"news_collector\.relay_bridge",
            expected_min=1,
            expected_max=1,
        ),
        _process_count_probe(
            records,
            name="process_news_platform_loop",
            pattern=r"news_platform\.main.*--loop",
            expected_min=1,
            expected_max=1,
        ),
    ]


def _parse_process_records(raw_json: str) -> list[dict[str, Any]]:
    if not raw_json.strip():
        return []
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    records: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return records
    for item in payload:
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "pid": int(item.get("ProcessId") or 0),
                "parent_pid": int(item.get("ParentProcessId") or 0),
                "name": str(item.get("Name") or ""),
                "command": str(item.get("CommandLine") or ""),
            }
        )
    return records


def _process_count_probe(
    records: Sequence[dict[str, Any]],
    *,
    name: str,
    pattern: str,
    expected_min: int,
    expected_max: int,
) -> ProbeResult:
    regex = re.compile(pattern)
    matching = [
        record
        for record in records
        if str(record.get("name", "")).lower().startswith("python")
        and regex.search(str(record.get("command", "")))
    ]
    matching_pids = {int(record.get("pid") or 0) for record in matching}
    roots = [
        record
        for record in matching
        if int(record.get("parent_pid") or 0) not in matching_pids
    ]
    count = len(roots)
    if count < expected_min:
        status = "missing"
    elif count > expected_max:
        status = "warn"
    else:
        status = "ok"
    return ProbeResult(
        name=name,
        status=status,
        row_count=count,
        detail=(
            f"expected {expected_min}-{expected_max} root process(es); "
            f"raw_python_matches={len(matching)}"
        ),
    )


def _latest_probe(
    conn: Any,
    *,
    name: str,
    table: str,
    timestamp_col: str,
    where: str,
    params: Sequence[Any],
    warn_minutes: int,
    stale_minutes: int,
    recent_minutes: int,
    detail: str,
) -> ProbeResult:
    timestamp = _quote_identifier(timestamp_col)
    recent_cutoff = _utc_now_naive() - timedelta(minutes=recent_minutes)
    sql = (
        f"SELECT COUNT(*), "
        f"COALESCE(SUM(CASE WHEN {timestamp} >= %s THEN 1 ELSE 0 END), 0), "
        f"MAX({timestamp}), "
        f"TIMESTAMPDIFF(MINUTE, MAX({timestamp}), UTC_TIMESTAMP()) "
        f"FROM {table} WHERE {where}"
    )
    values = (recent_cutoff.strftime("%Y-%m-%d %H:%M:%S"), *params)
    cur = conn.cursor()
    try:
        cur.execute(sql, values)
        row = cur.fetchone()
    finally:
        cur.close()

    row_count = int(row[0] or 0) if row else 0
    recent_count = int(row[1] or 0) if row else 0
    latest = row[2] if row else None
    age_minutes = int(row[3]) if row and row[3] is not None else None
    status = classify_freshness(
        row_count=row_count,
        age_minutes=age_minutes,
        warn_minutes=warn_minutes,
        stale_minutes=stale_minutes,
    )
    return ProbeResult(
        name=name,
        status=status,
        latest_utc=_format_datetime(latest),
        age_minutes=age_minutes,
        row_count=row_count,
        recent_count=recent_count,
        warn_minutes=warn_minutes,
        stale_minutes=stale_minutes,
        detail=detail,
    )


def _article_enrichment_probe(conn: Any, article_table: str) -> ProbeResult:
    grace_minutes = NEWS_PLATFORM_ENRICHMENT_GRACE_MINUTES
    sql = (
        f"SELECT COUNT(*), "
        "COALESCE(SUM(CASE WHEN keywords_json IS NULL "
        f"AND (fetched_at IS NULL OR fetched_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL {grace_minutes} MINUTE)) "
        "THEN 1 ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN topics_json IS NULL "
        f"AND (fetched_at IS NULL OR fetched_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL {grace_minutes} MINUTE)) "
        "THEN 1 ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN keywords_json IS NULL "
        f"AND fetched_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL {grace_minutes} MINUTE) "
        "THEN 1 ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN topics_json IS NULL "
        f"AND fetched_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL {grace_minutes} MINUTE) "
        "THEN 1 ELSE 0 END), 0), "
        "MAX(fetched_at), TIMESTAMPDIFF(MINUTE, MAX(fetched_at), UTC_TIMESTAMP()) "
        f"FROM {article_table} "
        "WHERE category IN ('society','politics')"
    )
    cur = conn.cursor()
    try:
        cur.execute(sql)
        row = cur.fetchone()
    finally:
        cur.close()

    row_count = int(row[0] or 0) if row else 0
    missing_keywords = int(row[1] or 0) if row else 0
    missing_topics = int(row[2] or 0) if row else 0
    pending_recent_keywords = int(row[3] or 0) if row else 0
    pending_recent_topics = int(row[4] or 0) if row else 0
    latest = row[5] if row else None
    age_minutes = int(row[6]) if row and row[6] is not None else None
    status = "missing" if row_count == 0 else "ok"
    if missing_keywords or missing_topics:
        status = "warn"
    detail = (
        f"missing_keywords={missing_keywords}, missing_topics={missing_topics}, "
        f"pending_recent_keywords={pending_recent_keywords}, "
        f"pending_recent_topics={pending_recent_topics}, "
        f"grace_minutes={grace_minutes}"
    )
    return ProbeResult(
        name="news_platform_article_enrichment",
        status=status,
        latest_utc=_format_datetime(latest),
        age_minutes=age_minutes,
        row_count=row_count,
        recent_count=row_count - missing_topics,
        detail=detail,
    )


def _taipei_now() -> datetime:
    return datetime.now(TAIPEI_TIMEZONE)


def _us_session_probe(probe: ProbeResult, *, calendar_state: Any) -> ProbeResult:
    if calendar_state.us.is_trading_day:
        return probe
    return replace(
        probe,
        status="skipped",
        detail=(
            f"{probe.detail} U.S. close session "
            f"{calendar_state.us_close_session_date.isoformat()} is closed "
            f"({calendar_state.us.reason}); row freshness is not expected to advance."
        ),
    )


def _scheduled_slot_probe(
    probe: ProbeResult,
    *,
    now_local: datetime,
    expected_slots: set[str],
    slot: str,
    due_time: time,
) -> ProbeResult:
    if slot not in expected_slots:
        return replace(
            probe,
            status="skipped",
            detail=(
                f"{probe.detail} Slot {slot} is not expected for the "
                f"{now_local.date().isoformat()} market calendar."
            ),
        )
    if now_local.time() < due_time:
        return replace(
            probe,
            status="skipped",
            detail=(
                f"{probe.detail} Slot {slot} is not due until "
                f"{due_time.strftime('%H:%M')} Asia/Taipei."
            ),
        )
    return probe


def _public_record_links_probe(
    conn: Any,
    *,
    article_table: str,
    record_table: str,
    link_table: str,
) -> ProbeResult:
    probe = _latest_probe(
        conn,
        name="public_record_links",
        table=link_table,
        timestamp_col="created_at",
        where="1=1",
        params=(),
        warn_minutes=2880,
        stale_minutes=5760,
        recent_minutes=5760,
        detail="Article-to-public-record link creation freshness.",
    )
    if STATUS_ORDER.get(probe.status, 4) == 0:
        return probe

    try:
        candidate_matches = _count_public_record_candidate_matches(
            conn,
            article_table=article_table,
            record_table=record_table,
        )
    except Exception as exc:
        return replace(probe, detail=f"{probe.detail} Candidate-match scan failed: {exc}")

    return _classify_public_record_link_probe(probe, candidate_matches=candidate_matches)


def _classify_public_record_link_probe(
    probe: ProbeResult,
    *,
    candidate_matches: int,
) -> ProbeResult:
    if candidate_matches <= 0:
        return replace(
            probe,
            status="ok",
            detail=(
                f"{probe.detail} No deterministic article-record matches in the "
                "recent candidate window; sparse link creation is expected."
            ),
        )
    return replace(
        probe,
        detail=f"{probe.detail} deterministic_candidate_matches={candidate_matches}",
    )


def _count_public_record_candidate_matches(
    conn: Any,
    *,
    article_table: str,
    record_table: str,
    lookback_days: int = 45,
    article_limit: int = 200,
    record_limit: int = 1000,
    match_cap: int = 25,
) -> int:
    cur = conn.cursor()
    try:
        cur.execute(
            (
                f"SELECT id, article_id, category, title, summary, published_at, "
                f"keywords_json, topics_json FROM {article_table} "
                "WHERE category IN ('politics','society') "
                "AND (published_at IS NULL OR published_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)) "
                "ORDER BY published_at DESC, id DESC LIMIT %s"
            ),
            (max(1, int(lookback_days)), max(1, int(article_limit))),
        )
        articles = [
            SimpleNamespace(
                row_id=int(row[0]),
                article_id=str(row[1]),
                category=str(row[2] or ""),
                title=str(row[3] or ""),
                summary=None if row[4] is None else str(row[4]),
                published_at=row[5],
                keywords_json=row[6],
                topics_json=row[7],
            )
            for row in cur.fetchall()
        ]
        cur.execute(
            (
                f"SELECT record_id, source_id, record_type, category, title, url, "
                f"occurred_at, region, metrics_json, tags_json, raw_json "
                f"FROM {record_table} "
                "WHERE (occurred_at IS NULL OR occurred_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)) "
                "AND (category IS NULL OR category IN ('politics','society')) "
                f"AND {_in_clause('record_type', len(PUBLIC_RECORD_MATCHABLE_TYPES))} "
                "ORDER BY occurred_at DESC, id DESC LIMIT %s"
            ),
            (
                max(1, int(lookback_days)),
                *PUBLIC_RECORD_MATCHABLE_TYPES,
                max(1, int(record_limit)),
            ),
        )
        records = [
            SimpleNamespace(
                record_id=str(row[0]),
                source_id=str(row[1]),
                record_type=str(row[2]),
                category=None if row[3] is None else str(row[3]),
                title=str(row[4] or ""),
                url=None if row[5] is None else str(row[5]),
                occurred_at=row[6],
                region=None if row[7] is None else str(row[7]),
                metrics_json=row[8],
                tags_json=row[9],
                raw_json=row[10],
            )
            for row in cur.fetchall()
        ]
    finally:
        cur.close()

    matcher = ArticlePublicRecordMatcher()
    matches = 0
    for article in articles:
        matches += len(matcher.match_article(article, records))
        if matches >= match_cap:
            return matches
    return matches


def _maybe_enabled_probe(
    *,
    enabled: bool,
    disabled_name: str,
    disabled_detail: str,
    factory: Any,
) -> ProbeResult:
    if not enabled:
        return ProbeResult(name=disabled_name, status="skipped", detail=disabled_detail)
    return factory()


def _event_driven_probe(probe: ProbeResult) -> ProbeResult:
    if probe.status == "missing" and (probe.row_count or 0) <= 0:
        return replace(
            probe,
            status="skipped",
            detail=f"{probe.detail} No stored rows yet; source is event-driven.",
        )
    if probe.status in {"warn", "stale"}:
        return replace(
            probe,
            status="skipped",
            detail=f"{probe.detail} Row creation is event-driven; age alone is not an outage signal.",
        )
    return probe


def _connect_mysql(mysql_connector: Any, config: DbConfig) -> Any:
    conn = mysql_connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        connection_timeout=config.connect_timeout,
    )
    cur = conn.cursor()
    try:
        cur.execute("SET time_zone='+00:00'")
    finally:
        cur.close()
    return conn


def _finance_where_clause() -> str:
    return (
        "("
        + _in_clause("source", len(FINANCE_RSS_SOURCES))
        + " OR "
        + " OR ".join(["LOWER(url) LIKE %s" for _ in FINANCE_URL_PATTERNS])
        + ")"
    )


def _finance_params() -> tuple[str, ...]:
    return (*FINANCE_RSS_SOURCES, *tuple(pattern.lower() for pattern in FINANCE_URL_PATTERNS))


def _international_where_clause() -> str:
    return (
        "("
        + " OR ".join(["source LIKE %s" for _ in INTERNATIONAL_RSS_PATTERNS])
        + " OR "
        + " OR ".join(["LOWER(url) LIKE %s" for _ in INTERNATIONAL_URL_PATTERNS])
        + ")"
    )


def _international_params() -> tuple[str, ...]:
    return (
        *INTERNATIONAL_RSS_PATTERNS,
        *tuple(pattern.lower() for pattern in INTERNATIONAL_URL_PATTERNS),
    )


def _in_clause(column: str, count: int) -> str:
    if count <= 0:
        raise ValueError("count must be positive")
    return f"{_quote_identifier(column)} IN ({','.join(['%s'] * count)})"


def _quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier):
        raise ValueError(f"unsafe SQL identifier: {identifier!r}")
    return f"`{identifier}`"


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    return str(value)


def _format_age(age_minutes: int | None) -> str:
    if age_minutes is None:
        return "-"
    if age_minutes < 60:
        return f"{age_minutes}m"
    hours, minutes = divmod(age_minutes, 60)
    if hours < 48:
        return f"{hours}h{minutes:02d}m"
    days, rem_hours = divmod(hours, 24)
    return f"{days}d{rem_hours:02d}h"


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
