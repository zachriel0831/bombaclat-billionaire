from datetime import datetime, timezone
from types import SimpleNamespace
import os
import unittest

from event_relay.market_analysis import _build_prompts, _compact_event_raw_json, _load_config, _normalize_text, _resolve_slot


class MarketAnalysisTests(unittest.TestCase):
    def test_resolve_slot_in_window(self) -> None:
        config = SimpleNamespace(slot="auto", window_minutes=25)
        now_local = datetime(2026, 4, 19, 7, 18, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "pre_tw_open")

    def test_resolve_slot_manual_override(self) -> None:
        config = SimpleNamespace(slot="us_close", window_minutes=25)
        now_local = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

        slot = _resolve_slot(config, now_local)

        self.assertEqual(slot, "us_close")

    def test_normalize_text_keeps_line_breaks(self) -> None:
        text = _normalize_text("  line1   \nline2  \n")
        self.assertEqual(text, "line1\nline2")

    def test_compact_event_raw_json_only_keeps_market_context_fields(self) -> None:
        raw = (
            '{"event_type":"market_context_point","dimension":"market_context","slot":"pre_tw_open",'
            '"point":{"source":"yahoo_chart","symbol":"^NDX","value":100,"raw":{"huge":true}}}'
        )

        compact = _compact_event_raw_json("market_context:yahoo_chart", raw)
        ignored = _compact_event_raw_json("BBC News", raw)

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


if __name__ == "__main__":
    unittest.main()
