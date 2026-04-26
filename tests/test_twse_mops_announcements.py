import unittest
from unittest.mock import patch

from news_collector.sources.twse_mops_announcements import TwseMopsAnnouncementsSource, _normalize_code, _parse_roc_datetime


class TwseMopsAnnouncementsTests(unittest.TestCase):
    """封裝 Twse Mops Announcements Tests 相關資料與行為。"""
    def test_normalize_code(self) -> None:
        """測試 test normalize code 的預期行為。"""
        self.assertEqual(_normalize_code("2330"), "2330")
        self.assertIsNone(_normalize_code("TSM"))

    def test_parse_roc_datetime(self) -> None:
        """測試 test parse roc datetime 的預期行為。"""
        value = _parse_roc_datetime("1150418", "70003")
        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value.isoformat(), "2026-04-18T07:00:03+08:00")

    @patch("news_collector.sources.twse_mops_announcements.http_get_json")
    def test_fetch_filters_by_tracked_codes(self, mock_get_json) -> None:
        """測試 test fetch filters by tracked codes 的預期行為。"""
        mock_get_json.return_value = {
            "data": [
                {
                    "出表日期": "1150419",
                    "發言日期": "1150418",
                    "發言時間": "70003",
                    "公司代號": "2330",
                    "公司名稱": "台積電",
                    "主旨 ": "公告董事會通過第一季財報",
                    "符合條款": "第31款",
                    "事實發生日": "1150418",
                    "說明": "董事會決議通過第一季財報。",
                },
                {
                    "出表日期": "1150419",
                    "發言日期": "1150418",
                    "發言時間": "112625",
                    "公司代號": "1101",
                    "公司名稱": "台泥",
                    "主旨 ": "公告其他事項",
                    "符合條款": "第51款",
                    "事實發生日": "1150418",
                    "說明": "其他說明。",
                },
            ]
        }

        source = TwseMopsAnnouncementsSource(
            tracked_codes=["2330", "2317"],
            timeout_seconds=3,
            max_items_per_company=5,
        )

        items = source.fetch(limit=10)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "twse_mops:2330")
        self.assertIn("2330", items[0].title)
        self.assertIn("第31款", items[0].summary or "")
        self.assertEqual(
            items[0].url,
            "https://openapi.twse.com.tw/v1/opendata/t187ap04_L#code=2330&date=1150418&time=70003",
        )

    @patch("news_collector.sources.twse_mops_announcements.http_get_json")
    def test_fetch_limits_items_per_company(self, mock_get_json) -> None:
        """測試 test fetch limits items per company 的預期行為。"""
        mock_get_json.return_value = {
            "data": [
                {
                    "出表日期": "1150419",
                    "發言日期": "1150418",
                    "發言時間": "130000",
                    "公司代號": "2330",
                    "公司名稱": "台積電",
                    "主旨 ": "A",
                    "符合條款": "第31款",
                    "說明": "A",
                },
                {
                    "出表日期": "1150419",
                    "發言日期": "1150418",
                    "發言時間": "120000",
                    "公司代號": "2330",
                    "公司名稱": "台積電",
                    "主旨 ": "B",
                    "符合條款": "第31款",
                    "說明": "B",
                },
            ]
        }

        source = TwseMopsAnnouncementsSource(
            tracked_codes=["2330"],
            timeout_seconds=3,
            max_items_per_company=1,
        )

        items = source.fetch(limit=10)

        self.assertEqual(len(items), 1)
        self.assertIn("A", items[0].title)

    @patch("news_collector.sources.twse_mops_announcements.http_get_json")
    def test_fetch_retries_once_on_transient_error(self, mock_get_json) -> None:
        """測試 test fetch retries once on transient error 的預期行為。"""
        mock_get_json.side_effect = [
            RuntimeError("temporary ssl error"),
            {
                "data": [
                    {
                        "出表日期": "1150419",
                        "發言日期": "1150418",
                        "發言時間": "70003",
                        "公司代號": "2330",
                        "公司名稱": "台積電",
                        "主旨 ": "公告董事會通過第一季財報",
                        "符合條款": "第31款",
                        "說明": "董事會決議通過第一季財報。",
                    }
                ]
            },
        ]

        source = TwseMopsAnnouncementsSource(
            tracked_codes=["2330"],
            timeout_seconds=3,
            max_items_per_company=5,
        )

        items = source.fetch(limit=10)

        self.assertEqual(len(items), 1)
        self.assertEqual(mock_get_json.call_count, 2)


if __name__ == "__main__":
    unittest.main()
