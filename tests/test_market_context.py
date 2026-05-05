from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_relay.market_context import (
    FredSeriesSpec,
    MarketContextConfig,
    MarketContextPoint,
    SourceFailure,
    TaiwanYahooSymbol,
    _parse_fred_csv,
    _parse_treasury_yield_curve_xml,
    _parse_tw_yahoo_symbols,
    _parse_yahoo_chart_payload,
    build_market_context_events,
    build_summary,
    fetch_fred_points,
    fetch_yahoo_tracked_tw_points,
    run_once,
)


class _FakeStore:
    """封裝 Fake Store 相關資料與行為。"""
    def __init__(self, _settings) -> None:
        """初始化物件狀態與必要依賴。"""
        self.events = []

    def initialize(self) -> None:
        """執行 initialize 方法的主要邏輯。"""
        return None

    def enqueue_event_if_new(self, event) -> bool:
        """執行 enqueue event if new 方法的主要邏輯。"""
        self.events.append(event)
        _FakeStore.events.append(event)
        return True


_FakeStore.events = []


class MarketContextTests(unittest.TestCase):
    """封裝 Market Context Tests 相關資料與行為。"""
    def test_parse_yahoo_chart_payload_builds_point(self) -> None:
        """測試 test parse yahoo chart payload builds point 的預期行為。"""
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "^SOX",
                            "regularMarketPrice": 9555.88,
                            "chartPreviousClose": 9329.35,
                            "regularMarketTime": 1776585600,
                            "currency": "USD",
                        }
                    }
                ]
            }
        }

        point = _parse_yahoo_chart_payload(payload, "PHLX Semiconductor", "semiconductor", "https://example.com")

        self.assertIsNotNone(point)
        assert point is not None
        self.assertEqual(point.source, "yahoo_chart")
        self.assertEqual(point.symbol, "^SOX")
        self.assertAlmostEqual(point.change or 0, 226.53, places=2)
        self.assertGreater(point.change_percent or 0, 2.0)

    def test_parse_tw_yahoo_symbols_supports_tpex_suffix(self) -> None:
        """台股 Yahoo fallback 可宣告上市 .TW 與上櫃 .TWO。"""
        items = _parse_tw_yahoo_symbols("2485.TW:兆赫,4749.TWO:新應材,2351")

        self.assertEqual([item.symbol for item in items], ["2485.TW", "4749.TWO", "2351.TW"])
        self.assertEqual([item.name for item in items], ["兆赫", "新應材", "2351"])

    def test_fetch_yahoo_tracked_tw_points_skips_official_twse_codes(self) -> None:
        """官方 TWSE 已有資料時，Yahoo fallback 只補缺口個股。"""
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "4749.TWO",
                            "regularMarketPrice": 205.5,
                            "chartPreviousClose": 200.0,
                            "regularMarketTime": 1776585600,
                            "currency": "TWD",
                        }
                    }
                ]
            }
        }

        with patch("event_relay.market_context.http_get_json", return_value=payload) as fake_get:
            points, failures = fetch_yahoo_tracked_tw_points(
                5,
                (
                    TaiwanYahooSymbol("2485.TW", "兆赫"),
                    TaiwanYahooSymbol("4749.TWO", "新應材"),
                ),
                skip_codes={"2485"},
            )

        self.assertEqual(failures, [])
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].symbol, "4749.TWO")
        self.assertEqual(points[0].category, "tw_tracked_stock")
        fake_get.assert_called_once()

    def test_parse_treasury_yield_curve_xml_uses_latest_record(self) -> None:
        """測試 test parse treasury yield curve xml uses latest record 的預期行為。"""
        xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
      xmlns="http://www.w3.org/2005/Atom">
  <entry><content><m:properties>
    <d:NEW_DATE>2026-04-16T00:00:00</d:NEW_DATE>
    <d:BC_2YEAR>3.60</d:BC_2YEAR><d:BC_10YEAR>4.20</d:BC_10YEAR><d:BC_30YEAR>4.70</d:BC_30YEAR>
  </m:properties></content></entry>
  <entry><content><m:properties>
    <d:NEW_DATE>2026-04-17T00:00:00</d:NEW_DATE>
    <d:BC_2YEAR>3.71</d:BC_2YEAR><d:BC_10YEAR>4.26</d:BC_10YEAR><d:BC_30YEAR>4.83</d:BC_30YEAR>
  </m:properties></content></entry>
</feed>"""

        points = _parse_treasury_yield_curve_xml(xml)

        self.assertEqual(len(points), 4)
        ten_year = next(point for point in points if point.symbol == "BC_10YEAR")
        spread = next(point for point in points if point.symbol == "US10Y2Y")
        self.assertEqual(ten_year.value, 4.26)
        self.assertAlmostEqual(spread.value or 0, 55.0)

    def test_parse_fred_csv_uses_latest_observation(self) -> None:
        """FRED CSV parsing keeps latest value and previous-period delta."""
        csv_text = """observation_date,DFEDTARU
2026-04-29,3.75
2026-04-30,3.75
2026-05-01,3.50
"""
        spec = FredSeriesSpec("DFEDTARU", "Fed Target Range Upper Limit", "fed_path", "percent")

        point = _parse_fred_csv(csv_text, spec)

        self.assertIsNotNone(point)
        assert point is not None
        self.assertEqual(point.source, "fred")
        self.assertEqual(point.category, "fed_path")
        self.assertEqual(point.symbol, "DFEDTARU")
        self.assertEqual(point.value, 3.50)
        self.assertEqual(point.previous_value, 3.75)
        self.assertAlmostEqual(point.change or 0, -0.25)

    def test_fetch_fred_points_reports_unknown_series(self) -> None:
        """Unknown configured FRED ids are explicit failures, not silent skips."""
        with patch("event_relay.market_context.http_get_text", return_value="observation_date,SOFR\n2026-05-01,3.66\n"):
            points, failures = fetch_fred_points(5, ("SOFR", "UNKNOWN_SERIES"))

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].symbol, "SOFR")
        self.assertEqual(len(failures), 1)
        self.assertIn("unknown", failures[0].error)

    def test_build_summary_mentions_key_sections(self) -> None:
        """測試 test build summary mentions key sections 的預期行為。"""
        points = [
            MarketContextPoint("yahoo_chart", "us_equity_index", "NASDAQ 100", "^NDX", 100.0, 99.0, 1.0, 1.01, "USD", None, "", {}),
            MarketContextPoint("yahoo_chart", "semiconductor", "PHLX Semiconductor", "^SOX", 100.0, 98.0, 2.0, 2.04, "USD", None, "", {}),
            MarketContextPoint("yahoo_chart", "volatility", "VIX", "^VIX", 17.5, 18.0, -0.5, -2.7, "USD", None, "", {}),
            MarketContextPoint("us_treasury", "rates", "US Treasury 10Y", "BC_10YEAR", 4.26, None, None, None, "percent", None, "", {}),
            MarketContextPoint("us_treasury", "rates_spread", "US Treasury 10Y-2Y Spread", "US10Y2Y", 55.0, None, None, None, "bp", None, "", {}),
            MarketContextPoint("fred", "fed_path", "Fed Target Range Upper Limit", "DFEDTARU", 3.75, 3.75, 0.0, 0.0, "percent", "2026-04-30", "", {}),
            MarketContextPoint("fred", "liquidity", "Reserve Balances", "WRESBAL", 2918599.0, 2910000.0, 8599.0, 0.3, "usd_millions", "2026-04-29", "", {}),
            MarketContextPoint("fred", "credit_stress", "US High Yield Option-Adjusted Spread", "BAMLH0A0HYM2", 2.83, 2.90, -0.07, -2.4, "percent", "2026-04-30", "", {}),
        ]

        summary = build_summary(points, [SourceFailure("test", "boom")], datetime(2026, 4, 20, tzinfo=timezone.utc))
        self.assertIn("Fed/liquidity", summary)
        self.assertIn("Credit/stress", summary)

        self.assertIn("早盤市場情境資料包", summary)
        self.assertIn("美股風險", summary)
        self.assertIn("利率", summary)
        self.assertIn("來源錯誤: 1", summary)

    def test_build_market_context_events_marks_events_stored_only(self) -> None:
        """測試 test build market context events marks events stored only 的預期行為。"""
        points = [
            MarketContextPoint("yahoo_chart", "us_equity_index", "NASDAQ 100", "^NDX", 100.0, 99.0, 1.0, 1.01, "USD", None, "https://example.com", {})
        ]
        config = MarketContextConfig(
            env_file=".env",
            analysis_slot="market_context_pre_tw_open",
            scheduled_time_local="07:20",
            timeout_seconds=5,
            twse_codes=["2330"],
        )

        events = build_market_context_events(points, [], config, datetime(2026, 4, 20, tzinfo=timezone.utc))

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].source, "market_context:yahoo_chart")
        self.assertTrue(events[0].raw["stored_only"])
        self.assertEqual(events[0].raw["event_type"], "market_context_point")
        self.assertEqual(events[-1].source, "market_context:collector")

    def test_run_once_writes_relay_events(self) -> None:
        """測試 test run once writes relay events 的預期行為。"""
        _FakeStore.events = []
        points = [
            MarketContextPoint("yahoo_chart", "us_equity_index", "NASDAQ 100", "^NDX", 100.0, 99.0, 1.0, 1.01, "USD", None, "", {})
        ]
        config = MarketContextConfig(
            env_file=".env",
            analysis_slot="market_context_pre_tw_open",
            scheduled_time_local="07:20",
            timeout_seconds=5,
            twse_codes=["2330"],
        )

        with patch("event_relay.market_context.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
            with patch("event_relay.market_context.MySqlEventStore", _FakeStore):
                with patch("event_relay.market_context.collect_market_context", return_value=(points, [])):
                    result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["analysis_slot"], "market_context_pre_tw_open")
        self.assertEqual(result["points"], 1)
        self.assertEqual(result["events"], 2)
        self.assertEqual(result["stored"], 2)
        self.assertEqual(len(_FakeStore.events), 2)
        self.assertEqual(_FakeStore.events[0].source, "market_context:yahoo_chart")


if __name__ == "__main__":
    unittest.main()
