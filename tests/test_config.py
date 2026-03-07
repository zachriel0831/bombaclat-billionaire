# 設定載入與預設值測試。
import os
import tempfile
import unittest
from pathlib import Path

from news_collector.config import DEFAULT_RSS_FEEDS, load_settings


class ConfigTests(unittest.TestCase):
    def test_load_settings_uses_defaults_when_env_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("", encoding="utf-8")

            settings = load_settings(str(env_path))

        self.assertFalse(settings.benzinga_enabled)
        self.assertIsNone(settings.benzinga_api_key)
        self.assertEqual(settings.benzinga_api_key_file, ".secrets/benzinga_api_key.dpapi")
        self.assertFalse(settings.benzinga_stop_on_429)
        self.assertFalse(settings.x_enabled)
        self.assertIsNone(settings.x_bearer_token)
        self.assertEqual(settings.x_bearer_token_file, ".secrets/x_bearer_token.dpapi")
        self.assertEqual(settings.x_accounts, [])
        self.assertEqual(settings.x_max_results_per_account, 5)
        self.assertTrue(settings.x_stop_on_429)
        self.assertFalse(settings.x_include_replies)
        self.assertFalse(settings.x_include_retweets)
        self.assertFalse(settings.gdelt_cooldown_on_429)
        self.assertEqual(settings.gdelt_cooldown_seconds, 600)
        self.assertEqual(settings.official_rss_feeds, DEFAULT_RSS_FEEDS)
        self.assertFalse(settings.official_rss_first_per_feed)
        self.assertGreaterEqual(settings.http_timeout_seconds, 1)

    def test_load_settings_reads_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "BENZINGA_ENABLED=true",
                        "BENZINGA_API_KEY=test-key",
                        "BENZINGA_API_KEY_FILE=.secrets/custom.dpapi",
                        "BENZINGA_STOP_ON_429=true",
                        "X_ENABLED=true",
                        "X_BEARER_TOKEN=x-token",
                        "X_BEARER_TOKEN_FILE=.secrets/x.dpapi",
                        "X_ACCOUNTS=https://x.com/elonmusk,@realDonaldTrump",
                        "X_MAX_RESULTS_PER_ACCOUNT=3",
                        "X_STOP_ON_429=false",
                        "X_INCLUDE_REPLIES=true",
                        "X_INCLUDE_RETWEETS=true",
                        "GDELT_QUERY=(cpi OR inflation)",
                        "GDELT_MAX_RECORDS=10",
                        "GDELT_COOLDOWN_ON_429=true",
                        "GDELT_COOLDOWN_SECONDS=900",
                        "OFFICIAL_RSS_FEEDS=https://a.example.com,https://b.example.com",
                        "OFFICIAL_RSS_FIRST_PER_FEED=true",
                        "HTTP_TIMEOUT_SECONDS=7",
                    ]
                ),
                encoding="utf-8",
            )

            # Avoid leakage from external shell environment.
            to_cleanup = [
                "BENZINGA_ENABLED",
                "BENZINGA_API_KEY",
                "BENZINGA_API_KEY_FILE",
                "BENZINGA_STOP_ON_429",
                "X_ENABLED",
                "X_BEARER_TOKEN",
                "X_BEARER_TOKEN_FILE",
                "X_ACCOUNTS",
                "X_MAX_RESULTS_PER_ACCOUNT",
                "X_STOP_ON_429",
                "X_INCLUDE_REPLIES",
                "X_INCLUDE_RETWEETS",
                "GDELT_QUERY",
                "GDELT_MAX_RECORDS",
                "GDELT_COOLDOWN_ON_429",
                "GDELT_COOLDOWN_SECONDS",
                "OFFICIAL_RSS_FEEDS",
                "OFFICIAL_RSS_FIRST_PER_FEED",
                "HTTP_TIMEOUT_SECONDS",
            ]
            original = {key: os.environ.get(key) for key in to_cleanup}
            for key in to_cleanup:
                os.environ.pop(key, None)

            settings = load_settings(str(env_path))

            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertTrue(settings.benzinga_enabled)
        self.assertEqual(settings.benzinga_api_key, "test-key")
        self.assertEqual(settings.benzinga_api_key_file, ".secrets/custom.dpapi")
        self.assertTrue(settings.benzinga_stop_on_429)
        self.assertTrue(settings.x_enabled)
        self.assertEqual(settings.x_bearer_token, "x-token")
        self.assertEqual(settings.x_bearer_token_file, ".secrets/x.dpapi")
        self.assertEqual(settings.x_accounts, ["https://x.com/elonmusk", "@realDonaldTrump"])
        self.assertEqual(settings.x_max_results_per_account, 3)
        self.assertFalse(settings.x_stop_on_429)
        self.assertTrue(settings.x_include_replies)
        self.assertTrue(settings.x_include_retweets)
        self.assertEqual(settings.gdelt_query, "(cpi OR inflation)")
        self.assertEqual(settings.gdelt_max_records, 10)
        self.assertTrue(settings.gdelt_cooldown_on_429)
        self.assertEqual(settings.gdelt_cooldown_seconds, 900)
        self.assertEqual(settings.official_rss_feeds, ["https://a.example.com", "https://b.example.com"])
        self.assertTrue(settings.official_rss_first_per_feed)
        self.assertEqual(settings.http_timeout_seconds, 7)


if __name__ == "__main__":
    unittest.main()
