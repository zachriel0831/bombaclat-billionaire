"""Convert structured market analyses into reviewable trade signals."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import replace
import hashlib
import json
import logging
import os
import re
import sys
from typing import Any

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore, TradeSignalRecord


logger = logging.getLogger(__name__)
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-_]{1,16}$")
_TW_MARKETS = {"TW", "TSE", "TWSE", "TPEx", "OTC"}
_DIRECTION_MAP = {
    "bullish": "long",
    "bearish": "short",
    "mixed": "watch",
    "neutral": "watch",
    "long": "long",
    "short": "short",
    "watch": "watch",
    "avoid": "avoid",
}
_DEFAULT_ENTRY_TIMING = "09:05後，確認價格落在進場區且量能未失守；不追開盤急拉"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SUSPECT_STOCK_NAME_RE = re.compile(r"[?\ufffd\ue000-\uf8ff]")
_DEFAULT_EXCLUDED_TICKERS = "4749"
VISIBLE_RECOMMENDATION_LIMIT = 10
MIN_CANDIDATE_RISK_REWARD = 1.5
FIXED_POOL_SIGNAL_BACKFILL_SLOTS = {"pre_tw_open", "us_close"}
FIXED_MARKET_ANALYSIS_WATCH_POOL: dict[str, dict[str, str]] = {
    "2330": {"name": "台積電", "market": "TWSE", "sector": "半導體（晶圓）"},
    "2317": {"name": "鴻海", "market": "TWSE", "sector": "AI伺服器/組裝"},
    "2454": {"name": "聯發科", "market": "TWSE", "sector": "IC設計"},
    "2308": {"name": "台達電", "market": "TWSE", "sector": "電源/AI伺服器"},
    "2881": {"name": "富邦金", "market": "TWSE", "sector": "金融"},
    "2882": {"name": "國泰金", "market": "TWSE", "sector": "金融"},
    "2485": {"name": "兆赫", "market": "TWSE", "sector": "網通/通訊"},
    "3535": {"name": "晶彩科", "market": "TWSE", "sector": "設備/光電"},
    "3715": {"name": "定穎投控", "market": "TWSE", "sector": "PCB/車用電子"},
    "2351": {"name": "順德", "market": "TWSE", "sector": "導線架/半導體材料"},
}
_FIXED_STOCK_WATCH_PROFILES: dict[str, dict[str, str]] = {
    "2330": {
        "bull": "AI/HPC、先進製程與半導體景氣若延續，權值資金通常會先看台積電。",
        "bear": "估值對美債利率、費半與外資動向敏感；若費半轉弱或外資賣超，追價風險升高。",
        "buy_note": "等回到進場區且大盤、費半同步轉強；只看有量的回測，不追開盤急拉。",
    },
    "2317": {
        "bull": "AI伺服器與組裝出貨題材仍是主要觀察點，若法人買盤回流可帶動評價修復。",
        "bear": "毛利率、客戶拉貨節奏與消費電子循環仍是壓力；量能不續時容易回到區間整理。",
        "buy_note": "確認AI伺服器新聞、法人買超與進場區支撐同時成立；跌破停損區先退出觀察。",
    },
    "2454": {
        "bull": "手機SoC、AI edge與ASIC題材可支撐IC設計族群人氣。",
        "bear": "Android需求、同業競爭與匯率變動會壓縮評價；若族群轉弱不宜單獨追高。",
        "buy_note": "等族群成交量放大且價格守住進場區，再用停損區控風險。",
    },
    "2308": {
        "bull": "AI電源、資料中心與電動車電源需求是中線題材核心。",
        "bear": "評價已容易反映成長預期；若訂單能見度或毛利率訊號不足，短線波動會放大。",
        "buy_note": "優先等回測進場區與量能確認，不在急漲後追價。",
    },
    "2881": {
        "bull": "金融股受惠利率、股債資產回升與配息預期時，容易吸引防禦型資金。",
        "bear": "信用利差擴大、債券評價損失或金融指數轉弱時，修復行情會被打斷。",
        "buy_note": "觀察金控族群同步性與金融指數支撐，價格未守進場區先不加碼。",
    },
    "2882": {
        "bull": "保險與銀行雙引擎在股債資產穩定時，有利金融股評價修復。",
        "bear": "利率急變、避險成本與信用風險會壓抑金融股表現。",
        "buy_note": "等金融族群轉強、成交量放大且價格守住停損區，再列為短中線觀察。",
    },
    "2485": {
        "bull": "網通與通訊設備題材若有訂單或族群輪動，低基期個股較容易被資金注意。",
        "bear": "中小型股流動性與訂單能見度較弱；沒有量能時容易只是題材反彈。",
        "buy_note": "必須看到量能與新聞催化，且價格回到進場區；否則只當固定池追蹤。",
    },
    "3535": {
        "bull": "設備與光電應用題材若跟隨科技股輪動，可帶來補漲想像。",
        "bear": "中小型股籌碼與流動性風險高；若沒有訂單或法人買盤，拉回速度可能很快。",
        "buy_note": "先看成交量是否明顯放大，再以停損區控回撤，不用小量突破追價。",
    },
    "3715": {
        "bull": "PCB與車用電子題材若接上AI/車用供應鏈輪動，具備補漲觀察價值。",
        "bear": "PCB景氣循環、車用需求與原物料成本可能壓抑毛利；族群不同步時不追。",
        "buy_note": "等族群確認轉強與價格守進場區，再用停損區作為失效線。",
    },
    "2351": {
        "bull": "導線架與半導體材料若跟隨半導體補庫存，可成為落後補漲觀察標的。",
        "bear": "材料族群對訂單能見度與毛利率敏感；若半導體主流轉弱，補漲容易失敗。",
        "buy_note": "只在半導體族群不弱、量能回升且價格守住進場區時觀察。",
    },
}
_DEFAULT_STOCK_WATCH_PROFILE = {
    "bull": "固定池標的仍可追蹤族群輪動與盤中量價是否轉強。",
    "bear": "今日缺少個股訊號、估值與相對強弱證據，追價參考價值有限。",
    "buy_note": "等價格、量能、新聞催化與停損條件都明確後再評估。",
}
_FIXED_MARKET_ANALYSIS_TICKERS = frozenset(FIXED_MARKET_ANALYSIS_WATCH_POOL)
_TW_STOCK_NAME_BY_TICKER = {
    "0050": "元大台灣50",
    "1605": "華新",
    "2308": "台達電",
    "2317": "鴻海",
    "2330": "台積電",
    "2351": "順德",
    "2382": "廣達",
    "2454": "聯發科",
    "2485": "兆赫",
    "2881": "富邦金",
    "2882": "國泰金",
    "3231": "緯創",
    "3535": "晶彩科",
    "3711": "日月光投控",
    "3715": "定穎投控",
    "4749": "新應材",
    "2603": "長榮",
    "4956": "光鋐",
}


def build_trade_signals_from_analysis(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    structured_payload: dict[str, Any] | None,
    pipeline_telemetry: dict[str, Any] | None = None,
) -> list[TradeSignalRecord]:
    """Build pending-review trade signals from structured analysis JSON."""
    if not isinstance(structured_payload, dict):
        return []

    evidence_by_ticker = _stage3_evidence_by_ticker(pipeline_telemetry)
    global_confidence = _clean_text(structured_payload.get("confidence"))
    raw_items = _iter_signal_items(structured_payload)
    signals: list[TradeSignalRecord] = []
    seen_keys: set[str] = set()

    for item in raw_items:
        ticker = _normalize_ticker(item.get("ticker") or item.get("symbol"))
        if not ticker:
            continue
        if is_excluded_trade_signal_ticker(ticker):
            continue
        if not is_fixed_market_analysis_watch_ticker(ticker):
            continue
        market = _normalize_market(item.get("market"))
        if market not in _TW_MARKETS:
            continue
        direction = _normalize_direction(item.get("direction") or item.get("side"))
        strategy_type = _normalize_strategy_type(
            item.get("strategy_type") or item.get("setup_type") or item.get("holding_horizon")
        )
        idempotency_key = _build_idempotency_key(
            analysis_id=analysis_id,
            analysis_date=analysis_date,
            analysis_slot=analysis_slot,
            market=market,
            ticker=ticker,
            direction=direction,
            strategy_type=strategy_type,
        )
        signal_key = f"sig_{idempotency_key[:24]}"
        if signal_key in seen_keys:
            continue
        seen_keys.add(signal_key)

        source_event_ids = _coerce_list(
            item.get("source_event_ids")
            or item.get("evidence_ids")
            or item.get("evidence_refs")
            or evidence_by_ticker.get(ticker)
        )
        raw_json = {
            "source": "t_market_analyses.structured_json",
            "item": item,
            "trace": {
                "analysis_id": analysis_id,
                "analysis_date": analysis_date,
                "analysis_slot": analysis_slot,
                "source_event_ids": source_event_ids,
            },
            "guardrail": "LLM signal only; review/risk gate required before order intent.",
        }

        signals.append(
            _with_candidate_metrics(
                TradeSignalRecord(
                signal_key=signal_key,
                idempotency_key=idempotency_key,
                analysis_id=analysis_id,
                analysis_date=analysis_date,
                analysis_slot=analysis_slot,
                market=market,
                ticker=ticker,
                name=_resolve_stock_name(ticker, item.get("name") or item.get("company_name") or item.get("company")),
                signal_type="analysis_stock_watch",
                strategy_type=strategy_type,
                direction=direction,
                confidence=_clean_text(item.get("confidence")) or global_confidence,
                entry_zone_json=_json_or_none(_first_present(item, "entry_zone", "entry", "entry_price_range")),
                invalidation_json=_json_or_none(_first_present(item, "invalidation", "stop_loss", "stop")),
                take_profit_zone_json=_json_or_none(
                    _first_present(item, "take_profit_zone", "tp_zone", "take_profit", "target_zone")
                ),
                holding_horizon=_clean_text(item.get("holding_horizon") or item.get("time_horizon")),
                rationale=_clean_text(item.get("rationale") or item.get("thesis") or item.get("reason")),
                risk_notes_json=_json_or_none(item.get("risk_notes") or item.get("risks")),
                source_event_ids_json=_json_or_none(source_event_ids),
                status="pending_review",
                raw_json=json.dumps(raw_json, ensure_ascii=False),
                )
            )
        )
    return signals


def build_quote_event_trade_signals(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    events: Iterable[Any],
    max_signals: int = VISIBLE_RECOMMENDATION_LIMIT,
    preferred_tickers: Iterable[Any] | None = None,
) -> list[TradeSignalRecord]:
    """Build fallback long signals from recent Taiwan quote/context events.

    This is used for delivery-eligible U.S. close and Taiwan pre-open reports
    to provide deterministic reference levels when structured ``stock_watch``
    rows are missing or incomplete. Signals remain pending review; they are
    not orders.
    """
    if analysis_slot not in {"pre_tw_open", "us_close"}:
        return []

    excluded = excluded_trade_signal_tickers_from_env()
    fixed_pool = set(_FIXED_MARKET_ANALYSIS_TICKERS) - excluded
    preferred = _normalize_ticker_set(preferred_tickers) & fixed_pool
    if not preferred:
        preferred = set(fixed_pool)
    candidates: dict[str, dict[str, Any]] = {}
    for event in events:
        candidate = _fallback_candidate_from_event(event)
        if candidate is None:
            continue
        ticker = str(candidate["ticker"])
        if ticker in excluded:
            continue
        if ticker not in fixed_pool:
            continue
        current = candidates.get(ticker)
        event_row_id = candidate.get("event_row_id")
        if current is None or _safe_int(event_row_id) > _safe_int(current.get("event_row_id")):
            candidates[ticker] = candidate

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            1 if str(item.get("ticker") or "") in preferred else 0,
            float(item.get("change_pct") or 0),
            int(item.get("volume") or 0),
        ),
        reverse=True,
    )[: max(1, min(int(max_signals), len(_FIXED_MARKET_ANALYSIS_TICKERS)))]

    signals: list[TradeSignalRecord] = []
    for item in ranked:
        ticker = str(item["ticker"])
        price = float(item["price"])
        change_pct = float(item["change_pct"])
        confidence = "medium" if change_pct >= 3 else "low"
        entry_zone, invalidation, take_profit, risk_reward_policy = _build_long_fallback_levels(
            price=price,
            entry_basis=item.get("entry_basis") or "fallback_price_reference",
            stop_basis=item.get("stop_basis") or "fallback_stop_reference",
            target_basis=item.get("target_basis") or "fallback_target_reference",
        )
        source_event_ids = [item["event_row_id"]] if item.get("event_row_id") is not None else []
        idempotency_key = _build_idempotency_key(
            analysis_id=analysis_id,
            analysis_date=analysis_date,
            analysis_slot=analysis_slot,
            market="TW",
            ticker=ticker,
            direction="long",
            strategy_type="swing",
        )
        raw_json = {
            "source": item.get("source_kind") or "fallback_stock_watch",
            "price": price,
            "change_pct": change_pct,
            "as_of": item.get("as_of"),
            "trace": {
                "analysis_id": analysis_id,
                "analysis_date": analysis_date,
                "analysis_slot": analysis_slot,
                "source_event_ids": source_event_ids,
            },
            "risk_reward_policy": risk_reward_policy,
            "guardrail": "Quote fallback signal only; review/risk gate required before order intent.",
        }
        signals.append(
            _with_candidate_metrics(
                TradeSignalRecord(
                    signal_key=f"sig_{idempotency_key[:24]}",
                    idempotency_key=idempotency_key,
                    analysis_id=analysis_id,
                    analysis_date=analysis_date,
                    analysis_slot=analysis_slot,
                    market="TW",
                    ticker=ticker,
                    name=_clean_text(item.get("name")),
                    signal_type=str(item.get("signal_type") or "quote_fallback_stock_watch"),
                    strategy_type="swing",
                    direction="long",
                    confidence=confidence,
                    entry_zone_json=json.dumps(entry_zone, ensure_ascii=False),
                    invalidation_json=json.dumps(invalidation, ensure_ascii=False),
                    take_profit_zone_json=json.dumps(take_profit, ensure_ascii=False),
                    holding_horizon="short_to_medium",
                    rationale=_clean_fallback_rationale(item.get("rationale")),
                    risk_notes_json=json.dumps(
                        [
                            "Fixed-pool quote/context fallback; not a model-selected ticker",
                            "Must pass independent review and risk gate",
                        ],
                        ensure_ascii=False,
                    ),
                    source_event_ids_json=json.dumps(source_event_ids, ensure_ascii=False),
                    status="pending_review",
                    raw_json=json.dumps(raw_json, ensure_ascii=False),
                )
            )
        )
    return signals


def build_prior_signal_reference_trade_signals(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    prior_rows: Iterable[dict[str, Any]],
    missing_tickers: Iterable[Any],
) -> list[TradeSignalRecord]:
    """Clone recent same-ticker signal rows as stale reference levels for today.

    These rows are intentionally downgraded to low confidence and marked with a
    distinct signal type. They preserve useful prior entry/stop/target levels,
    but the visible rationale must still require same-day confirmation.
    """
    missing = _normalize_ticker_set(missing_tickers) & _FIXED_MARKET_ANALYSIS_TICKERS
    signals: list[TradeSignalRecord] = []
    seen: set[str] = set()
    for row in prior_rows:
        ticker = _normalize_ticker(row.get("ticker"))
        if not ticker or ticker not in missing or ticker in seen:
            continue
        if is_excluded_trade_signal_ticker(ticker):
            continue
        direction = _normalize_direction(row.get("direction"))
        strategy_type = _normalize_strategy_type(row.get("strategy_type"))
        if direction != "long" or strategy_type not in {"swing", "medium"}:
            continue

        market = _normalize_market(row.get("market"))
        idempotency_key = _build_idempotency_key(
            analysis_id=analysis_id,
            analysis_date=analysis_date,
            analysis_slot=analysis_slot,
            market=market,
            ticker=ticker,
            direction=direction,
            strategy_type=strategy_type,
        )
        raw_json = {
            "source": "prior_t_trade_signals",
            "reference_signal_id": row.get("id"),
            "reference_analysis_id": row.get("analysis_id"),
            "reference_analysis_date": row.get("analysis_date"),
            "reference_analysis_slot": row.get("analysis_slot"),
            "reference_updated_at": row.get("updated_at"),
            "guardrail": "Prior signal is stale reference only; same-day price, volume, and news confirmation required.",
        }
        signals.append(
            _with_candidate_metrics(
                TradeSignalRecord(
                    signal_key=f"sig_{idempotency_key[:24]}",
                    idempotency_key=idempotency_key,
                    analysis_id=analysis_id,
                    analysis_date=analysis_date,
                    analysis_slot=analysis_slot,
                    market=market,
                    ticker=ticker,
                    name=_resolve_stock_name(ticker, row.get("name")),
                    signal_type="prior_signal_stock_watch",
                    strategy_type=strategy_type,
                    direction=direction,
                    confidence="low",
                    entry_zone_json=_json_value_or_none(row.get("entry_zone")),
                    invalidation_json=_json_value_or_none(row.get("invalidation")),
                    take_profit_zone_json=_json_value_or_none(row.get("take_profit_zone")),
                    holding_horizon=_clean_text(row.get("holding_horizon")),
                    rationale=_prior_reference_rationale(row),
                    risk_notes_json=_json_value_or_none(row.get("risk_notes")),
                    source_event_ids_json=_json_value_or_none(row.get("source_event_ids")),
                    status="pending_review",
                    raw_json=json.dumps(raw_json, ensure_ascii=False),
                )
            )
        )
        seen.add(ticker)
    return signals


def build_fixed_pool_repair_trade_signals(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    structured_payload: dict[str, Any] | None,
    pipeline_telemetry: dict[str, Any] | None = None,
    events: Iterable[Any] | None = None,
    prior_rows: Iterable[dict[str, Any]] | None = None,
    preferred_tickers: Iterable[Any] | None = None,
    max_signals: int = VISIBLE_RECOMMENDATION_LIMIT,
) -> tuple[list[TradeSignalRecord], dict[str, int]]:
    """Repair internal fixed-pool signals without changing visible reports.

    This is the safe backfill path for cases where a market-analysis row exists
    but the downstream stock-monitor watchlist was never populated. It first
    trusts structured ``stock_watch`` rows, then fills missing reference levels
    from recent quote/context events, and finally clones prior same-ticker
    reference levels for still-missing fixed-pool tickers.
    """
    signals = build_trade_signals_from_analysis(
        analysis_id=analysis_id,
        analysis_date=analysis_date,
        analysis_slot=analysis_slot,
        structured_payload=structured_payload,
        pipeline_telemetry=pipeline_telemetry,
    )
    metrics = {
        "structured_signals": len(signals),
        "quote_fallback_added": 0,
        "prior_signal_references": 0,
        "reference_levels_filled": 0,
    }
    if analysis_slot not in FIXED_POOL_SIGNAL_BACKFILL_SLOTS:
        return signals, metrics

    fallback_signals = build_quote_event_trade_signals(
        analysis_id=analysis_id,
        analysis_date=analysis_date,
        analysis_slot=analysis_slot,
        events=events or [],
        max_signals=max_signals,
        preferred_tickers=preferred_tickers,
    )
    signals, metrics["reference_levels_filled"] = _merge_reference_levels_from_fallbacks(
        signals,
        fallback_signals,
    )

    recommendation_tickers = {
        signal.ticker
        for signal in signals
        if not is_excluded_trade_signal_ticker(signal.ticker)
        if signal.direction == "long" and signal.strategy_type in {"swing", "medium"}
    }
    existing_tickers = {signal.ticker for signal in signals}
    preferred = _normalize_ticker_set(preferred_tickers)
    for fallback_signal in fallback_signals:
        if is_excluded_trade_signal_ticker(fallback_signal.ticker):
            continue
        if (
            len(recommendation_tickers) >= max_signals
            and fallback_signal.ticker not in preferred
        ):
            break
        if fallback_signal.ticker in existing_tickers:
            continue
        signals.append(fallback_signal)
        existing_tickers.add(fallback_signal.ticker)
        if fallback_signal.direction == "long" and fallback_signal.strategy_type in {"swing", "medium"}:
            recommendation_tickers.add(fallback_signal.ticker)
            metrics["quote_fallback_added"] += 1

    signals = [
        signal
        for signal in signals
        if not is_excluded_trade_signal_ticker(signal.ticker)
    ]
    existing_tickers = {signal.ticker for signal in signals}
    missing_tickers = [
        ticker
        for ticker in FIXED_MARKET_ANALYSIS_WATCH_POOL
        if ticker not in existing_tickers and not is_excluded_trade_signal_ticker(ticker)
    ]
    if missing_tickers:
        prior_signals = build_prior_signal_reference_trade_signals(
            analysis_id=analysis_id,
            analysis_date=analysis_date,
            analysis_slot=analysis_slot,
            prior_rows=prior_rows or [],
            missing_tickers=missing_tickers,
        )
        signals.extend(prior_signals)
        metrics["prior_signal_references"] = len(prior_signals)
    return signals, metrics


def _merge_reference_levels_from_fallbacks(
    signals: list[TradeSignalRecord],
    fallback_signals: list[TradeSignalRecord],
) -> tuple[list[TradeSignalRecord], int]:
    """Fill missing structured-signal levels with deterministic fallback levels."""
    fallback_by_ticker = {signal.ticker: signal for signal in fallback_signals}
    merged: list[TradeSignalRecord] = []
    filled = 0
    for signal in signals:
        fallback = fallback_by_ticker.get(signal.ticker)
        if fallback is None:
            merged.append(signal)
            continue

        updates: dict[str, Any] = {}
        if not signal.entry_zone_json and fallback.entry_zone_json:
            updates["entry_zone_json"] = fallback.entry_zone_json
        if not signal.invalidation_json and fallback.invalidation_json:
            updates["invalidation_json"] = fallback.invalidation_json
        if not signal.take_profit_zone_json and fallback.take_profit_zone_json:
            updates["take_profit_zone_json"] = fallback.take_profit_zone_json
        if not signal.holding_horizon and fallback.holding_horizon:
            updates["holding_horizon"] = fallback.holding_horizon
        if not signal.confidence and fallback.confidence:
            updates["confidence"] = fallback.confidence

        if updates:
            filled += 1
            merged.append(replace(signal, **updates))
        else:
            merged.append(signal)
    return merged, filled


def _with_candidate_metrics(signal: TradeSignalRecord) -> TradeSignalRecord:
    """Attach deterministic risk/reward and ranking fields to a signal."""
    risk_reward, risk_reason = _risk_reward_ratio_for_signal(signal)
    reasons: list[str] = []
    if signal.avoid_reason:
        reasons.append(signal.avoid_reason)
    if not _is_trade_direction(signal.direction):
        reasons.append("non_trade_direction")
    if risk_reason:
        reasons.append(risk_reason)
    if risk_reward is not None and risk_reward < MIN_CANDIDATE_RISK_REWARD:
        reasons.append("risk_reward_below_1_5")

    score = _candidate_score(signal, risk_reward, reasons)
    unique_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    return replace(
        signal,
        risk_reward_ratio=round(risk_reward, 4) if risk_reward is not None else None,
        candidate_score=round(score, 4),
        avoid_reason=";".join(unique_reasons) if unique_reasons else None,
    )


def _risk_reward_ratio_for_signal(signal: TradeSignalRecord) -> tuple[float | None, str | None]:
    """Return R multiple using the same level semantics as stock-monitor-service."""
    if not _is_trade_direction(signal.direction):
        return None, None
    is_short = str(signal.direction or "").lower() == "short"
    entry_zone = _json_object_or_none(signal.entry_zone_json)
    invalidation = _json_object_or_none(signal.invalidation_json)
    take_profit = _json_object_or_none(signal.take_profit_zone_json)
    entry = _price_from_object(entry_zone, ("low", "entry", "price") if is_short else ("high", "entry", "price"))
    stop = _price_from_object(invalidation, ("price", "stop", "stop_loss"))
    target = _price_from_object(take_profit, ("first", "target", "price", "take_profit"))
    if entry is None or stop is None or target is None:
        return None, "missing_price_levels"
    risk = stop - entry if is_short else entry - stop
    reward = entry - target if is_short else target - entry
    if risk <= 0 or reward <= 0:
        return None, "invalid_risk_reward"
    return reward / risk, None


def _candidate_score(signal: TradeSignalRecord, risk_reward: float | None, avoid_reasons: list[str]) -> float:
    """Score candidates on a stable 0-100 scale for watchlist ranking."""
    score = 20.0
    if _is_trade_direction(signal.direction):
        score += 15.0
    else:
        score -= 20.0

    strategy = (signal.strategy_type or "").strip().lower()
    if strategy in {"intraday", "swing"}:
        score += 10.0
    elif strategy == "medium":
        score += 6.0

    if signal.entry_zone_json and signal.invalidation_json and signal.take_profit_zone_json:
        score += 20.0

    if risk_reward is not None:
        score += min(max(risk_reward, 0.0), 3.0) / 3.0 * 25.0

    confidence = (signal.confidence or "").strip().lower()
    if confidence == "high":
        score += 12.0
    elif confidence == "medium":
        score += 8.0
    elif confidence == "low":
        score += 2.0

    score += min(_source_event_count(signal.source_event_ids_json), 5) * 2.0

    if avoid_reasons:
        score -= 25.0

    return max(0.0, min(100.0, score))


def _is_trade_direction(direction: Any) -> bool:
    text = str(direction or "").strip().lower()
    return text in {"long", "short"}


def _price_from_object(value: dict[str, Any] | None, keys: tuple[str, ...]) -> float | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        price = _to_float(value.get(key))
        if price is not None:
            return price
    return None


def _source_event_count(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return 0
    if isinstance(value, list):
        return len(value)
    return 1


def _prior_reference_rationale(row: dict[str, Any]) -> str:
    """Build visible stale-reference rationale with explicit confirmation caveats."""
    ref_date = _clean_text(row.get("analysis_date")) or "前次"
    prior_rationale = _clean_text(row.get("rationale")) or ""
    prior_bull = _extract_labeled_reason(
        prior_rationale,
        ("利多", "上漲邏輯", "上漲理由", "多方邏輯"),
    )
    prior_bear = _extract_labeled_reason(
        prior_rationale,
        ("利空", "風險", "下行風險", "低估/補漲", "低估理由", "為什麼被低估", "補漲邏輯"),
    )
    prior_buy = _extract_labeled_reason(
        prior_rationale,
        ("買入注意", "買進注意", "操作注意", "買入理由", "買進理由", "操作理由"),
    )
    if not prior_bull and prior_rationale:
        prior_bull = prior_rationale
    bull = (
        f"沿用 {ref_date} 前次固定池參考：{prior_bull}；今日仍需用盤中量價與新聞風控重新確認。"
        if prior_bull
        else f"沿用 {ref_date} 前次固定池參考，今日仍需用盤中量價與新聞風控重新確認。"
    )
    bear = (
        f"前次條件已過期，且仍需重驗：{prior_bear}。"
        if prior_bear
        else "前次條件已過期，今日若量能不配合、新聞轉弱或跌破停損區，參考價值下降。"
    )
    buy = (
        f"沿用前次條件：{prior_buy}；若今日未回到進場區、量能不配合或新聞轉弱，不追價。"
        if prior_buy
        else "沿用前次進場、停利、停損區作參考；若今日未回到進場區、量能不配合或新聞轉弱，不追價。"
    )
    return f"利多：{bull} 利空：{bear} 買入注意：{buy}"


def _fallback_candidate_from_event(event: Any) -> dict[str, Any] | None:
    """Extract one fallback candidate from supported event-shaped inputs."""
    source = str(getattr(event, "source", "") or "")
    if source == "yfinance_taiwan":
        return _fallback_candidate_from_yfinance_event(event)
    if source.startswith("market_context:"):
        return _fallback_candidate_from_twse_context_event(event)
    return None


def _fallback_candidate_from_yfinance_event(event: Any) -> dict[str, Any] | None:
    """Extract Taiwan quote fallback candidate from legacy yfinance relay events."""
    payload = _json_object_or_none(getattr(event, "summary", None))
    if payload is None:
        raw = _json_object_or_none(getattr(event, "raw_json", None))
        payload = _json_object_or_none((raw or {}).get("summary")) if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return None

    ticker = _normalize_ticker(payload.get("symbol"))
    if not ticker:
        return None
    price = _to_float(payload.get("price"))
    change_pct = _to_float(payload.get("change_pct"))
    if price is None or price <= 0 or change_pct is None:
        return None

    name = _resolve_stock_name(ticker, payload.get("name"))
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "volume": _safe_int(payload.get("volume")),
        "event_row_id": getattr(event, "row_id", None),
        "signal_type": "quote_fallback_stock_watch",
        "source_kind": "yfinance_taiwan_quote_fallback",
        "entry_basis": "latest_yfinance_taiwan_price",
        "as_of": payload.get("last_ts"),
        "rationale": (
            f"{name or ticker} 最新台股報價{_format_change_phrase(change_pct)}，"
            "搭配早盤偏多與AI/半導體主線觀察。"
        ),
    }


def _fallback_candidate_from_twse_context_event(event: Any) -> dict[str, Any] | None:
    """Extract fallback candidate from tracked-stock market context events."""
    raw = _json_object_or_none(getattr(event, "raw_json", None))
    point = raw.get("point") if isinstance(raw, dict) else None
    if not isinstance(point, dict) or point.get("category") != "tw_tracked_stock":
        return None

    raw_point = point.get("raw") if isinstance(point.get("raw"), dict) else {}
    ticker = _normalize_ticker(point.get("symbol") or raw_point.get("Code"))
    if not ticker:
        return None
    price = _to_float(point.get("value") or raw_point.get("ClosingPrice"))
    if price is None or price <= 0:
        return None

    change = _to_float(point.get("change") or raw_point.get("Change"))
    previous = _to_float(point.get("previous_value"))
    if previous is None and change is not None:
        previous = price - change
    change_pct = _to_float(point.get("change_percent"))
    if change_pct is None:
        change_pct = _calculate_change_pct(price=price, previous=previous)

    name = _resolve_stock_name(ticker, point.get("name") or raw_point.get("Name"))
    as_of = _clean_text(point.get("as_of") or raw_point.get("Date"))
    point_source = _clean_text(point.get("source")) or str(getattr(event, "source", "")).split(":", 1)[-1]
    source_label = "TWSE官方收盤基準" if point_source == "twse_openapi" else "市場情境報價"
    source_kind = (
        "twse_openapi_tracked_stock_fallback"
        if point_source == "twse_openapi"
        else f"{point_source}_tracked_stock_fallback"
    )
    entry_basis = (
        "official_twse_tracked_stock_close"
        if point_source == "twse_openapi"
        else "market_context_tracked_stock_price"
    )
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "change_pct": change_pct if change_pct is not None else 0.0,
        "volume": _safe_int(raw_point.get("TradeVolume")),
        "event_row_id": getattr(event, "row_id", None),
        "signal_type": "context_fallback_stock_watch",
        "source_kind": source_kind,
        "entry_basis": entry_basis,
        "as_of": as_of,
        "rationale": (
            f"{name or ticker} {source_label}{_format_change_phrase(change_pct or 0.0)}"
            f"{f'（{as_of}）' if as_of else ''}；需開盤量價確認。"
        ),
    }


def _calculate_change_pct(*, price: float, previous: float | None) -> float | None:
    """Calculate percent change when TWSE context provides price/change only."""
    if previous in (None, 0):
        return None
    return round((price - previous) / previous * 100.0, 2)


def _build_long_fallback_levels(
    *,
    price: float,
    entry_basis: str,
    stop_basis: str,
    target_basis: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build deterministic long fallback levels that satisfy the monitor R gate."""
    entry_zone = {
        "low": _round_tw_price(price * 0.985),
        "high": _round_tw_price(price * 1.005),
        "timing": _DEFAULT_ENTRY_TIMING,
        "basis": entry_basis,
    }
    invalidation = {
        "price": _round_tw_price(price * 0.965),
        "basis": stop_basis,
    }
    entry = float(entry_zone["high"])
    stop = float(invalidation["price"])
    risk = entry - stop
    minimum_first = _round_tw_price_up(entry + risk * MIN_CANDIDATE_RISK_REWARD)
    minimum_second = _round_tw_price_up(entry + risk * 2.0)
    base_first = _round_tw_price(price * 1.04)
    base_second = _round_tw_price(price * 1.08)
    first = max(base_first, minimum_first)
    second = max(base_second, minimum_second, first)
    take_profit = {
        "first": first,
        "second": second,
        "basis": target_basis,
    }
    policy = {
        "min_risk_reward": MIN_CANDIDATE_RISK_REWARD,
        "entry_for_gate": entry,
        "stop_for_gate": stop,
        "base_first_target": base_first,
        "calibrated_first_target": first,
        "calibrated": first != base_first,
    }
    return entry_zone, invalidation, take_profit, policy


def _clean_fallback_rationale(value: Any) -> str:
    """Keep fallback signal text short and remove repeated watchlist boilerplate."""
    text = str(value or "").strip()
    boilerplate = "作為早盤 " + "watchlist 補位"
    for phrase in (f"{boilerplate}；需開盤量價確認。", f"{boilerplate}；需開盤量價確認", boilerplate):
        text = text.replace(phrase, "需開盤量價確認。")
    text = text.replace("需開盤量價確認。；", "需開盤量價確認；")
    if text and "需開盤量價確認" not in text:
        text = f"{text.rstrip('。')}；需開盤量價確認。"
    return text or "需開盤量價確認。"


def sync_trade_signals_from_recent_analyses(
    store: MySqlEventStore,
    *,
    days: int = 14,
    limit: int = 50,
    analysis_id: int | None = None,
    include_fixed_pool_fallback: bool = False,
    event_days: int = 1,
    event_limit: int = 200,
    prior_days: int = 30,
) -> dict[str, int]:
    """Backfill signals from stored market analyses."""
    if analysis_id is not None:
        fetch_one = getattr(store, "fetch_market_analysis_for_signals", None)
        if not callable(fetch_one):
            raise RuntimeError("store does not support analysis-id signal repair")
        row = fetch_one(int(analysis_id))
        rows = [row] if row is not None else []
    else:
        rows = store.fetch_recent_market_analyses_for_signals(days=days, limit=limit)
    recent_events: list[Any] = []
    if include_fixed_pool_fallback:
        fetch_events = getattr(store, "fetch_recent_summary_events", None)
        if callable(fetch_events):
            recent_events = fetch_events(days=max(int(event_days), 1), limit=max(int(event_limit), 1))
    analyses_processed = 0
    analyses_skipped = 0
    signals_stored = 0
    quote_fallback_added = 0
    prior_signal_references = 0
    reference_levels_filled = 0
    for row in rows:
        structured_payload = _json_object_or_none(row.structured_json)
        raw_payload = _json_object_or_none(row.raw_json)
        if not _raw_payload_allows_signal_repair(raw_payload):
            analyses_skipped += 1
            continue
        pipeline_telemetry = raw_payload.get("pipeline_stages") if isinstance(raw_payload, dict) else None
        if include_fixed_pool_fallback:
            prior_rows = []
            if row.analysis_slot in FIXED_POOL_SIGNAL_BACKFILL_SLOTS:
                fetch_prior = getattr(store, "fetch_recent_trade_signal_references", None)
                if callable(fetch_prior):
                    prior_rows = fetch_prior(
                        tickers=FIXED_MARKET_ANALYSIS_WATCH_POOL,
                        exclude_analysis_id=row.row_id,
                        days=max(int(prior_days), 1),
                    )
            signals, metrics = build_fixed_pool_repair_trade_signals(
                analysis_id=row.row_id,
                analysis_date=row.analysis_date,
                analysis_slot=row.analysis_slot,
                structured_payload=structured_payload,
                pipeline_telemetry=pipeline_telemetry,
                events=recent_events,
                prior_rows=prior_rows,
                preferred_tickers=_preferred_tw_fallback_tickers_from_env(),
            )
            quote_fallback_added += metrics["quote_fallback_added"]
            prior_signal_references += metrics["prior_signal_references"]
            reference_levels_filled += metrics["reference_levels_filled"]
        else:
            signals = build_trade_signals_from_analysis(
                analysis_id=row.row_id,
                analysis_date=row.analysis_date,
                analysis_slot=row.analysis_slot,
                structured_payload=structured_payload,
                pipeline_telemetry=pipeline_telemetry,
            )
        signals_stored += store.replace_trade_signals_for_analysis(row.row_id, signals)
        analyses_processed += 1
    return {
        "analyses_processed": analyses_processed,
        "analyses_skipped": analyses_skipped,
        "signals_stored": signals_stored,
        "quote_fallback_added": quote_fallback_added,
        "prior_signal_references": prior_signal_references,
        "reference_levels_filled": reference_levels_filled,
    }


def _raw_payload_allows_signal_repair(raw_payload: dict[str, Any] | None) -> bool:
    """Honor the stored trust gate when repairing signals."""
    if not isinstance(raw_payload, dict):
        return True
    trust_gate = raw_payload.get("trust_gate")
    if not isinstance(trust_gate, dict):
        return True
    return trust_gate.get("signals_allowed") is not False


def _preferred_tw_fallback_tickers_from_env() -> set[str]:
    """Return tickers configured for Taiwan tracked-stock fallback events."""
    result: set[str] = set()
    for raw in str(os.getenv("MARKET_CONTEXT_TW_YAHOO_SYMBOLS") or "").split(","):
        entry = raw.strip()
        if not entry:
            continue
        symbol = entry
        for separator in (":", "|", "="):
            if separator in symbol:
                symbol = symbol.split(separator, 1)[0]
                break
        ticker = _normalize_ticker(symbol)
        if ticker and ticker.isdigit():
            result.add(ticker)
    return result


def build_trade_signal_recommendation_section(recommendations: list[dict[str, Any]]) -> str:
    """Build a deterministic report section from stored trade-signal rows."""
    lines = ["## 今日個股觀察", "固定十檔監控池（t_trade_signals）"]

    visible_recommendations = [
        item
        for item in recommendations
        if not is_excluded_trade_signal_ticker(item.get("ticker"))
        and is_fixed_market_analysis_watch_ticker(item.get("ticker"))
    ]
    rendered_items: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    neutral_added = 0
    for item in visible_recommendations:
        ticker = _normalize_ticker(item.get("ticker"))
        if not ticker or ticker in seen_tickers:
            continue
        rendered_items.append(item)
        seen_tickers.add(ticker)
        if len(rendered_items) >= VISIBLE_RECOMMENDATION_LIMIT:
            break
    for ticker in FIXED_MARKET_ANALYSIS_WATCH_POOL:
        if len(rendered_items) >= VISIBLE_RECOMMENDATION_LIMIT:
            break
        if ticker in seen_tickers or is_excluded_trade_signal_ticker(ticker):
            continue
        rendered_items.append(_neutral_fixed_pool_item(ticker))
        seen_tickers.add(ticker)
        neutral_added += 1
    if neutral_added:
        lines.append("註：沒有完整短中線訊號的固定池股票，以中性觀察列示；等待盤中量價、新聞催化與估值資料確認。")
    rendered = 0
    for idx, item in enumerate(rendered_items, start=1):
        ticker = str(item.get("ticker") or "").strip()
        if not ticker:
            continue
        rendered += 1
        raw_name = _clean_text(item.get("name"))
        name = _resolve_stock_name(ticker, raw_name)
        label = f"{ticker} {name}" if name else ticker
        strategy = _clean_text(item.get("strategy_type")) or "swing/medium"
        confidence = _clean_text(item.get("confidence")) or "unknown"
        entry = _format_zone(item.get("entry_zone")) or "待盤中確認"
        take_profit = _format_zone(item.get("take_profit_zone")) or "待盤中確認"
        invalidation = _format_zone(item.get("invalidation")) or "待盤中確認"
        rationale = _clean_text(item.get("rationale")) or "依早盤分析訊號"
        if raw_name and name and raw_name != name and _SUSPECT_STOCK_NAME_RE.search(raw_name):
            rationale = rationale.replace(raw_name, name)
        bull_case, bear_case, buy_note = _stock_reason_lines(
            ticker=ticker,
            rationale=rationale,
            risk_notes=item.get("risk_notes"),
            strategy=strategy,
            entry=entry,
            take_profit=take_profit,
            invalidation=invalidation,
            confidence=confidence,
        )
        lines.append(
            f"{idx}. {label}｜{_format_action_label(strategy, confidence)}｜"
            f"進場 {entry}｜停利 {take_profit}｜停損 {invalidation}｜信心 {confidence}\n"
            f"   - 利多：{bull_case}\n"
            f"   - 利空：{bear_case}\n"
            f"   - 買入注意：{buy_note}"
        )
    if rendered == 0:
        lines.append("資料缺口：固定十檔目前全數無法呈現；不可硬湊下單。")
    return "\n".join(lines) if len(lines) > 1 else ""


def _neutral_fixed_pool_item(ticker: str) -> dict[str, Any]:
    """Return a neutral visible row for a fixed-pool ticker with no signal."""
    name = _resolve_stock_name(ticker)
    profile = _stock_watch_profile(ticker)
    return {
        "ticker": ticker,
        "name": name,
        "strategy_type": "watch",
        "direction": "watch",
        "confidence": "low",
        "entry_zone": None,
        "take_profit_zone": None,
        "invalidation": None,
        "rationale": (
            f"利多：{profile['bull']}；"
            f"利空：今日缺少個股訊號與報價條件，{profile['bear']}；"
            f"買入注意：{profile['buy_note']}；沒有明確進場區前只列中性觀察。"
        ),
    }


def _stock_watch_profile(ticker: str) -> dict[str, str]:
    """Return ticker-aware fixed-pool context for neutral or thin-evidence rows."""
    normalized = _normalize_ticker(ticker) or ""
    return _FIXED_STOCK_WATCH_PROFILES.get(normalized, _DEFAULT_STOCK_WATCH_PROFILE)


def _stock_reason_lines(
    *,
    ticker: str,
    rationale: str,
    strategy: str,
    entry: str,
    take_profit: str,
    invalidation: str,
    confidence: str,
    risk_notes: Any = None,
) -> tuple[str, str, str]:
    """Split or derive visible stock notes without inventing valuation facts."""
    text = _clean_text(rationale) or "依早盤分析訊號"
    profile = _stock_watch_profile(ticker)
    bull = _extract_labeled_reason(
        text,
        ("利多", "上漲邏輯", "為什麼會漲", "會漲原因", "多方邏輯"),
    ) or text
    bear = _extract_labeled_reason(text, ("利空", "風險", "下行風險", "反方條件"))
    valuation = _extract_labeled_reason(text, ("低估/補漲", "低估理由", "為什麼被低估", "補漲邏輯"))
    risk_text = _format_risk_notes(risk_notes)
    buy = _extract_labeled_reason(
        text,
        ("買入注意", "買進注意", "操作注意", "買入理由", "買進理由", "操作理由"),
    )
    if not bear:
        if risk_text:
            bear = risk_text
        elif valuation:
            bear = f"估值或相對位置仍需重驗：{valuation}；若量能不續或跌破停損區，先降為觀望。"
        elif confidence.strip().lower() == "low":
            bear = f"訊號信心低，且{profile['bear']}"
        else:
            bear = profile["bear"]
    if not buy:
        buy = (
            f"{strategy or 'swing/medium'} 觀察；價格需落在進場區 {entry}，"
            f"風控看停損 {invalidation}，第一段停利看 {take_profit}；信心 {confidence}。"
        )
    return bull, bear, buy


def _extract_labeled_reason(text: str, labels: tuple[str, ...]) -> str | None:
    """Extract a semicolon-separated labeled reason from model rationale."""
    if not text:
        return None
    all_labels = (
        "利多",
        "利空",
        "風險",
        "下行風險",
        "反方條件",
        "買入注意",
        "買進注意",
        "操作注意",
        "上漲邏輯",
        "為什麼會漲",
        "會漲原因",
        "多方邏輯",
        "低估/補漲",
        "低估理由",
        "為什麼被低估",
        "補漲邏輯",
        "買入理由",
        "買進理由",
        "操作理由",
    )
    label_pattern = "|".join(re.escape(label) for label in all_labels)
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*(.*?)(?=(?:[；;]\s*)?(?:{label_pattern})\s*[:：]|$)"
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip(" ；;。")
            return value or None
    return None


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for one-shot signal extraction."""
    parser = argparse.ArgumentParser(description="Extract t_trade_signals from recent t_market_analyses rows")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--analysis-id", type=int, default=None)
    parser.add_argument(
        "--fixed-pool-fallback",
        action="store_true",
        help="Repair fixed-pool signals from recent quote/context events and prior signal references.",
    )
    parser.add_argument("--event-days", type=int, default=1)
    parser.add_argument("--event-limit", type=int, default=200)
    parser.add_argument("--prior-days", type=int, default=30)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main() -> int:
    """Run one-shot trade-signal extraction."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    settings = load_settings(args.env_file)
    if not settings.mysql_enabled:
        raise RuntimeError("trade signal extraction requires RELAY_MYSQL_ENABLED=true")
    store = MySqlEventStore(settings)
    store.initialize()
    result = sync_trade_signals_from_recent_analyses(
        store,
        days=args.days,
        limit=args.limit,
        analysis_id=args.analysis_id,
        include_fixed_pool_fallback=args.fixed_pool_fallback,
        event_days=args.event_days,
        event_limit=args.event_limit,
        prior_days=args.prior_days,
    )
    logger.info("Trade signal extraction result: %s", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _iter_signal_items(structured_payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield supported stock recommendation arrays without reparsing prose."""
    for key in ("trade_ideas", "stock_watch"):
        value = structured_payload.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                yield item


def _stage3_evidence_by_ticker(pipeline_telemetry: dict[str, Any] | None) -> dict[str, list[Any]]:
    """Extract ticker -> evidence_ids from stored stage3 telemetry if present."""
    if not isinstance(pipeline_telemetry, dict):
        return {}
    stage3 = pipeline_telemetry.get("tw_mapping") or pipeline_telemetry.get("stage3_output")
    if not isinstance(stage3, dict):
        return {}
    result: dict[str, list[Any]] = {}
    for item in stage3.get("stock_watch") or []:
        if not isinstance(item, dict):
            continue
        ticker = _normalize_ticker(item.get("ticker"))
        if ticker:
            result[ticker] = _coerce_list(item.get("evidence_ids"))
    return result


def _normalize_ticker(value: Any) -> str | None:
    """Normalize a ticker while rejecting prose-like values."""
    text = _clean_text(value)
    if not text:
        return None
    text = text.upper().replace(".TWO", "").replace(".TW", "")
    return text if _TICKER_RE.match(text) else None


def _normalize_ticker_set(values: Iterable[Any] | None) -> set[str]:
    """Normalize a caller-provided ticker list for ranking and matching."""
    result: set[str] = set()
    for value in values or []:
        ticker = _normalize_ticker(value)
        if ticker:
            result.add(ticker)
    return result


def excluded_trade_signal_tickers_from_env() -> set[str]:
    """Return tickers that should never appear in visible stock analysis."""
    raw = os.getenv("MARKET_ANALYSIS_EXCLUDED_TICKERS")
    if raw is None:
        raw = _DEFAULT_EXCLUDED_TICKERS
    values = [part for part in re.split(r"[,;\s]+", raw) if part]
    return _normalize_ticker_set(values)


def is_excluded_trade_signal_ticker(value: Any) -> bool:
    ticker = _normalize_ticker(value)
    return bool(ticker and ticker in excluded_trade_signal_tickers_from_env())


def is_fixed_market_analysis_watch_ticker(value: Any) -> bool:
    ticker = _normalize_ticker(value)
    return bool(ticker and ticker in _FIXED_MARKET_ANALYSIS_TICKERS)


def _resolve_stock_name(ticker: Any, value: Any = None) -> str | None:
    """Prefer a Traditional Chinese stock name when the row only has a ticker."""
    provided = _clean_text(value)
    normalized = _normalize_ticker(ticker)
    canonical = _TW_STOCK_NAME_BY_TICKER.get(normalized or "")
    if canonical and (
        not provided
        or _SUSPECT_STOCK_NAME_RE.search(provided)
        or not _CJK_RE.search(provided)
    ):
        return canonical
    return provided


def _normalize_market(value: Any) -> str:
    """Default analysis stock-watch output to Taiwan market."""
    text = _clean_text(value)
    if not text:
        return "TW"
    upper = text.upper()
    if upper in {"TW", "TSE", "TWSE"}:
        return "TW"
    if upper in {"TPEX", "OTC"}:
        return "TPEx"
    return upper


def _normalize_direction(value: Any) -> str:
    """Map analysis direction into execution-neutral signal direction."""
    text = (_clean_text(value) or "watch").lower()
    return _DIRECTION_MAP.get(text, "watch")


def _normalize_strategy_type(value: Any) -> str:
    """Keep strategy coarse; detailed rules belong to review/risk layers."""
    text = (_clean_text(value) or "").lower()
    if text in {"intraday", "daytrade", "day_trade", "當沖"} or "intraday" in text or "當沖" in text:
        return "intraday"
    if text in {"swing", "short_term", "短線"} or "swing" in text or "短" in text:
        return "swing"
    if text in {"medium", "medium_term", "中線"} or "medium" in text or "中" in text:
        return "medium"
    return "watch"


def _build_idempotency_key(
    *,
    analysis_id: int,
    analysis_date: str,
    analysis_slot: str,
    market: str,
    ticker: str,
    direction: str,
    strategy_type: str,
) -> str:
    """Stable duplicate guard for analysis-derived signals."""
    raw = "|".join(
        [
            str(int(analysis_id)),
            analysis_date.strip(),
            analysis_slot.strip(),
            market.strip().upper(),
            ticker.strip().upper(),
            direction.strip().lower(),
            strategy_type.strip().lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    """Return the first present value among compatible field aliases."""
    for key in keys:
        if key in item and item.get(key) not in (None, ""):
            return item.get(key)
    return None


def _coerce_list(value: Any) -> list[Any]:
    """Return list-like values as a compact list."""
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _json_or_none(value: Any) -> str | None:
    """Serialize structured optional fields for MySQL JSON columns."""
    if value in (None, "", []):
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_value_or_none(value: Any) -> str | None:
    """Keep existing JSON text or serialize structured optional fields."""
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return json.dumps(value, ensure_ascii=False)


def _format_risk_notes(value: Any) -> str | None:
    """Render stored risk notes as one compact bear-case sentence."""
    if value in (None, "", []):
        return None
    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
    if isinstance(parsed, list):
        notes = [_clean_text(item) for item in parsed]
        notes = [item for item in notes if item]
        return "；".join(notes) if notes else None
    if isinstance(parsed, dict):
        notes = []
        for key, item in parsed.items():
            text = _clean_text(item)
            if text:
                notes.append(f"{key}:{text}")
        return "；".join(notes) if notes else None
    return _clean_text(parsed)


def _clean_text(value: Any) -> str | None:
    """Trim scalar values and drop empty strings."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_object_or_none(value: str | None) -> dict[str, Any] | None:
    """Parse a JSON object string and ignore arrays/scalars."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_float(value: Any) -> float | None:
    """Return a float when the quote payload contains a numeric value."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _safe_int(value: Any) -> int:
    """Best-effort int conversion for ranking and trace IDs."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "").strip()))
        except ValueError:
            return 0
    return 0


def _tw_price_tick(value: float) -> float:
    if value < 10:
        return 0.01
    if value < 50:
        return 0.05
    if value < 100:
        return 0.1
    if value < 500:
        return 0.5
    if value < 1000:
        return 1.0
    return 5.0


def _round_tw_price(value: float) -> float:
    """Round reference levels to common Taiwan stock tick sizes."""
    tick = _tw_price_tick(value)
    rounded = round(value / tick) * tick
    return round(rounded, 2)


def _round_tw_price_up(value: float) -> float:
    """Round up to a Taiwan tick so minimum target math stays conservative."""
    rounded = _round_tw_price(value)
    if rounded < value:
        rounded += _tw_price_tick(max(value, rounded))
    return round(rounded, 2)


def _format_change_phrase(change_pct: float) -> str:
    """Format quote movement without implying weak names are rising."""
    if change_pct > 0:
        return f"上漲 {change_pct:.2f}%"
    if change_pct < 0:
        return f"下跌 {abs(change_pct):.2f}%"
    return "持平"


def _format_strategy_label(value: str) -> str:
    """Convert internal strategy labels into user-facing Chinese text."""
    normalized = (value or "").strip().lower()
    if normalized == "swing":
        return "波段"
    if normalized == "medium":
        return "中線"
    if normalized == "intraday":
        return "當沖"
    if normalized == "short_to_medium":
        return "短中線"
    return value or "短中線"


def _format_action_label(strategy: str, confidence: str) -> str:
    """Render a fixed-pool watch row without recommendation wording."""
    normalized = (strategy or "").strip().lower()
    if normalized == "watch":
        return "中性觀察" if (confidence or "").strip().lower() == "low" else "觀察"
    label = _format_strategy_label(strategy)
    if (confidence or "").strip().lower() == "low":
        return f"低信心{label}觀察"
    return f"{label}觀察"


def _format_zone(value: Any) -> str | None:
    """Format JSON/string price zones for human-readable analysis sections."""
    if value in (None, "", []):
        return None
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value.strip() or None
    if isinstance(parsed, dict):
        parts = [
            f"{key}:{_format_scalar(val)}"
            for key, val in parsed.items()
            if key not in {"basis", "source", "note", "timing", "time", "condition", "entry_timing"}
            and val not in (None, "")
        ]
        return ", ".join(parts) or None
    if isinstance(parsed, list):
        return ", ".join(str(item) for item in parsed if item not in (None, "")) or None
    return str(parsed).strip() or None


def _format_entry_timing(value: Any) -> str:
    """Return visible entry timing/condition for the recommendation line."""
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return _DEFAULT_ENTRY_TIMING
    if isinstance(parsed, dict):
        for key in ("timing", "entry_timing", "condition", "time"):
            text = _clean_text(parsed.get(key))
            if text:
                return text
    return _DEFAULT_ENTRY_TIMING


def _format_scalar(value: Any) -> str:
    """Format scalar values without noisy trailing decimals."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
