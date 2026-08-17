import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace

from data_source_health import (
    NEWS_PLATFORM_CATEGORY_STALE_MINUTES,
    NEWS_PLATFORM_CATEGORY_WARN_MINUTES,
    NEWS_PLATFORM_SOURCE_IDS,
    NEWS_PLATFORM_SOURCE_STALE_MINUTES,
    NEWS_PLATFORM_SOURCE_WARN_MINUTES,
    PUBLIC_RECORD_GROUPS,
    ProbeResult,
    _classify_public_record_link_probe,
    _event_driven_probe,
    _scheduled_slot_probe,
    _us_session_probe,
    classify_freshness,
    overall_status,
    render_text,
)
from data_source_health import HealthReport
from data_source_health import _parse_process_records, _process_count_probe


class DataSourceHealthTests(unittest.TestCase):
    def test_classify_freshness_marks_missing_rows(self) -> None:
        self.assertEqual(
            classify_freshness(row_count=0, age_minutes=None, warn_minutes=60, stale_minutes=120),
            "missing",
        )

    def test_classify_freshness_thresholds(self) -> None:
        self.assertEqual(
            classify_freshness(row_count=1, age_minutes=59, warn_minutes=60, stale_minutes=120),
            "ok",
        )
        self.assertEqual(
            classify_freshness(row_count=1, age_minutes=61, warn_minutes=60, stale_minutes=120),
            "warn",
        )
        self.assertEqual(
            classify_freshness(row_count=1, age_minutes=121, warn_minutes=60, stale_minutes=120),
            "stale",
        )

    def test_overall_status_ignores_skipped_but_keeps_worst_probe(self) -> None:
        probes = [
            ProbeResult(name="a", status="ok"),
            ProbeResult(name="b", status="skipped"),
            ProbeResult(name="c", status="warn"),
            ProbeResult(name="d", status="missing"),
        ]

        self.assertEqual(overall_status(probes), "missing")

    def test_event_driven_probe_skips_empty_missing(self) -> None:
        probe = ProbeResult(name="relay_sec_filings", status="missing", row_count=0, detail="Official SEC.")

        result = _event_driven_probe(probe)

        self.assertEqual(result.status, "skipped")
        self.assertIn("event-driven", result.detail)

    def test_event_driven_probe_skips_age_only_warning(self) -> None:
        probe = ProbeResult(name="relay_twse_mops", status="warn", row_count=20, detail="Official TWSE.")

        result = _event_driven_probe(probe)

        self.assertEqual(result.status, "skipped")
        self.assertIn("age alone", result.detail)

    def test_us_session_probe_skips_closed_session(self) -> None:
        calendar_state = SimpleNamespace(
            us_close_session_date=date(2026, 8, 16),
            us=SimpleNamespace(is_trading_day=False, reason="weekend"),
        )
        probe = ProbeResult(name="relay_us_index_tracker", status="warn", detail="US index.")

        result = _us_session_probe(probe, calendar_state=calendar_state)

        self.assertEqual(result.status, "skipped")
        self.assertIn("2026-08-16", result.detail)

    def test_scheduled_slot_probe_skips_before_due_time(self) -> None:
        probe = ProbeResult(name="analysis_tw_close", status="warn", detail="TW close.")

        result = _scheduled_slot_probe(
            probe,
            now_local=datetime(2026, 8, 17, 9, 40, tzinfo=timezone.utc),
            expected_slots={"tw_close"},
            slot="tw_close",
            due_time=time(15, 45),
        )

        self.assertEqual(result.status, "skipped")
        self.assertIn("15:45", result.detail)

    def test_scheduled_slot_probe_skips_calendar_ineligible_slot(self) -> None:
        probe = ProbeResult(name="analysis_us_close", status="warn", detail="US close.")

        result = _scheduled_slot_probe(
            probe,
            now_local=datetime(2026, 8, 17, 9, 40, tzinfo=timezone.utc),
            expected_slots={"pre_tw_open", "tw_close"},
            slot="us_close",
            due_time=time(5, 15),
        )

        self.assertEqual(result.status, "skipped")
        self.assertIn("not expected", result.detail)

    def test_public_record_link_probe_ok_when_no_candidate_matches(self) -> None:
        probe = ProbeResult(name="public_record_links", status="stale", detail="Link freshness.")

        result = _classify_public_record_link_probe(probe, candidate_matches=0)

        self.assertEqual(result.status, "ok")
        self.assertIn("No deterministic", result.detail)

    def test_public_record_link_probe_keeps_stale_when_matches_exist(self) -> None:
        probe = ProbeResult(name="public_record_links", status="stale", detail="Link freshness.")

        result = _classify_public_record_link_probe(probe, candidate_matches=2)

        self.assertEqual(result.status, "stale")
        self.assertIn("deterministic_candidate_matches=2", result.detail)

    def test_render_text_includes_summary_and_probe(self) -> None:
        report = HealthReport(
            generated_at_utc="2026-05-14T00:00:00+00:00",
            overall_status="warn",
            config={
                "rss_feeds_count": 28,
                "x_enabled": True,
                "sec_enabled": True,
                "twse_mops_enabled": True,
            },
            probes=[
                ProbeResult(
                    name="public_records_npa_traffic_accident_a1",
                    status="warn",
                    latest_utc="2026-05-12 03:41:26",
                    age_minutes=2953,
                    row_count=489,
                    recent_count=0,
                    detail="Structured official public-record ingestion freshness.",
                )
            ],
        )

        text = render_text(report)

        self.assertIn("Data source health: WARN", text)
        self.assertIn("rss_feeds=28", text)
        self.assertIn("public_records_npa_traffic_accident_a1", text)

    def test_news_platform_source_ids_exclude_disabled_sources(self) -> None:
        self.assertNotIn("tvbs", NEWS_PLATFORM_SOURCE_IDS)
        self.assertNotIn("ctee", NEWS_PLATFORM_SOURCE_IDS)
        self.assertNotIn("udn", NEWS_PLATFORM_SOURCE_IDS)
        self.assertNotIn("setn", NEWS_PLATFORM_SOURCE_IDS)

    def test_news_platform_per_source_window_is_wider_than_category_window(self) -> None:
        self.assertEqual(NEWS_PLATFORM_CATEGORY_WARN_MINUTES, 180)
        self.assertEqual(NEWS_PLATFORM_CATEGORY_STALE_MINUTES, 720)
        self.assertEqual(NEWS_PLATFORM_SOURCE_WARN_MINUTES, 1440)
        self.assertEqual(NEWS_PLATFORM_SOURCE_STALE_MINUTES, 2880)
        self.assertGreater(NEWS_PLATFORM_SOURCE_WARN_MINUTES, NEWS_PLATFORM_CATEGORY_WARN_MINUTES)

    def test_public_record_groups_include_npa_stat_sources(self) -> None:
        self.assertIn(("npa", "traffic_accident_a2_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("npa", "fraud_enforcement_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("nhi", "nhi_hospital_nursing_staff_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("mohw", "mohw_hospital_bed_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("moj", "moj_prosecution_disposition_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("mojac", "mojac_daily_custody_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("cwa", "cwa_typhoon_report"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("cwa", "cwa_earthquake_report"), PUBLIC_RECORD_GROUPS)

    def test_process_probe_counts_root_python_service_instances(self) -> None:
        records = _parse_process_records(
            """
            [
              {"ProcessId": 10, "ParentProcessId": 1, "Name": "powershell.exe", "CommandLine": "python -m news_platform.main --loop"},
              {"ProcessId": 11, "ParentProcessId": 10, "Name": "python.exe", "CommandLine": "python -m news_platform.main --loop"},
              {"ProcessId": 12, "ParentProcessId": 11, "Name": "python.exe", "CommandLine": "python -m news_platform.main --loop"}
            ]
            """
        )

        probe = _process_count_probe(
            records,
            name="process_news_platform_loop",
            pattern=r"news_platform\.main.*--loop",
            expected_min=1,
            expected_max=1,
        )

        self.assertEqual(probe.status, "ok")
        self.assertEqual(probe.row_count, 1)


if __name__ == "__main__":
    unittest.main()
