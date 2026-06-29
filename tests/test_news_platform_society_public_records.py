"""Society public-record source tests."""

from __future__ import annotations

import unittest

from news_platform.public_sources.society_public_records import (
    birth_month_rows_to_records,
    parse_npa_drug_case_csv,
)


BIRTH_ROWS = [
    {
        "statistic_yyymm": "11505",
        "site_id": "新北市板橋區",
        "birth_total": "2",
        "birth_total_m": "1",
        "birth_total_f": "1",
        "death_total": "3",
        "death_m": "2",
        "death_f": "1",
        "marry_pair": "4",
        "divorce_pair": "1",
    },
    {
        "statistic_yyymm": "11505",
        "site_id": "臺北市中正區",
        "birth_total": "5",
        "birth_total_m": "3",
        "birth_total_f": "2",
        "death_total": "1",
        "death_m": "1",
        "death_f": "0",
        "marry_pair": "2",
        "divorce_pair": "0",
    },
]

DRUG_CSV = """no,type,oc_dt,oc_addr,oc_p1,oc_p2,oc_p3,proc_no,kind,weight_g
編號,案類,發生日期,發生地點,發生場所一,發生場所二,發生場所三,嫌疑犯人數,毒品品項,數量（淨重）_克
1,毒品,20260115,臺東縣臺東市,公路, , ,1,依托咪酯,1
2,毒品,20260118,臺東縣臺東市,學校, , ,2,安非他命,0.4
3,毒品,20260106,桃園市蘆竹區,普通住宅, , ,1,安非他命,0
"""


class SocietyPublicRecordTests(unittest.TestCase):
    def test_birth_rows_aggregate_by_region_and_national_total(self):
        records = birth_month_rows_to_records(BIRTH_ROWS, dataset_url="https://example.com/birth")

        self.assertEqual({record.region for record in records}, {"新北市", "臺北市", "全國"})
        national = next(record for record in records if record.region == "全國")
        self.assertEqual(national.record_type, "ris_birth_monthly_stat")
        self.assertEqual(national.metrics["birth_total"], 7)
        self.assertIn("low_birthrate", national.tags)

    def test_drug_csv_aggregates_monthly_region_stats(self):
        records = parse_npa_drug_case_csv(DRUG_CSV, download_url="https://example.com/drug.csv")

        self.assertEqual({record.region for record in records}, {"臺東縣", "桃園市"})
        taitung = next(record for record in records if record.region == "臺東縣")
        self.assertEqual(taitung.record_type, "npa_drug_case_stat")
        self.assertEqual(taitung.metrics["case_count"], 2)
        self.assertEqual(taitung.metrics["suspect_count"], 3)
        self.assertEqual(taitung.metrics["school_case_count"], 1)
        self.assertIn("drug_abuse", taitung.tags)


if __name__ == "__main__":
    unittest.main()
