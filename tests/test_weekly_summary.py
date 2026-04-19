from datetime import datetime, timezone
import unittest

from line_event_relay.weekly_summary import WeeklySummaryConfig, _extract_text_from_response, _should_run_now


class WeeklySummaryTests(unittest.TestCase):
    def test_extract_text_from_response_output_text(self) -> None:
        text = _extract_text_from_response({"output_text": "hello"})
        self.assertEqual(text, "hello")

    def test_extract_text_from_response_output_content(self) -> None:
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

    def test_should_run_now_in_window(self) -> None:
        now_local = datetime(2026, 3, 8, 10, 5, 0, tzinfo=timezone.utc)
        config = WeeklySummaryConfig(
            env_file=".env",
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            api_key="k",
            api_key_file=".secrets/openai_api_key.dpapi",
            skill_macro_path="a",
            skill_line_format_path="b",
            lookback_days=7,
            max_events=100,
            weekday=6,
            hour=10,
            minute=0,
            window_minutes=20,
            state_file="runtime/state/test.txt",
            dry_run=True,
            force=False,
        )
        self.assertTrue(_should_run_now(config, now_local))


if __name__ == "__main__":
    unittest.main()
