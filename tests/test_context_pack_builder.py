import unittest

from event_relay.context_pack_builder import build_context_pack, classify_event_source


def _event(row_id, source, title, importance=0.1, raw=None):
    return {
        "id": row_id,
        "source": source,
        "title": title,
        "url": f"https://example.com/{row_id}",
        "summary": title,
        "published_at": "2026-05-04T12:00:00+00:00",
        "created_at": "2026-05-04 12:00:00",
        "raw": raw,
        "annotation": {"importance": importance},
        "impact": {},
    }


class ContextPackBuilderTests(unittest.TestCase):
    def test_classify_event_source(self) -> None:
        self.assertEqual(
            classify_event_source(_event(1, "market_context:scorecard", "score", raw={"event_type": "market_context_scorecard"})),
            "scorecard",
        )
        self.assertEqual(classify_event_source(_event(2, "market_context:fred", "fred")), "market_context")
        self.assertEqual(classify_event_source(_event(3, "sec:NVDA", "filing")), "official_data")
        self.assertEqual(classify_event_source(_event(4, "market_analysis:us_close", "analysis")), "upstream_analysis")
        self.assertEqual(classify_event_source(_event(5, "x:elonmusk", "tweet")), "social")

    def test_build_context_pack_guarantees_core_buckets_under_news_flood(self) -> None:
        events = [
            *[_event(100 + index, "reuters", f"high importance news {index}", importance=0.99) for index in range(10)],
            _event(1, "market_context:scorecard", "scorecard", raw={"event_type": "market_context_scorecard"}),
            _event(2, "market_context:collector", "collector", raw={"event_type": "market_context_collection"}),
            _event(3, "sec:NVDA", "NVDA 10-Q"),
            _event(4, "twse_mops:2330", "重大訊息"),
        ]

        packed, telemetry = build_context_pack(events, max_events=5)

        sources = {event["source"] for event in packed}
        self.assertIn("market_context:scorecard", sources)
        self.assertIn("market_context:collector", sources)
        self.assertIn("sec:NVDA", sources)
        self.assertIn("twse_mops:2330", sources)
        self.assertEqual(len(packed), 5)
        self.assertTrue(telemetry["guaranteed_buckets"]["scorecard"]["satisfied"])
        self.assertTrue(telemetry["guaranteed_buckets"]["market_context"]["satisfied"])
        self.assertTrue(telemetry["guaranteed_buckets"]["official_data"]["satisfied"])
        self.assertGreater(telemetry["dropped_counts"]["news"], 0)

    def test_build_context_pack_dedupes_by_event_id(self) -> None:
        events = [
            _event(1, "market_context:scorecard", "scorecard v1", raw={"event_type": "market_context_scorecard"}),
            _event(1, "market_context:scorecard", "scorecard duplicate", raw={"event_type": "market_context_scorecard"}),
            _event(2, "market_context:fred", "FRED"),
            _event(3, "reuters", "news"),
        ]

        packed, telemetry = build_context_pack(events, max_events=10)

        self.assertEqual([event["id"] for event in packed].count(1), 1)
        self.assertEqual(telemetry["input_count"], 4)
        self.assertEqual(telemetry["candidate_count"], 3)
        self.assertEqual(telemetry["output_count"], 3)
        self.assertEqual(packed[0]["context_bucket"], "scorecard")


if __name__ == "__main__":
    unittest.main()
