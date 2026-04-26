# 設定載入與預設值測試。
import os
import tempfile
import unittest
from pathlib import Path

from news_collector.config import DEFAULT_RSS_FEEDS, load_settings


class ConfigTests(unittest.TestCase):
    """封裝 Config Tests 相關資料與行為。"""
    def test_load_settings_uses_defaults_when_env_missing(self) -> None:
        """測試 test load settings uses defaults when env missing 的預期行為。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("", encoding="utf-8")

            settings = load_settings(str(env_path))

        self.assertFalse(settings.x_enabled)
        self.assertFalse(settings.sec_enabled)
        self.assertEqual(settings.sec_user_agent, "news-collector/0.1 local-admin@example.com")
        self.assertEqual(settings.sec_tracked_tickers, [])
        self.assertEqual(settings.sec_allowed_forms, ["8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "6-K", "6-K/A", "20-F", "20-F/A"])
        self.assertEqual(settings.sec_max_filings_per_company, 5)
        self.assertFalse(settings.twse_mops_enabled)
        self.assertEqual(settings.twse_mops_tracked_codes, [])
        self.assertEqual(settings.twse_mops_max_items_per_company, 5)
        self.assertIsNone(settings.x_bearer_token)
        self.assertEqual(settings.x_bearer_token_file, ".secrets/x_bearer_token.dpapi")
        self.assertEqual(settings.x_accounts, [])
        self.assertEqual(settings.x_max_results_per_account, 5)
        self.assertTrue(settings.x_stop_on_429)
        self.assertFalse(settings.x_include_replies)
        self.assertFalse(settings.x_include_retweets)
        self.assertTrue(settings.x_backfill_enabled)
        self.assertEqual(settings.x_backfill_max_results_per_account, 10)
        self.assertEqual(settings.official_rss_feeds, DEFAULT_RSS_FEEDS)
        self.assertFalse(settings.official_rss_first_per_feed)
        self.assertGreaterEqual(settings.http_timeout_seconds, 1)

    def test_load_settings_reads_env_file(self) -> None:
        """測試 test load settings reads env file 的預期行為。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "X_ENABLED=true",
                        "SEC_ENABLED=true",
                        "SEC_USER_AGENT=test-agent contact@example.com",
                        "SEC_TRACKED_TICKERS=NVDA,TSM",
                        "SEC_ALLOWED_FORMS=8-K,6-K",
                        "SEC_MAX_FILINGS_PER_COMPANY=3",
                        "TWSE_MOPS_ENABLED=true",
                        "TWSE_MOPS_TRACKED_CODES=2330,2317",
                        "TWSE_MOPS_MAX_ITEMS_PER_COMPANY=2",
                        "X_BEARER_TOKEN=x-token",
                        "X_BEARER_TOKEN_FILE=.secrets/x.dpapi",
                        "X_ACCOUNTS=https://x.com/elonmusk,@realDonaldTrump",
                        "X_MAX_RESULTS_PER_ACCOUNT=3",
                        "X_STOP_ON_429=false",
                        "X_INCLUDE_REPLIES=true",
                        "X_INCLUDE_RETWEETS=true",
                        "X_BACKFILL_ENABLED=false",
                        "X_BACKFILL_MAX_RESULTS_PER_ACCOUNT=12",
                        "OFFICIAL_RSS_FEEDS=https://a.example.com,https://b.example.com",
                        "OFFICIAL_RSS_FIRST_PER_FEED=true",
                        "HTTP_TIMEOUT_SECONDS=7",
                    ]
                ),
                encoding="utf-8",
            )

            # Avoid leakage from external shell environment.
            to_cleanup = [
                "X_ENABLED",
                "SEC_ENABLED",
                "SEC_USER_AGENT",
                "SEC_TRACKED_TICKERS",
                "SEC_ALLOWED_FORMS",
                "SEC_MAX_FILINGS_PER_COMPANY",
                "TWSE_MOPS_ENABLED",
                "TWSE_MOPS_TRACKED_CODES",
                "TWSE_MOPS_MAX_ITEMS_PER_COMPANY",
                "X_BEARER_TOKEN",
                "X_BEARER_TOKEN_FILE",
                "X_ACCOUNTS",
                "X_MAX_RESULTS_PER_ACCOUNT",
                "X_STOP_ON_429",
                "X_INCLUDE_REPLIES",
                "X_INCLUDE_RETWEETS",
                "X_BACKFILL_ENABLED",
                "X_BACKFILL_MAX_RESULTS_PER_ACCOUNT",
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

        self.assertTrue(settings.x_enabled)
        self.assertTrue(settings.sec_enabled)
        self.assertEqual(settings.sec_user_agent, "test-agent contact@example.com")
        self.assertEqual(settings.sec_tracked_tickers, ["NVDA", "TSM"])
        self.assertEqual(settings.sec_allowed_forms, ["8-K", "6-K"])
        self.assertEqual(settings.sec_max_filings_per_company, 3)
        self.assertTrue(settings.twse_mops_enabled)
        self.assertEqual(settings.twse_mops_tracked_codes, ["2330", "2317"])
        self.assertEqual(settings.twse_mops_max_items_per_company, 2)
        self.assertEqual(settings.x_bearer_token, "x-token")
        self.assertEqual(settings.x_bearer_token_file, ".secrets/x.dpapi")
        self.assertEqual(settings.x_accounts, ["https://x.com/elonmusk", "@realDonaldTrump"])
        self.assertEqual(settings.x_max_results_per_account, 3)
        self.assertFalse(settings.x_stop_on_429)
        self.assertTrue(settings.x_include_replies)
        self.assertTrue(settings.x_include_retweets)
        self.assertFalse(settings.x_backfill_enabled)
        self.assertEqual(settings.x_backfill_max_results_per_account, 12)
        self.assertEqual(settings.official_rss_feeds, ["https://a.example.com", "https://b.example.com"])
        self.assertTrue(settings.official_rss_first_per_feed)
        self.assertEqual(settings.http_timeout_seconds, 7)


if __name__ == "__main__":
    unittest.main()
