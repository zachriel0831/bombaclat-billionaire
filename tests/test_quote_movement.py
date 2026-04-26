import unittest

from event_relay.quote_movement import (
    DIMENSION,
    MovementThresholds,
    QuoteContext,
    SOURCE_PREFIX,
    build_event_id,
    detect_movement_events,
)


class GapDetectionTests(unittest.TestCase):
    """封裝 Gap Detection Tests 相關資料與行為。"""
    def test_gap_up_above_threshold(self) -> None:
        """測試 test gap up above threshold 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=605.0,
            last_price=605.0,
            volume=None,
            context=QuoteContext(prev_close=595.0),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertIn("gap_up", types)

    def test_gap_down_below_negative_threshold(self) -> None:
        """測試 test gap down below negative threshold 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=585.0,
            last_price=585.0,
            volume=None,
            context=QuoteContext(prev_close=600.0),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertIn("gap_down", types)

    def test_no_gap_within_threshold(self) -> None:
        """測試 test no gap within threshold 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=601.0,
            last_price=601.0,
            volume=None,
            context=QuoteContext(prev_close=600.0),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertNotIn("gap_up", types)
        self.assertNotIn("gap_down", types)

    def test_no_gap_when_prev_close_missing(self) -> None:
        """測試 test no gap when prev close missing 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=600.0,
            last_price=600.0,
            volume=None,
            context=QuoteContext(prev_close=None),
        )
        self.assertEqual(events, [])


class SharpMoveTests(unittest.TestCase):
    """封裝 Sharp Move Tests 相關資料與行為。"""
    def test_sharp_up_emits_when_above_threshold(self) -> None:
        """測試 test sharp up emits when above threshold 的預期行為。"""
        events = detect_movement_events(
            symbol="AAPL",
            market="US",
            session="regular",
            trade_date="2026-04-25",
            open_price=200.0,
            last_price=210.0,
            volume=None,
            context=QuoteContext(prev_close=200.0),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertIn("sharp_up", types)

    def test_sharp_down_at_negative_threshold(self) -> None:
        """測試 test sharp down at negative threshold 的預期行為。"""
        events = detect_movement_events(
            symbol="AAPL",
            market="US",
            session="regular",
            trade_date="2026-04-25",
            open_price=200.0,
            last_price=194.0,
            volume=None,
            context=QuoteContext(prev_close=200.0),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertIn("sharp_down", types)

    def test_below_threshold_no_sharp(self) -> None:
        """測試 test below threshold no sharp 的預期行為。"""
        events = detect_movement_events(
            symbol="AAPL",
            market="US",
            session="regular",
            trade_date="2026-04-25",
            open_price=200.0,
            last_price=204.0,
            volume=None,
            context=QuoteContext(prev_close=200.0),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertNotIn("sharp_up", types)
        self.assertNotIn("sharp_down", types)


class VolumeSpikeTests(unittest.TestCase):
    """封裝 Volume Spike Tests 相關資料與行為。"""
    def test_spike_above_multiple(self) -> None:
        """測試 test spike above multiple 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=600.0,
            last_price=600.0,
            volume=50_000_000,
            context=QuoteContext(prev_close=600.0, n_day_avg_volume=20_000_000),
        )
        spike = [e for e in events if e["raw_json"]["event_type"] == "volume_spike"]
        self.assertEqual(len(spike), 1)
        metric = spike[0]["raw_json"]["metric"]
        self.assertEqual(metric["volume_ratio"], 2.5)

    def test_no_spike_when_below(self) -> None:
        """測試 test no spike when below 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=600.0,
            last_price=600.0,
            volume=20_000_000,
            context=QuoteContext(prev_close=600.0, n_day_avg_volume=20_000_000),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertNotIn("volume_spike", types)

    def test_no_spike_when_avg_unknown(self) -> None:
        """測試 test no spike when avg unknown 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=600.0,
            last_price=600.0,
            volume=99_999_999,
            context=QuoteContext(prev_close=600.0, n_day_avg_volume=None),
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertNotIn("volume_spike", types)


class CompositeAndContractTests(unittest.TestCase):
    """封裝 Composite And Contract Tests 相關資料與行為。"""
    def test_gap_and_sharp_and_spike_can_coexist(self) -> None:
        """測試 test gap and sharp and spike can coexist 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=618.0,           # +3% gap
            last_price=625.0,           # +4.16% sharp
            volume=80_000_000,          # 4x avg
            context=QuoteContext(prev_close=600.0, n_day_avg_volume=20_000_000),
        )
        types = sorted(e["raw_json"]["event_type"] for e in events)
        self.assertEqual(types, ["gap_up", "sharp_up", "volume_spike"])

    def test_event_contract_fields(self) -> None:
        """測試 test event contract fields 的預期行為。"""
        events = detect_movement_events(
            symbol="2330.TW",
            market="TW",
            session="regular",
            trade_date="2026-04-25",
            open_price=618.0,
            last_price=618.0,
            volume=None,
            context=QuoteContext(prev_close=600.0),
        )
        self.assertEqual(len(events), 2)  # gap_up + sharp_up
        for evt in events:
            self.assertEqual(evt["source"], f"{SOURCE_PREFIX}:tw")
            self.assertEqual(evt["raw_json"]["dimension"], DIMENSION)
            self.assertIn("metric", evt["raw_json"])
            self.assertEqual(evt["raw_json"]["symbol"], "2330.TW")
            self.assertEqual(evt["raw_json"]["market"], "TW")

    def test_event_id_is_stable_per_day_and_type(self) -> None:
        """測試 test event id is stable per day and type 的預期行為。"""
        eid_a = build_event_id("TW", "2330.TW", "2026-04-25", "gap_up")
        eid_b = build_event_id("TW", "2330.TW", "2026-04-25", "gap_up")
        self.assertEqual(eid_a, eid_b)
        eid_c = build_event_id("TW", "2330.TW", "2026-04-25", "gap_down")
        self.assertNotEqual(eid_a, eid_c)
        eid_d = build_event_id("TW", "2330.TW", "2026-04-26", "gap_up")
        self.assertNotEqual(eid_a, eid_d)

    def test_threshold_override(self) -> None:
        # 0.5% open move would not trip default 1% gap_pct, but trips lowered threshold
        """測試 test threshold override 的預期行為。"""
        loose = MovementThresholds(gap_pct=0.004, sharp_pct=0.999, volume_multiple=999.0)
        events = detect_movement_events(
            symbol="X",
            market="US",
            session="regular",
            trade_date="2026-04-25",
            open_price=100.5,
            last_price=100.5,
            volume=None,
            context=QuoteContext(prev_close=100.0),
            thresholds=loose,
        )
        types = [e["raw_json"]["event_type"] for e in events]
        self.assertIn("gap_up", types)


if __name__ == "__main__":
    unittest.main()
