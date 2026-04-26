from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_relay.tw_market_flow import (
    OfficialFlowDataset,
    TwMarketFlowConfig,
    _build_snapshot,
    _extract_rows,
    _normalize_trade_date,
    _stable_event_id,
    build_tw_market_flow_events,
    run_once,
)


class _FakeStore:
    """封裝 Fake Store 相關資料與行為。"""
    events = []

    def __init__(self, _settings) -> None:
        """初始化物件狀態與必要依賴。"""
        self.initialized = False

    def initialize(self) -> None:
        """執行 initialize 方法的主要邏輯。"""
        self.initialized = True

    def enqueue_event_if_new(self, event) -> bool:
        """執行 enqueue event if new 方法的主要邏輯。"""
        _FakeStore.events.append(event)
        return True


def _sample_dataset() -> OfficialFlowDataset:
    """執行 sample dataset 的主要流程。"""
    return OfficialFlowDataset(
        family="tpex",
        source_family="tpex_flow",
        source="market_context:tpex_flow",
        dataset="tpex_3insti_dealer_trading",
        title="TPEx dealer trading",
        url="https://www.tpex.org.tw/openapi/v1/tpex_3insti_dealer_trading",
        date_fields=("Date",),
        metric_fields=("Buy", "Sell", "NetBuySell"),
    )


class TwMarketFlowTests(unittest.TestCase):
    """封裝 Tw Market Flow Tests 相關資料與行為。"""
    def test_normalize_trade_date_supports_roc_and_iso_values(self) -> None:
        """測試 test normalize trade date supports roc and iso values 的預期行為。"""
        self.assertEqual(_normalize_trade_date("1150421"), "2026-04-21")
        self.assertEqual(_normalize_trade_date("115/04/21"), "2026-04-21")
        self.assertEqual(_normalize_trade_date("20260421"), "2026-04-21")
        self.assertEqual(_normalize_trade_date("2026-04-21"), "2026-04-21")
        self.assertEqual(_normalize_trade_date("2026-04-21T00:00:00+08:00"), "2026-04-21")

    def test_build_snapshot_uses_dataset_trade_date_and_metrics(self) -> None:
        """測試 test build snapshot uses dataset trade date and metrics 的預期行為。"""
        dataset = _sample_dataset()
        payload = {
            "data": [
                {"Date": "1150421", "Buy": "1,000", "Sell": "200", "NetBuySell": "800"},
                {"Date": "1150421", "Buy": "500", "Sell": "900", "NetBuySell": "-400"},
            ]
        }

        snapshot = _build_snapshot(dataset, payload, datetime(2026, 4, 22, tzinfo=timezone.utc))

        self.assertEqual(snapshot.trade_date, "2026-04-21")
        self.assertEqual(snapshot.normalized_metrics["row_count"], 2)
        self.assertEqual(snapshot.normalized_metrics["field_totals"]["Buy"], 1500)
        self.assertEqual(snapshot.normalized_metrics["field_totals"]["Sell"], 1100)
        self.assertEqual(snapshot.normalized_metrics["field_totals"]["NetBuySell"], 400)

    def test_extract_rows_supports_twse_fields_data_tables(self) -> None:
        """測試 test extract rows supports twse fields data tables 的預期行為。"""
        payload = {
            "date": "20260422",
            "fields": ["證券代號", "三大法人買賣超股數"],
            "data": [["2330", "1,000"], ["2317", "-500"]],
        }
        dataset = OfficialFlowDataset(
            family="twse",
            source_family="twse_flow",
            source="market_context:twse_flow",
            dataset="T86_ALLBUT0999",
            title="TWSE institutional trading",
            url="https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date}&selectType=ALLBUT0999",
            date_fields=(),
            metric_fields=("三大法人買賣超股數",),
        )

        rows = _extract_rows(payload)
        snapshot = _build_snapshot(dataset, payload, datetime(2026, 4, 22, tzinfo=timezone.utc))

        self.assertEqual(rows[0]["證券代號"], "2330")
        self.assertEqual(snapshot.trade_date, "2026-04-22")
        self.assertEqual(snapshot.normalized_metrics["field_totals"]["三大法人買賣超股數"], 500)

    def test_build_tw_market_flow_events_marks_dataset_event_stored_only(self) -> None:
        """測試 test build tw market flow events marks dataset event stored only 的預期行為。"""
        dataset = _sample_dataset()
        snapshot = _build_snapshot(
            dataset,
            {"data": [{"Date": "1150421", "Buy": "100", "Sell": "20", "NetBuySell": "80"}]},
            datetime(2026, 4, 22, tzinfo=timezone.utc),
        )

        events = build_tw_market_flow_events([snapshot])

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source, "market_context:tpex_flow")
        self.assertEqual(event.raw["stored_only"], True)
        self.assertEqual(event.raw["dimension"], "market_context")
        self.assertEqual(event.raw["event_type"], "tw_market_flow_dataset")
        self.assertEqual(event.raw["trade_date"], "2026-04-21")
        self.assertEqual(event.raw["dataset"], "tpex_3insti_dealer_trading")
        self.assertEqual(
            event.raw["dedupe_key"],
            {
                "source_family": "tpex_flow",
                "trade_date": "2026-04-21",
                "dataset": "tpex_3insti_dealer_trading",
            },
        )
        self.assertEqual(event.raw["rows"][0]["Buy"], "100")
        self.assertEqual(event.raw["normalized_metrics"]["field_totals"]["NetBuySell"], 80)

    def test_stable_event_id_contains_required_dedupe_parts(self) -> None:
        """測試 test stable event id contains required dedupe parts 的預期行為。"""
        first = _stable_event_id("twse_flow", "2026-04-21", "MI_MARGN")
        second = _stable_event_id("twse_flow", "2026-04-21", "MI_MARGN")
        next_day = _stable_event_id("twse_flow", "2026-04-22", "MI_MARGN")

        self.assertEqual(first, second)
        self.assertNotEqual(first, next_day)
        self.assertIn("twse_flow", first)
        self.assertIn("2026-04-21", first)
        self.assertIn("MI_MARGN", first)

    def test_run_once_writes_events_to_store(self) -> None:
        """測試 test run once writes events to store 的預期行為。"""
        _FakeStore.events = []
        dataset = _sample_dataset()
        snapshot = _build_snapshot(
            dataset,
            {"data": [{"Date": "1150421", "Buy": "100", "Sell": "20", "NetBuySell": "80"}]},
            datetime(2026, 4, 22, tzinfo=timezone.utc),
        )
        config = TwMarketFlowConfig(env_file=".env", timeout_seconds=5, families=("tpex",))

        with patch("event_relay.tw_market_flow.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
            with patch("event_relay.tw_market_flow.MySqlEventStore", _FakeStore):
                with patch("event_relay.tw_market_flow.collect_tw_market_flow", return_value=([snapshot], [])):
                    result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["datasets"], 1)
        self.assertEqual(result["events"], 1)
        self.assertEqual(result["stored"], 1)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(len(_FakeStore.events), 1)
        self.assertEqual(_FakeStore.events[0].source, "market_context:tpex_flow")


if __name__ == "__main__":
    unittest.main()
