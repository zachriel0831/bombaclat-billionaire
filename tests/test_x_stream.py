import unittest

from news_collector.x_stream import XFilteredStreamer, XStreamConfig, _normalize_account


class XStreamTests(unittest.TestCase):
    def _streamer(self) -> XFilteredStreamer:
        return XFilteredStreamer(
            XStreamConfig(
                bearer_token="token",
                accounts=["https://x.com/elonmusk", "@realDonaldTrump"],
                include_replies=False,
                include_retweets=False,
            )
        )

    def test_normalize_account(self) -> None:
        self.assertEqual(_normalize_account("https://x.com/elonmusk"), "elonmusk")
        self.assertEqual(_normalize_account("@realDonaldTrump"), "realdonaldtrump")
        self.assertIsNone(_normalize_account("https://example.com/not-x"))

    def test_build_query_contains_accounts_and_excludes(self) -> None:
        streamer = self._streamer()
        query = streamer._build_query(["elonmusk", "realdonaldtrump"])
        self.assertIn("from:elonmusk", query)
        self.assertIn("from:realdonaldtrump", query)
        self.assertIn("-is:reply", query)
        self.assertIn("-is:retweet", query)

    def test_to_news_item_parses_stream_payload(self) -> None:
        streamer = self._streamer()
        payload = {
            "data": {
                "id": "2030137912345678901",
                "text": "Hello stream",
                "author_id": "44196397",
                "created_at": "2026-03-07T10:20:30.000Z",
                "lang": "en",
            },
            "includes": {
                "users": [
                    {"id": "44196397", "username": "elonmusk"},
                ]
            },
        }

        item = streamer._to_news_item(payload)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.id, "x-2030137912345678901")
        self.assertEqual(item.source, "x:elonmusk")
        self.assertEqual(item.title, "Hello stream")
        self.assertEqual(item.url, "https://x.com/elonmusk/status/2030137912345678901")
        self.assertIn("account:elonmusk", item.tags)
        self.assertIn("lang:en", item.tags)

    def test_remember_tweet_dedup(self) -> None:
        streamer = self._streamer()
        self.assertTrue(streamer._remember_tweet("x-1"))
        self.assertFalse(streamer._remember_tweet("x-1"))

    def test_is_too_many_connections_429(self) -> None:
        body = '{"title":"ConnectionException","connection_issue":"TooManyConnections"}'
        self.assertTrue(XFilteredStreamer._is_too_many_connections_429(body))
        self.assertFalse(XFilteredStreamer._is_too_many_connections_429('{"title":"RateLimited"}'))

    def test_parse_connection_kill_stats(self) -> None:
        success, failed = XFilteredStreamer._parse_connection_kill_stats(
            {"data": {"successful_kills": 2, "failed_kills": 1}}
        )
        self.assertEqual(success, 2)
        self.assertEqual(failed, 1)


if __name__ == "__main__":
    unittest.main()
