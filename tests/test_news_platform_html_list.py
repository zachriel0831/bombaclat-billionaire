"""news_platform.sources.html_list parser tests."""

import unittest

from news_platform.author_metadata import AUTHOR_STATUS_NO_DETAIL_FETCHED
from news_platform.sources.html_list import HtmlListSource


TVBS_HTML = """
<html><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "mainEntity": {
    "@type": "ItemList",
    "itemListElement": [
      {
        "@type": "ListItem",
        "item": {
          "@type": "NewsArticle",
          "headline": "社會測試標題",
          "url": "https://news.tvbs.com.tw/local/4004712",
          "datePublished": "2026-08-09T15:50:50.000Z"
        }
      },
      {
        "@type": "ListItem",
        "item": {
          "@type": "NewsArticle",
          "headline": "政治測試標題",
          "url": "https://news.tvbs.com.tw/politics/4004663"
        }
      }
    ]
  }
}
</script>
</body></html>
"""


UDN_HTML = """
<div class="story-list__news ">
  <div class="story-list__image">
    <a href="/news/story/7320/9680851?from=udn-catebreaknews_ch2"
       title="澎湖縣府介入 棄養子女神隱夫妻 允今天回家"></a>
  </div>
  <div class="story-list__text">
    <h3><a href="/news/story/7320/9680851?from=udn-catebreaknews_ch2">澎湖縣府介入 棄養子女神隱夫妻 允今天回家</a></h3>
    <p>澎湖縣政府前往評估。</p>
    <time class="story-list__time">2026-08-10 00:17</time>
  </div>
</div>
"""


SETN_HTML = """
<div class="news_list_item ">
  <div class="news_info">
    <div class="title title_pc"><a class="smart-link" href="https://www.setn.com/news/1886721">政治分類標題</a></div>
    <div class="time_box">
      <a class="tab smart-link" href="https://www.setn.com/catalog/politics">政治</a>
      <div class="time">2026/08/09 21:00</div>
    </div>
  </div>
</div>
<div class="news_list_item ">
  <div class="news_info">
    <div class="title title_pc"><a class="smart-link" href="https://www.setn.com/news/1886735">天氣分類標題</a></div>
    <div class="time_box">
      <a class="tab smart-link" href="https://www.setn.com/catalog/life">生活</a>
      <div class="time">2026/08/09 21:10</div>
    </div>
  </div>
</div>
"""


STORM_HTML = """
<a href="/article/11157253" target="_self" class="articleGeneralCover">
  <img src="cover.webp">
</a>
<a href="/article/11157253" class="generalLink">
  <!--[--><h3>台中會翻盤？郭正亮洞悉「何欣純實力」：江啟臣這樣打就能勝選</h3><!--]-->
</a>
<div class="text-smg-gray-600">2026-08-17 18:16</div>
<a href="/article/11157252" class="generalLink">
  <!--[-->被爆昔稱普發現金是「先窮台，再統一」 沈伯洋：我標準沒變過<!--]-->
</a>
<div class="text-smg-gray-600">2026-08-17 18:11:56</div>
<a href="/article/11157252" class="generalLink">
  <!--[-->被爆昔稱普發現金是「先窮台，再統一」 沈伯洋：我標準沒變過<!--]-->
</a>
"""


class HtmlListSourceTests(unittest.TestCase):
    def test_tvbs_json_ld_uses_path_filter(self):
        source = HtmlListSource(
            source_id="tvbs",
            country="TW",
            category="society",
            url="https://news.tvbs.com.tw/local",
            path_filter="/local/",
            max_age_days=0,
        )

        articles = source.parse(TVBS_HTML)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "社會測試標題")
        self.assertEqual(articles[0].url, "https://news.tvbs.com.tw/local/4004712")
        self.assertEqual(articles[0].author_extraction_status, AUTHOR_STATUS_NO_DETAIL_FETCHED)
        self.assertEqual(articles[0].raw["parser"], "tvbs_json_ld")

    def test_udn_story_list_parses_title_summary_and_time(self):
        source = HtmlListSource(
            source_id="udn",
            country="TW",
            category="society",
            url="https://udn.com/news/cate/2/6639",
            max_age_days=0,
        )

        articles = source.parse(UDN_HTML)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "澎湖縣府介入 棄養子女神隱夫妻 允今天回家")
        self.assertEqual(articles[0].url, "https://udn.com/news/story/7320/9680851")
        self.assertEqual(articles[0].summary, "澎湖縣政府前往評估。")
        self.assertEqual(articles[0].published_at.isoformat(), "2026-08-10T00:17:00+08:00")

    def test_setn_news_list_keeps_expected_category_only(self):
        source = HtmlListSource(
            source_id="setn",
            country="TW",
            category="politics",
            url="https://www.setn.com/ViewAll.aspx?PageGroupID=6",
            max_age_days=0,
        )

        articles = source.parse(SETN_HTML)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "政治分類標題")
        self.assertEqual(articles[0].url, "https://www.setn.com/news/1886721")
        self.assertEqual(articles[0].tags, ["政治"])
        self.assertEqual(articles[0].published_at.isoformat(), "2026-08-09T21:00:00+08:00")

    def test_storm_channel_parses_article_titles_and_dates(self):
        source = HtmlListSource(
            source_id="storm",
            country="TW",
            category="politics",
            url="https://www.storm.mg/channel/7",
            max_age_days=0,
        )

        articles = source.parse(STORM_HTML)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].title, "台中會翻盤？郭正亮洞悉「何欣純實力」：江啟臣這樣打就能勝選")
        self.assertEqual(articles[0].url, "https://www.storm.mg/article/11157253")
        self.assertEqual(articles[0].published_at.isoformat(), "2026-08-17T18:16:00+08:00")
        self.assertEqual(articles[0].raw["parser"], "storm_channel")
        self.assertEqual(articles[1].published_at.isoformat(), "2026-08-17T18:11:56+08:00")


if __name__ == "__main__":
    unittest.main()
