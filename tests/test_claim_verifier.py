import unittest

from event_relay.claim_verifier import verify_claim_coverage


class ClaimVerifierTests(unittest.TestCase):
    def test_verify_claim_coverage_supports_numbers_dates_and_tickers(self) -> None:
        result = verify_claim_coverage(
            summary_text="2026-05-04 2330 收 900 元，上漲 2.5%。",
            structured_payload={"stock_watch": [{"ticker": "2330"}]},
            events_payload=[
                {
                    "id": 1,
                    "source": "market_context:twse_openapi",
                    "title": "2330 台積電 900",
                    "summary": "2026-05-04 close 900 change 2.5%",
                    "raw": {"point": {"symbol": "2330", "value": 900, "change_percent": 2.5}},
                }
            ],
            market_payload=[],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["unsupported_counts"]["numbers"], 0)
        self.assertEqual(result["unsupported_counts"]["dates"], 0)
        self.assertEqual(result["unsupported_counts"]["tickers"], 0)

    def test_verify_claim_coverage_flags_missing_numeric_claim(self) -> None:
        result = verify_claim_coverage(
            summary_text="2330 目標價 1200 元。",
            structured_payload=None,
            events_payload=[
                {
                    "id": 1,
                    "source": "market_context:twse_openapi",
                    "title": "2330 台積電 900",
                    "summary": "close 900",
                    "raw": {},
                }
            ],
            market_payload=[],
        )

        self.assertFalse(result["ok"])
        self.assertIn("1200 元", result["unsupported"]["numbers"])


if __name__ == "__main__":
    unittest.main()
