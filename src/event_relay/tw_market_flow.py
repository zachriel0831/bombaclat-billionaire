from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
import sys
from typing import Any

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, RelayEvent
from news_collector.http_client import http_get_json


logger = logging.getLogger(__name__)

EVENT_TYPE = "tw_market_flow_dataset"
DIMENSION = "market_context"
TAIPEI_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class OfficialFlowDataset:
    """封裝 Official Flow Dataset 相關資料與行為。"""
    family: str
    source_family: str
    source: str
    dataset: str
    title: str
    url: str
    date_fields: tuple[str, ...]
    metric_fields: tuple[str, ...]


@dataclass(frozen=True)
class TwMarketFlowConfig:
    """封裝 Tw Market Flow Config 相關資料與行為。"""
    env_file: str
    timeout_seconds: int
    families: tuple[str, ...]
    dry_run: bool = False


@dataclass(frozen=True)
class DatasetSnapshot:
    """封裝 Dataset Snapshot 相關資料與行為。"""
    source_family: str
    source: str
    dataset: str
    title: str
    official_url: str
    trade_date: str
    rows: list[dict[str, Any]]
    normalized_metrics: dict[str, Any]
    generated_at: str


@dataclass(frozen=True)
class SourceFailure:
    """封裝 Source Failure 相關資料與行為。"""
    source_family: str
    dataset: str
    official_url: str
    error: str


TWSE_BASE = "https://openapi.twse.com.tw/v1"
TPEX_BASE = "https://www.tpex.org.tw/openapi/v1"
TAIFEX_BASE = "https://openapi.taifex.com.tw/v1"

DEFAULT_DATASETS: tuple[OfficialFlowDataset, ...] = (
    OfficialFlowDataset(
        family="twse",
        source_family="twse_flow",
        source="market_context:twse_flow",
        dataset="T86_ALLBUT0999",
        title="TWSE three major institutional investors trading",
        url="https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date}&selectType=ALLBUT0999",
        date_fields=(),
        metric_fields=(
            "外陸資買進股數(不含外資自營商)",
            "外陸資賣出股數(不含外資自營商)",
            "外陸資買賣超股數(不含外資自營商)",
            "外資自營商買賣超股數",
            "投信買進股數",
            "投信賣出股數",
            "投信買賣超股數",
            "自營商買賣超股數",
            "三大法人買賣超股數",
        ),
    ),
    OfficialFlowDataset(
        family="twse",
        source_family="twse_flow",
        source="market_context:twse_flow",
        dataset="MI_MARGN",
        title="TWSE margin trading balance",
        url=f"{TWSE_BASE}/exchangeReport/MI_MARGN",
        date_fields=(),
        metric_fields=(
            "融資買進",
            "融資賣出",
            "融資現金償還",
            "融資今日餘額",
            "融券買進",
            "融券賣出",
            "融券現券償還",
            "融券今日餘額",
            "資券互抵",
        ),
    ),
    OfficialFlowDataset(
        family="twse",
        source_family="twse_flow",
        source="market_context:twse_flow",
        dataset="MI_QFIIS_cat",
        title="TWSE foreign and mainland ownership by industry",
        url=f"{TWSE_BASE}/fund/MI_QFIIS_cat",
        date_fields=(),
        metric_fields=("Numbers", "ShareNumber", "ForeignMainlandAreaShare", "Percentage"),
    ),
    OfficialFlowDataset(
        family="twse",
        source_family="twse_flow",
        source="market_context:twse_flow",
        dataset="MI_QFIIS_sort_20",
        title="TWSE top foreign and mainland ownership",
        url=f"{TWSE_BASE}/fund/MI_QFIIS_sort_20",
        date_fields=(),
        metric_fields=("ShareNumber", "AvailableShare", "SharesHeld", "AvailableInvestPer", "SharesHeldPer"),
    ),
    OfficialFlowDataset(
        family="twse",
        source_family="twse_flow",
        source="market_context:twse_flow",
        dataset="SBL_TWT96U",
        title="TWSE / TPEx available securities borrowing and lending volume",
        url=f"{TWSE_BASE}/SBL/TWT96U",
        date_fields=(),
        metric_fields=("TWSEAvailableVolume", "GRETAIAvailableVolume"),
    ),
    OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_mainboard_margin_balance",
        title="TPEx margin trading balance",
        url=f"{TPEX_BASE}/tpex_mainboard_margin_balance",
        date_fields=("Date",),
        metric_fields=(
            "MarginPurchaseBalancePreviousDay",
            "MarginPurchase",
            "MarginSales",
            "CashRedemption",
            "MarginPurchaseBalance",
            "ShortSaleBalancePreviousDay",
            "ShortSale",
            "ShortConvering",
            "StockRedemption",
            "ShortSaleBalance",
            "Offsetting",
        ),
    ),
    OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_3insti_daily_trading",
        title="TPEx three major institutional investors daily trading",
        url=f"{TPEX_BASE}/tpex_3insti_daily_trading",
        date_fields=("Date",),
        metric_fields=(
            "ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy",
            "ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell",
            "ForeignInvestorsInclude MainlandAreaInvestors-Difference",
            "SecuritiesInvestmentTrustCompanies-TotalBuy",
            "SecuritiesInvestmentTrustCompanies-TotalSell",
            "SecuritiesInvestmentTrustCompanies-Difference",
            "Dealers-TotalBuy",
            "Dealers-TotalSell",
            "Dealers-Difference",
            "TotalDifference",
        ),
    ),
    OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_3insti_summary",
        title="TPEx three major institutional investors summary",
        url=f"{TPEX_BASE}/tpex_3insti_summary",
        date_fields=("Date",),
        metric_fields=("PurchaseAmount", "SaleAmount", "Net"),
    ),
    OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_margin_sbl",
        title="TPEx margin and securities borrowing short-sale balance",
        url=f"{TPEX_BASE}/tpex_margin_sbl",
        date_fields=("Date",),
        metric_fields=(
            "SaleBalancePreviousDay",
            "SaleSell",
            "SaleBuy",
            "SaleSpotSecurities",
            "SaleBalanceOfTheMarketDay",
            "SecuritiesBorrowingBalancePreviousDay",
            "SecuritiesBorrowingSale",
            "SecuritiesBorrowingReturn",
            "SecuritiesBorrowingAdjustment",
            "SecuritiesBorrowingBalanceOfTheMarketDay",
        ),
    ),
    OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_3insti_qfii_trading",
        title="TPEx foreign investor trading",
        url=f"{TPEX_BASE}/tpex_3insti_qfii_trading",
        date_fields=("Date",),
        metric_fields=(
            " ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy",
            " ForeignInvestorsIncludeMainlandAreaInvestors-Total Sell",
            "ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell",
            " ForeignInvestorsInclude MainlandAreaInvestors-Difference",
            " ForeignInvestorsIncludeMainlandAreaInvestors-Difference",
            " ForeignDealers-TotalBuy",
            " ForeignDealers-TotalSell",
            " ForeignDealers-Difference",
        ),
    ),
    OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_3insti_dealer_trading",
        title="TPEx dealer trading",
        url=f"{TPEX_BASE}/tpex_3insti_dealer_trading",
        date_fields=("Date",),
        metric_fields=("Buy", "Sell", "NetBuySell", "NetBuy"),
    ),
    OfficialFlowDataset(
        family="taifex",
        source_family="taifex_flow",
        source="market_context:taifex_flow",
        dataset="MarketDataOfMajorInstitutionalTradersGeneralBytheDate",
        title="TAIFEX major institutional traders general",
        url=f"{TAIFEX_BASE}/MarketDataOfMajorInstitutionalTradersGeneralBytheDate",
        date_fields=("Date",),
        metric_fields=(
            "TradingVolume(Long)",
            "TradingValue(Long)(Millions)",
            "TradingVolume(Short)",
            "TradingValue(Short)(Millions)",
            "TradingVolume(Net)",
            "TradingValue(Net)(Millions)",
            "OpenInterest(Long)",
            "ContractValueOfOpenInterest(Long)(Millions)",
            "OpenInterest(Short)",
            "ContractValueOfOpenInterest(Short)(Millions)",
            "OpenInterest(Net)",
            "ContractValueOfOpenInterest(Net)(Millions)",
        ),
    ),
    OfficialFlowDataset(
        family="taifex",
        source_family="taifex_flow",
        source="market_context:taifex_flow",
        dataset="MarketDataOfMajorInstitutionalTradersDividedByFuturesAndOptionsBytheDate",
        title="TAIFEX major institutional traders futures/options",
        url=f"{TAIFEX_BASE}/MarketDataOfMajorInstitutionalTradersDividedByFuturesAndOptionsBytheDate",
        date_fields=("Date",),
        metric_fields=(
            "FuturesTradingVolume(Long)",
            "OptionsTradingVolume(Long)",
            "FuturesTradingVolume(Short)",
            "OptionsTradingVolume(Short)",
            "FuturesTradingVolume(Net)",
            "OptionsTradingVolume(Net)",
            "FuturesOpenInterest(Long)",
            "OptionsOpenInterest(Long)",
            "FuturesOpenInterest(Short)",
            "OptionsOpenInterest(Short)",
            "FuturesOpenInterest(Net)",
            "OptionsOpenInterest(Net)",
        ),
    ),
    OfficialFlowDataset(
        family="taifex",
        source_family="taifex_flow",
        source="market_context:taifex_flow",
        dataset="MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate",
        title="TAIFEX major institutional traders futures contracts",
        url=f"{TAIFEX_BASE}/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate",
        date_fields=("Date",),
        metric_fields=(
            "TradingVolume(Long)",
            "TradingValue(Long)(Thousands)",
            "TradingVolume(Short)",
            "TradingValue(Short)(Thousands)",
            "TradingVolume(Net)",
            "TradingValue(Net)(Thousands)",
            "OpenInterest(Long)",
            "ContractValueofOpenInterest(Long)(Thousands)",
            "OpenInterest(Short)",
            "ContractValueofOpenInterest(Short)(Thousands)",
            "OpenInterest(Net)",
            "ContractValueofOpenInterest(Net)(Thousands)",
        ),
    ),
)


def _build_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器。"""
    parser = argparse.ArgumentParser(description="Collect official Taiwan market-flow facts into t_relay_events")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="Per-source HTTP timeout")
    parser.add_argument(
        "--families",
        default="all",
        help="Comma-separated source families: all, twse, tpex, taifex",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and build events without writing MySQL")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def _load_config(args: argparse.Namespace) -> TwMarketFlowConfig:
    """載入 load config 對應的資料或結果。"""
    return TwMarketFlowConfig(
        env_file=args.env_file,
        timeout_seconds=max(5, int(args.timeout_seconds)),
        families=_parse_families(args.families),
        dry_run=bool(args.dry_run),
    )


def _parse_families(value: str) -> tuple[str, ...]:
    """解析 parse families 對應的資料或結果。"""
    requested = [part.strip().lower() for part in (value or "all").split(",") if part.strip()]
    if not requested or "all" in requested:
        return ("twse", "tpex", "taifex")

    allowed = {"twse", "tpex", "taifex"}
    invalid = sorted(set(requested) - allowed)
    if invalid:
        raise ValueError(f"Unsupported families: {', '.join(invalid)}")
    ordered = tuple(family for family in ("twse", "tpex", "taifex") if family in set(requested))
    return ordered


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    """取出 extract rows 對應的資料或結果。"""
    if isinstance(payload, list):
        raw_rows = payload
        fields = None
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        raw_rows = payload["data"]
        fields = payload.get("fields") if isinstance(payload.get("fields"), list) else None
    elif isinstance(payload, dict):
        raw_rows = [payload]
        fields = None
    else:
        raw_rows = []

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if isinstance(row, dict):
            rows.append(dict(row))
        elif fields and isinstance(row, (list, tuple)):
            # 有些官方 API 會回 fields + data[list]，這裡統一轉成 dict，
            # 後面的 trade_date / metrics 邏輯才能用同一套欄位存取。
            rows.append({str(fields[index]): row[index] for index in range(min(len(fields), len(row)))})
    return rows


def _parse_number(value: Any) -> float | None:
    """解析 parse number 對應的資料或結果。"""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None

    text = str(value).strip()
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return -parsed if negative else parsed


def _normalize_trade_date(value: Any) -> str | None:
    """正規化 normalize trade date 對應的資料或結果。"""
    text = str(value or "").strip()
    if not text:
        return None

    if "T" in text:
        text = text.split("T", 1)[0]

    normalized = text.replace("/", "-").replace(".", "-")
    parts = normalized.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year = int(parts[0])
        if year < 1000:
            year += 1911
        month = int(parts[1])
        day = int(parts[2])
        return f"{year:04d}-{month:02d}-{day:02d}"

    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{int(digits[:4]):04d}-{int(digits[4:6]):02d}-{int(digits[6:8]):02d}"
    if len(digits) == 7:
        year = int(digits[:3]) + 1911
        return f"{year:04d}-{int(digits[3:5]):02d}-{int(digits[5:7]):02d}"
    return None


def _row_value(row: dict[str, Any], field: str) -> Any:
    """執行 row value 的主要流程。"""
    if field in row:
        return row[field]
    target = field.strip()
    for key, value in row.items():
        if str(key).strip() == target:
            return value
    return None


def _resolve_trade_date(
    rows: list[dict[str, Any]],
    dataset: OfficialFlowDataset,
    now_local: datetime,
    payload: Any | None = None,
) -> str:
    """解析並決定 resolve trade date 對應的資料或結果。"""
    dates: list[str] = []
    # 各資料集日期欄位格式不一致，先從 row-level 指定欄位抓；
    # 若抓不到，再退回 payload 頂層日期，最後才用當地今天保底。
    for row in rows:
        for field in dataset.date_fields:
            parsed = _normalize_trade_date(_row_value(row, field))
            if parsed:
                dates.append(parsed)
    if dates:
        return max(dates)
    if isinstance(payload, dict):
        for field in ("date", "Date", "tradeDate", "trade_date"):
            parsed = _normalize_trade_date(payload.get(field))
            if parsed:
                return parsed
    return now_local.astimezone(TAIPEI_TZ).date().isoformat()


def _display_number(value: float) -> int | float:
    """執行 display number 的主要流程。"""
    return int(value) if value.is_integer() else round(value, 4)


def _normalize_metrics(rows: list[dict[str, Any]], metric_fields: tuple[str, ...]) -> dict[str, Any]:
    """正規化 normalize metrics 對應的資料或結果。"""
    totals: dict[str, int | float] = {}
    counts: dict[str, int] = {}
    # 這裡不試圖做金融語意推理，只做 dataset-level totals/counts，
    # 讓後續分析能先快速看到這包官方資料大概在講什麼。
    for field in metric_fields:
        total = 0.0
        count = 0
        for row in rows:
            parsed = _parse_number(_row_value(row, field))
            if parsed is None:
                continue
            total += parsed
            count += 1
        if count:
            totals[field.strip()] = _display_number(total)
            counts[field.strip()] = count
    return {
        "row_count": len(rows),
        "field_totals": totals,
        "field_non_null_counts": counts,
    }


def _build_snapshot(
    dataset: OfficialFlowDataset,
    payload: Any,
    now_local: datetime,
    official_url: str | None = None,
) -> DatasetSnapshot:
    """建立 build snapshot 對應的資料或結果。"""
    rows = _extract_rows(payload)
    generated_at = now_local.astimezone(TAIPEI_TZ).isoformat()
    # snapshot 是 event 化之前的中繼層：保留原始 rows + 壓縮過的 totals，
    # 後面可以同時兼顧審計追溯與 prompt 瘦身。
    trade_date = _resolve_trade_date(rows, dataset, now_local, payload)
    metrics = _normalize_metrics(rows, dataset.metric_fields)
    metrics["trade_date"] = trade_date
    metrics["dataset"] = dataset.dataset
    metrics["source_family"] = dataset.source_family
    return DatasetSnapshot(
        source_family=dataset.source_family,
        source=dataset.source,
        dataset=dataset.dataset,
        title=dataset.title,
        official_url=official_url or dataset.url,
        trade_date=trade_date,
        rows=rows,
        normalized_metrics=metrics,
        generated_at=generated_at,
    )


def collect_tw_market_flow(
    config: TwMarketFlowConfig,
    now_local: datetime | None = None,
) -> tuple[list[DatasetSnapshot], list[SourceFailure]]:
    """彙整 collect tw market flow 對應的資料或結果。"""
    now_local = now_local or datetime.now(TAIPEI_TZ)
    enabled = set(config.families)
    snapshots: list[DatasetSnapshot] = []
    failures: list[SourceFailure] = []

    for dataset in DEFAULT_DATASETS:
        if dataset.family not in enabled:
            continue
        official_url = _dataset_url(dataset, now_local)
        try:
            # 每個 dataset 單獨抓、單獨記錄失敗，避免單一官方端點掛掉就讓整批資料中斷。
            payload = http_get_json(official_url, timeout=config.timeout_seconds)
            snapshot = _build_snapshot(
                dataset=dataset,
                payload=payload,
                now_local=now_local,
                official_url=official_url,
            )
            if snapshot.rows:
                snapshots.append(snapshot)
            else:
                failures.append(
                    SourceFailure(
                        source_family=dataset.source_family,
                        dataset=dataset.dataset,
                        official_url=official_url,
                        error="empty official dataset payload",
                    )
                )
        except Exception as exc:
            failures.append(
                SourceFailure(
                    source_family=dataset.source_family,
                    dataset=dataset.dataset,
                    official_url=official_url,
                    error=str(exc),
                )
            )
    return snapshots, failures


def _dataset_url(dataset: OfficialFlowDataset, now_local: datetime) -> str:
    """執行 dataset url 的主要流程。"""
    return dataset.url.replace("{date}", now_local.astimezone(TAIPEI_TZ).strftime("%Y%m%d"))


def _stable_event_id(source_family: str, trade_date: str, dataset: str) -> str:
    """執行 stable event id 的主要流程。"""
    dataset_slug = re.sub(r"[^0-9A-Za-z_]+", "_", dataset).strip("_") or hashlib.sha1(
        dataset.encode("utf-8")
    ).hexdigest()[:12]
    base = f"tw-market-flow-{source_family}-{trade_date}-{dataset_slug}"
    if len(base) <= 128:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"{base[:115]}-{digest}"


def _event_title(snapshot: DatasetSnapshot) -> str:
    """執行 event title 的主要流程。"""
    row_count = snapshot.normalized_metrics.get("row_count", len(snapshot.rows))
    return f"{snapshot.title} {snapshot.trade_date} rows={row_count}"


def _event_summary(snapshot: DatasetSnapshot) -> str:
    """執行 event summary 的主要流程。"""
    totals = snapshot.normalized_metrics.get("field_totals")
    total_items = list(totals.items())[:6] if isinstance(totals, dict) else []
    total_text = "; ".join(f"{key}={value}" for key, value in total_items)
    base = f"source_family={snapshot.source_family}; dataset={snapshot.dataset}; trade_date={snapshot.trade_date}; rows={len(snapshot.rows)}"
    return f"{base}; totals: {total_text}" if total_text else base


def _snapshot_to_event(snapshot: DatasetSnapshot) -> RelayEvent:
    """執行 snapshot to event 的主要流程。"""
    dedupe_key = {
        "source_family": snapshot.source_family,
        "trade_date": snapshot.trade_date,
        "dataset": snapshot.dataset,
    }
    return RelayEvent(
        event_id=_stable_event_id(snapshot.source_family, snapshot.trade_date, snapshot.dataset),
        source=snapshot.source,
        title=_event_title(snapshot),
        url=snapshot.official_url,
        summary=_event_summary(snapshot),
        published_at=f"{snapshot.trade_date}T00:00:00+08:00",
        log_only=False,
        raw={
            "stored_only": True,
            "dimension": DIMENSION,
            "event_type": EVENT_TYPE,
            "trade_date": snapshot.trade_date,
            "dataset": snapshot.dataset,
            "dataset_title": snapshot.title,
            "source_family": snapshot.source_family,
            "official_url": snapshot.official_url,
            "generated_at": snapshot.generated_at,
            "dedupe_key": dedupe_key,
            "rows": snapshot.rows,
            "normalized_metrics": snapshot.normalized_metrics,
        },
    )


def build_tw_market_flow_events(snapshots: list[DatasetSnapshot]) -> list[RelayEvent]:
    """建立 build tw market flow events 對應的資料或結果。"""
    return [_snapshot_to_event(snapshot) for snapshot in snapshots]


def run_once(config: TwMarketFlowConfig) -> dict[str, Any]:
    """執行單次任務流程並回傳結果。"""
    relay_settings = load_settings(config.env_file)
    if not relay_settings.mysql_enabled and not config.dry_run:
        raise RuntimeError("TW market flow requires RELAY_MYSQL_ENABLED=true")

    snapshots, failures = collect_tw_market_flow(config)
    events = build_tw_market_flow_events(snapshots)

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

    for failure in failures:
        logger.warning(
            "TW market flow source failure: source_family=%s dataset=%s url=%s error=%s",
            failure.source_family,
            failure.dataset,
            failure.official_url,
            failure.error,
        )

    result = {
        "ok": True,
        "families": list(config.families),
        "datasets": len(snapshots),
        "events": len(events),
        "stored": stored,
        "duplicates": duplicates,
        "dry_run": config.dry_run,
        "failures": len(failures),
        "failure_details": [failure.__dict__ for failure in failures],
        "sources": sorted({snapshot.source for snapshot in snapshots}),
    }
    logger.info("TW market flow events stored: %s", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> int:
    """程式入口，負責執行此模組的主要流程。"""
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
        logger.info("TW market flow result: %s", json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        logger.error("TW market flow failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
