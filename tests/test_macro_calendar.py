from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_relay.macro_calendar import (
    EarningsSymbolSpec,
    MacroCalendarConfig,
    build_manual_earnings_release,
    build_nasdaq_earnings_release,
    build_retail_release,
    dedupe_releases,
    parse_bls_schedule_html,
    parse_census_retail_schedule_html,
    parse_nasdaq_earnings_payload,
    run_once,
)


BLS_SAMPLE_HTML = """
<html><body>
  <h1>June 2026</h1>
  <table>
    <tr><th>Date</th><th>Time</th><th>Release</th></tr>
    <tr>
      <td>Wednesday, June 10, 2026</td>
      <td>08:30 AM</td>
      <td>Consumer Price Index for May 2026</td>
    </tr>
    <tr>
      <td>Thursday, June 11, 2026</td>
      <td>08:30 AM</td>
      <td>Producer Price Index for May 2026</td>
    </tr>
    <tr>
      <td>Friday, June 12, 2026</td>
      <td>10:00 AM</td>
      <td>Unrelated Release for May 2026</td>
    </tr>
  </table>
  <h1>July 2026</h1>
  <table>
    <tr>
      <td>Thursday, July 2, 2026</td>
      <td>08:30 AM</td>
      <td>Employment Situation for June 2026</td>
    </tr>
  </table>
</body></html>
"""


CENSUS_SAMPLE_HTML = """
<html><body>
  <h2>Advance Monthly Retail Trade Report</h2>
  <table>
    <tr><th>Data Month</th><th>Release Date at 8:30 am</th></tr>
    <tr><td>May 2026</td><td>June 17, 2026</td></tr>
    <tr><td>June 2026</td><td>July 16, 2026</td></tr>
  </table>
  <h2>Monthly Retail Trade Report</h2>
</body></html>
"""


class _FakeStore:
    releases = []

    def __init__(self, _env_file):
        return None

    def initialize(self):
        return None

    def upsert_releases(self, releases):
        _FakeStore.releases.extend(releases)
        return len(releases)

    def close(self):
        return None


class MacroCalendarTests(unittest.TestCase):
    def test_parse_bls_schedule_extracts_selected_releases(self) -> None:
        releases = parse_bls_schedule_html(BLS_SAMPLE_HTML, "https://www.bls.gov/schedule/2026/home.htm")

        self.assertEqual([item.indicator_code for item in releases], ["us_cpi", "us_ppi", "us_nonfarm_payrolls"])
        self.assertEqual(releases[0].period_label, "May 2026")
        self.assertEqual(releases[0].release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"), "2026-06-10 20:30:00")
        self.assertEqual(releases[0].reminder_date_taipei.isoformat(), "2026-06-09")
        self.assertEqual(releases[2].release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-02 20:30:00")

    def test_parse_census_retail_schedule_extracts_releases(self) -> None:
        releases = parse_census_retail_schedule_html(CENSUS_SAMPLE_HTML, "https://www.census.gov/retail/release_schedule.html")

        self.assertEqual(len(releases), 2)
        self.assertEqual(releases[0].indicator_code, "us_retail_sales")
        self.assertEqual(releases[0].period_label, "May 2026")
        self.assertEqual(releases[0].release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"), "2026-06-17 20:30:00")
        self.assertEqual(releases[0].reminder_date_taipei.isoformat(), "2026-06-16")

    def test_retail_release_uses_stable_event_key(self) -> None:
        first = build_retail_release("May 2026", "June 17, 2026", "https://www.census.gov/retail/release_schedule.html")
        second = build_retail_release("May 2026", "June 17, 2026", "https://www.census.gov/retail/release_schedule.html")

        self.assertEqual(first.event_key, second.event_key)
        self.assertEqual(first.release_at_utc, datetime.fromisoformat("2026-06-17T12:30:00+00:00"))

    def test_parse_nasdaq_earnings_payload_extracts_watched_symbols(self) -> None:
        payload = {
            "data": {
                "rows": [
                    {
                        "time": "time-after-hours",
                        "symbol": "NVDA",
                        "name": "NVIDIA Corporation",
                        "marketCap": "$4,000,000,000,000",
                        "fiscalQuarterEnding": "Apr/2026",
                        "epsForecast": "$1.00",
                        "noOfEsts": "38",
                    },
                    {"time": "time-pre-market", "symbol": "SMALL", "name": "Small Co"},
                ]
            }
        }

        releases = parse_nasdaq_earnings_payload(
            payload,
            "https://api.nasdaq.com/api/calendar/earnings?date=2026-08-26",
            datetime.fromisoformat("2026-08-26T00:00:00").date(),
            {"NVDA": EarningsSymbolSpec("NVDA", "NVIDIA", "US", 5)},
        )

        self.assertEqual(len(releases), 1)
        release = releases[0]
        self.assertEqual(release.indicator_code, "earnings_nvda")
        self.assertEqual(release.raw["event_type"], "earnings_release")
        self.assertEqual(release.raw["symbol"], "NVDA")
        self.assertEqual(release.period_label, "Apr/2026")
        self.assertEqual(release.release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-27 04:05:00")
        self.assertEqual(release.reminder_date_taipei.isoformat(), "2026-08-26")

    def test_parse_nasdaq_earnings_payload_ignores_empty_calendar_day(self) -> None:
        releases = parse_nasdaq_earnings_payload(
            {"data": None},
            "https://api.nasdaq.com/api/calendar/earnings?date=2026-06-08",
            datetime.fromisoformat("2026-06-08T00:00:00").date(),
            {"NVDA": EarningsSymbolSpec("NVDA", "NVIDIA", "US", 5)},
        )

        self.assertEqual(releases, [])

    def test_earnings_event_key_is_stable_when_estimated_date_moves(self) -> None:
        spec = EarningsSymbolSpec("NVDA", "NVIDIA", "US", 5)
        row = {"time": "time-after-hours", "symbol": "NVDA", "name": "NVIDIA", "fiscalQuarterEnding": "Apr/2026"}
        first = build_nasdaq_earnings_release(
            row,
            spec,
            datetime.fromisoformat("2026-08-26T00:00:00").date(),
            "https://api.nasdaq.com/api/calendar/earnings?date=2026-08-26",
        )
        second = build_nasdaq_earnings_release(
            row,
            spec,
            datetime.fromisoformat("2026-08-27T00:00:00").date(),
            "https://api.nasdaq.com/api/calendar/earnings?date=2026-08-27",
        )

        self.assertEqual(first.event_key, second.event_key)
        self.assertNotEqual(first.release_at_utc, second.release_at_utc)

    def test_manual_earnings_release_supports_taiwan_time(self) -> None:
        release = build_manual_earnings_release(
            {
                "symbol": "2330",
                "company_name": "台積電",
                "market": "TW",
                "release_date": "2026-07-16",
                "release_time": "14:00",
                "timezone": "Asia/Taipei",
                "time_label": "法說會",
                "period_label": "2026 Q2",
                "source_url": "https://example.test/tsmc",
                "importance": 5,
                "date_status": "confirmed",
            }
        )

        self.assertEqual(release.indicator_code, "earnings_2330")
        self.assertEqual(release.release_at_taipei.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-16 14:00:00")
        self.assertEqual(release.reminder_date_taipei.isoformat(), "2026-07-15")
        self.assertEqual(release.raw["market"], "TW")

    def test_dedupe_prefers_manual_earnings_for_same_symbol_period(self) -> None:
        spec = EarningsSymbolSpec("TSM", "TSMC ADR", "US", 5)
        nasdaq = build_nasdaq_earnings_release(
            {"time": "time-after-hours", "symbol": "TSM", "name": "Taiwan Semiconductor", "fiscalQuarterEnding": "Jun/2026"},
            spec,
            datetime.fromisoformat("2026-07-17T00:00:00").date(),
            "https://api.nasdaq.com/api/calendar/earnings?date=2026-07-17",
        )
        manual = build_manual_earnings_release(
            {
                "symbol": "TSM",
                "company_name": "TSMC ADR",
                "release_date": "2026-07-16",
                "release_time": "04:00",
                "timezone": "America/New_York",
                "period_label": "Jun/2026",
            }
        )

        releases = dedupe_releases([nasdaq, manual])

        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].source_id, "manual_earnings")

    def test_run_once_writes_calendar_rows(self) -> None:
        _FakeStore.releases = []
        config = MacroCalendarConfig(env_file=".env", bls_years=[2026], timeout_seconds=5)
        release = build_retail_release("May 2026", "June 17, 2026", "https://www.census.gov/retail/release_schedule.html")

        with patch("event_relay.macro_calendar.load_settings", return_value=SimpleNamespace(mysql_enabled=True, mysql_macro_calendar_table="t_macro_release_calendar")):
            with patch("event_relay.macro_calendar.collect_macro_release_calendar", return_value=SimpleNamespace(releases=[release], errors=[])):
                with patch("event_relay.macro_calendar.MacroReleaseCalendarStore", _FakeStore):
                    result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["releases"], 1)
        self.assertEqual(result["affected_rows"], 1)
        self.assertEqual(len(_FakeStore.releases), 1)
        self.assertEqual(_FakeStore.releases[0].indicator_code, "us_retail_sales")


if __name__ == "__main__":
    unittest.main()
