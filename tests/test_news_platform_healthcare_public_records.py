"""Healthcare public-record source tests."""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from datetime import datetime, timezone

from news_platform.models import PublicRecord
from news_platform.public_sources.healthcare_public_records import (
    HOSPITAL_WORKFORCE_SPEC,
    county_from_township,
    healthcare_bill_record_from_base,
    matched_healthcare_bill_terms,
    parse_mohw_annual_zip,
    parse_mohw_nursing_staff_csv,
    parse_nhi_bed_occupancy_ods,
    parse_nhi_hospital_nursing_staff_csv,
    parse_roc_year_month,
)


NHI_NURSING_CSV = """統計年月,分區別,縣市別,醫事機構代碼,醫事機構簡稱,當月執業登記人數,當月報備支援人數
11504,北區業務組,新竹市,0412040012,臺大新竹,969,10
11504,北區業務組,新竹市,0421040011,成大醫院,20,2
11504,臺北業務組,臺北市,0401180014,台大醫院,3000,0
"""


MOHW_NURSING_CSV = """年度,護理人員領證人數(累計),護理人員領證人數(累計)男性,護理人員領證人數(累計)女性,每萬人口護理人員數(人)
2018,285326,7070,278256,71.84
"""


class HealthcarePublicRecordsTests(unittest.TestCase):
    def test_nhi_nursing_staff_csv_aggregates_by_month_and_area(self):
        records = parse_nhi_hospital_nursing_staff_csv(NHI_NURSING_CSV)

        self.assertEqual(len(records), 2)
        hsinchu = next(record for record in records if record.region == "新竹市")
        self.assertEqual(hsinchu.record_type, "nhi_hospital_nursing_staff_stat")
        self.assertEqual(hsinchu.metrics["hospital_count"], 2)
        self.assertEqual(hsinchu.metrics["practicing_nurse_count"], 989)
        self.assertEqual(hsinchu.metrics["support_nurse_count"], 12)
        self.assertIn("healthcare_burden", hsinchu.tags)
        self.assertEqual(hsinchu.occurred_at.isoformat(), "2026-04-30T23:59:59+08:00")

    def test_nhi_bed_occupancy_ods_maps_hospital_rows(self):
        records = parse_nhi_bed_occupancy_ods(_ods_bytes())

        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first.record_type, "nhi_hospital_bed_occupancy_stat")
        self.assertEqual(first.metrics["year"], 2024)
        self.assertEqual(first.metrics["contract_type"], "醫學中心")
        self.assertEqual(first.metrics["acute_general_bed_occupancy_rate"], 0.8709)
        self.assertEqual(first.raw["hospital_id"], "0401180014")

    def test_mohw_annual_zip_aggregates_by_county(self):
        records = parse_mohw_annual_zip(
            _mohw_annual_zip_bytes(),
            HOSPITAL_WORKFORCE_SPEC,
            download_url="https://example.test/hos_personnel_113.zip",
        )

        self.assertEqual(len(records), 2)
        taipei = next(record for record in records if record.region == "臺北市")
        self.assertEqual(taipei.record_type, "mohw_hospital_workforce_stat")
        self.assertEqual(taipei.metrics["year"], 2024)
        self.assertEqual(taipei.metrics["facility_count"], 11)
        self.assertEqual(taipei.metrics["medical_staff_count"], 5410)
        self.assertEqual(taipei.metrics["nursing_staff_count"], 3087)
        self.assertEqual(county_from_township("臺北市松山區"), "臺北市")

    def test_mohw_nursing_staff_csv_maps_public_record(self):
        records = parse_mohw_nursing_staff_csv(MOHW_NURSING_CSV.encode("cp950"))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.record_type, "mohw_nursing_staff_stat")
        self.assertEqual(record.metrics["licensed_nursing_staff_count"], 285326)
        self.assertEqual(record.metrics["nursing_staff_per_10000_population"], 71.84)

    def test_healthcare_bill_record_is_topic_specific_copy(self):
        base = PublicRecord(
            record_id="ly:legislative_bill:abc",
            source_id="ly",
            record_type="legislative_bill",
            country="TW",
            category="politics",
            title="護理人員法部分條文修正草案",
            url="https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx",
            occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            region="TW",
            metrics={"term": 11},
            tags=["legislative_bill"],
            raw={"billName": "護理人員法部分條文修正草案"},
        )

        terms = matched_healthcare_bill_terms(base)
        record = healthcare_bill_record_from_base(base, terms)

        self.assertEqual(terms, ["護理人員法"])
        self.assertEqual(record.record_type, "healthcare_legislative_bill")
        self.assertEqual(record.category, "society")
        self.assertIn("healthcare_burden", record.tags)
        self.assertEqual(record.raw["base_record_type"], "legislative_bill")

    def test_roc_year_month_helper(self):
        self.assertEqual(parse_roc_year_month("11504"), (2026, 4))


def _ods_bytes() -> bytes:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
 <office:body><office:spreadsheet><table:table table:name="Sheet1">
  <table:table-row><table:table-cell><text:p>113年特約醫院四類病床年平均占床率</text:p></table:table-cell></table:table-row>
  <table:table-row>
   <table:table-cell><text:p>特約類別</text:p></table:table-cell>
   <table:table-cell><text:p>醫事機構代碼</text:p></table:table-cell>
   <table:table-cell><text:p>服務機構簡稱</text:p></table:table-cell>
   <table:table-cell><text:p>急性一般病床</text:p></table:table-cell>
   <table:table-cell><text:p>急性精神病床</text:p></table:table-cell>
   <table:table-cell><text:p>慢性一般病床</text:p></table:table-cell>
   <table:table-cell><text:p>慢性精神科病床</text:p></table:table-cell>
  </table:table-row>
  <table:table-row>
   <table:table-cell><text:p>醫學中心</text:p></table:table-cell>
   <table:table-cell><text:p>0401180014</text:p></table:table-cell>
   <table:table-cell><text:p>台大醫院</text:p></table:table-cell>
   <table:table-cell><text:p>87.09%</text:p></table:table-cell>
   <table:table-cell><text:p>91.10%</text:p></table:table-cell>
   <table:table-cell/><table:table-cell/>
  </table:table-row>
  <table:table-row>
   <table:table-cell><text:p>0412040012</text:p></table:table-cell>
   <table:table-cell><text:p>臺大新竹</text:p></table:table-cell>
   <table:table-cell><text:p>61.93%</text:p></table:table-cell>
   <table:table-cell><text:p>39.08%</text:p></table:table-cell>
   <table:table-cell/><table:table-cell/>
  </table:table-row>
 </table:table></office:spreadsheet></office:body>
</office:document-content>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("content.xml", content)
    return buffer.getvalue()


def _mohw_annual_zip_bytes() -> bytes:
    data = """鄉鎮市區碼,醫院家數,醫事人員總計,西醫師,中醫師,牙醫師,藥師,護理師,護士
101,5,2020,325,12,78,98,1091,96
102,6,3390,724,0,47,159,1808,92
701,1,100,20,0,5,4,50,5
"""
    mapping = """鄉鎮市區碼,鄉鎮市區名稱(101、102年適用),鄉鎮市區名稱(103年以後適用)
101,臺北市松山區,臺北市松山區
102,臺北市大安區,臺北市大安區
701,高雄市鳳山區,高雄市鳳山區
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hos_personnel_113.csv", data)
        archive.writestr("欄位說明.csv", mapping)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
