import unittest

from data_source_health import (
    NEWS_PLATFORM_SOURCE_IDS,
    PUBLIC_RECORD_GROUPS,
    ProbeResult,
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

    def test_news_platform_source_ids_include_commercial_times(self) -> None:
        self.assertIn("ctee", NEWS_PLATFORM_SOURCE_IDS)

    def test_public_record_groups_include_npa_stat_sources(self) -> None:
        self.assertIn(("npa", "traffic_accident_a2_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("npa", "fraud_enforcement_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("nhi", "nhi_hospital_nursing_staff_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("mohw", "mohw_hospital_bed_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("moj", "moj_prosecution_disposition_stat"), PUBLIC_RECORD_GROUPS)
        self.assertIn(("mojac", "mojac_daily_custody_stat"), PUBLIC_RECORD_GROUPS)

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
