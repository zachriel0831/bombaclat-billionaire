import unittest
from unittest.mock import patch

from news_collector.sources.rss import OfficialRssSource


def _rss(items: list[tuple[str, str]]) -> str:
    """執行 rss 的主要流程。"""
    item_xml = "\n".join(
        f"""
        <item>
          <title>{title}</title>
          <link>https://example.com/{title}</link>
          <pubDate>{published}</pubDate>
          <description>{title} summary</description>
        </item>
        """
        for title, published in items
    )
    return f"""
    <rss version="2.0">
      <channel>
        <title>Example Feed</title>
        {item_xml}
      </channel>
    </rss>
    """


class OfficialRssSourceTests(unittest.TestCase):
    """封裝 Official Rss Source Tests 相關資料與行為。"""
    def test_fetch_limit_applies_per_feed_not_globally(self) -> None:
        """測試 test fetch limit applies per feed not globally 的預期行為。"""
        payloads = {
            "https://feed-a.example/rss.xml": _rss(
                [
                    ("a1", "Wed, 22 Apr 2026 10:00:00 GMT"),
                    ("a2", "Wed, 22 Apr 2026 09:00:00 GMT"),
                    ("a3", "Wed, 22 Apr 2026 08:00:00 GMT"),
                ]
            ),
            "https://feed-b.example/rss.xml": _rss(
                [
                    ("b1", "Wed, 22 Apr 2026 10:30:00 GMT"),
                    ("b2", "Wed, 22 Apr 2026 09:30:00 GMT"),
                    ("b3", "Wed, 22 Apr 2026 08:30:00 GMT"),
                ]
            ),
        }

        def fake_get(url: str, timeout: int = 15, verify_ssl: bool = True) -> str:
            """執行 fake get 方法的主要邏輯。"""
            return payloads[url]

        source = OfficialRssSource(list(payloads), timeout_seconds=3)
        with patch("news_collector.sources.rss.http_get_text", side_effect=fake_get):
            items = source.fetch(limit=2)

        self.assertEqual([item.title for item in items], ["b1", "a1", "b2", "a2"])

    def test_first_per_feed_still_limits_each_feed_to_one_item(self) -> None:
        """測試 test first per feed still limits each feed to one item 的預期行為。"""
        payloads = {
            "https://feed-a.example/rss.xml": _rss(
                [
                    ("a1", "Wed, 22 Apr 2026 10:00:00 GMT"),
                    ("a2", "Wed, 22 Apr 2026 09:00:00 GMT"),
                ]
            ),
            "https://feed-b.example/rss.xml": _rss(
                [
                    ("b1", "Wed, 22 Apr 2026 10:30:00 GMT"),
                    ("b2", "Wed, 22 Apr 2026 09:30:00 GMT"),
                ]
            ),
        }

        def fake_get(url: str, timeout: int = 15, verify_ssl: bool = True) -> str:
            """執行 fake get 方法的主要邏輯。"""
            return payloads[url]

        source = OfficialRssSource(list(payloads), timeout_seconds=3, first_per_feed=True)
        with patch("news_collector.sources.rss.http_get_text", side_effect=fake_get):
            items = source.fetch(limit=20)

        self.assertEqual([item.title for item in items], ["b1", "a1"])

    def test_fetch_retries_missing_ski_feed_without_ssl_verification(self) -> None:
        calls: list[bool] = []

        def fake_get(url: str, timeout: int = 15, verify_ssl: bool = True) -> str:
            calls.append(verify_ssl)
            if verify_ssl:
                raise OSError("Missing Subject Key Identifier")
            return _rss([("a1", "Wed, 22 Apr 2026 10:00:00 GMT")])

        source = OfficialRssSource(["https://feed-a.example/rss.xml"], timeout_seconds=3)
        with patch("news_collector.sources.rss.http_get_text", side_effect=fake_get):
            items = source.fetch(limit=2)

        self.assertEqual(calls, [True, False])
        self.assertEqual([item.title for item in items], ["a1"])

    def test_relative_links_are_resolved_against_feed_url(self) -> None:
        source = OfficialRssSource(["https://www.twse.com.tw/rwd/zh/news/feed?type=rss"])
        items = source._parse_feed(
            """
            <rss version="2.0">
              <channel>
                <title>TWSE</title>
                <item>
                  <title>t1</title>
                  <link>/rwd/zh/news/newsDetail/abc</link>
                  <pubDate>Wed, 22 Apr 2026 10:00:00 GMT</pubDate>
                </item>
              </channel>
            </rss>
            """,
            "https://www.twse.com.tw/rwd/zh/news/feed?type=rss",
        )

        self.assertEqual(items[0].url, "https://www.twse.com.tw/rwd/zh/news/newsDetail/abc")


if __name__ == "__main__":
    unittest.main()
