import json
from types import SimpleNamespace
import unittest

from event_relay.trade_signals import (
    build_quote_event_trade_signals,
    build_trade_signal_recommendation_section,
    build_trade_signals_from_analysis,
    sync_trade_signals_from_recent_analyses,
)


class _FakeStore:
    """提供 recent analyses 與 signal write stub。"""

    def __init__(self) -> None:
        self.writes: list[tuple[int, list]] = []

    def fetch_recent_market_analyses_for_signals(self, *, days: int, limit: int) -> list:
        return [
            SimpleNamespace(
                row_id=9,
                analysis_date="2026-04-26",
                analysis_slot="pre_tw_open",
                structured_json=json.dumps(
                    {
                        "stock_watch": [
                            {"ticker": "2330", "direction": "bullish", "rationale": "AI"}
                        ]
                    },
                    ensure_ascii=False,
                ),
                raw_json=json.dumps(
                    {
                        "pipeline_stages": {
                            "tw_mapping": {
                                "stock_watch": [
                                    {
                                        "ticker": "2330",
                                        "direction": "bullish",
                                        "rationale": "AI",
                                        "evidence_ids": [123],
                                    }
                                ]
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                updated_at="2026-04-26 08:00:00",
            )
        ]

    def replace_trade_signals_for_analysis(self, analysis_id: int, signals: list) -> int:
        self.writes.append((analysis_id, list(signals)))
        return len(signals)


class TradeSignalExtractionTests(unittest.TestCase):
    """測試 analysis structured_json 轉 trade signal 的規則。"""

    def test_builds_pending_review_signal_with_stable_idempotency_key(self) -> None:
        """同一分析與同一股票策略會得到穩定 signal key。"""
        structured = {
            "confidence": "medium",
            "stock_watch": [
                {
                    "ticker": "2330.TW",
                    "market": "TWSE",
                    "direction": "bullish",
                    "rationale": "AI chain momentum",
                    "strategy_type": "intraday",
                    "entry_zone": {"low": 600, "high": 610},
                    "invalidation": {"price": 595},
                    "take_profit_zone": {"first": 625},
                    "risk_notes": ["gap up too much"],
                }
            ],
        }
        telemetry = {
            "tw_mapping": {
                "stock_watch": [
                    {
                        "ticker": "2330",
                        "direction": "bullish",
                        "rationale": "AI chain momentum",
                        "evidence_ids": [10, "11"],
                    }
                ]
            }
        }

        first = build_trade_signals_from_analysis(
            analysis_id=7,
            analysis_date="2026-04-26",
            analysis_slot="pre_tw_open",
            structured_payload=structured,
            pipeline_telemetry=telemetry,
        )
        second = build_trade_signals_from_analysis(
            analysis_id=7,
            analysis_date="2026-04-26",
            analysis_slot="pre_tw_open",
            structured_payload=structured,
            pipeline_telemetry=telemetry,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].signal_key, second[0].signal_key)
        self.assertEqual(first[0].idempotency_key, second[0].idempotency_key)
        self.assertEqual(first[0].ticker, "2330")
        self.assertEqual(first[0].market, "TW")
        self.assertEqual(first[0].direction, "long")
        self.assertEqual(first[0].strategy_type, "intraday")
        self.assertEqual(first[0].status, "pending_review")
        self.assertEqual(json.loads(first[0].source_event_ids_json), [10, "11"])
        self.assertIn("review/risk gate required", first[0].raw_json)

    def test_skips_non_tw_market_and_invalid_ticker(self) -> None:
        """只保留台股格式的推薦。"""
        structured = {
            "stock_watch": [
                {"ticker": "NVDA", "market": "US", "direction": "bullish", "rationale": "AI"},
                {"ticker": "bad ticker prose", "market": "TW", "direction": "bullish", "rationale": "bad"},
                {"ticker": "2454", "direction": "mixed", "rationale": "watch only"},
            ]
        }

        signals = build_trade_signals_from_analysis(
            analysis_id=8,
            analysis_date="2026-04-26",
            analysis_slot="us_close",
            structured_payload=structured,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].ticker, "2454")
        self.assertEqual(signals[0].direction, "watch")

    def test_known_tickers_fill_missing_chinese_names(self) -> None:
        """LLM structured rows only carrying ticker still get visible Chinese names."""
        structured = {
            "stock_watch": [
                {"ticker": "3711", "direction": "bullish", "strategy_type": "swing", "rationale": "HBM"},
                {"ticker": "2382", "name": "Quanta", "direction": "bullish", "strategy_type": "swing"},
                {"ticker": "3231", "direction": "bullish", "strategy_type": "medium"},
            ]
        }

        signals = build_trade_signals_from_analysis(
            analysis_id=18,
            analysis_date="2026-05-04",
            analysis_slot="pre_tw_open",
            structured_payload=structured,
        )

        self.assertEqual([signal.ticker for signal in signals], ["3711", "2382", "3231"])
        self.assertEqual([signal.name for signal in signals], ["日月光投控", "廣達", "緯創"])

    def test_sync_recent_analyses_backfills_store(self) -> None:
        """backfill 會讀 structured_json 並呼叫 store upsert。"""
        store = _FakeStore()

        result = sync_trade_signals_from_recent_analyses(store, days=7, limit=10)

        self.assertEqual(result, {"analyses_processed": 1, "signals_stored": 1})
        self.assertEqual(store.writes[0][0], 9)
        self.assertEqual(store.writes[0][1][0].ticker, "2330")
        self.assertEqual(json.loads(store.writes[0][1][0].source_event_ids_json), [123])

    def test_build_trade_signal_recommendation_section_formats_levels(self) -> None:
        """推薦區塊會把進場與平倉檔位格式化。"""
        text = build_trade_signal_recommendation_section(
            [
                {
                    "ticker": "2330",
                    "name": "台積電",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "medium",
                    "entry_zone": {"low": 600, "high": 610, "basis": "quote"},
                    "take_profit_zone": {"first": 630, "basis": "quote"},
                    "invalidation": {"price": 590, "basis": "quote"},
                    "rationale": "AI demand",
                }
            ]
        )

        self.assertIn("## 今日個股觀察", text)
        self.assertIn("短中線推薦買進候選", text)
        self.assertIn("2330 台積電", text)
        self.assertIn("可做波段", text)
        self.assertNotIn("做多｜波段", text)
        self.assertNotIn("direction=long", text)
        self.assertNotIn("進場時點", text)
        self.assertIn("進場 low:600, high:610", text)
        self.assertIn("停利 first:630", text)
        self.assertIn("停損 price:590", text)
        self.assertNotIn("basis", text)

    def test_quote_fallback_accepts_flat_and_negative_quotes_for_top_up(self) -> None:
        """Fallback 可用持平/小跌報價補滿 5 檔，但信心較低。"""
        events = [
            SimpleNamespace(
                row_id=200 + idx,
                source="yfinance_taiwan",
                summary=json.dumps(
                    {
                        "symbol": symbol,
                        "name": name,
                        "price": price,
                        "change_pct": change_pct,
                        "volume": volume,
                    },
                    ensure_ascii=False,
                ),
            )
            for idx, (symbol, name, price, change_pct, volume) in enumerate(
                [
                    ("2454.TW", "聯發科", 1200, 2.5, 900),
                    ("2330.TW", "台積電", 600, 1.1, 1000),
                    ("2308.TW", "台達電", 420, 0.4, 800),
                    ("0050.TW", "元大台灣50", 180, 0.0, 600),
                    ("2317.TW", "鴻海", 160, -0.3, 700),
                ]
            )
        ]

        signals = build_quote_event_trade_signals(
            analysis_id=77,
            analysis_date="2026-04-28",
            analysis_slot="pre_tw_open",
            events=events,
            max_signals=5,
        )

        self.assertEqual([signal.ticker for signal in signals], ["2454", "2330", "2308", "0050", "2317"])
        self.assertEqual(len(signals), 5)
        self.assertIn("timing", signals[0].entry_zone_json)
        self.assertIn("最新台股報價下跌 0.30%", signals[-1].rationale)

    def test_twse_context_fallback_builds_watchlist_signals(self) -> None:
        """官方 TWSE tracked-stock context 可在 yfinance 缺席時補 signal。"""
        raw_json = {
            "point": {
                "category": "tw_tracked_stock",
                "symbol": "2330",
                "name": "台積電",
                "value": 2265.0,
                "change": 80.0,
                "as_of": "2026-04-27",
                "raw": {"TradeVolume": "44600000"},
            }
        }
        events = [
            SimpleNamespace(
                row_id=301,
                source="market_context:twse_openapi",
                raw_json=json.dumps(raw_json, ensure_ascii=False),
                summary="category=tw_tracked_stock",
            )
        ]

        signals = build_quote_event_trade_signals(
            analysis_id=88,
            analysis_date="2026-04-28",
            analysis_slot="pre_tw_open",
            events=events,
            max_signals=5,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].ticker, "2330")
        self.assertEqual(signals[0].signal_type, "context_fallback_stock_watch")
        self.assertIn("twse_openapi_tracked_stock_fallback", signals[0].raw_json)
        self.assertIn("TWSE官方收盤基準上漲", signals[0].rationale)
        self.assertIn("需開盤量價確認", signals[0].rationale)
        self.assertNotIn("作為早盤 watchlist 補位", signals[0].rationale)

    def test_yahoo_market_context_fallback_supports_tpex_symbol(self) -> None:
        """Yahoo market_context 可補上櫃 .TWO 個股 signal。"""
        raw_json = {
            "point": {
                "source": "yahoo_chart",
                "category": "tw_tracked_stock",
                "symbol": "4749.TWO",
                "name": "新應材",
                "value": 205.5,
                "previous_value": 200.0,
                "change": 5.5,
                "change_percent": 2.75,
                "as_of": "2026-04-30T05:20:00+00:00",
                "raw": {},
            }
        }
        events = [
            SimpleNamespace(
                row_id=302,
                source="market_context:yahoo_chart",
                raw_json=json.dumps(raw_json, ensure_ascii=False),
                summary="category=tw_tracked_stock",
            )
        ]

        signals = build_quote_event_trade_signals(
            analysis_id=89,
            analysis_date="2026-04-30",
            analysis_slot="pre_tw_open",
            events=events,
            max_signals=5,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].ticker, "4749")
        self.assertIn("yahoo_chart_tracked_stock_fallback", signals[0].raw_json)
        self.assertIn("市場情境報價上漲", signals[0].rationale)

    def test_quote_fallback_prefers_configured_tracked_stocks(self) -> None:
        """Configured local tracked stocks rank ahead of generic quote candidates."""
        events = [
            SimpleNamespace(
                row_id=400 + idx,
                source="market_context:yahoo_chart",
                raw_json=json.dumps(
                    {
                        "point": {
                            "source": "yahoo_chart",
                            "category": "tw_tracked_stock",
                            "symbol": symbol,
                            "name": name,
                            "value": price,
                            "change_percent": change_pct,
                            "raw": {"TradeVolume": volume},
                        }
                    },
                    ensure_ascii=False,
                ),
                summary="category=tw_tracked_stock",
            )
            for idx, (symbol, name, price, change_pct, volume) in enumerate(
                [
                    ("2454.TW", "聯發科", 1200, 9.0, 9000),
                    ("2330.TW", "台積電", 600, 8.0, 8000),
                    ("2485.TW", "兆赫", 22, 0.2, 100),
                    ("3535.TW", "晶彩科", 90, -0.1, 100),
                    ("3715.TW", "定穎投控", 75, 0.0, 100),
                    ("2351.TW", "順德", 110, -0.2, 100),
                    ("4749.TWO", "新應材", 205, 0.1, 100),
                ]
            )
        ]

        signals = build_quote_event_trade_signals(
            analysis_id=90,
            analysis_date="2026-05-04",
            analysis_slot="pre_tw_open",
            events=events,
            max_signals=5,
            preferred_tickers={"2485", "3535", "3715", "2351", "4749"},
        )

        self.assertEqual([signal.ticker for signal in signals], ["2485", "4749", "3715", "3535", "2351"])
        self.assertEqual([signal.name for signal in signals], ["兆赫", "新應材", "定穎投控", "晶彩科", "順德"])

    def test_recommendation_section_backfills_missing_names(self) -> None:
        """Final visible section backfills names even for existing ticker-only DB rows."""
        text = build_trade_signal_recommendation_section(
            [
                {
                    "ticker": "2330",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "low",
                    "rationale": "AI",
                },
                {
                    "ticker": "3711",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "low",
                    "rationale": "HBM",
                },
            ]
        )

        self.assertIn("1. 2330 台積電", text)
        self.assertIn("2. 3711 日月光投控", text)


if __name__ == "__main__":
    unittest.main()
