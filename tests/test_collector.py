# collector 組態與來源啟用邏輯測試。
import unittest

from news_collector.collector import build_sources
from news_collector.config import Settings


class CollectorTests(unittest.TestCase):
    """封裝 Collector Tests 相關資料與行為。"""
    def _settings(
        self,
        x_enabled: bool = False,
        x_bearer_token: str | None = None,
        x_accounts: list[str] | None = None,
    ) -> Settings:
        """執行 settings 方法的主要邏輯。"""
        return Settings(
            sec_enabled=False,
            sec_user_agent="news-collector/0.1 local-admin@example.com",
            sec_tracked_tickers=["NVDA", "TSM"],
            sec_allowed_forms=["8-K", "10-Q", "10-K", "6-K", "20-F"],
            sec_max_filings_per_company=5,
            twse_mops_enabled=False,
            twse_mops_tracked_codes=["2330", "2317", "2454"],
            twse_mops_max_items_per_company=5,
            x_enabled=x_enabled,
            x_bearer_token=x_bearer_token,
            x_bearer_token_file=".secrets/does_not_exist_for_x_test.dpapi",
            x_accounts=x_accounts or ["https://x.com/elonmusk", "https://x.com/realdonaldtrump"],
            x_max_results_per_account=5,
            x_stop_on_429=True,
            x_auto_heal_too_many_connections=True,
            x_heal_cooldown_seconds=45,
            x_include_replies=False,
            x_include_retweets=False,
            x_backfill_enabled=True,
            x_backfill_max_results_per_account=10,
            official_rss_feeds=["https://example.com/rss.xml"],
            official_rss_first_per_feed=False,
            http_timeout_seconds=3,
        )

    def test_build_sources_all_without_x(self) -> None:
        """測試 test build sources all without x 的預期行為。"""
        sources = build_sources(self._settings(x_enabled=False, x_bearer_token=None), "all")
        names = [s.name for s in sources]
        self.assertIn("official_rss", names)
        self.assertNotIn("sec_filings", names)
        self.assertNotIn("twse_mops_announcements", names)
        self.assertNotIn("x_accounts", names)

    def test_build_sources_x_disabled(self) -> None:
        """測試 test build sources x disabled 的預期行為。"""
        with self.assertRaises(ValueError):
            build_sources(self._settings(x_enabled=False, x_bearer_token="token"), "x")

    def test_build_sources_x_requires_token(self) -> None:
        """測試 test build sources x requires token 的預期行為。"""
        with self.assertRaises(ValueError):
            build_sources(self._settings(x_enabled=True, x_bearer_token=None), "x")

    def test_build_sources_x_enabled(self) -> None:
        """測試 test build sources x enabled 的預期行為。"""
        sources = build_sources(
            self._settings(
                x_enabled=True,
                x_bearer_token="token",
                x_accounts=["https://x.com/elonmusk", "https://x.com/realdonaldtrump"],
            ),
            "x",
        )
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "x_accounts")

    def test_build_sources_sec_enabled(self) -> None:
        """測試 test build sources sec enabled 的預期行為。"""
        settings = self._settings(x_enabled=False, x_bearer_token=None)
        settings = Settings(
            **{
                **settings.__dict__,
                "sec_enabled": True,
                "sec_user_agent": "news-collector/0.1 local-admin@example.com",
                "sec_tracked_tickers": ["NVDA", "TSM"],
            }
        )

        sources = build_sources(settings, "sec")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "sec_filings")

    def test_build_sources_sec_requires_tickers(self) -> None:
        """測試 test build sources sec requires tickers 的預期行為。"""
        settings = self._settings(x_enabled=False, x_bearer_token=None)
        settings = Settings(
            **{
                **settings.__dict__,
                "sec_enabled": True,
                "sec_tracked_tickers": [],
            }
        )

        with self.assertRaises(ValueError):
            build_sources(settings, "sec")

    def test_build_sources_twse_enabled(self) -> None:
        """測試 test build sources twse enabled 的預期行為。"""
        settings = self._settings(x_enabled=False, x_bearer_token=None)
        settings = Settings(
            **{
                **settings.__dict__,
                "twse_mops_enabled": True,
                "twse_mops_tracked_codes": ["2330", "2317"],
            }
        )

        sources = build_sources(settings, "twse")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "twse_mops_announcements")

    def test_build_sources_twse_requires_codes(self) -> None:
        """測試 test build sources twse requires codes 的預期行為。"""
        settings = self._settings(x_enabled=False, x_bearer_token=None)
        settings = Settings(
            **{
                **settings.__dict__,
                "twse_mops_enabled": True,
                "twse_mops_tracked_codes": [],
            }
        )

        with self.assertRaises(ValueError):
            build_sources(settings, "twse")


if __name__ == "__main__":
    unittest.main()
