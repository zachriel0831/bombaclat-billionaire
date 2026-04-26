from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_relay.service import SummaryEvent
from event_relay.tw_close_context import (
    TwCloseContextConfig,
    build_tw_close_context_event,
    filter_tw_close_source_events,
    run_once,
)


class _FakeStore:
    """封裝 Fake Store 相關資料與行為。"""
    source_events: list[SummaryEvent] = []
    stored_events = []

    def __init__(self, _settings) -> None:
        """初始化物件狀態與必要依賴。"""
        return None

    def initialize(self) -> None:
        """執行 initialize 方法的主要邏輯。"""
        return None

    def fetch_recent_summary_events(self, days: int, limit: int) -> list[SummaryEvent]:
        """抓取 fetch recent summary events 對應的資料或結果。"""
        self.days = days
        self.limit = limit
        return list(_FakeStore.source_events)

    def enqueue_event_if_new(self, event) -> bool:
        """執行 enqueue event if new 方法的主要邏輯。"""
        _FakeStore.stored_events.append(event)
        return True


def _summary_event(
    row_id: int,
    source: str,
    title: str,
    trade_date: str,
    raw: dict | None = None,
) -> SummaryEvent:
    """執行 summary event 的主要流程。"""
    payload = {"trade_date": trade_date, "stored_only": True}
    if raw:
        payload.update(raw)
    return SummaryEvent(
        row_id=row_id,
        source=source,
        title=title,
        url=f"https://example.com/{row_id}",
        summary=f"summary {row_id}",
        published_at=f"{trade_date}T07:00:00+08:00",
        created_at=f"{trade_date} 15:10:00",
        raw_json=json.dumps(payload, ensure_ascii=False),
    )


class TwCloseContextTests(unittest.TestCase):
    """封裝 Tw Close Context Tests 相關資料與行為。"""
    def _config(self) -> TwCloseContextConfig:
        """執行 config 方法的主要邏輯。"""
        return TwCloseContextConfig(
            env_file=".env",
            slot="tw_close",
            scheduled_time_local="15:20",
            trade_date="2026-04-22",
            lookback_days=2,
            max_events=200,
            source_prefixes=(
                "market_context:twse_flow",
                "market_context:tpex_flow",
                "market_context:taifex_flow",
                "market_context:twse_openapi",
                "twse_mops:",
            ),
        )

    def test_filter_tw_close_source_events_keeps_same_day_taiwan_sources(self) -> None:
        """測試 test filter tw close source events keeps same day taiwan sources 的預期行為。"""
        events = [
            _summary_event(1, "market_context:twse_flow", "TWSE flow", "2026-04-22"),
            _summary_event(2, "market_context:tpex_flow", "TPEx flow", "2026-04-22"),
            _summary_event(3, "market_context:taifex_flow", "TAIFEX flow", "2026-04-21"),
            _summary_event(4, "BBC News", "not market context", "2026-04-22"),
        ]

        selected = filter_tw_close_source_events(
            events,
            trade_date="2026-04-22",
            source_prefixes=self._config().source_prefixes,
        )

        self.assertEqual([event.row_id for event in selected], [1, 2])

    def test_build_tw_close_context_event_raw_json_contract(self) -> None:
        """測試 test build tw close context event raw json contract 的預期行為。"""
        source_events = [
            _summary_event(
                1,
                "market_context:twse_flow",
                "TWSE close flow",
                "2026-04-22",
                {
                    "event_type": "tw_market_flow_dataset",
                    "dimension": "market_context",
                    "dataset": "T86_ALLBUT0999",
                    "normalized_metrics": {"field_totals": {"三大法人買賣超股數": 500}},
                },
            )
        ]

        event = build_tw_close_context_event(
            source_events,
            self._config(),
            datetime(2026, 4, 22, 15, 20, tzinfo=timezone.utc),
        )

        self.assertEqual(event.source, "market_context:tw_close")
        self.assertEqual(event.event_id, "market-context-tw_close-2026-04-22")
        self.assertTrue(event.raw["stored_only"])
        self.assertEqual(event.raw["dimension"], "market_context")
        self.assertEqual(event.raw["event_type"], "market_context_collection")
        self.assertEqual(event.raw["slot"], "tw_close")
        self.assertEqual(event.raw["trade_date"], "2026-04-22")
        self.assertEqual(event.raw["event_count"], 1)
        self.assertEqual(event.raw["source_counts"], {"market_context:twse_flow": 1})
        compact_source_raw = event.raw["events"][0]["raw"]
        self.assertEqual(compact_source_raw["dataset"], "T86_ALLBUT0999")
        self.assertEqual(compact_source_raw["normalized_metrics"]["field_totals"]["三大法人買賣超股數"], 500)

    def test_event_id_is_stable_for_same_trade_date(self) -> None:
        """測試 test event id is stable for same trade date 的預期行為。"""
        source_events = [_summary_event(1, "market_context:twse_flow", "TWSE close flow", "2026-04-22")]

        first = build_tw_close_context_event(
            source_events,
            self._config(),
            datetime(2026, 4, 22, 15, 20, tzinfo=timezone.utc),
        )
        second = build_tw_close_context_event(
            source_events,
            self._config(),
            datetime(2026, 4, 22, 15, 25, tzinfo=timezone.utc),
        )

        self.assertEqual(first.event_id, second.event_id)

    def test_run_once_writes_single_relay_event(self) -> None:
        """測試 test run once writes single relay event 的預期行為。"""
        _FakeStore.source_events = [
            _summary_event(1, "market_context:twse_flow", "TWSE close flow", "2026-04-22"),
            _summary_event(2, "twse_mops:2330", "MOPS disclosure", "2026-04-22"),
        ]
        _FakeStore.stored_events = []

        with patch("event_relay.tw_close_context.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
            with patch("event_relay.tw_close_context.MySqlEventStore", _FakeStore):
                result = run_once(self._config())

        self.assertTrue(result["ok"])
        self.assertEqual(result["slot"], "tw_close")
        self.assertEqual(result["events_used"], 2)
        self.assertEqual(result["stored"], 1)
        self.assertEqual(len(_FakeStore.stored_events), 1)
        self.assertEqual(_FakeStore.stored_events[0].source, "market_context:tw_close")


if __name__ == "__main__":
    unittest.main()
