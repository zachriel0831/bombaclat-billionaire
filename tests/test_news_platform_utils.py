"""news_platform.utils 工具函式測試。"""

import unittest
from datetime import datetime, timedelta, timezone

from news_platform.utils import canonical_url, clean_summary, is_recent, stable_id


class CanonicalUrlTests(unittest.TestCase):
    def test_strips_utm_and_fbclid(self):
        url = (
            "https://news.ltn.com.tw/news/society/breaking/123"
            "?utm_source=fb&utm_campaign=x&fbclid=abc&topic=crime"
        )
        self.assertEqual(
            canonical_url(url),
            "https://news.ltn.com.tw/news/society/breaking/123?topic=crime",
        )

    def test_strips_fragment(self):
        self.assertEqual(
            canonical_url("https://example.com/a#comments"),
            "https://example.com/a",
        )

    def test_lowercases_scheme_and_host(self):
        self.assertEqual(
            canonical_url("HTTPS://NEWS.LTN.COM.TW/abc"),
            "https://news.ltn.com.tw/abc",
        )

    def test_returns_empty_for_empty(self):
        self.assertEqual(canonical_url(""), "")
        self.assertEqual(canonical_url("   "), "")

    def test_passes_through_relative_paths(self):
        self.assertEqual(canonical_url("/news/abc"), "/news/abc")


class CleanSummaryTests(unittest.TestCase):
    def test_strips_html_and_unescapes(self):
        raw = "<p>事件&amp;摘要&nbsp;&nbsp;<br/>第二段</p>"
        self.assertEqual(clean_summary(raw), "事件&摘要 第二段")

    def test_collapses_whitespace(self):
        self.assertEqual(clean_summary("a   b\n\nc\t d"), "a b c d")

    def test_strips_related_reading_blocks(self):
        raw = "正文第一段 延伸閱讀： ● 不相關標題 ● 更多標題"
        self.assertEqual(clean_summary(raw), "正文第一段")

    def test_strips_related_reading_heading_without_colon(self):
        raw = "正文第二段 延伸閱讀 ● 不相關標題 ● 更多標題"
        self.assertEqual(clean_summary(raw), "正文第二段")

    def test_returns_none_for_empty_or_only_tags(self):
        self.assertIsNone(clean_summary(None))
        self.assertIsNone(clean_summary(""))
        self.assertIsNone(clean_summary("<p></p>"))

    def test_truncates_long_text(self):
        out = clean_summary("a" * 2000, max_chars=100)
        self.assertEqual(len(out), 100)


class IsRecentTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    def test_within_window(self):
        recent = self.now - timedelta(days=2)
        self.assertTrue(is_recent(recent, max_age_days=3, now=self.now))

    def test_outside_window(self):
        old = self.now - timedelta(days=10)
        self.assertFalse(is_recent(old, max_age_days=3, now=self.now))

    def test_none_published_passes(self):
        self.assertTrue(is_recent(None, max_age_days=3, now=self.now))

    def test_max_age_zero_disables_filter(self):
        old = self.now - timedelta(days=365)
        self.assertTrue(is_recent(old, max_age_days=0, now=self.now))

    def test_naive_datetime_treated_as_utc(self):
        naive = datetime(2026, 5, 7, 12, 0)
        self.assertTrue(is_recent(naive, max_age_days=3, now=self.now))


class StableIdTests(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(stable_id("a", "b", "c"), stable_id("a", "b", "c"))

    def test_changes_when_canonical_url_changes(self):
        a = stable_id("ltn", "society", "https://e.com/x", "title")
        b = stable_id("ltn", "society", "https://e.com/y", "title")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
