"""Detect significant price/volume moves from a market quote snapshot.

Pure functions only — no DB, no network. Given a current snapshot plus
historical context (prev_close, n-day average volume), classify which
movement events to emit. Each emitted event is a standardised dict ready
to be wrapped as a ``RelayEvent`` and written to ``t_relay_events``.

Event taxonomy (per REQ-019 acceptance):
  - gap_up / gap_down       : |open - prev_close| / prev_close >= gap_threshold
  - sharp_up / sharp_down   : |change_pct| >= sharp_threshold
  - volume_spike            : volume >= n_day_avg_volume * volume_multiple

Dedupe key is stable per (market, symbol, trade_date, event_type), so the
same gap fires once per day even if the detector runs every minute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SOURCE_PREFIX = "market_quote"
DIMENSION = "market_quote"


@dataclass(frozen=True)
class MovementThresholds:
    gap_pct: float = 0.01           # 1% gap vs prev_close
    sharp_pct: float = 0.03         # 3% intraday move
    volume_multiple: float = 2.0    # 2x n-day avg


@dataclass(frozen=True)
class QuoteContext:
    """Historical context needed for detection. All optional."""
    prev_close: float | None = None
    n_day_avg_volume: float | None = None
    n_day_window: int = 20


def detect_movement_events(
    *,
    symbol: str,
    market: str,
    session: str,
    trade_date: str,
    open_price: float | None,
    last_price: float | None,
    volume: int | None,
    context: QuoteContext,
    thresholds: MovementThresholds | None = None,
) -> list[dict[str, Any]]:
    """Return zero or more movement event dicts based on snapshot + context.

    Each dict has keys: event_id, source, title, summary, raw_json (dict).
    Caller wraps into RelayEvent and writes to t_relay_events.
    """
    th = thresholds or MovementThresholds()
    events: list[dict[str, Any]] = []

    gap = _classify_gap(open_price, context.prev_close, th.gap_pct)
    if gap is not None:
        events.append(
            _build_event(
                event_type=gap,
                symbol=symbol,
                market=market,
                session=session,
                trade_date=trade_date,
                metric={
                    "open": open_price,
                    "prev_close": context.prev_close,
                    "gap_pct": _pct_change(open_price, context.prev_close),
                },
            )
        )

    sharp = _classify_sharp(last_price, context.prev_close, th.sharp_pct)
    if sharp is not None:
        events.append(
            _build_event(
                event_type=sharp,
                symbol=symbol,
                market=market,
                session=session,
                trade_date=trade_date,
                metric={
                    "last": last_price,
                    "prev_close": context.prev_close,
                    "change_pct": _pct_change(last_price, context.prev_close),
                },
            )
        )

    if _is_volume_spike(volume, context.n_day_avg_volume, th.volume_multiple):
        events.append(
            _build_event(
                event_type="volume_spike",
                symbol=symbol,
                market=market,
                session=session,
                trade_date=trade_date,
                metric={
                    "volume": volume,
                    "n_day_avg_volume": context.n_day_avg_volume,
                    "volume_ratio": (volume / context.n_day_avg_volume)
                        if context.n_day_avg_volume else None,
                    "n_day_window": context.n_day_window,
                },
            )
        )

    return events


def build_event_id(market: str, symbol: str, trade_date: str, event_type: str) -> str:
    return f"market-quote-{market.lower()}-{symbol.lower()}-{trade_date}-{event_type}"


def _classify_gap(
    open_price: float | None, prev_close: float | None, threshold: float
) -> str | None:
    pct = _pct_change(open_price, prev_close)
    if pct is None:
        return None
    if pct >= threshold:
        return "gap_up"
    if pct <= -threshold:
        return "gap_down"
    return None


def _classify_sharp(
    last_price: float | None, prev_close: float | None, threshold: float
) -> str | None:
    pct = _pct_change(last_price, prev_close)
    if pct is None:
        return None
    if pct >= threshold:
        return "sharp_up"
    if pct <= -threshold:
        return "sharp_down"
    return None


def _is_volume_spike(
    volume: int | None, n_day_avg: float | None, multiple: float
) -> bool:
    if volume is None or n_day_avg is None or n_day_avg <= 0:
        return False
    return volume >= n_day_avg * multiple


def _pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return (current - base) / base


def _build_event(
    *,
    event_type: str,
    symbol: str,
    market: str,
    session: str,
    trade_date: str,
    metric: dict[str, Any],
) -> dict[str, Any]:
    event_id = build_event_id(market, symbol, trade_date, event_type)
    title = f"{market.upper()} {symbol} {event_type}"
    summary_bits = [f"{event_type}", f"symbol={symbol}", f"date={trade_date}"]
    pct = metric.get("change_pct") or metric.get("gap_pct")
    if pct is not None:
        summary_bits.append(f"change={pct:+.2%}")
    ratio = metric.get("volume_ratio")
    if ratio is not None:
        summary_bits.append(f"vol={ratio:.1f}x")
    summary = "; ".join(summary_bits)

    return {
        "event_id": event_id,
        "source": f"{SOURCE_PREFIX}:{market.lower()}",
        "title": title,
        "summary": summary,
        "raw_json": {
            "dimension": DIMENSION,
            "event_type": event_type,
            "symbol": symbol,
            "market": market,
            "session": session,
            "trade_date": trade_date,
            "metric": metric,
            "stored_only": False,
        },
    }
