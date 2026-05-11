"""Legislative Yuan public-record source tests."""

from __future__ import annotations

import json
import unittest
from datetime import date
from unittest.mock import patch

from news_platform.public_sources.ly_legislative_bill import (
    LegislativeBillSource,
    parse_legislative_bill_payload,
    parse_roc_date,
    row_to_public_record,
    split_names,
    to_roc_date,
)


ROWS = [
    {
        "date": "1150508",
        "term": "11",
        "sessionPeriod": "05",
        "sessionTimes": "09",
        "billName": "個人資料保護法第二條及第六條條文修正草案",
        "billProposer": "鄭正鈐",
        "billCosignatory": "陳玉珍 ; 王鴻薇 ; 翁曉玲",
        "billStatus": "",
    }
]


class LegislativeBillSourceTests(unittest.TestCase):
    def test_roc_date_helpers(self):
        self.assertEqual(to_roc_date(date(2026, 5, 11)), "1150511")
        self.assertEqual(parse_roc_date("1150508").isoformat(), "2026-05-08T00:00:00+08:00")

    def test_parse_payload_accepts_list(self):
        rows = parse_legislative_bill_payload(json.dumps(ROWS, ensure_ascii=False))

        self.assertEqual(rows[0]["billName"], ROWS[0]["billName"])

    def test_row_to_public_record_maps_fields(self):
        record = row_to_public_record(ROWS[0], params={"from": "1150501", "to": "1150511"})

        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.record_id.startswith("ly:legislative_bill:"))
        self.assertEqual(record.source_id, "ly")
        self.assertEqual(record.record_type, "legislative_bill")
        self.assertEqual(record.category, "politics")
        self.assertEqual(record.title, ROWS[0]["billName"])
        self.assertEqual(record.metrics["term"], 11)
        self.assertEqual(record.metrics["session_period"], 5)
        self.assertEqual(record.metrics["cosignatory_count"], 3)
        self.assertEqual(record.raw["proposers"], ["鄭正鈐"])
        self.assertEqual(record.raw["cosignatories"], ["陳玉珍", "王鴻薇", "翁曉玲"])

    def test_fetch_uses_roc_date_params_and_limit(self):
        source = LegislativeBillSource(timeout_seconds=5, lookback_days=3)
        with patch(
            "news_platform.public_sources.ly_legislative_bill.http_get_text",
            return_value=json.dumps(ROWS, ensure_ascii=False),
        ) as get:
            records = source.fetch(from_date=date(2026, 5, 1), to_date=date(2026, 5, 11), limit=1)

        self.assertEqual(len(records), 1)
        _, kwargs = get.call_args
        self.assertEqual(kwargs["params"]["from"], "1150501")
        self.assertEqual(kwargs["params"]["to"], "1150511")
        self.assertEqual(kwargs["params"]["mode"], "json")
        self.assertFalse(kwargs["verify_ssl"])

    def test_split_names_trims_semicolon_rows(self):
        self.assertEqual(split_names("陳玉珍 ; 王鴻薇   ; "), ["陳玉珍", "王鴻薇"])


if __name__ == "__main__":
    unittest.main()
