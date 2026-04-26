import unittest
from unittest.mock import patch

from news_collector.sources.sec_filings import SecFilingsSource, _normalize_ticker


class SecFilingsSourceTests(unittest.TestCase):
    """封裝 Sec Filings Source Tests 相關資料與行為。"""
    def test_normalize_ticker(self) -> None:
        """測試 test normalize ticker 的預期行為。"""
        self.assertEqual(_normalize_ticker(" nvda "), "NVDA")
        self.assertEqual(_normalize_ticker("BRK-B"), "BRK-B")
        self.assertIsNone(_normalize_ticker("bad ticker"))

    @patch("news_collector.sources.sec_filings.http_get_json_with_headers")
    def test_fetch_filters_allowed_forms_and_builds_index_url(self, mock_get_json) -> None:
        """測試 test fetch filters allowed forms and builds index url 的預期行為。"""
        mock_get_json.side_effect = [
            {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            },
            {
                "filings": {
                    "recent": {
                        "form": ["4", "8-K", "10-Q"],
                        "filingDate": ["2026-04-19", "2026-04-18", "2026-04-17"],
                        "acceptanceDateTime": [
                            "2026-04-19T12:30:00.000Z",
                            "2026-04-18T11:20:00.000Z",
                            "2026-04-17T10:10:00.000Z",
                        ],
                        "accessionNumber": [
                            "0000000000-26-000004",
                            "0001045810-26-000123",
                            "0001045810-26-000122",
                        ],
                        "primaryDocument": [
                            "form4.xml",
                            "earnings8k.htm",
                            "q1.htm",
                        ],
                        "primaryDocDescription": [
                            "FORM 4",
                            "Current report",
                            "Quarterly report",
                        ],
                    }
                }
            },
        ]

        source = SecFilingsSource(
            user_agent="news-collector/0.1 local-admin@example.com",
            tracked_tickers=["NVDA"],
            allowed_forms=["8-K", "10-Q"],
            timeout_seconds=3,
            max_filings_per_company=5,
        )

        items = source.fetch(limit=10)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source, "sec:NVDA")
        self.assertIn("8-K", items[0].title)
        self.assertEqual(
            items[1].url,
            "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000122/0001045810-26-000122-index.htm",
        )
        self.assertIn("Quarterly report", items[1].summary or "")

    @patch("news_collector.sources.sec_filings.http_get_json_with_headers")
    def test_fetch_skips_unknown_ticker(self, mock_get_json) -> None:
        """測試 test fetch skips unknown ticker 的預期行為。"""
        mock_get_json.return_value = {
            "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        }
        source = SecFilingsSource(
            user_agent="news-collector/0.1 local-admin@example.com",
            tracked_tickers=["TSM"],
            allowed_forms=["8-K"],
            timeout_seconds=3,
            max_filings_per_company=5,
        )

        items = source.fetch(limit=10)

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
