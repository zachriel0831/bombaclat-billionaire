from datetime import datetime, timezone
from typing import Any
import unittest
from unittest.mock import patch

from event_relay.analysis_stages.context import StageContext
from event_relay.prompt_assets import TokenUsage

# Sentinel usage row used by every call_llm_json mock so the new 3-tuple
# return shape (REQ-016) is satisfied without each test caring about the
# exact numbers.
_FAKE_USAGE = TokenUsage(provider="openai", model="gpt-test", prompt_tokens=100, completion_tokens=50)
from event_relay.analysis_stages.schemas import (
    STAGE1_DIGEST_SCHEMA,
    STAGE2_TRANSMISSION_SCHEMA,
    STAGE3_TW_MAPPING_SCHEMA,
    STAGE4_SYNTHESIS_SCHEMA,
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
    """封裝 Schema Validation Tests 相關資料與行為。"""
    def test_stage1_accepts_valid_payload(self) -> None:
        """測試 test stage1 accepts valid payload 的預期行為。"""
        validate_against_schema(_VALID_STAGE1, STAGE1_DIGEST_SCHEMA)

    def test_stage1_rejects_bad_importance(self) -> None:
        """測試 test stage1 rejects bad importance 的預期行為。"""
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
        """測試 test stage1 rejects unknown category 的預期行為。"""
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
        """測試 test stage1 rejects additional top level key 的預期行為。"""
        bad = dict(_VALID_STAGE1, extra_key="nope")
        with self.assertRaises(SchemaValidationError):
            validate_against_schema(bad, STAGE1_DIGEST_SCHEMA)

    def test_stage2_requires_assumptions(self) -> None:
        """測試 test stage2 requires assumptions 的預期行為。"""
        chain = dict(_VALID_STAGE2["chains"][0])
        chain.pop("assumptions")
        with self.assertRaises(SchemaValidationError):
            validate_against_schema({"chains": [chain]}, STAGE2_TRANSMISSION_SCHEMA)

    def test_stage3_accepts_valid_payload(self) -> None:
        """測試 test stage3 accepts valid payload 的預期行為。"""
        validate_against_schema(_VALID_STAGE3, STAGE3_TW_MAPPING_SCHEMA)

    def test_stage3_requires_evidence_ids_array(self) -> None:
        """測試 test stage3 requires evidence ids array 的預期行為。"""
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

    def test_stage4_schema_requires_every_closed_object_property(self) -> None:
        """OpenAI structured output rejects closed objects with optional properties."""

        def walk(schema: dict[str, Any], path: str = "$") -> None:
            schema_type = schema.get("type")
            is_object = schema_type == "object" or (
                isinstance(schema_type, list) and "object" in schema_type
            )
            properties = schema.get("properties")
            if is_object and isinstance(properties, dict) and schema.get("additionalProperties") is False:
                self.assertEqual(
                    set(properties),
                    set(schema.get("required") or []),
                    f"{path} required keys must match properties",
                )
            for key, child in (properties or {}).items():
                if isinstance(child, dict):
                    walk(child, f"{path}.{key}")
            items = schema.get("items")
            if isinstance(items, dict):
                walk(items, f"{path}[]")

        walk(STAGE4_SYNTHESIS_SCHEMA)

    def test_stage4_accepts_nullable_stock_execution_fields(self) -> None:
        """Stage4 stock_watch keeps all keys while allowing unknown prices as null."""
        payload = {
            "summary_text": "test",
            "headline": "test",
            "sentiment": "bullish",
            "confidence": "medium",
            "key_drivers": ["AI demand"],
            "tw_sector_watch": [],
            "stock_watch": [
                {
                    "ticker": "2330",
                    "market": "TW",
                    "name": None,
                    "direction": "bullish",
                    "rationale": "SOX supports Taiwan semis.",
                    "strategy_type": "swing",
                    "entry_zone": {
                        "low": 600,
                        "high": 610,
                        "timing": None,
                        "basis": "latest close",
                    },
                    "invalidation": None,
                    "take_profit_zone": None,
                    "holding_horizon": "short_to_medium",
                    "confidence": "medium",
                    "risk_notes": [],
                    "evidence_ids": [101],
                }
            ],
            "risks": [],
            "data_gaps": [],
        }

        validate_against_schema(payload, STAGE4_SYNTHESIS_SCHEMA)


class EvidenceTraceabilityTests(unittest.TestCase):
    """封裝 Evidence Traceability Tests 相關資料與行為。"""
    def test_all_evidence_ids_known(self) -> None:
        """測試 test all evidence ids known 的預期行為。"""
        missing = assert_evidence_ids_covered(_VALID_STAGE3, _VALID_STAGE1)
        self.assertEqual(missing, [])

    def test_detects_unknown_evidence_id(self) -> None:
        """測試 test detects unknown evidence id 的預期行為。"""
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
    """封裝 Stage Runner Fallback Tests 相關資料與行為。"""
    def _context(self) -> StageContext:
        """執行 context 方法的主要邏輯。"""
        return StageContext(
            provider="openai",
            api_base="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-test",
            slot="pre_tw_open",
            now_local=datetime(2026, 4, 22, 7, 30, tzinfo=timezone.utc),
        )

    def test_stage1_returns_error_result_on_llm_failure(self) -> None:
        """測試 test stage1 returns error result on llm failure 的預期行為。"""
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
        """測試 test stage1 happy path records event count 的預期行為。"""
        with patch(
            "event_relay.analysis_stages.stage1_digest.call_llm_json",
            return_value=(_VALID_STAGE1, "{\"events\": []}", _FAKE_USAGE),
        ):
            result = stage1_digest.run(
                context=self._context(),
                events_payload=[{"id": 101}],
                market_payload=[],
            )
        self.assertTrue(result.ok())
        self.assertEqual(result.extras["event_count"], 1)

    def test_stage2_uses_stage1_json_in_prompt(self) -> None:
        """測試 test stage2 uses stage1 json in prompt 的預期行為。"""
        captured = {}

        def fake_call(**kwargs):
            """執行 fake call 方法的主要邏輯。"""
            captured["user_prompt"] = kwargs["user_prompt"]
            return _VALID_STAGE2, "raw", _FAKE_USAGE

        with patch("event_relay.analysis_stages.stage2_transmission.call_llm_json", side_effect=fake_call):
            result = stage2_transmission.run(context=self._context(), stage1_output=_VALID_STAGE1)

        self.assertTrue(result.ok())
        self.assertIn("Fed cut policy rate", captured["user_prompt"])

    def test_stage2_includes_retrieved_examples_in_prompt(self) -> None:
        """測試 test stage2 includes retrieved examples in prompt 的預期行為。"""
        captured = {}

        def fake_call(**kwargs):
            """執行 fake call 方法的主要邏輯。"""
            captured["user_prompt"] = kwargs["user_prompt"]
            return _VALID_STAGE2, "raw", _FAKE_USAGE

        examples = [
            {
                "event_id": 55,
                "source": "reuters",
                "title": "Previous Fed cut supported semiconductors",
                "similarity": 0.77,
            }
        ]
        with patch("event_relay.analysis_stages.stage2_transmission.call_llm_json", side_effect=fake_call):
            result = stage2_transmission.run(
                context=self._context(),
                stage1_output=_VALID_STAGE1,
                retrieved_examples=examples,
            )

        self.assertTrue(result.ok())
        self.assertIn("Historical retrieved examples JSON", captured["user_prompt"])
        self.assertIn("Previous Fed cut supported semiconductors", captured["user_prompt"])
        self.assertEqual(result.extras["retrieved_examples_count"], 1)

    def test_stage3_happy_path_counts_buckets(self) -> None:
        """測試 test stage3 happy path counts buckets 的預期行為。"""
        with patch(
            "event_relay.analysis_stages.stage3_tw_mapping.call_llm_json",
            return_value=(_VALID_STAGE3, "raw", _FAKE_USAGE),
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
        """測試 test stage4 returns structured when schema valid 的預期行為。"""
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
            return_value=(structured, "raw", _FAKE_USAGE),
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

    def test_stage4_pre_open_prompt_uses_readable_sections(self) -> None:
        _system, user_prompt = stage4_synthesis.build_prompts(
            slot="pre_tw_open",
            now_local_iso="2026-04-30T08:00:00+08:00",
            stage1_json="{}",
            stage2_json="{}",
            stage3_json="{}",
            macro_skill="",
            line_skill="",
            structured=True,
        )

        self.assertIn("總經 Regime", user_prompt)
        self.assertIn("利率與流動性", user_prompt)
        self.assertIn("景氣循環", user_prompt)
        self.assertIn("市場情緒", user_prompt)
        self.assertIn("台股配置", user_prompt)
        self.assertIn("Section 2 利率與流動性", user_prompt)
        self.assertIn("date-only", user_prompt)
        self.assertNotIn("對台股的可能影響", user_prompt)

    def test_stage4_falls_back_to_text_when_schema_fails(self) -> None:
        """測試 test stage4 falls back to text when schema fails 的預期行為。"""
        with patch(
            "event_relay.analysis_stages.stage4_synthesis.call_llm_json",
            side_effect=SchemaValidationError("bad payload"),
        ), patch(
            "event_relay.analysis_stages.stage4_synthesis._call_llm",
            return_value=("  純文字降級報告  ", _FAKE_USAGE),
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
        """測試 test dual view produces distinct bull and bear 的預期行為。"""
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
            return_value=(dual_view_payload, "raw", _FAKE_USAGE),
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
        """測試 test dual view returns error result on llm failure 的預期行為。"""
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
        """測試 test critic recommends low confidence for thin evidence 的預期行為。"""
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
            """執行 fake call 方法的主要邏輯。"""
            captured["user_prompt"] = kwargs["user_prompt"]
            return critic_payload, "raw", _FAKE_USAGE

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
        """測試 test critic failure returns error result for pipeline to skip 的預期行為。"""
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
        """測試 test stage4 errors when both paths fail 的預期行為。"""
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
