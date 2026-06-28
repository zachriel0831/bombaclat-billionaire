"""news_platform.topic_llm tests."""

import json
import unittest
from unittest.mock import patch

from news_platform.config import NewsPlatformSettings
from news_platform.topic_llm import TopicLlmClassifier, _extract_anthropic_text, _extract_openai_text


def _settings(**overrides) -> NewsPlatformSettings:
    base = dict(
        mysql_enabled=True,
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="root",
        mysql_password="root",
        mysql_database="news_platform",
        mysql_article_table="t_news_articles",
        mysql_source_table="t_news_sources",
        mysql_public_record_table="t_public_records",
        mysql_article_record_link_table="t_news_article_public_record_links",
        mysql_author_table="t_news_authors",
        mysql_article_author_table="t_news_article_authors",
        mysql_author_coverage_daily_table="t_news_author_coverage_daily",
        mysql_connect_timeout_seconds=5,
        article_ttl_days=30,
        poll_interval_seconds=900,
        http_timeout_seconds=15,
        limit_per_feed=20,
        max_age_days=3,
        author_detail_backfill_enabled=True,
        author_detail_backfill_batch_size=30,
        author_detail_backfill_sources=("cna", "storm", "newtalk", "ltn", "ettoday", "tvbs", "ebc", "ctee", "pts"),
        author_detail_backfill_sleep_seconds=0.05,
        topic_llm_enabled=True,
        topic_llm_provider_order=("openai", "anthropic"),
        topic_llm_timeout_seconds=20,
        topic_llm_batch_size=50,
        topic_llm_min_confidence=0.55,
        topic_openai_model="gpt-5-nano",
        topic_openai_api_base="https://api.openai.com/v1",
        topic_openai_api_key="openai-key",
        topic_anthropic_model="claude-haiku-4-5-20251001",
        topic_anthropic_api_base="https://api.anthropic.com",
        topic_anthropic_api_key="anthropic-key",
    )
    base.update(overrides)
    return NewsPlatformSettings(**base)


class TopicLlmClassifierTests(unittest.TestCase):
    def test_openai_result_maps_to_topic(self):
        body = json.dumps(
            {
                "output_text": json.dumps(
                    {"topic_id": "fraud", "confidence": 0.82, "reason": "摘要提到被詐騙"}
                )
            },
            ensure_ascii=False,
        )
        with patch("news_platform.topic_llm._post_json", return_value=body) as post:
            result = TopicLlmClassifier(_settings()).classify(title="又有人受害", summary="民眾遭詐騙")

        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.topics[0]["topic_id"], "fraud")
        self.assertEqual(result.topics[0]["source"], "llm")
        self.assertEqual(result.topics[0]["provider"], "openai")
        self.assertEqual(post.call_count, 1)

    def test_falls_back_to_anthropic_when_openai_fails(self):
        anthropic_body = json.dumps(
            {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "topic_fallback",
                        "input": {
                            "topic_id": "housing_justice",
                            "confidence": 0.77,
                            "reason": "摘要提到買不起房",
                        },
                    }
                ]
            },
            ensure_ascii=False,
        )

        def fake_post(*, headers, **kwargs):
            if "Authorization" in headers:
                raise RuntimeError("openai down")
            return anthropic_body

        with patch("news_platform.topic_llm._post_json", side_effect=fake_post):
            result = TopicLlmClassifier(_settings()).classify(title="青年壓力", summary="房價高買不起房")

        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.model, "claude-haiku-4-5-20251001")
        self.assertEqual(result.topics[0]["topic_id"], "housing_justice")

    def test_low_confidence_returns_empty_topics(self):
        body = json.dumps(
            {
                "output_text": json.dumps(
                    {"topic_id": "fraud", "confidence": 0.2, "reason": "證據不足"}
                )
            },
            ensure_ascii=False,
        )
        with patch("news_platform.topic_llm._post_json", return_value=body):
            result = TopicLlmClassifier(_settings()).classify(title="不明事件", summary=None)

        self.assertEqual(result.topics, [])
        self.assertEqual(result.raw_topic_id, "fraud")

    def test_extract_text_helpers(self):
        openai_payload = {"output": [{"content": [{"type": "output_text", "text": "{\"x\":1}"}]}]}
        anthropic_payload = {"content": [{"type": "text", "text": "{\"x\":2}"}]}
        self.assertEqual(_extract_openai_text(openai_payload), "{\"x\":1}")
        self.assertEqual(_extract_anthropic_text(anthropic_payload), "{\"x\":2}")


if __name__ == "__main__":
    unittest.main()
