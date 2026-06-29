"""Housing public-record source tests."""

from __future__ import annotations

import unittest

from news_platform.public_sources.housing_public_records import parse_taipei_housing_price_index_csv


CSV = """住宅價格月指數類別,期別,月指數,季移動平均數,半年移動平均數,月指數變動率,季移動平均數變動率,半年移動平均數變動率,標準住宅總價（新台幣萬元）,標準住宅單價（新台幣萬元每坪）
全市,115/05,132.45,131.20,129.90,1.25%,0.8%,0.6%,2150,68.47
"""


class HousingPublicRecordsTests(unittest.TestCase):
    def test_taipei_housing_price_index_csv_maps_record(self):
        records = parse_taipei_housing_price_index_csv(CSV)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.record_type, "taipei_housing_price_index")
        self.assertEqual(record.source_id, "taipei_open_data")
        self.assertEqual(record.category, "society")
        self.assertEqual(record.region, "台北市")
        self.assertIn("housing_justice", record.tags)
        self.assertEqual(record.metrics["year"], 2026)
        self.assertEqual(record.metrics["month"], 5)
        self.assertEqual(record.metrics["monthly_index"], 132.45)
        self.assertEqual(record.metrics["monthly_index_change_rate"], 0.0125)
        self.assertEqual(record.metrics["standard_total_price_10k_twd"], 2150.0)
        self.assertIn("2026-05 台北市全市住宅價格月指數", record.title)


if __name__ == "__main__":
    unittest.main()
