import json
from types import SimpleNamespace
import unittest

from event_relay.trade_signals import (
    build_fixed_pool_repair_trade_signals,
    build_prior_signal_reference_trade_signals,
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
        """只保留固定監控池內的台股。"""
        structured = {
            "stock_watch": [
                {"ticker": "NVDA", "market": "US", "direction": "bullish", "rationale": "AI"},
                {"ticker": "bad ticker prose", "market": "TW", "direction": "bullish", "rationale": "bad"},
                {"ticker": "3711", "direction": "mixed", "rationale": "outside fixed pool"},
                {"ticker": "2330", "direction": "mixed", "rationale": "watch only"},
            ]
        }

        signals = build_trade_signals_from_analysis(
            analysis_id=8,
            analysis_date="2026-04-26",
            analysis_slot="us_close",
            structured_payload=structured,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].ticker, "2330")
        self.assertEqual(signals[0].direction, "watch")

    def test_known_tickers_fill_missing_chinese_names(self) -> None:
        """LLM structured rows only carrying ticker still get visible Chinese names."""
        structured = {
            "stock_watch": [
                {"ticker": "2317", "direction": "bullish", "strategy_type": "swing", "rationale": "AI server"},
                {"ticker": "2454", "name": "MediaTek", "direction": "bullish", "strategy_type": "swing"},
                {"ticker": "2308", "direction": "bullish", "strategy_type": "medium"},
            ]
        }

        signals = build_trade_signals_from_analysis(
            analysis_id=18,
            analysis_date="2026-05-04",
            analysis_slot="pre_tw_open",
            structured_payload=structured,
        )

        self.assertEqual([signal.ticker for signal in signals], ["2317", "2454", "2308"])
        self.assertEqual([signal.name for signal in signals], ["鴻海", "聯發科", "台達電"])

    def test_sync_recent_analyses_backfills_store(self) -> None:
        """backfill 會讀 structured_json 並呼叫 store upsert。"""
        store = _FakeStore()

        result = sync_trade_signals_from_recent_analyses(store, days=7, limit=10)

        self.assertEqual(result["analyses_processed"], 1)
        self.assertEqual(result["signals_stored"], 1)
        self.assertEqual(result["quote_fallback_added"], 0)
        self.assertEqual(result["prior_signal_references"], 0)
        self.assertEqual(store.writes[0][0], 9)
        self.assertEqual(store.writes[0][1][0].ticker, "2330")
        self.assertEqual(json.loads(store.writes[0][1][0].source_event_ids_json), [123])

    def test_fixed_pool_repair_uses_prior_references_when_structured_empty(self) -> None:
        """A stored analysis with empty stock_watch can still rebuild monitor signals."""
        signals, metrics = build_fixed_pool_repair_trade_signals(
            analysis_id=78,
            analysis_date="2026-05-25",
            analysis_slot="pre_tw_open",
            structured_payload={"stock_watch": []},
            prior_rows=[
                {
                    "id": 170,
                    "analysis_id": 70,
                    "analysis_date": "2026-05-23",
                    "analysis_slot": "pre_tw_open",
                    "market": "TW",
                    "ticker": "2330",
                    "name": "?啁???",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "medium",
                    "entry_zone": '{"low": 1000, "high": 1010}',
                    "invalidation": '{"price": 980}',
                    "take_profit_zone": '{"first": 1050}',
                    "rationale": "AI/HPC demand",
                    "updated_at": "2026-05-23 08:00:00",
                }
            ],
        )

        self.assertEqual([signal.ticker for signal in signals], ["2330"])
        self.assertEqual(signals[0].signal_type, "prior_signal_stock_watch")
        self.assertEqual(signals[0].entry_zone_json, '{"low": 1000, "high": 1010}')
        self.assertEqual(metrics["prior_signal_references"], 1)

    def test_sync_targeted_repair_honors_trust_gate(self) -> None:
        """Repair must not recreate monitor signals when stored trust gate blocks them."""
        class Store(_FakeStore):
            def fetch_market_analysis_for_signals(self, analysis_id: int):
                return SimpleNamespace(
                    row_id=analysis_id,
                    analysis_date="2026-05-25",
                    analysis_slot="pre_tw_open",
                    structured_json=json.dumps({"stock_watch": []}, ensure_ascii=False),
                    raw_json=json.dumps({"trust_gate": {"signals_allowed": False}}, ensure_ascii=False),
                    updated_at="2026-05-25 08:00:00",
                )

        store = Store()
        result = sync_trade_signals_from_recent_analyses(
            store,
            analysis_id=78,
            include_fixed_pool_fallback=True,
        )

        self.assertEqual(result["analyses_processed"], 0)
        self.assertEqual(result["analyses_skipped"], 1)
        self.assertEqual(result["signals_stored"], 0)
        self.assertEqual(store.writes, [])

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
        self.assertIn("固定十檔監控池", text)
        self.assertIn("2330 台積電", text)
        self.assertIn("波段觀察", text)
        self.assertIn("利多：AI demand", text)
        self.assertIn("利空：估值對美債利率、費半與外資動向敏感", text)
        self.assertIn("買入注意：swing 觀察", text)
        self.assertNotIn("上漲邏輯", text)
        self.assertNotIn("低估/補漲", text)
        self.assertNotIn("做多｜波段", text)
        self.assertNotIn("direction=long", text)
        self.assertNotIn("進場時點", text)
        self.assertIn("進場 low:600, high:610", text)
        self.assertIn("停利 first:630", text)
        self.assertIn("停損 price:590", text)
        self.assertNotIn("basis", text)

    def test_quote_fallback_accepts_flat_and_negative_quotes_for_fixed_pool(self) -> None:
        """Fallback 只補固定十檔，包含持平/小跌報價。"""
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
                    ("2454.TW", "聯發科", 1200, 9.0, 9000),
                    ("2317.TW", "鴻海", 220, 7.0, 900),
                    ("2308.TW", "台達電", 500, 6.0, 800),
                    ("2881.TW", "富邦金", 90, 3.0, 700),
                    ("2485.TW", "兆赫", 43, 2.0, 600),
                    ("3535.TW", "晶彩科", 120, 1.5, 500),
                    ("2330.TW", "台積電", 600, 1.1, 1000),
                    ("3715.TW", "定穎投控", 180, 0.2, 400),
                    ("2351.TW", "順德", 130, 0.0, 300),
                    ("2882.TW", "國泰金", 70, -0.3, 700),
                ]
            )
        ]

        signals = build_quote_event_trade_signals(
            analysis_id=77,
            analysis_date="2026-04-28",
            analysis_slot="pre_tw_open",
            events=events,
            max_signals=10,
        )

        self.assertEqual(
            [signal.ticker for signal in signals],
            ["2454", "2317", "2308", "2881", "2485", "3535", "2330", "3715", "2351", "2882"],
        )
        self.assertEqual(len(signals), 10)
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

    def test_yahoo_market_context_fallback_supports_fixed_pool_symbol(self) -> None:
        """Yahoo market_context 可補固定十檔個股 signal。"""
        raw_json = {
            "point": {
                "source": "yahoo_chart",
                "category": "tw_tracked_stock",
                "symbol": "3535.TW",
                "name": "晶彩科",
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
        self.assertEqual(signals[0].ticker, "3535")
        self.assertIn("yahoo_chart_tracked_stock_fallback", signals[0].raw_json)
        self.assertIn("市場情境報價上漲", signals[0].rationale)

    def test_quote_fallback_prefers_configured_fixed_pool_stocks(self) -> None:
        """Configured fixed-pool stocks rank ahead of other fixed-pool rows."""
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
                    ("2317.TW", "鴻海", 220, 7.0, 7000),
                    ("2308.TW", "台達電", 500, 5.0, 5000),
                    ("2485.TW", "兆赫", 43, 1.5, 100),
                    ("3535.TW", "晶彩科", 120, 2.0, 100),
                    ("3715.TW", "定穎投控", 180, 0.1, 100),
                    ("2351.TW", "順德", 130, -0.1, 100),
                    ("2882.TW", "國泰金", 70, 0.05, 100),
                ]
            )
        ]

        signals = build_quote_event_trade_signals(
            analysis_id=90,
            analysis_date="2026-05-04",
            analysis_slot="pre_tw_open",
            events=events,
            max_signals=10,
            preferred_tickers={"2485", "3535", "3715", "2351", "4749"},
        )

        self.assertEqual(
            [signal.ticker for signal in signals],
            ["3535", "2485", "3715", "2351", "2454", "2330", "2317", "2308", "2882"],
        )
        self.assertEqual(
            [signal.name for signal in signals],
            ["晶彩科", "兆赫", "定穎投控", "順德", "聯發科", "台積電", "鴻海", "台達電", "國泰金"],
        )

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
                    "ticker": "2317",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "low",
                    "rationale": "AI server",
                },
            ]
        )

        self.assertIn("1. 2330 台積電", text)
        self.assertIn("2. 2317 鴻海", text)

    def test_prior_signal_reference_clones_levels_with_confirmation_caveat(self) -> None:
        """Prior rows can seed levels, but stay low-confidence references."""
        signals = build_prior_signal_reference_trade_signals(
            analysis_id=99,
            analysis_date="2026-05-18",
            analysis_slot="pre_tw_open",
            missing_tickers=["2317", "2330"],
            prior_rows=[
                {
                    "id": 12,
                    "analysis_id": 50,
                    "analysis_date": "2026-05-09",
                    "analysis_slot": "pre_tw_open",
                    "market": "TW",
                    "ticker": "2317",
                    "name": "鴻海",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "medium",
                    "entry_zone": '{"low": 205, "high": 210}',
                    "invalidation": '{"price": 198}',
                    "take_profit_zone": '{"first": 225}',
                    "rationale": (
                        "上漲邏輯：AI server orders. "
                        "低估/補漲：lagging peer move. "
                        "買入理由：price returns to entry zone."
                    ),
                    "updated_at": "2026-05-09 08:00:00",
                }
            ],
        )

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.ticker, "2317")
        self.assertEqual(signal.signal_type, "prior_signal_stock_watch")
        self.assertEqual(signal.confidence, "low")
        self.assertEqual(signal.entry_zone_json, '{"low": 205, "high": 210}')
        self.assertIn("利多：沿用 2026-05-09 前次固定池參考", signal.rationale)
        self.assertIn("利空：前次條件已過期", signal.rationale)
        self.assertIn("買入注意：沿用前次條件", signal.rationale)
        self.assertIn("今日仍需用盤中量價與新聞風控重新確認", signal.rationale)
        self.assertIn("prior_t_trade_signals", signal.raw_json)

    def test_recommendation_section_renders_neutral_fixed_pool_when_empty(self) -> None:
        """Final visible section still lists the fixed pool when no signal rows exist."""
        text = build_trade_signal_recommendation_section([])

        self.assertIn("固定十檔監控池", text)
        self.assertIn("註：沒有完整短中線訊號", text)
        self.assertIn("1. 2330 台積電｜中性觀察", text)
        self.assertIn("10. 2351 順德｜中性觀察", text)
        self.assertIn("利多：AI/HPC、先進製程與半導體景氣若延續", text)
        self.assertIn("利空：今日缺少個股訊號與報價條件", text)
        self.assertIn("買入注意：等回到進場區且大盤、費半同步轉強", text)
        self.assertNotIn("上漲邏輯", text)
        self.assertNotIn("低估/補漲", text)
        self.assertNotIn("目前固定十檔沒有可用", text)

    def test_recommendation_section_excludes_blocked_ticker(self) -> None:
        """Final visible section excludes blocked tickers such as 4749."""
        text = build_trade_signal_recommendation_section(
            [
                {
                    "ticker": "4749",
                    "name": "?\u8139???",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "medium",
                    "rationale": "?\u8139??? market context",
                },
                {
                    "ticker": "2330",
                    "strategy_type": "swing",
                    "direction": "long",
                    "confidence": "low",
                    "rationale": "AI",
                },
            ]
        )

        self.assertNotIn("4749", text)
        self.assertIn("1. 2330 台積電", text)
        self.assertNotIn("?\u8139???", text)


if __name__ == "__main__":
    unittest.main()
