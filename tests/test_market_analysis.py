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
    run_once,
)
from event_relay.service import SummaryEvent


class _FakeAnalysisStore:
    records = []

    def __init__(self, _settings) -> None:
        return None

    def initialize(self) -> None:
        return None

    def fetch_recent_summary_events(self, days: int, limit: int) -> list[SummaryEvent]:
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
        return []

    def fetch_event_annotations(self, event_row_ids: list[int]) -> dict:
        return {}

    def upsert_market_analysis(self, record) -> None:
        _FakeAnalysisStore.records.append(record)


class MarketAnalysisTests(unittest.TestCase):
    def test_resolve_slot_in_window(self) -> None:
        config = SimpleNamespace(slot="auto", window_minutes=25)
        now_local = datetime(2026, 4, 20, 7, 50, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "pre_tw_open")

    def test_resolve_slot_auto_tw_close_window(self) -> None:
        config = SimpleNamespace(slot="auto", window_minutes=25)
        now_local = datetime(2026, 4, 22, 15, 30, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "tw_close")

    def test_resolve_slot_manual_override(self) -> None:
        config = SimpleNamespace(slot="us_close", window_minutes=25)
        now_local = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "us_close")

    def test_resolve_slot_manual_tw_close_override(self) -> None:
        config = SimpleNamespace(slot="tw_close", window_minutes=25)
        now_local = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "tw_close")

    def test_normalize_text_keeps_line_breaks(self) -> None:
        text = _normalize_text("  line1   \nline2  \n")
        self.assertEqual(text, "line1\nline2")

    def test_compact_event_raw_json_only_keeps_market_context_fields(self) -> None:
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
        self.assertIn("美股收盤重點", user_prompt)
        self.assertIn("對台股的可能影響", user_prompt)
        self.assertIn("風險與資料缺口", user_prompt)

    def test_build_prompts_tw_close_contains_close_review_sections(self) -> None:
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
        self.assertIn("台股收盤復盤", user_prompt)
        self.assertIn("法人/期權/融資券", user_prompt)
        self.assertIn("類股輪動", user_prompt)
        self.assertIn("隔日觀察與風險", user_prompt)

    def test_run_once_tw_close_raw_json_dimension(self) -> None:
        _FakeAnalysisStore.records = []
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
                        with patch("event_relay.market_analysis._call_llm", return_value="tw close analysis"):
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
        self.assertIn("market_context:tw_close", raw["event_context_sources"])
        self.assertFalse(result["push_enabled"])

    def test_build_events_payload_uses_stored_annotation_when_present(self) -> None:
        from event_relay.market_analysis import _build_events_payload

        class _Store:
            def fetch_event_annotations(self, ids):
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
        from event_relay.market_analysis import _build_events_payload

        class _Store:
            def fetch_event_annotations(self, ids):
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
    def _base_config(self) -> SimpleNamespace:
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

    def _run(self, *, pipeline_env: str, stage_side_effects: dict) -> tuple[dict, list]:
        _FakeAnalysisStore.records = []
        from event_relay import market_analysis as module

        patches = [
            patch("event_relay.market_analysis.load_settings", return_value=SimpleNamespace(mysql_enabled=True)),
            patch("event_relay.market_analysis.MySqlEventStore", _FakeAnalysisStore),
            patch("event_relay.market_analysis._write_prompt_snapshots", return_value=None),
            patch("event_relay.market_analysis._call_llm", return_value="legacy fallback text"),
            patch.dict(os.environ, {"MARKET_ANALYSIS_PIPELINE": pipeline_env}, clear=False),
        ]
        for stage_target, side_effect in stage_side_effects.items():
            patches.append(patch(stage_target, side_effect=side_effect))

        with _nested(*patches):
            result = module.run_once(self._base_config())
        return result, _FakeAnalysisStore.records

    def test_legacy_mode_skips_pipeline(self) -> None:
        stage_side_effects = {
            "event_relay.analysis_stages.stage1_digest.run": _boom("stage1 should not be called"),
        }
        result, records = self._run(pipeline_env="legacy", stage_side_effects=stage_side_effects)
        self.assertTrue(result["ok"])
        raw = json.loads(records[0].raw_json)
        self.assertEqual(raw["pipeline_mode"], "legacy")
        self.assertIsNone(raw["pipeline_stages"])
        self.assertEqual(records[0].summary_text, "legacy fallback text")

    def test_multi_stage_happy_path(self) -> None:
        from event_relay.analysis_stages.context import StageResult

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
        structured = json.loads(records[0].structured_json)
        self.assertEqual(structured["confidence"], "medium")

    def test_multi_stage_text_fallback_leaves_structured_none(self) -> None:
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
    def _side_effect(*_args, **_kwargs):
        return value
    return _side_effect


def _boom(message):
    def _side_effect(*_args, **_kwargs):
        raise AssertionError(message)
    return _side_effect


class _nested:
    """Small context-manager helper to stack an arbitrary list of patches."""

    def __init__(self, *managers) -> None:
        self._managers = managers
        self._entered: list = []

    def __enter__(self) -> None:
        for manager in self._managers:
            self._entered.append(manager.__enter__())
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        for manager in reversed(self._managers):
            manager.__exit__(exc_type, exc, tb)


if __name__ == "__main__":
    unittest.main()
