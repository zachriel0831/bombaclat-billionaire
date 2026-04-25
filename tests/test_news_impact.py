"""REQ-020 — trade-impact enrichment tests."""
import unittest

from event_relay.event_enrichment import (
    CONFIDENCE_VALUES,
    IMPACT_DIRECTION_VALUES,
    IMPACT_REGION_VALUES,
    IMPACT_SCOPE_VALUES,
    TOPIC_VALUES,
    URGENCY_VALUES,
    EventAnnotation,
    NewsImpact,
    annotate,
    compute_cluster_id,
    derive_news_impact,
)


def _ann(
    *,
    entities=(),
    category: str = "other",
    importance: float = 0.3,
    sentiment: str = "neutral",
) -> EventAnnotation:
    return EventAnnotation(
        entities=tuple(entities),
        category=category,
        importance=importance,
        sentiment=sentiment,
        annotator="rule",
        annotator_version="rule-v1",
    )


class TopicClassificationTests(unittest.TestCase):
    def test_central_bank_wins_over_macro(self) -> None:
        ann = annotate(source="reuters", title="FOMC cuts rates 25bp on softer CPI", summary="")
        impact = derive_news_impact(annotation=ann, title="FOMC cuts rates 25bp on softer CPI", summary="")
        self.assertEqual(impact.topic, "central_bank")

    def test_semiconductor_specific(self) -> None:
        ann = annotate(source="reuters", title="TSMC ramps 3nm wafer capacity", summary="")
        impact = derive_news_impact(annotation=ann, title="TSMC ramps 3nm wafer capacity", summary="")
        self.assertEqual(impact.topic, "semiconductor")

    def test_ai_bucket(self) -> None:
        ann = annotate(source="reuters", title="OpenAI ships new generative AI model with H200 GPUs", summary="")
        impact = derive_news_impact(
            annotation=ann,
            title="OpenAI ships new generative AI model with H200 GPUs",
            summary="",
        )
        self.assertEqual(impact.topic, "ai")

    def test_geopolitics(self) -> None:
        ann = annotate(source="reuters", title="Sanctions tighten amid escalating conflict", summary="")
        impact = derive_news_impact(
            annotation=ann,
            title="Sanctions tighten amid escalating conflict",
            summary="",
        )
        self.assertEqual(impact.topic, "geopolitics")

    def test_macro_release(self) -> None:
        ann = annotate(source="reuters", title="US PPI rises 0.4% in March", summary="")
        impact = derive_news_impact(annotation=ann, title="US PPI rises 0.4% in March", summary="")
        self.assertEqual(impact.topic, "macro")

    def test_other_when_no_topic_match(self) -> None:
        ann = _ann()
        impact = derive_news_impact(annotation=ann, title="An unrelated lifestyle headline", summary="")
        self.assertEqual(impact.topic, "other")

    def test_topic_value_in_taxonomy(self) -> None:
        ann = annotate(source="reuters", title="TSMC 3nm wafer", summary="")
        impact = derive_news_impact(annotation=ann, title="TSMC 3nm wafer", summary="")
        self.assertIn(impact.topic, TOPIC_VALUES)


class ImpactRegionScopeTests(unittest.TestCase):
    def test_single_country_single_name(self) -> None:
        ann = _ann(
            entities=({"kind": "country", "value": "TW"}, {"kind": "ticker", "value": "2330"}),
            category="earnings",
            importance=0.6,
        )
        impact = derive_news_impact(annotation=ann, title="2330 beats expectations", summary="")
        self.assertEqual(impact.impact_region, "TW")
        self.assertEqual(impact.impact_scope, "single_name")

    def test_multiple_countries_collapse_to_global(self) -> None:
        ann = _ann(
            entities=(
                {"kind": "country", "value": "US"},
                {"kind": "country", "value": "CN"},
            ),
            category="geopolitics",
            importance=0.7,
        )
        impact = derive_news_impact(annotation=ann, title="US-China tariff escalation", summary="")
        self.assertEqual(impact.impact_region, "Global")

    def test_no_country_defaults_to_global(self) -> None:
        ann = _ann(category="rate_decision", importance=0.7)
        impact = derive_news_impact(annotation=ann, title="FOMC cuts rates", summary="")
        self.assertEqual(impact.impact_region, "Global")

    def test_sector_scope_when_topic_is_industry_no_ticker(self) -> None:
        ann = _ann(category="supply_chain", importance=0.5)
        impact = derive_news_impact(annotation=ann, title="Wafer foundry capacity tightening", summary="")
        self.assertEqual(impact.impact_scope, "sector")

    def test_index_scope_for_macro_event(self) -> None:
        ann = _ann(category="macro_release", importance=0.6)
        impact = derive_news_impact(annotation=ann, title="US CPI prints 3.2%", summary="")
        self.assertEqual(impact.impact_scope, "index")


class DirectionUrgencyConfidenceTests(unittest.TestCase):
    def test_direction_unknown_when_thin_data(self) -> None:
        ann = _ann(importance=0.2)  # no entities, low importance
        impact = derive_news_impact(annotation=ann, title="vague headline", summary="")
        self.assertEqual(impact.impact_direction, "unknown")

    def test_direction_passes_through_bullish(self) -> None:
        ann = _ann(
            entities=({"kind": "company", "value": "TSMC"},),
            category="earnings",
            importance=0.6,
            sentiment="bullish",
        )
        impact = derive_news_impact(annotation=ann, title="TSMC beats estimates", summary="")
        self.assertEqual(impact.impact_direction, "bullish")

    def test_direction_neutral_with_entities_becomes_mixed(self) -> None:
        ann = _ann(
            entities=({"kind": "company", "value": "TSMC"},),
            category="corporate_action",
            importance=0.5,
            sentiment="neutral",
        )
        impact = derive_news_impact(annotation=ann, title="TSMC announces dividend policy", summary="")
        self.assertEqual(impact.impact_direction, "mixed")

    def test_urgency_high_for_central_bank(self) -> None:
        ann = annotate(source="reuters", title="FOMC raises rates 25bp", summary="")
        impact = derive_news_impact(annotation=ann, title="FOMC raises rates 25bp", summary="")
        self.assertEqual(impact.urgency, "high")

    def test_urgency_medium_for_macro(self) -> None:
        # Use a manually-built annotation to keep importance below the
        # 0.75 high-urgency threshold while still landing topic=macro.
        ann = _ann(category="macro_release", importance=0.55)
        impact = derive_news_impact(annotation=ann, title="US retail sales prints in line", summary="")
        self.assertEqual(impact.urgency, "medium")

    def test_confidence_low_when_no_entities(self) -> None:
        ann = _ann(importance=0.3)
        impact = derive_news_impact(annotation=ann, title="lifestyle headline", summary="")
        self.assertEqual(impact.confidence, "low")

    def test_confidence_high_when_strong_signal(self) -> None:
        ann = _ann(
            entities=({"kind": "policy", "value": "Fed"},),
            category="rate_decision",
            importance=0.85,
        )
        impact = derive_news_impact(annotation=ann, title="Fed surprise rate cut", summary="")
        self.assertEqual(impact.confidence, "high")

    def test_data_gap_true_when_other_or_no_entities(self) -> None:
        ann = _ann(category="other", importance=0.2)
        impact = derive_news_impact(annotation=ann, title="random text", summary="")
        self.assertTrue(impact.data_gap)


class ContractTests(unittest.TestCase):
    def test_to_dict_has_all_fields(self) -> None:
        ann = annotate(source="reuters", title="TSMC reports earnings", summary="")
        impact = derive_news_impact(annotation=ann, title="TSMC reports earnings", summary="")
        d = impact.to_dict()
        self.assertEqual(set(d.keys()),
            {"topic", "impact_region", "impact_scope", "impact_direction",
             "urgency", "confidence", "data_gap", "cluster_id"})

    def test_enum_values_in_taxonomy(self) -> None:
        ann = annotate(source="reuters", title="FOMC raises rates", summary="")
        impact = derive_news_impact(annotation=ann, title="FOMC raises rates", summary="")
        self.assertIn(impact.impact_region, IMPACT_REGION_VALUES)
        self.assertIn(impact.impact_scope, IMPACT_SCOPE_VALUES)
        self.assertIn(impact.impact_direction, IMPACT_DIRECTION_VALUES)
        self.assertIn(impact.urgency, URGENCY_VALUES)
        self.assertIn(impact.confidence, CONFIDENCE_VALUES)


class ClusterIdTests(unittest.TestCase):
    def test_same_headline_different_source_prefix_same_cluster(self) -> None:
        a = compute_cluster_id("Reuters - Powell signals slower rate cuts")
        b = compute_cluster_id("Bloomberg: Powell signals slower rate cuts")
        c = compute_cluster_id("Powell signals slower rate cuts")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_token_reorder_same_cluster(self) -> None:
        # token-set hashing is order-insensitive (same word forms required;
        # singular/plural differences land in different clusters by design)
        a = compute_cluster_id("Powell cut rates 25bp")
        b = compute_cluster_id("Rates 25bp cut Powell")
        self.assertEqual(a, b)

    def test_distinct_headlines_distinct_cluster(self) -> None:
        a = compute_cluster_id("Powell signals slower rate cuts")
        b = compute_cluster_id("TSMC reports record quarterly revenue")
        self.assertNotEqual(a, b)

    def test_empty_title_still_returns_id(self) -> None:
        cid = compute_cluster_id("")
        self.assertEqual(len(cid), 12)


if __name__ == "__main__":
    unittest.main()
