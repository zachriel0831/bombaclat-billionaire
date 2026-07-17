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
        self.assertTrue(any(item.startswith("1200") for item in result["unsupported"]["numbers"]))

    def test_verify_claim_coverage_ignores_internal_evidence_id_citations(self) -> None:
        result = verify_claim_coverage(
            summary_text="Internal source refs （128610,128539,128557）; 2330 target 12345.",
            structured_payload={"stock_watch": [{"ticker": "2330"}]},
            events_payload=[
                {
                    "id": 128610,
                    "source": "market_context:twse_openapi",
                    "title": "2330 close",
                    "summary": "2330 close 900",
                    "raw": {"symbol": "2330", "value": 900},
                }
            ],
            market_payload=[],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["checked_counts"]["numbers"], 1)
        self.assertNotIn("128610128", result["unsupported"]["numbers"])
        self.assertNotIn("128610", result["unsupported"]["numbers"])
        self.assertIn("12345", result["unsupported"]["numbers"])

    def test_verify_claim_coverage_allows_common_number_format_variants(self) -> None:
        result = verify_claim_coverage(
            summary_text="台股收 45,625 點，銀行準備金 3.14 兆美元，逆回購 1.25 億美元。",
            structured_payload=None,
            events_payload=[
                {
                    "id": 1,
                    "source": "market_context:scorecard",
                    "title": "market context",
                    "summary": "加權指數 45625.1，銀行準備金 3.141 兆美元，逆回購 1.25億美元。",
                    "raw": {
                        "taiex": 45625.1,
                        "reserve_trillion_usd": 3.141,
                        "reverse_repo": "1.25億美元",
                    },
                }
            ],
            market_payload=[],
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["unsupported_counts"]["numbers"], 0)

    def test_verify_claim_coverage_does_not_treat_range_delimiter_as_negative(self) -> None:
        result = verify_claim_coverage(
            summary_text="聯準會利率區間維持 3.5%-3.75% 不變。",
            structured_payload=None,
            events_payload=[
                {
                    "id": 1,
                    "source": "market_context:fed",
                    "title": "fed rate range",
                    "summary": "policy rate range 3.5%-3.75%",
                    "raw": {"lower": "3.5%", "upper": "3.75%"},
                }
            ],
            market_payload=[],
        )

        self.assertTrue(result["ok"], result)
        self.assertNotIn("-3.75%", result["unsupported"]["numbers"])

    def test_verify_claim_coverage_allows_configured_tickers(self) -> None:
        result = verify_claim_coverage(
            summary_text="Fixed pool watch: 2330.TW, 2317, and 2454.",
            structured_payload={"stock_watch": [{"ticker": "2330"}, {"ticker": "2317"}]},
            events_payload=[],
            market_payload=[],
            allowed_tickers={"2330", "2317", "2454"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["unsupported_counts"]["tickers"], 0)

    def test_verify_claim_coverage_still_flags_unconfigured_ticker(self) -> None:
        result = verify_claim_coverage(
            summary_text="Outside ticker 4749 is not part of the allowed pool.",
            structured_payload=None,
            events_payload=[],
            market_payload=[],
            allowed_tickers={"2330"},
        )

        self.assertFalse(result["ok"])
        self.assertIn("4749", result["unsupported"]["tickers"])


if __name__ == "__main__":
    unittest.main()
