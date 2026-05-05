from datetime import date, datetime, timezone
import unittest

from event_relay.market_calendar import (
    allowed_analysis_slots,
    is_tw_trading_day,
    is_us_trading_day,
    resolve_market_calendar_state,
)


class MarketCalendarTests(unittest.TestCase):
    def test_tw_labor_day_closed_us_previous_session_open(self) -> None:
        state = resolve_market_calendar_state(datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc))

        self.assertFalse(state.tw.is_trading_day)
        self.assertEqual(state.tw.holiday_name, "TWSE Labor Day")
        self.assertTrue(state.us.is_trading_day)
        self.assertEqual(allowed_analysis_slots(state), {"us_close"})

    def test_us_labor_day_previous_session_closed_tw_open(self) -> None:
        state = resolve_market_calendar_state(datetime(2026, 9, 8, 8, 0, tzinfo=timezone.utc))

        self.assertTrue(state.tw.is_trading_day)
        self.assertFalse(state.us.is_trading_day)
        self.assertEqual(state.us.holiday_name, "NYSE Labor Day")
        self.assertEqual(allowed_analysis_slots(state), {"pre_tw_open", "tw_close"})

    def test_both_markets_closed_routes_to_macro_daily(self) -> None:
        state = resolve_market_calendar_state(datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc))

        self.assertFalse(state.tw.is_trading_day)
        self.assertFalse(state.us.is_trading_day)
        self.assertEqual(allowed_analysis_slots(state), {"macro_daily"})

    def test_sunday_routes_to_weekly_only(self) -> None:
        state = resolve_market_calendar_state(datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc))

        self.assertTrue(state.is_sunday_local)
        self.assertEqual(allowed_analysis_slots(state), set())

    def test_known_us_and_tw_holidays(self) -> None:
        self.assertFalse(is_us_trading_day(date(2026, 4, 3)).is_trading_day)
        self.assertFalse(is_us_trading_day(date(2026, 12, 25)).is_trading_day)
        self.assertFalse(is_tw_trading_day(date(2026, 5, 1)).is_trading_day)


if __name__ == "__main__":
    unittest.main()
