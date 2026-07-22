from __future__ import annotations

import unittest

from news_platform.public_sources.cwa_disaster_public_records import (
    parse_earthquake_payload,
    parse_typhoon_payload,
)


class CwaDisasterPublicRecordsTest(unittest.TestCase):
    def test_parse_earthquake_payload(self) -> None:
        payload = {
            "records": {
                "Earthquake": [
                    {
                        "EarthquakeNo": "114001",
                        "ReportContent": "07/05 16:03 花蓮近海發生有感地震。",
                        "Web": "https://example.test/earthquake",
                        "EarthquakeInfo": {
                            "OriginTime": "2026-07-05 16:03:30",
                            "FocalDepth": "12.5",
                            "Epicenter": {
                                "Location": "花蓮縣近海",
                                "EpicenterLatitude": "23.9",
                                "EpicenterLongitude": "121.7",
                            },
                            "EarthquakeMagnitude": {
                                "MagnitudeValue": "5.2",
                            },
                        },
                    }
                ]
            }
        }

        records = parse_earthquake_payload(payload, dataset_id="E-A0015-001")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.record_id, "cwa:earthquake:114001")
        self.assertEqual(record.record_type, "cwa_earthquake_report")
        self.assertEqual(record.region, "花蓮縣近海")
        self.assertEqual(record.metrics["magnitude"], 5.2)
        self.assertEqual(record.metrics["depth_km"], 12.5)
        self.assertIn("earthquake", record.tags)

    def test_parse_typhoon_payload(self) -> None:
        payload = {
            "records": {
                "Typhoon": [
                    {
                        "TyphoonName": "丹娜絲颱風",
                        "ReportTime": "2026-07-06 08:00",
                        "SeaArea": "臺灣東方海面",
                        "Web": "https://example.test/typhoon",
                    }
                ]
            }
        }

        records = parse_typhoon_payload(payload, dataset_id="W-C0034-005")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertTrue(record.record_id.startswith("cwa:typhoon:"))
        self.assertEqual(record.title, "丹娜絲颱風")
        self.assertEqual(record.record_type, "cwa_typhoon_report")
        self.assertEqual(record.region, "臺灣東方海面")
        self.assertIn("typhoon", record.tags)

    def test_parse_tropical_depression_payload(self) -> None:
        payload = {
            "records": {
                "TropicalCyclones": {
                    "TropicalCyclone": [
                        {
                            "Year": "2026",
                            "CwaTdNo": "13",
                            "AnalysisData": {
                                "Fix": [
                                    {
                                        "DateTime": "2026-07-22T14:00:00+08:00",
                                        "CoordinateLongitude": "132.6",
                                        "CoordinateLatitude": "14.2",
                                    }
                                ]
                            },
                            "ForecastData": {"Fix": []},
                        }
                    ]
                }
            }
        }

        records = parse_typhoon_payload(payload, dataset_id="W-C0034-005")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.title, "熱帶性低氣壓 TD13")
        self.assertEqual(record.record_type, "cwa_typhoon_report")
        self.assertIn("typhoon", record.tags)


if __name__ == "__main__":
    unittest.main()
