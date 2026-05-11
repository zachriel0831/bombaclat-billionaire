"""LLM fallback classifier for Taiwan news topics."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from news_platform.config import NewsPlatformSettings
from news_platform.topics import TOPIC_REGISTRY, TopicSpec


logger = logging.getLogger(__name__)


class TopicLlmUnavailable(RuntimeError):
    """Raised when all configured LLM providers are unavailable."""


@dataclass(frozen=True)
class TopicLlmResult:
    topics: list[dict[str, object]]
    provider: str
    model: str
    raw_topic_id: str
    confidence: float
    reason: str


class TopicLlmClassifier:
    def __init__(self, settings: NewsPlatformSettings, *, topics: list[TopicSpec] | None = None) -> None:
        self._provider_order = settings.topic_llm_provider_order
        self._timeout_seconds = settings.topic_llm_timeout_seconds
        self._min_confidence = settings.topic_llm_min_confidence
        self._openai_model = settings.topic_openai_model
        self._openai_api_base = settings.topic_openai_api_base
        self._openai_api_key = settings.topic_openai_api_key
        self._anthropic_model = settings.topic_anthropic_model
        self._anthropic_api_base = settings.topic_anthropic_api_base
        self._anthropic_api_key = settings.topic_anthropic_api_key
        self._topics = topics or TOPIC_REGISTRY
        self._topic_by_id = {spec.topic_id: spec for spec in self._topics}

    def classify(self, *, title: str, summary: str | None) -> TopicLlmResult:
        errors: list[str] = []
        for provider in self._provider_order:
            if provider == "openai":
                if not self._openai_api_key:
                    errors.append("openai:missing_api_key")
                    continue
                try:
                    payload = self._call_openai(title=title, summary=summary)
                    return self._build_result(payload, provider="openai", model=self._openai_model)
                except Exception as exc:
                    logger.warning("OpenAI topic fallback failed: %s", exc)
                    errors.append(f"openai:{type(exc).__name__}")
                    continue
            if provider == "anthropic":
                if not self._anthropic_api_key:
                    errors.append("anthropic:missing_api_key")
                    continue
                try:
                    payload = self._call_anthropic(title=title, summary=summary)
                    return self._build_result(payload, provider="anthropic", model=self._anthropic_model)
                except Exception as exc:
                    logger.warning("Anthropic topic fallback failed: %s", exc)
                    errors.append(f"anthropic:{type(exc).__name__}")
                    continue
        raise TopicLlmUnavailable(";".join(errors) or "no_provider_configured")

    def _call_openai(self, *, title: str, summary: str | None) -> dict[str, Any]:
        url = f"{self._openai_api_base.rstrip('/')}/responses"
        payload: dict[str, Any] = {
            "model": self._openai_model,
            "instructions": _SYSTEM_PROMPT,
            "input": _build_user_prompt(title=title, summary=summary, topics=self._topics),
            "max_output_tokens": 220,
            "reasoning": {"effort": "minimal"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "topic_fallback",
                    "strict": True,
                    "schema": _response_schema(self._topics),
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "news-platform-topic-fallback/1.0",
        }
        try:
            body = _post_json(url=url, headers=headers, payload=payload, timeout_seconds=self._timeout_seconds)
        except HTTPError as exc:
            if exc.code == 400 and payload.pop("reasoning", None) is not None:
                body = _post_json(url=url, headers=headers, payload=payload, timeout_seconds=self._timeout_seconds)
            else:
                raise
        parsed = json.loads(body)
        text = _extract_openai_text(parsed)
        if not text:
            raise RuntimeError("OpenAI topic response has no output text")
        return _loads_json_object(text)

    def _call_anthropic(self, *, title: str, summary: str | None) -> dict[str, Any]:
        url = f"{self._anthropic_api_base.rstrip('/')}/v1/messages"
        schema = _response_schema(self._topics)
        payload = {
            "model": self._anthropic_model,
            "max_tokens": 220,
            "temperature": 0,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": _build_user_prompt(title=title, summary=summary, topics=self._topics),
                }
            ],
            "tools": [
                {
                    "name": "topic_fallback",
                    "description": "Return the article topic classification.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": "topic_fallback"},
        }
        headers = {
            "x-api-key": self._anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "news-platform-topic-fallback/1.0",
        }
        body = _post_json(url=url, headers=headers, payload=payload, timeout_seconds=self._timeout_seconds)
        parsed = json.loads(body)
        for block in parsed.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "topic_fallback":
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    return tool_input
        text = _extract_anthropic_text(parsed)
        if not text:
            raise RuntimeError("Anthropic topic response has no tool input or text")
        return _loads_json_object(text)

    def _build_result(self, payload: dict[str, Any], *, provider: str, model: str) -> TopicLlmResult:
        raw_topic_id = str(payload.get("topic_id") or "none").strip()
        confidence = _clamp_float(payload.get("confidence"), default=0.0)
        reason = _short_reason(str(payload.get("reason") or ""))
        spec = self._topic_by_id.get(raw_topic_id)
        if spec is None or confidence < self._min_confidence:
            return TopicLlmResult(
                topics=[],
                provider=provider,
                model=model,
                raw_topic_id=raw_topic_id,
                confidence=confidence,
                reason=reason,
            )
        return TopicLlmResult(
            topics=[
                {
                    "topic_id": spec.topic_id,
                    "label": spec.label,
                    "score": round(confidence, 2),
                    "source": "llm",
                    "provider": provider,
                    "model": model,
                    "reason": reason,
                }
            ],
            provider=provider,
            model=model,
            raw_topic_id=raw_topic_id,
            confidence=confidence,
            reason=reason,
        )


_SYSTEM_PROMPT = (
    "你是台灣新聞議題分類器。只根據標題與摘要判斷。"
    "若證據不足或不屬於清單議題，選 none。"
    "回傳必須符合指定 JSON schema，不要輸出解釋文字。"
)


def _build_user_prompt(*, title: str, summary: str | None, topics: list[TopicSpec]) -> str:
    topic_lines = "\n".join(f"- {spec.topic_id}: {spec.label}" for spec in topics)
    return (
        "請將這篇新聞分到最適合的一個議題，或選 none。\n\n"
        f"議題清單：\n{topic_lines}\n- none: 以上皆非或證據不足\n\n"
        f"標題：{title or ''}\n"
        f"摘要：{summary or ''}\n\n"
        "輸出欄位：topic_id, confidence, reason。confidence 介於 0 到 1。"
    )


def _response_schema(topics: list[TopicSpec]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "topic_id": {
                "type": "string",
                "enum": [spec.topic_id for spec in topics] + ["none"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "reason": {
                "type": "string",
                "maxLength": 120,
            },
        },
        "required": ["topic_id", "confidence", "reason"],
    }


def _post_json(*, url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: int) -> str:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, method="POST", data=data)
    for key, value in headers.items():
        req.add_header(key, value)
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        logger.debug("Topic LLM HTTP ok elapsed=%.2fs", time.perf_counter() - started)
        return body
    except HTTPError:
        logger.warning("Topic LLM HTTP error elapsed=%.2fs", time.perf_counter() - started)
        raise
    except URLError as exc:
        raise RuntimeError(f"Topic LLM URL error: {exc}") from exc


def _extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts).strip()


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts).strip()


def _loads_json_object(text: str) -> dict[str, Any]:
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("topic LLM response is not a JSON object")
    return parsed


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _short_reason(value: str) -> str:
    text = " ".join(value.split())
    return text[:120]
