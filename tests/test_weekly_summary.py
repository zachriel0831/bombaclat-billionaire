from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from event_relay.prompt_assets import TokenUsage
from event_relay.weekly_summary import (
    WeeklySummaryConfig,
    _call_llm,
    _call_openai_response,
    _analysis_date_key,
    _compile_prompts,
    _extract_text_from_anthropic,
    _extract_text_from_response,
    _llm_timeout_seconds,
    _load_weekly_config,
    _normalize_line_text,
    _openai_model_supports_temperature,
    _openai_web_search_enabled,
    _resolve_llm_settings,
    _should_run_now,
    _store_weekly_analysis,
    _weekly_runtime_failover_config,
    _week_key,
    run_once,
)


class WeeklySummaryTests(unittest.TestCase):
    def _config(self, **overrides: object) -> WeeklySummaryConfig:
        data: dict[str, object] = {
            "env_file": ".env",
            "model": "gpt-5",
            "api_base": "https://api.openai.com/v1",
            "api_key": "k",
            "api_key_file": ".secrets/openai_api_key.dpapi",
            "skill_macro_path": "a",
            "skill_line_format_path": "b",
            "lookback_days": 7,
            "max_events": 100,
            "weekday": 5,
            "hour": 23,
            "minute": 0,
            "window_minutes": 20,
            "state_file": "runtime/state/test.txt",
            "force": False,
        }
        data.update(overrides)
        return WeeklySummaryConfig(**data)

    """封裝 Weekly Summary Tests 相關資料與行為。"""
    def test_normalize_line_text_translates_internal_labels(self) -> None:
        text = (
            "週總經\n"
            "本週只使用 t_relay_events、market_context、raw_json 與 structured_json，"
            "未呼叫外部 LLM API，並由 Codex guard 檢查。"
        )

        cleaned = _normalize_line_text(text)

        self.assertNotIn("t_relay_events", cleaned)
        self.assertNotIn("market_context", cleaned)
        self.assertNotIn("raw_json", cleaned)
        self.assertNotIn("structured_json", cleaned)
        self.assertNotIn("LLM API", cleaned)
        self.assertNotIn("Codex guard", cleaned)
        self.assertIn("部分即時外部資料未納入", cleaned)

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
        config = self._config(weekday=0, hour=7, minute=30)
        self.assertTrue(_should_run_now(config, now_local))

    def test_week_key_uses_iso_week(self) -> None:
        """測試 test week key uses iso week 的預期行為。"""
        now_local = datetime(2026, 4, 20, 7, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(_week_key(now_local), "2026-W17")

    def test_analysis_date_key_uses_sunday_delivery_date_for_saturday_run(self) -> None:
        """Weekly rows should store the target Sunday date, not an ISO week label."""
        taipei = timezone(timedelta(hours=8))
        now_local = datetime(2026, 4, 25, 23, 0, 0, tzinfo=taipei)
        self.assertEqual(_analysis_date_key(now_local, self._config()), "2026-04-26")

    def test_analysis_date_key_keeps_same_sunday_for_sunday_rerun(self) -> None:
        """A Sunday recovery run should still target that same Sunday row."""
        taipei = timezone(timedelta(hours=8))
        now_local = datetime(2026, 4, 26, 10, 0, 0, tzinfo=taipei)
        self.assertEqual(_analysis_date_key(now_local, self._config()), "2026-04-26")

    def test_store_weekly_analysis_uses_hhmm_scheduled_time_and_telemetry(self) -> None:
        """weekly scheduled_time_local should match daily HH:MM format."""

        class FakeStore:
            def __init__(self) -> None:
                self.record = None

            def upsert_market_analysis(self, record):
                self.record = record
                return 1

        taipei = timezone(timedelta(hours=8))
        store = FakeStore()
        _store_weekly_analysis(
            store=store,
            now_local=datetime(2026, 4, 25, 23, 0, 0, tzinfo=taipei),
            config=self._config(),
            message="summary",
            events_used=3,
            usage=TokenUsage(
                provider="openai",
                model="gpt-5",
                prompt_tokens=100,
                completion_tokens=20,
                cached_tokens=5,
            ),
        )

        self.assertIsNotNone(store.record)
        self.assertEqual(store.record.scheduled_time_local, "05:10")
        raw_json = json.loads(store.record.raw_json)
        self.assertEqual(raw_json["section_contract"], ["週總經", "下週台股配置", "下週觀察清單"])
        self.assertEqual(raw_json["token_usage"]["provider"], "openai")
        self.assertEqual(raw_json["token_usage"]["prompt_tokens"], 100)
        self.assertEqual(raw_json["token_usage"]["completion_tokens"], 20)
        self.assertEqual(raw_json["token_usage"]["cached_tokens"], 5)

    def test_compile_prompts_uses_weekly_three_section_contract(self) -> None:
        """Weekly prompt should use the weekly-specific section contract."""
        with mock.patch("event_relay.weekly_summary._load_text", return_value=""):
            _system_prompt, reusable_prompt = _compile_prompts(self._config())

        self.assertIn("週總經", reusable_prompt)
        self.assertIn("下週台股配置", reusable_prompt)
        self.assertIn("下週觀察清單", reusable_prompt)
        self.assertIn("evidence -> mechanism -> Taiwan implication", reusable_prompt)
        self.assertIn("Weekly reports should not output intraday entry", reusable_prompt)
        self.assertIn("1200-2200 Chinese characters", reusable_prompt)
        self.assertNotIn("總經 Regime", reusable_prompt)
        self.assertNotIn("Section 2 利率與流動性", reusable_prompt)

    def test_call_llm_routes_to_openai_by_default(self) -> None:
        """測試 test call llm routes to openai by default 的預期行為。"""
        from event_relay.prompt_assets import TokenUsage
        fake = TokenUsage(provider="openai", model="m")
        with mock.patch("event_relay.weekly_summary._call_openai_response", return_value=("oai", fake)) as oai, \
             mock.patch("event_relay.weekly_summary._call_anthropic_message", return_value=("ant", fake)) as ant:
            text, usage = _call_llm("openai", "base", "key", "m", "sys", "usr")
        self.assertEqual(text, "oai")
        self.assertIs(usage, fake)
        oai.assert_called_once_with("base", "key", "m", "sys", "usr")
        ant.assert_not_called()

    def test_call_llm_routes_to_anthropic(self) -> None:
        """測試 test call llm routes to anthropic 的預期行為。"""
        from event_relay.prompt_assets import TokenUsage
        fake = TokenUsage(provider="anthropic", model="m")
        with mock.patch("event_relay.weekly_summary._call_openai_response", return_value=("oai", fake)) as oai, \
             mock.patch("event_relay.weekly_summary._call_anthropic_message", return_value=("ant", fake)) as ant:
            text, usage = _call_llm("Anthropic", "base", "key", "m", "sys", "usr")
        self.assertEqual(text, "ant")
        self.assertIs(usage, fake)
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
            text, _usage = _call_openai_response("https://api.openai.com/v1", "key", "gpt-5", "sys", "usr")

        self.assertEqual(text, "ok")
        payload = captured["payload"]
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["tools"], [{"type": "web_search"}])

    def test_llm_timeout_seconds_uses_env_with_bounds(self) -> None:
        """測試 test llm timeout seconds uses env with bounds 的預期行為。"""
        with mock.patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "180"}, clear=False):
            self.assertEqual(_llm_timeout_seconds(), 180)
        with mock.patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "3"}, clear=False):
            self.assertEqual(_llm_timeout_seconds(), 15)
        with mock.patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "999"}, clear=False):
            self.assertEqual(_llm_timeout_seconds(), 600)

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

    def test_load_weekly_config_loads_env_before_provider_resolution(self) -> None:
        """Weekly config must honor LLM_PROVIDER from the env file."""
        with TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "LLM_PROVIDER=anthropic",
                        "ANTHROPIC_API_KEY=sk-ant-test",
                        "ANTHROPIC_MODEL=claude-test",
                        "ANTHROPIC_API_BASE=https://api.anthropic.com",
                        "WEEKLY_SUMMARY_HOUR=21",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                config = _load_weekly_config(SimpleNamespace(env_file=str(env_file), force=False))

        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.model, "claude-test")
        self.assertEqual(config.api_key, "sk-ant-test")
        self.assertEqual(config.hour, 21)

    def test_weekly_runtime_failover_config_switches_openai_quota_to_anthropic(self) -> None:
        """OpenAI quota/rate failures should produce a Claude failover config."""
        with mock.patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-ant-test",
                "ANTHROPIC_MODEL": "claude-backup",
                "ANTHROPIC_API_BASE": "https://api.anthropic.com",
            },
            clear=False,
        ):
            config = _weekly_runtime_failover_config(
                self._config(provider="openai", model="gpt-5"),
                RuntimeError("OpenAI HTTPError status=429 body=insufficient_quota"),
            )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.provider, "anthropic")
        self.assertEqual(config.model, "claude-backup")
        self.assertEqual(config.api_key, "sk-ant-test")
        assert config.runtime_failover is not None
        self.assertEqual(config.runtime_failover["from_provider"], "openai")
        self.assertEqual(config.runtime_failover["to_provider"], "anthropic")

    def test_run_once_runtime_failover_openai_quota_to_anthropic(self) -> None:
        """A weekly run should retry on Claude and store the fallback metadata."""

        class FakeStore:
            def __init__(self) -> None:
                self.record = None

            def initialize(self) -> None:
                return None

            def fetch_recent_summary_events(self, *, days: int, limit: int):
                self.fetch_args = {"days": days, "limit": limit}
                return [
                    SimpleNamespace(
                        row_id=1,
                        source="test",
                        title="event",
                        url="https://example.test",
                        summary="summary",
                        published_at="2026-05-16",
                        created_at="2026-05-16 23:00:00",
                    )
                ]

            def upsert_market_analysis(self, record):
                self.record = record
                return 1

        store = FakeStore()
        usage = TokenUsage(provider="anthropic", model="claude-backup", prompt_tokens=10, completion_tokens=5)
        with TemporaryDirectory() as tmp, \
             mock.patch("event_relay.weekly_summary.load_settings", return_value=SimpleNamespace(mysql_enabled=True)), \
             mock.patch("event_relay.weekly_summary.MySqlEventStore", return_value=store), \
             mock.patch("event_relay.weekly_summary._write_prompt_snapshots"), \
             mock.patch(
                 "event_relay.weekly_summary._resolve_anthropic_settings",
                 return_value=("anthropic", "claude-backup", "https://api.anthropic.com", "ant-file", "ant-key"),
             ), \
             mock.patch(
                 "event_relay.weekly_summary._call_llm",
                 side_effect=[
                     RuntimeError("OpenAI HTTPError status=429 body=insufficient_quota"),
                     ("weekly summary from claude", usage),
                 ],
             ) as call_llm:
            result = run_once(
                self._config(
                    force=True,
                    state_file=str(Path(tmp) / "weekly-state.txt"),
                    provider="openai",
                    model="gpt-5",
                )
            )

        self.assertEqual(result["provider"], "anthropic")
        self.assertEqual(result["model"], "claude-backup")
        self.assertEqual(call_llm.call_count, 2)
        self.assertIsNotNone(store.record)
        self.assertEqual(store.record.model, "claude-backup")
        raw_json = json.loads(store.record.raw_json)
        self.assertEqual(raw_json["token_usage"]["provider"], "anthropic")
        self.assertEqual(raw_json["runtime_failover"]["from_provider"], "openai")
        self.assertEqual(raw_json["runtime_failover"]["to_provider"], "anthropic")


if __name__ == "__main__":
    unittest.main()
