"""輕量 HTTP helper — 僅 GET，預設 UA + 逾時。"""

from __future__ import annotations

import ssl
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    # 不附假聯絡方式：站方若需協商找不到比假信箱更好；保留 UA 識別性即可。
    "User-Agent": "news-platform/0.1",
    "Accept": "application/json, application/xml;q=0.9, text/xml;q=0.8, text/html;q=0.7, */*;q=0.5",
}


def http_get_text(
    url: str,
    params: dict[str, str | int] | None = None,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
    verify_ssl: bool = True,
) -> str:
    full_url = f"{url}?{urlencode(params)}" if params else url
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)
    req = Request(full_url, headers=request_headers)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read().decode("utf-8", errors="replace")


def http_get_bytes(
    url: str,
    params: dict[str, str | int] | None = None,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
    verify_ssl: bool = True,
) -> bytes:
    """回傳原始 bytes，讓 ElementTree 自行依 XML declaration 決定編碼。

    比 ``http_get_text`` 更適合餵給 RSS / Atom 解析，避免 Big5 / GB18030 被
    UTF-8 decoder 強制亂碼化。
    """
    full_url = f"{url}?{urlencode(params)}" if params else url
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)
    req = Request(full_url, headers=request_headers)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()
