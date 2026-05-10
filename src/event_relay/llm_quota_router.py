"""Quota-aware provider/model routing for market analysis.

Provider billing APIs expose cost/usage, not a perfect per-request "remaining
quota" oracle. This module uses Admin API cost reports when a monthly budget is
configured, then selects the first provider/model that is still within budget.
If the Admin API is unavailable, the decision records the gap and can either
continue or block based on env policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)
ROUTER_VERSION = "llm-quota-router-v1"


@dataclass(frozen=True)
class LlmRouteCandidate:
    provider: str
    model: str
    api_base: str
    api_key_file: str
    api_key: str | None


@dataclass(frozen=True)
class QuotaStatus:
    provider: str
    status: str
    checked: bool
    acceptable: bool
    reason: str
    spent_usd: float | None = None
    monthly_budget_usd: float | None = None
    remaining_usd: float | None = None
    min_remaining_usd: float | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "checked": self.checked,
            "acceptable": self.acceptable,
            "reason": self.reason,
            "spent_usd": self.spent_usd,
            "monthly_budget_usd": self.monthly_budget_usd,
            "remaining_usd": self.remaining_usd,
            "min_remaining_usd": self.min_remaining_usd,
            "source": self.source,
        }


@dataclass(frozen=True)
class ModelRouteDecision:
    selected: LlmRouteCandidate
    enabled: bool
    preferred_provider: str
    provider_order: list[str]
    statuses: list[QuotaStatus] = field(default_factory=list)
    fallback_reason: str | None = None
    version: str = ROUTER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "enabled": self.enabled,
            "preferred_provider": self.preferred_provider,
            "provider_order": self.provider_order,
            "selected_provider": self.selected.provider,
            "selected_model": self.selected.model,
            "fallback_reason": self.fallback_reason,
            "statuses": [status.to_dict() for status in self.statuses],
        }


def router_enabled_from_env() -> bool:
    raw = os.getenv("MARKET_ANALYSIS_MODEL_ROUTER_ENABLED")
    if raw is None or raw.strip() == "":
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def select_market_analysis_model(
    *,
    preferred: LlmRouteCandidate,
    alternatives: list[LlmRouteCandidate],
    now_utc: datetime | None = None,
    enabled: bool | None = None,
) -> ModelRouteDecision:
    """Select a provider/model using monthly cost checks when available."""
    now = now_utc or datetime.now(timezone.utc)
    is_enabled = router_enabled_from_env() if enabled is None else bool(enabled)
    candidates = _ordered_candidates(preferred, alternatives)
    preferred_provider = _provider_key(preferred.provider)
    provider_order = [_provider_key(candidate.provider) for candidate in candidates]

    if not is_enabled:
        return ModelRouteDecision(
            selected=preferred,
            enabled=False,
            preferred_provider=preferred_provider,
            provider_order=provider_order,
            statuses=[
                QuotaStatus(
                    provider=preferred_provider,
                    status="disabled",
                    checked=False,
                    acceptable=bool(preferred.api_key),
                    reason="router_disabled",
                )
            ],
        )

    statuses_by_provider: dict[str, QuotaStatus] = {}
    for candidate in candidates:
        provider = _provider_key(candidate.provider)
        if provider not in statuses_by_provider:
            statuses_by_provider[provider] = check_provider_quota(candidate, now)

    selected = preferred
    fallback_reason: str | None = None
    for candidate in candidates:
        status = statuses_by_provider[_provider_key(candidate.provider)]
        if candidate.api_key and status.acceptable:
            selected = candidate
            if _provider_key(selected.provider) != preferred_provider or selected.model != preferred.model:
                fallback_reason = statuses_by_provider[preferred_provider].reason
            break
    else:
        fallback_reason = "no_acceptable_provider"

    return ModelRouteDecision(
        selected=selected,
        enabled=True,
        preferred_provider=preferred_provider,
        provider_order=provider_order,
        statuses=list(statuses_by_provider.values()),
        fallback_reason=fallback_reason,
    )


def check_provider_quota(candidate: LlmRouteCandidate, now_utc: datetime | None = None) -> QuotaStatus:
    provider = _provider_key(candidate.provider)
    if not candidate.api_key:
        return QuotaStatus(
            provider=provider,
            status="missing_api_key",
            checked=False,
            acceptable=False,
            reason="missing_runtime_api_key",
        )

    budget = _provider_budget(provider)
    min_remaining = _provider_min_remaining(provider)
    if budget is None:
        return QuotaStatus(
            provider=provider,
            status="unknown",
            checked=False,
            acceptable=True,
            reason="monthly_budget_not_configured",
            min_remaining_usd=min_remaining,
        )

    admin_key = _provider_admin_key(provider)
    if not admin_key:
        return QuotaStatus(
            provider=provider,
            status="unknown",
            checked=False,
            acceptable=not _require_quota_check(),
            reason="admin_api_key_not_configured",
            monthly_budget_usd=budget,
            min_remaining_usd=min_remaining,
        )

    try:
        spent = (
            fetch_openai_month_to_date_cost_usd(candidate.api_base, admin_key, now_utc)
            if provider == "openai"
            else fetch_anthropic_month_to_date_cost_usd(candidate.api_base, admin_key, now_utc)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM quota check failed provider=%s error=%s", provider, exc)
        return QuotaStatus(
            provider=provider,
            status="check_error",
            checked=True,
            acceptable=not _require_quota_check(),
            reason=str(exc)[:300],
            monthly_budget_usd=budget,
            min_remaining_usd=min_remaining,
            source=f"{provider}_admin_cost_api",
        )

    remaining = round(budget - spent, 6)
    acceptable = remaining >= min_remaining
    return QuotaStatus(
        provider=provider,
        status="ok" if acceptable else "budget_exhausted",
        checked=True,
        acceptable=acceptable,
        reason="within_budget" if acceptable else "remaining_below_minimum",
        spent_usd=round(spent, 6),
        monthly_budget_usd=budget,
        remaining_usd=remaining,
        min_remaining_usd=min_remaining,
        source=f"{provider}_admin_cost_api",
    )


def fetch_openai_month_to_date_cost_usd(
    api_base: str,
    admin_api_key: str,
    now_utc: datetime | None = None,
) -> float:
    now = _as_utc(now_utc)
    start = _month_start(now)
    params = urlencode(
        {
            "start_time": int(start.timestamp()),
            "end_time": int(now.timestamp()),
            "bucket_width": "1d",
            "limit": 31,
        }
    )
    url = f"{api_base.rstrip('/')}/organization/costs?{params}"
    body = _get_json(url, {"Authorization": f"Bearer {admin_api_key}", "Content-Type": "application/json"})
    return _sum_openai_cost_response(body)


def fetch_anthropic_month_to_date_cost_usd(
    api_base: str,
    admin_api_key: str,
    now_utc: datetime | None = None,
) -> float:
    now = _as_utc(now_utc)
    start = _month_start(now)
    params = urlencode(
        {
            "starting_at": _iso_z(start),
            "ending_at": _iso_z(now),
            "bucket_width": "1d",
            "limit": 31,
        }
    )
    url = f"{api_base.rstrip('/')}/v1/organizations/cost_report?{params}"
    body = _get_json(
        url,
        {
            "x-api-key": admin_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    return _sum_anthropic_cost_response(body)


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = Request(url, method="GET")
    for key, value in headers.items():
        req.add_header(key, value)
    req.add_header("User-Agent", "news-collector-llm-quota-router/1.0")
    timeout_seconds = _router_timeout_seconds()
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"HTTP status={exc.code} body={body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error={exc}") from exc
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError("cost API returned non-object JSON")
    return parsed


def _sum_openai_cost_response(body: dict[str, Any]) -> float:
    total = 0.0
    for bucket in body.get("data") or []:
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("results") or []:
            if not isinstance(item, dict):
                continue
            amount = item.get("amount")
            if isinstance(amount, dict):
                total += _to_float(amount.get("value"))
    return total


def _sum_anthropic_cost_response(body: dict[str, Any]) -> float:
    total = 0.0
    for bucket in body.get("data") or []:
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("results") or []:
            if not isinstance(item, dict):
                continue
            total += _to_float(item.get("amount"))
    return total


def _ordered_candidates(
    preferred: LlmRouteCandidate,
    alternatives: list[LlmRouteCandidate],
) -> list[LlmRouteCandidate]:
    seen: set[tuple[str, str]] = set()
    by_provider: dict[str, list[LlmRouteCandidate]] = {}
    for candidate in [preferred, *alternatives]:
        key = (_provider_key(candidate.provider), candidate.model)
        if key in seen:
            continue
        seen.add(key)
        by_provider.setdefault(key[0], []).append(candidate)

    explicit_order = [
        _provider_key(item)
        for item in (os.getenv("MARKET_ANALYSIS_PROVIDER_ORDER") or "").split(",")
        if item.strip()
    ]
    order = explicit_order or ["openai", "anthropic"]
    preferred_key = _provider_key(preferred.provider)
    if preferred_key not in order:
        order.insert(0, preferred_key)
    for provider in by_provider:
        if provider not in order:
            order.append(provider)

    ordered: list[LlmRouteCandidate] = []
    for provider in order:
        ordered.extend(by_provider.get(provider, []))
    return ordered or [preferred]


def _provider_key(value: str) -> str:
    normalized = (value or "").strip().lower()
    return "anthropic" if normalized in {"anthropic", "claude"} else "openai"


def _provider_budget(provider: str) -> float | None:
    specific = os.getenv(f"MARKET_ANALYSIS_{provider.upper()}_MONTHLY_BUDGET_USD")
    raw = specific if specific is not None else os.getenv("MARKET_ANALYSIS_LLM_MONTHLY_BUDGET_USD")
    value = _to_float(raw)
    return value if value > 0 else None


def _provider_min_remaining(provider: str) -> float:
    specific = os.getenv(f"MARKET_ANALYSIS_{provider.upper()}_MIN_REMAINING_USD")
    raw = specific if specific is not None else os.getenv("MARKET_ANALYSIS_LLM_MIN_REMAINING_USD")
    return max(0.0, _to_float(raw))


def _provider_admin_key(provider: str) -> str:
    if provider == "anthropic":
        return (
            os.getenv("MARKET_ANALYSIS_ANTHROPIC_ADMIN_KEY")
            or os.getenv("ANTHROPIC_ADMIN_KEY")
            or os.getenv("ANTHROPIC_ADMIN_API_KEY")
            or ""
        ).strip()
    return (
        os.getenv("MARKET_ANALYSIS_OPENAI_ADMIN_KEY")
        or os.getenv("OPENAI_ADMIN_KEY")
        or ""
    ).strip()


def _require_quota_check() -> bool:
    raw = os.getenv("MARKET_ANALYSIS_REQUIRE_QUOTA_CHECK")
    return bool(raw and raw.strip().lower() in {"1", "true", "yes", "on"})


def _router_timeout_seconds() -> int:
    raw = os.getenv("MARKET_ANALYSIS_MODEL_ROUTER_TIMEOUT_SECONDS", "8")
    try:
        value = int(raw)
    except ValueError:
        return 8
    return max(2, min(value, 30))


def _as_utc(value: datetime | None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
