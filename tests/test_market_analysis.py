from datetime import datetime, timezone
from types import SimpleNamespace
import json
import os
import unittest
from unittest.mock import patch

from event_relay.market_analysis import (
    _build_prompts,
    _compact_event_raw_json,
    _load_config,
    _normalize_text,
    _resolve_slot,
    _resolve_slot_decision,
    run_once,
)
from event_relay.prompt_assets import TokenUsage
from event_relay.service import SummaryEvent

# Sentinel ``_call_llm`` return shape (REQ-016): every legacy-fallback mock
# now returns ``(text, TokenUsage)``.
_FAKE_LEGACY_USAGE = TokenUsage(provider="openai", model="m", prompt_tokens=10, completion_tokens=5)


class _FixedDateTime:
    current = datetime(2026, 4, 30, 8, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls):
        return cls.current


class _FakeAnalysisStore:
    """封裝 Fake Analysis Store 相關資料與行為。"""
    records = []
    signals = []
    updated_summaries = []
    summary_events = None
    latest_us_close = None

    def __init__(self, _settings) -> None:
        """初始化物件狀態與必要依賴。"""
        return None

    def initialize(self) -> None:
        """執行 initialize 方法的主要邏輯。"""
        return None

    def fetch_recent_summary_events(self, days: int, limit: int) -> list[SummaryEvent]:
        """抓取 fetch recent summary events 對應的資料或結果。"""
        if _FakeAnalysisStore.summary_events is not None:
            return _FakeAnalysisStore.summary_events
        return [
            SummaryEvent(
                row_id=101,
                source="market_context:tw_close",
                title="Taiwan close context collected 2026-04-22",
                url="internal://market_context/tw_close/2026-04-22",
                summary="Taiwan close context summary",
                published_at="2026-04-22T15:20:00+08:00",
                created_at="2026-04-22 15:20:00",
                raw_json=json.dumps(
                    {
                        "stored_only": True,
                        "event_type": "market_context_collection",
                        "dimension": "market_context",
                        "slot": "tw_close",
                        "trade_date": "2026-04-22",
                        "event_count": 1,
                        "source_counts": {"market_context:twse_flow": 1},
                    },
                    ensure_ascii=False,
                ),
            )
        ]

    def fetch_recent_market_snapshots(self, hours: int, limit: int) -> list:
        """抓取 fetch recent market snapshots 對應的資料或結果。"""
        return []

    def fetch_latest_market_analysis(self, analysis_slot: str):
        """Return latest stored analysis used as upstream context."""
        if analysis_slot == "us_close":
            return _FakeAnalysisStore.latest_us_close
        return None

    def fetch_event_annotations(self, event_row_ids: list[int]) -> dict:
        """抓取 fetch event annotations 對應的資料或結果。"""
        return {}

    def fetch_event_embedding_candidates(self, *, embedding_model: str, limit: int) -> list:
        """抓取 fetch event embedding candidates 對應的資料或結果。"""
        return []

    def upsert_market_analysis(self, record) -> int:
        """新增或更新 upsert market analysis 對應的資料或結果。"""
        _FakeAnalysisStore.records.append(record)
        return 777

    def replace_trade_signals_for_analysis(self, analysis_id: int, signals: list) -> int:
        """保存 extracted trade signals 方便測試確認。"""
        _FakeAnalysisStore.signals.append((analysis_id, list(signals)))
        return len(signals)

    def fetch_trade_signal_recommendations(self, analysis_id: int, *, limit: int = 5) -> list[dict]:
        """Return short/medium long signals for report-section tests."""
        rows = []
        for stored_analysis_id, signals in _FakeAnalysisStore.signals:
            if stored_analysis_id != analysis_id:
                continue
            for signal in signals:
                if signal.direction != "long" or signal.strategy_type not in {"swing", "medium"}:
                    continue
                rows.append(
                    {
                        "ticker": signal.ticker,
                        "name": signal.name,
                        "strategy_type": signal.strategy_type,
                        "direction": signal.direction,
                        "confidence": signal.confidence,
                        "signal_type": signal.signal_type,
                        "entry_zone": signal.entry_zone_json,
                        "invalidation": signal.invalidation_json,
                        "take_profit_zone": signal.take_profit_zone_json,
                        "holding_horizon": signal.holding_horizon,
                        "rationale": signal.rationale,
                        "risk_notes": signal.risk_notes_json,
                        "status": signal.status,
                    }
                )
        confidence_rank = {"high": 1, "medium": 2, "low": 3}
        source_rank = {"context_fallback_stock_watch": 1, "quote_fallback_stock_watch": 2}
        strategy_rank = {"swing": 1, "medium": 2}
        rows.sort(
            key=lambda row: (
                source_rank.get(str(row.get("signal_type") or ""), 3),
                confidence_rank.get(str(row.get("confidence") or ""), 4),
                strategy_rank.get(str(row.get("strategy_type") or ""), 3),
            )
        )
        return rows[:limit]

    def update_market_analysis_summary_text(self, analysis_id: int, summary_text: str) -> None:
        """Record deterministic signal-section write-back."""
        _FakeAnalysisStore.updated_summaries.append((analysis_id, summary_text))


class MarketAnalysisTests(unittest.TestCase):
    """封裝 Market Analysis Tests 相關資料與行為。"""
    def test_resolve_slot_in_window(self) -> None:
        """測試 test resolve slot in window 的預期行為。"""
        config = SimpleNamespace(slot="auto", window_minutes=25)
        now_local = datetime(2026, 4, 20, 7, 50, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "pre_tw_open")

    def test_resolve_slot_auto_tw_close_window(self) -> None:
        """測試 test resolve slot auto tw close window 的預期行為。"""
        config = SimpleNamespace(slot="auto", window_minutes=25)
        now_local = datetime(2026, 4, 22, 15, 30, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "tw_close")

    def test_resolve_slot_manual_override(self) -> None:
        """測試 test resolve slot manual override 的預期行為。"""
        config = SimpleNamespace(slot="us_close", window_minutes=25)
        now_local = datetime(2026, 4, 18, 5, 0, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "us_close")

    def test_resolve_slot_manual_tw_close_override(self) -> None:
        """測試 test resolve slot manual tw close override 的預期行為。"""
        config = SimpleNamespace(slot="tw_close", window_minutes=25)
        now_local = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "tw_close")

    def test_resolve_slot_skips_tw_analysis_on_tw_holiday(self) -> None:
        config = SimpleNamespace(slot="pre_tw_open", window_minutes=25, force=False)
        now_local = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)

        decision = _resolve_slot_decision(config, now_local)

        self.assertIsNone(decision.slot)
        self.assertEqual(decision.skipped_reason, "market_calendar")
        self.assertEqual(decision.calendar_state.to_dict()["allowed_analysis_slots"], ["us_close"])

    def test_resolve_slot_allows_us_close_on_tw_holiday_if_us_open(self) -> None:
        config = SimpleNamespace(slot="us_close", window_minutes=25, force=False)
        now_local = datetime(2026, 5, 1, 5, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(_resolve_slot(config, now_local), "us_close")

    def test_resolve_slot_routes_both_closed_to_macro_daily_owner(self) -> None:
        config = SimpleNamespace(slot="pre_tw_open", window_minutes=25, force=False)
        now_local = datetime(2026, 4, 6, 8, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(_resolve_slot(config, now_local), "macro_daily")

    def test_resolve_slot_sunday_weekly_only(self) -> None:
        config = SimpleNamespace(slot="us_close", window_minutes=25, force=False)
        now_local = datetime(2026, 5, 3, 5, 0, 0, tzinfo=timezone.utc)

        decision = _resolve_slot_decision(config, now_local)

        self.assertIsNone(decision.slot)
        self.assertEqual(decision.skipped_reason, "weekly_summary_only")

    def test_normalize_text_keeps_line_breaks(self) -> None:
        """測試 test normalize text keeps line breaks 的預期行為。"""
        text = _normalize_text("  line1   \nline2  \n")
        self.assertEqual(text, "line1\nline2")

    def test_compact_event_raw_json_only_keeps_market_context_fields(self) -> None:
        """測試 test compact event raw json only keeps market context fields 的預期行為。"""
        raw = (
            '{"event_type":"market_context_point","dimension":"market_context","slot":"pre_tw_open",'
            '"dataset":"T86_ALLBUT0999","series_id":"CUSR0000SA0",'
            '"normalized_metrics":{"value":100,"field_totals":{"Net":50}},'
            '"point":{"source":"yahoo_chart","symbol":"^NDX","value":100,"raw":{"huge":true}}}'
        )

        compact = _compact_event_raw_json("market_context:yahoo_chart", raw)
        ignored = _compact_event_raw_json("BBC News", raw)

        self.assertEqual(compact["dataset"], "T86_ALLBUT0999")
        self.assertEqual(compact["series_id"], "CUSR0000SA0")
        self.assertEqual(compact["normalized_metrics"]["field_totals"]["Net"], 50)
        self.assertEqual(compact["point"]["symbol"], "^NDX")
        self.assertNotIn("raw", compact["point"])
        self.assertIsNone(ignored)

    def test_build_prompts_contains_required_sections(self) -> None:
        """測試 test build prompts contains required sections 的預期行為。"""
        config = SimpleNamespace(skill_macro_path="", skill_line_format_path="")
        system_prompt, user_prompt = _build_prompts(
            config=config,
            slot="pre_tw_open",
            now_local=datetime(2026, 4, 19, 7, 30, 0, tzinfo=timezone.utc),
            events_json='[{"source":"market_context:yahoo_chart","raw":{"dimension":"market_context"}}]',
            market_json="[]",
        )

        self.assertIn("Traditional Chinese", system_prompt)
        self.assertIn("Evidence policy", system_prompt)
        self.assertIn("Recent events JSON includes news and stored-only market_context facts", user_prompt)
        self.assertIn("not exhaustive", user_prompt)
        self.assertIn("market_context", user_prompt)
        self.assertIn("總經 Regime", user_prompt)
        self.assertIn("利率與流動性", user_prompt)
        self.assertIn("景氣循環", user_prompt)
        self.assertIn("市場情緒", user_prompt)
        self.assertIn("台股配置", user_prompt)
        self.assertIn("Section 2 利率與流動性", user_prompt)
        self.assertNotIn("對台股的可能影響", user_prompt)
        self.assertIn("風險與資料缺口", user_prompt)

    def test_build_prompts_tw_close_contains_close_review_sections(self) -> None:
        """測試 test build prompts tw close contains close review sections 的預期行為。"""
        config = SimpleNamespace(skill_macro_path="", skill_line_format_path="")
        system_prompt, user_prompt = _build_prompts(
            config=config,
            slot="tw_close",
            now_local=datetime(2026, 4, 22, 15, 30, 0, tzinfo=timezone.utc),
            events_json='[{"source":"market_context:tw_close","raw":{"slot":"tw_close"}}]',
            market_json="[]",
        )

        self.assertIn("Taiwan close review", system_prompt)
        self.assertIn("market_context:tw_close", user_prompt)
        self.assertIn("總經 Regime", user_prompt)
        self.assertIn("利率與流動性", user_prompt)
        self.assertIn("景氣循環", user_prompt)
        self.assertIn("市場情緒", user_prompt)
        self.assertIn("台股配置", user_prompt)

    def test_run_once_tw_close_raw_json_dimension(self) -> None:
        """測試 test run once tw close raw json dimension 的預期行為。"""
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = None
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=True,
            slot="tw_close",
            provider="openai",
        )

        with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
            with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                    with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                        with patch("event_relay.market_analysis._call_llm", return_value=("tw close analysis", _FAKE_LEGACY_USAGE)):
                            with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["slot"], "tw_close")
        self.assertEqual(len(_FakeAnalysisStore.records), 1)
        record = _FakeAnalysisStore.records[0]
        self.assertEqual(record.analysis_slot, "tw_close")
        self.assertEqual(record.scheduled_time_local, "15:30")
        self.assertFalse(record.push_enabled)
        raw = json.loads(record.raw_json)
        self.assertEqual(raw["dimension"], "daily_tw_close")
        self.assertEqual(raw["slot"], "tw_close")
        self.assertEqual(raw["display_title"], "2026-04-30")
        self.assertIn("market_context:tw_close", raw["event_context_sources"])
        self.assertFalse(result["push_enabled"])

    def test_run_once_us_close_is_stored_but_not_delivery_enabled(self) -> None:
        """一般台股交易日的美股收盤分析只做早盤素材。"""
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = None
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=True,
            slot="us_close",
            provider="openai",
        )

        with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
            with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                    with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                        with patch("event_relay.market_analysis._call_llm", return_value=("us close analysis", _FAKE_LEGACY_USAGE)):
                            with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["slot"], "us_close")
        record = _FakeAnalysisStore.records[0]
        self.assertEqual(record.analysis_slot, "us_close")
        self.assertFalse(record.push_enabled)
        raw = json.loads(record.raw_json)
        self.assertFalse(raw["delivery_eligible"])
        self.assertEqual(raw["delivery_policy"], "daily_pre_tw_open_macro_or_tw_holiday_us_close")
        self.assertFalse(result["push_enabled"])

    def test_run_once_us_close_delivery_enabled_on_tw_holiday_if_us_open(self) -> None:
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = None
        previous_now = _FixedDateTime.current
        _FixedDateTime.current = datetime(2026, 5, 1, 5, 0, 0, tzinfo=timezone.utc)
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=True,
            slot="us_close",
            provider="openai",
        )

        try:
            with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
                with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                    with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                        with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                            with patch("event_relay.market_analysis._call_llm", return_value=("us close analysis", _FAKE_LEGACY_USAGE)):
                                with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                    result = run_once(config)
        finally:
            _FixedDateTime.current = previous_now

        self.assertTrue(result["ok"])
        self.assertEqual(result["slot"], "us_close")
        record = _FakeAnalysisStore.records[0]
        self.assertTrue(record.push_enabled)
        raw = json.loads(record.raw_json)
        self.assertTrue(raw["delivery_eligible"])
        self.assertEqual(raw["calendar_decision"]["calendar"]["allowed_analysis_slots"], ["us_close"])
        self.assertTrue(result["push_enabled"])

    def test_run_once_both_markets_closed_writes_macro_daily(self) -> None:
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = None
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=False,
            slot="pre_tw_open",
            provider="openai",
        )
        old_now = _FixedDateTime.current
        _FixedDateTime.current = datetime(2026, 4, 6, 8, 0, 0, tzinfo=timezone.utc)
        try:
            with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
                with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                    with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                        with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                            with patch("event_relay.market_analysis._call_llm", return_value=("macro analysis", _FAKE_LEGACY_USAGE)):
                                with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                    result = run_once(config)
        finally:
            _FixedDateTime.current = old_now

        self.assertTrue(result["ok"])
        self.assertEqual(result["slot"], "macro_daily")
        record = _FakeAnalysisStore.records[0]
        self.assertEqual(record.analysis_slot, "macro_daily")
        self.assertEqual(record.scheduled_time_local, "08:05")
        self.assertTrue(record.push_enabled)
        raw = json.loads(record.raw_json)
        self.assertEqual(raw["dimension"], "daily_macro")
        self.assertEqual(raw["calendar_decision"]["requested_slot"], "pre_tw_open")

    def test_run_once_calendar_skip_happens_before_api_key_check(self) -> None:
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key=None,
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=False,
            slot="pre_tw_open",
            provider="openai",
        )
        old_now = _FixedDateTime.current
        _FixedDateTime.current = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
        try:
            with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                result = run_once(config)
        finally:
            _FixedDateTime.current = old_now

        self.assertEqual(result["skipped"], "market_calendar")
        self.assertEqual(result["calendar"]["allowed_analysis_slots"], ["us_close"])

    def test_run_once_continues_when_rag_retrieval_fails(self) -> None:
        """測試 test run once continues when rag retrieval fails 的預期行為。"""
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = None
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=True,
            slot="pre_tw_open",
            provider="openai",
        )

        with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
            with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                    with patch("event_relay.market_analysis.retrieve_similar_events", side_effect=RuntimeError("rag down")):
                        with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                            with patch("event_relay.market_analysis._call_llm", return_value=("analysis text", _FAKE_LEGACY_USAGE)):
                                with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                    result = run_once(config)

        self.assertTrue(result["ok"])
        raw = json.loads(_FakeAnalysisStore.records[0].raw_json)
        self.assertEqual(raw["rag"]["examples_count"], 0)
        self.assertIn("rag down", raw["rag"]["error"])

    def test_build_events_payload_uses_stored_annotation_when_present(self) -> None:
        """測試 test build events payload uses stored annotation when present 的預期行為。"""
        from event_relay.market_analysis import _build_events_payload

        class _Store:
            """封裝 Store 相關資料與行為。"""
            def fetch_event_annotations(self, ids):
                """抓取 fetch event annotations 對應的資料或結果。"""
                return {
                    101: {
                        "entities": [{"kind": "policy", "value": "FOMC"}],
                        "category": "rate_decision",
                        "importance": 0.9,
                        "sentiment": "bearish",
                        "annotator": "llm",
                        "annotator_version": "gpt-4o-mini-v1",
                        "annotated_at": "2026-04-25 07:00:00",
                    }
                }

        events = [
            SummaryEvent(
                row_id=101,
                source="reuters",
                title="FOMC holds, Powell hawkish",
                url="https://example/1",
                summary="",
                published_at=None,
                created_at="2026-04-25 07:00:00",
                raw_json=None,
            )
        ]

        payload = _build_events_payload(_Store(), events)
        self.assertEqual(len(payload), 1)
        ann = payload[0]["annotation"]
        self.assertEqual(ann["annotator"], "llm")
        self.assertEqual(ann["category"], "rate_decision")
        self.assertAlmostEqual(ann["importance"], 0.9)

    def test_build_events_payload_falls_back_to_rule_annotation_when_missing(self) -> None:
        """測試 test build events payload falls back to rule annotation when missing 的預期行為。"""
        from event_relay.market_analysis import _build_events_payload

        class _Store:
            """封裝 Store 相關資料與行為。"""
            def fetch_event_annotations(self, ids):
                """抓取 fetch event annotations 對應的資料或結果。"""
                return {}

        events = [
            SummaryEvent(
                row_id=202,
                source="bloomberg",
                title="Nvidia surges to record high on AI demand",
                url="https://example/2",
                summary="",
                published_at=None,
                created_at="2026-04-25 07:00:00",
                raw_json=None,
            )
        ]

        payload = _build_events_payload(_Store(), events)
        ann = payload[0]["annotation"]
        self.assertEqual(ann["annotator"], "rule")
        self.assertEqual(ann["sentiment"], "bullish")
        self.assertIn(
            {"kind": "company", "value": "NVIDIA"},
            ann["entities"],
        )

    def test_load_config_prefers_market_analysis_env(self) -> None:
        """測試 test load config prefers market analysis env 的預期行為。"""
        old_model = os.environ.get("MARKET_ANALYSIS_MODEL")
        old_provider = os.environ.get("LLM_PROVIDER")
        try:
            os.environ["MARKET_ANALYSIS_MODEL"] = "gpt-5-mini"
            os.environ.pop("LLM_PROVIDER", None)
            args = SimpleNamespace(env_file=".env", force=False, slot="auto")

            config = _load_config(args)

            self.assertEqual(config.model, "gpt-5-mini")
            self.assertEqual(config.provider, "openai")
        finally:
            if old_model is None:
                os.environ.pop("MARKET_ANALYSIS_MODEL", None)
            else:
                os.environ["MARKET_ANALYSIS_MODEL"] = old_model
            if old_provider is None:
                os.environ.pop("LLM_PROVIDER", None)
            else:
                os.environ["LLM_PROVIDER"] = old_provider

    def test_load_config_switches_to_anthropic(self) -> None:
        """測試 test load config switches to anthropic 的預期行為。"""
        snapshot = {
            k: os.environ.get(k)
            for k in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "MARKET_ANALYSIS_MODEL")
        }
        try:
            os.environ["LLM_PROVIDER"] = "anthropic"
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
            os.environ["ANTHROPIC_MODEL"] = "claude-sonnet-4-6"
            os.environ.pop("MARKET_ANALYSIS_MODEL", None)
            args = SimpleNamespace(env_file=".env", force=False, slot="auto")

            config = _load_config(args)

            self.assertEqual(config.provider, "anthropic")
            self.assertEqual(config.model, "claude-sonnet-4-6")
            self.assertEqual(config.api_base, "https://api.anthropic.com")
            self.assertEqual(config.api_key, "sk-ant-test")
        finally:
            for k, v in snapshot.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class MultiStagePipelineTests(unittest.TestCase):
    """封裝 Multi Stage Pipeline Tests 相關資料與行為。"""
    def _base_config(self) -> SimpleNamespace:
        """執行 base config 方法的主要邏輯。"""
        return SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=20,
            max_market_rows=2,
            window_minutes=25,
            force=True,
            slot="pre_tw_open",
            provider="openai",
        )

    def _run(
        self,
        *,
        pipeline_env: str,
        stage_side_effects: dict,
        summary_events: list[SummaryEvent] | None = None,
        latest_us_close=None,
    ) -> tuple[dict, list]:
        """執行 run 方法的主要邏輯。"""
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = summary_events
        _FakeAnalysisStore.latest_us_close = latest_us_close
        from event_relay import market_analysis as module

        patches = [
            patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)),
            patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore),
            patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None),
            patch("event_relay.market_analysis._call_llm", return_value=("legacy fallback text", _FAKE_LEGACY_USAGE)),
            patch("event_relay.market_analysis.datetime", _FixedDateTime),
            patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": pipeline_env}, clear=False),
        ]
        for stage_target, side_effect in stage_side_effects.items():
            patches.append(patch(stage_target, side_effect=side_effect))

        with _nested(*patches):
            result = module.run_once(self._base_config())
        return result, _FakeAnalysisStore.records

    def test_legacy_mode_skips_pipeline(self) -> None:
        """測試 test legacy mode skips pipeline 的預期行為。"""
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _boom("stage1 should not be called"),
        }
        result, records = self._run(pipeline_env="legacy", stage_side_effects=stage_side_effects)
        self.assertTrue(result["ok"])
        raw = json.loads(records[0].raw_json)
        self.assertEqual(raw["pipeline_mode"], "legacy")
        self.assertIsNone(raw["pipeline_stages"])
        self.assertEqual(records[0].summary_text, "legacy fallback text")
        # REQ-016: legacy fallback usage is captured into raw_json.token_usage.
        token_usage = raw.get("token_usage") or {}
        self.assertEqual(token_usage["prompt_tokens"], _FAKE_LEGACY_USAGE.prompt_tokens)
        self.assertEqual(token_usage["completion_tokens"], _FAKE_LEGACY_USAGE.completion_tokens)
        self.assertEqual(len(token_usage["stages"]), 1)
        self.assertEqual(token_usage["stages"][0]["stage"], "legacy_single_call")

    def test_legacy_pre_open_prompt_includes_latest_us_close_analysis(self) -> None:
        """台股早盤 legacy prompt 會帶入上一筆美股收盤分析。"""
        captured: dict[str, str] = {}
        latest_us_close = SimpleNamespace(
            row_id=66,
            analysis_date="2026-04-27",
            analysis_slot="us_close",
            scheduled_time_local="05:00",
            summary_text="美股收盤：費半與大型科技走強，台股早盤需納入風險偏多脈絡。",
            raw_json=None,
            updated_at="2026-04-28 05:01:00",
        )

        def _fake_call_llm(*_args, **kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return "legacy fallback text", _FAKE_LEGACY_USAGE

        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = latest_us_close

        with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
            with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                    with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                        with patch("event_relay.market_analysis._call_llm", side_effect=_fake_call_llm):
                            with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                result = run_once(self._base_config())

        self.assertTrue(result["ok"])
        self.assertIn("market_analysis:us_close", captured["user_prompt"])
        self.assertIn("費半與大型科技走強", captured["user_prompt"])
        raw = json.loads(_FakeAnalysisStore.records[0].raw_json)
        self.assertTrue(raw["upstream_analysis_context"]["included"])
        self.assertEqual(raw["upstream_analysis_context"]["analysis_id"], 66)

    def test_legacy_pre_open_prompt_excludes_us_close_when_us_session_closed(self) -> None:
        """US 休市、TW 有交易時，早盤分析不帶舊的 us_close 內容。"""
        captured: dict[str, str] = {}
        latest_us_close = SimpleNamespace(
            row_id=66,
            analysis_date="2026-09-04",
            analysis_slot="us_close",
            scheduled_time_local="05:00",
            summary_text="stale us close analysis",
            raw_json=None,
            updated_at="2026-09-04 05:01:00",
        )

        def _fake_call_llm(*_args, **kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return "legacy fallback text", _FAKE_LEGACY_USAGE

        old_now = _FixedDateTime.current
        _FixedDateTime.current = datetime(2026, 9, 8, 8, 0, 0, tzinfo=timezone.utc)
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = latest_us_close

        try:
            with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
                with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                    with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                        with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                            with patch("event_relay.market_analysis._call_llm", side_effect=_fake_call_llm):
                                with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                    result = run_once(self._base_config())
        finally:
            _FixedDateTime.current = old_now

        self.assertTrue(result["ok"])
        self.assertNotIn("market_analysis:us_close", captured["user_prompt"])
        self.assertNotIn("stale us close analysis", captured["user_prompt"])
        raw = json.loads(_FakeAnalysisStore.records[0].raw_json)
        self.assertFalse(raw["upstream_analysis_context"]["included"])
        self.assertEqual(raw["upstream_analysis_context"]["reason"], "us_close_session_closed")

    def test_legacy_mode_appends_quote_fallback_trade_signal_section(self) -> None:
        """Legacy fallback still appends buy candidates from quote events."""
        quote_events = [
            SummaryEvent(
                row_id=901,
                source="yfinance_taiwan",
                title="[2026-04-24] 聯發科 (2454.TW) 2435.00 ▲9.93%",
                url="https://finance.yahoo.com/quote/2454.TW",
                summary=json.dumps(
                    {
                        "symbol": "2454.TW",
                        "name": "聯發科",
                        "price": 2435.0,
                        "prev_close": 2215.0,
                        "change_pct": 9.93,
                        "volume": 21684950,
                    },
                    ensure_ascii=False,
                ),
                published_at="2026-04-24T18:54:05+00:00",
                created_at="2026-04-24 18:54:05",
            )
        ]

        result, _records = self._run(
            pipeline_env="legacy",
            stage_side_effects={},
            summary_events=quote_events,
        )

        self.assertEqual(result["trade_signals_stored"], 1)
        self.assertEqual(result["trade_signal_recommendations"], 1)
        signal = _FakeAnalysisStore.signals[0][1][0]
        self.assertEqual(signal.ticker, "2454")
        self.assertEqual(signal.signal_type, "quote_fallback_stock_watch")
        self.assertEqual(signal.strategy_type, "swing")
        self.assertEqual(_FakeAnalysisStore.updated_summaries[0][0], 777)
        self.assertIn("legacy fallback text", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("## 今日個股觀察", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("短中線推薦買進候選", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("2454 聯發科", _FakeAnalysisStore.updated_summaries[0][1])

    def test_multi_stage_happy_path(self) -> None:
        """測試 test multi stage happy path 的預期行為。"""
        from event_relay.analysis_stages.context import StageResult

        # REQ-016: each stage attaches a ``usage`` extras row; aggregator
        # should sum these into raw_json.token_usage.
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(
                    name="stage1_digest", model="m",
                    output={"events": [{"id": 1}], "market_snapshot": {}},
                    extras={"usage": {"provider": "openai", "model": "m",
                                       "prompt_tokens": 1000, "completion_tokens": 100,
                                       "cached_tokens": 600, "cache_creation_tokens": 0}},
                )
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(
                    name="stage2_transmission", model="m", output={"chains": []},
                    extras={"usage": {"provider": "openai", "model": "m",
                                       "prompt_tokens": 500, "completion_tokens": 80,
                                       "cached_tokens": 400, "cache_creation_tokens": 0}},
                )
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(
                    name="stage3_tw_mapping",
                    model="m",
                    output={"sector_watch": [], "stock_watch": [], "risks": [], "data_gaps": []},
                    extras={"usage": {"provider": "openai", "model": "m",
                                       "prompt_tokens": 300, "completion_tokens": 60,
                                       "cached_tokens": 200, "cache_creation_tokens": 0}},
                )
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "多階段報告內容",
                        "structured": {
                            "summary_text": "多階段報告內容",
                            "headline": "Test headline",
                            "sentiment": "neutral",
                            "confidence": "medium",
                            "key_drivers": [],
                            "tw_sector_watch": [],
                            "stock_watch": [],
                            "risks": [],
                            "data_gaps": [],
                        },
                    },
                    extras={"usage": {"provider": "openai", "model": "m",
                                       "prompt_tokens": 200, "completion_tokens": 40,
                                       "cached_tokens": 100, "cache_creation_tokens": 0}},
                )
            ),
        }
        result, records = self._run(pipeline_env="multi_stage", stage_side_effects=stage_side_effects)
        self.assertTrue(result["ok"])
        self.assertEqual(records[0].summary_text, "多階段報告內容")
        raw = json.loads(records[0].raw_json)
        self.assertEqual(raw["pipeline_mode"], "multi_stage")
        self.assertEqual(raw["pipeline_stages"]["pipeline_version"], "multi-stage-v2")
        self.assertTrue(raw["pipeline_stages"]["stages"]["stage4"]["ok"])
        self.assertEqual(raw["structured"]["sentiment"], "neutral")
        self.assertIsNotNone(records[0].structured_json)
        # REQ-016: token_usage aggregates per-stage rows.
        token_usage = raw["token_usage"]
        self.assertEqual(token_usage["prompt_tokens"], 1000 + 500 + 300 + 200)
        self.assertEqual(token_usage["cached_tokens"], 600 + 400 + 200 + 100)
        self.assertEqual(token_usage["completion_tokens"], 100 + 80 + 60 + 40)
        # 1300 / 2000 = 0.65
        self.assertEqual(token_usage["cache_hit_ratio"], 0.65)
        self.assertEqual(len(token_usage["stages"]), 4)
        structured = json.loads(records[0].structured_json)
        self.assertEqual(structured["confidence"], "medium")

    def test_multi_stage_extracts_trade_signals_from_structured_stock_watch(self) -> None:
        """測試 structured stock_watch 會轉成 pending_review trade signal。"""
        from event_relay.analysis_stages.context import StageResult

        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [{"id": 101}], "market_snapshot": {}})
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(name="stage2_transmission", model="m", output={"chains": []})
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(
                    name="stage3_tw_mapping",
                    model="m",
                    output={
                        "sector_watch": [],
                        "stock_watch": [
                            {
                                "ticker": "2330",
                                "direction": "bullish",
                                "rationale": "AI demand supports TSMC supply chain",
                                "evidence_ids": [101],
                            }
                        ],
                        "risks": [],
                        "data_gaps": [],
                    },
                )
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "台股偏多，先觀察台積電。",
                        "structured": {
                            "summary_text": "台股偏多，先觀察台積電。",
                            "headline": "AI鏈偏多",
                            "sentiment": "bullish",
                            "confidence": "medium",
                            "key_drivers": ["AI demand"],
                            "tw_sector_watch": [],
                            "stock_watch": [
                                {
                                    "ticker": "2330",
                                    "market": "TW",
                                    "name": "台積電",
                                    "direction": "bullish",
                                    "rationale": "AI demand supports TSMC supply chain",
                                    "strategy_type": "swing",
                                    "entry_zone": {"low": 600, "high": 610},
                                    "invalidation": {"price": 590},
                                    "take_profit_zone": {"first": 630},
                                }
                            ],
                            "risks": [],
                            "data_gaps": [],
                        },
                    },
                )
            ),
        }

        result, _records = self._run(pipeline_env="multi_stage", stage_side_effects=stage_side_effects)

        self.assertEqual(result["trade_signals_stored"], 1)
        self.assertEqual(result["trade_signal_recommendations"], 1)
        self.assertEqual(_FakeAnalysisStore.signals[0][0], 777)
        signal = _FakeAnalysisStore.signals[0][1][0]
        self.assertEqual(signal.ticker, "2330")
        self.assertEqual(signal.direction, "long")
        self.assertEqual(signal.strategy_type, "swing")
        self.assertEqual(signal.status, "pending_review")
        self.assertEqual(json.loads(signal.source_event_ids_json), [101])
        self.assertEqual(_FakeAnalysisStore.updated_summaries[0][0], 777)
        self.assertIn("## 今日個股觀察", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("短中線推薦買進候選", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertNotIn("進場時點", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("可做波段", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("進場 low:600, high:610", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("停利 first:630", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("停損 price:590", _FakeAnalysisStore.updated_summaries[0][1])

    def test_multi_stage_tops_up_pre_open_recommendations_to_five(self) -> None:
        """structured 推薦不足 5 檔時，用近期台股報價事件補滿。"""
        from event_relay.analysis_stages.context import StageResult

        quote_events = [
            _quote_event(901, "2330.TW", "台積電", 600, 1.1, 1000),
            _quote_event(902, "2454.TW", "聯發科", 1200, 2.5, 900),
            _quote_event(903, "2308.TW", "台達電", 420, 0.4, 800),
            _quote_event(904, "2317.TW", "鴻海", 160, -0.3, 700),
            _quote_event(905, "0050.TW", "元大台灣50", 180, 0.0, 600),
        ]
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [{"id": 101}], "market_snapshot": {}})
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(name="stage2_transmission", model="m", output={"chains": []})
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(name="stage3_tw_mapping", model="m", output={"sector_watch": [], "stock_watch": []})
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "台股偏多，觀察權值電子。",
                        "structured": {
                            "summary_text": "台股偏多，觀察權值電子。",
                            "headline": "電子權值偏多",
                            "sentiment": "bullish",
                            "confidence": "medium",
                            "key_drivers": [],
                            "tw_sector_watch": [],
                            "stock_watch": [
                                {
                                    "ticker": "2330",
                                    "market": "TW",
                                    "name": "台積電",
                                    "direction": "bullish",
                                    "strategy_type": "swing",
                                    "entry_zone": {"low": 600, "high": 610},
                                }
                            ],
                            "risks": [],
                            "data_gaps": [],
                        },
                    },
                )
            ),
        }

        result, _records = self._run(
            pipeline_env="multi_stage",
            stage_side_effects=stage_side_effects,
            summary_events=quote_events,
        )

        self.assertEqual(result["trade_signal_recommendations"], 5)
        self.assertEqual(result["trade_signals_stored"], 5)
        stored_signals = _FakeAnalysisStore.signals[0][1]
        self.assertEqual([signal.ticker for signal in stored_signals], ["2330", "2454", "2308", "0050", "2317"])
        self.assertIn("2317 鴻海", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertIn("2330 台積電", _FakeAnalysisStore.updated_summaries[0][1])
        self.assertNotIn("進場時點", _FakeAnalysisStore.updated_summaries[0][1])

    def test_multi_stage_keeps_preferred_tracked_fallback_visible_when_structured_has_five(self) -> None:
        """User-configured tracked fallback stocks can still surface when LLM already emitted five ideas."""
        from event_relay.analysis_stages.context import StageResult

        preferred_env = "2485.TW:兆赫,3535.TW:晶彩科,3715.TW:定穎投控,2351.TW:順德,4749.TWO:新應材"
        quote_events = [
            _market_context_quote_event(910, "2485.TW", "兆赫", 22, 0.2, 100),
            _market_context_quote_event(911, "3535.TW", "晶彩科", 90, -0.1, 100),
            _market_context_quote_event(912, "3715.TW", "定穎投控", 75, 0.0, 100),
            _market_context_quote_event(913, "2351.TW", "順德", 110, -0.2, 100),
            _market_context_quote_event(914, "4749.TWO", "新應材", 205, 0.1, 100),
        ]
        structured_stock_watch = [
            {"ticker": "2330", "market": "TW", "direction": "bullish", "strategy_type": "swing"},
            {"ticker": "3711", "market": "TW", "direction": "bullish", "strategy_type": "swing"},
            {"ticker": "2382", "market": "TW", "direction": "bullish", "strategy_type": "swing"},
            {"ticker": "3231", "market": "TW", "direction": "bullish", "strategy_type": "swing"},
            {"ticker": "2317", "market": "TW", "direction": "bullish", "strategy_type": "medium"},
        ]
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [{"id": 101}], "market_snapshot": {}})
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(name="stage2_transmission", model="m", output={"chains": []})
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(name="stage3_tw_mapping", model="m", output={"sector_watch": [], "stock_watch": []})
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "台股偏多，觀察AI供應鏈。",
                        "structured": {
                            "summary_text": "台股偏多，觀察AI供應鏈。",
                            "headline": "AI鏈偏多",
                            "sentiment": "bullish",
                            "confidence": "low",
                            "key_drivers": [],
                            "tw_sector_watch": [],
                            "stock_watch": structured_stock_watch,
                            "risks": [],
                            "data_gaps": [],
                        },
                    },
                )
            ),
        }

        with patch.dict(os.environ, {"MARKET_CONTEXT_TW_YAHOO_SYMBOLS": preferred_env}, clear=False):
            result, _records = self._run(
                pipeline_env="multi_stage",
                stage_side_effects=stage_side_effects,
                summary_events=quote_events,
            )

        self.assertEqual(result["trade_signals_stored"], 10)
        self.assertEqual(result["trade_signal_recommendations"], 5)
        stored_tickers = [signal.ticker for signal in _FakeAnalysisStore.signals[0][1]]
        self.assertEqual(stored_tickers[-5:], ["2485", "4749", "3715", "3535", "2351"])
        rendered = _FakeAnalysisStore.updated_summaries[0][1]
        self.assertIn("1. 2485 兆赫", rendered)
        self.assertIn("2. 4749 新應材", rendered)
        self.assertIn("3. 3715 定穎投控", rendered)
        self.assertIn("4. 3535 晶彩科", rendered)
        self.assertIn("5. 2351 順德", rendered)

    def test_multi_stage_text_fallback_leaves_structured_none(self) -> None:
        """測試 test multi stage text fallback leaves structured none 的預期行為。"""
        from event_relay.analysis_stages.context import StageResult

        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [], "market_snapshot": {}})
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(name="stage2_transmission", model="m", output={"chains": []})
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(
                    name="stage3_tw_mapping",
                    model="m",
                    output={"sector_watch": [], "stock_watch": [], "risks": [], "data_gaps": []},
                )
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={"summary_text": "純文字降級", "structured": None},
                    extras={"structured_fallback": "schema_failed: bad"},
                )
            ),
        }
        result, records = self._run(pipeline_env="multi_stage", stage_side_effects=stage_side_effects)
        self.assertTrue(result["ok"])
        self.assertEqual(records[0].summary_text, "純文字降級")
        self.assertIsNone(records[0].structured_json)
        raw = json.loads(records[0].raw_json)
        self.assertIsNone(raw["structured"])

    def test_multi_stage_critic_failure_marks_critic_skipped_and_succeeds(self) -> None:
        """測試 test multi stage critic failure marks critic skipped and succeeds 的預期行為。"""
        from event_relay.analysis_stages.context import StageResult

        dual_view_payload = {
            "bull_case": {
                "thesis": "bull",
                "drivers": ["a"],
                "counter_risks": ["x"],
                "evidence_ids": [1],
            },
            "bear_case": {
                "thesis": "bear",
                "drivers": ["b"],
                "counter_risks": ["y"],
                "evidence_ids": [1],
            },
        }
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [{"id": 1}], "market_snapshot": {}})
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(name="stage2_transmission", model="m", output={"chains": []})
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(
                    name="stage3_tw_mapping",
                    model="m",
                    output={"sector_watch": [], "stock_watch": [], "risks": [], "data_gaps": []},
                )
            ),
            "event_relay.analysis_stages.stage_dual_view.run": _return(
                StageResult(name="stage_dual_view", model="m", output=dual_view_payload)
            ),
            "event_relay.analysis_stages.stage_critic.run": _return(
                StageResult(name="stage_critic", model="m", output=None, error="critic timeout")
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "在缺 critic 下仍完成的分析",
                        "structured": {
                            "summary_text": "在缺 critic 下仍完成的分析",
                            "headline": "headline",
                            "sentiment": "neutral",
                            "confidence": "low",
                            "key_drivers": [],
                            "tw_sector_watch": [],
                            "stock_watch": [],
                            "risks": [],
                            "data_gaps": [],
                        },
                    },
                )
            ),
        }
        result, records = self._run(pipeline_env="multi_stage", stage_side_effects=stage_side_effects)
        self.assertTrue(result["ok"])
        raw = json.loads(records[0].raw_json)
        self.assertEqual(raw["pipeline_mode"], "multi_stage")
        pipeline_stages = raw["pipeline_stages"]
        self.assertTrue(pipeline_stages["critic_skipped"])
        self.assertFalse(pipeline_stages["stages"]["stage_critic"]["ok"])
        self.assertEqual(pipeline_stages["bull_case"]["thesis"], "bull")
        self.assertEqual(pipeline_stages["bear_case"]["thesis"], "bear")
        self.assertIsNone(pipeline_stages["critique"])
        self.assertEqual(records[0].summary_text, "在缺 critic 下仍完成的分析")

    def test_multi_stage_stage3_failure_falls_back_to_legacy(self) -> None:
        """測試 test multi stage stage3 failure falls back to legacy 的預期行為。"""
        from event_relay.analysis_stages.context import StageResult

        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [], "market_snapshot": {}})
            ),
            "event_relay.analysis_stages.stage2_transmission.run": _return(
                StageResult(name="stage2_transmission", model="m", output={"chains": []})
            ),
            "event_relay.analysis_stages.stage3_tw_mapping.run": _return(
                StageResult(
                    name="stage3_tw_mapping", model="m", output=None, error="schema validation failed"
                )
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _boom("stage4 should not run after stage3 failure"),
        }
        result, records = self._run(pipeline_env="multi_stage", stage_side_effects=stage_side_effects)
        self.assertTrue(result["ok"])
        self.assertEqual(records[0].summary_text, "legacy fallback text")
        raw = json.loads(records[0].raw_json)
        self.assertEqual(raw["pipeline_mode"], "legacy")
        self.assertFalse(raw["pipeline_stages"]["stages"]["stage3"]["ok"])
        self.assertIn("schema validation failed", raw["pipeline_stages"]["stages"]["stage3"]["error"])


def _return(value):
    """執行 return 的主要流程。"""
    def _side_effect(*_args, **_kwargs):
        """執行 side effect 的主要流程。"""
        return value
    return _side_effect


def _quote_event(row_id: int, symbol: str, name: str, price: float, change_pct: float, volume: int) -> SummaryEvent:
    """Create a yfinance_taiwan summary event for recommendation fallback tests."""
    return SummaryEvent(
        row_id=row_id,
        source="yfinance_taiwan",
        title=f"{name} {symbol}",
        url=f"https://finance.yahoo.com/quote/{symbol}",
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
        published_at="2026-04-28T00:00:00+00:00",
        created_at="2026-04-28 08:00:00",
    )


def _market_context_quote_event(
    row_id: int, symbol: str, name: str, price: float, change_pct: float, volume: int
) -> SummaryEvent:
    """Create a tracked-stock market_context event for fallback tests."""
    return SummaryEvent(
        row_id=row_id,
        source="market_context:yahoo_chart",
        title=f"{name} {symbol}",
        url=f"https://finance.yahoo.com/quote/{symbol}",
        summary="category=tw_tracked_stock",
        published_at="2026-05-04T00:00:00+00:00",
        created_at="2026-05-04 08:00:00",
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
    )


def _boom(message):
    """執行 boom 的主要流程。"""
    def _side_effect(*_args, **_kwargs):
        """執行 side effect 的主要流程。"""
        raise AssertionError(message)
    return _side_effect


class _nested:
    """Small context-manager helper to stack an arbitrary list of patches."""

    def __init__(self, *managers) -> None:
        """初始化物件狀態與必要依賴。"""
        self._managers = managers
        self._entered: list = []

    def __enter__(self) -> None:
        """進入 context manager 並準備資源。"""
        for manager in self._managers:
            self._entered.append(manager.__enter__())
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        """離開 context manager 並釋放資源。"""
        for manager in reversed(self._managers):
            manager.__exit__(exc_type, exc, tb)


if __name__ == "__main__":
    unittest.main()
