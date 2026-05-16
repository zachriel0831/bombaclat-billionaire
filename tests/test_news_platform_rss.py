"""news_platform.sources.rss_feed 解析測試（不打外網）。"""

import unittest
from datetime import datetime, timedelta, timezone

from news_platform.sources.rss_feed import RssFeedSource


RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>自由時報社會</title>
    <item>
      <title>某社會事件</title>
      <link>https://news.ltn.com.tw/news/society/breaking/123?utm_source=fb&amp;fbclid=xyz</link>
      <pubDate>Thu, 08 May 2026 04:00:00 +0000</pubDate>
      <description><![CDATA[<p>事件&amp;摘要&nbsp;&nbsp;第二段</p>]]></description>
      <category>社會</category>
    </item>
    <item>
      <title>另一條新聞</title>
      <link>https://news.ltn.com.tw/news/society/breaking/456</link>
      <pubDate>Thu, 08 May 2026 03:00:00 +0000</pubDate>
      <description>另一條摘要</description>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ETtoday 社會</title>
  <entry>
    <title>Atom 條目</title>
    <link href="https://www.ettoday.net/news/20260508/abc.htm" />
    <updated>2026-05-08T05:00:00Z</updated>
    <summary>內容摘要</summary>
  </entry>
</feed>
"""


def _make_source(**overrides) -> RssFeedSource:
    base = dict(
        source_id="ltn",
        country="TW",
        category="society",
        url="https://example.com/rss",
        max_age_days=0,
    )
    base.update(overrides)
    return RssFeedSource(**base)


class RssFeedParseTests(unittest.TestCase):
    def setUp(self):
        self.source = _make_source()

    def test_parses_rss_items(self):
        articles = self.source.parse(RSS_SAMPLE)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].title, "某社會事件")
        self.assertEqual(articles[0].source_id, "ltn")
        self.assertEqual(articles[0].country, "TW")
        self.assertEqual(articles[0].category, "society")
        self.assertIsNotNone(articles[0].published_at)
        self.assertEqual(articles[0].tags, ["社會"])

    def test_canonicalises_url_during_parse(self):
        articles = self.source.parse(RSS_SAMPLE)
        # utm_source 與 fbclid 應被剝除
        self.assertEqual(
            articles[0].url,
            "https://news.ltn.com.tw/news/society/breaking/123",
        )
        # 原始 URL 仍保留在 raw 給之後追溯
        self.assertEqual(
            articles[0].raw["original_url"],
            "https://news.ltn.com.tw/news/society/breaking/123?utm_source=fb&fbclid=xyz",
        )

    def test_cleans_html_summary(self):
        articles = self.source.parse(RSS_SAMPLE)
        self.assertEqual(articles[0].summary, "事件&摘要 第二段")

    def test_parses_atom_entries(self):
        atom_source = _make_source(source_id="ettoday")
        articles = atom_source.parse(ATOM_SAMPLE)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Atom 條目")
        self.assertEqual(articles[0].url, "https://www.ettoday.net/news/20260508/abc.htm")

    def test_extracts_dc_creator_author(self):
        feed = """<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
          <item>
            <title>作者測試</title>
            <link>https://e.com/a</link>
            <pubDate>Thu, 08 May 2026 04:00:00 +0000</pubDate>
            <dc:creator>記者張文川／台北報導</dc:creator>
          </item>
        </channel></rss>"""
        articles = self.source.parse(feed)
        self.assertEqual(articles[0].authors, ["張文川"])
        self.assertEqual(articles[0].raw["author_values"], ["記者張文川／台北報導"])

    def test_extracts_atom_author_name(self):
        feed = """<feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Atom 作者</title>
            <link href="https://e.com/atom-author" />
            <updated>2026-05-08T05:00:00Z</updated>
            <author><name>Jane Doe</name></author>
          </entry>
        </feed>"""
        articles = self.source.parse(feed)
        self.assertEqual(articles[0].authors, ["Jane Doe"])

    def test_extracts_reporter_from_summary_when_author_tag_missing(self):
        feed = """<rss><channel>
          <item>
            <title>摘要作者</title>
            <link>https://e.com/byline</link>
            <description><![CDATA[〔記者王小明／台北報導〕新聞內容。]]></description>
          </item>
        </channel></rss>"""
        articles = self.source.parse(feed)
        self.assertEqual(articles[0].authors, ["王小明"])

    def test_skips_items_without_title_or_link(self):
        bad = """<rss><channel>
          <item><link>https://e.com/a</link></item>
          <item><title>no link</title></item>
          <item><title>ok</title><link>https://e.com/b</link></item>
        </channel></rss>"""
        articles = self.source.parse(bad)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "ok")

    def test_returns_empty_on_malformed_xml(self):
        self.assertEqual(self.source.parse("<not valid"), [])

    def test_accepts_bytes_input(self):
        articles = self.source.parse(RSS_SAMPLE.encode("utf-8"))
        self.assertEqual(len(articles), 2)

    def test_article_id_is_stable_across_calls(self):
        a = self.source.parse(RSS_SAMPLE)
        b = self.source.parse(RSS_SAMPLE)
        self.assertEqual([x.article_id for x in a], [x.article_id for x in b])

    def test_drops_old_items_when_filter_enabled(self):
        old_pub = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )
        recent_pub = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        feed = f"""<rss><channel>
          <item><title>old</title><link>https://e.com/old</link><pubDate>{old_pub}</pubDate></item>
          <item><title>fresh</title><link>https://e.com/fresh</link><pubDate>{recent_pub}</pubDate></item>
        </channel></rss>"""
        source = _make_source(max_age_days=3)
        titles = [a.title for a in source.parse(feed)]
        self.assertEqual(titles, ["fresh"])


if __name__ == "__main__":
    unittest.main()
