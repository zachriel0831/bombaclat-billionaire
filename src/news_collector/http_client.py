"""Shared HTTP helpers used by every news-collector source.

Thin wrappers around ``urllib`` providing JSON / text fetch with optional
headers, sane User-Agent, and a single retry/timeout policy."""

from __future__ import annotations

# 共用 HTTP Client：提供含標頭的文字與 JSON 讀取工具。
import json
import re
import ssl
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    "User-Agent": "news-collector/0.1 (+https://local.dev)",
    "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def http_get_text(
    url: str,
    params: dict[str, str | int] | None = None,
    timeout: int = 15,
    verify_ssl: bool = True,
) -> str:
    """執行 http get text 的主要流程。"""
    return http_get_text_with_headers(
        url=url,
        params=params,
        timeout=timeout,
        headers=None,
        verify_ssl=verify_ssl,
    )


def http_get_text_with_headers(
    url: str,
    params: dict[str, str | int] | None = None,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
    verify_ssl: bool = True,
) -> str:
    """執行 http get text with headers 的主要流程。"""
    full_url = f"{url}?{urlencode(params)}" if params else url
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)
    req = Request(full_url, headers=request_headers)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urlopen(req, timeout=timeout, context=context) as resp:
        payload = resp.read()
        charset = _detect_charset(resp, payload)
        return payload.decode(charset, errors="replace")


def http_get_json(url: str, params: dict[str, str | int] | None = None, timeout: int = 15) -> dict:
    """執行 http get json 的主要流程。"""
    return http_get_json_with_headers(url=url, params=params, timeout=timeout, headers=None)


def http_get_json_with_headers(
    url: str,
    params: dict[str, str | int] | None = None,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
) -> dict:
    """執行 http get json with headers 的主要流程。"""
    text = http_get_text_with_headers(url=url, params=params, timeout=timeout, headers=headers)
    data = json.loads(text)
    if isinstance(data, dict):
        return data
    return {"data": data}


_XML_DECLARATION_RE = re.compile(br'<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']', re.IGNORECASE)


def _detect_charset(resp: object, payload: bytes) -> str:
    headers = getattr(resp, "headers", None)
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset()
        if charset:
            return charset

    if payload.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    match = _XML_DECLARATION_RE.search(payload[:200])
    if match:
        try:
            return match.group(1).decode("ascii")
        except UnicodeDecodeError:
            pass

    return "utf-8"
