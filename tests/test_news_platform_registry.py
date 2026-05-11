"""news_platform.registry tests."""

import os
import unittest

from news_platform.registry import (
    SUPPORTED_TW_CATEGORIES,
    tw_news_feeds,
    tw_politics_feeds,
    tw_society_feeds,
)


class RegistryTests(unittest.TestCase):
    def test_default_news_feeds_include_society_and_politics(self):
        feeds = tw_news_feeds()
        categories = {feed.category for feed in feeds}

        self.assertEqual(categories, set(SUPPORTED_TW_CATEGORIES))
        self.assertEqual(len([f for f in feeds if f.category == "society"]), 6)
        self.assertEqual(len([f for f in feeds if f.category == "politics"]), 6)

    def test_politics_feeds_include_ettoday_list_source(self):
        feeds = tw_politics_feeds()
        by_source = {feed.source_id: feed for feed in feeds}

        self.assertEqual(by_source["ettoday"].kind, "ettoday_list")
        self.assertIn("{date}", by_source["ettoday"].url)
        self.assertEqual(by_source["tvbs"].path_filter, "/politics/")
        self.assertEqual(by_source["pts"].kind, "pts_category")
        self.assertEqual(by_source["pts"].url, "https://news.pts.org.tw/category/1")
        self.assertEqual(by_source["ebc"].path_filter, "/news/politics/")

    def test_society_feeds_still_use_existing_sources(self):
        feeds = tw_society_feeds()
        by_source = {feed.source_id: feed for feed in feeds}

        self.assertEqual(by_source["ettoday"].kind, "rss")
        self.assertEqual(by_source["tvbs"].path_filter, "/local/")
        self.assertEqual(by_source["pts"].kind, "pts_category")
        self.assertEqual(by_source["pts"].url, "https://news.pts.org.tw/category/7")

    def test_env_override_is_category_specific(self):
        key = "NEWSPF_FEED_LTN_POLITICS"
        old_value = os.environ.get(key)
        os.environ[key] = "https://example.test/politics.xml"
        try:
            feed = next(feed for feed in tw_politics_feeds() if feed.source_id == "ltn")
        finally:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        self.assertEqual(feed.url, "https://example.test/politics.xml")

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            tw_news_feeds(categories=("sports",))


if __name__ == "__main__":
    unittest.main()
