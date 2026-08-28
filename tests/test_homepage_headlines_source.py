import unittest
from datetime import timezone
from unittest.mock import patch

from news_collector.sources.homepage_headlines import HomepageHeadlinesSource


class HomepageHeadlinesSourceTests(unittest.TestCase):
    def test_fetch_parses_homepage_article_links(self) -> None:
        html = """
        <html>
          <body>
            <a href="/news/articles/c123">Global chip talks reshape AI supply chains</a>
            <a href="/news/articles/c123">Global chip talks reshape AI supply chains</a>
            <a href="/news">News</a>
            <a href="/sport/articles/c456">Football team wins final match</a>
          </body>
        </html>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.bbc.com/news"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "Homepage: BBC News")
        self.assertEqual(items[0].title, "Global chip talks reshape AI supply chains")
        self.assertEqual(items[0].url, "https://www.bbc.com/news/articles/c123")
        self.assertEqual(items[0].tags, ["english", "homepage_headline", "international"])
        self.assertEqual(items[0].raw["published_at_source"], "fetched_at_homepage_fallback")
        self.assertIsNotNone(items[0].published_at)
        assert items[0].published_at is not None
        self.assertEqual(items[0].published_at.tzinfo, timezone.utc)

    def test_custom_homepage_uses_readable_source_label(self) -> None:
        html = """<a href="/2026/08/28/world-story">A major world story with enough words</a>"""

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://world.example.com/"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "Homepage: world.example.com")
        self.assertEqual(items[0].url, "https://world.example.com/2026/08/28/world-story")

    def test_duplicate_article_keeps_cleaner_text_headline(self) -> None:
        html = """
        <a href="/2026/08/28/asia/example-intl-hnk">
          People stand near a building in Asia, August 28. Photographer/Reuters
        </a>
        <a href="/2026/08/28/asia/example-intl-hnk">
          Leaders agree to reopen border talks after regional summit
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.cnn.com/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Leaders agree to reopen border talks after regional summit")

    def test_image_alt_only_anchor_is_not_a_headline(self) -> None:
        html = """
        <a href="/news/articles/c123">
          <img alt="A suited official stands near a flag" />
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.bbc.com/news/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(items, [])

    def test_long_homepage_card_text_drops_summary_tail(self) -> None:
        html = """
        <a href="/world/2026/aug/28/example-news">
          Ministers agree new relief package after floods The agreement follows days of
          talks and local warnings about blocked roads.
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.theguardian.com/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Ministers agree new relief package after floods")

    def test_photo_caption_prefix_keeps_article_title(self) -> None:
        html = """
        <a href="/news/nepal-flood-glacier-risks-warming-himalayas">
          An aerial view shows houses deluged in sludge after flash flooding on Aug. 27, 2026.
          Nepal flood highlights glacier risks in warming Himalayas
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.cbsnews.com/world/"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Nepal flood highlights glacier risks in warming Himalayas")

    def test_long_year_caption_keeps_tail_title(self) -> None:
        html = """
        <a href="/news/articles/c5ywxpryj95o">
          Former commander appears in court at the International Criminal Tribunal in
          the Hague, June 3, 2011 Convicted war criminal dies aged 84
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.bbc.com/news/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Convicted war criminal dies aged 84")

    def test_caption_only_anchor_falls_back_to_url_slug(self) -> None:
        html = """
        <a href="/2026/08/27/asia/iran-war-us-oil-sanctions-china-resisting-trump-economic-threats-intl-hnk">
          Vessels in the Strait of Hormuz are visible near Iran, August 26, 2026.
          Majid Asgaripour via REUTERS ATTENTION EDITORS
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.cnn.com/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Iran War US Oil Sanctions China Resisting Trump Economic Threats")

    def test_live_news_hub_is_not_treated_as_article(self) -> None:
        html = """
        <a href="/2026/08/26/world/live-news/nepal-flash-flooding-floods-intl">
          Nepal flash flooding floods live updates
        </a>
        """

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.cnn.com/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(items, [])

    def test_time_prefix_is_removed_from_headline(self) -> None:
        html = """<a href="/news/articles/c123">44 mins ago What we know about deadly floods</a>"""

        with patch("news_collector.sources.homepage_headlines.http_get_text_with_headers", return_value=html):
            items = HomepageHeadlinesSource(["https://www.bbc.com/news/world"], timeout_seconds=3).fetch(limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "What we know about deadly floods")


if __name__ == "__main__":
    unittest.main()
