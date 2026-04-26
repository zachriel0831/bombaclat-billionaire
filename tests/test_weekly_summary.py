from datetime import datetime, timezone
import json
import os
import unittest
from unittest import mock

from event_relay.weekly_summary import (
    WeeklySummaryConfig,
    _call_llm,
    _call_openai_response,
    _extract_text_from_anthropic,
    _extract_text_from_response,
    _llm_timeout_seconds,
    _openai_model_supports_temperature,
    _openai_web_search_enabled,
    _resolve_llm_settings,
    _should_run_now,
    _week_key,
)


class WeeklySummaryTests(unittest.TestCase):
    """封裝 Weekly Summary Tests 相關資料與行為。"""
    def test_extract_text_from_response_output_text(self) -> None:
        """測試 test extract text from response output text 的預期行為。"""
        text = _extract_text_from_response({"output_text": "hello"})
        self.assertEqual(text, "hello")

    def test_extract_text_from_response_output_content(self) -> None:
        """測試 test extract text from response output content 的預期行為。"""
        payload = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "line 1"},
                        {"type": "output_text", "text": "line 2"},
                    ]
                }
            ]
        }
        text = _extract_text_from_response(payload)
        self.assertEqual(text, "line 1\nline 2")

    def test_extract_text_from_anthropic_single_block(self) -> None:
        """測試 test extract text from anthropic single block 的預期行為。"""
        text = _extract_text_from_anthropic({"content": [{"type": "text", "text": "hello"}]})
        self.assertEqual(text, "hello")

    def test_extract_text_from_anthropic_multi_block_skips_non_text(self) -> None:
        """測試 test extract text from anthropic multi block skips non text 的預期行為。"""
        payload = {
            "content": [
                {"type": "text", "text": "part1"},
                {"type": "tool_use", "id": "x"},
                {"type": "text", "text": "part2"},
            ]
        }
        self.assertEqual(_extract_text_from_anthropic(payload), "part1\npart2")

    def test_should_run_now_in_window(self) -> None:
        """測試 test should run now in window 的預期行為。"""
        now_local = datetime(2026, 3, 9, 7, 35, 0, tzinfo=timezone.utc)
        config = WeeklySummaryConfig(
            env_file=".env",
            model="gpt-5",
            api_base="https://api.openai.com/v1",
            api_key="k",
            api_key_file=".secrets/openai_api_key.dpapi",
            skill_macro_path="a",
            skill_line_format_path="b",
            lookback_days=7,
            max_events=100,
            weekday=0,
            hour=7,
            minute=30,
            window_minutes=20,
            state_file="runtime/state/test.txt",
            force=False,
        )
        self.assertTrue(_should_run_now(config, now_local))

    def test_week_key_uses_iso_week(self) -> None:
        """測試 test week key uses iso week 的預期行為。"""
        now_local = datetime(2026, 4, 20, 7, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(_week_key(now_local), "2026-W17")

    def test_call_llm_routes_to_openai_by_default(self) -> None:
        """測試 test call llm routes to openai by default 的預期行為。"""
        with mock.patch("event_relay.weekly_summary._call_openai_response", return_value="oai") as oai, \
             mock.patch("event_relay.weekly_summary._call_anthropic_message", return_value="ant") as ant:
            result = _call_llm("openai", "base", "key", "m", "sys", "usr")
        self.assertEqual(result, "oai")
        oai.assert_called_once_with("base", "key", "m", "sys", "usr")
        ant.assert_not_called()

    def test_call_llm_routes_to_anthropic(self) -> None:
        """測試 test call llm routes to anthropic 的預期行為。"""
        with mock.patch("event_relay.weekly_summary._call_openai_response", return_value="oai") as oai, \
             mock.patch("event_relay.weekly_summary._call_anthropic_message", return_value="ant") as ant:
            result = _call_llm("Anthropic", "base", "key", "m", "sys", "usr")
        self.assertEqual(result, "ant")
        ant.assert_called_once_with("base", "key", "m", "sys", "usr")
        oai.assert_not_called()

    def test_openai_model_supports_temperature_skips_gpt5_family(self) -> None:
        """測試 test openai model supports temperature skips gpt5 family 的預期行為。"""
        self.assertFalse(_openai_model_supports_temperature("gpt-5"))
        self.assertFalse(_openai_model_supports_temperature("gpt-5-mini"))
        self.assertTrue(_openai_model_supports_temperature("gpt-4.1-mini"))

    def test_openai_web_search_enabled_defaults_true(self) -> None:
        """測試 test openai web search enabled defaults true 的預期行為。"""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_openai_web_search_enabled())

    def test_openai_web_search_enabled_can_be_disabled(self) -> None:
        """測試 test openai web search enabled can be disabled 的預期行為。"""
        with mock.patch.dict(os.environ, {"LLM_WEB_SEARCH_ENABLED": "false"}, clear=True):
            self.assertFalse(_openai_web_search_enabled())

    def test_call_openai_response_includes_web_search_tool_when_enabled(self) -> None:
        """測試 test call openai response includes web search tool when enabled 的預期行為。"""
        captured: dict[str, object] = {}

        class FakeResponse:
            """封裝 Fake Response 相關資料與行為。"""
            def __enter__(self) -> "FakeResponse":
                """進入 context manager 並準備資源。"""
                return self

            def __exit__(self, *_args: object) -> None:
                """離開 context manager 並釋放資源。"""
                return None

            def read(self) -> bytes:
                """執行 read 方法的主要邏輯。"""
                return b'{"output_text":"ok"}'

        def fake_urlopen(req: object, timeout: int) -> FakeResponse:
            """執行 fake urlopen 方法的主要邏輯。"""
            captured["timeout"] = timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]
            return FakeResponse()

        with mock.patch.dict(os.environ, {"LLM_WEB_SEARCH_ENABLED": "true"}, clear=False), \
             mock.patch("event_relay.weekly_summary.urlopen", side_effect=fake_urlopen):
            result = _call_openai_response("https://api.openai.com/v1", "key", "gpt-5", "sys", "usr")

        self.assertEqual(result, "ok")
        payload = captured["payload"]
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["tools"], [{"type": "web_search"}])

    def test_llm_timeout_seconds_uses_env_with_bounds(self) -> None:
        """測試 test llm timeout seconds uses env with bounds 的預期行為。"""
        with mock.patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "180"}, clear=False):
            self.assertEqual(_llm_timeout_seconds(), 180)
        with mock.patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "3"}, clear=False):
            self.assertEqual(_llm_timeout_seconds(), 15)

    def test_resolve_llm_settings_anthropic_branch(self) -> None:
        """測試 test resolve llm settings anthropic branch 的預期行為。"""
        env_override = {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "ANTHROPIC_MODEL": "claude-sonnet-4-6",
            "ANTHROPIC_API_BASE": "https://api.anthropic.com",
        }
        with mock.patch.dict(os.environ, env_override, clear=False):
            provider, model, api_base, _key_file, api_key = _resolve_llm_settings("gpt-5")
        self.assertEqual(provider, "anthropic")
        self.assertEqual(model, "claude-sonnet-4-6")
        self.assertEqual(api_base, "https://api.anthropic.com")
        self.assertEqual(api_key, "sk-ant-test")

    def test_resolve_llm_settings_openai_default(self) -> None:
        """測試 test resolve llm settings openai default 的預期行為。"""
        env_override = {
            "WEEKLY_SUMMARY_OPENAI_API_KEY": "sk-oai-test",
            "WEEKLY_SUMMARY_MODEL": "gpt-5",
        }
        env_override.pop("LLM_PROVIDER", None)
        with mock.patch.dict(os.environ, env_override, clear=False):
            os.environ.pop("LLM_PROVIDER", None)
            provider, model, _api_base, _key_file, api_key = _resolve_llm_settings("gpt-5")
        self.assertEqual(provider, "openai")
        self.assertEqual(model, "gpt-5")
        self.assertEqual(api_key, "sk-oai-test")


if __name__ == "__main__":
    unittest.main()
