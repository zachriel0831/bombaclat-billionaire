import unittest
from unittest.mock import patch

from news_collector.sources.truth_social import (
    TruthSocialAccountSource,
    _TRUTH_ACCOUNT_ID_CACHE,
    _TRUTH_SINCE_ID_CACHE,
    _normalize_account,
    _plain_text_from_html,
)


class TruthSocialSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        _TRUTH_ACCOUNT_ID_CACHE.clear()
        _TRUTH_SINCE_ID_CACHE.clear()

    def test_normalize_account(self) -> None:
        self.assertEqual(_normalize_account("https://truthsocial.com/@realDonaldTrump"), "realdonaldtrump")
        self.assertEqual(_normalize_account("truthsocial:realDonaldTrump"), "realdonaldtrump")
        self.assertEqual(_normalize_account("@JDVance"), "jdvance")
        self.assertIsNone(_normalize_account("https://example.com/@realDonaldTrump"))

    def test_plain_text_from_html(self) -> None:
        self.assertEqual(
            _plain_text_from_html("<p>Hello&nbsp;<strong>world</strong><br/>Line 2</p>"),
            "Hello world Line 2",
        )

    def test_fetch_maps_public_statuses_to_news_items(self) -> None:
        source = TruthSocialAccountSource(
            accounts=["https://truthsocial.com/@realDonaldTrump"],
            timeout_seconds=3,
            max_results_per_account=5,
            user_agent="test-browser",
        )

        lookup_payload = {"id": "107780257626128497", "username": "realDonaldTrump"}
        statuses_payload = {
            "data": [
                {
                    "id": "116819418021640869",
                    "created_at": "2026-06-27T01:14:18.033Z",
                    "url": "https://truthsocial.com/@realDonaldTrump/116819418021640869",
                    "content": "<p>Hello&nbsp;<strong>Truth</strong></p>",
                    "language": "en",
                    "replies_count": 1,
                    "reblogs_count": 2,
                    "favourites_count": 3,
                    "account": {"id": "107780257626128497"},
                }
            ]
        }

        with patch.object(source, "_request_json", side_effect=[lookup_payload, statuses_payload]):
            items = source.fetch(limit=5)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.id, "truthsocial-116819418021640869")
        self.assertEqual(item.source, "truthsocial:realdonaldtrump")
        self.assertEqual(item.title, "Hello Truth")
        self.assertEqual(item.summary, "Hello Truth")
        self.assertEqual(item.url, "https://truthsocial.com/@realDonaldTrump/116819418021640869")
        self.assertIn("account:realdonaldtrump", item.tags)
        self.assertIn("platform:truthsocial", item.tags)
        self.assertEqual(item.raw["platform"], "truthsocial")
        self.assertEqual(item.raw["metrics"]["favourites_count"], 3)

    def test_fetch_applies_local_limit_when_api_returns_more(self) -> None:
        source = TruthSocialAccountSource(
            accounts=["@realDonaldTrump"],
            timeout_seconds=3,
            max_results_per_account=5,
            user_agent="test-browser",
        )

        lookup_payload = {"id": "107780257626128497", "username": "realDonaldTrump"}
        statuses_payload = {
            "data": [
                {
                    "id": "116819418021640869",
                    "created_at": "2026-06-27T01:14:18.033Z",
                    "url": "https://truthsocial.com/@realDonaldTrump/116819418021640869",
                    "content": "<p>First post</p>",
                    "language": "en",
                },
                {
                    "id": "116819418021640870",
                    "created_at": "2026-06-27T01:15:18.033Z",
                    "url": "https://truthsocial.com/@realDonaldTrump/116819418021640870",
                    "content": "<p>Second post</p>",
                    "language": "en",
                },
            ]
        }

        with patch.object(source, "_request_json", side_effect=[lookup_payload, statuses_payload]):
            items = source.fetch(limit=1)

        self.assertEqual([item.id for item in items], ["truthsocial-116819418021640869"])


if __name__ == "__main__":
    unittest.main()
