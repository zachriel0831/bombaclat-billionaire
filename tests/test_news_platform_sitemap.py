"""news_platform.sources.sitemap_news 解析測試（不打外網）。"""

import unittest
from datetime import datetime, timedelta, timezone

from news_platform.sources.sitemap_news import GoogleNewsSitemapSource


SITEMAP_SAMPLE = """<?xml version="1.0" encoding="UTF-8" ?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://news.tvbs.com.tw/local/3199430</loc>
    <news:news>
      <news:publication>
        <news:name>TVBS 新聞網</news:name>
        <news:language>zh-tw</news:language>
      </news:publication>
      <news:publication_date>2026-05-08T22:22:58+08:00</news:publication_date>
      <news:title><![CDATA[在地社會事件]]></news:title>
    </news:news>
  </url>
  <url>
    <loc>https://news.tvbs.com.tw/entertainment/3199433</loc>
    <news:news>
      <news:publication>
        <news:name>TVBS 新聞網</news:name>
        <news:language>zh-tw</news:language>
      </news:publication>
      <news:publication_date>2026-05-08T22:19:11+08:00</news:publication_date>
      <news:title><![CDATA[娛樂條目]]></news:title>
    </news:news>
  </url>
  <url>
    <loc>https://news.tvbs.com.tw/local/3199431?utm_source=fb</loc>
    <news:news>
      <news:publication>
        <news:name>TVBS 新聞網</news:name>
        <news:language>zh-tw</news:language>
      </news:publication>
      <news:publication_date>2026-05-08T21:00:00+08:00</news:publication_date>
      <news:title><![CDATA[另一條社會新聞]]></news:title>
    </news:news>
  </url>
</urlset>
"""


def _make(**overrides) -> GoogleNewsSitemapSource:
    base = dict(
        source_id="tvbs",
        country="TW",
        category="society",
        url="https://example.com/sitemap",
        path_filter="/local/",
        max_age_days=0,
    )
    base.update(overrides)
    return GoogleNewsSitemapSource(**base)


class GoogleNewsSitemapTests(unittest.TestCase):
    def test_filters_by_path(self):
        source = _make()
        articles = source.parse(SITEMAP_SAMPLE)
        # 娛樂條目應該被 path_filter `/local/` 過濾掉
        titles = {a.title for a in articles}
        self.assertEqual(titles, {"在地社會事件", "另一條社會新聞"})

    def test_no_filter_returns_all(self):
        source = _make(path_filter=None)
        articles = source.parse(SITEMAP_SAMPLE)
        self.assertEqual(len(articles), 3)

    def test_canonicalises_url(self):
        source = _make()
        articles = source.parse(SITEMAP_SAMPLE)
        urls = sorted(a.url for a in articles)
        self.assertEqual(
            urls,
            [
                "https://news.tvbs.com.tw/local/3199430",
                "https://news.tvbs.com.tw/local/3199431",
            ],
        )

    def test_extracts_publication_date(self):
        source = _make()
        articles = source.parse(SITEMAP_SAMPLE)
        for art in articles:
            self.assertIsNotNone(art.published_at)

    def test_extracts_optional_author_metadata(self):
        feed = """<?xml version="1.0" encoding="UTF-8" ?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url><loc>https://news.tvbs.com.tw/local/author</loc>
    <news:news>
      <news:publication><news:name>TVBS新聞網</news:name><news:language>zh-tw</news:language></news:publication>
      <news:publication_date>2026-05-08T22:22:58+08:00</news:publication_date>
      <news:title>作者測試</news:title>
      <news:author>記者王小明／台北報導</news:author>
    </news:news>
  </url>
</urlset>
"""
        articles = _make().parse(feed)
        self.assertEqual(articles[0].authors, ["王小明"])
        self.assertEqual(articles[0].raw["author_values"], ["記者王小明／台北報導"])
        self.assertEqual(articles[0].raw["publication_name"], "TVBS新聞網")

    def test_drops_old_entries(self):
        old_iso = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        recent_iso = datetime.now(timezone.utc).isoformat()
        feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url><loc>https://news.tvbs.com.tw/local/old</loc>
    <news:news>
      <news:publication><news:name>x</news:name><news:language>zh-tw</news:language></news:publication>
      <news:publication_date>{old_iso}</news:publication_date>
      <news:title>old</news:title>
    </news:news>
  </url>
  <url><loc>https://news.tvbs.com.tw/local/new</loc>
    <news:news>
      <news:publication><news:name>x</news:name><news:language>zh-tw</news:language></news:publication>
      <news:publication_date>{recent_iso}</news:publication_date>
      <news:title>fresh</news:title>
    </news:news>
  </url>
</urlset>
"""
        source = _make(max_age_days=3)
        titles = [a.title for a in source.parse(feed)]
        self.assertEqual(titles, ["fresh"])

    def test_returns_empty_on_malformed_xml(self):
        self.assertEqual(_make().parse("<not valid"), [])

    def test_skips_url_without_news_block(self):
        feed = """<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
          <url><loc>https://news.tvbs.com.tw/local/abc</loc></url>
        </urlset>"""
        self.assertEqual(_make().parse(feed), [])

    def test_accepts_bytes_input(self):
        articles = _make().parse(SITEMAP_SAMPLE.encode("utf-8"))
        self.assertEqual(len(articles), 2)


if __name__ == "__main__":
    unittest.main()
