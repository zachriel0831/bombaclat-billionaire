from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_relay.macro_calendar import (
    MacroCalendarConfig,
    build_retail_release,
    parse_bls_schedule_html,
    parse_census_retail_schedule_html,
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
