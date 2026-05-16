"""news_platform article-to-public-record matcher tests."""

from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace

from news_platform.public_record_matcher import (
    ArticlePublicRecordMatcher,
    PublicRecordLinkWorker,
)


def _article(title: str, *, article_id: str = "article-1", category: str = "politics") -> SimpleNamespace:
    return SimpleNamespace(
        row_id=1,
        article_id=article_id,
        category=category,
        title=title,
        summary="",
        published_at=datetime(2026, 5, 9, 8, 0, 0),
    )


def _record(title: str, *, record_id: str = "ly:bill:1", raw=None) -> SimpleNamespace:
    return SimpleNamespace(
        record_id=record_id,
        source_id="ly",
        record_type="legislative_bill",
        category="politics",
        title=title,
        url="https://www.ly.gov.tw/WebAPI/LegislativeBill.aspx",
        occurred_at=datetime(2026, 5, 8, 0, 0, 0),
        raw_json=raw or {"proposers": ["吳思瑤"]},
    )


def _fraud_record(title: str, *, raw=None) -> SimpleNamespace:
    return SimpleNamespace(
        record_id="npa:fraud_rumor:1",
        source_id="npa",
        record_type="fraud_rumor",
        category="society",
        title=title,
        url="https://data.gov.tw/dataset/38262",
        occurred_at=datetime(2026, 5, 8, 0, 0, 0),
        raw_json=raw or {"dataset_url": "https://data.gov.tw/dataset/38262"},
    )


class ArticlePublicRecordMatcherTests(unittest.TestCase):
    def test_matches_legislative_bill_by_law_name_person_and_date(self):
        matcher = ArticlePublicRecordMatcher(min_confidence=0.68)

        matches = matcher.match_article(
            _article("吳思瑤提大學法修正草案 盼強化學生權益"),
            [_record("大學法部分條文修正草案")],
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].public_record_id, "ly:bill:1")
        self.assertEqual(matches[0].matched_by, "ly_bill_rule")
        self.assertGreaterEqual(matches[0].confidence, 0.68)
        self.assertEqual(matches[0].evidence["matched_laws"], ["大學法"])
        self.assertEqual(matches[0].evidence["matched_people"], ["吳思瑤"])

    def test_does_not_match_on_person_name_only(self):
        matcher = ArticlePublicRecordMatcher(min_confidence=0.68)

        matches = matcher.match_article(
            _article("吳思瑤批市政攻防失焦"),
            [_record("大學法部分條文修正草案")],
        )

        self.assertEqual(matches, [])

    def test_matches_long_specific_law_name_without_person(self):
        matcher = ArticlePublicRecordMatcher(min_confidence=0.68)

        matches = matcher.match_article(
            _article("電子競技運動發展基本法將送立院審查"),
            [_record("電子競技運動發展基本法草案", raw={"proposers": ["羅廷瑋"]})],
        )

        self.assertEqual(len(matches), 1)
        self.assertGreaterEqual(matches[0].confidence, 0.68)
        self.assertEqual(matches[0].evidence["matched_laws"], ["電子競技運動發展基本法"])


    def test_matches_fraud_rumor_by_specific_title_terms(self):
        matcher = ArticlePublicRecordMatcher(min_confidence=0.68)

        matches = matcher.match_article(
            _article(
                "刑事警察局公布網路廣告平臺違法投資廣告態樣，提醒民眾防詐騙",
                category="society",
            ),
            [_fraud_record("公布114年第一季網路廣告平臺業者 刊登違法投資廣告態樣")],
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].public_record_id, "npa:fraud_rumor:1")
        self.assertEqual(matches[0].matched_by, "npa_fraud_rumor_rule")
        self.assertIn("網路廣告平臺", matches[0].evidence["matched_terms"])

    def test_fraud_rumor_does_not_cross_match_politics_category(self):
        matcher = ArticlePublicRecordMatcher(min_confidence=0.68)

        matches = matcher.match_article(
            _article("刑事警察局公布網路廣告平臺違法投資廣告態樣"),
            [_fraud_record("公布114年第一季網路廣告平臺業者 刊登違法投資廣告態樣")],
        )

        self.assertEqual(matches, [])


class FakeMatcherStore:
    def __init__(self) -> None:
        self.articles = [_article("吳思瑤提大學法修正草案", article_id="article-1")]
        self.records = [_record("大學法部分條文修正草案", record_id="ly:bill:abc")]
        self.links = []

    def fetch_articles_for_public_record_matching(self, **kwargs):
        self.article_kwargs = kwargs
        return self.articles

    def fetch_public_records_for_matching(self, **kwargs):
        self.record_kwargs = kwargs
        return self.records

    def link_article_public_record(self, **kwargs) -> bool:
        self.links.append(kwargs)
        return True


class PublicRecordLinkWorkerTests(unittest.TestCase):
    def test_worker_writes_matched_links(self):
        store = FakeMatcherStore()
        worker = PublicRecordLinkWorker(store, batch_size=50, lookback_days=30)

        result = worker.run_once()

        self.assertEqual(result.scanned_articles, 1)
        self.assertEqual(result.candidate_records, 1)
        self.assertEqual(result.linked, 1)
        self.assertEqual(store.article_kwargs["limit"], 50)
        self.assertEqual(store.record_kwargs["lookback_days"], 30)
        self.assertEqual(store.links[0]["article_id"], "article-1")
        self.assertEqual(store.links[0]["public_record_id"], "ly:bill:abc")
        self.assertEqual(store.links[0]["matched_by"], "ly_bill_rule")
        self.assertIn("matched_laws", store.links[0]["evidence"])


if __name__ == "__main__":
    unittest.main()
