from datetime import datetime, timezone
from typing import Any
import unittest
from unittest.mock import patch

from event_relay.analysis_stages.context import StageContext
from event_relay.analysis_stages.schemas import (
    STAGE1_DIGEST_SCHEMA,
    STAGE2_TRANSMISSION_SCHEMA,
    STAGE3_TW_MAPPING_SCHEMA,
    STAGE_CRITIC_SCHEMA,
    STAGE_DUAL_VIEW_SCHEMA,
    SchemaValidationError,
    assert_evidence_ids_covered,
    validate_against_schema,
)
from event_relay.analysis_stages import (
    stage1_digest,
    stage2_transmission,
    stage3_tw_mapping,
    stage4_synthesis,
    stage_critic,
    stage_dual_view,
)


_VALID_STAGE1 = {
    "events": [
        {
            "id": 101,
            "category": "rate_decision",
            "importance": 0.9,
            "entities": ["FOMC", "US Treasury"],
            "sentiment": "bullish",
            "one_line_fact": "Fed cut policy rate by 25bp.",
        }
    ],
    "market_snapshot": {"us_close": {"spx_pct": 0.8}},
}

_VALID_STAGE2 = {
    "chains": [
        {
            "trigger_event_ids": [101],
            "path": "FOMC dovish -> US 10y down -> TW semi beta",
            "direction": "bullish",
            "strength": 0.7,
            "assumptions": ["10y yield stays below 4.2%"],
        }
    ]
}

_VALID_STAGE3 = {
    "sector_watch": [
        {
            "sector": "半導體上游",
            "direction": "bullish",
            "rationale": "利率下行放大 AI 資本支出預期",
            "evidence_ids": [101],
        }
    ],
    "stock_watch": [],
    "risks": ["若通膨再加速則反轉"],
    "data_gaps": ["需確認費半盤後走勢"],
}


class SchemaValidationTests(unittest.TestCase):
    def test_stage1_accepts_valid_payload(self) -> None:
        validate_against_schema(_VALID_STAGE1, STAGE1_DIGEST_SCHEMA)

    def test_stage1_rejects_bad_importance(self) -> None:
        bad = {
            "events": [
                {
                    **_VALID_STAGE1["events"][0],
                    "importance": 1.5,
                }
            ],
            "market_snapshot": {},
        }
        with self.assertRaises(SchemaValidationError):
            validate_against_schema(bad, STAGE1_DIGEST_SCHEMA)

    def test_stage1_rejects_unknown_category(self) -> None:
        bad = {
            "events": [
                {
                    **_VALID_STAGE1["events"][0],
                    "category": "alien_invasion",
                }
            ],
            "market_snapshot": {},
        }
        with self.assertRaises(SchemaValidationError):
            validate_against_schema(bad, STAGE1_DIGEST_SCHEMA)

    def test_stage1_rejects_additional_top_level_key(self) -> None:
        bad = dict(_VALID_STAGE1, extra_key="nope")
        with self.assertRaises(SchemaValidationError):
            validate_against_schema(bad, STAGE1_DIGEST_SCHEMA)

    def test_stage2_requires_assumptions(self) -> None:
        chain = dict(_VALID_STAGE2["chains"][0])
        chain.pop("assumptions")
        with self.assertRaises(SchemaValidationError):
            validate_against_schema({"chains": [chain]}, STAGE2_TRANSMISSION_SCHEMA)

    def test_stage3_accepts_valid_payload(self) -> None:
        validate_against_schema(_VALID_STAGE3, STAGE3_TW_MAPPING_SCHEMA)

    def test_stage3_requires_evidence_ids_array(self) -> None:
        bad = {
            **_VALID_STAGE3,
            "sector_watch": [
                {
                    **_VALID_STAGE3["sector_watch"][0],
                    "evidence_ids": "101",
                }
            ],
        }
        with self.assertRaises(SchemaValidationError):
            validate_against_schema(bad, STAGE3_TW_MAPPING_SCHEMA)


class EvidenceTraceabilityTests(unittest.TestCase):
    def test_all_evidence_ids_known(self) -> None:
        missing = assert_evidence_ids_covered(_VALID_STAGE3, _VALID_STAGE1)
        self.assertEqual(missing, [])

    def test_detects_unknown_evidence_id(self) -> None:
        stage3_with_phantom = {
            **_VALID_STAGE3,
            "stock_watch": [
                {
                    "ticker": "2330",
                    "direction": "bullish",
                    "rationale": "test",
                    "evidence_ids": [999],
                }
            ],
        }
        missing = assert_evidence_ids_covered(stage3_with_phantom, _VALID_STAGE1)
        self.assertEqual(missing, ["stock_watch:999"])


class StageRunnerFallbackTests(unittest.TestCase):
    def _context(self) -> StageContext:
        return StageContext(
            provider="openai",
            api_base="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-test",
            slot="pre_tw_open",
            now_local=datetime(2026, 4, 22, 7, 30, tzinfo=timezone.utc),
        )

    def test_stage1_returns_error_result_on_llm_failure(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage1_digest.call_llm_json",
            side_effect=RuntimeError("boom"),
        ):
            result = stage1_digest.run(
                context=self._context(),
                events_payload=[],
                market_payload=[],
            )
        self.assertFalse(result.ok())
        self.assertIn("boom", result.error or "")

    def test_stage1_happy_path_records_event_count(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage1_digest.call_llm_json",
            return_value=(_VALID_STAGE1, "{\"events\": []}"),
        ):
            result = stage1_digest.run(
                context=self._context(),
                events_payload=[{"id": 101}],
                market_payload=[],
            )
        self.assertTrue(result.ok())
        self.assertEqual(result.extras["event_count"], 1)

    def test_stage2_uses_stage1_json_in_prompt(self) -> None:
        captured = {}

        def fake_call(**kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return _VALID_STAGE2, "raw"

        with patch("event_relay.analysis_stages.stage2_transmission.call_llm_json", side_effect=fake_call):
            result = stage2_transmission.run(context=self._context(), stage1_output=_VALID_STAGE1)

        self.assertTrue(result.ok())
        self.assertIn("Fed cut policy rate", captured["user_prompt"])

    def test_stage3_happy_path_counts_buckets(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage3_tw_mapping.call_llm_json",
            return_value=(_VALID_STAGE3, "raw"),
        ):
            result = stage3_tw_mapping.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage2_output=_VALID_STAGE2,
            )
        self.assertTrue(result.ok())
        self.assertEqual(result.extras["sectors_count"], 1)
        self.assertEqual(result.extras["stocks_count"], 0)

    def test_stage4_returns_structured_when_schema_valid(self) -> None:
        structured = {
            "summary_text": "最終中文報告",
            "headline": "Fed dovish supports TW semis",
            "sentiment": "bullish",
            "confidence": "medium",
            "key_drivers": ["FOMC 25bp cut"],
            "tw_sector_watch": [
                {"sector": "半導體", "direction": "bullish", "rationale": "利率下行"}
            ],
            "stock_watch": [],
            "risks": ["通膨反彈"],
            "data_gaps": [],
        }
        with patch(
            "event_relay.analysis_stages.stage4_synthesis.call_llm_json",
            return_value=(structured, "raw"),
        ):
            result = stage4_synthesis.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage2_output=_VALID_STAGE2,
                stage3_output=_VALID_STAGE3,
                macro_skill="",
                line_skill="",
            )
        self.assertTrue(result.ok())
        summary = result.output["summary_text"]
        self.assertTrue(summary.startswith("最終中文報告"))
        self.assertIn("信心等級：medium", summary)
        self.assertIn("主要反方觀點：", summary)
        self.assertEqual(result.output["structured"]["sentiment"], "bullish")
        self.assertTrue(result.extras["has_structured"])

    def test_stage4_falls_back_to_text_when_schema_fails(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage4_synthesis.call_llm_json",
            side_effect=SchemaValidationError("bad payload"),
        ), patch(
            "event_relay.analysis_stages.stage4_synthesis._call_llm",
            return_value="  純文字降級報告  ",
        ):
            result = stage4_synthesis.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage2_output=_VALID_STAGE2,
                stage3_output=_VALID_STAGE3,
                macro_skill="",
                line_skill="",
            )
        self.assertTrue(result.ok())
        summary = result.output["summary_text"]
        self.assertTrue(summary.startswith("純文字降級報告"))
        self.assertIn("信心等級：", summary)
        self.assertIn("主要反方觀點：", summary)
        self.assertIsNone(result.output["structured"])
        self.assertFalse(result.extras["has_structured"])
        self.assertIn("schema_failed", result.extras["structured_fallback"])

    def test_dual_view_produces_distinct_bull_and_bear(self) -> None:
        dual_view_payload = {
            "bull_case": {
                "thesis": "Fed 降息點燃台股半導體 risk-on",
                "drivers": ["FOMC 25bp cut", "10y yield 下行"],
                "counter_risks": ["通膨黏性"],
                "evidence_ids": [101],
            },
            "bear_case": {
                "thesis": "通膨再加速使降息預期回吐",
                "drivers": ["核心 CPI 黏性", "原油反彈"],
                "counter_risks": ["勞動市場降溫"],
                "evidence_ids": [101],
            },
        }
        validate_against_schema(dual_view_payload, STAGE_DUAL_VIEW_SCHEMA)
        with patch(
            "event_relay.analysis_stages.stage_dual_view.call_llm_json",
            return_value=(dual_view_payload, "raw"),
        ):
            result = stage_dual_view.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage2_output=_VALID_STAGE2,
                stage3_output=_VALID_STAGE3,
            )
        self.assertTrue(result.ok())
        self.assertNotEqual(
            result.output["bull_case"]["thesis"],
            result.output["bear_case"]["thesis"],
        )
        self.assertEqual(result.extras["bull_drivers"], 2)
        self.assertEqual(result.extras["bear_drivers"], 2)

    def test_dual_view_returns_error_result_on_llm_failure(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage_dual_view.call_llm_json",
            side_effect=RuntimeError("network down"),
        ):
            result = stage_dual_view.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage2_output=_VALID_STAGE2,
                stage3_output=_VALID_STAGE3,
            )
        self.assertFalse(result.ok())
        self.assertIn("network down", result.error or "")
        self.assertIsNone(result.output)

    def test_critic_recommends_low_confidence_for_thin_evidence(self) -> None:
        thin_stage1 = {"events": [], "market_snapshot": {}}
        thin_dual_view = {
            "bull_case": {
                "thesis": "缺證據之牽強多方",
                "drivers": [],
                "counter_risks": [],
                "evidence_ids": [],
            },
            "bear_case": {
                "thesis": "資料不足難以下結論",
                "drivers": [],
                "counter_risks": [],
                "evidence_ids": [],
            },
        }
        critic_payload = {
            "issues": [
                {
                    "type": "evidence_missing",
                    "description": "bull_case 沒有任何 evidence_ids 支持",
                    "severity": "high",
                },
                {
                    "type": "overconfidence",
                    "description": "在無事件下仍提出方向性論述",
                    "severity": "high",
                },
            ],
            "suggestions": ["於 stage4 顯式聲明 data gap"],
            "top_counterpoint": "目前事件量不足以形成任何方向性判斷",
            "confidence_recommendation": "low",
        }
        validate_against_schema(critic_payload, STAGE_CRITIC_SCHEMA)
        captured: dict[str, Any] = {}

        def fake_call(**kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return critic_payload, "raw"

        with patch(
            "event_relay.analysis_stages.stage_critic.call_llm_json",
            side_effect=fake_call,
        ):
            result = stage_critic.run(
                context=self._context(),
                stage1_output=thin_stage1,
                stage3_output=_VALID_STAGE3,
                dual_view_output=thin_dual_view,
            )
        self.assertTrue(result.ok())
        self.assertEqual(result.output["confidence_recommendation"], "low")
        self.assertEqual(result.extras["issues_count"], 2)
        self.assertEqual(result.extras["confidence_recommendation"], "low")
        self.assertIn("缺證據之牽強多方", captured["user_prompt"])

    def test_critic_failure_returns_error_result_for_pipeline_to_skip(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage_critic.call_llm_json",
            side_effect=RuntimeError("critic model timeout"),
        ):
            result = stage_critic.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage3_output=_VALID_STAGE3,
                dual_view_output={
                    "bull_case": {"thesis": "x", "drivers": [], "counter_risks": [], "evidence_ids": []},
                    "bear_case": {"thesis": "y", "drivers": [], "counter_risks": [], "evidence_ids": []},
                },
            )
        self.assertFalse(result.ok())
        self.assertIn("critic model timeout", result.error or "")
        self.assertIsNone(result.output)

    def test_stage4_errors_when_both_paths_fail(self) -> None:
        with patch(
            "event_relay.analysis_stages.stage4_synthesis.call_llm_json",
            side_effect=SchemaValidationError("bad payload"),
        ), patch(
            "event_relay.analysis_stages.stage4_synthesis._call_llm",
            side_effect=RuntimeError("network"),
        ):
            result = stage4_synthesis.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                stage2_output=_VALID_STAGE2,
                stage3_output=_VALID_STAGE3,
                macro_skill="",
                line_skill="",
            )
        self.assertFalse(result.ok())
        self.assertIn("network", result.error or "")
        self.assertIn("schema_failed", result.extras["structured_error"])


if __name__ == "__main__":
    unittest.main()
