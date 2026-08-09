"""Compare registered news sources with locally stored article coverage."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from news_platform.config import NewsPlatformSettings
from news_platform.main import build_source
from news_platform.models import NewsArticle
from news_platform.pipeline import run_once
from news_platform.registry import FeedSpec, active_source_ids, registered_source_ids, tw_news_feeds
from news_platform.store import NewsPlatformStore


logger = logging.getLogger(__name__)

DEFAULT_AUDIT_EXTRA_SOURCE_IDS = ("tvbs", "udn", "setn")
DEFAULT_SKIP_SOURCE_IDS = ("ctee",)
STATUS_ORDER = {
    "ok": 0,
    "warn": 1,
    "missing": 2,
    "error": 3,
}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class SourceAccuracyProbe:
    name: str
    status: str
    source_id: str
    category: str
    official_count: int = 0
    matched_count: int = 0
    missing_count: int = 0
    coverage_rate: float | None = None
    threshold: float = 0.85
    compensated: bool = False
    compensation_stored: int = 0
    compensation_duplicates: int = 0
    compensation_failed: int = 0
    detail: str = ""
    missing_samples: list[dict[str, str]] | None = None


@dataclass(frozen=True)
class SourceAccuracyReport:
    generated_at_utc: str
    overall_status: str
    probes: list[SourceAccuracyProbe]
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


def source_ids_for_accuracy_audit(
    *,
    categories: Iterable[str] | None = None,
    source_ids: Iterable[str] | None = None,
    skip_source_ids: Iterable[str] = DEFAULT_SKIP_SOURCE_IDS,
) -> tuple[str, ...]:
    skip = {source.strip().lower() for source in skip_source_ids if source.strip()}
    requested = tuple(dict.fromkeys(source.strip().lower() for source in (source_ids or ()) if source.strip()))
    if any(source == "all" for source in requested):
        selected = registered_source_ids(categories)
    elif requested:
        selected = requested
    else:
        selected = (
            *active_source_ids(categories),
            *DEFAULT_AUDIT_EXTRA_SOURCE_IDS,
        )
    return tuple(dict.fromkeys(source for source in selected if source not in skip))


def run_accuracy_audit(
    settings: NewsPlatformSettings,
    *,
    categories: tuple[str, ...],
    source_ids: tuple[str, ...] | None = None,
    skip_source_ids: tuple[str, ...] = DEFAULT_SKIP_SOURCE_IDS,
    limit_per_source: int = 20,
    min_coverage: float = 0.85,
    min_items: int = 3,
    compensate: bool = False,
) -> SourceAccuracyReport:
    selected_source_ids = source_ids_for_accuracy_audit(
        categories=categories,
        source_ids=source_ids,
        skip_source_ids=skip_source_ids,
    )
    specs = tw_news_feeds(categories=categories, source_ids=selected_source_ids)
    official_by_name: dict[str, list[NewsArticle]] = {}
    probes: list[SourceAccuracyProbe] = []

    if not settings.mysql_enabled:
        return _single_error_report("NEWSPF_MYSQL_ENABLED=false", categories, selected_source_ids, limit_per_source)

    conn = None
    try:
        mysql = _import_mysql_connector()
        conn = mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            connection_timeout=settings.mysql_connect_timeout_seconds,
            autocommit=True,
        )
        for spec in specs:
            source = build_source(spec, settings)
            fetch_error = ""
            try:
                official_articles = source.fetch(limit=max(1, int(limit_per_source)))
            except Exception as exc:  # pragma: no cover - source.fetch should usually swallow fetch errors.
                official_articles = []
                fetch_error = str(exc)
            official_by_name[_spec_name(spec)] = official_articles
            matched_ids, matched_urls = _fetch_stored_matches(
                conn,
                table=settings.mysql_article_table,
                source_id=spec.source_id,
                category=spec.category,
                official_articles=official_articles,
            )
            probes.append(
                evaluate_probe(
                    spec=spec,
                    official_articles=official_articles,
                    matched_article_ids=matched_ids,
                    matched_urls=matched_urls,
                    min_coverage=min_coverage,
                    min_items=min_items,
                    fetch_error=fetch_error,
                )
            )
    except Exception as exc:
        logger.warning("news source accuracy audit failed: %s", exc)
        return _single_error_report(str(exc), categories, selected_source_ids, limit_per_source)
    finally:
        if conn is not None:
            conn.close()

    if compensate:
        probes = _compensate_and_refresh(
            settings,
            specs=specs,
            probes=probes,
            official_by_name=official_by_name,
            limit_per_source=limit_per_source,
            min_coverage=min_coverage,
        )

    return SourceAccuracyReport(
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        overall_status=overall_status(probes),
        probes=probes,
        config={
            "categories": list(categories),
            "source_ids": list(selected_source_ids),
            "skip_source_ids": list(skip_source_ids),
            "limit_per_source": limit_per_source,
            "min_coverage": min_coverage,
            "min_items": min_items,
            "compensate": compensate,
        },
    )


def evaluate_probe(
    *,
    spec: FeedSpec,
    official_articles: Sequence[NewsArticle],
    matched_article_ids: set[str],
    matched_urls: set[str],
    min_coverage: float,
    min_items: int,
    fetch_error: str = "",
) -> SourceAccuracyProbe:
    official_count = len(official_articles)
    if official_count <= 0:
        detail = "official list returned 0 items"
        if fetch_error:
            detail = f"{detail}; error={fetch_error}"
        return SourceAccuracyProbe(
            name=_spec_name(spec),
            status="missing",
            source_id=spec.source_id,
            category=spec.category,
            threshold=min_coverage,
            detail=detail,
        )

    matched_count = 0
    missing_samples: list[dict[str, str]] = []
    for article in official_articles:
        if article.article_id in matched_article_ids or article.url in matched_urls:
            matched_count += 1
            continue
        if len(missing_samples) < 5:
            missing_samples.append({"title": article.title, "url": article.url})

    coverage = matched_count / official_count
    status = "ok"
    detail = "official list coverage is within threshold"
    if official_count < min_items:
        status = "warn"
        detail = f"official list has only {official_count} item(s); check source page"
    elif coverage < min_coverage:
        status = "warn"
        detail = "local DB is missing too many official-list items"

    return SourceAccuracyProbe(
        name=_spec_name(spec),
        status=status,
        source_id=spec.source_id,
        category=spec.category,
        official_count=official_count,
        matched_count=matched_count,
        missing_count=official_count - matched_count,
        coverage_rate=round(coverage, 4),
        threshold=min_coverage,
        detail=detail,
        missing_samples=missing_samples,
    )


def overall_status(probes: Iterable[SourceAccuracyProbe]) -> str:
    worst = "ok"
    for probe in probes:
        if STATUS_ORDER.get(probe.status, 3) > STATUS_ORDER.get(worst, 0):
            worst = probe.status
    return worst


def render_text(report: SourceAccuracyReport) -> str:
    lines = [
        f"News source accuracy: {report.overall_status.upper()}",
        f"Generated UTC: {report.generated_at_utc}",
        (
            "Config: categories={categories}, sources={sources}, limit={limit}, "
            "min_coverage={min_coverage:.0%}, compensate={compensate}"
        ).format(
            categories=",".join(report.config.get("categories", [])),
            sources=",".join(report.config.get("source_ids", [])),
            limit=report.config.get("limit_per_source"),
            min_coverage=float(report.config.get("min_coverage", 0.85)),
            compensate=report.config.get("compensate"),
        ),
        "",
    ]
    for probe in report.probes:
        rate = "-" if probe.coverage_rate is None else f"{probe.coverage_rate:.0%}"
        comp = ""
        if probe.compensated:
            comp = (
                f" | compensated stored={probe.compensation_stored} "
                f"duplicates={probe.compensation_duplicates} failed={probe.compensation_failed}"
            )
        lines.append(
            f"[{probe.status.upper():7}] {probe.name}: official={probe.official_count} "
            f"matched={probe.matched_count} missing={probe.missing_count} "
            f"coverage={rate} | {probe.detail}{comp}"
        )
        if probe.missing_samples:
            sample = "; ".join(item["title"] for item in probe.missing_samples[:3])
            lines.append(f"          missing samples: {sample}")
    return "\n".join(lines)


def _compensate_and_refresh(
    settings: NewsPlatformSettings,
    *,
    specs: Sequence[FeedSpec],
    probes: Sequence[SourceAccuracyProbe],
    official_by_name: dict[str, list[NewsArticle]],
    limit_per_source: int,
    min_coverage: float,
) -> list[SourceAccuracyProbe]:
    failing_names = {probe.name for probe in probes if probe.status == "warn" and probe.official_count > 0}
    if not failing_names:
        return list(probes)

    store = NewsPlatformStore(settings)
    store.initialize()
    conn = None
    try:
        mysql = _import_mysql_connector()
        conn = mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            connection_timeout=settings.mysql_connect_timeout_seconds,
            autocommit=True,
        )
        compensation_by_name: dict[str, tuple[int, int, int, set[str], set[str]]] = {}
        for spec in specs:
            name = _spec_name(spec)
            if name not in failing_names:
                continue
            result = run_once([build_source(spec, settings)], store, limit_per_source=limit_per_source)
            matched_ids, matched_urls = _fetch_stored_matches(
                conn,
                table=settings.mysql_article_table,
                source_id=spec.source_id,
                category=spec.category,
                official_articles=official_by_name.get(name, []),
            )
            compensation_by_name[name] = (result.stored, result.duplicates, result.failed, matched_ids, matched_urls)

        refreshed: list[SourceAccuracyProbe] = []
        specs_by_name = {_spec_name(spec): spec for spec in specs}
        for probe in probes:
            data = compensation_by_name.get(probe.name)
            if data is None:
                refreshed.append(probe)
                continue
            stored, duplicates, failed, matched_ids, matched_urls = data
            refreshed_probe = evaluate_probe(
                spec=specs_by_name[probe.name],
                official_articles=official_by_name.get(probe.name, []),
                matched_article_ids=matched_ids,
                matched_urls=matched_urls,
                min_coverage=min_coverage,
                min_items=1,
            )
            refreshed.append(
                replace(
                    refreshed_probe,
                    compensated=True,
                    compensation_stored=stored,
                    compensation_duplicates=duplicates,
                    compensation_failed=failed,
                )
            )
        return refreshed
    finally:
        store.close()
        if conn is not None:
            conn.close()


def _fetch_stored_matches(
    conn: Any,
    *,
    table: str,
    source_id: str,
    category: str,
    official_articles: Sequence[NewsArticle],
) -> tuple[set[str], set[str]]:
    if not official_articles:
        return set(), set()
    article_ids = tuple(dict.fromkeys(article.article_id for article in official_articles if article.article_id))
    urls = tuple(dict.fromkeys(article.url for article in official_articles if article.url))
    clauses: list[str] = []
    params: list[Any] = [source_id, category]
    if article_ids:
        clauses.append(f"article_id IN ({','.join(['%s'] * len(article_ids))})")
        params.extend(article_ids)
    if urls:
        clauses.append(f"url IN ({','.join(['%s'] * len(urls))})")
        params.extend(urls)
    if not clauses:
        return set(), set()

    sql = (
        f"SELECT article_id, url FROM {_quote_identifier(table)} "
        f"WHERE source_id=%s AND category=%s AND ({' OR '.join(clauses)})"
    )
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    finally:
        cur.close()
    return {str(row[0]) for row in rows if row[0]}, {str(row[1]) for row in rows if row[1]}


def _single_error_report(
    detail: str,
    categories: Sequence[str],
    source_ids: Sequence[str],
    limit_per_source: int,
) -> SourceAccuracyReport:
    return SourceAccuracyReport(
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        overall_status="error",
        probes=[
            SourceAccuracyProbe(
                name="news_source_accuracy_audit",
                status="error",
                source_id="",
                category="",
                detail=detail,
            )
        ],
        config={
            "categories": list(categories),
            "source_ids": list(source_ids),
            "limit_per_source": limit_per_source,
        },
    )


def _import_mysql_connector() -> Any:
    import mysql.connector  # type: ignore

    return mysql


def _quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier):
        raise ValueError(f"unsafe SQL identifier: {identifier!r}")
    return f"`{identifier}`"


def _spec_name(spec: FeedSpec) -> str:
    return f"{spec.source_id}:{spec.category}"
