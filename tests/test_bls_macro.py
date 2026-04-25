from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_relay.bls_macro import (
    BLS_SERIES_BY_ID,
    BlsApiError,
    BlsMacroConfig,
    _build_bls_payload,
    build_bls_macro_events,
    build_event_id,
    parse_bls_response,
    run_once,
)


def _sample_response(latest_flag: bool = True) -> dict:
    latest = {"latest": "true"} if latest_flag else {}
    return {
        "status": "REQUEST_SUCCEEDED",
        "responseTime": 12,
        "message": [],
        "Results": {
            "series": [
                {
                    "seriesID": "CUSR0000SA0",
                    "data": [
                        {
                            "year": "2026",
                            "period": "M01",
                            "periodName": "January",
                            "value": "318.000",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2026",
                            "period": "M13",
                            "periodName": "Annual",
                            "value": "999.000",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2025",
                            "period": "M03",
                            "periodName": "March",
                            "value": "315.000",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2026",
                            "period": "M02",
                            "periodName": "February",
                            "value": "319.000",
                            "footnotes": [{}],
                        },
                        {
                            "year": "2026",
                            "period": "M03",
                            "periodName": "March",
                            "value": "320.000",
                            "footnotes": [{"code": "P", "text": "Preliminary."}],
                            **latest,
                        },
                    ],
                }
            ]
        },
    }


class _FakeStore:
    events = []

    def __init__(self, _settings) -> None:
        return None

    def initialize(self) -> None:
        return None

    def enqueue_event_if_new(self, event) -> bool:
        _FakeStore.events.append(event)
        return True


class BlsMacroTests(unittest.TestCase):
    def test_parse_bls_response_builds_normalized_point(self) -> None:
        points = parse_bls_response(_sample_response())

        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertEqual(point.spec, BLS_SERIES_BY_ID["CUSR0000SA0"])
        self.assertEqual(point.observation.year, "2026")
        self.assertEqual(point.observation.period, "M03")
        self.assertEqual(point.observation.value_float, 320.0)
        self.assertEqual(point.previous_observation.value_float, 319.0)
        self.assertEqual(point.year_ago_observation.value_float, 315.0)
        self.assertEqual(point.normalized_metrics["period_change"], 1.0)
        self.assertAlmostEqual(point.normalized_metrics["year_over_year_percent"], 1.5873, places=4)
        self.assertTrue(point.normalized_metrics["is_preliminary"])

    def test_latest_observation_selection_uses_latest_period_when_no_flag(self) -> None:
        points = parse_bls_response(_sample_response(latest_flag=False))

        self.assertEqual(points[0].observation.year, "2026")
        self.assertEqual(points[0].observation.period, "M03")
        self.assertEqual(points[0].observation.period_name, "March")

    def test_event_id_contains_source_family_series_year_period(self) -> None:
        event_id = build_event_id("CUSR0000SA0", "2026", "M03")

        self.assertEqual(event_id, "market-context-bls_macro-cusr0000sa0-2026-m03")

    def test_build_events_marks_raw_json_stored_only(self) -> None:
        point = parse_bls_response(_sample_response())[0]

        events = build_bls_macro_events([point], generated_at="2026-04-22T00:00:00+00:00")

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source, "market_context:bls_macro")
        self.assertFalse(event.log_only)
        self.assertEqual(event.event_id, "market-context-bls_macro-cusr0000sa0-2026-m03")
        self.assertTrue(event.raw["stored_only"])
        self.assertEqual(event.raw["dimension"], "market_context")
        self.assertEqual(event.raw["event_type"], "market_context_point")
        self.assertEqual(event.raw["series_id"], "CUSR0000SA0")
        self.assertEqual(event.raw["year"], "2026")
        self.assertEqual(event.raw["period"], "M03")
        self.assertEqual(event.raw["value"], "320.000")
        self.assertEqual(event.raw["footnotes"], [{"code": "P", "text": "Preliminary."}])
        self.assertEqual(event.raw["normalized_metrics"]["value"], 320.0)

    def test_no_key_payload_omits_registration_key(self) -> None:
        no_key_payload = _build_bls_payload(["CUSR0000SA0"], api_key=None)
        keyed_payload = _build_bls_payload(["CUSR0000SA0"], api_key="secret-key")

        self.assertEqual(no_key_payload, {"seriesid": ["CUSR0000SA0"]})
        self.assertEqual(keyed_payload["registrationkey"], "secret-key")

    def test_api_error_response_raises_explicit_exception(self) -> None:
        with self.assertRaisesRegex(BlsApiError, "REQUEST_FAILED"):
            parse_bls_response({"status": "REQUEST_FAILED", "message": ["Invalid series id"]})

    def test_run_once_writes_relay_events(self) -> None:
        _FakeStore.events = []
        point = parse_bls_response(_sample_response())[0]
        config = BlsMacroConfig(
            env_file=".env",
            api_key=None,
            timeout_seconds=5,
            series_ids=["CUSR0000SA0"],
        )

        with patch("event_relay.bls_macro.load_settings", return_value=SimpleNamespace(mysql_enabled=True)):
            with patch("event_relay.bls_macro.MySqlEventStore", _FakeStore):
                with patch("event_relay.bls_macro.collect_bls_macro", return_value=[point]):
                    result = run_once(config)

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "market_context:bls_macro")
        self.assertEqual(result["events"], 1)
        self.assertEqual(result["stored"], 1)
        self.assertEqual(len(_FakeStore.events), 1)
        self.assertEqual(_FakeStore.events[0].source, "market_context:bls_macro")


if __name__ == "__main__":
    unittest.main()
