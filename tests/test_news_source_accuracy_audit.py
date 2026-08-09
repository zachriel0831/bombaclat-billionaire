"""news_platform.source_accuracy_audit tests."""

from datetime import datetime, timezone
import unittest

from news_platform.models import NewsArticle
from news_platform.registry import FeedSpec
from news_platform.source_accuracy_audit import (
    evaluate_probe,
    render_text,
    source_ids_for_accuracy_audit,
    SourceAccuracyReport,
)


class SourceAccuracyAuditTests(unittest.TestCase):
    def test_default_scope_includes_low_frequency_but_skips_ctee(self):
        source_ids = source_ids_for_accuracy_audit(categories=("society", "politics"))

        self.assertIn("ltn", source_ids)
        self.assertIn("tvbs", source_ids)
        self.assertIn("udn", source_ids)
        self.assertIn("setn", source_ids)
        self.assertNotIn("ctee", source_ids)

    def test_all_scope_can_include_registered_sources_when_not_skipped(self):
        source_ids = source_ids_for_accuracy_audit(
            categories=("society",),
            source_ids=("all",),
            skip_source_ids=(),
        )

        self.assertIn("ctee", source_ids)
        self.assertIn("tvbs", source_ids)

    def test_evaluate_probe_warns_when_coverage_is_low(self):
        spec = FeedSpec(source_id="ltn", category="politics", kind="rss", url="https://example.test/rss")
        articles = [
            _article("a1", "https://example.test/a1"),
            _article("a2", "https://example.test/a2"),
            _article("a3", "https://example.test/a3"),
        ]

        probe = evaluate_probe(
            spec=spec,
            official_articles=articles,
            matched_article_ids={"a1"},
            matched_urls=set(),
            min_coverage=0.85,
            min_items=3,
        )

        self.assertEqual(probe.status, "warn")
        self.assertEqual(probe.official_count, 3)
        self.assertEqual(probe.matched_count, 1)
        self.assertEqual(probe.missing_count, 2)
        self.assertEqual(len(probe.missing_samples or []), 2)

    def test_render_text_includes_compensation_summary(self):
        report = SourceAccuracyReport(
            generated_at_utc="2026-08-10T00:00:00+00:00",
            overall_status="ok",
            config={
                "categories": ["society"],
                "source_ids": ["ltn"],
                "limit_per_source": 20,
                "min_coverage": 0.85,
                "compensate": True,
            },
            probes=[
                evaluate_probe(
                    spec=FeedSpec(source_id="ltn", category="society", kind="rss", url="https://example.test/rss"),
                    official_articles=[_article("a1", "https://example.test/a1")],
                    matched_article_ids={"a1"},
                    matched_urls=set(),
                    min_coverage=0.85,
                    min_items=1,
                )
            ],
        )

        text = render_text(report)

        self.assertIn("News source accuracy: OK", text)
        self.assertIn("coverage=100%", text)


def _article(article_id: str, url: str) -> NewsArticle:
    return NewsArticle(
        article_id=article_id,
        source_id="ltn",
        country="TW",
        category="politics",
        title=f"title {article_id}",
        url=url,
        published_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        summary=None,
    )


if __name__ == "__main__":
    unittest.main()
