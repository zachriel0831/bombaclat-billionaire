"""Justice public-record source tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from news_platform.public_sources.justice_public_records import (
    MojProsecutionDispositionStatsSource,
    MojacDailyCustodyStatsSource,
    parse_moj_prosecution_disposition_csv,
    parse_mojac_daily_custody_xml,
    parse_roc_date,
)


PROSECUTION_CSV = """偵查終結情形,性別,民國年,月份,人
起訴,男性,115,03,22159
起訴,女性,115,03,5880
起訴,法人,115,03,157
緩起訴處分,男性,115,03,2994
緩起訴處分,女性,115,03,783
緩起訴處分,法人,115,03,66
不起訴處分,男性,115,03,20871
不起訴處分,女性,115,03,9248
不起訴處分,法人,115,03,95
其他,男性,115,03,10098
其他,女性,115,03,3026
其他,法人,115,03,29
"""

DAILY_CUSTODY_XML = """<?xml version="1.0" standalone="yes"?>
<NewDataSet>
  <Table>
    <日期>115/05/13</日期>
    <實際收容>63931</實際收容>
    <男>56958</男>
    <女>6973</女>
    <核定容額>60552</核定容額>
    <超收率>5.58%</超收率>
    <入監人數>191</入監人數>
    <出監人數>161</出監人數>
  </Table>
</NewDataSet>
"""


class JusticePublicRecordTests(unittest.TestCase):
    def test_parse_roc_date(self):
        self.assertEqual(parse_roc_date("115/05/13").isoformat(), "2026-05-13T23:59:59+08:00")

    def test_prosecution_disposition_csv_aggregates_monthly_people(self):
        records = parse_moj_prosecution_disposition_csv(PROSECUTION_CSV.encode("utf-8-sig"))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.record_type, "moj_prosecution_disposition_stat")
        self.assertEqual(record.source_id, "moj")
        self.assertEqual(record.metrics["year"], 2026)
        self.assertEqual(record.metrics["month"], 3)
        self.assertEqual(record.metrics["terminated_person_count"], 75406)
        self.assertEqual(record.metrics["prosecution_person_count"], 28196)
        self.assertEqual(record.metrics["deferred_prosecution_person_count"], 3843)
        self.assertEqual(record.metrics["non_prosecution_person_count"], 30214)
        self.assertEqual(record.metrics["other_person_count"], 13153)
        self.assertEqual(record.metrics["legal_entity_count"], 347)
        self.assertIn("judicial_burden", record.tags)
        self.assertIn("judicial_injustice", record.tags)

    def test_daily_custody_xml_maps_capacity_metrics(self):
        records = parse_mojac_daily_custody_xml(DAILY_CUSTODY_XML.encode("utf-8"))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source_id, "mojac")
        self.assertEqual(record.record_type, "mojac_daily_custody_stat")
        self.assertEqual(record.metrics["actual_custody_count"], 63931)
        self.assertEqual(record.metrics["approved_capacity_count"], 60552)
        self.assertEqual(record.metrics["over_capacity_count"], 3379)
        self.assertEqual(record.metrics["over_capacity_rate"], 0.0558)
        self.assertEqual(record.metrics["intake_count"], 191)
        self.assertEqual(record.metrics["release_count"], 161)

    def test_sources_fetch_and_apply_limit(self):
        with patch(
            "news_platform.public_sources.justice_public_records._http_get_bytes_with_ski_fallback",
            return_value=PROSECUTION_CSV.encode("utf-8-sig"),
        ):
            prosecution_records = MojProsecutionDispositionStatsSource().fetch(limit=1)
        with patch(
            "news_platform.public_sources.justice_public_records._http_get_bytes_with_ski_fallback",
            return_value=DAILY_CUSTODY_XML.encode("utf-8"),
        ):
            custody_records = MojacDailyCustodyStatsSource().fetch(limit=1)

        self.assertEqual(len(prosecution_records), 1)
        self.assertEqual(len(custody_records), 1)


if __name__ == "__main__":
    unittest.main()
