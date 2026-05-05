"""REQ-016 — prompt-cache + token-usage tests."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from event_relay.prompt_assets import (
    PROMPT_ASSETS_VERSION,
    TokenUsage,
    build_anthropic_system_blocks,
    compose_static_preamble,
    extract_usage_anthropic,
    extract_usage_openai,
    is_cacheable,
    merge_usage,
)


class CacheableSystemBlocksTests(unittest.TestCase):
    def test_large_block_carries_cache_control(self) -> None:
        big = "x" * 5000
        blocks = build_anthropic_system_blocks(big)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "text")
        self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral"})

    def test_small_block_omits_cache_control(self) -> None:
        small = "short text"
        blocks = build_anthropic_system_blocks(small)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("cache_control", blocks[0])

    def test_dynamic_suffix_appended_as_separate_block(self) -> None:
        big = "x" * 5000
        blocks = build_anthropic_system_blocks(big, dynamic_suffix="dynamic part")
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(blocks[1]["text"], "dynamic part")
        self.assertNotIn("cache_control", blocks[1])

    def test_compose_static_preamble_includes_skills_when_present(self) -> None:
        out = compose_static_preamble(macro_skill="MACRO", line_skill="LINE")
        self.assertIn("MACRO", out)
        self.assertIn("LINE", out)
        # Evidence policy header is the first section.
        self.assertTrue(out.startswith("You are part of"))

    def test_is_cacheable_threshold(self) -> None:
        self.assertFalse(is_cacheable("x" * 100))
        self.assertTrue(is_cacheable("x" * 5000))


class AnthropicPayloadCacheControlTests(unittest.TestCase):
    """REQ-016 acceptance: cache_control field appears in Anthropic request."""

    def _capture_anthropic_payload(self, system_text: str) -> dict:
        """Run ``_call_anthropic_message`` with a stubbed urlopen and capture payload."""
        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self) -> bytes:
                return json.dumps({
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1200, "output_tokens": 80,
                              "cache_creation_input_tokens": 1200,
                              "cache_read_input_tokens": 0},
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return FakeResp()

        from event_relay.weekly_summary import _call_anthropic_message
        with mock.patch("event_relay.weekly_summary.urlopen", side_effect=fake_urlopen):
            text, usage = _call_anthropic_message(
                "https://api.anthropic.com", "key", "claude-test", system_text, "user"
            )
        return captured["payload"], text, usage

    def test_large_string_system_is_wrapped_with_cache_control(self) -> None:
        payload, text, usage = self._capture_anthropic_payload("x" * 6000)
        self.assertEqual(text, "ok")
        self.assertIsInstance(payload["system"], list)
        self.assertEqual(payload["system"][0]["cache_control"], {"type": "ephemeral"})
        # Usage is parsed from the response.
        self.assertEqual(usage.prompt_tokens, 1200)
        self.assertEqual(usage.cache_creation_tokens, 1200)

    def test_small_system_stays_as_string(self) -> None:
        payload, _text, _usage = self._capture_anthropic_payload("hi")
        self.assertEqual(payload["system"], "hi")

    def test_explicit_blocks_pass_through_unchanged(self) -> None:
        explicit = build_anthropic_system_blocks("x" * 5000)

        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self) -> bytes:
                return json.dumps({
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 100, "output_tokens": 10},
                }).encode("utf-8")

        def fake_urlopen(req, timeout):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return FakeResp()

        from event_relay.weekly_summary import _call_anthropic_message
        with mock.patch("event_relay.weekly_summary.urlopen", side_effect=fake_urlopen):
            _call_anthropic_message(
                "https://api.anthropic.com", "key", "claude-test", explicit, "user"
            )
        self.assertEqual(captured["payload"]["system"], explicit)


class UsageExtractionTests(unittest.TestCase):
    def test_anthropic_extraction(self) -> None:
        body = {
            "usage": {
                "input_tokens": 1500,
                "output_tokens": 200,
                "cache_creation_input_tokens": 1200,
                "cache_read_input_tokens": 800,
            }
        }
        usage = extract_usage_anthropic(body, "claude-x")
        self.assertEqual(usage.provider, "anthropic")
        self.assertEqual(usage.prompt_tokens, 1500)
        self.assertEqual(usage.completion_tokens, 200)
        self.assertEqual(usage.cached_tokens, 800)
        self.assertEqual(usage.cache_creation_tokens, 1200)

    def test_openai_extraction_with_cached_details(self) -> None:
        body = {
            "usage": {
                "input_tokens": 2000,
                "output_tokens": 150,
                "input_tokens_details": {"cached_tokens": 1500},
            }
        }
        usage = extract_usage_openai(body, "gpt-x")
        self.assertEqual(usage.provider, "openai")
        self.assertEqual(usage.prompt_tokens, 2000)
        self.assertEqual(usage.cached_tokens, 1500)

    def test_missing_usage_block_yields_zeros(self) -> None:
        usage = extract_usage_anthropic({}, "claude-x")
        self.assertEqual(usage.prompt_tokens, 0)
        self.assertEqual(usage.cached_tokens, 0)


class MergeUsageTests(unittest.TestCase):
    def test_merge_sums_and_computes_hit_ratio(self) -> None:
        rows = [
            TokenUsage(provider="openai", model="m", prompt_tokens=1000, completion_tokens=100, cached_tokens=600),
            TokenUsage(provider="openai", model="m", prompt_tokens=500, completion_tokens=80, cached_tokens=400),
        ]
        merged = merge_usage(rows)
        self.assertEqual(merged["prompt_tokens"], 1500)
        self.assertEqual(merged["completion_tokens"], 180)
        self.assertEqual(merged["cached_tokens"], 1000)
        self.assertEqual(merged["cache_hit_ratio"], round(1000 / 1500, 3))
        self.assertEqual(merged["prompt_assets_version"], PROMPT_ASSETS_VERSION)
        self.assertEqual(len(merged["stages"]), 2)

    def test_merge_with_no_prompt_tokens_returns_zero_ratio(self) -> None:
        merged = merge_usage([])
        self.assertEqual(merged["cache_hit_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()
