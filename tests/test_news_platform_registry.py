"""news_platform.registry tests."""

import os
import unittest

from news_platform.registry import (
    SUPPORTED_TW_CATEGORIES,
    active_source_ids,
    registered_source_ids,
    source_meta,
    tw_news_feeds,
    tw_politics_feeds,
    tw_society_feeds,
)


class RegistryTests(unittest.TestCase):
    def test_default_news_feeds_include_society_and_politics(self):
        feeds = tw_news_feeds()
        categories = {feed.category for feed in feeds}

        self.assertEqual(categories, set(SUPPORTED_TW_CATEGORIES))
        self.assertEqual(len([f for f in feeds if f.category == "society"]), 7)
        self.assertEqual(len([f for f in feeds if f.category == "politics"]), 7)
        self.assertNotIn("tvbs", active_source_ids())
        self.assertNotIn("ctee", active_source_ids())
        self.assertNotIn("udn", active_source_ids())
        self.assertNotIn("setn", active_source_ids())

    def test_politics_feeds_include_ettoday_list_source(self):
        feeds = tw_politics_feeds()
        by_source = {feed.source_id: feed for feed in feeds}

        self.assertEqual(by_source["ettoday"].kind, "ettoday_list")
        self.assertIn("{date}", by_source["ettoday"].url)
        self.assertEqual(by_source["pts"].kind, "pts_category")
        self.assertEqual(by_source["pts"].url, "https://news.pts.org.tw/category/1")
        self.assertEqual(by_source["ebc"].path_filter, "/news/politics/")
        self.assertEqual(by_source["newtalk"].url, "https://newtalk.tw/rss/category/2")
        self.assertIn("channel_id/7", by_source["storm"].url)

    def test_society_feeds_still_use_existing_sources(self):
        feeds = tw_society_feeds()
        by_source = {feed.source_id: feed for feed in feeds}

        self.assertEqual(by_source["ettoday"].kind, "rss")
        self.assertEqual(by_source["pts"].kind, "pts_category")
        self.assertEqual(by_source["pts"].url, "https://news.pts.org.tw/category/7")
        self.assertEqual(by_source["newtalk"].url, "https://newtalk.tw/rss/category/14")
        self.assertIn("channel_id/9", by_source["storm"].url)

    def test_disabled_sources_can_be_reenabled_by_env(self):
        key = "NEWSPF_DISABLED_SOURCE_IDS"
        old_value = os.environ.get(key)
        os.environ[key] = ""
        try:
            politics = {feed.source_id: feed for feed in tw_politics_feeds()}
            society = {feed.source_id: feed for feed in tw_society_feeds()}
        finally:
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        self.assertEqual(politics["tvbs"].kind, "html_list")
        self.assertEqual(politics["tvbs"].url, "https://news.tvbs.com.tw/politics")
        self.assertEqual(politics["tvbs"].path_filter, "/politics/")
        self.assertEqual(politics["ctee"].path_filter, "-430104")
        self.assertEqual(society["tvbs"].kind, "html_list")
        self.assertEqual(society["tvbs"].url, "https://news.tvbs.com.tw/local")
        self.assertEqual(society["tvbs"].path_filter, "/local/")
        self.assertEqual(society["ctee"].path_filter, "-431401")
        self.assertEqual(society["udn"].url, "https://udn.com/news/cate/2/6639")
        self.assertEqual(society["setn"].url, "https://www.setn.com/ViewAll.aspx?PageGroupID=41")

    def test_source_ids_include_default_disabled_low_frequency_sources(self):
        feeds = tw_news_feeds(categories=("society",), source_ids=("tvbs", "udn", "setn"))
        by_source = {feed.source_id: feed for feed in feeds}

        self.assertEqual(tuple(by_source), ("tvbs", "udn", "setn"))
        self.assertTrue(all(feed.kind == "html_list" for feed in feeds))

    def test_registered_source_ids_include_disabled_sources(self):
        registered = registered_source_ids()

        self.assertIn("ctee", registered)
        self.assertIn("tvbs", registered)
        self.assertIn("udn", registered)
        self.assertIn("setn", registered)

    def test_ctee_source_metadata_is_registered(self):
        meta = source_meta("ctee")

        self.assertIsNotNone(meta)
        self.assertEqual(meta.name, "工商時報")

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
