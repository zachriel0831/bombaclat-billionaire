"""news_platform.sources.pts_category parser tests."""

import unittest
from unittest.mock import patch

from news_platform.sources.pts_category import PtsCategorySource


HTML_SAMPLE = """
<html><body>
  <div class="breakingnews">
    <figure><a href="https://news.pts.org.tw/article/807644"></a></figure>
    <h2><a href="https://news.pts.org.tw/article/807644">Political title</a></h2>
    <div class="news-info">
      <time datetime="2026-05-10 19:14:46">2026/5/10 19:14</time>
    </div>
  </div>
  <ul class="news-list">
    <li>
      <figure><a href="https://news.pts.org.tw/article/807620"></a></figure>
      <div>
        <h2 title="Cabinet title">
          <a href="https://news.pts.org.tw/article/807620?utm_source=x">Cabinet title</a>
        </h2>
        <time datetime="2026-05-10 12:10:03">2026/5/10 12:10</time>
      </div>
    </li>
  </ul>
</body></html>
"""


def _make_source(**overrides) -> PtsCategorySource:
    base = dict(
        source_id="pts",
        country="TW",
        category="politics",
        url="https://news.pts.org.tw/category/1",
        max_age_days=0,
    )
    base.update(overrides)
    return PtsCategorySource(**base)


class PtsCategoryTests(unittest.TestCase):
    def test_parses_category_page_rows(self):
        articles = _make_source().parse(HTML_SAMPLE)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].source_id, "pts")
        self.assertEqual(articles[0].category, "politics")
        self.assertEqual(articles[0].title, "Political title")
        self.assertEqual(articles[0].url, "https://news.pts.org.tw/article/807644")
        self.assertEqual(articles[0].published_at.isoformat(), "2026-05-10T19:14:46+08:00")
        self.assertEqual(articles[0].raw["kind"], "pts_category")
        self.assertEqual(
            articles[1].url,
            "https://news.pts.org.tw/article/807620",
        )

    def test_fetch_dedupes_image_and_title_links(self):
        with patch("news_platform.sources.pts_category.http_get_bytes", return_value=HTML_SAMPLE.encode("utf-8")):
            articles = _make_source().fetch(limit=20)

        self.assertEqual(len(articles), 2)
        self.assertEqual({a.title for a in articles}, {"Political title", "Cabinet title"})


if __name__ == "__main__":
    unittest.main()
