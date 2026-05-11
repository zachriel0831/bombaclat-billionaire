"""news_platform.sources.ettoday_list 解析測試（不打外網）。"""

import unittest
from unittest.mock import patch

from news_platform.sources.ettoday_list import EttodayNewsListSource


HTML_SAMPLE = """
<html><body>
  <div class="part_list_2">
    <h3>
      <span class="date">2026/05/10 18:45</span>
      <em class="tag c_news">政治</em>
      <a target="_blank" href="https://www.ettoday.net/news/20260510/3163601.htm?from=fb">
        行政院回應立院議案
      </a>
    </h3>
    <h3>
      <span class="date">2026/05/10 18:20</span>
      <em class="tag c_society">社會</em>
      <a target="_blank" href="https://www.ettoday.net/news/20260510/3163602.htm">
        社會新聞不應進政治來源
      </a>
    </h3>
    <h3>
      <span class="date">2026/05/10 17:30</span>
      <em class="tag c_news">政治</em>
      <a target="_blank" href="/news/20260510/3163603.htm">總統府說明出訪</a>
    </h3>
  </div>
</body></html>
"""


def _make_source(**overrides) -> EttodayNewsListSource:
    base = dict(
        source_id="ettoday",
        country="TW",
        category="politics",
        url="https://www.ettoday.net/news/news-list-2026-05-10-1.htm",
        max_age_days=0,
    )
    base.update(overrides)
    return EttodayNewsListSource(**base)


class EttodayNewsListTests(unittest.TestCase):
    def test_parses_only_expected_category_rows(self):
        articles = _make_source().parse(HTML_SAMPLE)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].category, "politics")
        self.assertEqual(articles[0].tags, ["政治"])
        self.assertEqual(articles[0].title, "行政院回應立院議案")
        self.assertEqual(
            articles[0].url,
            "https://www.ettoday.net/news/20260510/3163601.htm",
        )
        self.assertEqual(
            articles[1].url,
            "https://www.ettoday.net/news/20260510/3163603.htm",
        )

    def test_fetch_uses_date_template_and_dedupes(self):
        source = _make_source(url="https://www.ettoday.net/news/news-list-{date}-1.htm", max_age_days=0)
        with patch("news_platform.sources.ettoday_list.http_get_bytes", return_value=HTML_SAMPLE.encode("utf-8")):
            articles = source.fetch(limit=20)

        self.assertEqual(len(articles), 2)
        self.assertEqual({a.title for a in articles}, {"行政院回應立院議案", "總統府說明出訪"})


if __name__ == "__main__":
    unittest.main()
