"""Tests for relay-event reporter enrichment helpers."""

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_relay_event_authors.py"
SPEC = importlib.util.spec_from_file_location("backfill_relay_event_authors", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
backfill = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backfill
SPEC.loader.exec_module(backfill)


class RelayEventAuthorBackfillTests(unittest.TestCase):
    def test_source_id_for_url_maps_supported_finance_hosts(self) -> None:
        self.assertEqual(backfill.source_id_for_url("https://ec.ltn.com.tw/article/breakingnews/1"), "ltn")
        self.assertEqual(backfill.source_id_for_url("https://money.udn.com/money/story/1"), "moneyudn")
        self.assertIsNone(backfill.source_id_for_url("https://www.twse.com.tw/rwd/zh/news/newsDetail/abc"))

    def test_raw_rss_author_values_are_normalized_without_detail_fetch(self) -> None:
        result = backfill.result_from_raw_metadata(
            {"raw": {"author_values": ["reporter@example.com (Jane Doe)"]}}
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, backfill.AUTHOR_STATUS_PRESENT)
        self.assertEqual(result.authors, ["Jane Doe"])

    def test_existing_author_extraction_status_skips_without_retry(self) -> None:
        payload = {"author_extraction": {"status": "no_author_metadata"}}

        self.assertTrue(backfill.should_skip_existing(payload, retry_failed=False))
        self.assertFalse(backfill.should_skip_existing(payload, retry_failed=True))

    def test_sanitize_rejects_site_slug_author(self) -> None:
        result = backfill.ArticleDetailAuthorResult(
            authors=["edn"],
            status=backfill.AUTHOR_STATUS_PRESENT,
            method="article_detail",
            confidence=0.95,
            raw_text="edn",
        )

        sanitized = backfill.sanitize_author_result(result)

        self.assertEqual(sanitized.authors, [])
        self.assertEqual(sanitized.status, backfill.AUTHOR_STATUS_LOW_CONFIDENCE)
        self.assertEqual(sanitized.confidence, 0.0)

    def test_decode_raw_json_falls_back_to_empty_dict(self) -> None:
        self.assertEqual(backfill.decode_raw_json("{bad-json"), {})
        self.assertEqual(backfill.decode_raw_json('{"authors":["A"]}'), {"authors": ["A"]})


if __name__ == "__main__":
    unittest.main()
