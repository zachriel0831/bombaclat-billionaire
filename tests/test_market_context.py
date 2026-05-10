from datetime import datetime, timezone
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from event_relay.market_context import (
    FredSeriesSpec,
    MarketContextConfig,
    MarketContextPoint,
    SourceFailure,
    TaiwanYahooSymbol,
    _build_ai_capex_point,
    _parse_eia_crude_stocks_payload,
    _parse_fred_csv,
    _parse_treasury_yield_curve_xml,
    _parse_tw_yahoo_symbols,
    _parse_yahoo_chart_payload,
    _parse_yahoo_daily_series,
    build_market_context_events,
    build_market_scorecard,
    build_summary,
    fetch_ai_capex_points,
    fetch_eia_crude_stocks_point,
    fetch_fred_points,
    fetch_market_breadth_points,
    fetch_oil_supply_demand_points,
    fetch_yahoo_tracked_tw_points,
    run_once,
)


class _FakeStore:
    """Minimal in-memory store used by run_once tests."""

    events = []

    def __init__(self, _settings) -> None:
        self.events = []

    def initialize(self) -> None:
        return None

    def enqueue_event_if_new(self, event) -> bool:
        self.events.append(event)
        _FakeStore.events.append(event)
        return True


def _yahoo_payload(symbol: str, closes: list[float]) -> dict:
    timestamps = [1776000000 + index * 86400 for index in range(len(closes))]
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": symbol,
                        "regularMarketPrice": closes[-1],
                        "chartPreviousClose": closes[-2] if len(closes) >= 2 else closes[-1],
                        "regularMarketTime": timestamps[-1],
                        "currency": "USD",
                    },
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


def _companyfacts_payload(capex_values: tuple[float, float] = (72_000_000_000, 55_000_000_000)) -> dict:
    latest, previous = capex_values
    return {
        "facts": {
            "us-gaap": {
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-01",
                                "end": "2025-12-31",
                                "val": latest,
                            },
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-01",
                                "end": "2024-12-31",
                                "val": previous,
                            },
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-01",
                                "end": "2025-12-31",
                                "val": 120_000_000_000,
                            }
                        ]
                    }
                },
            }
        }
    }


def _context_point(
    symbol: str,
    value: float,
    *,
    source: str = "fred",
    category: str = "test",
    name: str | None = None,
    previous_value: float | None = None,
    change: float | None = None,
    change_percent: float | None = None,
    unit: str = "index",
    as_of: str = "2026-05-04",
    raw: dict | None = None,
) -> MarketContextPoint:
    return MarketContextPoint(
        source=source,
        category=category,
        name=name or symbol,
        symbol=symbol,
        value=value,
        previous_value=previous_value,
        change=change,
        change_percent=change_percent,
        unit=unit,
        as_of=as_of,
        url="https://example.com",
        raw=raw or {},
    )


class MarketContextTests(unittest.TestCase):
    def test_parse_yahoo_chart_payload_builds_point(self) -> None:
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

    def test_parse_yahoo_daily_series_builds_close_history(self) -> None:
        series = _parse_yahoo_daily_series(_yahoo_payload("RSP", [100.0, 101.0, 103.0]), "RSP", "https://example.com")

        self.assertIsNotNone(series)
        assert series is not None
        self.assertEqual(series["symbol"], "RSP")
        self.assertEqual(len(series["closes"]), 3)
        self.assertEqual(series["closes"][-1][1], 103.0)

    def test_parse_tw_yahoo_symbols_supports_tpex_suffix(self) -> None:
        items = _parse_tw_yahoo_symbols("2485.TW:兆赫,4749.TWO:新應材,2351")

        self.assertEqual([item.symbol for item in items], ["2485.TW", "4749.TWO", "2351.TW"])
        self.assertEqual([item.name for item in items], ["兆赫", "新應材", "2351"])

    def test_fetch_yahoo_tracked_tw_points_skips_official_twse_codes(self) -> None:
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
        self.assertEqual(points[0].name, "新應材")
        fake_get.assert_called_once()

    def test_parse_treasury_yield_curve_xml_uses_latest_record(self) -> None:
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
        with patch("event_relay.market_context.http_get_text", return_value="observation_date,SOFR\n2026-05-01,3.66\n"):
            points, failures = fetch_fred_points(5, ("SOFR", "UNKNOWN_SERIES"))

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].symbol, "SOFR")
        self.assertEqual(len(failures), 1)
        self.assertIn("unknown", failures[0].error)

    def test_fetch_market_breadth_points_builds_relative_spreads(self) -> None:
        payloads = {
            "SPY": _yahoo_payload("SPY", [100.0, 101.0, 102.0]),
            "RSP": _yahoo_payload("RSP", [100.0, 102.0, 105.0]),
            "QQQ": _yahoo_payload("QQQ", [100.0, 101.0, 104.0]),
            "QQEW": _yahoo_payload("QQEW", [100.0, 101.0, 102.0]),
            "IWM": _yahoo_payload("IWM", [100.0, 99.0, 100.0]),
        }

        def fake_get(url, params=None, timeout=15):
            symbol = url.rsplit("/", 1)[-1]
            return payloads[symbol]

        with patch("event_relay.market_context.http_get_json", side_effect=fake_get):
            points, failures = fetch_market_breadth_points(5)

        self.assertEqual(failures, [])
        self.assertEqual({point.symbol for point in points}, {"RSP-SPY", "QQEW-QQQ", "IWM-SPY"})
        rsp_spy = next(point for point in points if point.symbol == "RSP-SPY")
        self.assertEqual(rsp_spy.category, "market_breadth")
        self.assertGreater(rsp_spy.value or 0, 0)

    def test_build_ai_capex_point_uses_sec_companyfacts(self) -> None:
        point = _build_ai_capex_point("MSFT", "MICROSOFT CORP", "0000789019", _companyfacts_payload())

        self.assertIsNotNone(point)
        assert point is not None
        self.assertEqual(point.source, "sec_companyfacts")
        self.assertEqual(point.category, "ai_capex")
        self.assertEqual(point.symbol, "MSFT")
        self.assertEqual(point.value, 72_000_000_000)
        self.assertEqual(point.previous_value, 55_000_000_000)
        self.assertIn("free_cash_flow_proxy", point.raw)

    def test_fetch_ai_capex_points_requires_sec_user_agent(self) -> None:
        with patch.dict(os.environ, {"SEC_USER_AGENT": ""}, clear=False):
            points, failures = fetch_ai_capex_points(5, ("MSFT",))

        self.assertEqual(points, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("SEC_USER_AGENT", failures[0].error)

    def test_parse_eia_crude_stocks_payload_uses_latest_week(self) -> None:
        payload = {
            "response": {
                "data": [
                    {"period": "2026-04-24", "series": "WCESTUS1", "value": "440000"},
                    {"period": "2026-05-01", "series": "WCESTUS1", "value": "438000"},
                ]
            }
        }

        point = _parse_eia_crude_stocks_payload(payload)

        self.assertIsNotNone(point)
        assert point is not None
        self.assertEqual(point.source, "eia")
        self.assertEqual(point.symbol, "WCESTUS1")
        self.assertEqual(point.value, 438000)
        self.assertEqual(point.change, -2000)

    def test_fetch_eia_crude_stocks_requires_key(self) -> None:
        with patch.dict(os.environ, {"EIA_API_KEY": ""}, clear=False):
            points, failures = fetch_eia_crude_stocks_point(5)

        self.assertEqual(points, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("EIA_API_KEY", failures[0].error)

    def test_fetch_oil_supply_demand_points_builds_spread(self) -> None:
        csv_by_id = {
            "DCOILWTICO": "observation_date,DCOILWTICO\n2026-04-29,98\n2026-04-30,100\n",
            "DCOILBRENTEU": "observation_date,DCOILBRENTEU\n2026-04-29,101\n2026-04-30,104\n",
        }

        def fake_text(url, params=None, timeout=15):
            return csv_by_id[params["id"]]

        eia_payload = {
            "response": {
                "data": [
                    {"period": "2026-04-24", "series": "WCESTUS1", "value": "440000"},
                    {"period": "2026-05-01", "series": "WCESTUS1", "value": "438000"},
                ]
            }
        }

        with patch.dict(os.environ, {"EIA_API_KEY": "test-key"}, clear=False):
            with patch("event_relay.market_context.http_get_text", side_effect=fake_text):
                with patch("event_relay.market_context.http_get_json", return_value=eia_payload):
                    points, failures = fetch_oil_supply_demand_points(5)

        self.assertEqual(failures, [])
        self.assertIn("BRENT-WTI", {point.symbol for point in points})
        self.assertIn("WCESTUS1", {point.symbol for point in points})
        spread = next(point for point in points if point.symbol == "BRENT-WTI")
        self.assertEqual(spread.source, "fred_energy")
        self.assertEqual(spread.value, 4)

    def test_build_market_scorecard_scores_core_dimensions(self) -> None:
        points = [
            _context_point("RSP-SPY", 1.0, source="market_breadth", category="market_breadth", unit="pct_point"),
            _context_point("QQEW-QQQ", 0.5, source="market_breadth", category="market_breadth", unit="pct_point"),
            _context_point("IWM-SPY", 0.8, source="market_breadth", category="market_breadth", unit="pct_point"),
            _context_point("MSFT", 72_000_000_000, source="sec_companyfacts", category="ai_capex", unit="usd", change_percent=10.0, raw={"free_cash_flow_proxy": 48_000_000_000}),
            _context_point("GOOGL", 60_000_000_000, source="sec_companyfacts", category="ai_capex", unit="usd", change_percent=12.0, raw={"free_cash_flow_proxy": 40_000_000_000}),
            _context_point("META", 55_000_000_000, source="sec_companyfacts", category="ai_capex", unit="usd", change_percent=20.0, raw={"free_cash_flow_proxy": 30_000_000_000}),
            _context_point("DCOILWTICO", 95.0, source="fred_energy", category="oil_price", unit="usd_per_barrel"),
            _context_point("DCOILBRENTEU", 104.0, source="fred_energy", category="oil_price", unit="usd_per_barrel"),
            _context_point("BRENT-WTI", 9.0, source="fred_energy", category="oil_supply_demand", unit="usd_per_barrel"),
            _context_point("WCESTUS1", 438000.0, source="eia", category="oil_inventory", change=-6000.0, unit="thousand_barrels"),
            _context_point("BAMLH0A0HYM2", 2.8, source="fred", category="credit_stress", unit="percent"),
            _context_point("NFCI", -0.2, source="fred", category="financial_conditions"),
            _context_point("STLFSI4", -0.6, source="fred", category="financial_conditions"),
            _context_point("RRPONTSYD", 300.0, source="fred", category="liquidity", change=-50.0, unit="usd_billions"),
            _context_point("WRESBAL", 3300.0, source="fred", category="liquidity", change=100.0, unit="usd_millions"),
            _context_point("WTREGEN", 700.0, source="fred", category="liquidity", change=-40.0, unit="usd_millions"),
            _context_point("WALCL", 7200.0, source="fred", category="liquidity", change=90.0, unit="usd_millions"),
        ]

        scorecard = build_market_scorecard(points, [], datetime(2026, 5, 5, tzinfo=timezone.utc))

        dimensions = scorecard["dimensions"]
        self.assertEqual(dimensions["breadth_health"]["score"], 2)
        self.assertEqual(dimensions["ai_capex_quality"]["score"], 2)
        self.assertEqual(dimensions["energy_shock_risk"]["score"], -2)
        self.assertEqual(dimensions["credit_stress"]["score"], 2)
        self.assertEqual(dimensions["liquidity_impulse"]["score"], 2)
        self.assertEqual(scorecard["overall_score"], 6)
        self.assertEqual(dimensions["breadth_health"]["freshness"]["status"], "fresh")
        self.assertIn("input_hash", scorecard)

    def test_build_summary_mentions_key_sections(self) -> None:
        points = [
            MarketContextPoint("yahoo_chart", "us_equity_index", "NASDAQ 100", "^NDX", 100.0, 99.0, 1.0, 1.01, "USD", None, "", {}),
            MarketContextPoint("yahoo_chart", "semiconductor", "PHLX Semiconductor", "^SOX", 100.0, 98.0, 2.0, 2.04, "USD", None, "", {}),
            MarketContextPoint("yahoo_chart", "volatility", "VIX", "^VIX", 17.5, 18.0, -0.5, -2.7, "USD", None, "", {}),
            MarketContextPoint("us_treasury", "rates", "US Treasury 10Y", "BC_10YEAR", 4.26, None, None, None, "percent", None, "", {}),
            MarketContextPoint("us_treasury", "rates_spread", "US Treasury 10Y-2Y Spread", "US10Y2Y", 55.0, None, None, None, "bp", None, "", {}),
            MarketContextPoint("fred", "fed_path", "Fed Target Range Upper Limit", "DFEDTARU", 3.75, 3.75, 0.0, 0.0, "percent", "2026-04-30", "", {}),
            MarketContextPoint("fred", "liquidity", "Reserve Balances", "WRESBAL", 2918599.0, 2910000.0, 8599.0, 0.3, "usd_millions", "2026-04-29", "", {}),
            MarketContextPoint("fred", "credit_stress", "US High Yield Option-Adjusted Spread", "BAMLH0A0HYM2", 2.83, 2.90, -0.07, -2.4, "percent", "2026-04-30", "", {}),
            MarketContextPoint("market_breadth", "market_breadth", "S&P 500 equal-weight participation spread", "RSP-SPY", 1.2, 0.8, 1.7, None, "pct_point", "2026-05-01", "", {}),
            MarketContextPoint("sec_companyfacts", "ai_capex", "MSFT AI capex proxy", "MSFT", 72_000_000_000, 55_000_000_000, 17_000_000_000, 30.9, "usd", "2026-02-01", "", {}),
            MarketContextPoint("fred_energy", "oil_price", "WTI crude oil spot price", "DCOILWTICO", 100.0, 98.0, 2.0, 2.04, "usd_per_barrel", "2026-04-30", "", {}),
            MarketContextPoint("fred_energy", "oil_price", "Brent crude oil spot price", "DCOILBRENTEU", 104.0, 101.0, 3.0, 2.97, "usd_per_barrel", "2026-04-30", "", {}),
            MarketContextPoint("fred_energy", "oil_supply_demand", "Brent-WTI spread", "BRENT-WTI", 4.0, 3.0, 1.0, None, "usd_per_barrel", "2026-04-30", "", {}),
        ]

        summary = build_summary(points, [SourceFailure("test", "boom")], datetime(2026, 4, 20, tzinfo=timezone.utc))

        self.assertIn("市場情境資料", summary)
        self.assertIn("美股/風險", summary)
        self.assertIn("利率", summary)
        self.assertIn("市場廣度", summary)
        self.assertIn("AI capex", summary)
        self.assertIn("油價/供需", summary)
        self.assertIn("資料缺口: 1", summary)

    def test_build_market_context_events_marks_events_stored_only(self) -> None:
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

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].source, "market_context:yahoo_chart")
        self.assertTrue(events[0].raw["stored_only"])
        self.assertEqual(events[0].raw["event_type"], "market_context_point")
        self.assertEqual(events[1].source, "market_context:scorecard")
        self.assertEqual(events[1].raw["event_type"], "market_context_scorecard")
        self.assertIn("scorecard", events[1].raw)
        self.assertEqual(events[-1].source, "market_context:collector")
        self.assertTrue(events[-1].raw["market_breadth_enabled"])
        self.assertTrue(events[-1].raw["ai_capex_enabled"])
        self.assertTrue(events[-1].raw["oil_supply_enabled"])
        self.assertTrue(events[-1].raw["scorecard_enabled"])
        self.assertIn("scorecard_overall_score", events[-1].raw)

    def test_run_once_writes_relay_events(self) -> None:
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
        self.assertEqual(result["events"], 3)
        self.assertEqual(result["stored"], 3)
        self.assertEqual(len(_FakeStore.events), 3)
        self.assertEqual(_FakeStore.events[0].source, "market_context:yahoo_chart")


if __name__ == "__main__":
    unittest.main()
