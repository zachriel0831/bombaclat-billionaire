import unittest

from event_relay.event_enrichment import (
    ANNOTATOR_RULE_VERSION,
    CATEGORY_VALUES,
    SENTIMENT_VALUES,
    annotate,
)


class EntityExtractionTests(unittest.TestCase):
    """封裝 Entity Extraction Tests 相關資料與行為。"""
    def test_extracts_tw_ticker(self) -> None:
        """測試 test extracts tw ticker 的預期行為。"""
        ann = annotate(source="cnyes", title="台積電 2330 營收創高", summary="")
        kinds = [(entity["kind"], entity["value"]) for entity in ann.entities]
        self.assertIn(("ticker", "2330"), kinds)
        self.assertIn(("company", "TSMC"), kinds)

    def test_extracts_us_ticker_and_person(self) -> None:
        """測試 test extracts us ticker and person 的預期行為。"""
        ann = annotate(
            source="bloomberg",
            title="Powell signals caution on $NVDA rally",
            summary="",
        )
        kinds = [(entity["kind"], entity["value"]) for entity in ann.entities]
        self.assertIn(("ticker", "NVDA"), kinds)
        self.assertIn(("person", "Jerome Powell"), kinds)

    def test_extracts_policy_and_country(self) -> None:
        """測試 test extracts policy and country 的預期行為。"""
        ann = annotate(
            source="reuters",
            title="FOMC holds rates, Powell eyes US inflation",
            summary="",
        )
        kinds = {entity["kind"] for entity in ann.entities}
        values = {entity["value"] for entity in ann.entities}
        self.assertIn("policy", kinds)
        self.assertIn("country", kinds)
        self.assertIn("FOMC", values)
        self.assertIn("US", values)

    def test_extracts_macro_indicator(self) -> None:
        """測試 test extracts macro indicator 的預期行為。"""
        ann = annotate(
            source="bls",
            title="US CPI rose 0.4% in March",
            summary="",
        )
        self.assertIn({"kind": "macro_indicator", "value": "CPI"}, list(ann.entities))


class CategoryClassificationTests(unittest.TestCase):
    """封裝 Category Classification Tests 相關資料與行為。"""
    def _category(self, title: str, summary: str = "", source: str = "reuters") -> str:
        """執行 category 方法的主要邏輯。"""
        return annotate(source=source, title=title, summary=summary).category

    def test_all_categories_are_valid(self) -> None:
        """測試 test all categories are valid 的預期行為。"""
        ann = annotate(source="x", title="random", summary="")
        self.assertIn(ann.category, CATEGORY_VALUES)

    def test_rate_decision(self) -> None:
        """測試 test rate decision 的預期行為。"""
        self.assertEqual(self._category("FOMC hikes 25 bps as expected"), "rate_decision")

    def test_earnings(self) -> None:
        """測試 test earnings 的預期行為。"""
        self.assertEqual(self._category("TSMC Q2 earnings beat"), "earnings")

    def test_geopolitics(self) -> None:
        """測試 test geopolitics 的預期行為。"""
        self.assertEqual(self._category("Iran missile strike escalates war"), "geopolitics")

    def test_supply_chain(self) -> None:
        """測試 test supply chain 的預期行為。"""
        self.assertEqual(
            self._category("Semiconductor supply chain shortage worsens"),
            "supply_chain",
        )

    def test_regulation(self) -> None:
        """測試 test regulation 的預期行為。"""
        self.assertEqual(self._category("EU antitrust probe into big tech"), "regulation")

    def test_macro_release(self) -> None:
        """測試 test macro release 的預期行為。"""
        self.assertEqual(self._category("US CPI up 0.4% in March"), "macro_release")

    def test_corporate_action(self) -> None:
        """測試 test corporate action 的預期行為。"""
        self.assertEqual(self._category("Apple announces $90B buyback"), "corporate_action")

    def test_other_when_no_keyword(self) -> None:
        """測試 test other when no keyword 的預期行為。"""
        self.assertEqual(self._category("Local festival attracts crowds"), "other")


class ImportanceScoringTests(unittest.TestCase):
    """封裝 Importance Scoring Tests 相關資料與行為。"""
    def test_minimum_floor_around_default(self) -> None:
        """測試 test minimum floor around default 的預期行為。"""
        ann = annotate(source="random_blog", title="vague headline", summary="")
        self.assertGreaterEqual(ann.importance, 0.2)
        self.assertLessEqual(ann.importance, 0.4)

    def test_mid_range_for_earnings_with_number(self) -> None:
        """測試 test mid range for earnings with number 的預期行為。"""
        ann = annotate(
            source="bloomberg",
            title="TSMC Q2 earnings beat, revenue +20%",
            summary="Revenue hit $20 billion",
        )
        # base 0.3 + 0.2 (source) + 0.2 (number) + 0.1 (earnings)
        self.assertAlmostEqual(ann.importance, 0.8, places=3)

    def test_maxes_at_one_for_breaking_fomc(self) -> None:
        """測試 test maxes at one for breaking fomc 的預期行為。"""
        ann = annotate(
            source="reuters",
            title="BREAKING: FOMC cuts rate by 50 bps, citing recession risk",
            summary="Powell warns US economy is weak.",
        )
        self.assertEqual(ann.importance, 1.0)


class SentimentTests(unittest.TestCase):
    """封裝 Sentiment Tests 相關資料與行為。"""
    def test_sentiment_enum(self) -> None:
        """測試 test sentiment enum 的預期行為。"""
        ann = annotate(source="x", title="anything", summary="")
        self.assertIn(ann.sentiment, SENTIMENT_VALUES)

    def test_bullish(self) -> None:
        """測試 test bullish 的預期行為。"""
        ann = annotate(source="bloomberg", title="Nvidia beats and surges to record high", summary="")
        self.assertEqual(ann.sentiment, "bullish")

    def test_bearish(self) -> None:
        """測試 test bearish 的預期行為。"""
        ann = annotate(source="bloomberg", title="Stocks plunge on weak jobs report", summary="")
        self.assertEqual(ann.sentiment, "bearish")

    def test_neutral(self) -> None:
        """測試 test neutral 的預期行為。"""
        ann = annotate(source="cnyes", title="Board meeting scheduled for next week", summary="")
        self.assertEqual(ann.sentiment, "neutral")


class PayloadShapeTests(unittest.TestCase):
    """封裝 Payload Shape Tests 相關資料與行為。"""
    def test_to_dict_has_required_keys(self) -> None:
        """測試 test to dict has required keys 的預期行為。"""
        ann = annotate(source="reuters", title="FOMC decision", summary="")
        payload = ann.to_dict()
        self.assertEqual(
            sorted(payload.keys()),
            [
                "annotator",
                "annotator_version",
                "category",
                "entities",
                "importance",
                "sentiment",
            ],
        )
        self.assertEqual(payload["annotator"], "rule")
        self.assertEqual(payload["annotator_version"], ANNOTATOR_RULE_VERSION)

    def test_market_context_raw_json_is_surfaced(self) -> None:
        """測試 test market context raw json is surfaced 的預期行為。"""
        raw = (
            '{"dataset_title":"BLS CPI-U","event_type":"macro_release",'
            '"point":{"label":"CPI 0.4% MoM"}}'
        )
        ann = annotate(
            source="market_context:bls",
            title="market_context",
            summary="",
            raw_json=raw,
        )
        self.assertEqual(ann.category, "macro_release")


if __name__ == "__main__":
    unittest.main()
