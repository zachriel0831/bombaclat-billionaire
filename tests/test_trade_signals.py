import json
from types import SimpleNamespace
import unittest

from event_relay.trade_signals import build_trade_signals_from_analysis, sync_trade_signals_from_recent_analyses


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

    def test_sync_recent_analyses_backfills_store(self) -> None:
        """backfill 會讀 structured_json 並呼叫 store upsert。"""
        store = _FakeStore()

        result = sync_trade_signals_from_recent_analyses(store, days=7, limit=10)

        self.assertEqual(result, {"analyses_processed": 1, "signals_stored": 1})
        self.assertEqual(store.writes[0][0], 9)
        self.assertEqual(store.writes[0][1][0].ticker, "2330")
        self.assertEqual(json.loads(store.writes[0][1][0].source_event_ids_json), [123])


if __name__ == "__main__":
    unittest.main()
