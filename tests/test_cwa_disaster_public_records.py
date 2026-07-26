from __future__ import annotations

import unittest
from datetime import timezone
from unittest.mock import patch

from news_platform.public_sources.cwa_disaster_public_records import (
    CwaEarthquakeReportSource,
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

    def test_parse_earthquake_payload_accepts_iso_origin_time(self) -> None:
        payload = {
            "records": {
                "Earthquake": [
                    {
                        "EarthquakeNo": "115051",
                        "ReportContent": "07/26-20:36新北市雙溪區發生規模5.6有感地震。",
                        "EarthquakeInfo": {
                            "OriginTime": "2026-07-26T20:36:17+08:00",
                            "FocalDepth": 95.7,
                            "Epicenter": {
                                "Location": "新北市政府東南東方 35.8 公里 (位於新北市雙溪區)",
                                "EpicenterLatitude": 24.91,
                                "EpicenterLongitude": 121.8,
                            },
                            "EarthquakeMagnitude": {"MagnitudeValue": 5.6},
                        },
                    }
                ]
            }
        }

        records = parse_earthquake_payload(payload, dataset_id="E-A0015-001")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].occurred_at.astimezone(timezone.utc).isoformat(), "2026-07-26T12:36:17+00:00")

    def test_parse_small_area_earthquake_uses_dataset_scoped_id(self) -> None:
        payload = {
            "records": {
                "Earthquake": [
                    {
                        "EarthquakeNo": "115099",
                        "ReportContent": "小區域有感地震報告",
                        "EarthquakeInfo": {
                            "OriginTime": "2026-07-26T20:36:17+08:00",
                            "Epicenter": {"Location": "新北市雙溪區"},
                            "EarthquakeMagnitude": {"MagnitudeValue": 4.6},
                        },
                    }
                ]
            }
        }

        records = parse_earthquake_payload(payload, dataset_id="E-A0016-001")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_id, "cwa:earthquake:E-A0016-001:115099")
        self.assertEqual(records[0].metrics["magnitude"], 4.6)

    def test_earthquake_source_fetches_significant_and_small_area_datasets(self) -> None:
        payloads = {
            "E-A0015-001": {
                "records": {
                    "Earthquake": [
                        {
                            "EarthquakeNo": "115001",
                            "ReportContent": "顯著有感地震報告",
                            "EarthquakeInfo": {
                                "OriginTime": "2026-07-26T20:30:00+08:00",
                                "EarthquakeMagnitude": {"MagnitudeValue": 5.1},
                            },
                        }
                    ]
                }
            },
            "E-A0016-001": {
                "records": {
                    "Earthquake": [
                        {
                            "EarthquakeNo": "115002",
                            "ReportContent": "小區域有感地震報告",
                            "EarthquakeInfo": {
                                "OriginTime": "2026-07-26T20:36:00+08:00",
                                "EarthquakeMagnitude": {"MagnitudeValue": 4.6},
                            },
                        }
                    ]
                }
            },
        }

        with patch(
            "news_platform.public_sources.cwa_disaster_public_records._fetch_cwa_json",
            side_effect=lambda dataset_id, **_: payloads[dataset_id],
        ) as fetch:
            records = CwaEarthquakeReportSource(authorization="test-token").fetch(limit=5)

        self.assertEqual(fetch.call_count, 2)
        self.assertEqual([record.record_id for record in records], [
            "cwa:earthquake:E-A0016-001:115002",
            "cwa:earthquake:115001",
        ])

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
