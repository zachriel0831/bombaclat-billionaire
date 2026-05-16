"""NPA public-record source tests."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from news_platform.public_sources.npa_public_records import (
    NpaDrunkDrivingStatsSource,
    NpaFraudBlockedDomainStatsSource,
    NpaFraudEnforcementStatsSource,
    NpaFraudRumorSource,
    NpaTrafficAccidentA1Source,
    NpaTrafficAccidentA2StatsSource,
    fraud_rumor_row_to_record,
    parse_casualties,
    parse_drunk_driving_stats_csv,
    parse_fraud_blocked_domain_stats_csv,
    parse_fraud_enforcement_stats_csv,
    parse_fraud_rumor_csv,
    parse_npa_datetime,
    parse_traffic_a1_payload,
    parse_traffic_a2_zip_stats,
    parse_traffic_datetime,
    region_from_location,
)


FRAUD_CSV = """編號,標題,發佈時間,發佈內容
89,公布114年第一季網路廣告平臺業者 刊登違法投資廣告態樣,2025/04/26 09:00,刑事警察局通報下架詐騙廣告
"""

TRAFFIC_JSON = {
    "success": True,
    "result": {
        "records": [
            {
                "發生日期": "20260101",
                "發生時間": "053700",
                "事故類別名稱": "A1",
                "處理單位名稱警局層": "新北市政府警察局",
                "發生地點": "新北市淡水區中正路 / 新北市淡水區真理街",
                "死亡受傷人數": "死亡1;受傷0",
                "當事者順位": "1",
                "肇因研判子類別名稱-主要": "酒醉(後)駕駛",
                "經度": "121.433604",
                "緯度": "25.174412",
            },
            {
                "發生日期": "20260101",
                "發生時間": "053700",
                "事故類別名稱": "A1",
                "發生地點": "新北市淡水區中正路 / 新北市淡水區真理街",
                "死亡受傷人數": "死亡1;受傷0",
                "當事者順位": "2",
            },
        ]
    },
}

DRUNK_CSV = """year,A1-count,A2-count,dead,A1-hurt,A2-hurt
時間別,A1件數,A2件數,死亡人數,A1受傷人數,A2受傷人數
114年,10,200,12,3,250
"""

FRAUD_DASHBOARD_CSV = """年度,月,查緝不法犯罪集團團數,查緝不法犯罪集團人數,查扣不法所得金額,攔阻金額
114,9,353,2999,489284922,1319925538
"""

FRAUD_BLOCKED_CSV = """民國年月,網域,網站性質,法律依據,聲請單位
11505,example-scam.test,金融保險,詐欺犯罪危害防制條例,刑事警察局詐欺犯罪防制中心
11505,shop-scam.test,電子商務,詐欺犯罪危害防制條例,刑事警察局詐欺犯罪防制中心
11505,another-scam.test,金融保險,詐欺犯罪危害防制條例,刑事警察局詐欺犯罪防制中心
"""


class NpaPublicRecordTests(unittest.TestCase):
    def test_parse_npa_datetime(self):
        self.assertEqual(parse_npa_datetime("2025/04/26 09:00").isoformat(), "2025-04-26T09:00:00+08:00")
        self.assertEqual(parse_traffic_datetime("20260101", "053700").isoformat(), "2026-01-01T05:37:00+08:00")

    def test_fraud_rumor_row_maps_public_record(self):
        rows = parse_fraud_rumor_csv(FRAUD_CSV)

        self.assertEqual(len(rows), 1)
        record = rows[0]
        self.assertTrue(record.record_id.startswith("npa:fraud_rumor:"))
        self.assertEqual(record.source_id, "npa")
        self.assertEqual(record.record_type, "fraud_rumor")
        self.assertEqual(record.category, "society")
        self.assertIn("違法投資廣告", record.title)
        self.assertEqual(record.raw["serial"], "89")

    def test_fraud_rumor_row_without_title_is_skipped(self):
        self.assertIsNone(fraud_rumor_row_to_record({"編號": "1", "標題": ""}))

    def test_traffic_a1_payload_groups_party_rows(self):
        records = parse_traffic_a1_payload(json.dumps(TRAFFIC_JSON, ensure_ascii=False))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertTrue(record.record_id.startswith("npa:traffic_accident_a1:"))
        self.assertEqual(record.record_type, "traffic_accident_a1")
        self.assertEqual(record.region, "新北市")
        self.assertEqual(record.metrics["death_count"], 1)
        self.assertEqual(record.metrics["injury_count"], 0)
        self.assertEqual(record.metrics["party_count"], 2)
        self.assertEqual(record.metrics["latitude"], 25.174412)
        self.assertEqual(record.raw["main_cause"], "酒醉(後)駕駛")

    def test_traffic_helpers(self):
        self.assertEqual(parse_casualties("死亡2;受傷10"), (2, 10))
        self.assertEqual(region_from_location("高雄市前鎮區中山路"), "高雄市")

    def test_traffic_a2_zip_maps_monthly_region_stats(self):
        import io
        import zipfile

        payload = dict(TRAFFIC_JSON)
        payload["result"] = {
            "records": [
                {
                    "發生日期": "20260501",
                    "發生時間": "000500",
                    "事故類別名稱": "A2",
                    "發生地點": "高雄市大寮區三隆路",
                    "死亡受傷人數": "死亡0;受傷1",
                    "肇因研判子類別名稱-主要": "其他不當駕車行為",
                    "當事者順位": "1",
                },
                {
                    "發生日期": "20260501",
                    "發生時間": "000500",
                    "事故類別名稱": "A2",
                    "發生地點": "高雄市大寮區三隆路",
                    "死亡受傷人數": "死亡0;受傷1",
                    "當事者順位": "2",
                },
            ]
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("NPA_TMA2_JSON_5.json", json.dumps(payload, ensure_ascii=False))

        records = parse_traffic_a2_zip_stats(buffer.getvalue())

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_type, "traffic_accident_a2_stat")
        self.assertEqual(records[0].region, "高雄市")
        self.assertEqual(records[0].metrics["accident_count"], 1)
        self.assertEqual(records[0].metrics["injury_count"], 1)
        self.assertEqual(records[0].metrics["party_count"], 2)

    def test_stat_csv_sources_map_record_types(self):
        drunk = parse_drunk_driving_stats_csv(DRUNK_CSV)
        fraud_dashboard = parse_fraud_enforcement_stats_csv(FRAUD_DASHBOARD_CSV)
        blocked = parse_fraud_blocked_domain_stats_csv(FRAUD_BLOCKED_CSV)

        self.assertEqual(drunk[0].record_type, "traffic_drunk_driving_stat")
        self.assertEqual(drunk[0].metrics["total_accident_count"], 210)
        self.assertEqual(fraud_dashboard[0].record_type, "fraud_enforcement_stat")
        self.assertEqual(fraud_dashboard[0].metrics["blocked_amount"], 1319925538)
        self.assertEqual(len(blocked), 2)
        finance = next(record for record in blocked if "金融保險" in record.title)
        self.assertEqual(finance.record_type, "fraud_blocked_domain_stat")
        self.assertEqual(finance.metrics["blocked_domain_count"], 2)

    def test_sources_fetch_and_apply_limit(self):
        with patch("news_platform.public_sources.npa_public_records.http_get_text", return_value=FRAUD_CSV):
            fraud_records = NpaFraudRumorSource().fetch(limit=1)
        with patch(
            "news_platform.public_sources.npa_public_records.http_get_text",
            return_value=json.dumps(TRAFFIC_JSON, ensure_ascii=False),
        ):
            traffic_records = NpaTrafficAccidentA1Source().fetch(limit=1)
        with patch(
            "news_platform.public_sources.npa_public_records._http_get_bytes_with_ski_fallback",
            return_value=_zip_json_bytes(TRAFFIC_JSON),
        ):
            a2_records = NpaTrafficAccidentA2StatsSource().fetch(limit=1)
        with patch("news_platform.public_sources.npa_public_records.http_get_text", return_value=DRUNK_CSV):
            drunk_records = NpaDrunkDrivingStatsSource().fetch(limit=1)
        with patch("news_platform.public_sources.npa_public_records.http_get_text", return_value=FRAUD_DASHBOARD_CSV):
            enforcement_records = NpaFraudEnforcementStatsSource().fetch(limit=1)
        with patch("news_platform.public_sources.npa_public_records.http_get_text", return_value=FRAUD_BLOCKED_CSV):
            blocked_records = NpaFraudBlockedDomainStatsSource().fetch(limit=1)

        self.assertEqual(len(fraud_records), 1)
        self.assertEqual(len(traffic_records), 1)
        self.assertEqual(len(a2_records), 1)
        self.assertEqual(len(drunk_records), 1)
        self.assertEqual(len(enforcement_records), 1)
        self.assertEqual(len(blocked_records), 1)


def _zip_json_bytes(payload: dict) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("NPA_TMA2_JSON_1.json", json.dumps(payload, ensure_ascii=False))
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
