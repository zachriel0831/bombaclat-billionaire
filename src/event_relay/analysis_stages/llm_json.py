"""JSON-mode LLM helper for multi-stage analysis.

Provides ``call_llm_json`` which wraps the existing OpenAI Responses API and
Anthropic Messages helpers from ``event_relay.weekly_summary`` but coerces the
model to return schema-valid JSON:

* OpenAI: Responses API ``text.format={"type":"json_schema","strict":true}``.
* Anthropic: ``tools=[...]`` + ``tool_choice={"type":"tool","name":"..."}`` so
  the model must call a single tool whose ``input_schema`` matches our schema.

On the first response, the payload is locally re-validated with
``schemas.validate_against_schema``. If validation fails, one retry is issued
with the validator error appended to the user prompt. If the second attempt
still fails, ``SchemaValidationError`` is raised so the orchestrator can log
the failure and decide whether to fall back to the legacy single-call path.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from event_relay.analysis_stages.schemas import (
    SchemaValidationError,
    validate_against_schema,
)
from event_relay.prompt_assets import (
    TokenUsage,
    build_anthropic_system_blocks,
    extract_usage_anthropic,
    extract_usage_openai,
    is_cacheable,
)
from event_relay.weekly_summary import (
    _extract_text_from_anthropic,
    _extract_text_from_response,
    _llm_timeout_seconds,
    _openai_model_supports_temperature,
)


logger = logging.getLogger(__name__)


class JsonModeUnavailable(RuntimeError):
    """The provider rejected JSON-mode parameters for this model."""


def call_llm_json(
    *,
    provider: str,
    api_base: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    schema_name: str,
    max_retries: int = 1,
) -> tuple[dict[str, Any], str, TokenUsage]:
    """Call the LLM and return ``(parsed_json, raw_text, usage)``.

    Re-prompts once with the validation error if the first response is invalid.
    Token usage from the *last* call is returned (a successful retry's usage,
    or the failed attempt's usage if retries are exhausted).
    """
    provider_key = (provider or "").strip().lower()
    prompt = user_prompt
    last_error: str | None = None
    last_usage: TokenUsage | None = None

    # JSON mode 先讓模型生成，再做本地 schema 驗證。
    # 驗證失敗時不是立刻放棄，而是把 validator error 回灌給模型重試一次。
    for attempt in range(max_retries + 1):
        if provider_key == "anthropic":
            raw_text, last_usage = _call_anthropic_tool(
                api_base=api_base,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                schema=schema,
                schema_name=schema_name,
            )
        else:
            raw_text, last_usage = _call_openai_structured(
                api_base=api_base,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                schema=schema,
                schema_name=schema_name,
            )

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            last_error = f"response was not valid JSON: {exc}"
            logger.warning(
                "Stage %s attempt %d: invalid JSON (%s); raw=%s",
                schema_name,
                attempt + 1,
                exc,
                raw_text[:400],
            )
            prompt = _append_retry_hint(user_prompt, last_error)
            continue

        try:
            validate_against_schema(parsed, schema)
        except SchemaValidationError as exc:
            last_error = f"schema validation failed: {exc}"
            logger.warning(
                "Stage %s attempt %d: %s",
                schema_name,
                attempt + 1,
                last_error,
            )
            prompt = _append_retry_hint(user_prompt, last_error)
            continue

        return parsed, raw_text, last_usage

    raise SchemaValidationError(
        f"stage {schema_name!r} exhausted retries; last error: {last_error}"
    )


def _append_retry_hint(original_user_prompt: str, error_message: str) -> str:
    """執行 append retry hint 的主要流程。"""
    return (
        f"{original_user_prompt}\n\n"
        "Your previous response did not satisfy the required schema.\n"
        f"Validator error: {error_message}\n"
        "Return a corrected JSON object that satisfies the schema exactly."
    )


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], provider_label: str) -> str:
    """送出 post json 對應的資料或結果。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, method="POST", data=data)
    for key, value in headers.items():
        req.add_header(key, value)

    timeout_seconds = _llm_timeout_seconds(120)
    started = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        logger.info(
            "[LLM_HTTP] provider=%s mode=json elapsed=%.2fs timeout=%ss status=ok",
            provider_label,
            elapsed,
            timeout_seconds,
        )
        return body
    except HTTPError as exc:
        elapsed = time.perf_counter() - started
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        logger.warning(
            "[LLM_HTTP] provider=%s mode=json elapsed=%.2fs timeout=%ss status=http_error code=%s",
            provider_label,
            elapsed,
            timeout_seconds,
            exc.code,
        )
        # 400/403/404 常是「這模型/帳號不接受這種 json-mode 參數」，
        # 往上拋專門例外，讓 orchestrator 有機會改走 fallback，而不是誤判成暫時性網路錯誤。
        if exc.code in (400, 403, 404):
            raise JsonModeUnavailable(
                f"{provider_label} rejected json-mode payload: status={exc.code} body={body[:400]}"
            ) from exc
        raise RuntimeError(
            f"{provider_label} HTTPError status={exc.code} body={body[:800]}"
        ) from exc
    except URLError as exc:
        elapsed = time.perf_counter() - started
        logger.warning(
            "[LLM_HTTP] provider=%s mode=json elapsed=%.2fs timeout=%ss status=url_error error=%s",
            provider_label,
            elapsed,
            timeout_seconds,
            exc,
        )
        raise RuntimeError(f"{provider_label} URLError: {exc}") from exc


def _call_openai_structured(
    *,
    api_base: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, TokenUsage]:
    """OpenAI structured-output call. Returns ``(raw_text, usage)``."""
    url = f"{api_base.rstrip('/')}/responses"
    payload: dict[str, Any] = {
        "model": model,
        "instructions": system_prompt,
        "input": user_prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": False,
            }
        },
    }
    if _openai_model_supports_temperature(model):
        payload["temperature"] = 0.2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "news-collector-market-analysis/1.0",
    }
    body = _post_json(url=url, headers=headers, payload=payload, provider_label="OpenAI")
    parsed = json.loads(body)
    text = _extract_text_from_response(parsed)
    if not text:
        raise RuntimeError("OpenAI structured response has no output text")
    usage = extract_usage_openai(parsed, model)
    return text.strip(), usage


def _call_anthropic_tool(
    *,
    api_base: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    schema_name: str,
) -> tuple[str, TokenUsage]:
    """Anthropic tool-use call. Returns ``(raw_text, usage)``.

    Wraps the system prompt into cacheable blocks (REQ-016) when large enough
    so the static prefix can land in the prompt cache.
    """
    url = f"{api_base.rstrip('/')}/v1/messages"
    system_value: Any = (
        build_anthropic_system_blocks(system_prompt)
        if isinstance(system_prompt, str) and is_cacheable(system_prompt)
        else system_prompt
    )
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_value,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.2,
        "tools": [
            {
                "name": schema_name,
                "description": f"Return the {schema_name} payload.",
                "input_schema": schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": schema_name},
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "user-agent": "news-collector-market-analysis/1.0",
    }
    body = _post_json(url=url, headers=headers, payload=payload, provider_label="Anthropic")
    parsed = json.loads(body)
    usage = extract_usage_anthropic(parsed, model)

    # Anthropic 理想情況會走 tool_use；若模型回成一般文字，仍嘗試把 text 當 JSON 解析，
    # 讓上層統一走同一套 schema 驗證與 retry。
    for block in parsed.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == schema_name:
            tool_input = block.get("input")
            if isinstance(tool_input, dict):
                return json.dumps(tool_input, ensure_ascii=False), usage

    fallback_text = _extract_text_from_anthropic(parsed)
    if fallback_text:
        return fallback_text, usage
    raise RuntimeError("Anthropic tool response has no tool_use block")
