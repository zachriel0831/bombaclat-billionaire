"""Built-in market calendar rules for scheduled analysis routing.

The calendar is intentionally small and explicit.  It covers the 2026
Taiwan / U.S. market holidays needed by the local scheduler, and falls back
to weekday-only behavior when a future year has not been refreshed yet.

Source pages checked 2026-04-30:
- TWSE holiday schedule: https://www.twse.com.tw/en/trading/holiday.html
- NYSE holidays and trading hours: https://www.nyse.com/trade/hours-calendars
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


TW_MARKET_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "TWSE New Year holiday",
    date(2026, 2, 12): "TWSE no trading, settlement only before Lunar New Year",
    date(2026, 2, 13): "TWSE no trading, settlement only before Lunar New Year",
    date(2026, 2, 15): "TWSE Lunar New Year holiday",
    date(2026, 2, 16): "TWSE Lunar New Year holiday",
    date(2026, 2, 17): "TWSE Lunar New Year holiday",
    date(2026, 2, 18): "TWSE Lunar New Year holiday",
    date(2026, 2, 19): "TWSE Lunar New Year holiday",
    date(2026, 2, 20): "TWSE Lunar New Year make-up holiday",
    date(2026, 2, 27): "TWSE Peace Memorial Day observed",
    date(2026, 2, 28): "TWSE Peace Memorial Day",
    date(2026, 4, 3): "TWSE Children's Day observed",
    date(2026, 4, 4): "TWSE Children's Day",
    date(2026, 4, 5): "TWSE Qingming Festival",
    date(2026, 4, 6): "TWSE Qingming Festival observed",
    date(2026, 5, 1): "TWSE Labor Day",
    date(2026, 6, 19): "TWSE Dragon Boat Festival",
    date(2026, 9, 25): "TWSE Mid-Autumn Festival",
    date(2026, 9, 28): "TWSE Teachers' Day",
    date(2026, 10, 9): "TWSE National Day observed",
    date(2026, 10, 10): "TWSE National Day",
    date(2026, 10, 25): "TWSE Taiwan Restoration Day",
    date(2026, 10, 26): "TWSE Taiwan Restoration Day observed",
    date(2026, 12, 25): "TWSE Constitution Day",
}

US_MARKET_HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "NYSE New Year's Day",
    date(2026, 1, 19): "NYSE Martin Luther King Jr. Day",
    date(2026, 2, 16): "NYSE Washington's Birthday",
    date(2026, 4, 3): "NYSE Good Friday",
    date(2026, 5, 25): "NYSE Memorial Day",
    date(2026, 6, 19): "NYSE Juneteenth",
    date(2026, 7, 3): "NYSE Independence Day observed",
    date(2026, 9, 7): "NYSE Labor Day",
    date(2026, 11, 26): "NYSE Thanksgiving Day",
    date(2026, 12, 25): "NYSE Christmas Day",
}

TW_MARKET_HOLIDAYS_BY_YEAR = {2026: TW_MARKET_HOLIDAYS_2026}
US_MARKET_HOLIDAYS_BY_YEAR = {2026: US_MARKET_HOLIDAYS_2026}


@dataclass(frozen=True)
class TradingDayStatus:
    """One market's open/closed status for a specific trade date."""

    market: str
    trade_date: date
    is_trading_day: bool
    reason: str
    holiday_name: str | None = None
    calendar_year_supported: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "trade_date": self.trade_date.isoformat(),
            "is_trading_day": self.is_trading_day,
            "reason": self.reason,
            "holiday_name": self.holiday_name,
            "calendar_year_supported": self.calendar_year_supported,
        }


@dataclass(frozen=True)
class MarketCalendarState:
    """Local-day calendar state used by analysis slot routing."""

    local_date: date
    us_close_session_date: date
    is_sunday_local: bool
    tw: TradingDayStatus
    us: TradingDayStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_date": self.local_date.isoformat(),
            "us_close_session_date": self.us_close_session_date.isoformat(),
            "is_sunday_local": self.is_sunday_local,
            "tw": self.tw.to_dict(),
            "us": self.us.to_dict(),
            "allowed_analysis_slots": sorted(allowed_analysis_slots(self)),
        }


def is_tw_trading_day(day: date) -> TradingDayStatus:
    """Return TWSE trading status for the given Taiwan local date."""

    holidays = TW_MARKET_HOLIDAYS_BY_YEAR.get(day.year)
    if day.weekday() >= 5:
        return TradingDayStatus("TW", day, False, "weekend", _holiday_name(holidays, day), holidays is not None)
    if holidays is None:
        return TradingDayStatus("TW", day, True, "weekday_calendar_year_missing", None, False)
    holiday_name = holidays.get(day)
    if holiday_name:
        return TradingDayStatus("TW", day, False, "holiday", holiday_name, True)
    return TradingDayStatus("TW", day, True, "regular_trading_day", None, True)


def is_us_trading_day(day: date) -> TradingDayStatus:
    """Return NYSE trading status for the U.S. session date."""

    holidays = US_MARKET_HOLIDAYS_BY_YEAR.get(day.year)
    if day.weekday() >= 5:
        return TradingDayStatus("US", day, False, "weekend", _holiday_name(holidays, day), holidays is not None)
    if holidays is None:
        return TradingDayStatus("US", day, True, "weekday_calendar_year_missing", None, False)
    holiday_name = holidays.get(day)
    if holiday_name:
        return TradingDayStatus("US", day, False, "holiday", holiday_name, True)
    return TradingDayStatus("US", day, True, "regular_trading_day", None, True)


def resolve_market_calendar_state(now_local: datetime) -> MarketCalendarState:
    """Build routing state for the Taiwan-local scheduler timestamp."""

    local_day = now_local.date()
    # 中文：台北早上產生的 us_close 對應前一個美股交易日，不是台北當天。
    us_session_day = local_day - timedelta(days=1)
    return MarketCalendarState(
        local_date=local_day,
        us_close_session_date=us_session_day,
        is_sunday_local=local_day.weekday() == 6,
        tw=is_tw_trading_day(local_day),
        us=is_us_trading_day(us_session_day),
    )


def allowed_analysis_slots(state: MarketCalendarState) -> set[str]:
    """Return the only analysis slots allowed for the local calendar state."""

    # 中文：週日只做 weekly_summary；daily market-analysis 全部跳過。
    if state.is_sunday_local:
        return set()
    # 中文：兩邊都開時照常產生美股收盤、台股早盤、台股收盤分析。
    if state.tw.is_trading_day and state.us.is_trading_day:
        return {"us_close", "pre_tw_open", "tw_close"}
    # 中文：TW 休、US 開時只產生 us_close，且該列會讓 Java 可推送。
    if not state.tw.is_trading_day and state.us.is_trading_day:
        return {"us_close"}
    # 中文：US 休、TW 開時只做台股分析；此時 prompt 不應帶舊的 us_close。
    if state.tw.is_trading_day and not state.us.is_trading_day:
        return {"pre_tw_open", "tw_close"}
    # 中文：TW/US 都休市時只做 macro_daily，避免送出舊市場摘要。
    return {"macro_daily"}


def _holiday_name(holidays: dict[date, str] | None, day: date) -> str | None:
    if holidays is None:
        return None
    return holidays.get(day)
