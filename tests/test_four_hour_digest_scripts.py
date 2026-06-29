"""Unit tests for four-hour digest helper scripts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from collect_four_hour_digest_context import clean_text, filter_usable_items, looks_mojibake, safe_table_name  # noqa: E402
from store_four_hour_digest_to_redis import (  # noqa: E402
    load_payload,
    redis_config,
    repair_mojibake_text,
    safe_key_fragment,
    store_digest,
    validate_digest,
)


class FourHourDigestScriptTest(unittest.TestCase):
    def test_safe_table_name_quotes_allowed_identifiers(self) -> None:
        self.assertEqual(safe_table_name("t_relay_events"), "`t_relay_events`")
        self.assertEqual(safe_table_name("news_platform.t_news_articles"), "`news_platform`.`t_news_articles`")

    def test_safe_table_name_rejects_unsafe_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            safe_table_name("t_relay_events;DROP")

    def test_clean_text_compacts_whitespace_and_truncates(self) -> None:
        self.assertEqual(clean_text("  a\n b\tc  ", 20), "a b c")
        self.assertEqual(clean_text("abcdef", 4), "abc…")

    def test_filter_usable_items_drops_private_use_mojibake(self) -> None:
        notes: list[str] = []
        items = [
            {"title": "正常標題", "summary": "正常摘要", "source": "source"},
            {"title": "壞掉\ue123標題", "summary": "摘要", "source": "source"},
        ]
        self.assertTrue(looks_mojibake("壞掉\ue123標題"))
        self.assertEqual(len(filter_usable_items(items, notes, "finance")), 1)
        self.assertEqual(notes, ["finance: skipped 1 likely mojibake rows"])

    def test_safe_key_fragment_keeps_redis_friendly_id(self) -> None:
        self.assertEqual(safe_key_fragment("four-hour:2026-06-28T12:00:00+08:00"), "four-hour:2026-06-28T12:00:00+08:00")
        self.assertEqual(safe_key_fragment("bad id / value"), "bad-id-value")

    def test_validate_digest_requires_minimal_contract(self) -> None:
        payload = json.dumps(
            {
                "windowStart": "2026-06-28T08:00:00+08:00",
                "windowEnd": "2026-06-28T12:00:00+08:00",
                "generatedAt": "2026-06-28T12:01:00+08:00",
                "sections": [],
            }
        )
        self.assertEqual(validate_digest(payload)["windowEnd"], "2026-06-28T12:00:00+08:00")

    def test_validate_digest_rejects_question_mark_mojibake(self) -> None:
        payload = json.dumps(
            {
                "windowStart": "2026-06-28T08:00:00+08:00",
                "windowEnd": "2026-06-28T12:00:00+08:00",
                "generatedAt": "2026-06-28T12:01:00+08:00",
                "headline": "???? market digest",
                "sections": [],
            }
        )
        with self.assertRaises(ValueError):
            validate_digest(payload)

    def test_validate_digest_rejects_internal_encoding_failure_copy(self) -> None:
        payload = json.dumps(
            {
                "windowStart": "2026-06-28T08:00:00+08:00",
                "windowEnd": "2026-06-28T12:00:00+08:00",
                "generatedAt": "2026-06-28T12:01:00+08:00",
                "headline": "\u672c\u5730\u4e2d\u6587\u5167\u5bb9\u9700\u5148\u4fee\u6b63\u7de8\u78bc",
                "sections": [],
            },
            ensure_ascii=False,
        )
        with self.assertRaises(ValueError):
            validate_digest(payload)

    def test_repair_mojibake_text_fixes_latin1_decoded_utf8(self) -> None:
        bad = "近四小時".encode("utf-8").decode("latin-1")
        self.assertEqual(repair_mojibake_text(bad), "近四小時")

    def test_load_payload_accepts_utf8_bom_files(self) -> None:
        path = ROOT / "runtime" / "four-hour-digest" / "bom-test.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "windowStart": "2026-06-28T08:00:00+08:00",
                    "windowEnd": "2026-06-28T12:00:00+08:00",
                    "generatedAt": "2026-06-28T12:01:00+08:00",
                    "sections": [],
                }
            ),
            encoding="utf-8-sig",
        )
        self.assertEqual(validate_digest(load_payload(str(path)))["windowEnd"], "2026-06-28T12:00:00+08:00")

    def test_redis_config_defaults_to_localhost(self) -> None:
        config = redis_config("")
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 6379)
        self.assertEqual(config.db, 0)

    def test_store_digest_keeps_latest_without_ttl(self) -> None:
        class FakeRedis:
            def __init__(self) -> None:
                self.commands: list[tuple[str, ...]] = []

            def execute(self, *args: str):
                self.commands.append(args)
                if args[0] == "GET":
                    return b"old-version"
                return "OK"

        client = FakeRedis()
        store_digest(client, "latest", "current", "version", '{"ok":true}', 15000)

        self.assertIn(("SET", "version", '{"ok":true}', "EX", "15000"), client.commands)
        self.assertIn(("SET", "latest", '{"ok":true}'), client.commands)
        self.assertIn(("SET", "current", "version"), client.commands)
        self.assertNotIn(("SET", "latest", '{"ok":true}', "EX", "15000"), client.commands)
        self.assertIn(("DEL", "old-version"), client.commands)


if __name__ == "__main__":
    unittest.main()
