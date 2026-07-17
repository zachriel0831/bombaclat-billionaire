from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import os
import unittest
from unittest.mock import patch

from event_relay.market_analysis import (
    _apply_provider_context_policy,
    _build_prompts,
    _compact_event_raw_json,
    _load_config,
    _normalize_text,
    _resolve_slot,
    _resolve_slot_decision,
    _sanitize_visible_report_text,
    MarketAnalysisConfig,
    SLOTS,
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
    prior_signal_references = []

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

    def fetch_trade_signal_recommendations(self, analysis_id: int, *, limit: int = 10) -> list[dict]:
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

    def fetch_recent_trade_signal_references(
        self,
        *,
        tickers,
        exclude_analysis_id: int,
        days: int = 30,
        limit: int = 80,
    ) -> list[dict]:
        """Return test-provided prior signal references."""
        wanted = {str(ticker).replace(".TW", "").replace(".TWO", "") for ticker in tickers}
        return [
            row for row in _FakeAnalysisStore.prior_signal_references
            if str(row.get("ticker") or "") in wanted
            and int(row.get("analysis_id") or 0) != int(exclude_analysis_id)
        ][:limit]

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

    def test_pre_tw_open_slot_metadata_is_0730(self) -> None:
        self.assertEqual(SLOTS["pre_tw_open"], (7, 30))

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

    def test_compact_event_raw_json_keeps_scorecard(self) -> None:
        raw = json.dumps(
            {
                "event_type": "market_context_scorecard",
                "dimension": "market_context",
                "scorecard": {
                    "overall_score": 3,
                    "dimensions": {"breadth_health": {"score": 1}},
                },
            },
            ensure_ascii=False,
        )

        compact = _compact_event_raw_json("market_context:scorecard", raw)

        self.assertEqual(compact["event_type"], "market_context_scorecard")
        self.assertEqual(compact["scorecard"]["overall_score"], 3)

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
        self.assertIn("Recent events JSON includes local news and stored-only market facts", user_prompt)
        self.assertIn("not exhaustive", user_prompt)
        self.assertIn("market_context", user_prompt)
        self.assertIn("Do not expose internal pipeline labels", user_prompt)
        self.assertIn("market scorecard", user_prompt)
        self.assertIn("07:20 market_context", user_prompt)
        self.assertIn("今日主命題", user_prompt)
        self.assertIn("三個證據", user_prompt)
        self.assertIn("市場正在定價什麼", user_prompt)
        self.assertIn("台股傳導", user_prompt)
        self.assertIn("反證條件", user_prompt)
        self.assertNotIn("6) 台股配置", user_prompt)
        self.assertIn("Do not include a dedicated 台股配置 section", user_prompt)
        self.assertIn("NVIDIA", user_prompt)
        self.assertIn("Magnificent Seven", user_prompt)
        self.assertIn("Section 2 三個證據", user_prompt)
        self.assertIn("what expectations are already in prices", user_prompt)
        self.assertNotIn("對台股的可能影響", user_prompt)
        self.assertIn("風險與資料缺口", user_prompt)

    def test_sanitize_visible_report_text_translates_internal_labels(self) -> None:
        """Reader-visible analysis text must not leak pipeline field names."""
        raw = (
            "今日一句話\n"
            "> market scorecard 為 +4，07:20 market_context 顯示風險資產有支撐。\n"
            "- Market scorecard 2026-06-25 overall +4、raw_json 與 analysis_slot 僅供內部稽核。"
            "- 本次修復只使用本地 t_relay_events、t_market_index_snapshots 與 structured_json，未呼叫外部 LLM API；claim_verifier 由 Codex guard 補查。"
            "另未呼叫外部 LLM API。"
        )

        cleaned = _sanitize_visible_report_text(raw)

        self.assertNotIn("market scorecard", cleaned)
        self.assertNotIn("Market scorecard", cleaned)
        self.assertNotIn("market_context", cleaned)
        self.assertNotIn("07:20", cleaned)
        self.assertNotIn("raw_json", cleaned)
        self.assertNotIn("analysis_slot", cleaned)
        self.assertNotIn("t_relay_events", cleaned)
        self.assertNotIn("t_market_index_snapshots", cleaned)
        self.assertNotIn("structured_json", cleaned)
        self.assertNotIn("LLM API", cleaned)
        self.assertNotIn("claim_verifier", cleaned)
        self.assertNotIn("Codex guard", cleaned)
        self.assertIn("盤前市場環境綜合指標", cleaned)
        self.assertIn("盤前市場環境資料", cleaned)
        self.assertIn("本次分析主要依據本地新聞、行情與公開資料", cleaned)
        self.assertIn("部分即時外部資料未納入", cleaned)

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
        self.assertIn("今日主命題", user_prompt)
        self.assertIn("三個證據", user_prompt)
        self.assertIn("市場正在定價什麼", user_prompt)
        self.assertIn("台股傳導", user_prompt)
        self.assertIn("反證條件", user_prompt)
        self.assertNotIn("6) 台股配置", user_prompt)

    def test_triggered_prompt_skills_match_fixed_ten_contract(self) -> None:
        """Prompt assets loaded by market_analysis must not carry stale fixed-five rules."""
        macro_skill = Path("skills/macro-weekly-summary-skill/SKILLS.md").read_text(encoding="utf-8")
        line_skill = Path("skills/line-brief-format-skill/line-weekly-brief.md").read_text(encoding="utf-8")

        self.assertIn("固定十", macro_skill)
        for text in (macro_skill, line_skill):
            self.assertIn("市場正在定價什麼", text)
            self.assertIn("台股傳導", text)
            self.assertIn("今日個股觀察", text)
            self.assertTrue("do not" in text.lower() or "不可" in text)
            self.assertNotIn("固定五", text)
        self.assertIn("`2317`", macro_skill)
        self.assertIn("`2351`", macro_skill)
        self.assertNotIn("`2603`", macro_skill)

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
        self.assertTrue(raw["context_pack"]["enabled"])
        self.assertFalse(result["push_enabled"])

    def test_run_once_context_pack_keeps_scorecard_and_official_data(self) -> None:
        captured: dict[str, str] = {}
        news_events = [
            SummaryEvent(
                row_id=1000 + index,
                source="reuters",
                title=f"high importance news {index}",
                url=f"https://example.com/news/{index}",
                summary="news",
                published_at="2026-04-30T00:00:00+00:00",
                created_at="2026-04-30 00:00:00",
                raw_json=None,
            )
            for index in range(10)
        ]
        scorecard_raw = json.dumps(
            {
                "stored_only": True,
                "event_type": "market_context_scorecard",
                "dimension": "market_context",
                "scorecard": {
                    "overall_score": 1,
                    "dimensions": {"breadth_health": {"score": 1}},
                },
            },
            ensure_ascii=False,
        )
        summary_events = [
            *news_events,
            SummaryEvent(
                row_id=1,
                source="market_context:scorecard",
                title="Market scorecard overall +1",
                url="internal://market_context/scorecard",
                summary="市場 scorecard",
                published_at="2026-04-30T07:20:00+08:00",
                created_at="2026-04-30 07:20:00",
                raw_json=scorecard_raw,
            ),
            SummaryEvent(
                row_id=2,
                source="market_context:collector",
                title="Market context collected",
                url="internal://market_context/collector",
                summary="市場情境資料",
                published_at="2026-04-30T07:20:00+08:00",
                created_at="2026-04-30 07:20:00",
                raw_json=json.dumps({"event_type": "market_context_collection", "dimension": "market_context"}, ensure_ascii=False),
            ),
            SummaryEvent(
                row_id=3,
                source="sec:NVDA",
                title="NVDA 10-Q",
                url="https://sec.gov/nvda",
                summary="official filing",
                published_at="2026-04-30T00:00:00+00:00",
                created_at="2026-04-30 00:00:00",
                raw_json=None,
            ),
        ]
        config = SimpleNamespace(
            env_file=".env",
            model="test-model",
            api_base="https://example.test",
            api_key="test-key",
            api_key_file=".secrets/test.dpapi",
            skill_macro_path="",
            skill_line_format_path="",
            lookback_hours=24,
            max_events=5,
            max_market_rows=2,
            context_pack_enabled=True,
            context_pack_candidate_limit=30,
            window_minutes=25,
            force=True,
            slot="pre_tw_open",
            provider="openai",
        )

        def _fake_call_llm(*_args, **kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return "analysis", _FAKE_LEGACY_USAGE

        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = summary_events
        _FakeAnalysisStore.latest_us_close = None
        try:
            with patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": "legacy"}, clear=False):
                with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                    with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                        with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                            with patch("event_relay.market_analysis._call_llm", side_effect=_fake_call_llm):
                                with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                    result = run_once(config)
        finally:
            _FakeAnalysisStore.summary_events = None

        self.assertTrue(result["ok"])
        self.assertIn("market_context:scorecard", captured["user_prompt"])
        self.assertIn("market_context:collector", captured["user_prompt"])
        self.assertIn("sec:NVDA", captured["user_prompt"])
        record = _FakeAnalysisStore.records[0]
        self.assertLessEqual(record.events_used, 5)
        raw = json.loads(record.raw_json)
        self.assertTrue(raw["context_pack"]["guaranteed_buckets"]["scorecard"]["satisfied"])
        self.assertGreaterEqual(raw["context_pack"]["selected_counts"]["official_data"], 1)

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

    def test_run_once_runtime_failover_openai_quota_to_anthropic(self) -> None:
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = None
        _FakeAnalysisStore.latest_us_close = None
        calls: list[str] = []
        config = MarketAnalysisConfig(
            env_file=".env",
            model="gpt-5",
            api_base="https://api.openai.com/v1",
            api_key="sk-openai-test",
            api_key_file=".secrets/openai.dpapi",
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

        def _fake_call_llm(*_args, **kwargs):
            provider = kwargs["provider"]
            calls.append(provider)
            if provider == "openai":
                raise RuntimeError("OpenAI HTTPError status=429 body=insufficient_quota")
            return "anthropic fallback analysis", TokenUsage(
                provider="anthropic",
                model=kwargs["model"],
                prompt_tokens=12,
                completion_tokens=4,
            )

        env = {
            "MARKET_ANALYSIS_PIPELINE": "legacy",
            "MARKET_ANALYSIS_RUNTIME_FAILOVER_ENABLED": "1",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "ANTHROPIC_MODEL": "claude-backup",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
                with patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore):
                    with patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None):
                        with patch("event_relay.market_analysis._call_llm", side_effect=_fake_call_llm):
                            with patch("event_relay.market_analysis.datetime", _FixedDateTime):
                                result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "anthropic")
        self.assertEqual(result["model"], "claude-backup")
        self.assertEqual(calls, ["openai", "anthropic"])
        record = _FakeAnalysisStore.records[0]
        self.assertEqual(record.model, "claude-backup")
        raw = json.loads(record.raw_json)
        self.assertEqual(raw["runtime_failover"]["from_provider"], "openai")
        self.assertEqual(raw["runtime_failover"]["to_provider"], "anthropic")
        self.assertEqual(raw["model_router"]["runtime_failover"]["to_model"], "claude-backup")

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
        old_router = os.environ.get("MARKET_ANALYSIS_MODEL_ROUTER_ENABLED")
        try:
            os.environ["MARKET_ANALYSIS_MODEL"] = "gpt-5-mini"
            os.environ["MARKET_ANALYSIS_MODEL_ROUTER_ENABLED"] = "0"
            os.environ["LLM_PROVIDER"] = "openai"
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
            if old_router is None:
                os.environ.pop("MARKET_ANALYSIS_MODEL_ROUTER_ENABLED", None)
            else:
                os.environ["MARKET_ANALYSIS_MODEL_ROUTER_ENABLED"] = old_router

    def test_load_config_switches_to_anthropic(self) -> None:
        """測試 test load config switches to anthropic 的預期行為。"""
        snapshot = {
            k: os.environ.get(k)
            for k in (
                "LLM_PROVIDER",
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_MODEL",
                "MARKET_ANALYSIS_MODEL",
                "MARKET_ANALYSIS_MODEL_ROUTER_ENABLED",
            )
        }
        try:
            os.environ["LLM_PROVIDER"] = "anthropic"
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
            os.environ["ANTHROPIC_MODEL"] = "claude-sonnet-4-6"
            os.environ["MARKET_ANALYSIS_MODEL_ROUTER_ENABLED"] = "0"
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

    def test_load_config_model_router_falls_back_to_anthropic(self) -> None:
        """Quota-aware router can switch provider before analysis."""
        env = {
            "LLM_PROVIDER": "openai",
            "MARKET_ANALYSIS_OPENAI_API_KEY": "sk-openai-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "MARKET_ANALYSIS_MODEL": "gpt-expensive",
            "ANTHROPIC_MODEL": "claude-backup",
            "MARKET_ANALYSIS_OPENAI_MONTHLY_BUDGET_USD": "10",
            "MARKET_ANALYSIS_ANTHROPIC_MONTHLY_BUDGET_USD": "10",
            "MARKET_ANALYSIS_OPENAI_ADMIN_KEY": "openai-admin",
            "MARKET_ANALYSIS_ANTHROPIC_ADMIN_KEY": "anthropic-admin",
            "MARKET_ANALYSIS_MODEL_ROUTER_ENABLED": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("event_relay.llm_quota_router.fetch_openai_month_to_date_cost_usd", return_value=10.5):
                with patch("event_relay.llm_quota_router.fetch_anthropic_month_to_date_cost_usd", return_value=1.0):
                    args = SimpleNamespace(env_file=".env", force=False, slot="auto")

                    config = _load_config(args)

        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.model, "claude-backup")
        self.assertEqual(config.api_key, "sk-ant-test")
        self.assertEqual((config.model_router or {})["selected_provider"], "anthropic")

    def test_load_config_model_router_respects_llm_provider_without_override(self) -> None:
        """Market analysis uses LLM_PROVIDER when no market-specific provider order is set."""
        env = {
            "LLM_PROVIDER": "anthropic",
            "MARKET_ANALYSIS_OPENAI_API_KEY": "sk-openai-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "MARKET_ANALYSIS_MODEL": "gpt-primary",
            "ANTHROPIC_MODEL": "claude-secondary",
            "MARKET_ANALYSIS_MODEL_ROUTER_ENABLED": "1",
            "MARKET_ANALYSIS_PRIMARY_PROVIDER": "",
            "MARKET_ANALYSIS_PROVIDER_ORDER": "",
            "MARKET_ANALYSIS_OPENAI_MONTHLY_BUDGET_USD": "",
            "MARKET_ANALYSIS_ANTHROPIC_MONTHLY_BUDGET_USD": "",
        }
        with patch.dict(os.environ, env, clear=False):
            args = SimpleNamespace(env_file=".env", force=False, slot="auto")

            config = _load_config(args)

        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.model, "claude-secondary")
        self.assertEqual((config.model_router or {})["provider_order"][:2], ["anthropic", "openai"])

    def test_anthropic_context_policy_compacts_prompt_payloads(self) -> None:
        """Claude fallback gets smaller prompt payloads while preserving scorecard context."""
        long_summary = "x" * 240
        events = [
            {
                "id": 1,
                "source": "market_context:scorecard",
                "title": "scorecard",
                "summary": long_summary,
                "url": "https://example.test/scorecard",
                "published_at": "2026-05-07",
                "raw": {"event_type": "market_context_scorecard", "scorecard": {"dimensions": {"breadth_health": {"score": -1}}}},
                "annotation": {"importance": 0.1, "category": "market_context", "sentiment": "neutral"},
            }
        ]
        events.extend(
            {
                "id": idx,
                "source": "rss",
                "title": f"event {idx}",
                "summary": long_summary,
                "url": f"https://example.test/{idx}",
                "published_at": "2026-05-07",
                "raw": {"huge": "y" * 500},
                "annotation": {"importance": float(idx % 5), "category": "macro", "sentiment": "neutral"},
            }
            for idx in range(2, 14)
        )
        env = {
            "MARKET_ANALYSIS_ANTHROPIC_MAX_EVENTS": "10",
            "MARKET_ANALYSIS_ANTHROPIC_MAX_MARKET_ROWS": "1",
            "MARKET_ANALYSIS_ANTHROPIC_RAG_K": "1",
            "MARKET_ANALYSIS_ANTHROPIC_EVENT_SUMMARY_CHARS": "120",
        }

        with patch.dict(os.environ, env, clear=False):
            compact_events, compact_market, compact_rag, telemetry = _apply_provider_context_policy(
                provider="anthropic",
                events_payload=events,
                market_payload=[{"event_id": "m1", "quote_url": "https://quote", "symbol": "SPY"}, {"event_id": "m2"}],
                rag_examples=[{"event_id": "r1", "title": "rag", "summary": long_summary}, {"event_id": "r2"}],
            )

        self.assertEqual(telemetry["mode"], "anthropic_compact")
        self.assertEqual(len(compact_events), 10)
        self.assertEqual(len(compact_market), 1)
        self.assertEqual(len(compact_rag), 1)
        self.assertEqual(compact_events[0]["source"], "market_context:scorecard")
        self.assertIn("scorecard", compact_events[0]["raw"])
        self.assertNotIn("url", compact_events[0])
        self.assertTrue(compact_events[0]["summary"].endswith("..."))


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
        prior_signal_references: list[dict] | None = None,
        slot: str = "pre_tw_open",
        now: datetime | None = None,
        extra_env: dict[str, str] | None = None,
        legacy_text: str = "legacy fallback text",
    ) -> tuple[dict, list]:
        """執行 run 方法的主要邏輯。"""
        _FakeAnalysisStore.records = []
        _FakeAnalysisStore.signals = []
        _FakeAnalysisStore.updated_summaries = []
        _FakeAnalysisStore.summary_events = summary_events
        _FakeAnalysisStore.latest_us_close = latest_us_close
        _FakeAnalysisStore.prior_signal_references = prior_signal_references or []
        from event_relay import market_analysis as module
        config = self._base_config()
        config.slot = slot
        old_now = _FixedDateTime.current
        if now is not None:
            _FixedDateTime.current = now

        env = {
            "MARKET_ANALYSIS_PIPELINE": pipeline_env,
            "MARKET_ANALYSIS_US_CLOSE_PIPELINE": "",
            "MARKET_ANALYSIS_US_CLOSE_DIGEST_MAX_EVENTS": "",
            "MARKET_ANALYSIS_US_CLOSE_DIGEST_MAX_MARKET_ROWS": "",
            "MARKET_ANALYSIS_PRE_TW_OPEN_PIPELINE": "",
            "MARKET_ANALYSIS_TW_CLOSE_PIPELINE": "",
            "MARKET_ANALYSIS_MACRO_DAILY_PIPELINE": "",
            "MARKET_ANALYSIS_CLAIM_GATE_ENABLED": "",
        }
        if extra_env:
            env.update(extra_env)
        patches = [
            patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)),
            patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore),
            patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None),
            patch("event_relay.market_analysis._call_llm", return_value=(legacy_text, _FAKE_LEGACY_USAGE)),
            patch("event_relay.market_analysis.datetime", _FixedDateTime),
            patch.dict(os.environ, env, clear=False),
        ]
        for stage_target, side_effect in stage_side_effects.items():
            patches.append(patch(stage_target, side_effect=side_effect))

        try:
            with _nested(*patches):
                result = module.run_once(config)
        finally:
            _FixedDateTime.current = old_now
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

    def test_us_close_slot_digest_override_skips_multi_stage_and_recommendations(self) -> None:
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _boom("stage1 should not be called"),
        }
        result, records = self._run(
            pipeline_env="multi_stage",
            stage_side_effects=stage_side_effects,
            slot="us_close",
            extra_env={
                "MARKET_ANALYSIS_US_CLOSE_PIPELINE": "digest",
                "MARKET_ANALYSIS_US_CLOSE_DIGEST_MAX_EVENTS": "12",
                "MARKET_ANALYSIS_US_CLOSE_DIGEST_MAX_MARKET_ROWS": "2",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["trade_signals_stored"], 0)
        self.assertEqual(result["trade_signal_recommendations"], 0)
        raw = json.loads(records[0].raw_json)
        self.assertEqual(raw["requested_pipeline_mode"], "digest")
        self.assertEqual(raw["pipeline_mode"], "digest")
        self.assertEqual(raw["analysis_intent"], "us_close_digest_for_preopen")
        self.assertIsNone(raw["pipeline_stages"])
        self.assertTrue(raw["provider_context_policy"]["digest_policy"]["enabled"])

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

    def test_legacy_mode_keeps_trade_signals_internal_without_visible_section(self) -> None:
        """Legacy fallback keeps fixed-pool signals internal and does not append the daily section."""
        quote_events = [
            SummaryEvent(
                row_id=901,
                source="yfinance_taiwan",
                title="[2026-04-24] 聯發科 (2454.TW) 1200.00 ▲2.50%",
                url="https://finance.yahoo.com/quote/2454.TW",
                summary=json.dumps(
                    {
                        "symbol": "2454.TW",
                        "name": "聯發科",
                        "price": 1200.0,
                        "prev_close": 1170.7,
                        "change_pct": 2.5,
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
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])

    def test_claim_verifier_allows_fixed_pool_tickers_without_quote_evidence(self) -> None:
        """Fixed-pool ticker names in structured signal context are allowed claims."""
        result, records = self._run(
            pipeline_env="legacy",
            stage_side_effects={},
            summary_events=[],
            legacy_text="Fixed pool watch: 2330 2317 2454.",
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["push_enabled"])
        raw = json.loads(records[0].raw_json)
        self.assertTrue(raw["claim_verifier"]["ok"])
        self.assertEqual(raw["claim_verifier"]["unsupported_counts"]["tickers"], 0)
        self.assertEqual(raw["trust_gate"]["reason"], "claim_verifier_ok")

    def test_claim_verifier_failure_blocks_delivery_and_trade_signals(self) -> None:
        """Unsupported claims keep the row stored but block delivery and signal extraction."""
        quote_events = [
            _quote_event(901, "2454.TW", "聯發科", 1200.0, 2.5, 21684950)
        ]

        result, records = self._run(
            pipeline_env="legacy",
            stage_side_effects={},
            summary_events=quote_events,
            legacy_text="2454 聯發科目標價 9999 元。",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["push_enabled"])
        self.assertEqual(result["trade_signals_stored"], 0)
        self.assertEqual(result["trade_signal_recommendations"], 0)
        self.assertEqual(_FakeAnalysisStore.signals, [])
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])
        record = records[0]
        self.assertFalse(record.push_enabled)
        raw = json.loads(record.raw_json)
        self.assertFalse(raw["claim_verifier"]["ok"])
        self.assertTrue(any(item.startswith("9999") for item in raw["claim_verifier"]["unsupported"]["numbers"]))
        self.assertFalse(raw["delivery_eligible"])
        self.assertTrue(raw["delivery_eligible_before_trust_gate"])
        self.assertEqual(raw["trust_gate"]["reason"], "claim_verifier_failed")
        self.assertTrue(raw["trust_gate"]["delivery_blocked"])
        self.assertTrue(raw["trust_gate"]["signals_blocked"])
        self.assertFalse(raw["trust_gate"]["signals_allowed"])
        self.assertEqual(result["trust_gate"]["reason"], "claim_verifier_failed")

    def test_claim_verifier_gate_can_be_disabled(self) -> None:
        """Emergency override keeps old delivery behavior while retaining verifier telemetry."""
        quote_events = [
            _quote_event(901, "2454.TW", "聯發科", 1200.0, 2.5, 21684950)
        ]

        result, records = self._run(
            pipeline_env="legacy",
            stage_side_effects={},
            summary_events=quote_events,
            legacy_text="2454 聯發科目標價 9999 元。",
            extra_env={"MARKET_ANALYSIS_CLAIM_GATE_ENABLED": "0"},
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["push_enabled"])
        self.assertEqual(result["trade_signals_stored"], 1)
        self.assertEqual(result["trade_signal_recommendations"], 1)
        record = records[0]
        self.assertTrue(record.push_enabled)
        raw = json.loads(record.raw_json)
        self.assertFalse(raw["claim_verifier"]["ok"])
        self.assertTrue(raw["delivery_eligible"])
        self.assertEqual(raw["trust_gate"]["reason"], "disabled")
        self.assertFalse(raw["trust_gate"]["delivery_blocked"])
        self.assertFalse(raw["trust_gate"]["signals_blocked"])

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
        self.assertEqual(raw["pipeline_stages"]["pipeline_version"], "multi-stage-v3")
        self.assertIn("stage0", raw["pipeline_stages"]["stages"])
        self.assertIn("claim_verifier", raw)
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

        result, _records = self._run(
            pipeline_env="multi_stage",
            stage_side_effects=stage_side_effects,
            summary_events=[_quote_event(901, "2330.TW", "台積電", 600.0, 1.0, 1000000)],
        )

        self.assertEqual(result["trade_signals_stored"], 1)
        self.assertEqual(result["trade_signal_recommendations"], 1)
        self.assertEqual(_FakeAnalysisStore.signals[0][0], 777)
        signal = _FakeAnalysisStore.signals[0][1][0]
        self.assertEqual(signal.ticker, "2330")
        self.assertEqual(signal.direction, "long")
        self.assertEqual(signal.strategy_type, "swing")
        self.assertEqual(signal.status, "pending_review")
        self.assertEqual(json.loads(signal.source_event_ids_json), [101])
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])

    def test_us_close_keeps_recommendations_internal_and_fills_missing_levels(self) -> None:
        """U.S. close keeps fixed-pool rows internal while preserving price references."""
        from event_relay.analysis_stages.context import StageResult

        quote_events = [
            _quote_event(901, "2330.TW", "台積電", 600.0, 6.14, 1000000)
        ]
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _return(
                StageResult(name="stage1_digest", model="m", output={"events": [{"id": 901}], "market_snapshot": {}})
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
                                "rationale": "AI demand and SOX strength support a swing setup",
                                "evidence_ids": [901],
                            }
                        ],
                        "risks": [],
                        "data_gaps": [],
                    },
                )
            ),
            "event_relay.analysis_stages.stage_dual_view.run": _return(
                StageResult(name="stage_dual_view", model="m", output={"bull_case": {}, "bear_case": {}})
            ),
            "event_relay.analysis_stages.stage_critic.run": _return(
                StageResult(
                    name="stage_critic",
                    model="m",
                    output={
                        "issues": [],
                        "suggestions": [],
                        "top_counterpoint": "TSM leadership is still required.",
                        "confidence_recommendation": "medium",
                    },
                )
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "U.S. close report",
                        "structured": {
                            "summary_text": "U.S. close report",
                            "headline": "AI setup",
                            "sentiment": "bullish",
                            "confidence": "medium",
                            "key_drivers": ["SOX strength"],
                            "tw_sector_watch": [],
                            "stock_watch": [
                                {
                                    "ticker": "2330",
                                    "market": "TW",
                                    "name": None,
                                    "direction": "bullish",
                                    "rationale": "AI demand and SOX strength support a swing setup",
                                    "strategy_type": "swing",
                                    "entry_zone": None,
                                    "invalidation": None,
                                    "take_profit_zone": None,
                                    "holding_horizon": None,
                                    "confidence": "medium",
                                    "risk_notes": [],
                                    "evidence_ids": [901],
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
            slot="us_close",
            now=datetime(2026, 5, 9, 1, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["trade_signals_stored"], 1)
        self.assertEqual(result["trade_signal_recommendations"], 1)
        signal = _FakeAnalysisStore.signals[0][1][0]
        self.assertEqual(signal.ticker, "2330")
        self.assertIsNotNone(signal.entry_zone_json)
        self.assertIsNotNone(signal.invalidation_json)
        self.assertIsNotNone(signal.take_profit_zone_json)
        self.assertEqual(json.loads(signal.entry_zone_json)["low"], 591.0)
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])

    def test_multi_stage_tops_up_pre_open_recommendations_to_ten(self) -> None:
        """structured 觀察不足 10 檔時，只用固定池報價事件補滿。"""
        from event_relay.analysis_stages.context import StageResult

        quote_events = [
            _quote_event(901, "2330.TW", "台積電", 600, 1.1, 1000),
            _quote_event(902, "2454.TW", "聯發科", 1200, 9.0, 9000),
            _quote_event(903, "2317.TW", "鴻海", 220, 7.0, 900),
            _quote_event(904, "2308.TW", "台達電", 500, 6.0, 800),
            _quote_event(905, "2881.TW", "富邦金", 90, 3.0, 700),
            _quote_event(906, "2485.TW", "兆赫", 43, 2.0, 600),
            _quote_event(907, "3535.TW", "晶彩科", 120, 1.5, 500),
            _quote_event(908, "3715.TW", "定穎投控", 180, 0.2, 400),
            _quote_event(909, "2351.TW", "順德", 130, 0.0, 300),
            _quote_event(910, "2882.TW", "國泰金", 70, -0.3, 700),
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
            "event_relay.analysis_stages.stage_dual_view.run": _return(
                StageResult(name="stage_dual_view", model="m", output={"bull_case": {}, "bear_case": {}})
            ),
            "event_relay.analysis_stages.stage_critic.run": _return(
                StageResult(name="stage_critic", model="m", output={"issues": []})
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

        self.assertEqual(result["trade_signal_recommendations"], 10)
        self.assertEqual(result["trade_signals_stored"], 10)
        stored_signals = _FakeAnalysisStore.signals[0][1]
        self.assertEqual(
            [signal.ticker for signal in stored_signals],
            ["2330", "2454", "2317", "2308", "2881", "2485", "3535", "3715", "2351", "2882"],
        )
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])

    def test_multi_stage_keeps_fixed_pool_fallback_internal_when_structured_has_outside_tickers(self) -> None:
        """Configured fallback can only store fixed-pool tickers and stays out of visible daily text."""
        from event_relay.analysis_stages.context import StageResult

        preferred_env = "2485.TW:兆赫,3535.TW:晶彩科,3715.TW:定穎投控,2351.TW:順德,4749.TWO:新應材"
        quote_events = [
            _market_context_quote_event(901, "2330.TW", "台積電", 600, 1.0, 1000),
            _market_context_quote_event(902, "2317.TW", "鴻海", 220, 0.8, 1000),
            _market_context_quote_event(903, "3711.TW", "日月光投控", 180, 0.4, 1000),
            _market_context_quote_event(904, "2382.TW", "廣達", 300, 0.3, 1000),
            _market_context_quote_event(905, "3231.TW", "緯創", 120, 0.2, 1000),
            _market_context_quote_event(910, "2454.TW", "聯發科", 1200, 9.0, 9000),
            _market_context_quote_event(911, "2308.TW", "台達電", 500, 5.0, 5000),
            _market_context_quote_event(912, "2881.TW", "富邦金", 90, 3.0, 700),
            _market_context_quote_event(914, "4749.TWO", "新應材", 205, 0.1, 100),
            _market_context_quote_event(915, "2882.TW", "國泰金", 70, 0.05, 100),
            _market_context_quote_event(916, "2485.TW", "兆赫", 43, 1.5, 100),
            _market_context_quote_event(917, "3535.TW", "晶彩科", 120, 2.0, 100),
            _market_context_quote_event(918, "3715.TW", "定穎投控", 180, 0.1, 100),
            _market_context_quote_event(919, "2351.TW", "順德", 130, -0.1, 100),
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
            "event_relay.analysis_stages.stage_dual_view.run": _return(
                StageResult(name="stage_dual_view", model="m", output={"bull_case": {}, "bear_case": {}})
            ),
            "event_relay.analysis_stages.stage_critic.run": _return(
                StageResult(name="stage_critic", model="m", output={"issues": []})
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
        self.assertEqual(result["trade_signal_recommendations"], 10)
        stored_tickers = [signal.ticker for signal in _FakeAnalysisStore.signals[0][1]]
        self.assertEqual(
            stored_tickers,
            ["2330", "2317", "3535", "2485", "3715", "2351", "2454", "2308", "2881", "2882"],
        )
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])

    def test_multi_stage_uses_prior_signal_reference_for_missing_fixed_pool_ticker(self) -> None:
        """When today's evidence is thin, prior same-ticker levels can seed internal signal context."""
        from event_relay.analysis_stages.context import StageResult

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
            "event_relay.analysis_stages.stage_dual_view.run": _return(
                StageResult(name="stage_dual_view", model="m", output={"bull_case": {}, "bear_case": {}})
            ),
            "event_relay.analysis_stages.stage_critic.run": _return(
                StageResult(name="stage_critic", model="m", output={"issues": []})
            ),
            "event_relay.analysis_stages.stage4_synthesis.run": _return(
                StageResult(
                    name="stage4_synthesis",
                    model="m",
                    output={
                        "summary_text": "台股偏多，先看台積電。",
                        "structured": {
                            "summary_text": "台股偏多，先看台積電。",
                            "headline": "權值偏多",
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
                                    "entry_zone": {"low": 1000, "high": 1020},
                                }
                            ],
                            "risks": [],
                            "data_gaps": [],
                        },
                    },
                )
            ),
        }
        prior_refs = [
            {
                "id": 61,
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
                "rationale": "上漲邏輯：AI server orders. 低估/補漲：relative laggard. 買入理由：entry zone retest.",
                "updated_at": "2026-05-09 08:00:00",
            }
        ]

        result, _records = self._run(
            pipeline_env="multi_stage",
            stage_side_effects=stage_side_effects,
            summary_events=[_quote_event(901, "2330.TW", "台積電", 1000.0, 1.0, 1000000)],
            prior_signal_references=prior_refs,
        )

        self.assertEqual(result["trade_signals_stored"], 2)
        self.assertEqual(result["trade_signal_recommendations"], 2)
        self.assertEqual(result["prior_signal_references"], 1)
        stored = _FakeAnalysisStore.signals[0][1]
        self.assertEqual([signal.ticker for signal in stored], ["2330", "2317"])
        self.assertEqual(stored[1].signal_type, "prior_signal_stock_watch")
        self.assertEqual(stored[1].confidence, "low")
        self.assertEqual(json.loads(stored[1].entry_zone_json)["low"], 205)
        self.assertEqual(_FakeAnalysisStore.updated_summaries, [])

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
