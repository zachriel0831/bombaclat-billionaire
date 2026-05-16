from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import unittest
from unittest.mock import patch

from event_relay.llm_quota_router import (
    LlmRouteCandidate,
    fetch_anthropic_month_to_date_cost_usd,
    fetch_openai_month_to_date_cost_usd,
    select_market_analysis_model,
)


class _FakeResp:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LlmQuotaRouterTests(unittest.TestCase):
    def test_fetch_openai_cost_sums_result_amounts(self) -> None:
        payload = {
            "data": [
                {"results": [{"amount": {"value": 1.25}}, {"amount": {"value": "2.75"}}]},
                {"results": [{"amount": {"value": 3}}]},
            ]
        }

        def fake_urlopen(req, timeout):
            self.assertIn("/organization/costs?", req.full_url)
            self.assertEqual(timeout, 8)
            return _FakeResp(payload)

        with patch("event_relay.llm_quota_router.urlopen", side_effect=fake_urlopen):
            cost = fetch_openai_month_to_date_cost_usd(
                "https://api.openai.com/v1",
                "admin-key",
                datetime(2026, 5, 7, 8, 30, tzinfo=timezone.utc),
            )

        self.assertEqual(cost, 7.0)

    def test_fetch_anthropic_cost_sums_result_amounts(self) -> None:
        payload = {"data": [{"results": [{"amount": "4.5"}, {"amount": 0.5}]}]}

        def fake_urlopen(req, timeout):
            self.assertIn("/v1/organizations/cost_report?", req.full_url)
            return _FakeResp(payload)

        with patch("event_relay.llm_quota_router.urlopen", side_effect=fake_urlopen):
            cost = fetch_anthropic_month_to_date_cost_usd(
                "https://api.anthropic.com",
                "admin-key",
                datetime(2026, 5, 7, 8, 30, tzinfo=timezone.utc),
            )

        self.assertEqual(cost, 5.0)

    def test_select_model_falls_back_when_preferred_budget_exhausted(self) -> None:
        openai = LlmRouteCandidate("openai", "gpt-main", "https://api.openai.com/v1", "", "openai-key")
        anthropic = LlmRouteCandidate("anthropic", "claude-main", "https://api.anthropic.com", "", "claude-key")
        env = {
            "MARKET_ANALYSIS_OPENAI_MONTHLY_BUDGET_USD": "10",
            "MARKET_ANALYSIS_ANTHROPIC_MONTHLY_BUDGET_USD": "10",
            "MARKET_ANALYSIS_OPENAI_ADMIN_KEY": "openai-admin",
            "MARKET_ANALYSIS_ANTHROPIC_ADMIN_KEY": "anthropic-admin",
        }

        with patch.dict(os.environ, env, clear=False):
            with patch("event_relay.llm_quota_router.fetch_openai_month_to_date_cost_usd", return_value=11.0):
                with patch("event_relay.llm_quota_router.fetch_anthropic_month_to_date_cost_usd", return_value=2.0):
                    decision = select_market_analysis_model(
                        preferred=openai,
                        alternatives=[anthropic],
                        now_utc=datetime(2026, 5, 7, tzinfo=timezone.utc),
                    )

        self.assertEqual(decision.selected.provider, "anthropic")
        self.assertEqual(decision.selected.model, "claude-main")
        self.assertEqual(decision.statuses[0].status, "budget_exhausted")
        self.assertEqual(decision.statuses[1].status, "ok")

    def test_select_model_keeps_preferred_when_budget_not_configured(self) -> None:
        openai = LlmRouteCandidate("openai", "gpt-main", "https://api.openai.com/v1", "", "openai-key")
        anthropic = LlmRouteCandidate("anthropic", "claude-main", "https://api.anthropic.com", "", "claude-key")
        env = {
            "MARKET_ANALYSIS_OPENAI_MONTHLY_BUDGET_USD": "",
            "MARKET_ANALYSIS_ANTHROPIC_MONTHLY_BUDGET_USD": "",
        }

        with patch.dict(os.environ, env, clear=False):
            decision = select_market_analysis_model(
                preferred=openai,
                alternatives=[anthropic],
                now_utc=datetime(2026, 5, 7, tzinfo=timezone.utc),
            )

        self.assertEqual(decision.selected.provider, "openai")
        self.assertEqual(decision.statuses[0].status, "unknown")
        self.assertEqual(decision.statuses[0].reason, "monthly_budget_not_configured")

    def test_select_model_keeps_preferred_provider_first_without_explicit_order(self) -> None:
        openai = LlmRouteCandidate("openai", "gpt-main", "https://api.openai.com/v1", "", "openai-key")
        anthropic = LlmRouteCandidate("anthropic", "claude-main", "https://api.anthropic.com", "", "claude-key")

        with patch.dict(os.environ, {"MARKET_ANALYSIS_PROVIDER_ORDER": ""}, clear=False):
            decision = select_market_analysis_model(
                preferred=anthropic,
                alternatives=[openai],
                now_utc=datetime(2026, 5, 7, tzinfo=timezone.utc),
            )

        self.assertEqual(decision.provider_order[:2], ["anthropic", "openai"])
        self.assertEqual(decision.selected.provider, "anthropic")

    def test_select_model_explicit_order_can_prefer_openai(self) -> None:
        openai = LlmRouteCandidate("openai", "gpt-main", "https://api.openai.com/v1", "", "openai-key")
        anthropic = LlmRouteCandidate("anthropic", "claude-main", "https://api.anthropic.com", "", "claude-key")

        with patch.dict(os.environ, {"MARKET_ANALYSIS_PROVIDER_ORDER": "openai,anthropic"}, clear=False):
            decision = select_market_analysis_model(
                preferred=anthropic,
                alternatives=[openai],
                now_utc=datetime(2026, 5, 7, tzinfo=timezone.utc),
            )

        self.assertEqual(decision.provider_order[:2], ["openai", "anthropic"])
        self.assertEqual(decision.selected.provider, "openai")


if __name__ == "__main__":
    unittest.main()
